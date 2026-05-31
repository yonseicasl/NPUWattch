module intadd_tb;
    localparam int A_WIDTH = 8;
    localparam int B_WIDTH = 8;
    localparam int OUT_WIDTH = 16;
    localparam int PIPELINE_STAGES = 2;
    localparam int NUM_CASES = 12;

    logic signed [A_WIDTH-1:0] i_a;
    logic signed [B_WIDTH-1:0] i_b;
    logic i_clk;
    logic i_rst_n;
    logic signed [OUT_WIDTH-1:0] o_sum;

    logic [A_WIDTH-1:0] vec_a [0:NUM_CASES-1];
    logic [B_WIDTH-1:0] vec_b [0:NUM_CASES-1];
    logic [OUT_WIDTH-1:0] vec_expected [0:NUM_CASES-1];
    string vec_desc [0:NUM_CASES-1];
    int errors;

    intadd #(
        .A_WIDTH(A_WIDTH),
        .B_WIDTH(B_WIDTH),
        .OUT_WIDTH(OUT_WIDTH),
        .PIPELINE_STAGES(PIPELINE_STAGES)
    ) dut (
        .i_a(i_a),
        .i_b(i_b),
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .o_sum(o_sum)
    );

    always #5 i_clk <= ~i_clk;

    initial begin
        i_clk = 1'b0;
        i_rst_n = 1'b0;
        i_a = '0;
        i_b = '0;

        vec_a[0] = 8'h00;
        vec_b[0] = 8'h00;
        vec_expected[0] = 16'h0000;
        vec_desc[0] = "0 + 0";

        vec_a[1] = 8'h01;
        vec_b[1] = 8'h01;
        vec_expected[1] = 16'h0002;
        vec_desc[1] = "1 + 1";

        vec_a[2] = 8'hff;
        vec_b[2] = 8'h01;
        vec_expected[2] = 16'h0000;
        vec_desc[2] = "-1 + 1";

        vec_a[3] = 8'h07;
        vec_b[3] = 8'hfd;
        vec_expected[3] = 16'h0004;
        vec_desc[3] = "7 + -3";

        vec_a[4] = 8'hf8;
        vec_b[4] = 8'hfb;
        vec_expected[4] = 16'hfff3;
        vec_desc[4] = "-8 + -5";

        vec_a[5] = 8'h0d;
        vec_b[5] = 8'h15;
        vec_expected[5] = 16'h0022;
        vec_desc[5] = "13 + 21";

        vec_a[6] = 8'hef;
        vec_b[6] = 8'h09;
        vec_expected[6] = 16'hfff8;
        vec_desc[6] = "-17 + 9";

        vec_a[7] = 8'h1f;
        vec_b[7] = 8'hff;
        vec_expected[7] = 16'h001e;
        vec_desc[7] = "31 + -1";

        vec_a[8] = 8'he0;
        vec_b[8] = 8'h0f;
        vec_expected[8] = 16'hffef;
        vec_desc[8] = "-32 + 15";

        vec_a[9] = 8'h05;
        vec_b[9] = 8'hf4;
        vec_expected[9] = 16'hfff9;
        vec_desc[9] = "5 + -12";

        vec_a[10] = 8'h12;
        vec_b[10] = 8'h12;
        vec_expected[10] = 16'h0024;
        vec_desc[10] = "18 + 18";

        vec_a[11] = 8'heb;
        vec_b[11] = 8'hf9;
        vec_expected[11] = 16'hffe4;
        vec_desc[11] = "-21 + -7";

        repeat (2) @(posedge i_clk);
        i_rst_n = 1'b1;
        for (int n = 0; n < NUM_CASES; n = n + 1) begin
            @(negedge i_clk);
            i_a = $signed(vec_a[n]);
            i_b = $signed(vec_b[n]);
            repeat (PIPELINE_STAGES) @(posedge i_clk);
            #1;
            $display("intadd case=%0d desc=%s a=%0d b=%0d got=%0d exp=%0d",
                n, vec_desc[n], i_a, i_b, o_sum, $signed(vec_expected[n]));
            if (o_sum !== $signed(vec_expected[n])) begin
                errors = errors + 1;
                $display("intadd mismatch at case %0d", n);
            end
        end
        if (errors == 0) begin
            $display("intadd_tb PASS");
        end else begin
            $display("intadd_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
