// =============================================================================
// tb_simd_core.v - system test: runs a whole program on the complete core
// =============================================================================
// This testbench plays the role of the "computer around the chip":
//   * it holds the instruction memory and the data memory
//   * it loads a program and its input data from hex files
//   * it releases reset, lets the core run until HALT, and then
//   * compares EVERYTHING with the Python golden model:
//       - every word of data memory
//       - every scalar register (read through the debug port)
//       - the number of instructions and clock cycles
//
// The hex files are made by sw/run_workloads.py, which also runs this
// testbench for every workload and lane count. Files are passed in as
// "plusargs" on the command line:
//
//   vvp tb.vvp +prog=prog.hex +data=data.hex +expect_mem=mem.hex
//              +expect_scalar=scalar.hex [+vcd=wave.vcd]
//
// LANES is a parameter, so one testbench covers the scalar (LANES = 1)
// and SIMD (LANES = 2, 4, 8) versions.
// =============================================================================

`timescale 1ns/1ps

module tb_simd_core;

    parameter  LANES      = 8;
    localparam W          = 16;
    localparam IADDR_W    = 8;
    localparam DADDR_W    = 10;
    localparam IDEPTH     = 1 << IADDR_W;
    localparam DDEPTH     = 1 << DADDR_W;
    localparam MAX_CYCLES = 200000;      // give up if HALT never comes

    // ---- Clock and reset ---------------------------------------------------------
    reg clk = 1'b0;
    reg rst = 1'b1;
    always #5 clk = ~clk;                // 10 ns period = 100 MHz in simulation

    // ---- The core ------------------------------------------------------------------
    wire [IADDR_W-1:0] imem_addr;
    reg  [31:0]        imem_data;
    wire [DADDR_W-1:0] dmem_addr;
    wire [LANES*W-1:0] dmem_wdata;
    wire               dmem_we;
    reg  [LANES*W-1:0] dmem_rdata;
    reg  [2:0]         debug_sel = 3'd0;
    wire [31:0]        debug_data;
    wire               halted;
    wire [31:0]        cycle_count, instr_count;

    simd_core #(.LANES(LANES), .W(W), .IADDR_W(IADDR_W), .DADDR_W(DADDR_W)) dut (
        .clk(clk), .rst(rst),
        .imem_addr(imem_addr), .imem_data(imem_data),
        .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata), .dmem_we(dmem_we), .dmem_rdata(dmem_rdata),
        .debug_sel(debug_sel), .debug_data(debug_data),
        .halted(halted), .cycle_count(cycle_count), .instr_count(instr_count)
    );

    // ---- Memories --------------------------------------------------------------------
    // Both behave like FPGA block RAM: the data for an address appears one
    // clock edge after the address is given.
    reg [31:0]        imem       [0:IDEPTH-1];
    reg [LANES*W-1:0] dmem       [0:DDEPTH-1];
    reg [LANES*W-1:0] expect_mem [0:DDEPTH-1];
    reg [31:0]        expect_scalar [0:9];   // s0..s7, then instructions, then cycles

    always @(posedge clk) begin
        imem_data  <= imem[imem_addr];
        if (dmem_we)
            dmem[dmem_addr] <= dmem_wdata;
        dmem_rdata <= dmem[dmem_addr];
    end

    // ---- The test ----------------------------------------------------------------------
    reg [8*256-1:0] prog_file, data_file, mem_file, scalar_file, vcd_file;
    integer errors = 0;
    integer i;

    initial begin
        if (!$value$plusargs("prog=%s", prog_file) ||
            !$value$plusargs("data=%s", data_file) ||
            !$value$plusargs("expect_mem=%s", mem_file) ||
            !$value$plusargs("expect_scalar=%s", scalar_file)) begin
            $display("usage: +prog= +data= +expect_mem= +expect_scalar= [+vcd=]");
            $display("TEST FAILED");
            $finish;
        end
        if ($value$plusargs("vcd=%s", vcd_file)) begin
            $dumpfile(vcd_file);
            $dumpvars(0, tb_simd_core);
        end

        $readmemh(prog_file,   imem);
        $readmemh(data_file,   dmem);
        $readmemh(mem_file,    expect_mem);
        $readmemh(scalar_file, expect_scalar);

        // Hold reset for two clocks, then let the program run.
        repeat (2) @(posedge clk);
        @(negedge clk) rst = 1'b0;

        // Wait for HALT (or give up).
        i = 0;
        while (!halted && i < MAX_CYCLES) begin
            @(posedge clk);
            i = i + 1;
        end
        @(negedge clk);

        if (!halted) begin
            $display("  TIMEOUT: no HALT after %0d cycles", MAX_CYCLES);
            errors = errors + 1;
        end

        // 1. Data memory must match word for word.
        for (i = 0; i < DDEPTH; i = i + 1)
            if (dmem[i] !== expect_mem[i]) begin
                errors = errors + 1;
                if (errors <= 10)
                    $display("  MEMORY MISMATCH word %0d: got %h want %h", i, dmem[i], expect_mem[i]);
            end

        // 2. Scalar registers, read through the debug port (the scalar interface).
        for (i = 0; i < 8; i = i + 1) begin
            debug_sel = i;
            #1;
            if (debug_data !== expect_scalar[i]) begin
                errors = errors + 1;
                $display("  SCALAR MISMATCH s%0d: got %h want %h", i, debug_data, expect_scalar[i]);
            end
        end

        // 3. Instruction and cycle counts must match the golden model exactly.
        if (instr_count !== expect_scalar[8]) begin
            errors = errors + 1;
            $display("  INSTRUCTION COUNT: got %0d want %0d", instr_count, expect_scalar[8]);
        end
        if (cycle_count !== expect_scalar[9]) begin
            errors = errors + 1;
            $display("  CYCLE COUNT: got %0d want %0d", cycle_count, expect_scalar[9]);
        end

        // One machine-readable line for run_workloads.py.
        $display("PERF lanes=%0d cycles=%0d instructions=%0d", LANES, cycle_count, instr_count);
        if (errors == 0) $display("TEST PASSED");
        else             $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end

endmodule
