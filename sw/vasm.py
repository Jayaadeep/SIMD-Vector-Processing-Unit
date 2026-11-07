"""
vasm.py - a tiny assembler for the SIMD vector processing unit.

An assembler turns human-readable instructions into the 32-bit numbers the
hardware understands. For example

    loop:  VLD  v1, A(s1)        # load one vector from memory
           VADD v3, v1, v2       # add two vectors, lane by lane
           BNE  s1, s2, loop     # jump back while s1 != s2

becomes one hex number per instruction. The Verilog testbench reads that file
into instruction memory with $readmemh.

Instruction layout (same as rtl/simd_defs.vh):

    bits 31-26  opcode     bits 25-23  rd     bits 22-20  ra
    bits 19-17  rb         bits 15-0   imm (signed 16-bit constant)

Usage:
    python3 sw/vasm.py program.s -o program.hex -D LANES=8 -D ITER=32
"""

import argparse
import re
import sys

# ALU jobs, in the same order as the ALU_* codes in rtl/simd_defs.vh.
ALU_OPS = ["ADD", "SUB", "AND", "OR", "XOR", "SLL", "SRL", "SRA",
           "MUL", "SEQ", "SLT", "SLTU", "MIN", "MAX"]

# Opcodes of class 11 (memory, scalar maths, program flow).
OP_VLD, OP_VST = 0x30, 0x31
OP_ADDI, OP_ADD = 0x38, 0x39
OP_BNE, OP_HALT = 0x3C, 0x3F

# Class prefixes: the top 2 opcode bits.
CLASS_VV, CLASS_VX, CLASS_RED = 0x00, 0x10, 0x20

IMEM_DEPTH = 256          # instruction memory size in the RTL


class AsmError(Exception):
    """A mistake in the program text, reported with its line number."""


def encode(opcode, rd=0, ra=0, rb=0, imm=0):
    """Pack the fields into one 32-bit instruction word."""
    if not -32768 <= imm <= 32767:
        raise AsmError(f"constant {imm} does not fit in 16 bits")
    return (opcode << 26) | (rd << 23) | (ra << 20) | (rb << 17) | (imm & 0xFFFF)


def reg(text, kind):
    """Turn 'v3' or 's2' into the number 3 or 2, checking the letter."""
    m = re.fullmatch(r"([vs])([0-7])", text.strip().lower())
    if not m:
        raise AsmError(f"'{text}' is not a register (v0-v7 or s0-s7)")
    if kind and m.group(1) != kind:
        raise AsmError(f"'{text}' should be a {'vector' if kind == 'v' else 'scalar'} register")
    return int(m.group(2))


def value(text, symbols):
    """Work out a constant such as 'B', 'ITER' or 'OUT+3*STRIDE'.

    Uses Python's own arithmetic with only our symbol names available.
    The programs are our own files, so this is safe enough for a course tool.
    """
    try:
        result = eval(text, {"__builtins__": {}}, dict(symbols))
    except Exception as exc:
        raise AsmError(f"cannot work out the value of '{text}' ({exc})") from None
    if not isinstance(result, int):
        raise AsmError(f"'{text}' is not a whole number (use // to divide)")
    return result


def split_mem(text):
    """Split 'A+1(s1)' into ('A+1', 's1')."""
    m = re.fullmatch(r"(.*)\(\s*(s[0-7])\s*\)", text.strip(), re.IGNORECASE)
    if not m:
        raise AsmError(f"'{text}' should look like offset(sN), e.g. A(s1)")
    return (m.group(1).strip() or "0"), m.group(2)


def clean_lines(source):
    """Remove comments and blank lines; yield (line_number, text)."""
    for number, line in enumerate(source.splitlines(), start=1):
        line = re.split(r"[#;]", line, maxsplit=1)[0].strip()
        if line:
            yield number, line


def assemble(source, symbols=None):
    """Assemble program text into a list of 32-bit instruction words."""
    symbols = dict(symbols or {})

    # Pass 1: find the address of every label, so jumps can point forwards.
    program = []                      # (line_number, text) for each instruction
    for number, line in clean_lines(source):
        while ":" in line:
            label, line = line.split(":", 1)
            label = label.strip()
            if not re.fullmatch(r"[A-Za-z_]\w*", label):
                raise AsmError(f"line {number}: '{label}' is not a valid label name")
            if label in symbols:
                raise AsmError(f"line {number}: '{label}' is already defined")
            symbols[label] = len(program)
            line = line.strip()
        if line:
            program.append((number, line))

    # Pass 2: turn every instruction into a word.
    words = []
    for address, (number, line) in enumerate(program):
        try:
            words.append(assemble_one(line, address, symbols))
        except AsmError as err:
            raise AsmError(f"line {number}: {err}  ->  {line}") from None
    if len(words) > IMEM_DEPTH:
        raise AsmError(f"program has {len(words)} instructions, memory holds {IMEM_DEPTH}")
    return words


def assemble_one(line, address, symbols):
    """Assemble a single instruction (labels already removed)."""
    parts = line.split(None, 1)
    name = parts[0].upper()
    args = [a.strip() for a in parts[1].split(",")] if len(parts) > 1 else []

    def need(count):
        if len(args) != count:
            raise AsmError(f"{name} needs {count} operands, got {len(args)}")

    # Vector ALU:  VADD vd, va, vb   (vector)   or   VADD vd, va, sb   (broadcast scalar)
    if name.startswith("V") and name[1:] in ALU_OPS:
        need(3)
        func = ALU_OPS.index(name[1:])
        third_is_scalar = args[2].strip().lower().startswith("s")
        opclass = CLASS_VX if third_is_scalar else CLASS_VV
        return encode(opclass | func, reg(args[0], "v"), reg(args[1], "v"),
                      reg(args[2], "s" if third_is_scalar else "v"))

    # Reduce:  VREDADD sd, va, vb  (sum of va[i] + vb[i]);  VDOT = VREDMUL
    if name == "VDOT":
        name = "VREDMUL"
    if name.startswith("VRED") and name[4:] in ALU_OPS:
        need(3)
        func = ALU_OPS.index(name[4:])
        return encode(CLASS_RED | func, reg(args[0], "s"), reg(args[1], "v"), reg(args[2], "v"))

    if name == "VLD":                 # VLD vd, offset(sa)
        need(2)
        offset, base = split_mem(args[1])
        return encode(OP_VLD, rd=reg(args[0], "v"), ra=reg(base, "s"), imm=value(offset, symbols))

    if name == "VST":                 # VST vb, offset(sa)
        need(2)
        offset, base = split_mem(args[1])
        return encode(OP_VST, rb=reg(args[0], "v"), ra=reg(base, "s"), imm=value(offset, symbols))

    if name == "ADDI":                # ADDI sd, sa, constant
        need(3)
        return encode(OP_ADDI, reg(args[0], "s"), reg(args[1], "s"), imm=value(args[2], symbols))

    if name == "ADD":                 # ADD sd, sa, sb
        need(3)
        return encode(OP_ADD, reg(args[0], "s"), reg(args[1], "s"), reg(args[2], "s"))

    if name == "BNE":                 # BNE sa, sb, label   (jump is relative to this instruction)
        need(3)
        target = value(args[2], symbols)
        return encode(OP_BNE, ra=reg(args[0], "s"), rb=reg(args[1], "s"), imm=target - address)

    if name == "HALT":
        need(0)
        return encode(OP_HALT)

    raise AsmError(f"unknown instruction '{name}'")


def write_hex(words, path, depth=IMEM_DEPTH):
    """Write one 8-digit hex word per line, padded with HALT to fill memory."""
    halt = encode(OP_HALT)
    padded = list(words) + [halt] * (depth - len(words))
    with open(path, "w") as f:
        f.write("\n".join(f"{w:08x}" for w in padded) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Assemble a SIMD program to hex.")
    parser.add_argument("source")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("-D", dest="defines", action="append", default=[],
                        metavar="NAME=VALUE", help="define a constant, e.g. -D ITER=32")
    args = parser.parse_args()

    symbols = {}
    for item in args.defines:
        name, equals, val = item.partition("=")
        try:
            symbols[name] = int(val, 0)
        except ValueError:
            sys.exit(f"-D {item}: write it as NAME=NUMBER, for example -D ITER=32")
        if not equals:
            sys.exit(f"-D {item}: write it as NAME=NUMBER, for example -D ITER=32")

    try:
        with open(args.source) as f:
            words = assemble(f.read(), symbols)
    except AsmError as err:
        sys.exit(f"{args.source}: {err}")
    write_hex(words, args.output)
    print(f"{args.source}: {len(words)} instructions -> {args.output}")


if __name__ == "__main__":
    main()
