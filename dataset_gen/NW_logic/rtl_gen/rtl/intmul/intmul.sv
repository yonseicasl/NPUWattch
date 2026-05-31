module intmul #(
    parameter int A_WIDTH = 8,
    parameter int B_WIDTH = 8,
    parameter int OUT_WIDTH = 16,
    parameter int PIPELINE_STAGES = 2
) (
    input  logic signed [A_WIDTH-1:0] i_a,
    input  logic signed [B_WIDTH-1:0] i_b,
    input  logic                      i_clk,
    input  logic                      i_rst_n,
    output logic signed [OUT_WIDTH-1:0] o_product
);

    localparam int SEG_COUNT = PIPELINE_STAGES - 1;
    localparam int CHUNK_WIDTH = (B_WIDTH + SEG_COUNT - 1) / SEG_COUNT;
    localparam int FULL_WIDTH = A_WIDTH + B_WIDTH;

    logic [A_WIDTH-1:0] a_mag_r;
    logic [B_WIDTH-1:0] b_mag_r;
    logic sign_r;

    logic [A_WIDTH-1:0] a_pipe [0:SEG_COUNT-1];
    logic [B_WIDTH-1:0] b_pipe [0:SEG_COUNT-1];
    logic sign_pipe [0:SEG_COUNT-1];
    logic [FULL_WIDTH-1:0] acc_pipe [0:SEG_COUNT-1];

    wire [A_WIDTH-1:0] a_abs = i_a[A_WIDTH-1] ? (~i_a + 1'b1) : i_a;
    wire [B_WIDTH-1:0] b_abs = i_b[B_WIDTH-1] ? (~i_b + 1'b1) : i_b;

    always_ff @(posedge i_clk) begin
        if (!i_rst_n) begin
            a_mag_r <= '0;
            b_mag_r <= '0;
            sign_r <= 1'b0;
        end else begin
            a_mag_r <= a_abs;
            b_mag_r <= b_abs;
            sign_r <= i_a[A_WIDTH-1] ^ i_b[B_WIDTH-1];
        end
    end

    generate
        genvar g;
        for (g = 0; g < SEG_COUNT; g = g + 1) begin : gen_mul_stage
            localparam int LO = g * CHUNK_WIDTH;
            localparam int HI = ((LO + CHUNK_WIDTH) > B_WIDTH) ? (B_WIDTH - 1) : (LO + CHUNK_WIDTH - 1);
            localparam int CW = HI - LO + 1;

            wire [A_WIDTH-1:0] a_in = (g == 0) ? a_mag_r : a_pipe[g-1];
            wire [B_WIDTH-1:0] b_in = (g == 0) ? b_mag_r : b_pipe[g-1];
            wire sign_in = (g == 0) ? sign_r : sign_pipe[g-1];
            wire [FULL_WIDTH-1:0] acc_in = (g == 0) ? '0 : acc_pipe[g-1];
            wire [CW-1:0] b_chunk = b_in[HI:LO];
            wire [A_WIDTH+CW-1:0] partial_small = a_in * b_chunk;
            wire [FULL_WIDTH-1:0] partial_shifted = { {(FULL_WIDTH-A_WIDTH-CW-LO){1'b0}}, partial_small, {LO{1'b0}} };
            wire [FULL_WIDTH-1:0] acc_next = acc_in + partial_shifted;

            always_ff @(posedge i_clk) begin
                if (!i_rst_n) begin
                    a_pipe[g] <= '0;
                    b_pipe[g] <= '0;
                    sign_pipe[g] <= 1'b0;
                    acc_pipe[g] <= '0;
                end else begin
                    a_pipe[g] <= a_in;
                    b_pipe[g] <= b_in;
                    sign_pipe[g] <= sign_in;
                    acc_pipe[g] <= acc_next;
                end
            end
        end
    endgenerate

    wire [OUT_WIDTH-1:0] mag_trunc = acc_pipe[SEG_COUNT-1][OUT_WIDTH-1:0];
    wire [OUT_WIDTH-1:0] product_bits = sign_pipe[SEG_COUNT-1] ? (~mag_trunc + 1'b1) : mag_trunc;
    assign o_product = $signed(product_bits);

endmodule
