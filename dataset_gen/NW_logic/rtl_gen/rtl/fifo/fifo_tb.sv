module fifo_tb;
    localparam int WIDTH = 32;
    localparam int NUM_CASES = 128;

    logic i_clk;
    logic i_rst_n;
    logic i_push;
    logic [WIDTH-1:0] i_push_data;
    logic i_pop;
    logic [WIDTH-1:0] o_pop_data;
    logic o_pop_valid;
    logic o_full;
    logic o_empty;

    logic vec_push [0:NUM_CASES-1];
    logic vec_pop [0:NUM_CASES-1];
    logic [WIDTH-1:0] vec_push_data [0:NUM_CASES-1];
    logic vec_expected_valid [0:NUM_CASES-1];
    logic [WIDTH-1:0] vec_expected_data [0:NUM_CASES-1];
    logic vec_expected_full [0:NUM_CASES-1];
    logic vec_expected_empty [0:NUM_CASES-1];
    int errors;

    fifo dut (
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .i_push(i_push),
        .i_push_data(i_push_data),
        .i_pop(i_pop),
        .o_pop_data(o_pop_data),
        .o_pop_valid(o_pop_valid),
        .o_full(o_full),
        .o_empty(o_empty)
    );

    always #5 i_clk <= ~i_clk;

    initial begin
        i_clk = 1'b0;
        i_rst_n = 1'b0;
        i_push = 1'b0;
        i_push_data = '0;
        i_pop = 1'b0;
        errors = 0;

        vec_push[0] = 1'b1;
        vec_pop[0] = 1'b0;
        vec_push_data[0] = 32'h73981515;
        vec_expected_valid[0] = 1'b0;
        vec_expected_data[0] = 32'h00000000;
        vec_expected_full[0] = 1'b0;
        vec_expected_empty[0] = 1'b0;

        vec_push[1] = 1'b1;
        vec_pop[1] = 1'b0;
        vec_push_data[1] = 32'h60081191;
        vec_expected_valid[1] = 1'b0;
        vec_expected_data[1] = 32'h00000000;
        vec_expected_full[1] = 1'b0;
        vec_expected_empty[1] = 1'b0;

        vec_push[2] = 1'b1;
        vec_pop[2] = 1'b0;
        vec_push_data[2] = 32'hb5b39c50;
        vec_expected_valid[2] = 1'b0;
        vec_expected_data[2] = 32'h00000000;
        vec_expected_full[2] = 1'b0;
        vec_expected_empty[2] = 1'b0;

        vec_push[3] = 1'b1;
        vec_pop[3] = 1'b0;
        vec_push_data[3] = 32'h87c70af7;
        vec_expected_valid[3] = 1'b0;
        vec_expected_data[3] = 32'h00000000;
        vec_expected_full[3] = 1'b0;
        vec_expected_empty[3] = 1'b0;

        vec_push[4] = 1'b1;
        vec_pop[4] = 1'b0;
        vec_push_data[4] = 32'hb2b2f245;
        vec_expected_valid[4] = 1'b0;
        vec_expected_data[4] = 32'h00000000;
        vec_expected_full[4] = 1'b0;
        vec_expected_empty[4] = 1'b0;

        vec_push[5] = 1'b1;
        vec_pop[5] = 1'b0;
        vec_push_data[5] = 32'had670ded;
        vec_expected_valid[5] = 1'b0;
        vec_expected_data[5] = 32'h00000000;
        vec_expected_full[5] = 1'b0;
        vec_expected_empty[5] = 1'b0;

        vec_push[6] = 1'b1;
        vec_pop[6] = 1'b0;
        vec_push_data[6] = 32'h02380442;
        vec_expected_valid[6] = 1'b0;
        vec_expected_data[6] = 32'h00000000;
        vec_expected_full[6] = 1'b0;
        vec_expected_empty[6] = 1'b0;

        vec_push[7] = 1'b1;
        vec_pop[7] = 1'b0;
        vec_push_data[7] = 32'hacb31b79;
        vec_expected_valid[7] = 1'b0;
        vec_expected_data[7] = 32'h00000000;
        vec_expected_full[7] = 1'b0;
        vec_expected_empty[7] = 1'b0;

        vec_push[8] = 1'b1;
        vec_pop[8] = 1'b0;
        vec_push_data[8] = 32'hfb10166a;
        vec_expected_valid[8] = 1'b0;
        vec_expected_data[8] = 32'h00000000;
        vec_expected_full[8] = 1'b0;
        vec_expected_empty[8] = 1'b0;

        vec_push[9] = 1'b1;
        vec_pop[9] = 1'b0;
        vec_push_data[9] = 32'h29e49b8e;
        vec_expected_valid[9] = 1'b0;
        vec_expected_data[9] = 32'h00000000;
        vec_expected_full[9] = 1'b0;
        vec_expected_empty[9] = 1'b0;

        vec_push[10] = 1'b0;
        vec_pop[10] = 1'b1;
        vec_push_data[10] = 32'hee7c7c44;
        vec_expected_valid[10] = 1'b1;
        vec_expected_data[10] = 32'h73981515;
        vec_expected_full[10] = 1'b0;
        vec_expected_empty[10] = 1'b0;

        vec_push[11] = 1'b0;
        vec_pop[11] = 1'b1;
        vec_push_data[11] = 32'hf4f5776a;
        vec_expected_valid[11] = 1'b1;
        vec_expected_data[11] = 32'h60081191;
        vec_expected_full[11] = 1'b0;
        vec_expected_empty[11] = 1'b0;

        vec_push[12] = 1'b0;
        vec_pop[12] = 1'b1;
        vec_push_data[12] = 32'h2b96913e;
        vec_expected_valid[12] = 1'b1;
        vec_expected_data[12] = 32'hb5b39c50;
        vec_expected_full[12] = 1'b0;
        vec_expected_empty[12] = 1'b0;

        vec_push[13] = 1'b0;
        vec_pop[13] = 1'b1;
        vec_push_data[13] = 32'h279424ef;
        vec_expected_valid[13] = 1'b1;
        vec_expected_data[13] = 32'h87c70af7;
        vec_expected_full[13] = 1'b0;
        vec_expected_empty[13] = 1'b0;

        vec_push[14] = 1'b0;
        vec_pop[14] = 1'b1;
        vec_push_data[14] = 32'hc45b83e9;
        vec_expected_valid[14] = 1'b1;
        vec_expected_data[14] = 32'hb2b2f245;
        vec_expected_full[14] = 1'b0;
        vec_expected_empty[14] = 1'b0;

        vec_push[15] = 1'b0;
        vec_pop[15] = 1'b1;
        vec_push_data[15] = 32'h550a526a;
        vec_expected_valid[15] = 1'b1;
        vec_expected_data[15] = 32'had670ded;
        vec_expected_full[15] = 1'b0;
        vec_expected_empty[15] = 1'b0;

        vec_push[16] = 1'b0;
        vec_pop[16] = 1'b1;
        vec_push_data[16] = 32'h583e33a4;
        vec_expected_valid[16] = 1'b1;
        vec_expected_data[16] = 32'h02380442;
        vec_expected_full[16] = 1'b0;
        vec_expected_empty[16] = 1'b0;

        vec_push[17] = 1'b0;
        vec_pop[17] = 1'b1;
        vec_push_data[17] = 32'heacd4a48;
        vec_expected_valid[17] = 1'b1;
        vec_expected_data[17] = 32'hacb31b79;
        vec_expected_full[17] = 1'b0;
        vec_expected_empty[17] = 1'b0;

        vec_push[18] = 1'b0;
        vec_pop[18] = 1'b1;
        vec_push_data[18] = 32'heb30b369;
        vec_expected_valid[18] = 1'b1;
        vec_expected_data[18] = 32'hfb10166a;
        vec_expected_full[18] = 1'b0;
        vec_expected_empty[18] = 1'b0;

        vec_push[19] = 1'b0;
        vec_pop[19] = 1'b1;
        vec_push_data[19] = 32'h6bae3374;
        vec_expected_valid[19] = 1'b1;
        vec_expected_data[19] = 32'h29e49b8e;
        vec_expected_full[19] = 1'b0;
        vec_expected_empty[19] = 1'b1;

        vec_push[20] = 1'b0;
        vec_pop[20] = 1'b1;
        vec_push_data[20] = 32'hd5e733ea;
        vec_expected_valid[20] = 1'b0;
        vec_expected_data[20] = 32'h00000000;
        vec_expected_full[20] = 1'b0;
        vec_expected_empty[20] = 1'b1;

        vec_push[21] = 1'b0;
        vec_pop[21] = 1'b1;
        vec_push_data[21] = 32'h2504611e;
        vec_expected_valid[21] = 1'b0;
        vec_expected_data[21] = 32'h00000000;
        vec_expected_full[21] = 1'b0;
        vec_expected_empty[21] = 1'b1;

        vec_push[22] = 1'b0;
        vec_pop[22] = 1'b1;
        vec_push_data[22] = 32'hfbd4c5c8;
        vec_expected_valid[22] = 1'b0;
        vec_expected_data[22] = 32'h00000000;
        vec_expected_full[22] = 1'b0;
        vec_expected_empty[22] = 1'b1;

        vec_push[23] = 1'b0;
        vec_pop[23] = 1'b1;
        vec_push_data[23] = 32'hd69ceb8d;
        vec_expected_valid[23] = 1'b0;
        vec_expected_data[23] = 32'h00000000;
        vec_expected_full[23] = 1'b0;
        vec_expected_empty[23] = 1'b1;

        vec_push[24] = 1'b1;
        vec_pop[24] = 1'b0;
        vec_push_data[24] = 32'h9278a38a;
        vec_expected_valid[24] = 1'b0;
        vec_expected_data[24] = 32'h00000000;
        vec_expected_full[24] = 1'b0;
        vec_expected_empty[24] = 1'b0;

        vec_push[25] = 1'b1;
        vec_pop[25] = 1'b1;
        vec_push_data[25] = 32'hb90ba9e7;
        vec_expected_valid[25] = 1'b1;
        vec_expected_data[25] = 32'h9278a38a;
        vec_expected_full[25] = 1'b0;
        vec_expected_empty[25] = 1'b0;

        vec_push[26] = 1'b1;
        vec_pop[26] = 1'b0;
        vec_push_data[26] = 32'h7efe11c5;
        vec_expected_valid[26] = 1'b0;
        vec_expected_data[26] = 32'h00000000;
        vec_expected_full[26] = 1'b0;
        vec_expected_empty[26] = 1'b0;

        vec_push[27] = 1'b1;
        vec_pop[27] = 1'b1;
        vec_push_data[27] = 32'hc8597d8c;
        vec_expected_valid[27] = 1'b1;
        vec_expected_data[27] = 32'hb90ba9e7;
        vec_expected_full[27] = 1'b0;
        vec_expected_empty[27] = 1'b0;

        vec_push[28] = 1'b1;
        vec_pop[28] = 1'b0;
        vec_push_data[28] = 32'h556dd1ae;
        vec_expected_valid[28] = 1'b0;
        vec_expected_data[28] = 32'h00000000;
        vec_expected_full[28] = 1'b0;
        vec_expected_empty[28] = 1'b0;

        vec_push[29] = 1'b0;
        vec_pop[29] = 1'b0;
        vec_push_data[29] = 32'h14e2b04a;
        vec_expected_valid[29] = 1'b0;
        vec_expected_data[29] = 32'h00000000;
        vec_expected_full[29] = 1'b0;
        vec_expected_empty[29] = 1'b0;

        vec_push[30] = 1'b1;
        vec_pop[30] = 1'b0;
        vec_push_data[30] = 32'h42c66e99;
        vec_expected_valid[30] = 1'b0;
        vec_expected_data[30] = 32'h00000000;
        vec_expected_full[30] = 1'b0;
        vec_expected_empty[30] = 1'b0;

        vec_push[31] = 1'b1;
        vec_pop[31] = 1'b1;
        vec_push_data[31] = 32'h33c9581f;
        vec_expected_valid[31] = 1'b1;
        vec_expected_data[31] = 32'h7efe11c5;
        vec_expected_full[31] = 1'b0;
        vec_expected_empty[31] = 1'b0;

        vec_push[32] = 1'b1;
        vec_pop[32] = 1'b1;
        vec_push_data[32] = 32'h5abff387;
        vec_expected_valid[32] = 1'b1;
        vec_expected_data[32] = 32'hc8597d8c;
        vec_expected_full[32] = 1'b0;
        vec_expected_empty[32] = 1'b0;

        vec_push[33] = 1'b0;
        vec_pop[33] = 1'b1;
        vec_push_data[33] = 32'h7e059f6e;
        vec_expected_valid[33] = 1'b1;
        vec_expected_data[33] = 32'h556dd1ae;
        vec_expected_full[33] = 1'b0;
        vec_expected_empty[33] = 1'b0;

        vec_push[34] = 1'b0;
        vec_pop[34] = 1'b0;
        vec_push_data[34] = 32'hf7cd106a;
        vec_expected_valid[34] = 1'b0;
        vec_expected_data[34] = 32'h00000000;
        vec_expected_full[34] = 1'b0;
        vec_expected_empty[34] = 1'b0;

        vec_push[35] = 1'b1;
        vec_pop[35] = 1'b1;
        vec_push_data[35] = 32'hce80fbb2;
        vec_expected_valid[35] = 1'b1;
        vec_expected_data[35] = 32'h42c66e99;
        vec_expected_full[35] = 1'b0;
        vec_expected_empty[35] = 1'b0;

        vec_push[36] = 1'b1;
        vec_pop[36] = 1'b1;
        vec_push_data[36] = 32'h19514d75;
        vec_expected_valid[36] = 1'b1;
        vec_expected_data[36] = 32'h33c9581f;
        vec_expected_full[36] = 1'b0;
        vec_expected_empty[36] = 1'b0;

        vec_push[37] = 1'b0;
        vec_pop[37] = 1'b1;
        vec_push_data[37] = 32'h3b3a6192;
        vec_expected_valid[37] = 1'b1;
        vec_expected_data[37] = 32'h5abff387;
        vec_expected_full[37] = 1'b0;
        vec_expected_empty[37] = 1'b0;

        vec_push[38] = 1'b1;
        vec_pop[38] = 1'b1;
        vec_push_data[38] = 32'h5a69a9e0;
        vec_expected_valid[38] = 1'b1;
        vec_expected_data[38] = 32'hce80fbb2;
        vec_expected_full[38] = 1'b0;
        vec_expected_empty[38] = 1'b0;

        vec_push[39] = 1'b1;
        vec_pop[39] = 1'b0;
        vec_push_data[39] = 32'h408b1c7f;
        vec_expected_valid[39] = 1'b0;
        vec_expected_data[39] = 32'h00000000;
        vec_expected_full[39] = 1'b0;
        vec_expected_empty[39] = 1'b0;

        vec_push[40] = 1'b1;
        vec_pop[40] = 1'b1;
        vec_push_data[40] = 32'ha3be3dc3;
        vec_expected_valid[40] = 1'b1;
        vec_expected_data[40] = 32'h19514d75;
        vec_expected_full[40] = 1'b0;
        vec_expected_empty[40] = 1'b0;

        vec_push[41] = 1'b1;
        vec_pop[41] = 1'b0;
        vec_push_data[41] = 32'hc1047ee7;
        vec_expected_valid[41] = 1'b0;
        vec_expected_data[41] = 32'h00000000;
        vec_expected_full[41] = 1'b0;
        vec_expected_empty[41] = 1'b0;

        vec_push[42] = 1'b1;
        vec_pop[42] = 1'b1;
        vec_push_data[42] = 32'habb22388;
        vec_expected_valid[42] = 1'b1;
        vec_expected_data[42] = 32'h5a69a9e0;
        vec_expected_full[42] = 1'b0;
        vec_expected_empty[42] = 1'b0;

        vec_push[43] = 1'b1;
        vec_pop[43] = 1'b1;
        vec_push_data[43] = 32'h5a57fb98;
        vec_expected_valid[43] = 1'b1;
        vec_expected_data[43] = 32'h408b1c7f;
        vec_expected_full[43] = 1'b0;
        vec_expected_empty[43] = 1'b0;

        vec_push[44] = 1'b1;
        vec_pop[44] = 1'b0;
        vec_push_data[44] = 32'h62d8aa6b;
        vec_expected_valid[44] = 1'b0;
        vec_expected_data[44] = 32'h00000000;
        vec_expected_full[44] = 1'b0;
        vec_expected_empty[44] = 1'b0;

        vec_push[45] = 1'b1;
        vec_pop[45] = 1'b1;
        vec_push_data[45] = 32'haf25d017;
        vec_expected_valid[45] = 1'b1;
        vec_expected_data[45] = 32'ha3be3dc3;
        vec_expected_full[45] = 1'b0;
        vec_expected_empty[45] = 1'b0;

        vec_push[46] = 1'b0;
        vec_pop[46] = 1'b1;
        vec_push_data[46] = 32'h22983f75;
        vec_expected_valid[46] = 1'b1;
        vec_expected_data[46] = 32'hc1047ee7;
        vec_expected_full[46] = 1'b0;
        vec_expected_empty[46] = 1'b0;

        vec_push[47] = 1'b1;
        vec_pop[47] = 1'b0;
        vec_push_data[47] = 32'h778bb735;
        vec_expected_valid[47] = 1'b0;
        vec_expected_data[47] = 32'h00000000;
        vec_expected_full[47] = 1'b0;
        vec_expected_empty[47] = 1'b0;

        vec_push[48] = 1'b0;
        vec_pop[48] = 1'b0;
        vec_push_data[48] = 32'h5ae6ea46;
        vec_expected_valid[48] = 1'b0;
        vec_expected_data[48] = 32'h00000000;
        vec_expected_full[48] = 1'b0;
        vec_expected_empty[48] = 1'b0;

        vec_push[49] = 1'b0;
        vec_pop[49] = 1'b1;
        vec_push_data[49] = 32'h72dcf563;
        vec_expected_valid[49] = 1'b1;
        vec_expected_data[49] = 32'habb22388;
        vec_expected_full[49] = 1'b0;
        vec_expected_empty[49] = 1'b0;

        vec_push[50] = 1'b1;
        vec_pop[50] = 1'b0;
        vec_push_data[50] = 32'h5faa61c2;
        vec_expected_valid[50] = 1'b0;
        vec_expected_data[50] = 32'h00000000;
        vec_expected_full[50] = 1'b0;
        vec_expected_empty[50] = 1'b0;

        vec_push[51] = 1'b1;
        vec_pop[51] = 1'b1;
        vec_push_data[51] = 32'h4db3fccb;
        vec_expected_valid[51] = 1'b1;
        vec_expected_data[51] = 32'h5a57fb98;
        vec_expected_full[51] = 1'b0;
        vec_expected_empty[51] = 1'b0;

        vec_push[52] = 1'b1;
        vec_pop[52] = 1'b1;
        vec_push_data[52] = 32'ha17b089a;
        vec_expected_valid[52] = 1'b1;
        vec_expected_data[52] = 32'h62d8aa6b;
        vec_expected_full[52] = 1'b0;
        vec_expected_empty[52] = 1'b0;

        vec_push[53] = 1'b1;
        vec_pop[53] = 1'b0;
        vec_push_data[53] = 32'h6fd22fc5;
        vec_expected_valid[53] = 1'b0;
        vec_expected_data[53] = 32'h00000000;
        vec_expected_full[53] = 1'b0;
        vec_expected_empty[53] = 1'b0;

        vec_push[54] = 1'b1;
        vec_pop[54] = 1'b1;
        vec_push_data[54] = 32'hce665358;
        vec_expected_valid[54] = 1'b1;
        vec_expected_data[54] = 32'haf25d017;
        vec_expected_full[54] = 1'b0;
        vec_expected_empty[54] = 1'b0;

        vec_push[55] = 1'b0;
        vec_pop[55] = 1'b1;
        vec_push_data[55] = 32'h63ec31e3;
        vec_expected_valid[55] = 1'b1;
        vec_expected_data[55] = 32'h778bb735;
        vec_expected_full[55] = 1'b0;
        vec_expected_empty[55] = 1'b0;

        vec_push[56] = 1'b1;
        vec_pop[56] = 1'b0;
        vec_push_data[56] = 32'h51d9af43;
        vec_expected_valid[56] = 1'b0;
        vec_expected_data[56] = 32'h00000000;
        vec_expected_full[56] = 1'b0;
        vec_expected_empty[56] = 1'b0;

        vec_push[57] = 1'b0;
        vec_pop[57] = 1'b1;
        vec_push_data[57] = 32'ha4da8acc;
        vec_expected_valid[57] = 1'b1;
        vec_expected_data[57] = 32'h5faa61c2;
        vec_expected_full[57] = 1'b0;
        vec_expected_empty[57] = 1'b0;

        vec_push[58] = 1'b0;
        vec_pop[58] = 1'b0;
        vec_push_data[58] = 32'hc9c82580;
        vec_expected_valid[58] = 1'b0;
        vec_expected_data[58] = 32'h00000000;
        vec_expected_full[58] = 1'b0;
        vec_expected_empty[58] = 1'b0;

        vec_push[59] = 1'b0;
        vec_pop[59] = 1'b0;
        vec_push_data[59] = 32'hdd1f48f3;
        vec_expected_valid[59] = 1'b0;
        vec_expected_data[59] = 32'h00000000;
        vec_expected_full[59] = 1'b0;
        vec_expected_empty[59] = 1'b0;

        vec_push[60] = 1'b1;
        vec_pop[60] = 1'b1;
        vec_push_data[60] = 32'h18e46c28;
        vec_expected_valid[60] = 1'b1;
        vec_expected_data[60] = 32'h4db3fccb;
        vec_expected_full[60] = 1'b0;
        vec_expected_empty[60] = 1'b0;

        vec_push[61] = 1'b1;
        vec_pop[61] = 1'b1;
        vec_push_data[61] = 32'h8196063b;
        vec_expected_valid[61] = 1'b1;
        vec_expected_data[61] = 32'ha17b089a;
        vec_expected_full[61] = 1'b0;
        vec_expected_empty[61] = 1'b0;

        vec_push[62] = 1'b1;
        vec_pop[62] = 1'b1;
        vec_push_data[62] = 32'h28137006;
        vec_expected_valid[62] = 1'b1;
        vec_expected_data[62] = 32'h6fd22fc5;
        vec_expected_full[62] = 1'b0;
        vec_expected_empty[62] = 1'b0;

        vec_push[63] = 1'b1;
        vec_pop[63] = 1'b1;
        vec_push_data[63] = 32'hb64e9cda;
        vec_expected_valid[63] = 1'b1;
        vec_expected_data[63] = 32'hce665358;
        vec_expected_full[63] = 1'b0;
        vec_expected_empty[63] = 1'b0;

        vec_push[64] = 1'b1;
        vec_pop[64] = 1'b0;
        vec_push_data[64] = 32'hc5ce4c2f;
        vec_expected_valid[64] = 1'b0;
        vec_expected_data[64] = 32'h00000000;
        vec_expected_full[64] = 1'b0;
        vec_expected_empty[64] = 1'b0;

        vec_push[65] = 1'b1;
        vec_pop[65] = 1'b1;
        vec_push_data[65] = 32'ha9b5a678;
        vec_expected_valid[65] = 1'b1;
        vec_expected_data[65] = 32'h51d9af43;
        vec_expected_full[65] = 1'b0;
        vec_expected_empty[65] = 1'b0;

        vec_push[66] = 1'b1;
        vec_pop[66] = 1'b1;
        vec_push_data[66] = 32'hb703d83d;
        vec_expected_valid[66] = 1'b1;
        vec_expected_data[66] = 32'h18e46c28;
        vec_expected_full[66] = 1'b0;
        vec_expected_empty[66] = 1'b0;

        vec_push[67] = 1'b1;
        vec_pop[67] = 1'b1;
        vec_push_data[67] = 32'hb5f6fb24;
        vec_expected_valid[67] = 1'b1;
        vec_expected_data[67] = 32'h8196063b;
        vec_expected_full[67] = 1'b0;
        vec_expected_empty[67] = 1'b0;

        vec_push[68] = 1'b1;
        vec_pop[68] = 1'b0;
        vec_push_data[68] = 32'hea983c71;
        vec_expected_valid[68] = 1'b0;
        vec_expected_data[68] = 32'h00000000;
        vec_expected_full[68] = 1'b0;
        vec_expected_empty[68] = 1'b0;

        vec_push[69] = 1'b1;
        vec_pop[69] = 1'b1;
        vec_push_data[69] = 32'ha1fa011c;
        vec_expected_valid[69] = 1'b1;
        vec_expected_data[69] = 32'h28137006;
        vec_expected_full[69] = 1'b0;
        vec_expected_empty[69] = 1'b0;

        vec_push[70] = 1'b1;
        vec_pop[70] = 1'b1;
        vec_push_data[70] = 32'h128e6caf;
        vec_expected_valid[70] = 1'b1;
        vec_expected_data[70] = 32'hb64e9cda;
        vec_expected_full[70] = 1'b0;
        vec_expected_empty[70] = 1'b0;

        vec_push[71] = 1'b1;
        vec_pop[71] = 1'b0;
        vec_push_data[71] = 32'hd455c68c;
        vec_expected_valid[71] = 1'b0;
        vec_expected_data[71] = 32'h00000000;
        vec_expected_full[71] = 1'b0;
        vec_expected_empty[71] = 1'b0;

        vec_push[72] = 1'b1;
        vec_pop[72] = 1'b0;
        vec_push_data[72] = 32'h5942696e;
        vec_expected_valid[72] = 1'b0;
        vec_expected_data[72] = 32'h00000000;
        vec_expected_full[72] = 1'b0;
        vec_expected_empty[72] = 1'b0;

        vec_push[73] = 1'b1;
        vec_pop[73] = 1'b1;
        vec_push_data[73] = 32'hbcb4933c;
        vec_expected_valid[73] = 1'b1;
        vec_expected_data[73] = 32'hc5ce4c2f;
        vec_expected_full[73] = 1'b0;
        vec_expected_empty[73] = 1'b0;

        vec_push[74] = 1'b1;
        vec_pop[74] = 1'b1;
        vec_push_data[74] = 32'h4c2f16a3;
        vec_expected_valid[74] = 1'b1;
        vec_expected_data[74] = 32'ha9b5a678;
        vec_expected_full[74] = 1'b0;
        vec_expected_empty[74] = 1'b0;

        vec_push[75] = 1'b1;
        vec_pop[75] = 1'b1;
        vec_push_data[75] = 32'h5f4d70c7;
        vec_expected_valid[75] = 1'b1;
        vec_expected_data[75] = 32'hb703d83d;
        vec_expected_full[75] = 1'b0;
        vec_expected_empty[75] = 1'b0;

        vec_push[76] = 1'b1;
        vec_pop[76] = 1'b1;
        vec_push_data[76] = 32'hff203967;
        vec_expected_valid[76] = 1'b1;
        vec_expected_data[76] = 32'hb5f6fb24;
        vec_expected_full[76] = 1'b0;
        vec_expected_empty[76] = 1'b0;

        vec_push[77] = 1'b1;
        vec_pop[77] = 1'b1;
        vec_push_data[77] = 32'hf2ed5291;
        vec_expected_valid[77] = 1'b1;
        vec_expected_data[77] = 32'hea983c71;
        vec_expected_full[77] = 1'b0;
        vec_expected_empty[77] = 1'b0;

        vec_push[78] = 1'b1;
        vec_pop[78] = 1'b0;
        vec_push_data[78] = 32'habd83578;
        vec_expected_valid[78] = 1'b0;
        vec_expected_data[78] = 32'h00000000;
        vec_expected_full[78] = 1'b0;
        vec_expected_empty[78] = 1'b0;

        vec_push[79] = 1'b1;
        vec_pop[79] = 1'b1;
        vec_push_data[79] = 32'hfe04f26b;
        vec_expected_valid[79] = 1'b1;
        vec_expected_data[79] = 32'ha1fa011c;
        vec_expected_full[79] = 1'b0;
        vec_expected_empty[79] = 1'b0;

        vec_push[80] = 1'b1;
        vec_pop[80] = 1'b0;
        vec_push_data[80] = 32'h32829d3e;
        vec_expected_valid[80] = 1'b0;
        vec_expected_data[80] = 32'h00000000;
        vec_expected_full[80] = 1'b0;
        vec_expected_empty[80] = 1'b0;

        vec_push[81] = 1'b1;
        vec_pop[81] = 1'b1;
        vec_push_data[81] = 32'hd3358957;
        vec_expected_valid[81] = 1'b1;
        vec_expected_data[81] = 32'h128e6caf;
        vec_expected_full[81] = 1'b0;
        vec_expected_empty[81] = 1'b0;

        vec_push[82] = 1'b1;
        vec_pop[82] = 1'b0;
        vec_push_data[82] = 32'h4ffce5f0;
        vec_expected_valid[82] = 1'b0;
        vec_expected_data[82] = 32'h00000000;
        vec_expected_full[82] = 1'b0;
        vec_expected_empty[82] = 1'b0;

        vec_push[83] = 1'b1;
        vec_pop[83] = 1'b0;
        vec_push_data[83] = 32'he31d93f7;
        vec_expected_valid[83] = 1'b0;
        vec_expected_data[83] = 32'h00000000;
        vec_expected_full[83] = 1'b0;
        vec_expected_empty[83] = 1'b0;

        vec_push[84] = 1'b1;
        vec_pop[84] = 1'b1;
        vec_push_data[84] = 32'h72415057;
        vec_expected_valid[84] = 1'b1;
        vec_expected_data[84] = 32'hd455c68c;
        vec_expected_full[84] = 1'b0;
        vec_expected_empty[84] = 1'b0;

        vec_push[85] = 1'b1;
        vec_pop[85] = 1'b1;
        vec_push_data[85] = 32'hdc669f57;
        vec_expected_valid[85] = 1'b1;
        vec_expected_data[85] = 32'h5942696e;
        vec_expected_full[85] = 1'b0;
        vec_expected_empty[85] = 1'b0;

        vec_push[86] = 1'b1;
        vec_pop[86] = 1'b1;
        vec_push_data[86] = 32'he4c30ad7;
        vec_expected_valid[86] = 1'b1;
        vec_expected_data[86] = 32'hbcb4933c;
        vec_expected_full[86] = 1'b0;
        vec_expected_empty[86] = 1'b0;

        vec_push[87] = 1'b1;
        vec_pop[87] = 1'b1;
        vec_push_data[87] = 32'hfbe76125;
        vec_expected_valid[87] = 1'b1;
        vec_expected_data[87] = 32'h4c2f16a3;
        vec_expected_full[87] = 1'b0;
        vec_expected_empty[87] = 1'b0;

        vec_push[88] = 1'b1;
        vec_pop[88] = 1'b1;
        vec_push_data[88] = 32'hf3919d96;
        vec_expected_valid[88] = 1'b1;
        vec_expected_data[88] = 32'h5f4d70c7;
        vec_expected_full[88] = 1'b0;
        vec_expected_empty[88] = 1'b0;

        vec_push[89] = 1'b1;
        vec_pop[89] = 1'b0;
        vec_push_data[89] = 32'hfe781429;
        vec_expected_valid[89] = 1'b0;
        vec_expected_data[89] = 32'h00000000;
        vec_expected_full[89] = 1'b0;
        vec_expected_empty[89] = 1'b0;

        vec_push[90] = 1'b1;
        vec_pop[90] = 1'b1;
        vec_push_data[90] = 32'hd8f4bd22;
        vec_expected_valid[90] = 1'b1;
        vec_expected_data[90] = 32'hff203967;
        vec_expected_full[90] = 1'b0;
        vec_expected_empty[90] = 1'b0;

        vec_push[91] = 1'b1;
        vec_pop[91] = 1'b1;
        vec_push_data[91] = 32'h764ef1a5;
        vec_expected_valid[91] = 1'b1;
        vec_expected_data[91] = 32'hf2ed5291;
        vec_expected_full[91] = 1'b0;
        vec_expected_empty[91] = 1'b0;

        vec_push[92] = 1'b1;
        vec_pop[92] = 1'b1;
        vec_push_data[92] = 32'h6dcd6db6;
        vec_expected_valid[92] = 1'b1;
        vec_expected_data[92] = 32'habd83578;
        vec_expected_full[92] = 1'b0;
        vec_expected_empty[92] = 1'b0;

        vec_push[93] = 1'b1;
        vec_pop[93] = 1'b0;
        vec_push_data[93] = 32'h4d50ce81;
        vec_expected_valid[93] = 1'b0;
        vec_expected_data[93] = 32'h00000000;
        vec_expected_full[93] = 1'b0;
        vec_expected_empty[93] = 1'b0;

        vec_push[94] = 1'b1;
        vec_pop[94] = 1'b1;
        vec_push_data[94] = 32'he420e214;
        vec_expected_valid[94] = 1'b1;
        vec_expected_data[94] = 32'hfe04f26b;
        vec_expected_full[94] = 1'b0;
        vec_expected_empty[94] = 1'b0;

        vec_push[95] = 1'b1;
        vec_pop[95] = 1'b1;
        vec_push_data[95] = 32'h0b51c21b;
        vec_expected_valid[95] = 1'b1;
        vec_expected_data[95] = 32'h32829d3e;
        vec_expected_full[95] = 1'b0;
        vec_expected_empty[95] = 1'b0;

        vec_push[96] = 1'b0;
        vec_pop[96] = 1'b1;
        vec_push_data[96] = 32'ha60a201d;
        vec_expected_valid[96] = 1'b1;
        vec_expected_data[96] = 32'hd3358957;
        vec_expected_full[96] = 1'b0;
        vec_expected_empty[96] = 1'b0;

        vec_push[97] = 1'b0;
        vec_pop[97] = 1'b1;
        vec_push_data[97] = 32'he6e0646f;
        vec_expected_valid[97] = 1'b1;
        vec_expected_data[97] = 32'h4ffce5f0;
        vec_expected_full[97] = 1'b0;
        vec_expected_empty[97] = 1'b0;

        vec_push[98] = 1'b0;
        vec_pop[98] = 1'b1;
        vec_push_data[98] = 32'h89f6ba08;
        vec_expected_valid[98] = 1'b1;
        vec_expected_data[98] = 32'he31d93f7;
        vec_expected_full[98] = 1'b0;
        vec_expected_empty[98] = 1'b0;

        vec_push[99] = 1'b0;
        vec_pop[99] = 1'b1;
        vec_push_data[99] = 32'heab02b0f;
        vec_expected_valid[99] = 1'b1;
        vec_expected_data[99] = 32'h72415057;
        vec_expected_full[99] = 1'b0;
        vec_expected_empty[99] = 1'b0;

        vec_push[100] = 1'b0;
        vec_pop[100] = 1'b1;
        vec_push_data[100] = 32'h5cb18263;
        vec_expected_valid[100] = 1'b1;
        vec_expected_data[100] = 32'hdc669f57;
        vec_expected_full[100] = 1'b0;
        vec_expected_empty[100] = 1'b0;

        vec_push[101] = 1'b0;
        vec_pop[101] = 1'b1;
        vec_push_data[101] = 32'h761ca2c5;
        vec_expected_valid[101] = 1'b1;
        vec_expected_data[101] = 32'he4c30ad7;
        vec_expected_full[101] = 1'b0;
        vec_expected_empty[101] = 1'b0;

        vec_push[102] = 1'b0;
        vec_pop[102] = 1'b1;
        vec_push_data[102] = 32'h4d6ccc9a;
        vec_expected_valid[102] = 1'b1;
        vec_expected_data[102] = 32'hfbe76125;
        vec_expected_full[102] = 1'b0;
        vec_expected_empty[102] = 1'b0;

        vec_push[103] = 1'b0;
        vec_pop[103] = 1'b1;
        vec_push_data[103] = 32'h2f25e24f;
        vec_expected_valid[103] = 1'b1;
        vec_expected_data[103] = 32'hf3919d96;
        vec_expected_full[103] = 1'b0;
        vec_expected_empty[103] = 1'b0;

        vec_push[104] = 1'b0;
        vec_pop[104] = 1'b1;
        vec_push_data[104] = 32'hb237d176;
        vec_expected_valid[104] = 1'b1;
        vec_expected_data[104] = 32'hfe781429;
        vec_expected_full[104] = 1'b0;
        vec_expected_empty[104] = 1'b0;

        vec_push[105] = 1'b0;
        vec_pop[105] = 1'b1;
        vec_push_data[105] = 32'h68dcbb6a;
        vec_expected_valid[105] = 1'b1;
        vec_expected_data[105] = 32'hd8f4bd22;
        vec_expected_full[105] = 1'b0;
        vec_expected_empty[105] = 1'b0;

        vec_push[106] = 1'b0;
        vec_pop[106] = 1'b1;
        vec_push_data[106] = 32'hf88cd9c7;
        vec_expected_valid[106] = 1'b1;
        vec_expected_data[106] = 32'h764ef1a5;
        vec_expected_full[106] = 1'b0;
        vec_expected_empty[106] = 1'b0;

        vec_push[107] = 1'b0;
        vec_pop[107] = 1'b1;
        vec_push_data[107] = 32'h9219f8fc;
        vec_expected_valid[107] = 1'b1;
        vec_expected_data[107] = 32'h6dcd6db6;
        vec_expected_full[107] = 1'b0;
        vec_expected_empty[107] = 1'b0;

        vec_push[108] = 1'b0;
        vec_pop[108] = 1'b1;
        vec_push_data[108] = 32'h14955e0e;
        vec_expected_valid[108] = 1'b1;
        vec_expected_data[108] = 32'h4d50ce81;
        vec_expected_full[108] = 1'b0;
        vec_expected_empty[108] = 1'b0;

        vec_push[109] = 1'b0;
        vec_pop[109] = 1'b1;
        vec_push_data[109] = 32'h8efaa5f0;
        vec_expected_valid[109] = 1'b1;
        vec_expected_data[109] = 32'he420e214;
        vec_expected_full[109] = 1'b0;
        vec_expected_empty[109] = 1'b0;

        vec_push[110] = 1'b0;
        vec_pop[110] = 1'b1;
        vec_push_data[110] = 32'h4ba2ba21;
        vec_expected_valid[110] = 1'b1;
        vec_expected_data[110] = 32'h0b51c21b;
        vec_expected_full[110] = 1'b0;
        vec_expected_empty[110] = 1'b1;

        vec_push[111] = 1'b0;
        vec_pop[111] = 1'b1;
        vec_push_data[111] = 32'h84f0d38b;
        vec_expected_valid[111] = 1'b0;
        vec_expected_data[111] = 32'h00000000;
        vec_expected_full[111] = 1'b0;
        vec_expected_empty[111] = 1'b1;

        vec_push[112] = 1'b0;
        vec_pop[112] = 1'b1;
        vec_push_data[112] = 32'hcfd5b992;
        vec_expected_valid[112] = 1'b0;
        vec_expected_data[112] = 32'h00000000;
        vec_expected_full[112] = 1'b0;
        vec_expected_empty[112] = 1'b1;

        vec_push[113] = 1'b0;
        vec_pop[113] = 1'b1;
        vec_push_data[113] = 32'h1fb5f74b;
        vec_expected_valid[113] = 1'b0;
        vec_expected_data[113] = 32'h00000000;
        vec_expected_full[113] = 1'b0;
        vec_expected_empty[113] = 1'b1;

        vec_push[114] = 1'b0;
        vec_pop[114] = 1'b1;
        vec_push_data[114] = 32'h96db441f;
        vec_expected_valid[114] = 1'b0;
        vec_expected_data[114] = 32'h00000000;
        vec_expected_full[114] = 1'b0;
        vec_expected_empty[114] = 1'b1;

        vec_push[115] = 1'b0;
        vec_pop[115] = 1'b1;
        vec_push_data[115] = 32'he4f027c6;
        vec_expected_valid[115] = 1'b0;
        vec_expected_data[115] = 32'h00000000;
        vec_expected_full[115] = 1'b0;
        vec_expected_empty[115] = 1'b1;

        vec_push[116] = 1'b0;
        vec_pop[116] = 1'b1;
        vec_push_data[116] = 32'h8993bd88;
        vec_expected_valid[116] = 1'b0;
        vec_expected_data[116] = 32'h00000000;
        vec_expected_full[116] = 1'b0;
        vec_expected_empty[116] = 1'b1;

        vec_push[117] = 1'b0;
        vec_pop[117] = 1'b1;
        vec_push_data[117] = 32'h7e533a8f;
        vec_expected_valid[117] = 1'b0;
        vec_expected_data[117] = 32'h00000000;
        vec_expected_full[117] = 1'b0;
        vec_expected_empty[117] = 1'b1;

        vec_push[118] = 1'b0;
        vec_pop[118] = 1'b1;
        vec_push_data[118] = 32'hd1de38a1;
        vec_expected_valid[118] = 1'b0;
        vec_expected_data[118] = 32'h00000000;
        vec_expected_full[118] = 1'b0;
        vec_expected_empty[118] = 1'b1;

        vec_push[119] = 1'b0;
        vec_pop[119] = 1'b1;
        vec_push_data[119] = 32'heb9e6342;
        vec_expected_valid[119] = 1'b0;
        vec_expected_data[119] = 32'h00000000;
        vec_expected_full[119] = 1'b0;
        vec_expected_empty[119] = 1'b1;

        vec_push[120] = 1'b0;
        vec_pop[120] = 1'b1;
        vec_push_data[120] = 32'hf2720929;
        vec_expected_valid[120] = 1'b0;
        vec_expected_data[120] = 32'h00000000;
        vec_expected_full[120] = 1'b0;
        vec_expected_empty[120] = 1'b1;

        vec_push[121] = 1'b0;
        vec_pop[121] = 1'b1;
        vec_push_data[121] = 32'ha8b51b84;
        vec_expected_valid[121] = 1'b0;
        vec_expected_data[121] = 32'h00000000;
        vec_expected_full[121] = 1'b0;
        vec_expected_empty[121] = 1'b1;

        vec_push[122] = 1'b0;
        vec_pop[122] = 1'b1;
        vec_push_data[122] = 32'hb40dcbf7;
        vec_expected_valid[122] = 1'b0;
        vec_expected_data[122] = 32'h00000000;
        vec_expected_full[122] = 1'b0;
        vec_expected_empty[122] = 1'b1;

        vec_push[123] = 1'b0;
        vec_pop[123] = 1'b1;
        vec_push_data[123] = 32'hf3aef2a5;
        vec_expected_valid[123] = 1'b0;
        vec_expected_data[123] = 32'h00000000;
        vec_expected_full[123] = 1'b0;
        vec_expected_empty[123] = 1'b1;

        vec_push[124] = 1'b0;
        vec_pop[124] = 1'b1;
        vec_push_data[124] = 32'h1a6d9e5c;
        vec_expected_valid[124] = 1'b0;
        vec_expected_data[124] = 32'h00000000;
        vec_expected_full[124] = 1'b0;
        vec_expected_empty[124] = 1'b1;

        vec_push[125] = 1'b0;
        vec_pop[125] = 1'b1;
        vec_push_data[125] = 32'hf616c436;
        vec_expected_valid[125] = 1'b0;
        vec_expected_data[125] = 32'h00000000;
        vec_expected_full[125] = 1'b0;
        vec_expected_empty[125] = 1'b1;

        vec_push[126] = 1'b0;
        vec_pop[126] = 1'b1;
        vec_push_data[126] = 32'he62b7517;
        vec_expected_valid[126] = 1'b0;
        vec_expected_data[126] = 32'h00000000;
        vec_expected_full[126] = 1'b0;
        vec_expected_empty[126] = 1'b1;

        vec_push[127] = 1'b0;
        vec_pop[127] = 1'b1;
        vec_push_data[127] = 32'h217527a9;
        vec_expected_valid[127] = 1'b0;
        vec_expected_data[127] = 32'h00000000;
        vec_expected_full[127] = 1'b0;
        vec_expected_empty[127] = 1'b1;

        repeat (2) @(posedge i_clk);
        i_rst_n = 1'b1;

        for (int n = 0; n < NUM_CASES; n = n + 1) begin
            @(negedge i_clk);
            i_push = vec_push[n];
            i_pop = vec_pop[n];
            i_push_data = vec_push_data[n];
            @(posedge i_clk);
            #1;
            $display("fifo case=%0d push=%0b pop=%0b valid=%0b exp_valid=%0b data=%h exp=%h full=%0b empty=%0b",
                n, i_push, i_pop, o_pop_valid, vec_expected_valid[n],
                o_pop_data, vec_expected_data[n], o_full, o_empty);
            if ((o_pop_valid !== vec_expected_valid[n]) ||
                (o_pop_data !== vec_expected_data[n]) ||
                (o_full !== vec_expected_full[n]) ||
                (o_empty !== vec_expected_empty[n])) begin
                errors = errors + 1;
                $display("fifo mismatch at case %0d", n);
            end
        end

        if (errors == 0) begin
            $display("fifo_tb PASS");
        end else begin
            $display("fifo_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
