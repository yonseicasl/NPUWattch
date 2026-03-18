`timescale 1ns/1ps

module fpmult_tb;

    // Configurable Parameters
    parameter E = 8;
    parameter M = 40;
    parameter PIPES = 5; // Selectable: 2, 3, 4, 5, 6, 7, 8, or 9

    localparam WIDTH = E + M + 1;

    reg [WIDTH-1:0] i_A, i_B;
    reg i_CLK;
    wire [WIDTH-1:0] o_PRODUCT;
    wire o_OVFL, o_UDFL;

    // Instantiate DUT
    fpmult #(
        .EXPONENT_BITS(E),
        .MANTISSA_BITS(M),
        .PIPELINE_STAGE(PIPES)
    ) dut (
        .i_A(i_A), .i_B(i_B), .i_CLK(i_CLK),
        .o_PRODUCT(o_PRODUCT), .o_OVFL(o_OVFL), .o_UDFL(o_UDFL)
    );

    initial i_CLK = 0;
    always #5 i_CLK = ~i_CLK;

    // ----------------------------------------------------------------
    // Helper functions
    // ----------------------------------------------------------------
    function real abs_real(input real val);
        return (val < 0) ? -val : val;
    endfunction

    function [WIDTH-1:0] real_to_fp(input real val);
        integer exp;
        real mant;
        reg s;
        reg [E-1:0] e_bits;
        reg [M-1:0] m_bits;

        if (val == 0) return {WIDTH{1'b0}};
        s = (val < 0);
        exp = $floor($ln(abs_real(val)) / $ln(2.0));
        mant = abs_real(val) / (2.0**exp);
        e_bits = exp + ((1 << (E-1)) - 1);
        m_bits = (mant - 1.0) * (2.0**M);
        return {s, e_bits, m_bits};
    endfunction

    function real fp_to_real(input [WIDTH-1:0] bits);
        real res;
        integer exp_val;
        reg [E-1:0] e_bits;
        reg [M-1:0] m_bits;

        e_bits = bits[WIDTH-2 : M];
        m_bits = bits[M-1 : 0];

        if (e_bits == 0 && m_bits == 0) return 0.0;
        if (e_bits == {E{1'b1}}) return 0.0; // Inf/NaN -> 0 for comparison
        exp_val = e_bits - ((1 << (E-1)) - 1);
        res = (1.0 + (real'(m_bits) / (2.0**M))) * (2.0**exp_val);
        return bits[WIDTH-1] ? -res : res;
    endfunction

    // Build special FP constants
    function [WIDTH-1:0] make_zero(input reg sign);
        return {sign, {(E+M){1'b0}}};
    endfunction

    function [WIDTH-1:0] make_inf(input reg sign);
        return {sign, {E{1'b1}}, {M{1'b0}}};
    endfunction

    function [WIDTH-1:0] make_nan();
        return {1'b0, {E{1'b1}}, 1'b1, {(M-1){1'b0}}};
    endfunction

    // ----------------------------------------------------------------
    // Test infrastructure
    // ----------------------------------------------------------------
    real val_a, val_b, golden_product, dut_product_real;
    integer i;
    integer pass_count, fail_count, total_count;

    task automatic apply_and_check(
        input [WIDTH-1:0] a_in,
        input [WIDTH-1:0] b_in,
        input real         expected,
        input string       test_name,
        input real         tolerance    // relative tolerance, 0 = exact-hex check
    );
        begin
            i_A = a_in;
            i_B = b_in;
            repeat(PIPES) @(posedge i_CLK);
            #1;
            dut_product_real = fp_to_real(o_PRODUCT);
            total_count = total_count + 1;

            $display("\n[%0s]", test_name);
            $display("  Input A:        %h  (%f)", a_in, fp_to_real(a_in));
            $display("  Input B:        %h  (%f)", b_in, fp_to_real(b_in));
            $display("  Expected:       %f", expected);
            $display("  DUT Product:    %f  (Hex: %h)", dut_product_real, o_PRODUCT);
            $display("  Overflow: %b  Underflow: %b", o_OVFL, o_UDFL);

            if (expected == 0.0) begin
                if (dut_product_real == 0.0) begin
                    $display("  RESULT: PASSED"); pass_count = pass_count + 1;
                end else begin
                    $display("  RESULT: FAILED"); fail_count = fail_count + 1;
                end
            end else if (abs_real(dut_product_real - expected) > abs_real(expected) * tolerance) begin
                $display("  RESULT: FAILED"); fail_count = fail_count + 1;
            end else begin
                $display("  RESULT: PASSED"); pass_count = pass_count + 1;
            end
        end
    endtask

    // ----------------------------------------------------------------
    // Special-case hex check (for inf/nan where fp_to_real returns 0)
    // ----------------------------------------------------------------
    task automatic apply_and_check_hex(
        input [WIDTH-1:0] a_in,
        input [WIDTH-1:0] b_in,
        input [WIDTH-1:0] expected_hex,
        input string       test_name
    );
        begin
            i_A = a_in;
            i_B = b_in;
            repeat(PIPES) @(posedge i_CLK);
            #1;
            total_count = total_count + 1;

            $display("\n[%0s]", test_name);
            $display("  Input A:        %h", a_in);
            $display("  Input B:        %h", b_in);
            $display("  Expected Hex:   %h", expected_hex);
            $display("  DUT Product:    %h", o_PRODUCT);
            $display("  Overflow: %b  Underflow: %b", o_OVFL, o_UDFL);

            if (o_PRODUCT === expected_hex) begin
                $display("  RESULT: PASSED"); pass_count = pass_count + 1;
            end else begin
                $display("  RESULT: FAILED"); fail_count = fail_count + 1;
            end
        end
    endtask

    // ================================================================
    // Main test sequence
    // ================================================================
    initial begin
        $display("===========================================================");
        $display("  Pipelined FPMULT Testbench");
        $display("  Config: Exponent=%0d, Mantissa=%0d, Pipeline Stages=%0d", E, M, PIPES);
        $display("===========================================================");

        pass_count = 0;
        fail_count = 0;
        total_count = 0;
        i_A = 0;
        i_B = 0;

        // Flush pipeline with zeros
        repeat(PIPES + 2) @(posedge i_CLK);

        // =============================================================
        // SECTION 1 : Basic arithmetic (known values)
        // =============================================================
        $display("\n--- Section 1: Basic Arithmetic ---");

        apply_and_check(real_to_fp(1.0),  real_to_fp(1.0),  1.0,   "1.0 * 1.0 = 1.0",       0.001);
        apply_and_check(real_to_fp(2.0),  real_to_fp(3.0),  6.0,   "2.0 * 3.0 = 6.0",       0.001);
        apply_and_check(real_to_fp(1.5),  real_to_fp(2.5),  3.75,  "1.5 * 2.5 = 3.75",      0.001);
        apply_and_check(real_to_fp(0.5),  real_to_fp(0.5),  0.25,  "0.5 * 0.5 = 0.25",      0.001);
        apply_and_check(real_to_fp(10.0), real_to_fp(0.1),  1.0,   "10.0 * 0.1 = 1.0",      0.01);
        apply_and_check(real_to_fp(7.0),  real_to_fp(11.0), 77.0,  "7.0 * 11.0 = 77.0",     0.001);
        apply_and_check(real_to_fp(1.0),  real_to_fp(0.0),  0.0,   "1.0 * 0.0 = 0.0",       0.001);
        apply_and_check(real_to_fp(100.0),real_to_fp(100.0),10000.0,"100.0 * 100.0 = 10000", 0.001);

        // =============================================================
        // SECTION 2 : Signed multiplication
        // =============================================================
        $display("\n--- Section 2: Signed Multiplication ---");

        apply_and_check(real_to_fp(-1.0), real_to_fp(1.0),  -1.0,  "(-1) * 1 = -1",         0.001);
        apply_and_check(real_to_fp(-2.0), real_to_fp(3.0),  -6.0,  "(-2) * 3 = -6",         0.001);
        apply_and_check(real_to_fp(-4.0), real_to_fp(-5.0), 20.0,  "(-4) * (-5) = 20",      0.001);
        apply_and_check(real_to_fp(-0.5), real_to_fp(0.25), -0.125,"(-0.5) * 0.25 = -0.125",0.001);

        // =============================================================
        // SECTION 3 : Special values (zero, infinity, NaN)
        // =============================================================
        $display("\n--- Section 3: Special Values ---");

        // +0 * +0 = +0
        apply_and_check_hex(make_zero(0), make_zero(0), make_zero(0), "+0 * +0 = +0");

        // -0 * +0 = -0
        apply_and_check_hex(make_zero(1), make_zero(0), make_zero(1), "-0 * +0 = -0");

        // +inf * 2.0 = +inf
        apply_and_check_hex(make_inf(0), real_to_fp(2.0), make_inf(0), "+inf * 2.0 = +inf");

        // -inf * 3.0 = -inf
        apply_and_check_hex(make_inf(1), real_to_fp(3.0), make_inf(1), "-inf * 3.0 = -inf");

        // +inf * -2.0 = -inf
        apply_and_check_hex(make_inf(0), real_to_fp(-2.0), make_inf(1), "+inf * (-2.0) = -inf");

        // +inf * 0 = NaN
        apply_and_check_hex(make_inf(0), make_zero(0), make_nan(), "+inf * 0 = NaN");

        // NaN * 1.0 -> NaN (exponent = all-1, mantissa != 0)
        begin
            i_A = make_nan();
            i_B = real_to_fp(1.0);
            repeat(PIPES) @(posedge i_CLK);
            #1;
            total_count = total_count + 1;
            $display("\n[NaN * 1.0 = NaN]");
            $display("  Input A:        %h", make_nan());
            $display("  Input B:        %h", real_to_fp(1.0));
            $display("  DUT Product:    %h", o_PRODUCT);
            $display("  Overflow: %b  Underflow: %b", o_OVFL, o_UDFL);
            // Verify exponent is all-1 and mantissa is non-zero (i.e. NaN)
            if (o_PRODUCT[WIDTH-2:M] == {E{1'b1}} && o_PRODUCT[M-1:0] != 0) begin
                $display("  RESULT: PASSED (output is NaN)");
                pass_count = pass_count + 1;
            end else begin
                $display("  RESULT: FAILED (expected NaN)");
                fail_count = fail_count + 1;
            end
        end

        // =============================================================
        // SECTION 4 : Overflow / Underflow flag checks
        // =============================================================
        $display("\n--- Section 4: Overflow/Underflow Flag Checks ---");

        // Overflow: very large * very large
        begin
            reg [E-1:0] big_exp;
            big_exp = {E{1'b1}} - 1; // max finite exponent
            i_A = {1'b0, big_exp, {M{1'b1}}};
            i_B = {1'b0, big_exp, {M{1'b1}}};
            repeat(PIPES) @(posedge i_CLK);
            #1;
            total_count = total_count + 1;
            $display("\n[Overflow: large * large]");
            $display("  DUT Product: %h  Overflow: %b", o_PRODUCT, o_OVFL);
            if (o_OVFL === 1'b1) begin
                $display("  RESULT: PASSED (overflow detected)");
                pass_count = pass_count + 1;
            end else begin
                $display("  RESULT: FAILED (expected overflow)");
                fail_count = fail_count + 1;
            end
        end

        // Underflow: very small * very small
        begin
            reg [E-1:0] small_exp;
            small_exp = {{(E-1){1'b0}}, 1'b1}; // exponent = 1 (smallest normal)
            i_A = {1'b0, small_exp, {M{1'b0}}};
            i_B = {1'b0, small_exp, {M{1'b0}}};
            repeat(PIPES) @(posedge i_CLK);
            #1;
            total_count = total_count + 1;
            $display("\n[Underflow: tiny * tiny]");
            $display("  DUT Product: %h  Underflow: %b", o_PRODUCT, o_UDFL);
            if (o_UDFL === 1'b1) begin
                $display("  RESULT: PASSED (underflow detected)");
                pass_count = pass_count + 1;
            end else begin
                $display("  RESULT: FAILED (expected underflow)");
                fail_count = fail_count + 1;
            end
        end

        // =============================================================
        // SECTION 5 : Powers of two (exact results expected)
        // =============================================================
        $display("\n--- Section 5: Powers of Two ---");

        apply_and_check(real_to_fp(2.0),   real_to_fp(2.0),   4.0,   "2 * 2 = 4",      0.0);
        apply_and_check(real_to_fp(4.0),   real_to_fp(8.0),   32.0,  "4 * 8 = 32",     0.0);
        apply_and_check(real_to_fp(0.25),  real_to_fp(4.0),   1.0,   "0.25 * 4 = 1",   0.0);
        apply_and_check(real_to_fp(0.125), real_to_fp(0.125), 0.015625, "0.125^2 = 0.015625", 0.0);

        // =============================================================
        // SECTION 6 : Pipeline continuity (back-to-back inputs)
        // =============================================================
        $display("\n--- Section 6: Back-to-Back Pipeline Throughput ---");
        begin
            real a_vals [0:4];
            real b_vals [0:4];
            real expected_vals [0:4];
            real actual_val;
            reg [WIDTH-1:0] captured [0:4];
            integer j, k;

            a_vals[0] = 1.0; b_vals[0] = 2.0; expected_vals[0] = 2.0;
            a_vals[1] = 3.0; b_vals[1] = 4.0; expected_vals[1] = 12.0;
            a_vals[2] = 5.0; b_vals[2] = 6.0; expected_vals[2] = 30.0;
            a_vals[3] = 7.0; b_vals[3] = 8.0; expected_vals[3] = 56.0;
            a_vals[4] = 9.0; b_vals[4] = 10.0;expected_vals[4] = 90.0;

            // Inject on negedge (stable before posedge), capture
            // results PIPES posedges later using fork-join.
            fork
                // --- Injection (negedge: avoids race with DUT posedge) ---
                begin
                    for (j = 0; j < 5; j = j + 1) begin
                        @(negedge i_CLK);
                        i_A = real_to_fp(a_vals[j]);
                        i_B = real_to_fp(b_vals[j]);
                    end
                end
                // --- Capture (posedge + #1 settling) ---
                begin
                    // First result emerges PIPES posedges after DUT
                    // captures the first input.
                    repeat(PIPES) @(posedge i_CLK);
                    for (k = 0; k < 5; k = k + 1) begin
                        #1;
                        captured[k] = o_PRODUCT;
                        if (k < 4) @(posedge i_CLK);
                    end
                end
            join

            // Evaluate captured results
            for (k = 0; k < 5; k = k + 1) begin
                actual_val = fp_to_real(captured[k]);
                total_count = total_count + 1;
                $display("  B2B[%0d]: %f * %f = %f (expected %f) %s",
                    k, a_vals[k], b_vals[k], actual_val, expected_vals[k],
                    (abs_real(actual_val - expected_vals[k]) <= abs_real(expected_vals[k]) * 0.001) ? "PASSED" : "FAILED");
                if (abs_real(actual_val - expected_vals[k]) <= abs_real(expected_vals[k]) * 0.001)
                    pass_count = pass_count + 1;
                else
                    fail_count = fail_count + 1;
            end
        end

        // =============================================================
        // SECTION 7 : Random test vectors
        // =============================================================
        $display("\n--- Section 7: Random Test Vectors ---");

        for (i = 0; i < 50; i = i + 1) begin
            val_a = (real'($urandom % 100000)) + (real'($urandom % 100000) / 100000.0);
            val_b = (real'($urandom % 100000)) + (real'($urandom % 100000) / 100000.0);
            golden_product = val_a * val_b;

            i_A = real_to_fp(val_a);
            i_B = real_to_fp(val_b);

            repeat(PIPES) @(posedge i_CLK);
            #1;

            dut_product_real = fp_to_real(o_PRODUCT);
            total_count = total_count + 1;

            $display("\nRandom Test %0d:", i+1);
            $display("  Input A:        %f", val_a);
            $display("  Input B:        %f", val_b);
            $display("  Golden Product: %f", golden_product);
            $display("  DUT Product:    %f (Hex: %h)", dut_product_real, o_PRODUCT);

            // Allow 1% tolerance for rounding precision
            if (golden_product == 0.0) begin
                if (dut_product_real == 0.0) begin
                    $display("  RESULT: PASSED"); pass_count = pass_count + 1;
                end else begin
                    $display("  RESULT: FAILED"); fail_count = fail_count + 1;
                end
            end else if (abs_real(dut_product_real - golden_product) > abs_real(golden_product) * 0.01) begin
                $display("  RESULT: FAILED"); fail_count = fail_count + 1;
            end else begin
                $display("  RESULT: PASSED"); pass_count = pass_count + 1;
            end
        end

        // =============================================================
        // Final Summary
        // =============================================================
        $display("\n===========================================================");
        $display("  TEST SUMMARY");
        $display("  Pipeline Stages: %0d", PIPES);
        $display("  Total:  %0d", total_count);
        $display("  Passed: %0d", pass_count);
        $display("  Failed: %0d", fail_count);
        $display("===========================================================");
        if (fail_count == 0)
            $display("  >>> ALL TESTS PASSED <<<");
        else
            $display("  >>> SOME TESTS FAILED <<<");
        $display("===========================================================\n");
        $finish;
    end

endmodule
