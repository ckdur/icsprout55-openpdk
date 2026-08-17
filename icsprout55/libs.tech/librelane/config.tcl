# icsprout55/libs.tech/librelane/config.tcl

# Standard cell library default (also settable via --scl/STD_CELL_LIBRARY)
set ::env(STD_CELL_LIBRARY) "ics55_LLSC_H7CR"

# Power/ground pins
set ::env(VDD_PIN) "VDD"
set ::env(GND_PIN) "VSS"

# Technology LEF, as a map of corner patterns to files.
# NOTE: the bring-up config used the plain N551P6M.lef (not the _ecos variant).
set ::env(TECH_LEFS) [list \
    "nom_*" "$::env(PDK_ROOT)/$::env(PDK)/libs.ref/prtech/techLEF/N551P6M_ecos.lef" \
]

# Timing corners (IPVT). Corner names match the bring-up configuration exactly.
set ::env(DEFAULT_CORNER) "nom_tt_025C_1v20"
set ::env(TIMING_VIOLATION_CORNERS) "*"
set ::env(STA_CORNERS) [list \
    "nom_tt_025C_1v20" \
    "nom_ss_125C_1v08" \
    "nom_ff_n40C_1v32" \
]

# Routing layers
set ::env(RT_MIN_LAYER) "MET1"
set ::env(RT_MAX_LAYER) "MET4"

# IO pin layers (tech.yml: metal_layers.hor-layer/ver-layer)
set ::env(IO_PIN_H_LAYER) "MET3"
set ::env(IO_PIN_V_LAYER) "MET2"

# Global routing layer adjustments, one value per routing layer in the tech
# LEF (MET1..MET5, T4M2; extra layers are left unadjusted).
set ::env(GRT_LAYER_ADJUSTMENTS) [list 0.99 0 0 0 0 0]

# Primary GDSII stream-out tool. This PDK ships no magic tech file, so magic
# cannot be primary.
set ::env(PRIMARY_GDSII_STREAMOUT_TOOL) "klayout"

# Placement cell padding in sites. 0 matches the bring-up configuration
# (DFFRAM RAM blocks are macro-dominated; >0 is only needed for diode
# insertion flows, which are inactive as long as DIODE_CELL is unset).
set ::env(GPL_CELL_PADDING) 0
set ::env(DPL_CELL_PADDING) 0

# ----------------------------------------------------------------------------
# Signoff tool collateral NOT shipped with this PDK.
#
# ----------------------------------------------------------------------------
set ::env(MAGICRC) "/dev/null"
set ::env(MAGIC_TECH) "/dev/null"
set ::env(MAGIC_PDK_SETUP) "/dev/null"
set ::env(NETGEN_SETUP) "/dev/null"
set ::env(KLAYOUT_TECH) "/dev/null"
set ::env(KLAYOUT_PROPERTIES) "/dev/null"
set ::env(KLAYOUT_DEF_LAYER_MAP) "/dev/null"

# TODO: This is the only file that is left to implement for RCX
set ::env(RCX_RULESETS) [list \
    "nom_*" "$::env(PDK_ROOT)/$::env(PDK)/libs.ref/prtech/techLEF/N551P6M_ecos.lef" \
]

 # icsprout55-pdk/libs.tech/librelane/ics55_LLSC_H7CR/config.tcl

set scl_dir "$::env(PDK_ROOT)/$::env(PDK)/libs.ref/$::env(STD_CELL_LIBRARY)"

# SCL-specific power/ground pins
set ::env(SCL_POWER_PINS) [list "VDD"]
set ::env(SCL_GROUND_PINS) [list "VSS"]

# --- Views ------------------------------------------------------------------
# The bring-up configuration used the "_ecos" cell LEF with the plain
# (non-ecos) tech LEF; keep that proven combination.
set ::env(CELL_LEFS) [list \
    "$scl_dir/lef/ics55_LLSC_H7CR_ecos.lef" \
]
set ::env(CELL_GDS) [list \
    "$scl_dir/gds/ics55_LLSC_H7CR.gds" \
]
set ::env(CELL_VERILOG_MODELS) [list \
    "$scl_dir/verilog/ics55_LLSC_H7CR.v" \
]
set ::env(CELL_CDLS) [list \
    "$scl_dir/cdl/ics55_LLSC_H7CR.cdl" \
]

# --- Timing libraries (tech.yml: sta.libs) ------------------------------------
# Exactly one entry must match DEFAULT_CORNER (nom_tt_025C_1v20).
set ::env(LIB) [list \
    "nom_tt_025C_1v20" "$scl_dir/liberty/ics55_LLSC_H7CR_typ_tt_1p2_25_nldm.lib" \
    "nom_ss_125C_1v08" "$scl_dir/liberty/ics55_LLSC_H7CR_ss_rcworst_1p08_125_nldm.lib" \
    "nom_ff_n40C_1v32" "$scl_dir/liberty/ics55_LLSC_H7CR_ff_rcbest_1p32_m40_nldm.lib" \
]

# --- Excluded cells ------------------------------------------------------------
# No exclusions. /dev/null satisfies the required-Path check and reads empty.
set ::env(SYNTH_EXCLUDED_CELL_FILE) "/dev/null"
set ::env(PNR_EXCLUDED_CELL_FILE) "/dev/null"

# --- Constraints (tech.yml: sta + bring-up configuration) ----------------------
set ::env(OUTPUT_CAP_LOAD) 33.5
set ::env(MAX_FANOUT_CONSTRAINT) 10
set ::env(CLOCK_UNCERTAINTY_CONSTRAINT) 0.25
set ::env(CLOCK_TRANSITION_CONSTRAINT) 0.15
set ::env(TIME_DERATING_CONSTRAINT) 5
set ::env(IO_DELAY_CONSTRAINT) 20

# --- Synthesis cells (tech.yml: sta.driving_cell, tie) --------------------------
set ::env(SYNTH_DRIVING_CELL) "INVX8H7R/Y"
set ::env(SYNTH_BUFFER_CELL) "BUFX4H7R/A/Y"
set ::env(SYNTH_TIEHI_CELL) "TIEHIH7R/Z"
set ::env(SYNTH_TIELO_CELL) "TIELOH7R/Z"

# Tri-state buffers exist in the library (TBUF*H7R) but were not part of the
# bring-up configuration; uncomment if needed.
# set ::env(TRISTATE_CELLS) [list "TBUF*H7R"]

# --- Fill / decap / tap cells (tech.yml: fills) ---------------------------------
# tech.yml gives regular expressions; LibreLane wants shell wildcards.
set ::env(DECAP_CELLS) [list "FILLCAP*H7R"]
set ::env(FILL_CELLS) [list "FILLER*H7R"]
set ::env(CELL_PAD_EXCLUDE) [list "FILLCAP*H7R" "TIEHIH7R" "TIELOH7R"]

# Welltap insertion (tech.yml: fills.tap + tap_distance).
set ::env(WELLTAP_CELL) "FILLTAPH7R"
set ::env(FP_TAPCELL_DIST) 15

# No endcap cells in this library; ENDCAP_CELL intentionally unset.
# see: https://github.com/openecos-projects/ecos-studio/issues/47

# Antenna diode: tech.yml fills.diode is empty -- this library has no diode
# cell. DIODE_CELL intentionally left unset; all diode insertion steps skip
# themselves when it is null.
# set ::env(DIODE_CELL) "..."

# --- Clock tree synthesis --------------------------------------------------------
set ::env(CTS_ROOT_BUFFER) "BUFX16H7R"
set ::env(CTS_CLK_BUFFERS) [list "BUFX4H7R" "BUFX8H7R" "BUFX16H7R"]

# --- Placement site (tech.yml: site) ----------------------------------------------
set ::env(PLACE_SITE) "core7"

# --- Tracks -----------------------------------------------------------------------
# Explicit track grid (pitch/offset from the tech LEF), copied from the
# bring-up configuration.
set ::env(FP_TRACKS_INFO) "$::env(PDK_ROOT)/$::env(PDK)/libs.tech/librelane/$::env(STD_CELL_LIBRARY)/tracks.info"

# directions (MET4 VERTICAL, MET5 HORIZONTAL).
set ::env(PDN_MULTILAYER) 1
set ::env(PDN_RAIL_LAYER) "MET1"
set ::env(PDN_RAIL_WIDTH) 0.16
set ::env(PDN_RAIL_OFFSET) 0.0
set ::env(PDN_VERTICAL_LAYER) "MET4"
set ::env(PDN_HORIZONTAL_LAYER) "MET5"
set ::env(PDN_VWIDTH) 1
set ::env(PDN_HWIDTH) 1
set ::env(PDN_VPITCH) 16
set ::env(PDN_HPITCH) 16
set ::env(PDN_VOFFSET) 0.5
set ::env(PDN_HOFFSET) 0.5
set ::env(PDN_VSPACING) 1.0
set ::env(PDN_HSPACING) 1.0

# PDN core ring (disabled; parameters kept from the bring-up configuration).
set ::env(PDN_CORE_RING) 0
set ::env(PDN_CORE_RING_VWIDTH) 3.1
set ::env(PDN_CORE_RING_HWIDTH) 3.1
set ::env(PDN_CORE_RING_VSPACING) 1.7
set ::env(PDN_CORE_RING_HSPACING) 1.7
set ::env(PDN_CORE_RING_VOFFSET) 12.45
set ::env(PDN_CORE_RING_HOFFSET) 12.45