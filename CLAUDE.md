# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An OpenPDK-style packaging of the ICsprout 55nm PDK (`icsprout55`, "ICsprout 55LLULP 1P6M") so it can be used with the
open LibreLane flow instead of the ECOS toolchain. The vendor data comes from the `icsprout55-pdk` git submodule;
this repo adds the missing open-tool views (KLayout DRC/LVS, Magic, netgen, LibreLane config, ngspice models)
and the scripts used to derive them.

## Environment

All EDA tools (KLayout 0.30, OpenROAD, LibreLane 3.0, Magic, ngspice) are used from the container
`factory.symbioticeda.com/asic-all:dev`. Typical invocation from the repo root:

```bash
docker run --rm -v "$PWD":/work -w /work factory.symbioticeda.com/asic-all:dev bash -lc '<command>'
```

## Commands

```bash
bash ./install.sh                     # init submodule, download vendor IP, populate icsprout55/libs.ref
export PDK_ROOT=$(pwd) PDK=icsprout55

# LibreLane with the private 9-track standard cells instead of the default 7-track library
librelane --pdk icsprout55 --scl ICsprout55_9TSVT_basic --manual-pdk config.json

# KLayout DRC / LVS regression on the std cells and IO (≈1 h, run in the container; hacking/svrf2klayout/regress.sh wraps it)
cd icsprout55/libs.tech/klayout/tech/testing
python3 run_regression.py                         # all testcases, exit 1 on any change vs golden/
python3 run_regression.py --tests drc_stdcell_H7CR,lvs_io   # subset
python3 run_regression.py --tests ant_vehicle,ant_stdcell_H7CR_M2   # antenna deck (seconds)
python3 run_regression.py --update                # accept current results as the new golden files

# Single DRC / LVS run
klayout -b -r icsprout55/libs.tech/klayout/tech/ics55.drc -rd input=<gds> [-rd topcell=X] -rd report=<lyrdb>
klayout -b -r icsprout55/libs.tech/klayout/tech/ics55.lvs -rd input=<gds> -rd schematic=<cdl> [-rd topcell=X] \
        [-rd report=<lvsdb>] [-rd tapless=true] [-rd implicit_nets="VDDIO VSSIO"]

# LibreLane demos (demo_chip uses demo_counter's final views as a macro, run counter first)
cd demo_counter && bash run.sh
cd demo_chip && bash run.sh

# Antenna check / repair (OpenROAD vs KLayout): bash run.sh [norepair]
cd demo_antenna && bash run.sh

# ngspice model demos
cd demo_sim && ./run.sh
```

`icsprout55/libs.ref` is gitignored and only exists after `install.sh`; the regression and demos need it.

## Relationship to icsprout55-pdk

`icsprout55-pdk` is both the vendor data submodule here and, as a fork, the repository that ships the PDK. The open
tool views are kept in sync between the two: `icsprout55/libs.tech/<tool>` here is `<tool>/` there, `hacking/
{cdl_convert,cdl_to_spice,calibre_layers_to_klayout_drc,layermap*}.py` and `hacking/layermap` are `scripts/`, and the
three demos are copied verbatim. The fork's `make openpdk` does there what `install.sh` does here (including the
private 9-track libraries) and installs into `icsprout55/`, so `PDK_ROOT=<fork> PDK=icsprout55` works the same way.
The KLayout DRC/LVS regression (`libs.tech/klayout/tech/testing`) stays in this repository only.

## Architecture

- `icsprout55/libs.tech/librelane/config.tcl` — LibreLane PDK config (std cell lib `ics55_LLSC_H7C{R,H,L}`, IO lib
  `ICsprout_55LLULP1233_IO_251013`). Important pairing: `CELL_LEFS` uses the `_ecos` cell LEF whose signal pins are on
  MET2 (installed as `_ecos_openpdk.lef`: plus the per-pin antenna data from Magic, `hacking/magic/lef_antenna.py`
  and `libs.tech/librelane/<lib>/antenna.pins`), so `CELL_GDS` must be the matching `*_M2.gds` (the plain GDS only has MET1 pins → every routed pin is open).
  The cell LEF/GDS pair and the liberty file names are picked per standard cell family (`regexp` on
  `STD_CELL_LIBRARY`); the technology LEF (`N551P6M_ecos.lef`) is the same for both families.
- Two standard cell families are supported:
  - `ics55_LLSC_H7C{R,H,L}` — 7-track, public, from the `icsprout55-pdk` submodule. Default (`H7CR`). Shared
    configuration in `libs.tech/librelane/ics55_LLSC_H7C_common.tcl`, sourced by each library's `config.tcl`;
    the three Vt flavours differ only in the cell name suffix (`H7R`/`H7H`/`H7L`). The installed GDS and cell
    LEFs are the DRC fixed ones from `stdcell_fixed/` (made by `hacking/stdcell_fix/make_fixed.py`, see its
    README; liberty and CDL stay the vendor ones): 606 of 785 cells per library are DRC clean (Calibre checked), the
    other 179 are unusable (176 keep the vendor layout; XNOR2X0P5/X0P7/X1 have a Calibre-only NP_EN_3).
    `synth_exclude.cells` / `pnr_exclude.cells` (209) are those 179 plus the cells whose layout does not match
    their CDL (the 18 vendor mismatches and the 14 with a swapped series stack, found by per-cell LVS of every
    usable cell). Async reset flops map to the set flops with `QN` (no `DFFR*` is usable),
    `latch_map.v` builds the negative enable reset latches from `LATHR*` / `LATHSR*`, `DECAP_CELLS` is
    `FILLCAP4` only. `FILL_CELLS` = `FILLDENS{4..64}` (density filler cells: floating well-type AA + field
    poly, no devices, `hacking/stdcell_fix/density_fill.py`, own GDS / LEF / CDL added to the `CELL_*` lists)
    plus `FILLER1` / `FILLER2` for gaps below 4 sites (OpenROAD fills largest first, so the bigger plain
    fillers are left out): dummy fill cannot enter the rows, the AA / PO density of the core comes from them.
    No vendor endcap cells: the rows are closed with the plain fillers, `ENDCAP_CELL` =
    `FILLER1` at the row ends and `ENDCAP_HORIZONTAL_CELLS` (the `FILLER*` family) filling the top / bottom row
    of every row block, which needs the plugin step `ICS55.TapEndcapInsertion` (all demos substitute it).
    NP / PP of the cells extend past the cell edge and are only complete with neighbours on all four sides;
    `testing/rowend_check.py` checks every cell at a row end / outer row (clean with both, 12410 markers
    without).
  - `ICsprout55_9T{S,H,L}VT_basic` — 9-track, **private**, installed by `install.sh` from
    `../pdk/ICsprout_55LLULP1225_STD_0818` when that directory exists (`PRIVATE_STD_ROOT=` to point elsewhere,
    `PRIVATE_STD_LIBERTY=all` for every NLDM corner instead of the three in `STA_CORNERS`; the vendor `lib/` is
    ~15 GB per library, so only the used corners are installed). Site `SC9T_site` (0.2 × 1.8, same geometry as the
    tech LEF's `core9`), signal pins on MET1 so no `_ecos` / `_M2` split, and every cell carries the well bias pins
    `VNW` / `VPW` besides the rails. Shared configuration in
    `libs.tech/librelane/ICsprout55_SC9T_common.tcl`, sourced by each library's `config.tcl`; the three Vt flavours
    have the same 719 cells and differ only in the cell name suffix.
- `icsprout55/libs.tech/librelane/librelane_plugin_ics55/` — LibreLane plugin (discovered via `PYTHONPATH`, set in the
  demo `run.sh`). Provides step `ICS55.KLayoutLVS`, because upstream `KLayout.LVS` only runs for IHP PDKs. Either in
  place of Netgen (`"-Netgen.LVS": OpenROAD.WriteCDL` + `Netgen.LVS: ICS55.KLayoutLVS`) or next to it
  (`"+Netgen.LVS": ICS55.KLayoutLVS`, demo_counter): it then adds its error count to Netgen's, so one Checker.LVS
  covers both, and keeps the Magic extracted SPICE view. Step `ICS55.TapEndcapInsertion` (substitutes
  `OpenROAD.TapEndcapInsertion`): `place_endcaps` with `ENDCAP_CELL` at the row ends and
  `ENDCAP_HORIZONTAL_CELLS` in the top / bottom row of every row block, then `place_tapcells`
  (`scripts/tapcell_boundary.tcl`); without `ENDCAP_HORIZONTAL_CELLS` it is the upstream step.
  `scripts/pad_supply_terminals.tcl` (`ics55_pad_supply_terminals`, called from a chip's `PDN_CFG`, see
  `demo_chip/pdn_cfg.tcl`): BTerms for `VDD_NETS` / `GND_NETS` on the bond pads of the power pads. The Chip flow
  gives only netlist ports (`IOVDD`, `IOVSS`) a bond pad terminal; without one PSM has no source on VDD / VSS
  (`PSM-0025`, counted by `Checker.PowerGridViolations`). No `VSRC_LOC_FILES` needed.
- WP4 (Chip flow): `KLAYOUT_FILLER_SCRIPT` = `libs.tech/klayout/tech/ics55_fill.py` (dummy AA / PO / MET1-5 /
  T4M2 per the AADUM / PODUM / MnDUM / T4M2DUM rules; IO cells only get T4M2 fill), `KLAYOUT_DENSITY_RUNSET` =
  `ics55.drc` with `select _D_[0-9]` (the DRC step runs with `densityRules False`; the former `densityRules 0`
  had no effect), `KLAYOUT_SEALRING_SCRIPT` = `ics55_sealring.py` (DRM 3.3.46 / SRCK_*, drawn on the die edge,
  `PAD_EDGE_SPACING 20`; the deck reads SRINGBLK from 354;13, the DRM table says 354;12, both drawn). All three
  verified with Calibre (fill on demo_chip, filler cells next to every usable cell, ring on a test die: KLayout
  and Calibre identical on all 712 rules). LibreLane's Tcl config only sees `set` / `dict set` on `::env`,
  never `lappend`.
- WP5 (KLayout runtime on chips): density windows through a box tree with a cache, an exact rewrite of the
  `*DUM_S_7` rules (`rewrite_svrf`), and `-rd jobs=N` (rules in N KLayout processes, reports merged, IHP
  style; LibreLane uses `jobs 4`, every process reads the layout). All verified identical against Calibre /
  the single-process run, details in `hacking/svrf2klayout/README.md`.
- KLayout DRC in LibreLane runs the deck flat (`KLAYOUT_DRC_DEFINES flat 1`), the mode it is verified in against
  Calibre (`compare.py` forces `flat=1`). Flat is single threaded (KLayout only uses `threads` when tiled):
  3 h 34 min on `demo_chip`. Deep mode used to report `LU_S_2_*` inside placed cells (`BUFX10/16H7R`) and lose
  some enclosure / spacing markers: KLayout 0.30 `Edges#inside_part` / `#outside_part` drop child cell edges that
  are covered by a parent cell polygon only (`hacking/svrf2klayout/tests/deep_edge_parts.rb`). The runtime uses
  the equivalent boolean operators in deep mode (`sv_ein` / `sv_eout`); deep and flat now agree on
  `demo_counter` and the library goldens are deep results that match flat. The antenna deck runs flat as well
  (`KLAYOUT_ANTENNA_DEFINES flat 1`): the guard rings of the abutted pad ring merge into one polygon of ~43000
  points, which made the net extraction of the first stage take hours (deep too); the runtime breaks polygons over
  512 points before the connectivity (`sv_break_big`, flat only; results identical, checked on the antenna test
  layout with notched plates and `-rd break_points=32`).
- `icsprout55/libs.tech/magic/ics55.tech` and `libs.tech/netgen/ics55_setup.tcl` — GENERATED by
  `hacking/magic/gen_magic_tech.py` (layer numbers and device recognition from the Calibre LVS runset, R/C from the ITF
  and the WP1 FasterCap solutions, DRC rules translated from the Calibre DRC deck by `svrf2magic_drc.py`). Don't
  hand-edit; `hacking/magic/README.md` has the type model, the approximations and the regression results.
  - Devices: core svt/lvt/hvt/native MOS, 3.3 V TGOX MOS, junction diodes, poly resistors (no BJT/MOM/varactor/SRAM).
  - Magic only reads GDS layers <= 255: markers above (NODRC, SUBCKTLVS, PSUB, CHIPBLK, WELTXT/SUBTXT, ...) are read
    as `(L-256, D+100)` from a GDS converted with `hacking/magic/magic_gds.py`, ignored otherwise, never written.
  - DRC: ~160 of the 711 Calibre rules (native rules + CIF rules on derived layers, 255 CIF layers max per style);
    coverage per rule in `hacking/magic/drc_coverage.txt`. KLayout stays signoff.
  - Netgen compares against `libs.ref/<lib>/spice/<lib>_lvs.spice` (`CELL_SPICE_MODELS`), made by
    `hacking/magic/lvs_netlist.py` in install.sh: parametrised helper subckts inlined, CDL device stubs dropped,
    split gates reduced (`reduce_split_gates.py`).
  - Library regressions: `hacking/magic/testing/lvs_lib.py` (Magic extraction + netgen per cell) and `drc_lib.py`
    (Magic DRC vs. the KLayout goldens).
- `icsprout55/libs.tech/klayout/tech/` — KLayout DRC (`ics55.drc`) and LVS (`ics55.lvs`) decks. Both are GENERATED
  from the vendor Calibre runsets in `icsprout55-pdk/pv/{DRC,LVS}/` by `hacking/svrf2klayout/` (SVRF parser, code
  generators and the Ruby runtimes that get embedded in the decks). Don't hand-edit the decks: change the translator
  or runtime and regenerate (`hacking/svrf2klayout/README.md` has the commands, deck options and the verification
  status against Calibre).
  - Rule names and values are the Calibre ones, nothing is relaxed. The regression goldens therefore carry what
    Calibre also reports on the libraries: latch-up (`LU_S_2_*`, the wrapped cells have no taps), density minima and,
    for the 7-track libraries, the cell-intrinsic contact/poly/metal findings.
  - Metal stack is fixed to the Calibre default: 6 metals, 1 top metal (M1–M5, T4V2, T4M2).
  - LVS flattens by default like Calibre; `tapless=true` compares per cell and ties the wells to the rails,
    `implicit_nets=` joins same-named labels (Calibre `VIRTUAL CONNECT NAME`).
  - Antenna (WP2): the tech LEFs carry the runset's antenna rules (`hacking/svrf2klayout/ant2lef.py`, re-run after
    `itf2lef.py`); 7-track `DIODE_CELL` = `ANT2H7*` with a generated liberty (`hacking/antenna_liberty.py`,
    `<lib>_antenna.lib` added to LIB); `demo_antenna` checks OpenROAD vs KLayout with and without repair.
  - `ics55_antenna.drc`: the vendor antenna runset (`pv/DRC/*.ant`) through the same generator (incremental
    connectivity, per gate `ACCUMULATE`, diode allowance; runs flat). LibreLane `KLAYOUT_ANTENNA_RUNSET`.
    Semantics settled on `hacking/svrf2klayout/tests/antenna` (identical to Calibre on all 23 firing rules).
  - Via array spacing (`V1_S_2`..`V4_S_2`, `CT_S_1a`): `hacking/svrf2klayout/cutspacing2lef.py` writes them into the
    tech LEFs as cut layer `SPACING s ADJACENTCUTS 3 WITHIN d` (also re-run after `itf2lef.py`); pdngen honours it
    (4 x 4 arrays at 0.13) but ignores the VIARULE GENERATE pitch.
  - `rule_decks/` holds the earlier hand translation; it is no longer included by the decks.
- `testing/` — regression: `wrap_lib.py`/`lvs_wrap.py` place a whole library under a top cell `ALL` (DRC: abutted,
  alternately mirrored rows like a placed design, FILLER4 at the row ends and a filler row below / above; LVS: grid +
  matching `.SUBCKT ALL`); `check_cells.py` runs the same DRC (+ LVS with `--cdl`) on a few cells in seconds, IO LVS runs per cell. Results are compared against
  `golden/*.json`; known remaining findings are explained in `testing/README.md`.
- `hacking/` — reverse-engineering and generator scripts that feed the PDK:
  - `ICSIOA_N55_3P3_1P6M1TM_openpdk.lef` is the vendor IO `_ecos` LEF with the pad terminals moved to RDL;
    `PAD_LEFS` points at it (installed next to the vendor LEFs, not over them). `io_lef_openpdk.py` (in place,
    idempotent) applies two OpenROAD fixes to it: the MET5 shapes of the signal pins become MET5 OBS (OpenROAD 26Q4
    detailed routing builds access points on pin shapes above `RT_MAX_LAYER` and aborts, `initMazeIdx_ap no idx`),
    and the 49 um core edge supply stubs of the power pads on MET4 / MET5 are split into overlapping 4 um
    rectangles (pdngen `-connect_to_pads` makes one ring-wide strap per pin rectangle and drops it when a stripe
    of the other supply crosses it, which left the VDD pad of `demo_chip` unconnected).
  - `cdl_convert.py` produces the installed (LVS-ready) CDLs from the vendor CDLs (strips CDL `/` and `$` annotations,
    dedups helper subckts, declares `nw/pw/nl/pl` params, prefixes private helper subckts per library so std cell
    `NAND2` and IO `nand2` don't collide; `--lef` adds empty subckts for physical-only IO cells needed by
    OpenROAD `write_cdl`). `install.sh` runs it instead of copying.
  - `cdl_to_spice.py` makes the ngspice netlists; `layermap*_to_lyp.py` generate the `.lyp` from `hacking/layermap`.
  - `NOTES.md` documents how RCX parameters were recovered from the ECOS binaries.
  - `stdcell_fix/` fixes the DRC violations of the 7-track cells: polygon legalization per layer against the
    Calibre rules (`legalize.py`, up to three sites of growth), NP/PP boundary solver (`implant.py`), DRC/LVS
    feedback rounds and the Vt variants (`make_fixed.py`, ~1.5 h with 16 jobs; outputs are GBs, use `/opt/ext` or
    the home folder, not `/tmp`). The result is committed gzipped in `stdcell_fixed/<lib>/{gds,lef}` with
    `unusable.cells` and `report.json`; `install.sh` unpacks it over libs.ref. Liberty files are not regenerated.
- `icsprout55/libs.tech/ngspice` / `hspice` — device models (ngspice copies adapted from hspice).
- `generate_rcx_rules/` — OpenRCX rules from the vendor StarRC ITF (`../pdk/.../StarRC/ITF`, same data as
  `hacking/decrypted_output/kItf*`): `itf2rcx.py` field solves every OpenRCX context with FasterCap 2D
  (drawn dimensions × the ITF 0.9 half node shrink) into `libs.tech/librelane/rcx/ics55_{typ,rcworst,rcbest}.rules`
  (`nom_*` / `max_*` / `min_*`) and `rcx/layers_rc.tcl`; `itf2lef.py` writes the per corner tech LEFs
  `N551P6M_ecos{,_max,_min}.lef` (resistance, since LibreLane extracts with `-lef_res`). Solutions are kept in
  `solutions/*.csv` (`--from-csv` regenerates without solving, a full solve is ~4 h per corner).
  Method and validation in `generate_rcx_rules/README.md`. The old `Makefile` flow is superseded.

## Known gaps

Open work is tracked in the SymbioticEDA Plane tracker (bugs.ckdur.dev, workspace `symbioticeda`, label
`icsprout55`, titles `[ICS55] ...`; SYMBI-47 is the umbrella ticket). Keep it in sync with this list.

- Full-chip KLayout LVS (`demo_chip`) is disabled: layer derivation is far too slow on the filled chip.
- With the container's LibreLane 3.0.16, `Odb.CustomIOPlacement` makes the IO pins span the whole die (default pin
  length from the layer min AREA comes out ~10^6 too long when `IO_PIN_H_LENGTH` / `IO_PIN_V_LENGTH` are unset):
  `OpenROAD.IRDropReport` then fails with `PSM-0069` and `KLayout.Render` writes a zero-height image.
  `demo_counter` sets both lengths to 1 um and completes (2026-11-13, Netgen and KLayout LVS clean).
- RCX: Cbest / Cworst ITF corners are not generated (no STA corner uses them).
- `demo_chip` with OpenROAD 26Q4: the detailed routing crash (pad MET5 pins), the unconnected VDD pad and
  `PSM-0025` are fixed (`io_lef_openpdk.py`, `pad_supply_terminals.tcl`; PDN checked alone: both nets connected,
  no unconnected shapes). Full run 2026-11-15 (`runs/debug_ics`): route DRC 0, power grid 0, OpenROAD and KLayout
  antenna 0, setup / hold WS 12.0 / 0.06 ns, IR drop worst 39 mV, Netgen LVS clean, Magic DRC 21 (one sliver on
  M2-M4 where the pad ring corner meets the next filler, abstract views), KLayout DRC 8422: 6990 in the IO pads
  (vendor layout, identical per instance to the `drc_io` golden / a lone pad; RV_W_1 splits per pad seam on the
  ring), 1379 density minima (no fill), 49 M5 at the VDD3 / VSS3 pad connections (pdngen cuts the pad strap 0.1um
  from the core stripes, pieces 12.8um wide: M5_S_2/S_3/W_1b; the tech LEF has no wide metal SPACINGTABLE),
  2 PO_S_9 between rows (SYMBI-29), 2 recommended rules (NW1_R_1 untapped top filler row, RV_R_1). The core has no
  other marker. `Magic.StreamOut` is disabled in `demo_chip`: Magic
  takes the macro size from the PR boundary in the GDS, which is on layer 351/12, and reads no layer above 255.
- KLayout DRC on the demos reports vendor-intrinsic findings (IO pads, see above) and the density minima, so the
  demo configs set `ERROR_ON_KLAYOUT_DRC: false`; LVS errors still fail the flow. demo_counter (2026-11-15):
  KLayout DRC 12, Magic DRC 1094 (not classified).
- 18 std cells per Vt library differ between vendor CDL and layout (listed in `testing/README.md`). Per cell, 15
  more have a series stack in another order than the CDL (NAND2X0P5 ...; KLayout per cell, netgen and Calibre
  agree, the KLayout library-wrapper regression misses them, list in `hacking/magic/README.md`). All usable ones
  are excluded since 2026-11-17 (AOI22X4 already was).
- Magic: GDS layers > 255 need `hacking/magic/magic_gds.py`; netgen has no split-gate reduction, so LibreLane LVS with
  `MAGIC_EXT_USE_GDS: true` fails on cells with split stacks (the default abstract extraction is fine); Magic DRC
  covers ~160 Calibre rules, no RECTANGLE ENCLOSURE via rules, no antenna, no density.
- The standard cell libraries have no endcap cells (7-track: fillers instead, see Architecture; a design that does
  not substitute `ICS55.TapEndcapInsertion` only gets the row end `FILLER1`, and the cells in its top / bottom
  rows report `NP_EN_3` / `PP_EN_3`; 9-track: not checked). OpenROAD `tapcell` inserts no taps in rows shorter
  than `FP_TAPCELL_DIST` (15 µm), so tiny dies need absolute sizing.
- No decap insertion for the 9-track libraries (`DECAP_CELLS` empty). OpenROAD fill insertion runs after detailed
  routing and is not routing aware, and the `FILLCAP*` / `GFILL*` cells have their internal nodes on MET1, so they
  short to whatever MET1 the router already put in the gap. The plain `FILL*` cells have no devices and no MET1
  outside the rails. The same hazard exists for `FILLCAP4H7R` in the 7-track libraries, it just does not trigger on
  the demos.
- 7-track DRC fix (`stdcell_fixed/`): 179 cells per library still fail DRC and are excluded, among them every
  asynchronous reset / set+reset flop, the scan flops, most XOR / XNOR and `FILLCAP8/16/32`. Only left / right
  abutment is checked (`testing/abut_check.py`); poly ends of vertically adjacent rows can still meet `PO_S_9`
  (SYMBI-29). The per pin antenna areas (`antenna.pins`) were extracted from the vendor layout.
