module fattree_tb;
    localparam int DATA_WIDTH = 32;
    localparam int RADIX = 2;
    localparam int NUM_LEVELS = 3;
    localparam int OVERSUBSCRIPTION_NUM = 1;
    localparam int OVERSUBSCRIPTION_DEN = 1;
    localparam int NUM_NODES = 8;
    localparam int NODE_ID_WIDTH = (NUM_NODES <= 1) ? 1 : $clog2(NUM_NODES);
    localparam int NUM_CYCLES = 80;

    logic [NUM_NODES*DATA_WIDTH-1:0] i_node_data;
    logic [NUM_NODES-1:0] i_node_valid;
    logic [NUM_NODES*NODE_ID_WIDTH-1:0] i_node_dest;
    logic [NUM_NODES*DATA_WIDTH-1:0] o_node_data;
    logic [NUM_NODES-1:0] o_node_valid;
    logic [NUM_NODES*NODE_ID_WIDTH-1:0] o_node_src;
    logic [NUM_NODES-1:0] o_node_grant;

    int errors;

    fattree #(
        .DATA_WIDTH(DATA_WIDTH),
        .RADIX(RADIX),
        .NUM_LEVELS(NUM_LEVELS),
        .OVERSUBSCRIPTION_NUM(OVERSUBSCRIPTION_NUM),
        .OVERSUBSCRIPTION_DEN(OVERSUBSCRIPTION_DEN),
        .NUM_NODES(NUM_NODES)
    ) dut (
        .i_node_data(i_node_data),
        .i_node_valid(i_node_valid),
        .i_node_dest(i_node_dest),
        .o_node_data(o_node_data),
        .o_node_valid(o_node_valid),
        .o_node_src(o_node_src),
        .o_node_grant(o_node_grant)
    );

    initial begin
        i_node_data = '0;
        i_node_valid = '0;
        i_node_dest = '0;
        errors = 0;
        for (int cycle = 0; cycle < NUM_CYCLES; cycle = cycle + 1) begin
            logic [NUM_NODES*DATA_WIDTH-1:0] exp_data;
            logic [NUM_NODES-1:0] exp_valid;
            logic [NUM_NODES*NODE_ID_WIDTH-1:0] exp_src;
            logic [NUM_NODES-1:0] exp_grant;

            i_node_data = '0;
            i_node_valid = '0;
            i_node_dest = '0;
            for (int src = 0; src < NUM_NODES; src = src + 1) begin
                i_node_data[src*DATA_WIDTH +: DATA_WIDTH] = DATA_WIDTH'($urandom);
                i_node_dest[src*NODE_ID_WIDTH +: NODE_ID_WIDTH] = NODE_ID_WIDTH'($urandom_range(0, NUM_NODES - 1));
                if (cycle < 16) begin
                    i_node_valid[src] = 1'b0;
                end else if (cycle < 36) begin
                    i_node_valid[src] = ($urandom_range(0, 7) == 0);
                end else if (cycle < 60) begin
                    i_node_valid[src] = ($urandom_range(0, 1) == 0);
                end else begin
                    i_node_valid[src] = 1'b1;
                end
            end

            exp_data = '0;
            exp_valid = '0;
            exp_src = '0;
            exp_grant = '0;
            for (int dst = 0; dst < NUM_NODES; dst = dst + 1) begin
                for (int src = 0; src < NUM_NODES; src = src + 1) begin
                    if (i_node_valid[src] &&
                        (i_node_dest[src*NODE_ID_WIDTH +: NODE_ID_WIDTH] == NODE_ID_WIDTH'(dst)) &&
                        !exp_valid[dst]) begin
                        exp_data[dst*DATA_WIDTH +: DATA_WIDTH] = i_node_data[src*DATA_WIDTH +: DATA_WIDTH];
                        exp_valid[dst] = 1'b1;
                        exp_src[dst*NODE_ID_WIDTH +: NODE_ID_WIDTH] = NODE_ID_WIDTH'(src);
                        exp_grant[src] = 1'b1;
                    end
                end
            end

            #1;
            $display("fattree cycle=%0d node_valid=%b out_valid=%b", cycle, i_node_valid, o_node_valid);
            if ((o_node_valid !== exp_valid) || (o_node_data !== exp_data) || (o_node_src !== exp_src) || (o_node_grant !== exp_grant)) begin
                errors = errors + 1;
                $display("fattree mismatch cycle=%0d", cycle);
            end
        end

        if (errors == 0) begin
            $display("fattree_tb PASS");
        end else begin
            $display("fattree_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
