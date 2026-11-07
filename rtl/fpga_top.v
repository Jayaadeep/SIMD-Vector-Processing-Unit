// =============================================================================
// fpga_top.v - the SIMD core plus its memories, ready to put on an FPGA
// =============================================================================
// simd_core.v has no memories of its own. On a real FPGA board we need:
//   * an instruction memory, filled with a program when the chip powers up
//   * a data memory, filled with the input arrays
// Both are written so the FPGA tools turn them into block RAM (the FPGA's
// built-in memory blocks): they read on the clock edge, just like the
// testbench memories.
//
// Board connections are kept tiny so the design fits any small board:
//   clk       the board clock
//   rst       a push button: hold to run the program again from the start
//             (memory is not reloaded, so a program that overwrites its own
//             input, like saxpy, needs the FPGA reprogrammed for a fresh run)
//   sel[2:0]  three switches: which scalar register to show (s0..s7)
//   led[7:0]  eight LEDs: the low 8 bits of that register
//   done      one LED: lights up when the program reaches HALT
//
// With the dot-product program loaded, setting the switches to 3 shows the
// low byte of the dot product on the LEDs.
// =============================================================================

module fpga_top #(
    parameter LANES        = 8,
    parameter W            = 16,
    parameter PROGRAM_FILE = "program.hex",   // made by sw/vasm.py
    parameter DATA_FILE    = "data.hex"       // made by sw/run_workloads.py
) (
    input  wire       clk,
    input  wire       rst,
    input  wire [2:0] sel,
    output wire [7:0] led,
    output wire       done
);

    localparam IADDR_W = 8;     // 256 instructions
    localparam DADDR_W = 9;     // 512 vectors: two 256-element arrays fit even with 1 lane

    wire [IADDR_W-1:0] imem_addr;
    reg  [31:0]        imem_data;
    wire [DADDR_W-1:0] dmem_addr;
    wire [LANES*W-1:0] dmem_wdata;
    wire               dmem_we;
    reg  [LANES*W-1:0] dmem_rdata;
    /* verilator lint_off UNUSEDSIGNAL */      // only 8 LEDs, and the counters are for simulation
    wire [31:0]        debug_data;
    wire [31:0]        cycle_count, instr_count;
    /* verilator lint_on UNUSEDSIGNAL */

    // ---- Reset --------------------------------------------------------------------
    // 1. Power-on reset: right after the FPGA is programmed, hold the core in
    //    reset for 15 clocks, so the program always starts cleanly at address 0
    //    even if nobody presses the button.
    // 2. The button is not in step with the clock. Two flip-flops in a row
    //    ("synchroniser") line it up with the clock before the core sees it.
    reg [3:0] power_on_count;
    reg [1:0] button_sync;

    // Starting values, loaded into the flip-flops when the FPGA is programmed.
    initial begin
        power_on_count = 4'd15;
        button_sync    = 2'b00;
    end

    always @(posedge clk) begin
        if (power_on_count != 4'd0)
            power_on_count <= power_on_count - 4'd1;
        button_sync <= {button_sync[0], rst};
    end

    wire core_rst = (power_on_count != 4'd0) || button_sync[1];

    // ---- Instruction memory (read-only, loaded at power-up) ------------------
    reg [31:0] imem [0:(1<<IADDR_W)-1];
    initial $readmemh(PROGRAM_FILE, imem);
    always @(posedge clk)
        imem_data <= imem[imem_addr];

    // ---- Data memory (read and write) ------------------------------------------
    reg [LANES*W-1:0] dmem [0:(1<<DADDR_W)-1];
    initial $readmemh(DATA_FILE, dmem);
    always @(posedge clk) begin
        if (dmem_we)
            dmem[dmem_addr] <= dmem_wdata;
        dmem_rdata <= dmem[dmem_addr];
    end

    // ---- The core ----------------------------------------------------------------
    simd_core #(.LANES(LANES), .W(W), .IADDR_W(IADDR_W), .DADDR_W(DADDR_W)) u_core (
        .clk(clk), .rst(core_rst),
        .imem_addr(imem_addr), .imem_data(imem_data),
        .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata), .dmem_we(dmem_we), .dmem_rdata(dmem_rdata),
        .debug_sel(sel), .debug_data(debug_data),
        .halted(done), .cycle_count(cycle_count), .instr_count(instr_count)
    );

    assign led = debug_data[7:0];

endmodule
