module intmac #(
    parameter int A_WIDTH = 32,
    parameter int B_WIDTH = 32,
    parameter int OUT_WIDTH = 64,
    parameter int ACC_WIDTH = 64,
    parameter int PIPELINE_STAGES = 3
) (
    input  logic signed [A_WIDTH-1:0] i_a,
    input  logic signed [B_WIDTH-1:0] i_b,
    input  logic                      i_clk,
    input  logic                      i_rst_n,
    output logic signed [OUT_WIDTH-1:0] o_result
);

    localparam int SEG_COUNT = PIPELINE_STAGES - 1;
    localparam int CHUNK_WIDTH = (B_WIDTH + SEG_COUNT - 1) / SEG_COUNT;
    localparam int FULL_WIDTH = A_WIDTH + B_WIDTH;

    logic [A_WIDTH-1:0] a_mag_r;
    logic [B_WIDTH-1:0] b_mag_r;
    logic sign_r;
    logic valid_r;
    logic signed [A_WIDTH-1:0] prev_a;
    logic signed [B_WIDTH-1:0] prev_b;
    logic signed [ACC_WIDTH-1:0] acc_state;

    /* verilator lint_off UNDRIVEN */
    logic [A_WIDTH-1:0] a_pipe [0:SEG_COUNT-1];
    logic [B_WIDTH-1:0] b_pipe [0:SEG_COUNT-1];
    logic sign_pipe [0:SEG_COUNT-1];
    logic valid_pipe [0:SEG_COUNT-1];
    logic [FULL_WIDTH-1:0] pp_pipe [0:SEG_COUNT-1];
    /* verilator lint_on UNDRIVEN */

    wire [A_WIDTH-1:0] a_abs = i_a[A_WIDTH-1] ? (~i_a + 1'b1) : i_a;
    wire [B_WIDTH-1:0] b_abs = i_b[B_WIDTH-1] ? (~i_b + 1'b1) : i_b;

    always_ff @(posedge i_clk) begin
        if (!i_rst_n) begin
            a_mag_r <= '0;
            b_mag_r <= '0;
            sign_r <= 1'b0;
            valid_r <= 1'b0;
            prev_a <= '0;
            prev_b <= '0;
        end else begin
            a_mag_r <= a_abs;
            b_mag_r <= b_abs;
            sign_r <= i_a[A_WIDTH-1] ^ i_b[B_WIDTH-1];
            valid_r <= (i_a != prev_a) || (i_b != prev_b);
            prev_a <= i_a;
            prev_b <= i_b;
        end
    end

    generate
        genvar g;
        for (g = 0; g < SEG_COUNT; g = g + 1) begin : gen_mac_stage
            localparam int LO = g * CHUNK_WIDTH;
            localparam int HI = ((LO + CHUNK_WIDTH) > B_WIDTH) ? (B_WIDTH - 1) : (LO + CHUNK_WIDTH - 1);
            localparam int CW = HI - LO + 1;

            wire [A_WIDTH-1:0] a_in = (g == 0) ? a_mag_r : a_pipe[g-1];
            wire [B_WIDTH-1:0] b_in = (g == 0) ? b_mag_r : b_pipe[g-1];
            wire sign_in = (g == 0) ? sign_r : sign_pipe[g-1];
            wire valid_in = (g == 0) ? valid_r : valid_pipe[g-1];
            wire [FULL_WIDTH-1:0] pp_in = (g == 0) ? '0 : pp_pipe[g-1];
            wire [CW-1:0] b_chunk = b_in[HI:LO];
            wire [A_WIDTH+CW-1:0] partial_small = a_in * b_chunk;
            wire [FULL_WIDTH-1:0] partial_shifted = { {(FULL_WIDTH-A_WIDTH-CW-LO){1'b0}}, partial_small, {LO{1'b0}} };
            wire [FULL_WIDTH-1:0] pp_next = pp_in + partial_shifted;
            localparam int PROD_COPY_W = (ACC_WIDTH < FULL_WIDTH) ? ACC_WIDTH : FULL_WIDTH;
            wire [ACC_WIDTH-1:0] prod_acc = { {(ACC_WIDTH-PROD_COPY_W){1'b0}}, pp_next[PROD_COPY_W-1:0] };
            wire signed [ACC_WIDTH-1:0] prod_signed = sign_in ? -$signed(prod_acc) : $signed(prod_acc);
            wire signed [ACC_WIDTH-1:0] acc_next = acc_state + prod_signed;

            if (g < SEG_COUNT - 1) begin : gen_mid
                always_ff @(posedge i_clk) begin
                    if (!i_rst_n) begin
                        a_pipe[g] <= '0;
                        b_pipe[g] <= '0;
                        sign_pipe[g] <= 1'b0;
                        pp_pipe[g] <= '0;
                    end else begin
                        a_pipe[g] <= a_in;
                        b_pipe[g] <= b_in;
                        sign_pipe[g] <= sign_in;
                        valid_pipe[g] <= valid_in;
                        pp_pipe[g] <= pp_next;
                    end
                end
            end else begin : gen_last
                always_ff @(posedge i_clk) begin
                    if (!i_rst_n) begin
                        acc_state <= '0;
                    end else if (valid_in) begin
                        acc_state <= acc_next;
                    end
                end
            end
        end
    endgenerate

    assign o_result = $signed(acc_state[OUT_WIDTH-1:0]);

endmodule
