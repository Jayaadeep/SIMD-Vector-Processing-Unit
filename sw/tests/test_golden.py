"""
Self-checks for the golden model.

Run:  python3 -m unittest discover -s sw/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import golden  # noqa: E402

# Some checks assemble a program, so they wait until the assembler and the
# programs are in the repository.
try:
    import vasm  # noqa: E402
except ImportError:
    vasm = None
VADD = Path(__file__).resolve().parents[1] / "programs" / "vadd.s"
needs_assembler = unittest.skipIf(vasm is None or not VADD.exists(),
                                  "needs sw/vasm.py and sw/programs/vadd.s")


class GoldenModelTests(unittest.TestCase):

    def test_alu_corner_cases(self):
        add, sra, slt, sltu, mul = (golden.ALU_OPS.index(n) for n in
                                    ["ADD", "SRA", "SLT", "SLTU", "MUL"])
        self.assertEqual(golden.alu(add, 0xFFFF, 1), 0)          # wraps around
        self.assertEqual(golden.alu(sra, 0x8000, 15), 0xFFFF)    # keeps the sign
        self.assertEqual(golden.alu(slt, 0xFFFF, 1), 0xFFFF)     # -1 < 1
        self.assertEqual(golden.alu(sltu, 0xFFFF, 1), 0)         # 65535 > 1
        self.assertEqual(golden.alu(mul, 300, 300), 90000 & 0xFFFF)

    @needs_assembler
    def test_s0_stays_zero(self):
        model = golden.SimdModel(lanes=1)
        model.run(vasm.assemble("ADDI s0, s0, 5\nHALT"))
        self.assertEqual(model.s[0], 0)

    @needs_assembler
    def test_vadd_program(self):
        source = VADD.read_text()
        for lanes in (1, 8):
            model = golden.SimdModel(lanes)
            a, b = list(range(16)), list(range(100, 116))
            golden.store_array(model, 0, a)
            golden.store_array(model, 100, b)
            words = vasm.assemble(source, dict(A=0, B=100, C=200, ITER=16 // lanes))
            instructions, cycles = model.run(words)
            self.assertEqual(golden.load_array(model, 200, 16), [x + y for x, y in zip(a, b)])
            self.assertEqual(cycles, instructions + 2 * (16 // lanes))   # loads cost 1 extra cycle


if __name__ == "__main__":
    unittest.main()
