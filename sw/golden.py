"""
golden.py - a Python model of the SIMD processor (the "golden model").

It runs the same machine code as the hardware, one instruction at a time,
and records what the memory and registers should contain at the end, plus
how many instructions and clock cycles the program should take.

The testbench then compares the real hardware against these numbers. If
both agree on every memory word, every scalar register and the exact cycle
count, we can be confident the hardware is right.

This model only describes WHAT each instruction does. It knows nothing about
wires, clocks or lanes running in parallel - that is the point: it is a
completely separate description of the same behaviour.
"""

ALU_OPS = ["ADD", "SUB", "AND", "OR", "XOR", "SLL", "SRL", "SRA",
           "MUL", "SEQ", "SLT", "SLTU", "MIN", "MAX"]


def to_signed(x, bits):
    """Read a raw bit pattern as a signed number: 0xFFFF -> -1 for 16 bits."""
    x &= (1 << bits) - 1
    return x - (1 << bits) if x >> (bits - 1) else x


def alu(op, a, b, w=16):
    """What one lane computes. a and b are raw w-bit patterns."""
    mask = (1 << w) - 1
    sa, sb = to_signed(a, w), to_signed(b, w)
    shift = b % w
    name = ALU_OPS[op] if op < len(ALU_OPS) else None
    result = {
        "ADD": sa + sb,
        "SUB": sa - sb,
        "AND": a & b,
        "OR": a | b,
        "XOR": a ^ b,
        "SLL": a << shift,
        "SRL": a >> shift,
        "SRA": sa >> shift,               # Python's >> on negative numbers keeps the sign
        "MUL": sa * sb,
        "SEQ": -1 if a == b else 0,
        "SLT": -1 if sa < sb else 0,
        "SLTU": -1 if a < b else 0,
        "MIN": a if sa < sb else b,
        "MAX": b if sa < sb else a,
    }.get(name, 0)
    return result & mask


class SimdModel:
    """The processor state: registers, data memory and counters.

    Sizes match the simulation testbench: 256 instructions (the program
    counter wraps after 255) and 1,024 data-memory words (addresses wrap).
    """

    def __init__(self, lanes, w=16, dmem_words=1024):
        self.lanes, self.w = lanes, w
        self.v = [[0] * lanes for _ in range(8)]       # vector registers
        self.s = [0] * 8                               # scalar registers (32-bit)
        self.mem = [[0] * lanes for _ in range(dmem_words)]
        self.instructions = 0
        self.cycles = 0

    def run(self, program, max_steps=1_000_000):
        """Run machine code until HALT. Returns (instructions, cycles)."""
        pc = 0
        mask32 = 0xFFFFFFFF
        for _ in range(max_steps):
            # Past the end of the program counts as HALT (memory is padded with HALT).
            word = program[pc] if pc < len(program) else 0x3F << 26
            opcode = word >> 26
            rd, ra, rb = (word >> 23) & 7, (word >> 20) & 7, (word >> 17) & 7
            imm = to_signed(word & 0xFFFF, 16)
            iclass, func = opcode >> 4, opcode & 0xF
            s = self.s
            next_pc = pc + 1
            self.instructions += 1
            self.cycles += 1

            if iclass in (0, 1, 2):                       # vector ALU work
                a = self.v[ra]
                b = [s[rb] & ((1 << self.w) - 1)] * self.lanes if iclass == 1 else self.v[rb]
                out = [alu(func, a[i], b[i], self.w) for i in range(self.lanes)]
                if iclass == 2:                           # reduce: add all lanes into a scalar
                    self.write_s(rd, sum(to_signed(x, self.w) for x in out))
                else:
                    self.v[rd] = out
            elif opcode == 0x30:                          # VLD (takes one extra cycle)
                self.v[rd] = list(self.mem[self.addr(s[ra] + imm)])
                self.cycles += 1
            elif opcode == 0x31:                          # VST
                self.mem[self.addr(s[ra] + imm)] = list(self.v[rb])
            elif opcode == 0x38:                          # ADDI
                self.write_s(rd, s[ra] + imm)
            elif opcode == 0x39:                          # ADD
                self.write_s(rd, s[ra] + s[rb])
            elif opcode == 0x3C:                          # BNE
                if s[ra] != s[rb]:
                    next_pc = pc + imm
            elif opcode == 0x3F:                          # HALT
                return self.instructions, self.cycles
            pc = next_pc & 0xFF
            for i in range(8):
                s[i] &= mask32
        raise RuntimeError("program did not reach HALT")

    def write_s(self, index, val):
        if index != 0:                                    # s0 always stays 0
            self.s[index] = val & 0xFFFFFFFF

    def addr(self, a):
        return a % len(self.mem)


# ---- Memory layout helpers ---------------------------------------------------
# Element i of an array lives in vector word (i // lanes), lane (i % lanes).
# With 8 lanes, elements 0..7 share word 0, elements 8..15 share word 1, ...

def store_array(model, base, values):
    """Place a list of numbers into memory starting at vector word 'base'."""
    lanes, mask = model.lanes, (1 << model.w) - 1
    for i, x in enumerate(values):
        model.mem[base + i // lanes][i % lanes] = x & mask


def load_array(model, base, count):
    """Read 'count' signed numbers back out of memory."""
    lanes = model.lanes
    return [to_signed(model.mem[base + i // lanes][i % lanes], model.w) for i in range(count)]


def memory_hex_lines(model):
    """One hex line per memory word, lane 0 in the lowest (rightmost) digits."""
    digits = model.w // 4
    return ["".join(f"{x:0{digits}x}" for x in reversed(word)) for word in model.mem]
