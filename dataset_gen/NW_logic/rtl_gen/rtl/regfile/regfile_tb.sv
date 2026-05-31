module regfile_tb;
    localparam int W_PORT_WIDTH = 1;
    localparam int W_ADDR_BITS = 6;
    localparam int W_DATA_BITS = 32;
    localparam int R_ADDR_BITS = 6;
    localparam int R_DATA_BITS = 32;
    localparam int NUM_CASES = 96;

    logic i_clk;
    logic i_rst_n;
    logic [W_PORT_WIDTH-1:0] i_w_en;
    logic [W_ADDR_BITS-1:0] i_w_addr;
    logic [W_DATA_BITS-1:0] i_w_data;
    logic [R_ADDR_BITS-1:0] i_r_addr;
    logic [R_DATA_BITS-1:0] o_r_data;

    logic [W_PORT_WIDTH-1:0] vec_w_en [0:NUM_CASES-1];
    logic [W_ADDR_BITS-1:0] vec_w_addr [0:NUM_CASES-1];
    logic [W_DATA_BITS-1:0] vec_w_data [0:NUM_CASES-1];
    logic [R_ADDR_BITS-1:0] vec_r_addr [0:NUM_CASES-1];
    logic [R_DATA_BITS-1:0] vec_r_expected [0:NUM_CASES-1];
    int errors;

    regfile dut (
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .i_w_en(i_w_en),
        .i_w_addr(i_w_addr),
        .i_w_data(i_w_data),
        .i_r_addr(i_r_addr),
        .o_r_data(o_r_data)
    );

    always #5 i_clk <= ~i_clk;

    initial begin
        i_clk = 1'b0;
        i_rst_n = 1'b0;
        i_w_en = '0;
        i_w_addr = '0;
        i_w_data = '0;
        i_r_addr = '0;
        errors = 0;

        vec_w_en[0] = 1'h1;
        vec_w_addr[0] = 6'h00;
        vec_w_data[0] = 32'h850a4120;
        vec_r_addr[0] = 6'h00;
        vec_r_expected[0] = 32'h850a4120;

        vec_w_en[1] = 1'h1;
        vec_w_addr[1] = 6'h01;
        vec_w_data[1] = 32'h885e3586;
        vec_r_addr[1] = 6'h02;
        vec_r_expected[1] = 32'h00000000;

        vec_w_en[2] = 1'h1;
        vec_w_addr[2] = 6'h39;
        vec_w_data[2] = 32'hd26271bc;
        vec_r_addr[2] = 6'h29;
        vec_r_expected[2] = 32'h00000000;

        vec_w_en[3] = 1'h1;
        vec_w_addr[3] = 6'h13;
        vec_w_data[3] = 32'he52c8de9;
        vec_r_addr[3] = 6'h00;
        vec_r_expected[3] = 32'h850a4120;

        vec_w_en[4] = 1'h1;
        vec_w_addr[4] = 6'h16;
        vec_w_data[4] = 32'h348c966c;
        vec_r_addr[4] = 6'h09;
        vec_r_expected[4] = 32'h00000000;

        vec_w_en[5] = 1'h1;
        vec_w_addr[5] = 6'h05;
        vec_w_data[5] = 32'h26ac8ee5;
        vec_r_addr[5] = 6'h28;
        vec_r_expected[5] = 32'h00000000;

        vec_w_en[6] = 1'h1;
        vec_w_addr[6] = 6'h29;
        vec_w_data[6] = 32'ha921d99c;
        vec_r_addr[6] = 6'h06;
        vec_r_expected[6] = 32'h00000000;

        vec_w_en[7] = 1'h1;
        vec_w_addr[7] = 6'h34;
        vec_w_data[7] = 32'hc54622cf;
        vec_r_addr[7] = 6'h26;
        vec_r_expected[7] = 32'h00000000;

        vec_w_en[8] = 1'h1;
        vec_w_addr[8] = 6'h37;
        vec_w_data[8] = 32'hc23bacca;
        vec_r_addr[8] = 6'h15;
        vec_r_expected[8] = 32'h00000000;

        vec_w_en[9] = 1'h1;
        vec_w_addr[9] = 6'h2d;
        vec_w_data[9] = 32'hbff5aa50;
        vec_r_addr[9] = 6'h26;
        vec_r_expected[9] = 32'h00000000;

        vec_w_en[10] = 1'h1;
        vec_w_addr[10] = 6'h03;
        vec_w_data[10] = 32'h84fc2b6e;
        vec_r_addr[10] = 6'h2a;
        vec_r_expected[10] = 32'h00000000;

        vec_w_en[11] = 1'h1;
        vec_w_addr[11] = 6'h10;
        vec_w_data[11] = 32'h57e245ed;
        vec_r_addr[11] = 6'h23;
        vec_r_expected[11] = 32'h00000000;

        vec_w_en[12] = 1'h1;
        vec_w_addr[12] = 6'h27;
        vec_w_data[12] = 32'h27d09367;
        vec_r_addr[12] = 6'h05;
        vec_r_expected[12] = 32'h26ac8ee5;

        vec_w_en[13] = 1'h1;
        vec_w_addr[13] = 6'h01;
        vec_w_data[13] = 32'hd3f97f17;
        vec_r_addr[13] = 6'h34;
        vec_r_expected[13] = 32'hc54622cf;

        vec_w_en[14] = 1'h1;
        vec_w_addr[14] = 6'h17;
        vec_w_data[14] = 32'hc43a6c7b;
        vec_r_addr[14] = 6'h2f;
        vec_r_expected[14] = 32'h00000000;

        vec_w_en[15] = 1'h1;
        vec_w_addr[15] = 6'h01;
        vec_w_data[15] = 32'h94f668af;
        vec_r_addr[15] = 6'h16;
        vec_r_expected[15] = 32'h348c966c;

        vec_w_en[16] = 1'h1;
        vec_w_addr[16] = 6'h2b;
        vec_w_data[16] = 32'h17419b62;
        vec_r_addr[16] = 6'h17;
        vec_r_expected[16] = 32'hc43a6c7b;

        vec_w_en[17] = 1'h1;
        vec_w_addr[17] = 6'h02;
        vec_w_data[17] = 32'ha036e72e;
        vec_r_addr[17] = 6'h39;
        vec_r_expected[17] = 32'hd26271bc;

        vec_w_en[18] = 1'h1;
        vec_w_addr[18] = 6'h0a;
        vec_w_data[18] = 32'h85015631;
        vec_r_addr[18] = 6'h04;
        vec_r_expected[18] = 32'h00000000;

        vec_w_en[19] = 1'h1;
        vec_w_addr[19] = 6'h20;
        vec_w_data[19] = 32'he3c6314b;
        vec_r_addr[19] = 6'h33;
        vec_r_expected[19] = 32'h00000000;

        vec_w_en[20] = 1'h1;
        vec_w_addr[20] = 6'h06;
        vec_w_data[20] = 32'h634abb38;
        vec_r_addr[20] = 6'h02;
        vec_r_expected[20] = 32'ha036e72e;

        vec_w_en[21] = 1'h1;
        vec_w_addr[21] = 6'h28;
        vec_w_data[21] = 32'h1fcb79ab;
        vec_r_addr[21] = 6'h36;
        vec_r_expected[21] = 32'h00000000;

        vec_w_en[22] = 1'h1;
        vec_w_addr[22] = 6'h1f;
        vec_w_data[22] = 32'h49d373c4;
        vec_r_addr[22] = 6'h2c;
        vec_r_expected[22] = 32'h00000000;

        vec_w_en[23] = 1'h1;
        vec_w_addr[23] = 6'h00;
        vec_w_data[23] = 32'he0ec39e5;
        vec_r_addr[23] = 6'h05;
        vec_r_expected[23] = 32'h26ac8ee5;

        vec_w_en[24] = 1'h0;
        vec_w_addr[24] = 6'h0d;
        vec_w_data[24] = 32'h21c3555c;
        vec_r_addr[24] = 6'h03;
        vec_r_expected[24] = 32'h84fc2b6e;

        vec_w_en[25] = 1'h0;
        vec_w_addr[25] = 6'h04;
        vec_w_data[25] = 32'heb41d9eb;
        vec_r_addr[25] = 6'h38;
        vec_r_expected[25] = 32'h00000000;

        vec_w_en[26] = 1'h1;
        vec_w_addr[26] = 6'h00;
        vec_w_data[26] = 32'hfb3a1bde;
        vec_r_addr[26] = 6'h04;
        vec_r_expected[26] = 32'h00000000;

        vec_w_en[27] = 1'h1;
        vec_w_addr[27] = 6'h11;
        vec_w_data[27] = 32'hac31d7b1;
        vec_r_addr[27] = 6'h0d;
        vec_r_expected[27] = 32'h00000000;

        vec_w_en[28] = 1'h1;
        vec_w_addr[28] = 6'h0f;
        vec_w_data[28] = 32'hd2c43bdd;
        vec_r_addr[28] = 6'h2a;
        vec_r_expected[28] = 32'h00000000;

        vec_w_en[29] = 1'h1;
        vec_w_addr[29] = 6'h2f;
        vec_w_data[29] = 32'hfff0589e;
        vec_r_addr[29] = 6'h25;
        vec_r_expected[29] = 32'h00000000;

        vec_w_en[30] = 1'h1;
        vec_w_addr[30] = 6'h02;
        vec_w_data[30] = 32'h76fcecd5;
        vec_r_addr[30] = 6'h02;
        vec_r_expected[30] = 32'h76fcecd5;

        vec_w_en[31] = 1'h1;
        vec_w_addr[31] = 6'h2e;
        vec_w_data[31] = 32'h5d1d0561;
        vec_r_addr[31] = 6'h1d;
        vec_r_expected[31] = 32'h00000000;

        vec_w_en[32] = 1'h1;
        vec_w_addr[32] = 6'h3a;
        vec_w_data[32] = 32'h4c3f12a4;
        vec_r_addr[32] = 6'h0c;
        vec_r_expected[32] = 32'h00000000;

        vec_w_en[33] = 1'h0;
        vec_w_addr[33] = 6'h35;
        vec_w_data[33] = 32'h3b3435b5;
        vec_r_addr[33] = 6'h2f;
        vec_r_expected[33] = 32'hfff0589e;

        vec_w_en[34] = 1'h1;
        vec_w_addr[34] = 6'h30;
        vec_w_data[34] = 32'hc18c61c3;
        vec_r_addr[34] = 6'h00;
        vec_r_expected[34] = 32'hfb3a1bde;

        vec_w_en[35] = 1'h1;
        vec_w_addr[35] = 6'h00;
        vec_w_data[35] = 32'h8cc7b31b;
        vec_r_addr[35] = 6'h1b;
        vec_r_expected[35] = 32'h00000000;

        vec_w_en[36] = 1'h1;
        vec_w_addr[36] = 6'h05;
        vec_w_data[36] = 32'h5ce8aa56;
        vec_r_addr[36] = 6'h01;
        vec_r_expected[36] = 32'h94f668af;

        vec_w_en[37] = 1'h1;
        vec_w_addr[37] = 6'h02;
        vec_w_data[37] = 32'h56d47f25;
        vec_r_addr[37] = 6'h2b;
        vec_r_expected[37] = 32'h17419b62;

        vec_w_en[38] = 1'h1;
        vec_w_addr[38] = 6'h2a;
        vec_w_data[38] = 32'hee47c66e;
        vec_r_addr[38] = 6'h1b;
        vec_r_expected[38] = 32'h00000000;

        vec_w_en[39] = 1'h1;
        vec_w_addr[39] = 6'h0d;
        vec_w_data[39] = 32'h34ddf4ab;
        vec_r_addr[39] = 6'h27;
        vec_r_expected[39] = 32'h27d09367;

        vec_w_en[40] = 1'h1;
        vec_w_addr[40] = 6'h05;
        vec_w_data[40] = 32'h73a75f47;
        vec_r_addr[40] = 6'h1d;
        vec_r_expected[40] = 32'h00000000;

        vec_w_en[41] = 1'h1;
        vec_w_addr[41] = 6'h23;
        vec_w_data[41] = 32'h232d9272;
        vec_r_addr[41] = 6'h34;
        vec_r_expected[41] = 32'hc54622cf;

        vec_w_en[42] = 1'h0;
        vec_w_addr[42] = 6'h13;
        vec_w_data[42] = 32'h8afd851e;
        vec_r_addr[42] = 6'h00;
        vec_r_expected[42] = 32'h8cc7b31b;

        vec_w_en[43] = 1'h0;
        vec_w_addr[43] = 6'h19;
        vec_w_data[43] = 32'h310d49f3;
        vec_r_addr[43] = 6'h0d;
        vec_r_expected[43] = 32'h34ddf4ab;

        vec_w_en[44] = 1'h1;
        vec_w_addr[44] = 6'h01;
        vec_w_data[44] = 32'h2c7d4e41;
        vec_r_addr[44] = 6'h04;
        vec_r_expected[44] = 32'h00000000;

        vec_w_en[45] = 1'h0;
        vec_w_addr[45] = 6'h03;
        vec_w_data[45] = 32'hb4a302a7;
        vec_r_addr[45] = 6'h35;
        vec_r_expected[45] = 32'h00000000;

        vec_w_en[46] = 1'h1;
        vec_w_addr[46] = 6'h20;
        vec_w_data[46] = 32'h3826e1d0;
        vec_r_addr[46] = 6'h3f;
        vec_r_expected[46] = 32'h00000000;

        vec_w_en[47] = 1'h1;
        vec_w_addr[47] = 6'h00;
        vec_w_data[47] = 32'h21316228;
        vec_r_addr[47] = 6'h0a;
        vec_r_expected[47] = 32'h85015631;

        vec_w_en[48] = 1'h1;
        vec_w_addr[48] = 6'h06;
        vec_w_data[48] = 32'h6f926532;
        vec_r_addr[48] = 6'h06;
        vec_r_expected[48] = 32'h6f926532;

        vec_w_en[49] = 1'h1;
        vec_w_addr[49] = 6'h2e;
        vec_w_data[49] = 32'h35364a2a;
        vec_r_addr[49] = 6'h18;
        vec_r_expected[49] = 32'h00000000;

        vec_w_en[50] = 1'h0;
        vec_w_addr[50] = 6'h01;
        vec_w_data[50] = 32'h084cbb51;
        vec_r_addr[50] = 6'h01;
        vec_r_expected[50] = 32'h2c7d4e41;

        vec_w_en[51] = 1'h1;
        vec_w_addr[51] = 6'h1d;
        vec_w_data[51] = 32'ha43ab567;
        vec_r_addr[51] = 6'h30;
        vec_r_expected[51] = 32'hc18c61c3;

        vec_w_en[52] = 1'h1;
        vec_w_addr[52] = 6'h14;
        vec_w_data[52] = 32'h8883955c;
        vec_r_addr[52] = 6'h26;
        vec_r_expected[52] = 32'h00000000;

        vec_w_en[53] = 1'h1;
        vec_w_addr[53] = 6'h22;
        vec_w_data[53] = 32'h9dbae8b8;
        vec_r_addr[53] = 6'h3f;
        vec_r_expected[53] = 32'h00000000;

        vec_w_en[54] = 1'h1;
        vec_w_addr[54] = 6'h13;
        vec_w_data[54] = 32'he9170f78;
        vec_r_addr[54] = 6'h05;
        vec_r_expected[54] = 32'h73a75f47;

        vec_w_en[55] = 1'h1;
        vec_w_addr[55] = 6'h06;
        vec_w_data[55] = 32'h3571f178;
        vec_r_addr[55] = 6'h05;
        vec_r_expected[55] = 32'h73a75f47;

        vec_w_en[56] = 1'h1;
        vec_w_addr[56] = 6'h0d;
        vec_w_data[56] = 32'hf6691d19;
        vec_r_addr[56] = 6'h1d;
        vec_r_expected[56] = 32'ha43ab567;

        vec_w_en[57] = 1'h1;
        vec_w_addr[57] = 6'h30;
        vec_w_data[57] = 32'h26e62cdf;
        vec_r_addr[57] = 6'h15;
        vec_r_expected[57] = 32'h00000000;

        vec_w_en[58] = 1'h1;
        vec_w_addr[58] = 6'h12;
        vec_w_data[58] = 32'h2704b233;
        vec_r_addr[58] = 6'h15;
        vec_r_expected[58] = 32'h00000000;

        vec_w_en[59] = 1'h1;
        vec_w_addr[59] = 6'h0a;
        vec_w_data[59] = 32'hd00f337f;
        vec_r_addr[59] = 6'h23;
        vec_r_expected[59] = 32'h232d9272;

        vec_w_en[60] = 1'h0;
        vec_w_addr[60] = 6'h04;
        vec_w_data[60] = 32'h4df39ff6;
        vec_r_addr[60] = 6'h04;
        vec_r_expected[60] = 32'h00000000;

        vec_w_en[61] = 1'h1;
        vec_w_addr[61] = 6'h0e;
        vec_w_data[61] = 32'ha0eb1b67;
        vec_r_addr[61] = 6'h1c;
        vec_r_expected[61] = 32'h00000000;

        vec_w_en[62] = 1'h0;
        vec_w_addr[62] = 6'h30;
        vec_w_data[62] = 32'h2731413f;
        vec_r_addr[62] = 6'h31;
        vec_r_expected[62] = 32'h00000000;

        vec_w_en[63] = 1'h1;
        vec_w_addr[63] = 6'h05;
        vec_w_data[63] = 32'h307a8b12;
        vec_r_addr[63] = 6'h1e;
        vec_r_expected[63] = 32'h00000000;

        vec_w_en[64] = 1'h1;
        vec_w_addr[64] = 6'h0b;
        vec_w_data[64] = 32'h78d7ac59;
        vec_r_addr[64] = 6'h03;
        vec_r_expected[64] = 32'h84fc2b6e;

        vec_w_en[65] = 1'h1;
        vec_w_addr[65] = 6'h02;
        vec_w_data[65] = 32'h6fc4571b;
        vec_r_addr[65] = 6'h3c;
        vec_r_expected[65] = 32'h00000000;

        vec_w_en[66] = 1'h1;
        vec_w_addr[66] = 6'h18;
        vec_w_data[66] = 32'h8a013b6d;
        vec_r_addr[66] = 6'h03;
        vec_r_expected[66] = 32'h84fc2b6e;

        vec_w_en[67] = 1'h1;
        vec_w_addr[67] = 6'h23;
        vec_w_data[67] = 32'h5cc742db;
        vec_r_addr[67] = 6'h17;
        vec_r_expected[67] = 32'hc43a6c7b;

        vec_w_en[68] = 1'h0;
        vec_w_addr[68] = 6'h21;
        vec_w_data[68] = 32'hbff2de82;
        vec_r_addr[68] = 6'h02;
        vec_r_expected[68] = 32'h6fc4571b;

        vec_w_en[69] = 1'h0;
        vec_w_addr[69] = 6'h3d;
        vec_w_data[69] = 32'ha3e43276;
        vec_r_addr[69] = 6'h30;
        vec_r_expected[69] = 32'h26e62cdf;

        vec_w_en[70] = 1'h1;
        vec_w_addr[70] = 6'h00;
        vec_w_data[70] = 32'h09a3291a;
        vec_r_addr[70] = 6'h30;
        vec_r_expected[70] = 32'h26e62cdf;

        vec_w_en[71] = 1'h0;
        vec_w_addr[71] = 6'h08;
        vec_w_data[71] = 32'ha25e6d85;
        vec_r_addr[71] = 6'h21;
        vec_r_expected[71] = 32'h00000000;

        vec_w_en[72] = 1'h1;
        vec_w_addr[72] = 6'h38;
        vec_w_data[72] = 32'hbeb69ac0;
        vec_r_addr[72] = 6'h02;
        vec_r_expected[72] = 32'h6fc4571b;

        vec_w_en[73] = 1'h1;
        vec_w_addr[73] = 6'h11;
        vec_w_data[73] = 32'h2e3e9635;
        vec_r_addr[73] = 6'h0f;
        vec_r_expected[73] = 32'hd2c43bdd;

        vec_w_en[74] = 1'h1;
        vec_w_addr[74] = 6'h11;
        vec_w_data[74] = 32'h41bf8390;
        vec_r_addr[74] = 6'h16;
        vec_r_expected[74] = 32'h348c966c;

        vec_w_en[75] = 1'h1;
        vec_w_addr[75] = 6'h05;
        vec_w_data[75] = 32'h26d989b5;
        vec_r_addr[75] = 6'h08;
        vec_r_expected[75] = 32'h00000000;

        vec_w_en[76] = 1'h0;
        vec_w_addr[76] = 6'h3c;
        vec_w_data[76] = 32'heee3b36f;
        vec_r_addr[76] = 6'h06;
        vec_r_expected[76] = 32'h3571f178;

        vec_w_en[77] = 1'h1;
        vec_w_addr[77] = 6'h2a;
        vec_w_data[77] = 32'ha349213a;
        vec_r_addr[77] = 6'h1c;
        vec_r_expected[77] = 32'h00000000;

        vec_w_en[78] = 1'h0;
        vec_w_addr[78] = 6'h22;
        vec_w_data[78] = 32'hf7892898;
        vec_r_addr[78] = 6'h01;
        vec_r_expected[78] = 32'h2c7d4e41;

        vec_w_en[79] = 1'h1;
        vec_w_addr[79] = 6'h0e;
        vec_w_data[79] = 32'h3ab8bc3c;
        vec_r_addr[79] = 6'h16;
        vec_r_expected[79] = 32'h348c966c;

        vec_w_en[80] = 1'h1;
        vec_w_addr[80] = 6'h03;
        vec_w_data[80] = 32'h26683906;
        vec_r_addr[80] = 6'h3a;
        vec_r_expected[80] = 32'h4c3f12a4;

        vec_w_en[81] = 1'h0;
        vec_w_addr[81] = 6'h2e;
        vec_w_data[81] = 32'h0b93c759;
        vec_r_addr[81] = 6'h08;
        vec_r_expected[81] = 32'h00000000;

        vec_w_en[82] = 1'h1;
        vec_w_addr[82] = 6'h09;
        vec_w_data[82] = 32'hc6f2e177;
        vec_r_addr[82] = 6'h3f;
        vec_r_expected[82] = 32'h00000000;

        vec_w_en[83] = 1'h0;
        vec_w_addr[83] = 6'h14;
        vec_w_data[83] = 32'hac18fd08;
        vec_r_addr[83] = 6'h09;
        vec_r_expected[83] = 32'hc6f2e177;

        vec_w_en[84] = 1'h0;
        vec_w_addr[84] = 6'h23;
        vec_w_data[84] = 32'he60803ce;
        vec_r_addr[84] = 6'h00;
        vec_r_expected[84] = 32'h09a3291a;

        vec_w_en[85] = 1'h1;
        vec_w_addr[85] = 6'h01;
        vec_w_data[85] = 32'h48014dd4;
        vec_r_addr[85] = 6'h34;
        vec_r_expected[85] = 32'hc54622cf;

        vec_w_en[86] = 1'h1;
        vec_w_addr[86] = 6'h24;
        vec_w_data[86] = 32'hc4041b9a;
        vec_r_addr[86] = 6'h32;
        vec_r_expected[86] = 32'h00000000;

        vec_w_en[87] = 1'h0;
        vec_w_addr[87] = 6'h2d;
        vec_w_data[87] = 32'h1f7506f7;
        vec_r_addr[87] = 6'h08;
        vec_r_expected[87] = 32'h00000000;

        vec_w_en[88] = 1'h1;
        vec_w_addr[88] = 6'h2b;
        vec_w_data[88] = 32'hcd27edd7;
        vec_r_addr[88] = 6'h24;
        vec_r_expected[88] = 32'hc4041b9a;

        vec_w_en[89] = 1'h0;
        vec_w_addr[89] = 6'h33;
        vec_w_data[89] = 32'h9d3e1d9c;
        vec_r_addr[89] = 6'h2e;
        vec_r_expected[89] = 32'h35364a2a;

        vec_w_en[90] = 1'h1;
        vec_w_addr[90] = 6'h06;
        vec_w_data[90] = 32'h1e3f98a9;
        vec_r_addr[90] = 6'h06;
        vec_r_expected[90] = 32'h1e3f98a9;

        vec_w_en[91] = 1'h1;
        vec_w_addr[91] = 6'h01;
        vec_w_data[91] = 32'he552f9a3;
        vec_r_addr[91] = 6'h00;
        vec_r_expected[91] = 32'h09a3291a;

        vec_w_en[92] = 1'h1;
        vec_w_addr[92] = 6'h3d;
        vec_w_data[92] = 32'h6f8cb4ad;
        vec_r_addr[92] = 6'h14;
        vec_r_expected[92] = 32'h8883955c;

        vec_w_en[93] = 1'h1;
        vec_w_addr[93] = 6'h20;
        vec_w_data[93] = 32'hcf6be22c;
        vec_r_addr[93] = 6'h0f;
        vec_r_expected[93] = 32'hd2c43bdd;

        vec_w_en[94] = 1'h1;
        vec_w_addr[94] = 6'h34;
        vec_w_data[94] = 32'hc4c411b4;
        vec_r_addr[94] = 6'h13;
        vec_r_expected[94] = 32'he9170f78;

        vec_w_en[95] = 1'h0;
        vec_w_addr[95] = 6'h04;
        vec_w_data[95] = 32'hc68ce968;
        vec_r_addr[95] = 6'h00;
        vec_r_expected[95] = 32'h09a3291a;

        repeat (2) @(posedge i_clk);
        i_rst_n = 1'b1;

        for (int n = 0; n < NUM_CASES; n = n + 1) begin
            @(negedge i_clk);
            i_w_en = vec_w_en[n];
            i_w_addr = vec_w_addr[n];
            i_w_data = vec_w_data[n];
            i_r_addr = vec_r_addr[n];
            @(posedge i_clk);
            #1;
            $display("regfile case=%0d r=%h exp=%h", n, o_r_data, vec_r_expected[n]);
            if (o_r_data !== vec_r_expected[n]) begin
                errors = errors + 1;
                $display("regfile mismatch at case %0d", n);
            end
        end

        if (errors == 0) begin
            $display("regfile_tb PASS");
        end else begin
            $display("regfile_tb FAIL errors=%0d", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule
