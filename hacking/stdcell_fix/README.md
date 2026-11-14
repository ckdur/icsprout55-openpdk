# 7-track standard cell DRC fix

The vendor 7-track libraries `ics55_LLSC_H7C{R,H,L}` violate the Calibre rules of the PDK they come with
(contact to gate 0.050 instead of `CT_S_4` 0.055, M1 enclosure of contacts, 45 degree M1, small pins, ...;
see `icsprout55/libs.tech/klayout/tech/testing/README.md`). These scripts move the cell geometry until the
KLayout deck (the Calibre rules, unrelaxed) is clean, and list the cells for which that does not work.
ICsprout agreed to the cells being modified.

| Script | |
|---|---|
| `legalize.py` | the migration of one cell (below) |
| `implant.py` | the NP / PP boundary of a legalized cell re-solved as a step line (below) |
| `fix_filltap.py` | hand fix of the tap cell `FILLTAPH7R` |
| `markers.py` | DRC markers of a check run, per cell in cell coordinates (feedback rounds) |
| `fix_lib.py` | `legalize.py` + `implant.py` on every cell of a library, both GDS views together |
| `classify.py` | per cell DRC / LVS result of a fixed library (`check_cells.py` run dir) |
| `derive_vt.py` | H7CH / H7CL from the fixed H7CR (same layout except the Vt layers, which are copies of the fixed NP / PP, as they are of the vendor NP / PP) |
| `lef_from_gds.py` | cell LEF geometry (SIZE, pins, OBS) from a GDS, the vendor LEF as template |
| `make_fixed.py` | the whole flow: fix, verify, Vt variants, LEFs, list of unusable cells |

```bash
# in the tool container, from the repository root, after install.sh
python3 hacking/stdcell_fix/make_fixed.py <out_dir>
```

The liberty files are not regenerated (cells that grew keep their liberty area, timing is that of the
original layout: the transistors are unchanged, the wiring moved by a few nm).

## Method

`legalize.py` is a 1D layout migration, alternating x and y passes.

- The cell is flattened into merged polygons per layer. 45 degree M1 (342 cells) is replaced first: a 45
  degree wire piece (a band, two parallel diagonal edges one wire width apart) becomes an L or Z route of
  the same width between the band ends, the route that keeps the most space to the other shapes (several
  rounds, so neighbouring 45 degree wires find positions that fit together); a single diagonal edge becomes
  a corner, or, where no corner fits, a staircase of 10 nm steps. 45 degree well / implant edges (NW, NP,
  PP) always become a 20 nm staircase: a corner would move the edge up to half the diagonal's length
  closer to the devices (`ACT_S_5` / `ACT_EN_2` in the LATL / DFFSR cells).
- A pass gives every vertical edge a variable. Pairs of edges that see each other get a difference
  constraint from their relation in the current layout and the rule tables: gap (`SPACE`, corner to corner
  euclidean), width (`WIDTH`; CT, V1 and the gate length rigid), enclosure (`ENC`, `ENC_MODES`),
  distance to the cell boundary (`HALF`: the original distance up to half the spacing rule, so any two
  cells can abut; V1 to 0.065 for `V1_S_3`, NW steps 0.32 from the side for `NW1_W_1` across the seam),
  order of poly / diffusion against implant and well edges, coincident edges stay coincident. The well /
  implant enclosure of AA is also kept corner to corner (a step of the well edge beside an AA, euclidean
  like the deck). Two same side edges of one M1 shape that meet in a step only keep their order, so a
  staircase can flatten.
- Constraints that ask for more than the current distance are elastic (slack at a high cost); the LP
  (scipy HiGHS) minimises the edge movement. Slack left on a hard rule means the cell does not fit:
  the x pass is retried with the cell one site (0.2 um) wider, up to three sites.
- Rules with alternatives (contact / via enclosure: two opposite sides 0.04 or all sides 0.025 / 0.03)
  get a mode per contact, switched when it does not fit. Conditional rules the tables cannot express
  exactly (line end `MET1_S_5` / `PO_S_9` / `M2_S_5`, wide shapes `ACT_S_2` / `PO_S_2` / `M*_S_2`, area
  `MET1_A_1` / `M2_A_1` / `PO_A_1`) are cheaper soft targets: never worse than now, the full value if the
  LP finds room; the deck decides.
- The y pass is the same on the transposed cell with the rails, wells, implants, AA and boundary frozen
  (cell height, row contract and transistor widths stay). M1 pairs the y pass cannot space apart become
  x separation hints for the next x pass.

- `NP_EN_3` / `PP_EN_3` (field poly end closer than 0.15 to the NP / PP edge): the poly end is extended
  across the implant edge (poly crossing both implants is exempt), unless that makes a new gate or touches
  other poly (`cross_implant_edge`; a fallback keeps the full poly spacing).

`implant.py` then re-solves the NP / PP boundary of every legalized cell (the passes keep it frozen in
y). Between the N+ and P+ diffusion the boundary is one line; its height per 5 nm column is chosen by
dynamic programming against the Calibre rules: N+ / P+ AA enclosure and spacing 0.12 (euclidean),
implant extension 0.16 beyond the gate end at the AA edge (`SNP_68`), 0.15 from the whole AA edge a gate
ends on (the H7CH / H7CL Vt rules `NVT*_EX_2` / `PVT*_S_3`, the Vt layers being copies of NP / PP), field poly enclosure 0.15 unless
the piece touches both implants (`PO_CUT`, exempt as a whole), every step at least 0.18 wide, the
vendor height for 0.09 at the cell sides. A piece that still violates may have its end grown until it
touches the boundary, keeping 0.12 to other poly. Cells whose vendor boundary meets these rules keep
it (no cell without implant markers is changed); NP / PP overlaps (`PP_R_1`) are redrawn.

Every fixed cell is then checked with the real deck (abutted, alternately mirrored rows) and compared
with its CDL; only cells that are clean (besides latch-up, floating well and density, which need a placed
design) and match like the original are used.

`make_fixed.py` around that:

1. two variants, with and without the poly extension across the implant edge; per cell the better
   result (usable, else LVS as good as the original, else fewer DRC markers);
2. feedback rounds (3): the legalized cells that still have markers are legalized again from their
   result, each marker becoming a hard constraint of the pass (`markers.py` maps the markers into cell
   coordinates, `legalize.Fix`: the two facing edges of the marker's layers get the rule value). For
   implant enclosure markers the extension is tried first (only at the markers), then a local step of the
   implant edge (`implant_jog`), then the constraints alone; a cell takes the new result only when it
   improved. Growth stays limited to three sites in total;
3. the tap cell (`WELLTAP_CELL`), whose implant islands are below the widths the passes model, is fixed
   by hand (`fix_filltap.py`: P+ pickup AA 0.15 from the well, N+ AA 0.15 inside it). Its P+ island
   (0.102 um2) needs `PP_A_1` 0.12 um2, but it cannot grow in y (well edge, and `PP_S_1` to the island
   of a tap in the mirrored row) and in a one site cell not in x either: neighbour gates are 0.2 from
   their cell side and `PP_S_5` / `NP_EX_1` / `PP_EX_1` want 0.30 from the islands. The tap therefore
   grows to two sites (0.8 um) with 0.24 wide islands 0.28 from both sides;
4. the unusable cells keep the vendor layout and are listed in `<lib>/unusable.cells`;
5. H7CH / H7CL: the fixed H7CR cell plus the Vt layers (`derive_vt.py`). In the vendor cells they
   are exact copies of NP / PP, so they are copied from the fixed NP / PP (stretching the vendor
   Vt shapes instead left `NVT3_EX_2` / `PVT3_S_3` on ~110 cells where the implant boundary moved).
   Both derived libraries are checked again (`check_cells.py`, `_M2` view); a usable cell with a Vt
   rule marker would become unusable in all three libraries (none does);
6. the LEF macros of the usable cells are rewritten from the GDS (`lef_from_gds.py`).

## Result (2026-11-14, H7CR, 785 cells; H7CH / H7CL identical)

| step | usable |
|---|---|
| with poly extension | 488 |
| without | 482 |
| better of both | 493 |
| feedback round 1 | 598 |
| feedback round 2 | 608 |
| round 3 | +0 |
| tap cell by hand | 609 |

609 usable (growth: 186 none, 263 one site including the tap, 129 two, 31 three), 176 unusable:

- 106 legalized but still with DRC markers (cells per rule): `PP_EN_3` 34, `NP_EN_3` 18 (27 cells only
  these; e.g. XOR / XNOR, where the gate's `NP_EX_1` and the aligned poly end's `NP_EN_3` cannot both
  hold), `MET1_S_5` 26, `PO_S_2` 22, `PO_S_9` 21, `PO_S_14/15` 27, `PO_S_1` 10, `ACT_S_2` 6,
  `MET1_S_2` 5, `PO_EX_2` 4, `V1_S_3` 4, `NP/PP_EX_1_EX_1a` 5, ...
- 67 not legalized within three sites, mostly M1 spacing in y (7 tracks, 48) and in x (12)
- 3 LVS worse than the original (`FILLCAP8/16/32`, also with DRC markers)

The H7CH / H7CL Vt check finds no Vt rule marker in the usable cells; the three unusable lists are the
same.

Sequential cells: usable are `DFFQX1` (`DFFQX0P5` is one of the CDL mismatches), `DFFX1`, `DFFNX0P5/1`,
`DFFNQX2/3`, `DFFNSX2`, `DFFSX0P5/1/2`, `DFFTRQ*`, the latches `LATHX0P5/1/2`, `LATHRX*`, `LATHSRX*`, `LATHSX2`,
`LATLX1-4`, `LATLSX0P5/1`, `SDFFNX0P5` and the ICGs `ICGX0P5/2/3/4`, `ICGNX2/4`. No flop with an
asynchronous reset (`DFFR*`, `DFFRQ*`, `DFFSR*`) is usable, the vendor M1 of `DFFRQ` / `DFFSQ` needs about
70 nm more height than a 7-track cell has. Yosys `dfflibmap` maps reset flops onto the set flops with
the `QN` output (`DFFSX*`), so designs with asynchronous reset still synthesize; only flops with both set
and reset, and scan flops, are lost. The LibreLane `latch_map.v` builds the negative enable reset latches
from `LATHR*` / `LATHSR*` with an inverter. `FILLCAP4` is the only clean decap.

Checks of the 609 usable cells among themselves (GDS with only those cells, so every neighbour is
usable):

- plain and `_M2` view, abutted and mirrored rows (`check_cells.py`): besides the context rules
  (latch-up, density, `NW1_R_1`) 12 markers, none inside a cell. 5 `MET1_S_5` with the left
  neighbour's M1 and the rail (AO21X*, OR3X8, AOI221X1P4), 7 `PO_S_9` / `PO_S_2` between the poly
  ends of vertically adjacent rows (60 nm from the cell edge in the vendor cells too);
- plain view LVS: 759 of 777 cells match, the other 18 are the vendor CDL mismatches;
- every left / right side pair (`testing/abut_check.py`): only `ACT_S_2` is confirmed in real cells,
  111 sides (the vendor layout of the same 609 cells: `ACT_S_2` 127 sides, `MET1_S_4` 819,
  `NW1_W_1` 317). The first tap fix (islands 0.24 wide in one site) conflicted with ~240 cell sides
  here, hence the two site tap;
- every cell alone at the edge of a row block (`testing/rowend_check.py`): clean between two
  `FILLER1` endcaps with a filler row above and below, which is how the LibreLane config closes the
  rows (`ENDCAP_CELL`, `ENDCAP_HORIZONTAL_CELLS`, plugin step `ICS55.TapEndcapInsertion`); without
  them 12410 markers (`NP_EN_3` / `PP_EN_3` from the open top / bottom on ~500 cells,
  `NP/PP_EX_1_EX_1a` from the open sides on ~240).

LibreLane `demo_counter` with the fixed libraries (2026-11-15, with `ICS55.TapEndcapInsertion`): Netgen
and KLayout LVS clean, antenna clean, no routing DRC, timing met. KLayout DRC: only density minima,
latch-up inside `BUFX10` / `BUFX16` and `CHIPEDGE` / `V4_S_2` at the die corner (small unfilled die).
Before the endcaps the cells at the row ends had `NP/PP_EX_1_EX_1a` (8) and the top row `NP_EN_3` (2).
Poly ends of vertically adjacent rows (60 nm from the cell top / bottom, as in the vendor cells) can
still meet `PO_S_9` in other placements; neither `abut_check.py` nor the regression covers rows above /
below with real cells.
