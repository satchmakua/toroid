// 4-bit saturating counter — the canonical sample DUT for Inductor.
// Clean (bug-free) variant. Buggy variants land alongside this in later milestones.
//
// Behavior: synchronous active-high reset clears `count` to 0. When `en` is high,
// `count` increments, saturating at 15 (does not wrap). When `en` is low, `count`
// holds its value.
module counter (
    input            clk,
    input            rst,   // synchronous, active-high
    input            en,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 4'd0;
        else if (en && count != 4'd15)
            count <= count + 4'd1;
        // else: hold
    end
endmodule
