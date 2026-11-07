// =============================================================================
// simd_core.v - the complete SIMD vector processing unit
// =============================================================================
// This file only connects the blocks together. The picture:
//
//                    +----------------+
//   instruction ---->| control unit   |---- on/off signals to everything below
//   memory           +----------------+
//                           |
//      +--------------------+------------------------+
//      v                                              v
//  +------------+   va   +-----------+   +-----+   +-----------------+
//  | vector     |------->| lane ALUs |-->|     |   | result combiner |
//  | registers  |   vb   | (LANES in |   | ... |-->|  vector  / sum  |
//  |  v0..v7    |--+     | parallel) |   +-----+   +-----------------+
//  +------------+  |     +-----------+                 |        |
//                  +-> lane mux <-- scalar s[rb]       |        |
//  +------------+          (vector or broadcast)       v        v
//  | scalar     |                               vector reg   scalar reg
//  | registers  |--> scalar adder --> address / loop counter
//  |  s0..s7    |
//  +------------+
//
// Memories live outside this module (in the testbench or fpga_top.v), so the
// same core can be tested in simulation and built for an FPGA.
//
// LANES is a parameter. With LANES = 1 this exact design becomes an ordinary
// one-number-at-a-time (scalar) processor. That is our fair baseline: same
// instructions, same program, only the number of lanes changes.
// =============================================================================

module simd_core #(
    parameter LANES   = 8,     // elements processed per instruction
    parameter W       = 16,    // bits per element
    parameter IADDR_W = 8,     // instruction memory: 2^8  = 256 instructions
    parameter DADDR_W = 10     // data memory:        2^10 = 1024 vectors
) (
    input  wire               clk,
    input  wire               rst,

    // Instruction memory (data arrives one clock after the address)
    output wire [IADDR_W-1:0] imem_addr,
    input  wire [31:0]        imem_data,

    // Data memory: each memory word holds one whole vector (LANES*W bits)
    output wire [DADDR_W-1:0] dmem_addr,
    output wire [LANES*W-1:0] dmem_wdata,
    output wire               dmem_we,
    input  wire [LANES*W-1:0] dmem_rdata,

    // Scalar interface: lets the host read any scalar register
    input  wire [2:0]         debug_sel,
    output wire [31:0]        debug_data,

    // Status and performance counters
    output wire               halted,
    output reg  [31:0]        cycle_count,   // clock cycles the program has run
    output reg  [31:0]        instr_count    // instructions completed
);

    // ---- Wires between the blocks ---------------------------------------------
    wire [2:0]  rd, ra, rb;
    wire [31:0] imm;
    wire [3:0]  alu_op;
    wire        use_scalar, vreg_write, vreg_from_mem;
    wire        sreg_write, sreg_from_sum, add_use_imm, mem_write, retire;

    wire [LANES*W-1:0] va, vb;              // vector registers read this cycle
    wire [31:0]        sa, sb;              // scalar registers read this cycle
    wire [LANES*W-1:0] lane_b;              // operand B after the lane mux
    wire [LANES*W-1:0] alu_out;             // raw lane outputs
    wire [LANES*W-1:0] vector_result;       // lane outputs as one vector
    wire [31:0]        sum_result;          // lane outputs added together

    // ---- Control unit -------------------------------------------------------------
    vec_control_unit #(.IADDR_W(IADDR_W)) u_ctrl (
        .clk           (clk),
        .rst           (rst),
        .instr         (imem_data),
        .regs_differ   (sa != sb),
        .imem_addr     (imem_addr),
        .rd            (rd),
        .ra            (ra),
        .rb            (rb),
        .imm           (imm),
        .alu_op        (alu_op),
        .use_scalar    (use_scalar),
        .vreg_write    (vreg_write),
        .vreg_from_mem (vreg_from_mem),
        .sreg_write    (sreg_write),
        .sreg_from_sum (sreg_from_sum),
        .add_use_imm   (add_use_imm),
        .mem_write     (mem_write),
        .halted        (halted),
        .retire        (retire)
    );

    // ---- Scalar side: registers and one adder ---------------------------------
    // The same adder does ADDI / ADD and works out memory addresses (s[ra] + imm).
    wire [31:0] scalar_sum   = sa + (add_use_imm ? imm : sb);
    wire [31:0] sreg_wdata   = sreg_from_sum ? sum_result : scalar_sum;

    scalar_regfile u_sregs (
        .clk         (clk),
        .read_addr_a (ra),
        .read_data_a (sa),
        .read_addr_b (rb),
        .read_data_b (sb),
        .write_en    (sreg_write),
        .write_addr  (rd),
        .write_data  (sreg_wdata),
        .debug_addr  (debug_sel),
        .debug_data  (debug_data)
    );

    // ---- Vector side: registers, lane mux, lane ALUs, combiner -----------------
    // A load writes memory data; everything else writes the lane results.
    wire [LANES*W-1:0] vreg_wdata = vreg_from_mem ? dmem_rdata : vector_result;

    vec_regfile #(.LANES(LANES), .W(W)) u_vregs (
        .clk         (clk),
        .read_addr_a (ra),
        .read_data_a (va),
        .read_addr_b (rb),
        .read_data_b (vb),
        .write_en    (vreg_write),
        .write_addr  (rd),
        .write_data  (vreg_wdata)
    );

    lane_mux #(.LANES(LANES), .W(W)) u_lane_mux (
        .use_scalar (use_scalar),
        .vector_b   (vb),
        .scalar_b   (sb[W-1:0]),
        .lane_b     (lane_b)
    );

    vec_alu_array #(.LANES(LANES), .W(W)) u_alus (
        .op (alu_op),
        .a  (va),
        .b  (lane_b),
        .y  (alu_out)
    );

    result_combiner #(.LANES(LANES), .W(W)) u_combiner (
        .lane_results  (alu_out),
        .vector_result (vector_result),
        .sum_result    (sum_result)
    );

    // ---- Data memory connections ---------------------------------------------
    // VLD and VST both use address s[ra] + imm. VST stores vector register rb.
    assign dmem_addr  = scalar_sum[DADDR_W-1:0];
    assign dmem_wdata = vb;
    assign dmem_we    = mem_write;

    // ---- Performance counters --------------------------------------------------
    // These let us measure speed-up: run the same program with LANES = 1 and
    // LANES = 8 and compare the cycle counts.
    always @(posedge clk) begin
        if (rst) begin
            cycle_count <= 32'd0;
            instr_count <= 32'd0;
        end else if (!halted) begin
            cycle_count <= cycle_count + 1'b1;
            if (retire)
                instr_count <= instr_count + 1'b1;
        end
    end

endmodule
