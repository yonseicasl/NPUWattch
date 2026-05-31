module intadd #(
    parameter int A_WIDTH = 8,
    parameter int B_WIDTH = 8,
    parameter int OUT_WIDTH = 16,
    parameter int PIPELINE_STAGES = 2
) (
    input  logic signed [A_WIDTH-1:0] i_a,
    input  logic signed [B_WIDTH-1:0] i_b,
    input  logic                      i_clk,
    input  logic                      i_rst_n,
    output logic signed [OUT_WIDTH-1:0] o_sum
);

    localparam int SEG_COUNT = PIPELINE_STAGES - 1;
    localparam int CHUNK_WIDTH = (OUT_WIDTH + SEG_COUNT - 1) / SEG_COUNT;

    logic signed [OUT_WIDTH-1:0] a_r;
    logic signed [OUT_WIDTH-1:0] b_r;
    logic signed [OUT_WIDTH-1:0] a_pipe [0:SEG_COUNT-1];
    logic signed [OUT_WIDTH-1:0] b_pipe [0:SEG_COUNT-1];
    logic [OUT_WIDTH-1:0] partial_pipe [0:SEG_COUNT-1];
    logic carry_pipe [0:SEG_COUNT-1];

    always_ff @(posedge i_clk) begin
        if (!i_rst_n) begin
            a_r <= '0;
            b_r <= '0;
        end else begin
            /* verilator lint_off WIDTHEXPAND */
            a_r <= $signed(i_a);
            b_r <= $signed(i_b);
            /* verilator lint_on WIDTHEXPAND */
        end
    end

    generate
        genvar g;
        for (g = 0; g < SEG_COUNT; g = g + 1) begin : gen_add_stage
            localparam int LO = g * CHUNK_WIDTH;
            localparam int HI = ((LO + CHUNK_WIDTH) > OUT_WIDTH) ? (OUT_WIDTH - 1) : (LO + CHUNK_WIDTH - 1);
            localparam int CW = HI - LO + 1;

            wire signed [OUT_WIDTH-1:0] a_in = (g == 0) ? a_r : a_pipe[g-1];
            wire signed [OUT_WIDTH-1:0] b_in = (g == 0) ? b_r : b_pipe[g-1];
            wire [OUT_WIDTH-1:0] partial_in = (g == 0) ? '0 : partial_pipe[g-1];
            wire carry_in = (g == 0) ? 1'b0 : carry_pipe[g-1];
            /* verilator lint_off WIDTHEXPAND */
            wire [CW:0] chunk_sum = {1'b0, a_in[HI:LO]} + {1'b0, b_in[HI:LO]} + carry_in;
            /* verilator lint_on WIDTHEXPAND */
            wire [OUT_WIDTH-1:0] chunk_insert = { {(OUT_WIDTH-HI-1){1'b0}}, chunk_sum[CW-1:0], {LO{1'b0}} };
            wire [OUT_WIDTH-1:0] partial_next = partial_in | chunk_insert;

            always_ff @(posedge i_clk) begin
                if (!i_rst_n) begin
                    a_pipe[g] <= '0;
                    b_pipe[g] <= '0;
                    partial_pipe[g] <= '0;
                    carry_pipe[g] <= 1'b0;
                end else begin
                    a_pipe[g] <= a_in;
                    b_pipe[g] <= b_in;
                    partial_pipe[g] <= partial_next;
                    carry_pipe[g] <= chunk_sum[CW];
                end
            end
        end
    endgenerate

    assign o_sum = $signed(partial_pipe[SEG_COUNT-1]);

endmodule
