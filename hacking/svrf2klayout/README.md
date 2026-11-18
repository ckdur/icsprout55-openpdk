# svrf2klayout — Calibre SVRF → KLayout DRC/LVS for ICS55

The KLayout decks `icsprout55/libs.tech/klayout/tech/ics55.drc` and `ics55.lvs`
are **generated** from the public Calibre decks in `icsprout55-pdk/pv/`.
Do not edit them by hand; change the translator or runtime here and regenerate.

## Regenerating

```bash
. 616cad                                   # Calibre on PATH (only needed to re-expand the TVF decks)
calibre -E ICsprout_CalDRC_expanded.svrf -drc ../../icsprout55-pdk/pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc
calibre -E ICsprout_CalLVS_expanded.svrf -lvs ../../icsprout55-pdk/pv/LVS/ICsprout_CalLVS_55LLULP1233_REV1_0_OS.lvs
calibre -E ICsprout_CalANT_expanded.svrf -drc ../../icsprout55-pdk/pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.ant
# (they stop with "cannot open *.gds" after writing the expanded file - that is fine)

python3 svrf2klayout.py     ICsprout_CalDRC_expanded.svrf ../../icsprout55/libs.tech/klayout/tech/ics55.drc
python3 svrf2klayout_lvs.py ICsprout_CalLVS_expanded.svrf ../../icsprout55/libs.tech/klayout/tech/ics55.lvs
python3 svrf2klayout.py     ICsprout_CalANT_expanded.svrf ../../icsprout55/libs.tech/klayout/tech/ics55_antenna.drc --name ICS55_ANTENNA

# antenna rules into the LibreLane tech LEFs (after generate_rcx_rules/itf2lef.py rewrote them)
L=../../icsprout55/libs.tech/librelane
python3 ant2lef.py ICsprout_CalANT_expanded.svrf $L/N551P6M_ecos.lef $L/N551P6M_ecos_max.lef $L/N551P6M_ecos_min.lef
# via array spacing (V1_S_2 .. V4_S_2, CT_S_1a) as cut layer ADJACENTCUTS spacing, same files
python3 cutspacing2lef.py ICsprout_CalDRC_expanded.svrf $L/N551P6M_ecos.lef $L/N551P6M_ecos_max.lef $L/N551P6M_ecos_min.lef
```

The same files are copied to `../icsprout55-pdk/klayout/tech/` (the PDK fork).

## Pieces

| file | purpose |
|---|---|
| `svrf_parse.py` | SVRF parser (layers, derived layers, rule checks, `#IFDEF`, macros, CONNECT, DEVICE, ATTACH) |
| `svrf2klayout.py` / `svrf_runtime.rb` | DRC code generator and the Ruby runtime implementing each SVRF operation |
| `svrf2klayout_lvs.py` / `svrf_lvs_runtime.rb` | LVS generator, generic seed/pin device extractor, CDL reader, split-gate reduction |
| `compare.py`, `microtest.py`, `unmatched.py`, `show_rule.py`, `dbgrun.sh` | run Calibre and KLayout on one layout and compare rule by rule |
| `gen_critical.py`, `crit_report.py` | generate pass/fail critical shapes per rule and classify the result |
| `mkrow.py`, `mkrows.py`, `lvs_percell.sh`, `calibre_lvs.sh`, `runlvs.sh`, `v2cdl.py`, `swapcells.py` | LVS test vehicles and runners |
| `tests/` | micro-test inputs, critical-shape layout description, result tables |

KLayout is run through docker (`kl.sh`); set `KLAYOUT_BIN` for a native binary in `klayout_run.py`.

### Lazy operands

Derived layers inside a rule are lazy (`SvScope`), but the operands of one operation were
evaluated eagerly. For operations that are empty when one operand is empty, the generator passes
the operands as `SvLazy` (`sv_bool_lz`, `sv_esel_lz`, `sv_check_lz`), and the runtime looks at
one operand first and skips the other when the first is empty:

- `NOT` / `AND`: the first operand.
- Edge selections (`COIN`, `TOUCH`, `INSIDE`, `WITH EDGE` ...): either operand. The second one only
  without `NOT`, without a count and not for `OUTSIDE EDGE`.
- Two layer `EXT` / `INT` / `ENC`: either operand, not with `OUTSIDE ALSO` or `CONNECTED`.

The operand to look at first is one that is computed already. If neither is, the generator
decides with a static cost estimate (`Gen.cost`): checks are expensive, and through a lazy
operation the cost is that of its cheapest short-circuiting operand. Example: `M1DUM_S_7` (all
metals) computes a 0.6 um spacing on all of M1 but only uses it next to M1 >= 1.5 um wide,
which the standard cells do not have. It took 131 of 177 s on 100 abutted 7-track cells and now
takes nothing. The results are identical marker by marker (abutted and grid std cells, IO
library, antenna vehicle).

## Running the decks

DRC (`klayout -b -r ics55.drc -rd ...`): `input`, `topcell`, `report`, `thr`/`threads`,
`flat=1`, `select=<regex>`, `unselect=<regex>`, `densityRules=False`, `dump=LAYER[,RULE:LAYER]`,
`jobs=N`, `sv_verbose_flag=1` (time per rule and per slow layer), `log=<file>`, and any deck switch,
e.g. `-rd OPEN_RECOMMENDED_ON=YES`.

`jobs=N` (as the IHP sg13g2 runner does with its rule tables): the parent reads no layout, splits the
selected rules into N groups (the density rules together, the others round-robin in deck order) and
runs each in its own KLayout process (`-rd rules_file=...`, the threads divided among them), then
merges the reports. Every process reads the layout and derives its own layers, so memory grows with
N. Identical to the single-process run (filled `demo_counter`, all 712 rules vs Calibre).

Chip-level runtime (WP5, filled `demo_chip`):
* Density windows: the merged layer goes into a box tree and each window only clips the polygons it
  overlaps; the window densities are cached per layer and window set (the `_min` / `_max` rules).
  The former `(layer & window).area` per window scanned the whole layer ~1000 times per rule: all
  density rules ~1 h -> ~15 min, results identical (the M3-M5 `_D_3` gradient differences to
  Calibre are older, see the known approximations).
* `MnDUM_S_7` / `T4M2DUM_S_7`: an exact rewrite of the rule text before parsing (`rewrite_svrf` in
  `svrf2klayout.py`). `X1 = EXT MnALL < 0.6 ...` measured every pair of neighbouring dummies (M1
  alone 443 s flat, M2 did not finish in 10 min); X3 is now taken from the pairs with a wide
  polygon and the later uses of X1 from the polygons within 2.2 um of X4_near / X4_far. Checked on
  a fill with ~10000 S_7 violations: Calibre with the original and with the rewritten rules and
  the KLayout deck give the same markers.

LVS (`klayout -b -r ics55.lvs -rd ...`): `input`, `schematic`, `report`, `target_netlist`,
`topcell`, `run_mode=deep|flat`, `hier=1` (keep hierarchy; default flattens like Calibre),
`no_compare=1`, `schematic_out=<file>` (reduced schematic as compared, for debugging).
Prints `INFO : Congratulations! Netlists match.` or `ERROR : Netlists don't match`.

* `tapless=true` — library regression of tap-less cells: compares hierarchically (each cell is its
  own circuit pair) and ties the well nets of every cell to `tapless_power` (VDD) /
  `tapless_ground` (VSS). Labelled nets of a cell become pins even if the parent leaves them open.
* `implicit_nets="VDD VSS CELL:LABEL"` — joins nets carrying the same label by name
  (KLayout `connect_implicit`, the counterpart of Calibre `VIRTUAL CONNECT NAME`), e.g. the supply
  rails of a standalone IO cell.

## Regression suite

`icsprout55/libs.tech/klayout/tech/testing/run_regression.py` runs the installed decks on the
standard-cell and IO libraries and compares with `testing/golden/`. It needs `klayout` and its
python module; `./regress.sh [--tests a,b] [--update]` runs it inside the docker image.

## Antenna deck (`ics55_antenna.drc`)

The vendor antenna runset (`.ant`, 6 metals / 1 top metal / RDL 1.595 um) uses
`DRC INCREMENTAL CONNECT YES` and `NET AREA RATIO ... [expression] ACCUMULATE <layer>`.
The runtime (`sv_nar`, `sv_net_area`, `sv_stage`) implements it as Calibre does, settled by
running both tools on the test vehicle `tests/antenna/` (`mk_antenna_test.py` builds it,
`run_calibre.py` runs Calibre, `compare.py` compares with the KLayout report):

* every check sees only the CONNECT statements above it (the connectivity of its stage is
  set up with `clear_connections`; the deck therefore runs flat);
* the bracketed expression is evaluated per net on the areas (um2) / perimeters (um) of the
  listed layers; `!!AREA(X)` is 1 when the net has X. Nets without gate area are skipped;
* plain checks report the merged polygons of the first layer on the failing nets;
* `ACCUMULATE` works per gate (last layer): the value of a gate is the value of its net at
  this level plus its value in the `ACCUMULATE` layer (the raw ratios of the lower levels,
  `AC<n>`), so lower metal keeps counting, while the diode allowance of the expression is
  applied once; the failing gates are reported.
* the connectivity layers are broken into pieces of <= 512 points first (`sv_break_big`, flat
  runs; `-rd break_points=<n>`): an abutted IO pad ring merges its guard rings into one ACT /
  SD polygon of ~43000 points and ~10000 holes, and the net extraction against ~500000
  contacts did not finish in hours (5 s broken). Per-net areas do not change; perimeters
  (only PO and RDL are used) would, but those polygons stay far below the limit. The notched
  test vehicle gives identical markers with `break_points=32` and without breaking.

All 23 rules that fire on the 15 cases of the test vehicle (poly area and perimeter, contacts,
M1-T4M2 with / without diode, cumulative M2, per gate accumulation, single and cumulative vias,
1.8 V gates, RV and RDL) report the same cases as Calibre; `demo_counter` and the H7CR
library have no findings in either tool. The regression (`testing/run_regression.py
--tests ant_vehicle,ant_stdcell_H7CR_M2`) checks the vehicle against the Calibre result.

### LEF antenna rules (`ant2lef.py`)

The same checks as LEF statements for OpenROAD (check_antennas / repair_antennas), per layer
and gate oxide (GATE -> OXIDE1, GATE18 -> OXIDE2): a check `> v` with the diode allowance
`a*A + b` becomes `ANTENNA[CUM]AREARATIO v` and `ANTENNA[CUM]DIFFAREARATIO PWL ((0 v+b) (100
v+b+100a))`; accumulated metal and via checks are the CUM forms, single via / CT / RV the plain
ones, the RDL perimeter check `ANTENNASIDEAREARATIO` with the runset's RDL thickness. POLY (a
masterslice layer) and the GATE1825 check of RV are left to the KLayout deck.

### LEF via array spacing (`cutspacing2lef.py`)

The DRC deck checks cuts in an array with a larger spacing than single cuts (`V1_S_2` ..
`V4_S_2`: 0.13 between vias closer than 0.14 to each other; `CT_S_1a`: 0.14 / 0.15). The
`SIZE BY a OVERUNDER` / `SIZE BY b UNDEROVER` / `INSIDE` / `EXT < s` form of these rules becomes
`SPACING s ADJACENTCUTS 3 WITHIN 2a` on the cut layer. Without it pdngen builds the PDN via
arrays with the single cut spacing 0.11 (it ignores the VIARULE GENERATE pitch), and every
array of 3 x 3 cuts or more fails `V*_S_2` (50 markers on `demo_counter`, 0 with the rule).
Recommended rules (`T4V2_S_2`) are not written.

## Verification status (against Calibre 2012.2)

DRC
* Critical shapes (`tests/results/drc_critical_report.md`): 346 rules have generated pass/fail tiles
  (recommended rules enabled). 255 show the clean pattern in Calibre (fail tile triggers, pass tile
  does not) and KLayout is identical; 91 more agree with Calibre on every tile; 0 disagree.
  All 368 rules that fire on that layout match Calibre.
* Real layouts (`tests/results/drc_real_layout_diffs.txt`): H7CR library 49 of 60 firing rules match,
  IO library 68 of 71. The others differ by a few markers (mostly 45-degree geometry).
* Known approximations: DENSITY windows (BACKUP/GRADIENT), `DRAWN ACUTE/OFFGRID` (not supported),
  projection enclosure against diagonal edges, WITH WIDTH on non-orthogonal shapes.
* Seal ring (`ics55_sealring.py`, 300 x 300 um test die): identical to Calibre on all 712 rules,
  SRCK_* included (a 2.1 um outer ring is caught by SRCK_4 / SRCK_5 in both tools).
* Runtime fixes of 2026-11-17, each settled with Calibre on `tests/micro`:
  - `INTERACT` / `TOUCH` (no count): a contact in a single point (corner to corner, vertex on an
    edge) is no interaction in Calibre (`exp_pttouch`; NP_EN_3 was missed on XNOR2X0P5H7R, whose
    poly meets a PP notch corner and was taken for a poly crossing NP / PP).
  - `HOLES ... INNER`: holes that contain no other hole (`exp_holes`; was all holes, so SRCK_6 took
    the outer seal ring for the inner one). The micro comparison matches markers by overlapping
    boxes and had hidden this: nested rings overlap.
  - `ANGLED` constraint of dimensional checks (was ignored; SRCK_4 / 5 / 8 / 10 measured the joints of
    straight and 45 degree edges).
  - `WITH EDGE`: coincident edge parts extended 1 dbu into the polygon instead of the edge centres,
    whose quarter points on 45 degree edges rounded off the polygon (`exp_srck3`).

LVS
* Per-cell runs (tap + cell + tap) of all 784 H7CR cells: same verdict as Calibre on 777
  (`tests/results/lvs_h7cr_percell.txt`); the 7 others are empty filler cells (Calibre: "nothing in layout").
* 12 IO cells: same verdict on all; total extracted MOS width per model identical to Calibre.
* Fault injection (short, swapped supplies, swapped pins, missing cell, wrong width, wrong cell):
  rejected by both tools.
* Not exercised (no layouts available): BJT, MOM, varactor, diffusion/well/metal resistors,
  native/2.5 V/SRAM MOS. ERC checks and WPE/LOD properties of the Calibre deck are not translated.

## Notes on the demo data

* `demo_counter` was streamed with the MET1-pin cell GDS, but P&R used `*_ecos.lef` (pins on MET2):
  the signal pins are open in `counter.gds`. The matching cells are in `ics55_LLSC_H7CR_M2.gds`
  (`swapcells.py` re-streams a design with them).
* The counter has no tap cells, so its wells float; both Calibre and KLayout LVS report that.
