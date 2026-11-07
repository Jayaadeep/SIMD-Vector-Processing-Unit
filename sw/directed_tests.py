"""
directed_tests.py - small programs that poke at the corners of the design.

The benchmark programs use the processor the normal way. These programs check
the unusual cases, where bugs like to hide:
  * writes to s0 (must be ignored, even from VDOT)
  * memory addresses past the end or below zero (they wrap around)
  * the program counter running past the last instruction (it wraps to 0)
  * two loads in a row, a load right after a jump, a store then a load
  * a scalar wider than 16 bits broadcast to the lanes (only the low 16 bits count)
  * reduce instructions on compare results (each true lane adds -1)
  * unused op codes (the vector ones write 0, the others do nothing)

Some of these need op codes that the assembler refuses on purpose, so the
programs are built here in Python. run_workloads.py runs each one on the golden
model and on the RTL, for every lane count, and the two must agree exactly.
Memory starts full of random numbers so every word is meaningful.
"""

import random

import golden
import vasm

HALT = vasm.encode(vasm.OP_HALT)
NOP = vasm.encode(0x3E)            # an unused class-11 op code does nothing


def corner_program():
    words = vasm.assemble("""
            ADDI s0, s0, 5          # write to s0: must be dropped
            ADDI s1, s0, -1         # s1 = 0xFFFFFFFF
            VLD  v1, 0(s1)          # address -1 wraps to the top word
            VLD  v2, -2(s0)         # address -2
            VLD  v2, 3(s0)          # two loads in a row into the same register
            VDOT s0, v1, v2         # reduce into s0: must be dropped
            ADDI s2, s0, 0x1234
            ADD  s2, s2, s2
            ADD  s2, s2, s2
            ADD  s2, s2, s2
            ADD  s2, s2, s2
            ADDI s2, s2, 5          # s2 = 0x12345, wider than 16 bits
            VADD v3, v1, s2         # broadcast uses only the low 16 bits
            VSLL v4, v1, s2         # shift by 5
            VSRA v5, v1, s2
            VREDSEQ s3, v1, v1      # every lane true: s3 = -LANES
            VREDSLT s4, v1, v2
            VREDSLTU s5, v1, v2
            VST  v3, 0(s1)          # store at the top word
            VST  v4, 1(s1)          # 0xFFFFFFFF + 1 wraps to word 0
            ADDI s6, s0, 0x7FFF
            ADD  s6, s6, s6
            ADD  s6, s6, s6
            ADD  s6, s6, s6         # 0x3FFF8: wraps inside memory
            VST  v5, 0(s6)
            VLD  v6, 0(s6)          # store then load the same address
            BNE  s1, s0, fwd        # forward branch, taken
            VST  v6, 5(s0)          # must be skipped
    fwd:    VST  v6, 6(s0)
            BNE  s0, s0, never      # forward branch, not taken
            VLD  v7, 9(s0)
            BNE  s1, s0, tgt        # jump straight to a load
            HALT
    tgt:    VLD  v7, 10(s0)
            BNE  s7, s1, bump       # a load followed by a branch
    never:  HALT
    bump:   ADDI s7, s7, -1
            VST  v7, 7(s0)
            BNE  s7, s1, tgt
            VREDMAX s7, v1, v2
    """)
    # Unused op codes with every field set, each followed by a store or add
    # that makes its effect (or lack of one) visible.
    extra = []
    for opcode in (0x0E, 0x0F, 0x1E, 0x1F):          # unused vector jobs: write 0 to v6
        extra.append(vasm.encode(opcode, rd=6, ra=1, rb=2))
        extra.append(vasm.assemble(f"VST v6, {20 + len(extra)}(s0)")[0])
    for opcode in (0x2E, 0x2F):                      # unused reduce jobs: write 0 to s3
        extra.append(vasm.encode(opcode, rd=3, ra=1, rb=2))
        extra.append(vasm.assemble("ADD s4, s4, s3")[0])
    for opcode in (0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x3A, 0x3B, 0x3D, 0x3E):
        extra.append(vasm.encode(opcode, rd=5, ra=1, rb=2, imm=0x7FFF))   # must do nothing
    extra.append(vasm.assemble("VST v3, 40(s0)")[0])
    extra.append(HALT)
    return words + extra


def pc_wrap_program():
    words = [NOP] * 256
    words[0] = vasm.assemble("ADDI s1, s1, 1")[0]
    words[1] = vasm.assemble("ADDI s2, s0, 3")[0]
    words[2] = vasm.encode(vasm.OP_BNE, ra=1, rb=2, imm=-10)   # 2 - 10 wraps to 248
    words[3] = HALT
    words[248] = vasm.assemble("ADDI s3, s3, 1")[0]
    words[254] = vasm.assemble("VLD v1, 0(s3)")[0]
    words[255] = vasm.assemble("VST v1, 100(s3)")[0]           # then the PC wraps 255 -> 0
    return words


DIRECTED = {
    "corners": corner_program,
    "pc_wrap": pc_wrap_program,
}


def prepare_directed(name, lanes, w=16):
    """Golden-model run of one directed program, in the same form as
    run_workloads.prepare() returns."""
    rng = random.Random(f"{name}-seed")
    model = golden.SimdModel(lanes, w)
    for i in range(len(model.mem)):
        model.mem[i] = [rng.randrange(1 << w) for _ in range(lanes)]
    start_memory = golden.memory_hex_lines(model)
    words = DIRECTED[name]()
    instructions, cycles = model.run(words)
    return dict(words=words, start_memory=start_memory, model=model,
                instructions=instructions, cycles=cycles, elements=0)
