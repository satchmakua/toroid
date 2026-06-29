// max2_alt — a different implementation of 4-bit maximum, EQUIVALENT to max2.
// (Uses >= instead of >; the a == b case returns the same value either way.)
module max2_alt (
    input  [3:0] a,
    input  [3:0] b,
    output [3:0] y
);
    assign y = (a >= b) ? a : b;
endmodule
