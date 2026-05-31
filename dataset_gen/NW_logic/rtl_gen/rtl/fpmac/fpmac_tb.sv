module fpmac_tb;
    localparam int EXPONENT_BITS = 8;
    localparam int MANTISSA_BITS = 23;
    localparam int PIPELINE_STAGES = 2;
    localparam int FP_WIDTH = EXPONENT_BITS + MANTISSA_BITS + 1;
    localparam int NUM_CASES = 12;

    logic [FP_WIDTH-1:0] i_a;
    logic [FP_WIDTH-1:0] i_b;
    logic [FP_WIDTH-1:0] i_c;
    logic i_clk;
    logic i_rst_n;
    logic [FP_WIDTH-1:0] o_result;
    logic o_ovfl;
    logic o_udfl;

    logic [FP_WIDTH-1:0] vec_a [0:NUM_CASES-1];
    logic [FP_WIDTH-1:0] vec_b [0:NUM_CASES-1];
    logic [FP_WIDTH-1:0] vec_c [0:NUM_CASES-1];
    logic [FP_WIDTH-1:0] vec_expected [0:NUM_CASES-1];
    string vec_desc [0:NUM_CASES-1];
    int errors;

    fpmac #(
        .EXPONENT_BITS(EXPONENT_BITS),
        .MANTISSA_BITS(MANTISSA_BITS),
        .PIPELINE_STAGES(PIPELINE_STAGES)
    ) dut (
        .i_a(i_a),
        .i_b(i_b),
        .i_c(i_c),
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .o_result(o_result),
        .o_ovfl(o_ovfl),
        .o_udfl(o_udfl)
    );

    always #5 i_clk <= ~i_clk;

    initial begin
        i_clk = 1'b0;
        i_rst_n = 1'b0;
        i_a = '0;
        i_b = '0;
        i_c = '0;

        vec_a[0] = 32'h3fc00000;
        vec_b[0] = 32'h40000000;
        vec_c[0] = 32'h3e800000;
        vec_expected[0] = 32'h40500000;
        vec_desc[0] = "1.5 * 2.0 + 0.25";

        vec_a[1] = 32'hc0200000;
        vec_b[1] = 32'h3fc00000;
        vec_c[1] = 32'h40800000;
        vec_expected[1] = 32'h3e800000;
        vec_desc[1] = "-2.5 * 1.5 + 4.0";

        vec_a[2] = 32'h3f000000;
        vec_b[2] = 32'h3d000000;
        vec_c[2] = 32'h3f800000;
        vec_expected[2] = 32'h3f820000;
        vec_desc[2] = "0.5 * 0.03125 + 1.0";

        vec_a[3] = 32'hbf400000;
        vec_b[3] = 32'hc0900000;
        vec_c[3] = 32'hbfa00000;
        vec_expected[3] = 32'h40080000;
        vec_desc[3] = "-0.75 * -4.5 + -1.25";

        vec_a[4] = 32'h40700000;
        vec_b[4] = 32'h00000000;
        vec_c[4] = 32'h40100000;
        vec_expected[4] = 32'h40100000;
        vec_desc[4] = "3.75 * 0.0 + 2.25";

        vec_a[5] = 32'h40e40000;
        vec_b[5] = 32'h3ff00000;
        vec_c[5] = 32'hc1000000;
        vec_expected[5] = 32'h40ab8000;
        vec_desc[5] = "7.125 * 1.875 + -8.0";

        vec_a[6] = 32'h41800000;
        vec_b[6] = 32'hbf000000;
        vec_c[6] = 32'h3f800000;
        vec_expected[6] = 32'hc0e00000;
        vec_desc[6] = "16.0 * -0.5 + 1.0";

        vec_a[7] = 32'h3f900000;
        vec_b[7] = 32'h3f900000;
        vec_c[7] = 32'h3f900000;
        vec_expected[7] = 32'h40190000;
        vec_desc[7] = "1.125 * 1.125 + 1.125";

        vec_a[8] = 32'h3e800000;
        vec_b[8] = 32'h3e800000;
        vec_c[8] = 32'h3e800000;
        vec_expected[8] = 32'h3ea00000;
        vec_desc[8] = "0.25 * 0.25 + 0.25";

        vec_a[9] = 32'hc0600000;
        vec_b[9] = 32'h40000000;
        vec_c[9] = 32'h40e00000;
        vec_expected[9] = 32'h00000000;
        vec_desc[9] = "-3.5 * 2.0 + 7.0";

        vec_a[10] = 32'h40b00000;
        vec_b[10] = 32'hbfc00000;
        vec_c[10] = 32'h3f000000;
        vec_expected[10] = 32'hc0f80000;
        vec_desc[10] = "5.5 * -1.5 + 0.5";

        vec_a[11] = 32'h3d800000;
        vec_b[11] = 32'h40800000;
        vec_c[11] = 32'hbe800000;
        vec_expected[11] = 32'h00000000;
        vec_desc[11] = "0.0625 * 4.0 + -0.25";

        repeat (2) @(posedge i_clk);
        i_rst_n = 1'b1;

        for (int n = 0; n < NUM_CASES; n = n + 1) begin
            @(negedge i_clk);
            i_a = vec_a[n];
            i_b = vec_b[n];
            i_c = vec_c[n];
            repeat (4) @(posedge i_clk);
            #1;
            $display("fpmac case=%0d desc=%s a=%h b=%h c=%h got=%h exp=%h ov=%0b ud=%0b",
                n, vec_desc[n], vec_a[n], vec_b[n], vec_c[n], o_result, vec_expected[n], o_ovfl, o_udfl);
            if (o_result !== vec_expected[n]) begin
                errors = errors + 1;
                $display("fpmac mismatch at case %0d", n);
            end
        end

        if (errors == 0) begin
            $display("fpmac_tb PASS");
        end else begin
            $display("fpmac_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
