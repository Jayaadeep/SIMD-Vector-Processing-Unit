"""
Self-checks for the assembler.

Run:  python3 -m unittest discover -s sw/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vasm  # noqa: E402

PROGRAMS = Path(__file__).resolve().parent.parent / "programs"


class AssemblerTests(unittest.TestCase):

    def test_known_encodings(self):
        # Worked out by hand from the instruction layout in rtl/simd_defs.vh.
        cases = {
            "ADDI s1, s0, 0":   0xE0800000,   # opcode 0x38, rd = 1
            "VLD v1, 0(s1)":    0xC0900000,   # opcode 0x30, rd = 1, ra = 1
            "VADD v3, v1, v2":  0x01940000,   # opcode 0x00, rd = 3, ra = 1, rb = 2
            "VMUL v1, v1, s3":  0x60960000,   # opcode 0x18 (vector-scalar MUL)
            "VDOT s4, v1, v2":  0xA2140000,   # opcode 0x28 (reduce MUL)
            "VST v3, 512(s1)":  0xC4160200,   # opcode 0x31, ra = 1, rb = 3 (store data), imm = 512
            "HALT":             0xFC000000,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(vasm.assemble(text)[0], want)

    def test_branch_offset_is_relative(self):
        # BNE on the second line jumps back one instruction: offset -1 = 0xFFFF.
        words = vasm.assemble("top: ADDI s1, s1, 1\n BNE s1, s2, top")
        self.assertEqual(words[1] & 0xFFFF, 0xFFFF)

    def test_negative_constant(self):
        self.assertEqual(vasm.assemble("ADDI s4, s0, -1")[0] & 0xFFFF, 0xFFFF)

    def test_symbols_and_expressions(self):
        word = vasm.assemble("VST v3, OUT+2*STRIDE(s1)", {"OUT": 64, "STRIDE": 32})[0]
        self.assertEqual(word & 0xFFFF, 128)

    def test_mistakes_are_reported(self):
        for bad in ["VADD v3, v1", "VADD v9, v1, v2", "ADDI s1, s0, 40000",
                    "FOO v1", "VLD v1, A", "VDOT v4, v1, v2"]:
            with self.subTest(bad=bad), self.assertRaises(vasm.AsmError):
                vasm.assemble(bad, {"A": 0})

    def test_labels_are_checked(self):
        with self.assertRaises(vasm.AsmError):
            vasm.assemble("loop: HALT\nloop: HALT")               # defined twice
        with self.assertRaises(vasm.AsmError):
            vasm.assemble("A: HALT", {"A": 256})                  # clashes with a constant
        with self.assertRaises(vasm.AsmError):
            vasm.assemble("2x: HALT")                             # not a valid name

    def test_constants_must_be_whole_numbers(self):
        with self.assertRaises(vasm.AsmError):
            vasm.assemble("ADDI s1, s0, N/3", {"N": 8})
        self.assertEqual(vasm.assemble("ADDI s1, s0, N//3", {"N": 8})[0] & 0xFFFF, 2)

    def test_every_program_assembles(self):
        symbols = dict(A=0, B=256, C=512, X=0, Y=256, OUT=64, STRIDE=32, ITER=32, ALPHA=3, LIMIT=100)
        for path in sorted(PROGRAMS.glob("*.s")):
            with self.subTest(program=path.name):
                words = vasm.assemble(path.read_text(), symbols)
                self.assertEqual(words[-1], 0xFC000000)    # every program ends with HALT


if __name__ == "__main__":
    unittest.main()
