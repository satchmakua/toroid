// max2_min_bug — claims to be max2 but returns the MINIMUM. NOT equivalent;
// equivalence checking should find a distinguishing input (any a != b).
module max2_min_bug (
    input  [3:0] a,
    input  [3:0] b,
    output [3:0] y
);
    assign y = (a < b) ? a : b;   // BUG: this is min(a, b), not max
endmodule
