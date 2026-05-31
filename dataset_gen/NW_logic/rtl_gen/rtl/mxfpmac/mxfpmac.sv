/* verilator lint_off UNUSEDPARAM */
module mxfpmac #(
    parameter int BLOCK_ELEMS = 32,
    parameter int NUM_BLOCKS = 2,
    parameter int ELEM_WIDTH = 8,
    parameter int ELEM_EXP_BITS = 4,
    parameter int ELEM_MANT_BITS = 3,
    parameter int ELEM_BIAS = 7,
    parameter int SCALE_EXP_BITS = 8,
    parameter int SCALE_BIAS = 127,
    parameter int USE_SCALE = 1,
    parameter int ACC_WIDTH = 32,
    parameter int DECODE_WIDTH = 24,
    parameter int DECODE_FRAC_BITS = 8,
    parameter int PRODUCT_WIDTH = 48,
    parameter int TOTAL_ELEMS = 64
) (
    input  logic                                      i_clk,
    input  logic                                      i_rst_n,
    input  logic                                      i_valid,
    input  logic [TOTAL_ELEMS*ELEM_WIDTH-1:0]         i_a,
    input  logic [TOTAL_ELEMS*ELEM_WIDTH-1:0]         i_b,
    input  logic [NUM_BLOCKS*SCALE_EXP_BITS-1:0]      i_scale_a,
    input  logic [NUM_BLOCKS*SCALE_EXP_BITS-1:0]      i_scale_b,
    output logic                                      o_valid,
    output logic signed [ACC_WIDTH-1:0]               o_result
);
/* verilator lint_on UNUSEDPARAM */

    logic signed [ACC_WIDTH-1:0] block_sum [0:NUM_BLOCKS-1];
    logic signed [ACC_WIDTH-1:0] mac_comb;

    function automatic signed [DECODE_WIDTH-1:0] decode_elem(
        input logic [ELEM_WIDTH-1:0] elem,
        input logic [SCALE_EXP_BITS-1:0] scale
    );
        logic sign;
        int exp_field;
        int mant_field;
        int shift_amt;
        logic signed [DECODE_WIDTH-1:0] mag;
        logic signed [DECODE_WIDTH-1:0] shifted;
        begin
            sign = elem[ELEM_WIDTH-1];
            exp_field = int'(elem[ELEM_MANT_BITS +: ELEM_EXP_BITS]);
            mant_field = int'(elem[0 +: ELEM_MANT_BITS]);
            if ((exp_field == 0) && (mant_field == 0)) begin
                decode_elem = '0;
            end else begin
                if (exp_field == 0) begin
                    mag = DECODE_WIDTH'(mant_field);
                    shift_amt = 1 - ELEM_BIAS - ELEM_MANT_BITS + DECODE_FRAC_BITS;
                end else begin
                    mag = DECODE_WIDTH'((1 << ELEM_MANT_BITS) | mant_field);
                    shift_amt = exp_field - ELEM_BIAS - ELEM_MANT_BITS + DECODE_FRAC_BITS;
                end
                if (USE_SCALE != 0) begin
                    shift_amt = shift_amt + int'(scale) - SCALE_BIAS;
                end
                if (shift_amt >= 0) begin
                    shifted = mag <<< shift_amt;
                end else begin
                    shifted = mag >>> (-shift_amt);
                end
                decode_elem = sign ? -shifted : shifted;
            end
        end
    endfunction

    always_comb begin
        for (int block = 0; block < NUM_BLOCKS; block = block + 1) begin
            block_sum[block] = '0;
        end

        for (int block = 0; block < NUM_BLOCKS; block = block + 1) begin
            for (int elem = 0; elem < BLOCK_ELEMS; elem = elem + 1) begin
                automatic int flat = block * BLOCK_ELEMS + elem;
                automatic logic signed [DECODE_WIDTH-1:0] a_dec;
                automatic logic signed [DECODE_WIDTH-1:0] b_dec;
                automatic logic signed [PRODUCT_WIDTH-1:0] product;
                /* verilator lint_off UNUSEDSIGNAL */
                automatic logic signed [PRODUCT_WIDTH-1:0] aligned;
                /* verilator lint_on UNUSEDSIGNAL */
                a_dec = decode_elem(
                    i_a[flat*ELEM_WIDTH +: ELEM_WIDTH],
                    i_scale_a[block*SCALE_EXP_BITS +: SCALE_EXP_BITS]
                );
                b_dec = decode_elem(
                    i_b[flat*ELEM_WIDTH +: ELEM_WIDTH],
                    i_scale_b[block*SCALE_EXP_BITS +: SCALE_EXP_BITS]
                );
                product = a_dec * b_dec;
                aligned = product >>> DECODE_FRAC_BITS;
                block_sum[block] = block_sum[block] + ACC_WIDTH'(aligned);
            end
        end

        mac_comb = '0;
            for (int block = 0; block < NUM_BLOCKS; block = block + 1) begin
                mac_comb = mac_comb + block_sum[block];
            end
    end

    always_ff @(posedge i_clk) begin
        if (!i_rst_n) begin
            o_valid <= 1'b0;
            o_result <= '0;
        end else begin
            o_valid <= i_valid;
            if (i_valid) begin
                o_result <= mac_comb;
            end else begin
                o_result <= '0;
            end
        end
    end

endmodule
