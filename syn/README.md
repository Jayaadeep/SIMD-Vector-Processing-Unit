# FPGA synthesis: size and speed

Simulation proves the design is *correct*. Synthesis shows what it *costs* on a real chip (how much of the FPGA it uses) and how *fast* it can run (the maximum clock frequency, Fmax).

## Targets

| FPGA | Board examples | Tools | Gives |
| --- | --- | --- | --- |
| Lattice **ECP5-25F** (LFE5U-25F, speed 6) | ULX3S, OrangeCrab, Colorlight | Yosys + nextpnr (open source) | resources **and** Fmax after place-and-route |
| Xilinx **Artix-7 xc7a35t** | Basys-3, Arty A7 | Yosys `synth_xilinx` | resource estimate |
| Xilinx Artix-7, exact | Basys-3 | Vivado: [`vivado/build.tcl`](vivado/build.tcl) | exact resources and Fmax (needs Vivado; to run in the lab) |

The design is built for every lane count (1, 2, 4, 8) with the dot-product program already loaded in its memories. Before each build, `run_syn.py` simulates that exact board version ([`tb/tb_fpga_top.v`](../tb/tb_fpga_top.v)), started only by its power-on reset, and stops unless the LEDs show the golden model's dot product. Place-and-route picks a random starting point, so each ECP5 build is placed 3 times with different seeds and the median Fmax is reported.

The board version (`rtl/fpga_top.v`) adds three things to the core: 512 words of data memory (both 256-element arrays fit even with 1 lane), a power-on reset that holds the core for 15 clocks after the FPGA is programmed, and a two-flip-flop synchroniser on the reset button.

## Commands

```bash
pip install yowasp-nextpnr-ecp5        # or install nextpnr-ecp5 from your package manager
python3 syn/run_syn.py                 # about 7 minutes -> results/fpga_ecp5.csv, results/fpga_artix7.csv
python3 syn/run_syn.py --board-only    # just the board simulation, a few seconds (part of make test)
uv run --python 3.12 --with matplotlib python syn/plot_fpga.py     # results/figures/fpga_scaling.png

# In the lab, with Vivado installed (after run_syn.py has made the memory files):
vivado -mode batch -source syn/vivado/build.tcl -tclargs 8
```

## Results

<p align="center"><img src="../results/figures/fpga_scaling.png" width="640" alt="Logic cells and maximum clock frequency against the number of lanes"></p>

**Lattice ECP5-25F, after place-and-route** (`results/fpga_ecp5.csv`)

| Lanes | Logic cells (of 24,288) | Flip-flops | Multipliers (of 28) | Block RAM (of 56) | Fmax, median of 3 seeds |
| --- | --- | --- | --- | --- | --- |
| 1 | 949 (3.9%) | 16 | 1 | 2 | 50.8 MHz |
| 2 | 1,636 (6.7%) | 91 | 2 | 2 | 41.4 MHz |
| 4 | 2,865 (11.8%) | 155 | 4 | 3 | 37.1 MHz |
| 8 | 4,650 (19.1%) | 283 | 8 | 5 | 33.6 MHz |

**Xilinx Artix-7 xc7a35t, Yosys estimate** (`results/fpga_artix7.csv`)

| Lanes | LUTs (of 20,800) | LUTs used as RAM | Flip-flops | DSP48 (of 90) | Block RAM 36K (of 50) |
| --- | --- | --- | --- | --- | --- |
| 1 | 1,084 | 44 | 188 | 2 | 1 |
| 2 | 1,438 | 56 | 190 | 3 | 1 |
| 4 | 2,170 | 76 | 190 | 5 | 2 |
| 8 | 3,704 | 120 | 190 | 9 | 4 |

## What the numbers say

* **Area grows roughly in step with the lanes.** Each lane adds its own ALU and one hardware multiplier. Going from 4 to 8 lanes adds about 1,790 logic cells. The parts shared by all lanes (control unit, scalar registers, memories) are paid once, so 8 lanes cost 4.9× the logic of 1 lane, not 8×.
* **The register files sit in LUT RAM, not flip-flops.** Yosys stores the vector and scalar registers in the FPGA's small distributed memories (the "LUTs used as RAM" column). That is why the flip-flop count stays so low.
* **The clock gets slower with more lanes**: 50.8 MHz at 1 lane, 33.6 MHz at 8. The longest path runs through one clock cycle in full: instruction out of block RAM → decode → register read → multiply → adder tree → scalar register. Wider designs also spread out on the chip, so the wires get longer. More lanes also mean a deeper adder tree.
* **Real speed-up is therefore lower than cycle speed-up.** 8 lanes take 7.89× fewer cycles but run at 0.66× the clock, so the program finishes 5.2× sooner in real time. Pipelining the core (Phase II) would recover most of the lost clock speed.
* **Small FPGAs are not enough.** On a Lattice iCE40 (UP5K, 5,280 cells), the 8-lane design did not fit even with its 8 DSP blocks in use.

## Files

| File | Purpose |
| --- | --- |
| [`run_syn.py`](run_syn.py) | Runs the sweep and writes the two CSV files. |
| [`plot_fpga.py`](plot_fpga.py) | Draws the scaling figure. |
| [`vivado/build.tcl`](vivado/build.tcl), [`vivado/basys3.xdc`](vivado/basys3.xdc) | Vivado flow and pin map for the Basys-3 board. Not yet run (no Vivado on the development machine). The Basys-3 clock is 100 MHz, above the expected Fmax, so a slower clock (clock divider or MMCM) is needed before running on the board. |
