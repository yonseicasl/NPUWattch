module mxfpmac_tb;
    localparam int NUM_BLOCKS = 2;
    localparam int ELEM_WIDTH = 8;
    localparam int SCALE_EXP_BITS = 8;
    localparam int ACC_WIDTH = 32;
    localparam int TOTAL_ELEMS = 64;
    localparam int NUM_CASES = 6;

    logic i_clk;
    logic i_rst_n;
    logic i_valid;
    logic [TOTAL_ELEMS*ELEM_WIDTH-1:0] i_a;
    logic [TOTAL_ELEMS*ELEM_WIDTH-1:0] i_b;
    logic [NUM_BLOCKS*SCALE_EXP_BITS-1:0] i_scale_a;
    logic [NUM_BLOCKS*SCALE_EXP_BITS-1:0] i_scale_b;
    logic o_valid;
    logic signed [ACC_WIDTH-1:0] o_result;

    logic [TOTAL_ELEMS*ELEM_WIDTH-1:0] vec_a [0:NUM_CASES-1];
    logic [TOTAL_ELEMS*ELEM_WIDTH-1:0] vec_b [0:NUM_CASES-1];
    logic [NUM_BLOCKS*SCALE_EXP_BITS-1:0] vec_scale_a [0:NUM_CASES-1];
    logic [NUM_BLOCKS*SCALE_EXP_BITS-1:0] vec_scale_b [0:NUM_CASES-1];
    logic [ACC_WIDTH-1:0] vec_expected [0:NUM_CASES-1];
    string vec_desc [0:NUM_CASES-1];
    int errors;

    mxfpmac dut (
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .i_valid(i_valid),
        .i_a(i_a),
        .i_b(i_b),
        .i_scale_a(i_scale_a),
        .i_scale_b(i_scale_b),
        .o_valid(o_valid),
        .o_result(o_result)
    );

    always #5 i_clk <= ~i_clk;

    initial begin
        i_clk = 1'b0;
        i_rst_n = 1'b0;
        i_valid = 1'b0;
        i_a = '0;
        i_b = '0;
        i_scale_a = '0;
        i_scale_b = '0;
        errors = 0;

        vec_a[0] = 512'h00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000;
        vec_b[0] = 512'h00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000;
        vec_scale_a[0] = 16'h7f7f;
        vec_scale_b[0] = 16'h7f7f;
        vec_expected[0] = 32'h00000000;
        vec_desc[0] = "idle zeros";

        vec_a[1] = 512'h40384440384440384440384440384440384440384440384440384440384440384038444038444038444038444038444038444038444038444038444038444038;
        vec_b[1] = 512'h40384038403840384038403840384038403840384038403840384038403840384038403840384038403840384038403840384038403840384038403840384038;
        vec_scale_a[1] = 16'h7f7f;
        vec_scale_b[1] = 16'h7f7f;
        vec_expected[1] = 32'h0000be00;
        vec_desc[1] = "positive ramp";

        vec_a[2] = 512'hb8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0;
        vec_b[2] = 512'h3840c0b8003840c0b8003840c0b8003840c0b8003840c0b8003840c0b80038403840c0b8003840c0b8003840c0b8003840c0b8003840c0b8003840c0b8003840;
        vec_scale_a[2] = 16'h7f7f;
        vec_scale_b[2] = 16'h7f7f;
        vec_expected[2] = 32'hffff7e00;
        vec_desc[2] = "signed mix";

        vec_a[3] = 512'h40404040404040404040404040404040404040404040404040404040404040403838383838383838383838383838383838383838383838383838383838383838;
        vec_b[3] = 512'h00b83800b83800b83800b83800b83800b83800b83800b83800b83800b83800b800b83800b83800b83800b83800b83800b83800b83800b83800b83800b83800b8;
        vec_scale_a[3] = 16'h7f7e;
        vec_scale_b[3] = 16'h7f7f;
        vec_expected[3] = 32'hfffffd80;
        vec_desc[3] = "scaled blocks";

        vec_a[4] = 512'h00000000400000000000004000000000000040000000000000400000000000000000004000000000000040000000000000400000000000004000000000000040;
        vec_b[4] = 512'h38b838383838b838383838b838383838b838383838b838383838b838383838b838b838383838b838383838b838383838b838383838b838383838b838383838b8;
        vec_scale_a[4] = 16'h7f7f;
        vec_scale_b[4] = 16'h7f7f;
        vec_expected[4] = 32'h00000a00;
        vec_desc[4] = "sparse";

        vec_a[5] = 512'h00b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0;
        vec_b[5] = 512'h3800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0403800b8c0;
        vec_scale_a[5] = 16'h7f7f;
        vec_scale_b[5] = 16'h7f7f;
        vec_expected[5] = 32'h00004100;
        vec_desc[5] = "busy";

        repeat (2) @(posedge i_clk);
        i_rst_n = 1'b1;

        for (int n = 0; n < NUM_CASES; n = n + 1) begin
            @(negedge i_clk);
            i_valid = 1'b1;
            i_a = vec_a[n];
            i_b = vec_b[n];
            i_scale_a = vec_scale_a[n];
            i_scale_b = vec_scale_b[n];
            @(posedge i_clk);
            #1;
            $display("mxfpmac case=%0d desc=%s got=%0d exp=%0d valid=%0b",
                n, vec_desc[n], o_result, $signed(vec_expected[n]), o_valid);
            if ((o_valid !== 1'b1) || (o_result !== $signed(vec_expected[n]))) begin
                errors = errors + 1;
                $display("mxfpmac mismatch at case %0d", n);
            end
        end

        @(negedge i_clk);
        i_valid = 1'b0;
        i_a = '0;
        i_b = '0;
        i_scale_a = '0;
        i_scale_b = '0;
        @(posedge i_clk);
        #1;
        if (o_valid !== 1'b0) begin
            errors = errors + 1;
            $display("mxfpmac valid did not deassert");
        end

        if (errors == 0) begin
            $display("mxfpmac_tb PASS");
        end else begin
            $display("mxfpmac_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
