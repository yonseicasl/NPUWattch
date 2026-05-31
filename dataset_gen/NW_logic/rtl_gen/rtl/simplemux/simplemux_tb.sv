module simplemux_tb;
    localparam int DATA_WIDTH = 32;
    localparam int NUM_INPUTS = 4;
    localparam int SEL_WIDTH = (NUM_INPUTS <= 1) ? 1 : $clog2(NUM_INPUTS);
    localparam int NUM_CYCLES = 80;

    logic [NUM_INPUTS*DATA_WIDTH-1:0] i_data;
    logic [NUM_INPUTS-1:0] i_valid;
    logic [DATA_WIDTH-1:0] o_data;
    logic o_valid;
    logic [SEL_WIDTH-1:0] o_sel;
    logic [NUM_INPUTS-1:0] o_grant;

    int errors;

    simplemux #(
        .DATA_WIDTH(DATA_WIDTH),
        .NUM_INPUTS(NUM_INPUTS)
    ) dut (
        .i_data(i_data),
        .i_valid(i_valid),
        .o_data(o_data),
        .o_valid(o_valid),
        .o_sel(o_sel),
        .o_grant(o_grant)
    );

    initial begin
        i_data = '0;
        i_valid = '0;
        errors = 0;
        for (int cycle = 0; cycle < NUM_CYCLES; cycle = cycle + 1) begin
            logic [DATA_WIDTH-1:0] exp_data;
            logic exp_valid;
            logic [SEL_WIDTH-1:0] exp_sel;
            logic [NUM_INPUTS-1:0] exp_grant;

            i_data = '0;
            i_valid = '0;
            for (int src = 0; src < NUM_INPUTS; src = src + 1) begin
                i_data[src*DATA_WIDTH +: DATA_WIDTH] = DATA_WIDTH'($urandom);
                if (cycle < 16) begin
                    i_valid[src] = 1'b0;
                end else if (cycle < 36) begin
                    i_valid[src] = ($urandom_range(0, 7) == 0);
                end else if (cycle < 60) begin
                    i_valid[src] = ($urandom_range(0, 1) == 0);
                end else begin
                    i_valid[src] = 1'b1;
                end
            end

            exp_data = '0;
            exp_valid = 1'b0;
            exp_sel = '0;
            exp_grant = '0;
            for (int src = 0; src < NUM_INPUTS; src = src + 1) begin
                if (i_valid[src] && !exp_valid) begin
                    exp_data = i_data[src*DATA_WIDTH +: DATA_WIDTH];
                    exp_valid = 1'b1;
                    exp_sel = SEL_WIDTH'(src);
                    exp_grant[src] = 1'b1;
                end
            end

            #1;
            $display("simplemux cycle=%0d valid=%b got_valid=%0b exp_valid=%0b", cycle, i_valid, o_valid, exp_valid);
            if ((o_valid !== exp_valid) || (o_data !== exp_data) || (o_sel !== exp_sel) || (o_grant !== exp_grant)) begin
                errors = errors + 1;
                $display("simplemux mismatch cycle=%0d got_data=%h exp_data=%h got_sel=%0d exp_sel=%0d", cycle, o_data, exp_data, o_sel, exp_sel);
            end
        end

        if (errors == 0) begin
            $display("simplemux_tb PASS");
        end else begin
            $display("simplemux_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
