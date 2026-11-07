"""
plot_fpga.py - how the FPGA cost and clock speed change with the lane count.

Reads results/fpga_ecp5.csv (from run_syn.py) and draws two small charts
side by side in results/figures/fpga_scaling.png:
  left : logic cells used (ECP5-25F)
  right: maximum clock frequency, median of the seeds, with the min-max range

They are two separate charts on purpose: cells and MHz are different units,
so they should not share one axis.

Usage:  uv run --python 3.12 --with matplotlib python syn/plot_fpga.py
"""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BLUE, ORANGE, GREY, INK = "#2a78d6", "#eb6834", "#8a8984", "#52514e"


def style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GREY)
    ax.spines["bottom"].set_color(GREY)
    ax.tick_params(colors=INK, labelsize=9)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)


def main():
    with open(ROOT / "results" / "fpga_ecp5.csv") as f:
        rows = list(csv.DictReader(f))
    lanes = [int(r["lanes"]) for r in rows]
    cells = [int(r["logic_cells"]) for r in rows]
    fmax = [float(r["fmax_mhz_median"]) for r in rows]
    low = [f - float(r["fmax_mhz_min"]) for f, r in zip(fmax, rows)]
    high = [float(r["fmax_mhz_max"]) - f for f, r in zip(fmax, rows)]

    fig, (left, right) = plt.subplots(1, 2, figsize=(6.8, 3.0))

    left.bar([str(n) for n in lanes], cells, width=0.55, color=BLUE)
    for i, c in enumerate(cells):
        left.annotate(f"{c}", (i, c), textcoords="offset points", xytext=(0, 3),
                      ha="center", color=INK, fontsize=8)
    left.set_title("Logic cells (ECP5-25F)", color=INK, fontsize=10)
    left.set_xlabel("lanes", color=INK)
    style(left)

    right.errorbar(lanes, fmax, yerr=[low, high], marker="o", markersize=7, color=ORANGE,
                   linewidth=2, capsize=3)
    for n, f in zip(lanes, fmax):
        right.annotate(f"{f:.1f}", (n, f), textcoords="offset points", xytext=(6, 4),
                       color=INK, fontsize=8)
    right.set_title("Max clock (MHz)", color=INK, fontsize=10)
    right.set_xlabel("lanes", color=INK)
    right.set_xticks(lanes)
    right.set_ylim(0, max(fmax) * 1.25)
    style(right)

    fig.tight_layout()
    out = ROOT / "results" / "figures" / "fpga_scaling.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
