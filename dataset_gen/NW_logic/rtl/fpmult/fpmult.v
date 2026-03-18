// ============================================================================
//  fpmult_new.v — Pipelined Floating-Point Multiplier (2 GHz / 16 nm target)
// ============================================================================
//
//  Architectural improvements over the previous design:
//
//  1. Carry-Save Accumulator Multiplier (pipelined_mul_cs)
//     ────────────────────────────────────────────────────
//     OLD: each intermediate stage performed  chunk×B  +  CPA(accumulator)
//          CPA width = PROD_W → O(log PROD_W) delay per stage → UNBALANCED
//     NEW: each intermediate stage performs   chunk×B  +  CSA(accumulator)
//          CSA depth = 1 full-adder delay → every stage is balanced to
//              (small_multiply  +  1 FA)
//          The single CPA occurs only in the final combinational zone.
//
//     Zone 0  :  pp₀ = A_chunk[0] × B                          → reg (CS)
//     Zone k  :  CSA( CS_S, CS_C, A_chunk[k]×B << k·CW )       → reg (CS)
//     Zone N  :  product = CS_S + CS_C + A_chunk[N]×B << N·CW    (CPA, comb)
//
//     Delay per intermediate zone:  ~T_small_mul + T_FA   (uniform)
//     Delay of final zone:          ~T_small_mul + T_FA + T_CPA
//
//  2. Tree-Based Leading-Zero Counter (clz_tree)
//     ──────────────────────────────────────────
//     OLD: cascaded O(2·MANTISSA_BITS) mux waterfall  ≈ 225 mux levels
//          at 15 ps/mux → 3.4 ns (far beyond 500 ps budget)
//     NEW: divide-and-conquer tree  →  O(log₂ N) mux levels
//          for 226 bits: ~8 levels at 30 ps → 240 ps
//
//  Pipeline budget (PIPELINE_STAGE = S, range 2..7):
//     Stage 0            :  Input register
//     Stages 1 .. S-2    :  pipelined_mul_cs internal registers  (S-2 stages)
//     Stage S-1          :  Output register (absorbs post-multiply logic)
//     Total latency      =  S clock cycles
//
// ============================================================================


// ============================================================================
//  Module: clz_tree — Tree-based Leading-Zero Counter
// ============================================================================
//  Computes the number of leading zeros from the MSB of a W-bit vector.
//  Depth: O(log₂ W) levels of muxes.
//  Fully combinational, no flip-flops.
// ============================================================================
module clz_tree #(
    parameter integer W = 8
) (
    input  wire [W-1:0]                     i_DATA,
    output wire [$clog2(W+1)-1:0]           o_CLZ,   // 0 .. W
    output wire                             o_ZERO   // 1 if all bits are zero
);
    generate
        if (W == 1) begin : base1
            assign o_CLZ  = ~i_DATA[0];
            assign o_ZERO = ~i_DATA[0];
        end
        else if (W == 2) begin : base2
            assign o_CLZ  = i_DATA[1] ? 2'd0 : (i_DATA[0] ? 2'd1 : 2'd2);
            assign o_ZERO = ~|i_DATA;
        end
        else begin : recurse
            localparam integer HI_W = (W + 1) / 2;   // upper-half width (ceil)
            localparam integer LO_W = W - HI_W;       // lower-half width
            localparam integer CLZ_BITS = $clog2(W + 1);

            wire [$clog2(HI_W+1)-1:0] hi_clz;
            wire                       hi_zero;
            wire [$clog2(LO_W+1)-1:0] lo_clz;
            wire                       lo_zero;

            clz_tree #(.W(HI_W)) u_hi (
                .i_DATA (i_DATA[W-1 -: HI_W]),
                .o_CLZ  (hi_clz),
                .o_ZERO (hi_zero)
            );
            clz_tree #(.W(LO_W)) u_lo (
                .i_DATA (i_DATA[LO_W-1:0]),
                .o_CLZ  (lo_clz),
                .o_ZERO (lo_zero)
            );

            assign o_ZERO = hi_zero & lo_zero;
            assign o_CLZ  = hi_zero ? (HI_W[CLZ_BITS-1:0] + {{(CLZ_BITS-$clog2(LO_W+1)){1'b0}}, lo_clz})
                                    : {{(CLZ_BITS - $clog2(HI_W+1)){1'b0}}, hi_clz};
        end
    endgenerate
endmodule


// ============================================================================
//  Module: pipelined_mul_cs — Carry-Save Accumulator Multiplier
// ============================================================================
//  Performs WIDTH_A × WIDTH_B unsigned multiplication.
//
//  STAGES = 0 : purely combinational.
//  STAGES >= 1 : operand A is split into (STAGES+1) equal chunks.
//               Each pipeline stage computes one chunk×B partial product
//               and merges it with the running total using a 3:2 CSA
//               (one full-adder depth — NOT a CPA).
//               Only the final combinational zone performs a CPA.
//
//  Delay per registered zone : T(chunk_W × WIDTH_B multiply) + T(FA)
//  Delay of final comb. zone : T(chunk_W × WIDTH_B multiply) + T(FA) + T(CPA)
//
//  All registered zones have near-identical delay, satisfying the
//  "uniformly distributed" requirement.
// ============================================================================
module pipelined_mul_cs #(
    parameter integer WIDTH_A = 113,
    parameter integer WIDTH_B = 113,
    parameter integer STAGES  = 0
) (
    input  wire                           i_CLK,
    input  wire [WIDTH_A-1:0]             i_A,
    input  wire [WIDTH_B-1:0]             i_B,
    output wire [WIDTH_A+WIDTH_B-1:0]     o_PRODUCT
);
    localparam integer PROD_W = WIDTH_A + WIDTH_B;

    generate
    // ------------------------------------------------------------------
    // Fully combinational (STAGES == 0)
    // ------------------------------------------------------------------
    if (STAGES == 0) begin : gen_comb
        assign o_PRODUCT = i_A * i_B;
    end
    // ------------------------------------------------------------------
    // Carry-save pipelined (STAGES >= 1)
    // ------------------------------------------------------------------
    else begin : gen_pipe
        localparam integer NUM_CHUNKS = STAGES + 1;
        localparam integer CHUNK_W    = (WIDTH_A + NUM_CHUNKS - 1) / NUM_CHUNKS;

        // Pipeline registers : carry-save accumulator + forwarded operands
        reg  [PROD_W-1:0]   cs_s [0:STAGES-1];   // carry-save sum
        reg  [PROD_W-1:0]   cs_c [0:STAGES-1];   // carry-save carry (pre-shifted)
        reg  [WIDTH_A-1:0]  a_r  [0:STAGES-1];
        reg  [WIDTH_B-1:0]  b_r  [0:STAGES-1];

        // ==============================================================
        // Zone 0 : first chunk multiply — no CSA merge needed
        // ==============================================================
        wire [CHUNK_W-1:0]         chunk0 = i_A[CHUNK_W-1:0];
        wire [CHUNK_W+WIDTH_B-1:0] pp0    = chunk0 * i_B;

        always @(posedge i_CLK) begin
            cs_s[0] <= {{(PROD_W - CHUNK_W - WIDTH_B){1'b0}}, pp0};
            cs_c[0] <= {PROD_W{1'b0}};
            a_r[0]  <= i_A;
            b_r[0]  <= i_B;
        end

        // ==============================================================
        // Zones 1 .. STAGES-1 : chunk multiply + CSA accumulation
        // ==============================================================
        genvar s;
        for (s = 1; s < STAGES; s = s + 1) begin : zone
            wire [WIDTH_A-1:0]         a_cur = a_r[s-1];
            wire [WIDTH_B-1:0]         b_cur = b_r[s-1];

            // Extract chunk s from the forwarded A
            wire [CHUNK_W-1:0]         chunk_s     = a_cur >> (s * CHUNK_W);
            wire [CHUNK_W+WIDTH_B-1:0] pp_s        = chunk_s * b_cur;
            wire [PROD_W-1:0]          pp_aligned  =
                {{(PROD_W - CHUNK_W - WIDTH_B){1'b0}}, pp_s} << (s * CHUNK_W);

            // 3:2 Carry-Save Adder  (1 full-adder depth)
            //   value_in  = cs_s + cs_c + pp_aligned
            //   value_out = csa_sum + csa_carry   (carry pre-shifted by 1)
            wire [PROD_W-1:0] x = cs_s[s-1];
            wire [PROD_W-1:0] y = cs_c[s-1];
            wire [PROD_W-1:0] z = pp_aligned;

            wire [PROD_W-1:0] csa_sum   = x ^ y ^ z;
            wire [PROD_W-1:0] carry_raw = (x & y) | (y & z) | (x & z);
            wire [PROD_W-1:0] csa_carry = {carry_raw[PROD_W-2:0], 1'b0};

            always @(posedge i_CLK) begin
                cs_s[s] <= csa_sum;
                cs_c[s] <= csa_carry;
                a_r[s]  <= a_cur;
                b_r[s]  <= b_cur;
            end
        end

        // ==============================================================
        // Zone STAGES : final chunk + CSA + CPA (combinational output)
        // ==============================================================
        wire [WIDTH_A-1:0]         a_last     = a_r[STAGES-1];
        wire [WIDTH_B-1:0]         b_last     = b_r[STAGES-1];
        wire [CHUNK_W-1:0]         chunk_last = a_last >> (STAGES * CHUNK_W);
        wire [CHUNK_W+WIDTH_B-1:0] pp_last    = chunk_last * b_last;
        wire [PROD_W-1:0]          pp_last_al =
            {{(PROD_W - CHUNK_W - WIDTH_B){1'b0}}, pp_last} << (STAGES * CHUNK_W);

        // Final 3:2 CSA then 2-input CPA (synthesis converts to prefix adder)
        wire [PROD_W-1:0] fx = cs_s[STAGES-1];
        wire [PROD_W-1:0] fy = cs_c[STAGES-1];
        wire [PROD_W-1:0] fz = pp_last_al;

        wire [PROD_W-1:0] f_sum       = fx ^ fy ^ fz;
        wire [PROD_W-1:0] f_carry_raw = (fx & fy) | (fy & fz) | (fx & fz);
        wire [PROD_W-1:0] f_carry     = {f_carry_raw[PROD_W-2:0], 1'b0};

        assign o_PRODUCT = f_sum + f_carry;
    end
    endgenerate

endmodule


// ============================================================================
//  Module: fpmult_new — Top-Level Pipelined Floating-Point Multiplier
// ============================================================================
//
//  PIPELINE_STAGE  |  MUL_STAGES  |  Description
//  ----------------+--------------+------------------------------------------
//       2          |      0       |  input-reg -> comb -> output-reg
//       3          |      1       |  +1 carry-save stage in multiplier
//       4          |      2       |  +2 carry-save stages
//       5          |      3       |  +3 carry-save stages
//       6          |      4       |  +4 carry-save stages
//       7          |      5       |  +5 carry-save stages
//
//  Latency = PIPELINE_STAGE clock cycles.
//  Throughput = 1 result per clock after pipeline fill.
//
// ============================================================================
module fpmult #(
    parameter integer EXPONENT_BITS  = 8,
    parameter integer MANTISSA_BITS  = 23,
    parameter integer PIPELINE_STAGE = 5          // 2 .. 7
) (
    input  wire [EXPONENT_BITS+MANTISSA_BITS:0]  i_A,
    input  wire [EXPONENT_BITS+MANTISSA_BITS:0]  i_B,
    input  wire                                   i_CLK,
    output reg  [EXPONENT_BITS+MANTISSA_BITS:0]   o_PRODUCT,
    output reg                                    o_OVFL,
    output reg                                    o_UDFL
);

    // ----------------------------------------------------------------
    // Local parameters
    // ----------------------------------------------------------------
    localparam integer FP_MSB      = EXPONENT_BITS + MANTISSA_BITS;
    localparam integer FRAC_W      = MANTISSA_BITS + 1;          // with implicit bit
    localparam integer FRAC_PROD_W = 2 * FRAC_W;                // full product width
    localparam integer MUL_STAGES  = PIPELINE_STAGE - 2;         // 0 .. 5
    localparam integer PAYLOAD_W   = EXPONENT_BITS + MANTISSA_BITS;
    localparam integer CLZ_W       = $clog2(FRAC_PROD_W + 1);   // bits for CLZ result

    // ================================================================
    //  STAGE 0 : Input Registers
    // ================================================================
    reg [FP_MSB:0] a, b;
    always @(posedge i_CLK) begin
        a <= i_A;
        b <= i_B;
    end

    // ================================================================
    //  Combinational Decode (from registered a, b)
    // ================================================================
    wire sign_a = a[FP_MSB];
    wire sign_b = b[FP_MSB];

    wire [EXPONENT_BITS-1:0] exp_a = a[FP_MSB-1 : MANTISSA_BITS];
    wire [EXPONENT_BITS-1:0] exp_b = b[FP_MSB-1 : MANTISSA_BITS];

    wire is_subnormal_a = (exp_a == {EXPONENT_BITS{1'b0}});
    wire is_subnormal_b = (exp_b == {EXPONENT_BITS{1'b0}});

    wire [FRAC_W-1:0] frac_a = is_subnormal_a ? {1'b0, a[MANTISSA_BITS-1:0]}
                                               : {1'b1, a[MANTISSA_BITS-1:0]};
    wire [FRAC_W-1:0] frac_b = is_subnormal_b ? {1'b0, b[MANTISSA_BITS-1:0]}
                                               : {1'b1, b[MANTISSA_BITS-1:0]};

    wire a_mant_zero = (a[MANTISSA_BITS-1:0] == {MANTISSA_BITS{1'b0}});
    wire b_mant_zero = (b[MANTISSA_BITS-1:0] == {MANTISSA_BITS{1'b0}});

    wire zero_a = is_subnormal_a & a_mant_zero;
    wire zero_b = is_subnormal_b & b_mant_zero;

    wire exp_all1_a = (exp_a == {EXPONENT_BITS{1'b1}});
    wire exp_all1_b = (exp_b == {EXPONENT_BITS{1'b1}});

    wire inf_a = exp_all1_a &  a_mant_zero;
    wire inf_b = exp_all1_b &  b_mant_zero;
    wire nan_a = exp_all1_a & ~a_mant_zero;
    wire nan_b = exp_all1_b & ~b_mant_zero;

    wire sign_product = sign_a ^ sign_b;

    // exp_sum = exp_a + exp_b - (bias - 1)
    // where bias = 2^(EXPONENT_BITS-1) - 1.
    // Subtracting (bias-1) = 2^(EXPONENT_BITS-1) - 2 here so the normalisation
    // step that expects the MSB at bit [FRAC_PROD_W-1] absorbs the remaining -1.
    wire signed [EXPONENT_BITS+1:0] exp_sum;
    assign exp_sum = $signed({2'b00, exp_a})
                   + $signed({2'b00, exp_b})
                   - $signed({{3'b000}, {(EXPONENT_BITS-2){1'b1}}, 1'b0});

    // ================================================================
    //  Pipelined Fraction Multiplier (carry-save accumulator)
    // ================================================================
    wire [FRAC_PROD_W-1:0] frac_full_product;

    pipelined_mul_cs #(
        .WIDTH_A (FRAC_W),
        .WIDTH_B (FRAC_W),
        .STAGES  (MUL_STAGES)
    ) u_mul (
        .i_CLK     (i_CLK),
        .i_A       (frac_a),
        .i_B       (frac_b),
        .o_PRODUCT (frac_full_product)
    );

    // ================================================================
    //  Metadata Delay Pipeline  (MUL_STAGES cycles)
    // ================================================================
    //  Bundled: sign(1) + exp_sum(E+2) + flags(6) + payloads(2*PAYLOAD_W)
    // ----------------------------------------------------------------
    localparam integer META_W = 1 + (EXPONENT_BITS + 2) + 6 + 2 * PAYLOAD_W;

    wire [META_W-1:0] meta_in = { sign_product,
                                   exp_sum,
                                   nan_a, nan_b, inf_a, inf_b, zero_a, zero_b,
                                   a[FP_MSB-1:0],
                                   b[FP_MSB-1:0] };
    wire [META_W-1:0] meta_out;

    generate
        if (MUL_STAGES == 0) begin : gen_meta_bypass
            assign meta_out = meta_in;
        end
        else begin : gen_meta_sr
            reg [META_W-1:0] meta_sr [0:MUL_STAGES-1];
            always @(posedge i_CLK) meta_sr[0] <= meta_in;
            genvar g;
            for (g = 1; g < MUL_STAGES; g = g + 1) begin : sr
                always @(posedge i_CLK) meta_sr[g] <= meta_sr[g-1];
            end
            assign meta_out = meta_sr[MUL_STAGES-1];
        end
    endgenerate

    // ---- Unpack delayed metadata ------------------------------------
    localparam integer B_LO     = 0;
    localparam integer A_LO     = PAYLOAD_W;
    localparam integer FL_LO    = 2 * PAYLOAD_W;
    localparam integer ES_LO    = 2 * PAYLOAD_W + 6;
    localparam integer SIGN_POS = META_W - 1;

    wire [PAYLOAD_W-1:0]            b_pay_d   = meta_out[B_LO  +: PAYLOAD_W];
    wire [PAYLOAD_W-1:0]            a_pay_d   = meta_out[A_LO  +: PAYLOAD_W];
    wire                            zero_b_d  = meta_out[FL_LO + 0];
    wire                            zero_a_d  = meta_out[FL_LO + 1];
    wire                            inf_b_d   = meta_out[FL_LO + 2];
    wire                            inf_a_d   = meta_out[FL_LO + 3];
    wire                            nan_b_d   = meta_out[FL_LO + 4];
    wire                            nan_a_d   = meta_out[FL_LO + 5];
    wire signed [EXPONENT_BITS+1:0] exp_sum_d = $signed(meta_out[ES_LO +: (EXPONENT_BITS+2)]);
    wire                            sign_d    = meta_out[SIGN_POS];

    // ================================================================
    //  Post-Multiply Combinational Logic
    //  (between multiplier output and output register)
    // ================================================================

    // --- (A) Tree-based normalisation shift ---------------------------
    //  CLZ of the full product tells us how many left-shift positions
    //  are needed to place the leading 1 at bit [FRAC_PROD_W-1].
    wire [CLZ_W-1:0] norm_shift;
    wire              prod_is_zero;

    clz_tree #(.W(FRAC_PROD_W)) u_clz (
        .i_DATA (frac_full_product),
        .o_CLZ  (norm_shift),
        .o_ZERO (prod_is_zero)
    );

    // --- (B) Determine actual shift and exponent ---------------------
    //  norm_shift : left-shift needed to place MSB at bit [FRAC_PROD_W-1]
    //  If exp_sum > norm_shift -> normal result
    //  If 0 < exp_sum <= norm_shift -> subnormal (shift limited by exp_sum)
    //  If exp_sum <= 0 -> right-shift
    //
    //  Use a common comparison width to handle cases where CLZ_W may
    //  exceed EXPONENT_BITS+2 (e.g. E=3, M=7 -> CLZ_W=5, E+2=5).
    localparam integer CMP_W = (CLZ_W > EXPONENT_BITS + 2) ? CLZ_W + 1
                                                            : EXPONENT_BITS + 2;

    wire signed [CMP_W-1:0] exp_sum_cmp   = $signed(exp_sum_d);
    wire signed [CMP_W-1:0] norm_shift_cmp = $signed({{(CMP_W - CLZ_W){1'b0}}, norm_shift});

    wire limit_left_shift = (exp_sum_cmp <= norm_shift_cmp);

    wire signed [CMP_W-1:0] exp_diff = exp_sum_cmp - norm_shift_cmp;

    wire [EXPONENT_BITS:0] exp_nonneg;
    assign exp_nonneg = limit_left_shift
                      ? {(EXPONENT_BITS+1){1'b0}}
                      : exp_diff[EXPONENT_BITS:0];

    // --- (C) Barrel shift --------------------------------------------
    //  Use CMP_W-bit signed shift amount for safe indexing.
    wire [FRAC_PROD_W-1:0] frac_shifted;
    wire [CLZ_W-1:0] actual_left_shift = limit_left_shift
                                        ? exp_sum_cmp[CLZ_W-1:0]
                                        : norm_shift;
    assign frac_shifted =
        (exp_sum_d > 0)
            ? (frac_full_product << actual_left_shift)
            : (frac_full_product >> (-exp_sum_d));

    // --- (D) Extract mantissa and rounding bits ----------------------
    //  After shifting, the leading 1 should sit at bit [FRAC_PROD_W-1].
    //  Mantissa occupies bits [FRAC_PROD_W-2 : FRAC_PROD_W-1-MANTISSA_BITS].
    wire [MANTISSA_BITS-1:0] frac_result =
        frac_shifted[FRAC_PROD_W-2 -: MANTISSA_BITS];

    wire [EXPONENT_BITS:0] exp_prerounding;
    assign exp_prerounding =
        (~frac_shifted[FRAC_PROD_W-1])
            ? {(EXPONENT_BITS+1){1'b0}} :
        ((exp_nonneg == 0) & frac_shifted[FRAC_PROD_W-1])
            ? {{EXPONENT_BITS{1'b0}}, 1'b1}
            : exp_nonneg;

    // Guard / round / sticky for round-to-nearest-even
    localparam integer GRS_TOP = FRAC_PROD_W - 1 - MANTISSA_BITS - 1; // guard bit position
    wire guard  = frac_shifted[GRS_TOP];
    wire round_ = (GRS_TOP >= 1) ? frac_shifted[GRS_TOP - 1]  : 1'b0;
    wire sticky = (GRS_TOP >= 2) ? |frac_shifted[GRS_TOP-2:0] : 1'b0;

    // --- (E) Rounding (round-to-nearest-even) ------------------------
    wire round_up = guard & (round_ | sticky | frac_result[0]);
    wire [FP_MSB:0] rounded = {exp_prerounding, frac_result}
                             + {{FP_MSB{1'b0}}, round_up};

    // --- (F) Special-case multiplexer --------------------------------
    wire [FP_MSB:0] product;
    assign product =
        (nan_a_d | nan_b_d)
            ? {sign_d, a_pay_d | b_pay_d} :
        (inf_a_d | inf_b_d)
            ? ((zero_a_d | zero_b_d)
                ? {1'b0, {EXPONENT_BITS{1'b1}}, 1'b1, {(MANTISSA_BITS-1){1'b0}}}
                : {sign_d, {EXPONENT_BITS{1'b1}}, {MANTISSA_BITS{1'b0}}}) :
        (zero_a_d | zero_b_d)
            ? {sign_d, {(EXPONENT_BITS + MANTISSA_BITS){1'b0}}} :
        (rounded[FP_MSB:MANTISSA_BITS] >= {{1'b0}, {EXPONENT_BITS{1'b1}}})
            ? {sign_d, {EXPONENT_BITS{1'b1}}, {MANTISSA_BITS{1'b0}}} :
        {sign_d, rounded[FP_MSB-1:0]};

    // --- (G) Overflow / underflow flags ------------------------------
    wire overflow  =  &product[FP_MSB-1 : MANTISSA_BITS];
    wire underflow = ~|product[FP_MSB-1 : MANTISSA_BITS];

    // ================================================================
    //  LAST STAGE : Output Registers
    // ================================================================
    always @(posedge i_CLK) begin
        o_PRODUCT <= product;
        o_OVFL    <= overflow;
        o_UDFL    <= underflow;
    end

endmodule