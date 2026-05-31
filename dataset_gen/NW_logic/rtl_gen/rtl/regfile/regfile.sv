module regfile #(
    parameter int WIDTH = 32,
    parameter int DEPTH = 64,
    parameter int ADDR_WIDTH = 6,
    parameter int NUM_READ_PORTS = 1,
    parameter int NUM_WRITE_PORTS = 1,
    parameter int W_PORT_WIDTH = 1,
    parameter int W_ADDR_BITS = 6,
    parameter int W_DATA_BITS = 32,
    parameter int R_ADDR_BITS = 6,
    parameter int R_DATA_BITS = 32
) (
    input  logic                                i_clk,
    input  logic                                i_rst_n,
    input  logic [W_PORT_WIDTH-1:0]             i_w_en,
    input  logic [W_ADDR_BITS-1:0]              i_w_addr,
    input  logic [W_DATA_BITS-1:0]              i_w_data,
    input  logic [R_ADDR_BITS-1:0]               i_r_addr,
    output logic [R_DATA_BITS-1:0]               o_r_data
);

    logic [WIDTH-1:0] mem [0:DEPTH-1];

    always_ff @(posedge i_clk) begin
        automatic int addr;
        /* verilator lint_off SELRANGE */
        for (int port = 0; port < NUM_WRITE_PORTS; port = port + 1) begin
            addr = int'(i_w_addr[port*ADDR_WIDTH +: ADDR_WIDTH]);
            if (i_w_en[port] && (addr < DEPTH)) begin
                mem[addr] <= i_w_data[port*WIDTH +: WIDTH];
            end
        end
        /* verilator lint_on SELRANGE */
    end

    always_comb begin
        automatic int addr;
        o_r_data = '0;
        /* verilator lint_off SELRANGE */
        for (int port = 0; port < NUM_READ_PORTS; port = port + 1) begin
            addr = int'(i_r_addr[port*ADDR_WIDTH +: ADDR_WIDTH]);
            if (addr < DEPTH) begin
                o_r_data[port*WIDTH +: WIDTH] = mem[addr];
            end
        end
        /* verilator lint_on SELRANGE */
    end

endmodule
