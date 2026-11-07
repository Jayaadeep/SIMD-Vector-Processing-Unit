"""
run_syn.py - builds the SIMD unit for real FPGAs and records size and speed.

For each lane count (1, 2, 4, 8) it:
  1. prepares the dot-product program and data for the FPGA memories, and
     simulates the board version (fpga_top, tb/tb_fpga_top.v) to prove it
     gives the golden model's answer before anything is built
  2. Lattice ECP5-25F:  Yosys synthesis + nextpnr place-and-route
       -> logic cells, flip-flops, multipliers, block RAM and the
          maximum clock frequency (Fmax) from the timing analysis.
          Place-and-route uses a random starting point, so we run 3 seeds
          and keep the median.
  3. Xilinx Artix-7 (xc7a35t, the Basys-3 board): Yosys synthesis only
       -> LUTs, flip-flops, DSP blocks and block RAM (an estimate; the
          exact numbers and Fmax come from Vivado, see syn/vivado/)

Outputs: results/fpga_ecp5.csv and results/fpga_artix7.csv

Needs: yosys, and nextpnr-ecp5 (or "pip install yowasp-nextpnr-ecp5").
Usage:  python3 syn/run_syn.py [--lanes 1 2 4 8] [--seeds 3]
        python3 syn/run_syn.py --board-only      # just the board simulation (used by make test)
"""

import argparse
import csv
import json
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sw"))
import run_workloads  # noqa: E402
import vasm           # noqa: E402

BUILD = ROOT / "build" / "syn"
RTL = sorted(str(p) for p in (ROOT / "rtl").glob("*.v"))
FPGA_DMEM_WORDS = 512        # fpga_top.v data memory depth (DADDR_W = 9)


def find_nextpnr():
    for name in ("nextpnr-ecp5", "yowasp-nextpnr-ecp5"):
        if shutil.which(name):
            return name
    sys.exit("nextpnr-ecp5 not found: install it with  pip install yowasp-nextpnr-ecp5")


def prepare_memories(folder, lanes):
    """Fill the FPGA memories with the dot-product program and its data,
    then simulate the board version to check it gives the right answer."""
    folder.mkdir(parents=True, exist_ok=True)
    run = run_workloads.prepare("dot", lanes)
    memory = run["start_memory"]
    # Everything past the FPGA's memory size must be empty, or data would be lost.
    dropped = [i for i, line in enumerate(memory[FPGA_DMEM_WORDS:], FPGA_DMEM_WORDS) if line.strip("0")]
    if dropped:
        sys.exit(f"lanes={lanes}: data at word {dropped[0]} does not fit the FPGA memory")
    vasm.write_hex(run["words"], folder / "program.hex")
    (folder / "data.hex").write_text("\n".join(memory[:FPGA_DMEM_WORDS]) + "\n")
    simulate_board(folder, lanes, expected=run["model"].s[3])


def simulate_board(folder, lanes, expected):
    """Run tb_fpga_top on the exact memories the FPGA will hold."""
    folder = Path(folder).resolve()
    vvp = folder / "tb_fpga_top.vvp"
    subprocess.run(["iverilog", "-g2012", "-I", str(ROOT / "rtl"), "-y", str(ROOT / "rtl"),
                    f"-Ptb_fpga_top.LANES={lanes}", "-o", str(vvp), str(ROOT / "tb" / "tb_fpga_top.v")],
                   check=True)
    result = subprocess.run(["vvp", "-n", str(vvp), f"+expect={expected:08x}", "+sel=3"],
                            cwd=folder, capture_output=True, text=True)
    if "TEST PASSED" not in result.stdout:
        sys.exit(f"lanes={lanes}: board simulation failed\n{result.stdout}{result.stderr}")
    print(f"board   lanes={lanes}: dot product {expected:#010x} on the LEDs, simulation passed")


def yosys(folder, lanes, synth_cmd, json_out=None):
    """Run Yosys and return the cell counts from its 'stat' report."""
    write = f"write_json {json_out}; " if json_out else ""
    script = (f"read_verilog -I {ROOT / 'rtl'} {' '.join(RTL)}; "
              f"chparam -set LANES {lanes} fpga_top; {synth_cmd}; {write}tee -o stat.txt stat")
    subprocess.run(["yosys", "-q", "-p", script], cwd=folder, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cells = {}
    for line in (folder / "stat.txt").read_text().splitlines():
        m = re.match(r"\s+(\d+)\s+(\S+)$", line)
        if m:
            cells[m.group(2)] = cells.get(m.group(2), 0) + int(m.group(1))
    return cells


def ecp5(lanes, seeds, nextpnr):
    folder = BUILD / f"ecp5_L{lanes}"
    prepare_memories(folder, lanes)
    yosys(folder, lanes, "synth_ecp5 -top fpga_top", json_out="fpga.json")

    fmax, util = [], {}
    for seed in range(1, seeds + 1):
        report = folder / f"report_seed{seed}.json"
        subprocess.run([nextpnr, "--25k", "--package", "CABGA256", "--speed", "6",
                        "--json", "fpga.json", "--lpf-allow-unconstrained",
                        "--freq", "25", "--timing-allow-fail", "--seed", str(seed),
                        "--report", report.name, "-q"],
                       cwd=folder, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        data = json.loads(report.read_text())
        fmax.append(min(c["achieved"] for c in data["fmax"].values()))
        util = data["utilization"]

    used = lambda k: util.get(k, {}).get("used", 0)
    return dict(lanes=lanes,
                logic_cells=used("TRELLIS_COMB"), logic_cells_total=util["TRELLIS_COMB"]["available"],
                flip_flops=used("TRELLIS_FF"),
                lutram_blocks=used("TRELLIS_RAMW"),
                multipliers=used("MULT18X18D"), multipliers_total=util["MULT18X18D"]["available"],
                block_ram=used("DP16KD"), block_ram_total=util["DP16KD"]["available"],
                fmax_mhz_median=round(statistics.median(fmax), 2),
                fmax_mhz_min=round(min(fmax), 2), fmax_mhz_max=round(max(fmax), 2))


def artix7(lanes):
    folder = BUILD / f"artix7_L{lanes}"
    prepare_memories(folder, lanes)
    c = yosys(folder, lanes, "synth_xilinx -family xc7 -top fpga_top")
    count = lambda prefix: sum(v for k, v in c.items() if k.startswith(prefix))
    return dict(lanes=lanes,
                luts=count("LUT"), luts_total=20800,
                lutram=count("RAM32") + count("RAM64") + count("RAM128"),
                flip_flops=count("FD"), flip_flops_total=41600,
                dsp48=count("DSP48"), dsp48_total=90,
                bram36_equiv=count("RAMB36") + count("RAMB18") / 2, bram36_total=50,
                carry4=count("CARRY4"))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description="FPGA resource and Fmax sweep.")
    parser.add_argument("--lanes", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--board-only", action="store_true",
                        help="only simulate the board version (no synthesis tools needed)")
    args = parser.parse_args()
    if args.board_only:
        for lanes in args.lanes:
            prepare_memories(BUILD / f"board_L{lanes}", lanes)
        return
    nextpnr = find_nextpnr()

    ecp5_rows, artix_rows = [], []
    for lanes in args.lanes:
        row = ecp5(lanes, args.seeds, nextpnr)
        ecp5_rows.append(row)
        print(f"ECP5    lanes={lanes}: {row['logic_cells']} cells, {row['multipliers']} mult, "
              f"Fmax {row['fmax_mhz_median']} MHz")
        row = artix7(lanes)
        artix_rows.append(row)
        print(f"Artix-7 lanes={lanes}: {row['luts']} LUTs, {row['flip_flops']} FFs, {row['dsp48']} DSP")

    write_csv(ROOT / "results" / "fpga_ecp5.csv", ecp5_rows)
    write_csv(ROOT / "results" / "fpga_artix7.csv", artix_rows)


if __name__ == "__main__":
    main()
