"""
run_workloads.py - runs every workload on the golden model and on the RTL.

For each workload and each lane count it:
  1. makes random input data (fixed seed, so every run is the same)
  2. assembles the program with the right constants (ITER = N / LANES, ...)
  3. runs the Python golden model
  4. checks the golden model against plain maths (e.g. C == A + B),
     which catches mistakes in the PROGRAM itself
  5. writes the hex files and runs the Verilog testbench (tb_simd_core.v),
     which compares the HARDWARE against the golden model
  6. records the cycle counts for the scalar-vs-SIMD comparison

It also runs the directed corner tests from directed_tests.py on the RTL
(they check odd cases, not speed, so they are left out of the CSV).

Usage:
    python3 sw/run_workloads.py                       # all workloads, 8 lanes
    python3 sw/run_workloads.py --lanes 1 2 4 8 --csv results/perf.csv
    python3 sw/run_workloads.py --no-rtl              # golden model only
    python3 sw/run_workloads.py --workloads dot --lanes 8 --vcd   # save waveforms
"""

import argparse
import csv
import random
import re
import subprocess
import sys
from pathlib import Path

import directed_tests
import golden
import vasm

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "sim"
N = 256                  # elements per array in the main workloads
W = 16


def rand_list(rng, count, low, high):
    return [rng.randint(low, high) for _ in range(count)]


# ---- Workload definitions -----------------------------------------------------
# Each workload says: which program, where the arrays go (vector word
# addresses), how to make its inputs, and what the correct answer is.

def setup_vadd(rng, m):
    a, b = rand_list(rng, N, -1000, 1000), rand_list(rng, N, -1000, 1000)
    golden.store_array(m, 0, a)
    golden.store_array(m, 256, b)
    check = lambda m: golden.load_array(m, 512, N) == [x + y for x, y in zip(a, b)]
    return dict(A=0, B=256, C=512), N, check


def setup_saxpy(rng, m):
    x, y, alpha = rand_list(rng, N, -1000, 1000), rand_list(rng, N, -1000, 1000), 3
    golden.store_array(m, 0, x)
    golden.store_array(m, 256, y)
    check = lambda m: golden.load_array(m, 256, N) == [alpha * p + q for p, q in zip(x, y)]
    return dict(X=0, Y=256, ALPHA=alpha), N, check


def setup_relu(rng, m):
    x = rand_list(rng, N, -1000, 1000)
    golden.store_array(m, 0, x)
    check = lambda m: golden.load_array(m, 256, N) == [max(v, 0) for v in x]
    return dict(X=0, Y=256), N, check


def setup_threshold(rng, m):
    x, limit = rand_list(rng, N, -1000, 1000), 100
    golden.store_array(m, 0, x)
    check = lambda m: golden.load_array(m, 256, N) == [v if v >= limit else 0 for v in x]
    return dict(X=0, Y=256, LIMIT=limit), N, check


def setup_dot(rng, m):
    a, b = rand_list(rng, N, -100, 100), rand_list(rng, N, -100, 100)
    golden.store_array(m, 0, a)
    golden.store_array(m, 256, b)
    want = sum(x * y for x, y in zip(a, b)) & 0xFFFFFFFF
    check = lambda m: m.s[3] == want
    return dict(A=0, B=256), N, check


def setup_isa_test(rng, m):
    count = 32           # smaller arrays: this program writes 28 result areas
    golden.store_array(m, 0, rand_list(rng, count, -32768, 32767))
    golden.store_array(m, 32, rand_list(rng, count, -32768, 32767))
    check = lambda m: True       # no simple maths formula; the golden model is the reference
    return dict(A=0, B=32, OUT=64, STRIDE=32), count, check


WORKLOADS = {
    "vadd": setup_vadd,
    "saxpy": setup_saxpy,
    "relu": setup_relu,
    "threshold": setup_threshold,
    "dot": setup_dot,
    "isa_test": setup_isa_test,
}


# ---- Running ----------------------------------------------------------------------

def prepare(name, lanes):
    """Golden-model run of one workload. Returns everything the RTL run needs."""
    rng = random.Random(f"{name}-seed")          # same data for every lane count
    model = golden.SimdModel(lanes, W)
    symbols, elements, check = WORKLOADS[name](rng, model)
    if elements % lanes:
        raise ValueError(f"{name}: {elements} elements do not split into {lanes} lanes")
    symbols["ITER"] = elements // lanes

    source = (ROOT / "sw" / "programs" / f"{name}.s").read_text()
    words = vasm.assemble(source, symbols)
    start_memory = golden.memory_hex_lines(model)
    instructions, cycles = model.run(words)
    if not check(model):
        raise AssertionError(f"{name} (lanes={lanes}): golden model disagrees with plain maths")
    return dict(words=words, start_memory=start_memory, model=model,
                instructions=instructions, cycles=cycles, elements=elements)


def write_files(folder, run):
    folder.mkdir(parents=True, exist_ok=True)
    vasm.write_hex(run["words"], folder / "prog.hex")
    (folder / "data.hex").write_text("\n".join(run["start_memory"]) + "\n")
    (folder / "expect_mem.hex").write_text("\n".join(golden.memory_hex_lines(run["model"])) + "\n")
    scalars = run["model"].s + [run["instructions"], run["cycles"]]
    (folder / "expect_scalar.hex").write_text("\n".join(f"{v:08x}" for v in scalars) + "\n")


def compile_tb(lanes):
    """Build the testbench once per lane count."""
    BUILD.mkdir(parents=True, exist_ok=True)
    out = BUILD / f"tb_simd_core_L{lanes}.vvp"
    cmd = ["iverilog", "-g2012", "-I", "rtl", "-y", "rtl",
           f"-Ptb_simd_core.LANES={lanes}", "-o", str(out), "tb/tb_simd_core.v"]
    subprocess.run(cmd, cwd=ROOT, check=True)
    return out


def run_rtl(vvp, folder, vcd):
    args = ["vvp", "-n", str(vvp),
            f"+prog={folder / 'prog.hex'}", f"+data={folder / 'data.hex'}",
            f"+expect_mem={folder / 'expect_mem.hex'}",
            f"+expect_scalar={folder / 'expect_scalar.hex'}"]
    if vcd:
        args.append(f"+vcd={folder / 'wave.vcd'}")
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    perf = re.search(r"PERF lanes=\d+ cycles=(\d+) instructions=(\d+)", result.stdout)
    passed = "TEST PASSED" in result.stdout
    if not passed:
        print(result.stdout)
    return passed, (int(perf.group(1)), int(perf.group(2))) if perf else (None, None)


def main():
    parser = argparse.ArgumentParser(description="Run workloads on the golden model and RTL.")
    parser.add_argument("--lanes", type=int, nargs="+", default=[8])
    parser.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=list(WORKLOADS))
    parser.add_argument("--no-rtl", action="store_true", help="golden model only")
    parser.add_argument("--no-directed", action="store_true", help="skip the directed corner tests")
    parser.add_argument("--vcd", action="store_true", help="save a waveform for each run")
    parser.add_argument("--csv", help="write the results table to this file")
    args = parser.parse_args()

    rows, failures = [], 0
    for lanes in args.lanes:
        vvp = None if args.no_rtl else compile_tb(lanes)
        for name in args.workloads:
            run = prepare(name, lanes)
            folder = BUILD / f"{name}_L{lanes}"
            write_files(folder, run)
            status = "golden only"
            if vvp:
                passed, (cycles, instrs) = run_rtl(vvp, folder, args.vcd)
                status = "PASS" if passed else "FAIL"
                failures += not passed
            print(f"{name:10s} lanes={lanes}  instructions={run['instructions']:6d}  "
                  f"cycles={run['cycles']:6d}  {status}")
            rows.append(dict(workload=name, lanes=lanes, elements=run["elements"],
                             instructions=run["instructions"], cycles=run["cycles"],
                             status=status))
        if vvp and not args.no_directed:
            for name in directed_tests.DIRECTED:
                run = directed_tests.prepare_directed(name, lanes)
                folder = BUILD / f"directed_{name}_L{lanes}"
                write_files(folder, run)
                passed, _ = run_rtl(vvp, folder, args.vcd)
                failures += not passed
                print(f"{name:10s} lanes={lanes}  instructions={run['instructions']:6d}  "
                      f"cycles={run['cycles']:6d}  {'PASS' if passed else 'FAIL'}  (directed)")

    if args.csv:
        add_speedup(rows)
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.csv}")

    if failures:
        sys.exit(f"{failures} run(s) FAILED")


def add_speedup(rows):
    """Speed-up = cycles with 1 lane / cycles with N lanes (needs a 1-lane run)."""
    base = {r["workload"]: r["cycles"] for r in rows if r["lanes"] == 1}
    for r in rows:
        b = base.get(r["workload"])
        r["speedup"] = round(b / r["cycles"], 3) if b else ""
        r["elements_per_cycle"] = round(r["elements"] / r["cycles"], 4)


if __name__ == "__main__":
    main()
