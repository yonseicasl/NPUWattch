module fpadder #(parameter integer EXPONENT_BITS = 8, parameter integer MANTISSA_BITS = 23) (
        input wire [EXPONENT_BITS+MANTISSA_BITS:0] i_A,  // 64-bit floating-point input a
        input wire [EXPONENT_BITS+MANTISSA_BITS:0] i_B,  // 64-bit floating-point input b

        input wire i_CLK,
        output reg [EXPONENT_BITS+MANTISSA_BITS:0] o_SUM,
        output reg o_OVFL, o_UDFL
    );

    reg [EXPONENT_BITS+MANTISSA_BITS:0] a, b;
    always @(posedge i_CLK) a <= i_A;
    always @(posedge i_CLK) b <= i_B;
    
    wire [EXPONENT_BITS+MANTISSA_BITS:0] sum;

    // function called clogb2 that returns an integer which has the
    // value of the ceiling of the log base 2.
    function integer clogb2 (input integer bit_depth);
        begin
            for(clogb2=0; bit_depth>0; clogb2=clogb2+1)
                bit_depth = bit_depth >> 1;
        end
    endfunction

    localparam integer FP_MSB = EXPONENT_BITS + MANTISSA_BITS;
    localparam integer SHIFT_COUNTER_BITS = clogb2(MANTISSA_BITS+4);

    // Internal signals
    // special cases
    wire zero_a, zero_b, inf_a, inf_b, nan_a, nan_b, abs_a_eq_abs_b;
    wire sign_a, sign_b, sign_sum, is_sum;
    wire [EXPONENT_BITS-1 : 0] exp_a, exp_b, exp_sum, exp_large, exp_small, exp_pre_rounding;
    wire [MANTISSA_BITS-1 : 0] frac_a, frac_b;
    wire [MANTISSA_BITS : 0] frac_large;
    wire [MANTISSA_BITS+3 : 0] frac_shifted;
    wire [MANTISSA_BITS+4 : 0] frac_result;
    wire [EXPONENT_BITS : 0] exp_diff;
    wire carry_out, abs_a_gt_abs_b;
    wire [MANTISSA_BITS-1 : 0] frac_sum_adj;
    wire [SHIFT_COUNTER_BITS-1 : 0] frac_sum_shift_n, actual_shift;

    // Assign sign, exponent and fraction
    assign sign_a = a[FP_MSB];
    assign sign_b = b[FP_MSB];
    assign exp_a = a[FP_MSB-1 : MANTISSA_BITS];
    assign exp_b = b[FP_MSB-1 : MANTISSA_BITS];
    assign frac_a = a[MANTISSA_BITS-1 : 0];
    assign frac_b = b[MANTISSA_BITS-1 : 0];

    // Check if a or b is infinity or nan
    wire exp_a_all_ones;
    assign exp_a_all_ones = &(exp_a);
    wire frac_a_not_zero;
    assign frac_a_not_zero = |(frac_a);
    assign inf_a = exp_a_all_ones && !frac_a_not_zero;
    assign nan_a = exp_a_all_ones && frac_a_not_zero;

    wire exp_b_all_ones;
    assign exp_b_all_ones = &(exp_b);
    wire frac_b_not_zero;
    assign frac_b_not_zero = |(frac_b);
    assign inf_b = exp_b_all_ones && !frac_b_not_zero;
    assign nan_b = exp_b_all_ones && frac_b_not_zero;

    // Check if any exponents are zeros
    wire exp_a_is_zero;
    assign exp_a_is_zero = !(|(exp_a));
    wire exp_b_is_zero;
    assign exp_b_is_zero = !(|(exp_b));

    // Check if a or b is zero
    assign zero_a = exp_a_is_zero && !frac_a_not_zero;
    assign zero_b = exp_b_is_zero && !frac_b_not_zero;

    // Calculate exponent difference
    assign exp_diff = (exp_a > exp_b) ? (exp_a - exp_b) : (exp_b - exp_a);

    // Determine which number is larger
    assign abs_a_gt_abs_b = a[FP_MSB-1 : 0] > b[FP_MSB-1 : 0];
    assign abs_a_eq_abs_b = abs_a_gt_abs_b ? 0 : (a[FP_MSB-1 : 0] == b[FP_MSB-1 : 0]);

    // Ensure frac_large has the larger exponent
    assign exp_large = abs_a_gt_abs_b ? exp_a : exp_b;
    assign exp_small = abs_a_gt_abs_b ? exp_b : exp_a;
    // leading bit of frac is restored
    assign frac_large = abs_a_gt_abs_b ? {!exp_a_is_zero, frac_a} : {!exp_b_is_zero, frac_b};
    wire [MANTISSA_BITS : 0] frac_small;
    assign frac_small = abs_a_gt_abs_b ? {!exp_b_is_zero, frac_b} : {!exp_a_is_zero, frac_a};

    wire sh_frac_odd, sh_frac_guard, sh_frac_round, sh_frac_sticky;
    assign sh_frac_odd = (exp_diff > 2 && exp_diff < MANTISSA_BITS+4) ? frac_small[exp_diff-3] : 1'b0;
    assign sh_frac_guard = (exp_diff > 3 && exp_diff < MANTISSA_BITS+5) ? frac_small[exp_diff-4] : 1'b0;
    assign sh_frac_round = (exp_diff > 4 && exp_diff < MANTISSA_BITS+6) ? frac_small[exp_diff-5] : 1'b0;
    assign sh_frac_sticky = (exp_diff > 5 && exp_diff < MANTISSA_BITS+7) ? frac_small[exp_diff-6] : 1'b0;
    wire sh_frac_round_up;
    assign sh_frac_round_up = (sh_frac_guard && (sh_frac_round || sh_frac_sticky || sh_frac_odd));

    // Shift the smaller fraction right by the exponent difference
    assign frac_shifted = ({frac_small, 3'b000} >> exp_diff) + sh_frac_round_up;

    // Add or subtract the fractions based on the sign
    assign is_sum = (sign_a == sign_b);
    assign frac_result = { is_sum ?
                           {1'b0, frac_large, 3'b0} + {1'b0, frac_shifted} :
                           {1'b0, frac_large, 3'b0} - {1'b0, frac_shifted}};
    // no zero-crossing in this process.

    // Normalize the result if necessary
    assign carry_out = frac_result[MANTISSA_BITS+4];

    // waterfall to determine how many bits to shift
    wire [SHIFT_COUNTER_BITS-1 : 0] frac_sum_shift_gen [MANTISSA_BITS+3 : 0];
    assign frac_sum_shift_gen[MANTISSA_BITS+3] = frac_result[1] ? MANTISSA_BITS+3 : MANTISSA_BITS+4;
    genvar i;
    generate
        for (i = MANTISSA_BITS+3; i > 0; i=i-1)
        begin
            assign frac_sum_shift_gen[i-1] = frac_result[MANTISSA_BITS+5-i] ? i-1 : frac_sum_shift_gen[i];
        end
    endgenerate

    wire [EXPONENT_BITS-1 : 0] exp_large_plus_one;
    // we have ruled out nan (exp all ones), so no wrap-around will occur here
    assign exp_large_plus_one = exp_large + 1;

    assign frac_sum_shift_n = is_sum ? (carry_out ? 0 : 1) : frac_sum_shift_gen[0]; // number of bits to shift to normalize
    // if sum and we got a denormalized result, the only possibility is that both numbers are denormalized
    // therefore, it is still covered by the condition below.
    assign actual_shift = (exp_large_plus_one >= frac_sum_shift_n) ? frac_sum_shift_n : exp_large_plus_one;

    //assign actual_shift = (exp_large_plus_one >= frac_sum_shift_gen[0]) ? frac_sum_shift_gen[0] : exp_large_plus_one;

    wire exp_sum_pre_rounding_is_zero;
    assign exp_sum_pre_rounding_is_zero = is_sum ?
        (exp_a_is_zero && exp_b_is_zero && !carry_out && !frac_result[MANTISSA_BITS+3]) :
        !(exp_large_plus_one >= frac_sum_shift_n);
    assign exp_pre_rounding = exp_sum_pre_rounding_is_zero? 0 : (exp_large_plus_one - frac_sum_shift_n);

    //assign exp_pre_rounding = exp_large_plus_one - actual_shift;

    wire [MANTISSA_BITS+4 : 0] frac_sum_shifted;
    assign frac_sum_shifted = frac_result << actual_shift;
    assign frac_sum_adj = frac_sum_shifted[MANTISSA_BITS+3:4];

    // Extract the guard, round, and sticky bits for rounding
    wire guard, round, sticky;
    assign guard = (actual_shift > 3) ? 1'b0 : frac_result[3-actual_shift];
    assign round = (actual_shift > 2) ? 1'b0 : frac_result[2-actual_shift];
    assign sticky = (actual_shift > 1) ? 1'b0 :             // >1
                    actual_shift[0] ? frac_result[0] :      // 1
                    (frac_result[1] || frac_result[0]);     // 0            // maybe with "|| frac_result[0]"

    // Apply round-to-nearest-even
    wire round_up;
    assign round_up = (guard && (round || sticky || frac_sum_adj[0]));

    wire [FP_MSB-1 : 0] rounded_sum;
    assign rounded_sum = {exp_pre_rounding, frac_sum_adj} + round_up;

    // Determine the sign of the result
    assign sign_sum = (is_sum || abs_a_gt_abs_b) ? sign_a : sign_b;

    // Final result and special case handling
    assign sum = zero_a ? b :   // zeros
                zero_b ? a :    // zeros
                (nan_a || nan_b) ? { sign_sum, {a[FP_MSB-1:0] | b[FP_MSB-1:0]} } :  // nans
                inf_a ? (inf_b ? (is_sum ? a : { sign_sum, {(EXPONENT_BITS){1'b1}}, 1'b1, {(MANTISSA_BITS-1){1'b0}} }) : a) :   // infs
                inf_b ? b :     // infs
                &(rounded_sum[FP_MSB-1 : MANTISSA_BITS]) ? { sign_sum, {(EXPONENT_BITS){1'b1}}, {(MANTISSA_BITS){1'b0}} } : // normal add leads to signed inf
                {sign_sum, rounded_sum};    // normal add

    // Overflow and underflow detection
    wire overflow = &(sum[FP_MSB-1 : MANTISSA_BITS]);
    wire underflow = !(|(sum[FP_MSB-1 : MANTISSA_BITS]));


always @(posedge i_CLK) begin
    o_SUM <= sum;
    o_OVFL <= overflow;
    o_UDFL <= underflow;
end

endmodule