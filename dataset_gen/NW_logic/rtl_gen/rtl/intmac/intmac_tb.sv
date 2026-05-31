module intmac_tb;
    localparam int A_WIDTH = 32;
    localparam int B_WIDTH = 32;
    localparam int OUT_WIDTH = 64;
    localparam int ACC_WIDTH = 64;
    localparam int PIPELINE_STAGES = 3;
    localparam int NUM_CASES = 12;

    logic signed [A_WIDTH-1:0] i_a;
    logic signed [B_WIDTH-1:0] i_b;
    logic i_clk;
    logic i_rst_n;
    logic signed [OUT_WIDTH-1:0] o_result;

    logic [A_WIDTH-1:0] vec_a [0:NUM_CASES-1];
    logic [B_WIDTH-1:0] vec_b [0:NUM_CASES-1];
    logic [OUT_WIDTH-1:0] vec_expected [0:NUM_CASES-1];
    string vec_desc [0:NUM_CASES-1];
    int errors;

    intmac #(
        .A_WIDTH(A_WIDTH),
        .B_WIDTH(B_WIDTH),
        .OUT_WIDTH(OUT_WIDTH),
        .ACC_WIDTH(ACC_WIDTH),
        .PIPELINE_STAGES(PIPELINE_STAGES)
    ) dut (
        .i_a(i_a),
        .i_b(i_b),
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .o_result(o_result)
    );

    always #5 i_clk <= ~i_clk;

    initial begin
        i_clk = 1'b0;
        i_rst_n = 1'b0;
        i_a = '0;
        i_b = '0;

        vec_a[0] = 32'h00000001;
        vec_b[0] = 32'h00000001;
        vec_expected[0] = 64'h0000000000000001;
        vec_desc[0] = "acc + (1 * 1)";

        vec_a[1] = 32'h00000002;
        vec_b[1] = 32'h00000003;
        vec_expected[1] = 64'h0000000000000007;
        vec_desc[1] = "acc + (2 * 3)";

        vec_a[2] = 32'hfffffffc;
        vec_b[2] = 32'h00000005;
        vec_expected[2] = 64'hfffffffffffffff3;
        vec_desc[2] = "acc + (-4 * 5)";

        vec_a[3] = 32'h00000007;
        vec_b[3] = 32'hfffffffe;
        vec_expected[3] = 64'hffffffffffffffe5;
        vec_desc[3] = "acc + (7 * -2)";

        vec_a[4] = 32'hfffffffd;
        vec_b[4] = 32'hfffffffd;
        vec_expected[4] = 64'hffffffffffffffee;
        vec_desc[4] = "acc + (-3 * -3)";

        vec_a[5] = 32'h00000000;
        vec_b[5] = 32'h00000009;
        vec_expected[5] = 64'hffffffffffffffee;
        vec_desc[5] = "acc + (0 * 9)";

        vec_a[6] = 32'h00000005;
        vec_b[6] = 32'h00000005;
        vec_expected[6] = 64'h0000000000000007;
        vec_desc[6] = "acc + (5 * 5)";

        vec_a[7] = 32'hfffffff8;
        vec_b[7] = 32'h00000004;
        vec_expected[7] = 64'hffffffffffffffe7;
        vec_desc[7] = "acc + (-8 * 4)";

        vec_a[8] = 32'h00000006;
        vec_b[8] = 32'hfffffff9;
        vec_expected[8] = 64'hffffffffffffffbd;
        vec_desc[8] = "acc + (6 * -7)";

        vec_a[9] = 32'h00000003;
        vec_b[9] = 32'h0000000c;
        vec_expected[9] = 64'hffffffffffffffe1;
        vec_desc[9] = "acc + (3 * 12)";

        vec_a[10] = 32'hfffffffe;
        vec_b[10] = 32'h0000000b;
        vec_expected[10] = 64'hffffffffffffffcb;
        vec_desc[10] = "acc + (-2 * 11)";

        vec_a[11] = 32'h00000009;
        vec_b[11] = 32'hffffffff;
        vec_expected[11] = 64'hffffffffffffffc2;
        vec_desc[11] = "acc + (9 * -1)";

        repeat (2) @(posedge i_clk);
        i_rst_n = 1'b1;
        for (int n = 0; n < NUM_CASES; n = n + 1) begin
            @(negedge i_clk);
            i_a = $signed(vec_a[n]);
            i_b = $signed(vec_b[n]);
            repeat (PIPELINE_STAGES) @(posedge i_clk);
            #1;
            $display("intmac case=%0d desc=%s a=%0d b=%0d got=%0d exp=%0d",
                n, vec_desc[n], i_a, i_b, o_result, $signed(vec_expected[n]));
            if (o_result !== $signed(vec_expected[n])) begin
                errors = errors + 1;
                $display("intmac mismatch at case %0d", n);
            end
        end
        if (errors == 0) begin
            $display("intmac_tb PASS");
        end else begin
            $display("intmac_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
