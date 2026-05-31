module intmul_tb;
    localparam int A_WIDTH = 8;
    localparam int B_WIDTH = 8;
    localparam int OUT_WIDTH = 16;
    localparam int PIPELINE_STAGES = 2;
    localparam int NUM_CASES = 12;

    logic signed [A_WIDTH-1:0] i_a;
    logic signed [B_WIDTH-1:0] i_b;
    logic i_clk;
    logic i_rst_n;
    logic signed [OUT_WIDTH-1:0] o_product;

    logic [A_WIDTH-1:0] vec_a [0:NUM_CASES-1];
    logic [B_WIDTH-1:0] vec_b [0:NUM_CASES-1];
    logic [OUT_WIDTH-1:0] vec_expected [0:NUM_CASES-1];
    string vec_desc [0:NUM_CASES-1];
    int errors;

    intmul #(
        .A_WIDTH(A_WIDTH),
        .B_WIDTH(B_WIDTH),
        .OUT_WIDTH(OUT_WIDTH),
        .PIPELINE_STAGES(PIPELINE_STAGES)
    ) dut (
        .i_a(i_a),
        .i_b(i_b),
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .o_product(o_product)
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
        vec_desc[0] = "0 * 0";

        vec_a[1] = 8'h01;
        vec_b[1] = 8'h01;
        vec_expected[1] = 16'h0001;
        vec_desc[1] = "1 * 1";

        vec_a[2] = 8'hff;
        vec_b[2] = 8'h01;
        vec_expected[2] = 16'hffff;
        vec_desc[2] = "-1 * 1";

        vec_a[3] = 8'h03;
        vec_b[3] = 8'hfe;
        vec_expected[3] = 16'hfffa;
        vec_desc[3] = "3 * -2";

        vec_a[4] = 8'hfc;
        vec_b[4] = 8'hfb;
        vec_expected[4] = 16'h0014;
        vec_desc[4] = "-4 * -5";

        vec_a[5] = 8'h07;
        vec_b[5] = 8'h09;
        vec_expected[5] = 16'h003f;
        vec_desc[5] = "7 * 9";

        vec_a[6] = 8'hf5;
        vec_b[6] = 8'h06;
        vec_expected[6] = 16'hffbe;
        vec_desc[6] = "-11 * 6";

        vec_a[7] = 8'h0f;
        vec_b[7] = 8'hf9;
        vec_expected[7] = 16'hff97;
        vec_desc[7] = "15 * -7";

        vec_a[8] = 8'hf0;
        vec_b[8] = 8'h05;
        vec_expected[8] = 16'hffb0;
        vec_desc[8] = "-16 * 5";

        vec_a[9] = 8'h0c;
        vec_b[9] = 8'h0c;
        vec_expected[9] = 16'h0090;
        vec_desc[9] = "12 * 12";

        vec_a[10] = 8'hf7;
        vec_b[10] = 8'hfd;
        vec_expected[10] = 16'h001b;
        vec_desc[10] = "-9 * -3";

        vec_a[11] = 8'h02;
        vec_b[11] = 8'hf3;
        vec_expected[11] = 16'hffe6;
        vec_desc[11] = "2 * -13";

        repeat (2) @(posedge i_clk);
        i_rst_n = 1'b1;
        for (int n = 0; n < NUM_CASES; n = n + 1) begin
            @(negedge i_clk);
            i_a = $signed(vec_a[n]);
            i_b = $signed(vec_b[n]);
            repeat (PIPELINE_STAGES) @(posedge i_clk);
            #1;
            $display("intmul case=%0d desc=%s a=%0d b=%0d got=%0d exp=%0d",
                n, vec_desc[n], i_a, i_b, o_product, $signed(vec_expected[n]));
            if (o_product !== $signed(vec_expected[n])) begin
                errors = errors + 1;
                $display("intmul mismatch at case %0d", n);
            end
        end
        if (errors == 0) begin
            $display("intmul_tb PASS");
        end else begin
            $display("intmul_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
