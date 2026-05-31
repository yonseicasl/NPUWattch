module fpadd #(
    parameter int EXPONENT_BITS = 8,
    parameter int MANTISSA_BITS = 23,
    parameter int PIPELINE_STAGES = 2
) (
    input  logic [EXPONENT_BITS+MANTISSA_BITS:0] i_a,
    input  logic [EXPONENT_BITS+MANTISSA_BITS:0] i_b,
    input  logic                                 i_clk,
    input  logic                                 i_rst_n,
    output logic [EXPONENT_BITS+MANTISSA_BITS:0] o_sum,
    output logic                                 o_ovfl,
    output logic                                 o_udfl
);

    function automatic int clogb2(input int bit_depth);
        int value;
        begin
            value = bit_depth - 1;
            for (clogb2 = 0; value > 0; clogb2 = clogb2 + 1) begin
                value = value >> 1;
            end
        end
    endfunction

    localparam int FP_MSB = EXPONENT_BITS + MANTISSA_BITS;
    localparam int SHIFT_COUNTER_BITS = clogb2(MANTISSA_BITS + 5);
    localparam int EXTRA_STAGES = PIPELINE_STAGES - 2;

    logic [FP_MSB:0] a_r;
    logic [FP_MSB:0] b_r;

    logic [FP_MSB:0] sum_c;
    logic overflow_c;
    logic underflow_c;

    logic [FP_MSB:0] sum_pipe   [0:EXTRA_STAGES];
    logic            ovfl_pipe  [0:EXTRA_STAGES];
    logic            udfl_pipe  [0:EXTRA_STAGES];

    integer idx;

    always_ff @(posedge i_clk) begin
        if (!i_rst_n) begin
            a_r <= '0;
            b_r <= '0;
        end else begin
            a_r <= i_a;
            b_r <= i_b;
        end
    end

    wire zero_a;
    wire zero_b;
    wire inf_a;
    wire inf_b;
    wire nan_a;
    wire nan_b;
    wire abs_a_eq_abs_b;
    wire sign_a;
    wire sign_b;
    wire sign_sum;
    wire is_sum;
    wire [EXPONENT_BITS-1:0] exp_a;
    wire [EXPONENT_BITS-1:0] exp_b;
    wire [EXPONENT_BITS-1:0] exp_large;
    wire [EXPONENT_BITS-1:0] exp_pre_rounding;
    wire [MANTISSA_BITS-1:0] frac_a;
    wire [MANTISSA_BITS-1:0] frac_b;
    wire [MANTISSA_BITS:0] frac_large;
    wire [MANTISSA_BITS:0] frac_small;
    wire [MANTISSA_BITS+3:0] frac_shifted;
    wire [MANTISSA_BITS+4:0] frac_result;
    wire [EXPONENT_BITS:0] exp_diff;
    wire carry_out;
    wire abs_a_gt_abs_b;
    wire [MANTISSA_BITS-1:0] frac_sum_adj;
    wire [SHIFT_COUNTER_BITS-1:0] frac_sum_shift_n;
    wire [SHIFT_COUNTER_BITS-1:0] actual_shift;

    assign sign_a = a_r[FP_MSB];
    assign sign_b = b_r[FP_MSB];
    assign exp_a = a_r[FP_MSB-1:MANTISSA_BITS];
    assign exp_b = b_r[FP_MSB-1:MANTISSA_BITS];
    assign frac_a = a_r[MANTISSA_BITS-1:0];
    assign frac_b = b_r[MANTISSA_BITS-1:0];

    wire exp_a_all_ones = &exp_a;
    wire exp_b_all_ones = &exp_b;
    wire frac_a_not_zero = |frac_a;
    wire frac_b_not_zero = |frac_b;
    wire exp_a_is_zero = ~|exp_a;
    wire exp_b_is_zero = ~|exp_b;

    // Subnormals (exp field 0) have an effective unbiased exponent of (1 - bias),
    // i.e. they align as if the exponent field were 1 while keeping a 0 hidden bit.
    wire [EXPONENT_BITS-1:0] exp_a_eff = exp_a_is_zero ? { {(EXPONENT_BITS-1){1'b0}}, 1'b1} : exp_a;
    wire [EXPONENT_BITS-1:0] exp_b_eff = exp_b_is_zero ? { {(EXPONENT_BITS-1){1'b0}}, 1'b1} : exp_b;

    assign inf_a = exp_a_all_ones && !frac_a_not_zero;
    assign inf_b = exp_b_all_ones && !frac_b_not_zero;
    assign nan_a = exp_a_all_ones && frac_a_not_zero;
    assign nan_b = exp_b_all_ones && frac_b_not_zero;
    assign zero_a = exp_a_is_zero && !frac_a_not_zero;
    assign zero_b = exp_b_is_zero && !frac_b_not_zero;

    assign exp_diff = (exp_a_eff > exp_b_eff) ? (exp_a_eff - exp_b_eff) : (exp_b_eff - exp_a_eff);
    assign abs_a_gt_abs_b = a_r[FP_MSB-1:0] > b_r[FP_MSB-1:0];
    assign abs_a_eq_abs_b = !abs_a_gt_abs_b && (a_r[FP_MSB-1:0] == b_r[FP_MSB-1:0]);

    assign exp_large = abs_a_gt_abs_b ? exp_a_eff : exp_b_eff;
    assign frac_large = abs_a_gt_abs_b ? {!exp_a_is_zero, frac_a} : {!exp_b_is_zero, frac_b};
    assign frac_small = abs_a_gt_abs_b ? {!exp_b_is_zero, frac_b} : {!exp_a_is_zero, frac_a};

    /* verilator lint_off WIDTHEXPAND */
    /* verilator lint_off WIDTHTRUNC */
    // Align the smaller operand by a single right shift, preserving every bit that
    // falls below the three guard/round/sticky positions as a sticky OR. Rounding is
    // then applied exactly once on the post-add result; pre-rounding the shifted
    // operand here would cause a double-rounding error.
    wire [MANTISSA_BITS+3:0] frac_small_ext  = {frac_small, 3'b000};
    wire [MANTISSA_BITS+3:0] frac_small_sh   = frac_small_ext >> exp_diff;
    wire [MANTISSA_BITS+3:0] frac_lost_mask  = ~({(MANTISSA_BITS+4){1'b1}} << exp_diff);
    wire frac_sticky_lost = |(frac_small_ext & frac_lost_mask);
    assign frac_shifted = {frac_small_sh[MANTISSA_BITS+3:1], frac_small_sh[0] | frac_sticky_lost};
    assign is_sum = (sign_a == sign_b);
    assign frac_result = is_sum
        ? ({1'b0, frac_large, 3'b0} + {1'b0, frac_shifted})
        : ({1'b0, frac_large, 3'b0} - {1'b0, frac_shifted});

    assign carry_out = frac_result[MANTISSA_BITS+4];

    logic [SHIFT_COUNTER_BITS-1:0] frac_sum_shift_gen [0:MANTISSA_BITS+3];
    always_comb begin
        frac_sum_shift_gen[MANTISSA_BITS+3] = frac_result[1] ? MANTISSA_BITS + 3 : MANTISSA_BITS + 4;
        for (int j = MANTISSA_BITS + 3; j > 0; j = j - 1) begin
            frac_sum_shift_gen[j-1] = frac_result[MANTISSA_BITS + 5 - j] ? j - 1 : frac_sum_shift_gen[j];
        end
    end

    wire [EXPONENT_BITS-1:0] exp_large_plus_one = exp_large + 1'b1;
    assign frac_sum_shift_n = is_sum ? (carry_out ? '0 : 1) : frac_sum_shift_gen[0];

    // The subtract path produces a subnormal result when the normalized exponent
    // (exp_large_plus_one - frac_sum_shift_n) would drop to zero or below. A
    // subnormal carries no hidden one, so the significand is left denormalized by
    // shifting one position short of full normalization while the exponent field
    // is forced to zero.
    wire sub_is_normal = exp_large_plus_one > frac_sum_shift_n;
    assign actual_shift = is_sum
        ? frac_sum_shift_n
        : (sub_is_normal ? frac_sum_shift_n : (exp_large_plus_one - 1'b1));

    wire exp_sum_pre_rounding_is_zero = is_sum
        ? (exp_a_is_zero && exp_b_is_zero && !carry_out && !frac_result[MANTISSA_BITS+3])
        : !sub_is_normal;
    assign exp_pre_rounding = exp_sum_pre_rounding_is_zero ? '0 : (exp_large_plus_one - frac_sum_shift_n);

    /* verilator lint_off UNUSEDSIGNAL */
    wire [MANTISSA_BITS+4:0] frac_sum_shifted = frac_result << actual_shift;
    /* verilator lint_on UNUSEDSIGNAL */
    assign frac_sum_adj = frac_sum_shifted[MANTISSA_BITS+3:4];

    wire guard = (actual_shift > 3) ? 1'b0 : frac_result[3-actual_shift];
    wire round_bit = (actual_shift > 2) ? 1'b0 : frac_result[2-actual_shift];
    wire sticky = (actual_shift > 1) ? 1'b0
        : (actual_shift[0] ? frac_result[0] : (frac_result[1] || frac_result[0]));
    wire round_up = guard && (round_bit || sticky || frac_sum_adj[0]);
    wire [FP_MSB-1:0] rounded_sum = {exp_pre_rounding, frac_sum_adj} + round_up;
    /* verilator lint_on WIDTHTRUNC */
    /* verilator lint_on WIDTHEXPAND */

    assign sign_sum = (is_sum || abs_a_gt_abs_b || abs_a_eq_abs_b) ? sign_a : sign_b;

    always_comb begin
        sum_c = '0;
        if (zero_a && zero_b) begin
            // Under round-to-nearest the sum of two zeros is +0 unless both are -0.
            sum_c = {sign_a & sign_b, {(FP_MSB){1'b0}}};
        end else if (zero_a) begin
            sum_c = b_r;
        end else if (zero_b) begin
            sum_c = a_r;
        end else if (nan_a || nan_b) begin
            sum_c = {sign_sum, {a_r[FP_MSB-1:0] | b_r[FP_MSB-1:0]}};
        end else if (inf_a) begin
            sum_c = inf_b ? (is_sum ? a_r : {sign_sum, {EXPONENT_BITS{1'b1}}, 1'b1, {(MANTISSA_BITS-1){1'b0}}}) : a_r;
        end else if (inf_b) begin
            sum_c = b_r;
        end else if (!is_sum && (frac_result == '0)) begin
            sum_c = '0;
        end else if (&rounded_sum[FP_MSB-1:MANTISSA_BITS]) begin
            sum_c = {sign_sum, {EXPONENT_BITS{1'b1}}, {MANTISSA_BITS{1'b0}}};
        end else begin
            sum_c = {sign_sum, rounded_sum};
        end
    end

    assign overflow_c = &sum_c[FP_MSB-1:MANTISSA_BITS];
    assign underflow_c = ~|sum_c[FP_MSB-1:MANTISSA_BITS];

    always_ff @(posedge i_clk) begin
        if (!i_rst_n) begin
            for (idx = 0; idx <= EXTRA_STAGES; idx = idx + 1) begin
                sum_pipe[idx] <= '0;
                ovfl_pipe[idx] <= 1'b0;
                udfl_pipe[idx] <= 1'b0;
            end
        end else begin
            sum_pipe[0] <= sum_c;
            ovfl_pipe[0] <= overflow_c;
            udfl_pipe[0] <= underflow_c;
            for (idx = 1; idx <= EXTRA_STAGES; idx = idx + 1) begin
                sum_pipe[idx] <= sum_pipe[idx-1];
                ovfl_pipe[idx] <= ovfl_pipe[idx-1];
                udfl_pipe[idx] <= udfl_pipe[idx-1];
            end
        end
    end

    assign o_sum = sum_pipe[EXTRA_STAGES];
    assign o_ovfl = ovfl_pipe[EXTRA_STAGES];
    assign o_udfl = udfl_pipe[EXTRA_STAGES];

endmodule
