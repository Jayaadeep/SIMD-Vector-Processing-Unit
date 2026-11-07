# Verification

Every block is tested on its own first (unit tests), then the whole processor runs real programs (system tests). Every test checks itself and prints `TEST PASSED` or `TEST FAILED`. Run them all with:

```bash
make test
```

## Test plan

| Level | Testbench | What it checks | Size |
| --- | --- | --- | --- |
| Unit | [`tb_vec_alu.v`](tb_vec_alu.v) | All 14 ALU jobs on 8 lanes against a separate integer model. All 64 pairs of 8 tricky values (0, 1, −1, 32767, −32768, …), every shift amount 0–23, no carry leaking between lanes, 2,000 random vectors per job, unused op codes give 0. | 225,496 lane checks |
| Unit | [`tb_regfiles.v`](tb_regfiles.v) | Vector and scalar register files: every register through both read ports, write-enable off, read-during-write, `s0` stays 0, debug port, 2,000 random cycles each. | 10,044 checks |
| Unit | [`tb_lane_combiner.v`](tb_lane_combiner.v) | Lane MUX in both modes; result combiner sum against a plain loop, with the extreme values (all lanes 32767 or −32768). Run for 1, 2, 4 and 8 lanes. | 11,008 checks × 4 |
| System | [`tb_simd_core.v`](tb_simd_core.v) | Whole programs on the full core. After `HALT`, compares all 1,024 data-memory words, all 8 scalar registers, the instruction count and the cycle count with the Python golden model. | 6 programs; 1 and 8 lanes in `make test`, all 4 lane counts in `make perf` |
| System | [`../sw/directed_tests.py`](../sw/directed_tests.py) | Corner cases on the same testbench: writes to `s0`, address and PC wrap-around, two loads in a row, a load right after a branch, store then load, a 32-bit scalar broadcast, reduces on compare results, every unused op code. | 2 programs, same lane counts |
| Board | [`tb_fpga_top.v`](tb_fpga_top.v) | The FPGA version with its block RAM, started only by its power-on reset (no button press): the LEDs must show the golden model's dot product. | 4 lane counts |
| Software | [`../sw/tests/`](../sw/tests) | Assembler encodings worked out by hand, branch offsets, label and constant checks, error messages, every program assembles; golden-model corner cases and `s0` stays 0. | 11 tests |

## How the system test decides "correct"

```mermaid
flowchart LR
    P["program.s"] --> A["vasm.py<br/>assembler"]
    A --> G["golden.py<br/>Python model"]
    A --> R["tb_simd_core.v<br/>RTL simulation"]
    D["random input data<br/>(fixed seed)"] --> G
    D --> R
    G --> M{"plain maths<br/>e.g. C = A + B"}
    G --> C{"compare every<br/>memory word,<br/>register and<br/>cycle count"}
    R --> C
```

There are two separate checks:

1. **Golden model vs plain maths.** This catches mistakes in the *program*. For example, the vector-add result must equal `[a + b for a, b in zip(A, B)]`.
2. **Hardware vs golden model.** This catches mistakes in the *hardware*. Memory, registers and timing must match exactly.

## Coverage

* **Instructions.** [`isa_test.s`](../sw/programs/isa_test.s) runs every vector–vector, vector–scalar and reduce instruction on random 16-bit data, plus `VDOT`, loads, stores, `ADDI`, `ADD`, `BNE` and `HALT`. Together with the five benchmark programs, all 48 instructions run on the real core.
* **ALU outcomes.** `tb_vec_alu` prints how many times each job was checked. It also fails if a compare job never produced both a true and a false answer.
* **Corner cases.** The directed programs cover what the benchmarks never do: wrap-around, back-to-back loads, branches into loads, unused op codes. They came out of an independent review of the design; the hardware and the golden model agreed on every one.
* **Lane counts.** Every system program runs with 1, 2, 4 and 8 lanes (`make perf`), so lanes that exist in one build but not another are tested too.
* **The board version.** `make board` runs the FPGA top exactly as built, memories included, and checks the LEDs.

## Do the tests actually catch bugs?

The tests were checked by breaking the design on purpose ("mutation testing"):

| Bug introduced | Caught by | Result |
| --- | --- | --- |
| `SRA` made a logical shift (sign not kept) | `tb_vec_alu` | mismatches on every negative input |
| Adder tree pairs the wrong lanes | `tb_lane_combiner` | 5,002 errors |
| Control unit forgets to wait for load data | `tb_simd_core` | every result word wrong |
| Combiner zero-extends instead of sign-extending (1 lane) | `tb_lane_combiner` | 2,507 errors |

## Waveforms

To look at signals in GTKWave or [Surfer](https://surfer-project.org):

```bash
python3 sw/run_workloads.py --workloads vadd --lanes 8 --vcd
gtkwave build/sim/vadd_L8/wave.vcd
```
