// Antenna test design: inputs on the west edge drive minimum size inverters
// (INVX0P5, instantiated so synthesis / resizing cannot change them) directly,
// outputs leave on the east edge of a 3 mm long die. The resizer repairs are off
// (config.json), so the routed input nets are long wires on small gates without
// any diffusion until the antenna repair adds diodes.
module antenna (
    input  [7:0] a,
    output [7:0] y
);
  genvar i;
  generate
    for (i = 0; i < 8; i = i + 1) begin : g
      INVX0P5H7R u (.A(a[i]), .Y(y[i]));
    end
  endgenerate
endmodule
