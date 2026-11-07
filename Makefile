# =============================================================================
# Makefile - one-word commands for the whole project
# =============================================================================
#   make test     lint + unit testbenches + Python checks + full-system runs + board check
#   make lint     check every Verilog file with Verilator
#   make perf     scalar vs SIMD cycle counts for 1, 2, 4, 8 lanes -> results/perf.csv
#   make syn      FPGA size and maximum clock speed            -> results/fpga_*.csv
#   make plots    figures                                       -> results/figures/
#   make report   IEEE report PDF                               -> reports/Phase1_Report.pdf
#   make clean    delete build outputs
#
# Each test only runs if its files exist, so the project can be built up one
# pull request at a time.
# =============================================================================

BUILD    := build
IVERILOG := iverilog -g2012 -I rtl -y rtl
PLOT     := uv run --python 3.12 --with matplotlib python

# The whole-core checks need every block plus the assembler. Until all of them
# are in the repository, those checks wait (each block is still tested alone).
CORE_PARTS := rtl/vec_alu_lane.v rtl/vec_alu_array.v rtl/vec_regfile.v rtl/scalar_regfile.v \
              rtl/lane_mux.v rtl/result_combiner.v rtl/vec_control_unit.v rtl/simd_core.v \
              sw/vasm.py sw/programs/vadd.s
CORE_READY := $(if $(filter-out $(wildcard $(CORE_PARTS)),$(CORE_PARTS)),,yes)
LINT_WAIT  := $(if $(CORE_READY),,rtl/simd_core.v rtl/fpga_top.v)

.PHONY: test lint unit pytest system board perf syn plots report clean

test: lint unit pytest system board

# ---- Lint: every module on its own, all warnings on ---------------------------
lint:
	@for f in $(filter-out $(LINT_WAIT),$(wildcard rtl/*.v)); do \
	  m=$$(basename $$f .v); \
	  verilator --lint-only -Wall -Irtl $$f --top-module $$m || exit 1; \
	  echo "lint ok: $$m"; \
	done

# ---- Unit testbenches: each one prints TEST PASSED or TEST FAILED -------------
# run_tb <testbench> <name> <extra flags>
define run_tb
	$(IVERILOG) $(3) -o $(BUILD)/$(2).vvp $(1)
	vvp -n $(BUILD)/$(2).vvp > $(BUILD)/$(2).log
	@grep -E "checks|TEST" $(BUILD)/$(2).log
	@grep -q "TEST PASSED" $(BUILD)/$(2).log
endef

UNIT := $(basename $(notdir $(wildcard tb/tb_vec_alu.v tb/tb_regfiles.v tb/tb_lane_combiner.v)))

unit: $(UNIT)

$(BUILD):
	@mkdir -p $(BUILD)

tb_vec_alu tb_regfiles: | $(BUILD)
	$(call run_tb,tb/$@.v,$@,)

# The lane mux and combiner are checked for every lane count.
tb_lane_combiner: | $(BUILD)
	$(call run_tb,tb/$@.v,$@_L1,-P$@.LANES=1)
	$(call run_tb,tb/$@.v,$@_L2,-P$@.LANES=2)
	$(call run_tb,tb/$@.v,$@_L4,-P$@.LANES=4)
	$(call run_tb,tb/$@.v,$@_L8,-P$@.LANES=8)

# ---- Python self-checks (assembler and golden model) --------------------------
pytest:
ifneq ($(wildcard sw/tests),)
	python3 -m unittest discover -s sw/tests
endif

# ---- Full system: every workload on the scalar (1 lane) and SIMD (8 lane) core --
system:
ifneq ($(and $(CORE_READY),$(wildcard tb/tb_simd_core.v)),)
	python3 sw/run_workloads.py --lanes 1 8
else
	@echo "system: waiting for every block to be merged"
endif

# ---- The FPGA version (fpga_top) gives the right answer from power-on ------------
board:
ifneq ($(and $(CORE_READY),$(wildcard rtl/fpga_top.v)),)
	python3 syn/run_syn.py --board-only
endif

# ---- Experiments ------------------------------------------------------------------
perf:
	python3 sw/run_workloads.py --lanes 1 2 4 8 --csv results/perf.csv

syn:
	python3 syn/run_syn.py

plots:
	$(PLOT) sw/plot_perf.py
	$(PLOT) syn/plot_fpga.py

report:
	cd reports/src && tectonic -X compile main.tex
	cp reports/src/main.pdf reports/Phase1_Report.pdf

clean:
	rm -rf $(BUILD) reports/src/main.pdf
