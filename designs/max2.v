// max2 — combinational 4-bit maximum. The reference (spec).
module max2 (
    input  [3:0] a,
    input  [3:0] b,
    output [3:0] y
);
    assign y = (a > b) ? a : b;
endmodule
