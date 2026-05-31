module crossbar_tb;
    localparam int DATA_WIDTH = 32;
    localparam int NUM_INPUTS = 4;
    localparam int NUM_OUTPUTS = 4;
    localparam int DEST_WIDTH = (NUM_OUTPUTS <= 1) ? 1 : $clog2(NUM_OUTPUTS);
    localparam int IN_SEL_WIDTH = (NUM_INPUTS <= 1) ? 1 : $clog2(NUM_INPUTS);
    localparam int NUM_CYCLES = 80;

    logic [NUM_INPUTS*DATA_WIDTH-1:0] i_data;
    logic [NUM_INPUTS-1:0] i_valid;
    logic [NUM_INPUTS*DEST_WIDTH-1:0] i_dest;
    logic [NUM_OUTPUTS*DATA_WIDTH-1:0] o_data;
    logic [NUM_OUTPUTS-1:0] o_valid;
    logic [NUM_OUTPUTS*IN_SEL_WIDTH-1:0] o_sel;
    logic [NUM_INPUTS-1:0] o_grant;

    int errors;

    crossbar #(
        .DATA_WIDTH(DATA_WIDTH),
        .NUM_INPUTS(NUM_INPUTS),
        .NUM_OUTPUTS(NUM_OUTPUTS)
    ) dut (
        .i_data(i_data),
        .i_valid(i_valid),
        .i_dest(i_dest),
        .o_data(o_data),
        .o_valid(o_valid),
        .o_sel(o_sel),
        .o_grant(o_grant)
    );

    initial begin
        i_data = '0;
        i_valid = '0;
        i_dest = '0;
        errors = 0;
        for (int cycle = 0; cycle < NUM_CYCLES; cycle = cycle + 1) begin
            logic [NUM_OUTPUTS*DATA_WIDTH-1:0] exp_data;
            logic [NUM_OUTPUTS-1:0] exp_valid;
            logic [NUM_OUTPUTS*IN_SEL_WIDTH-1:0] exp_sel;
            logic [NUM_INPUTS-1:0] exp_grant;

            i_data = '0;
            i_valid = '0;
            i_dest = '0;
            for (int src = 0; src < NUM_INPUTS; src = src + 1) begin
                i_data[src*DATA_WIDTH +: DATA_WIDTH] = DATA_WIDTH'($urandom);
                i_dest[src*DEST_WIDTH +: DEST_WIDTH] = DEST_WIDTH'($urandom_range(0, NUM_OUTPUTS - 1));
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
            exp_valid = '0;
            exp_sel = '0;
            exp_grant = '0;
            for (int dst = 0; dst < NUM_OUTPUTS; dst = dst + 1) begin
                for (int src = 0; src < NUM_INPUTS; src = src + 1) begin
                    if (i_valid[src] &&
                        (i_dest[src*DEST_WIDTH +: DEST_WIDTH] == DEST_WIDTH'(dst)) &&
                        !exp_valid[dst]) begin
                        exp_data[dst*DATA_WIDTH +: DATA_WIDTH] = i_data[src*DATA_WIDTH +: DATA_WIDTH];
                        exp_valid[dst] = 1'b1;
                        exp_sel[dst*IN_SEL_WIDTH +: IN_SEL_WIDTH] = IN_SEL_WIDTH'(src);
                        exp_grant[src] = 1'b1;
                    end
                end
            end

            #1;
            $display("crossbar cycle=%0d in_valid=%b out_valid=%b", cycle, i_valid, o_valid);
            if ((o_valid !== exp_valid) || (o_data !== exp_data) || (o_sel !== exp_sel) || (o_grant !== exp_grant)) begin
                errors = errors + 1;
                $display("crossbar mismatch cycle=%0d", cycle);
            end
        end

        if (errors == 0) begin
            $display("crossbar_tb PASS");
        end else begin
            $display("crossbar_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
