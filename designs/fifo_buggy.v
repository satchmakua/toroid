// Synchronous FIFO (DEPTH=4, WIDTH=8) — BUGGY variant with an injected off-by-one
// in the `full` flag: it asserts `full` one slot early (count == DEPTH-1). This is
// the classic FIFO full/empty bug. Everything else matches fifo.v.
//
// Module is named `fifo` (same top) so the same property file applies to both.
module fifo #(
    parameter WIDTH = 8,
    parameter DEPTH = 4
) (
    input              clk,
    input              rst,
    input              wr_en,
    input              rd_en,
    input  [WIDTH-1:0] wdata,
    output [WIDTH-1:0] rdata,
    output             full,
    output             empty,
    output [2:0]       count
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [1:0]       wptr, rptr;
    reg [2:0]       cnt;

    assign full  = (cnt == 3'd3);   // BUG: off-by-one (should be count == DEPTH == 4)
    assign empty = (cnt == 3'd0);
    assign count = cnt;
    assign rdata = mem[rptr];

    wire do_wr = wr_en && !full;
    wire do_rd = rd_en && !empty;

    always @(posedge clk) begin
        if (rst) begin
            wptr <= 2'd0;
            rptr <= 2'd0;
            cnt  <= 3'd0;
        end else begin
            if (do_wr) begin
                mem[wptr] <= wdata;
                wptr <= wptr + 2'd1;
            end
            if (do_rd)
                rptr <= rptr + 2'd1;
            case ({do_wr, do_rd})
                2'b10:   cnt <= cnt + 3'd1;
                2'b01:   cnt <= cnt - 3'd1;
                default: cnt <= cnt;
            endcase
        end
    end
endmodule
