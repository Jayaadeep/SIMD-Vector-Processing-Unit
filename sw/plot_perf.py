"""
plot_perf.py - figures for the scalar vs SIMD comparison.

Reads results/perf.csv (from run_workloads.py) and, if it exists,
results/fpga_ecp5.csv (from syn/run_syn.py) and draws:

  results/figures/cycles.png   clock cycles per workload for 1, 2, 4, 8 lanes
  results/figures/speedup.png  speed-up vs lanes: counted in clock cycles, and
                               in real time once the clock speed of each
                               design is taken into account

Usage:  uv run --python 3.12 --with matplotlib python sw/plot_perf.py
"""

import csv
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"

# Colours from a colour-blind-safe palette.
BLUE, ORANGE, GREY, INK = "#2a78d6", "#eb6834", "#8a8984", "#52514e"
LANE_SHADES = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]   # light -> dark = few -> many lanes
WORKLOADS = ["vadd", "saxpy", "relu", "threshold", "dot"]    # isa_test is a coverage test, not a benchmark


def read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GREY)
    ax.spines["bottom"].set_color(GREY)
    ax.tick_params(colors=INK, labelsize=9)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)


def plot_cycles(perf):
    lanes_list = sorted({int(r["lanes"]) for r in perf})
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    width = 0.8 / len(lanes_list)
    for j, lanes in enumerate(lanes_list):
        values = [next(int(r["cycles"]) for r in perf if r["workload"] == w and int(r["lanes"]) == lanes)
                  for w in WORKLOADS]
        xs = [i + (j - (len(lanes_list) - 1) / 2) * width for i in range(len(WORKLOADS))]
        ax.bar(xs, values, width * 0.92, color=LANE_SHADES[j], label=f"{lanes} lane{'s' if lanes > 1 else ''}")
    ax.set_xticks(range(len(WORKLOADS)), WORKLOADS)
    ax.set_ylabel("clock cycles (N = 256)", color=INK)
    style(ax)
    ax.legend(frameon=False, fontsize=9, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.12))
    fig.tight_layout()
    fig.savefig(FIGURES / "cycles.png", dpi=300)
    plt.close(fig)


def plot_speedup(perf, fpga):
    lanes_list = sorted({int(r["lanes"]) for r in perf})
    cycle_speedup = [statistics.mean(float(r["speedup"]) for r in perf
                                     if r["workload"] in WORKLOADS and int(r["lanes"]) == n)
                     for n in lanes_list]

    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(lanes_list, lanes_list, linestyle="--", color=GREY, linewidth=1.5)
    ax.annotate("ideal (= lanes)", (lanes_list[-1], lanes_list[-1]), textcoords="offset points",
                xytext=(-8, 6), ha="right", color=INK, fontsize=9)

    ax.plot(lanes_list, cycle_speedup, marker="o", markersize=7, color=BLUE, linewidth=2,
            label="in clock cycles")
    ax.annotate(f"{cycle_speedup[-1]:.2f}x", (lanes_list[-1], cycle_speedup[-1]),
                textcoords="offset points", xytext=(8, -4), color=INK, fontsize=9)

    if fpga:
        fmax = {int(r["lanes"]): float(r["fmax_mhz_median"]) for r in fpga}
        if 1 in fmax:
            wall = [s * fmax[n] / fmax[1] for s, n in zip(cycle_speedup, lanes_list)]
            ax.plot(lanes_list, wall, marker="s", markersize=7, color=ORANGE, linewidth=2,
                    label="in real time (cycles x ECP5 Fmax)")
            ax.annotate(f"{wall[-1]:.2f}x", (lanes_list[-1], wall[-1]),
                        textcoords="offset points", xytext=(8, -4), color=INK, fontsize=9)

    ax.set_xticks(lanes_list)
    ax.set_xlabel("lanes", color=INK)
    ax.set_ylabel("speed-up over 1 lane", color=INK)
    ax.set_xlim(0.5, lanes_list[-1] + 1.2)
    ax.set_ylim(0, lanes_list[-1] + 1)
    style(ax)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGURES / "speedup.png", dpi=300)
    plt.close(fig)


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    perf = read_csv(RESULTS / "perf.csv")
    fpga_path = RESULTS / "fpga_ecp5.csv"
    fpga = read_csv(fpga_path) if fpga_path.exists() else None
    plot_cycles(perf)
    plot_speedup(perf, fpga)
    print("wrote results/figures/cycles.png and results/figures/speedup.png")


if __name__ == "__main__":
    main()
