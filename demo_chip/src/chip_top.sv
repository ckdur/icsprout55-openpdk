// SPDX-FileCopyrightText: © 2025 LibreLane Template Contributors
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module chip_top #(
    // Power/ground pads for core
    parameter NUM_VDD_PADS = 1,
    parameter NUM_VSS_PADS = 1,
    
    // Power/ground pads for I/O
    parameter NUM_IOVDD_PADS = 1,
    parameter NUM_IOVSS_PADS = 1,
    
    // Signal pads
    parameter NUM_INPUT_PADS  = 10,
    parameter NUM_OUTPUT_PADS = 8,
    parameter NUM_BIDIR_PADS  = 8,
    parameter NUM_ANALOG_PADS = 8
    )(
    `ifdef USE_POWER_PINS
    inout wire IOVDD,
    inout wire IOVSS,
    inout wire VDD,
    inout wire VSS,
    `endif
    inout  wire clk_XI_PAD,
    inout  wire clk_XO_PAD,
    inout  wire rst_n_PAD,
    inout  wire [NUM_INPUT_PADS-1 :0] input_PAD,
    inout  wire [NUM_OUTPUT_PADS-1:0] output_PAD,
    inout  wire [NUM_BIDIR_PADS-1 :0] bidir_PAD,
    inout  wire [NUM_ANALOG_PADS-1:0] analog_PAD
);

    wire clk_PAD2CORE;
    wire rst_n_PAD2CORE;
    wire [NUM_INPUT_PADS-1 :0] input_PAD2CORE;
    wire [NUM_OUTPUT_PADS-1:0] output_CORE2PAD;
    wire [NUM_BIDIR_PADS-1 :0] bidir_PAD2CORE;
    wire [NUM_BIDIR_PADS-1 :0] bidir_CORE2PAD;
    wire [NUM_BIDIR_PADS-1 :0] bidir_CORE2PAD_OE;
    wire [NUM_ANALOG_PADS-1:0] analog_PADRES;

    // Power/ground pad instances
    generate
    for (genvar i=0; i<NUM_IOVDD_PADS; i++) begin : iovdd_pads
        (* keep *)
        P65_1233_VDDIO3 iovdd_pad  (
            `ifdef USE_POWER_PINS
            .VDDIO  (IOVDD)
            `endif
        );
    end
    for (genvar i=0; i<NUM_IOVSS_PADS; i++) begin : iovss_pads
        (* keep *)
        P65_1233_VSSIO3 iovss_pad  (
            `ifdef USE_POWER_PINS
            .VDDIO  (IOVDD),
            .VSSIO  (IOVSS),
            .VDD    (VDD),
            .VSS    (VSS)
            `endif
        );
    end
    for (genvar i=0; i<NUM_VDD_PADS; i++) begin : vdd_pads
        (* keep *)
        P65_1233_VDD3 vdd_pad  (
            `ifdef USE_POWER_PINS
            .VDDIO  (IOVDD),
            .VSSIO  (IOVSS),
            .VDD    (VDD),
            .VSS    (VSS)
            `endif
        );
    end
    for (genvar i=0; i<NUM_VSS_PADS; i++) begin : vss_pads
        (* keep *)
        P65_1233_VSS3 vss_pad  (
            `ifdef USE_POWER_PINS
            .VDDIO  (IOVDD),
            .VSSIO  (IOVSS),
            .VDD    (VDD),
            .VSS    (VSS)
            `endif
        );
    end
    endgenerate

    // Signal IO pad instances

    // Clock crystal oscillator
    P65_1233_PWE clk_pad (
        `ifdef USE_POWER_PINS
        .VDDIO  (IOVDD),
        .VSSIO  (IOVSS),
        .VDD    (VDD),
        .VSS    (VSS),
        `endif
        .E      (1'b1),
        .XC     (clk_PAD2CORE),
        .XIN    (clk_XI_PAD),
        .XOUT   (clk_XO_PAD)
    );
    
    // Normal input
    P65_1233_PBMUX rst_n_pad (
        `ifdef USE_POWER_PINS
        .VDDIO  (IOVDD),
        .VSSIO  (IOVSS),
        .VDD    (VDD),
        .VSS    (VSS),
        `endif
        .C      (rst_n_PAD2CORE),
        .A      (),
        .PAD    (rst_n_PAD),
        .IE     (1'b1),
        .CS     (1'b0),
        .I      (1'b0),
        .OE     (1'b0),
        .OD     (1'b0),
        .PU     (1'b0),
        .PD     (1'b0),
        .DS0    (1'b0),
        .DS1    (1'b0)
    );

    generate
    for (genvar i=0; i<NUM_INPUT_PADS; i++) begin : inputs
        P65_1233_PBMUX input_pad (
            `ifdef USE_POWER_PINS
            .VDDIO  (IOVDD),
            .VSSIO  (IOVSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
            .C      (input_PAD2CORE[i]),
            .A      (),
            .PAD    (input_PAD[i]),
            .IE     (1'b1),
            .CS     (1'b0),
            .I      (1'b0),
            .OE     (1'b0),
            .OD     (1'b0),
            .PU     (1'b0),
            .PD     (1'b0),
            .DS0    (1'b0),
            .DS1    (1'b0)
        );
    end
    endgenerate

    generate
    for (genvar i=0; i<NUM_OUTPUT_PADS; i++) begin : outputs
        P65_1233_PBMUX output_pad (
            `ifdef USE_POWER_PINS
            .VDDIO  (IOVDD),
            .VSSIO  (IOVSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
            .C      (),
            .A      (),
            .PAD    (output_PAD[i]),
            .IE     (1'b0),
            .CS     (1'b0),
            .I      (output_CORE2PAD[i]),
            .OE     (1'b1),
            .OD     (1'b0), // TODO: Activate open-drain?
            .PU     (1'b0),
            .PD     (1'b0),
            .DS0    (1'b0), // TODO: In output mode, what should be the DS?
            .DS1    (1'b0)
        );
    end
    endgenerate

    generate
    for (genvar i=0; i<NUM_BIDIR_PADS; i++) begin : bidirs
        P65_1233_PBMUX bidir_pad (
            `ifdef USE_POWER_PINS
            .VDDIO  (IOVDD),
            .VSSIO  (IOVSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
            .C      (bidir_PAD2CORE[i]),
            .A      (),
            .PAD    (output_PAD[i]),
            .IE     (!bidir_CORE2PAD_OE[i]),
            .CS     (1'b0),
            .I      (bidir_CORE2PAD[i]),
            .OE     (bidir_CORE2PAD_OE[i]),
            .OD     (1'b0), // TODO: Activate open-drain?
            .PU     (1'b0),
            .PD     (1'b0),
            .DS0    (1'b0), // TODO: In output mode, what should be the DS?
            .DS1    (1'b0)
        );
    end
    endgenerate
    
    generate
    for (genvar i=0; i<NUM_ANALOG_PADS; i++) begin : analogs
        (* keep *)
        // NOTE: Can be also P65_1233_PAR_5
        P65_1233_PAR analog_pad (
            `ifdef USE_POWER_PINS
            .VDDA   (IOVDD), // TODO: This is wrong
            .VSSA   (IOVSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
            .A      (analog_PADRES[i]),
            .PAD    (analog_PAD[i])
        );
    end
    endgenerate

    // Core design

    (* keep *) chip_core #(
        .NUM_INPUT_PADS  (NUM_INPUT_PADS),
        .NUM_OUTPUT_PADS (NUM_OUTPUT_PADS),
        .NUM_BIDIR_PADS  (NUM_BIDIR_PADS),
        .NUM_ANALOG_PADS (NUM_ANALOG_PADS)
    ) i_chip_core (
        .clk        (clk_PAD2CORE),
        .rst_n      (rst_n_PAD2CORE),
        .input_in   (input_PAD2CORE),
        .output_out (output_CORE2PAD),
        .bidir_in   (bidir_PAD2CORE),
        .bidir_out  (bidir_CORE2PAD),
        .bidir_oe   (bidir_CORE2PAD_OE),
        .analog     (analog_PADRES)
    );

endmodule

`default_nettype wire
