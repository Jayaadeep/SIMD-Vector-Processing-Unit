// =============================================================================
// tb_fpga_top.v - checks the board version (fpga_top) gives the right answer
// =============================================================================
// This is the design exactly as it goes onto the FPGA, memories included.
// Like a freshly programmed chip, nobody presses the reset button: the
// power-on reset inside fpga_top must start the program by itself.
//
// After HALT we read the scalar register picked by +sel= (3 for the dot
// product) and compare it, and the 8 LEDs, with the value the golden model
// expects (+expect=, in hex).
//
// syn/run_syn.py runs this for every lane count before synthesis, from a
// folder that holds program.hex and data.hex.
// =============================================================================

`timescale 1ns/1ps

module tb_fpga_top;

    parameter LANES = 8;

    reg        clk = 1'b0;
    reg        rst = 1'b0;          // the button is never pressed
    reg  [2:0] sel = 3'd3;
    wire [7:0] led;
    wire       done;

    always #5 clk = ~clk;

    fpga_top #(.LANES(LANES)) dut (.clk(clk), .rst(rst), .sel(sel), .led(led), .done(done));

    reg [31:0] expected;
    integer    cycles;

    initial begin
        if (!$value$plusargs("expect=%h", expected)) begin
            $display("usage: +expect=<hex value of the selected register>");
            $display("TEST FAILED");
            $finish;
        end
        if (!$value$plusargs("sel=%d", sel)) sel = 3'd3;

        cycles = 0;
        // done is unknown (X) until the power-on reset has run, so wait for a real 1.
        while (done !== 1'b1 && cycles < 20000) begin
            @(posedge clk);
            cycles = cycles + 1;
        end
        #1;

        $display("board run: done=%b after %0d cycles, s%0d=%h (expected %h), LEDs=%h",
                 done, cycles, sel, dut.debug_data, expected, led);
        if (done && dut.debug_data === expected && led === expected[7:0])
            $display("TEST PASSED");
        else
            $display("TEST FAILED");
        $finish;
    end

endmodule
