# ICS55 KLayout DRC / LVS regression

Runs `tech/ics55.drc` and `tech/ics55.lvs` on the PDK standard cells and IO
library and compares the results against the baselines in `golden/`:

- DRC: markers per rule and per cell
- LVS: match status per cell

The GDS and CDL files come from `icsprout55/libs.ref`, which is not tracked in
git (it is populated by `install.sh`).

## Running

Inside the tools container (KLayout 0.30), about one hour for everything (the DRC
deck is the complete Calibre rule set; `hacking/svrf2klayout/regress.sh` is a
wrapper for the command below):

```
docker run --rm -v "$PWD":/work -w /work factory.symbioticeda.com/asic-all:dev \
    bash -lc 'cd icsprout55/libs.tech/klayout/tech/testing && python3 run_regression.py'
```

Options:

- `--tests drc_stdcell_H7CR,lvs_io` run a subset
- `--update` overwrite the golden files with the current results
- `--run-dir DIR` output directory (default `run/`, ignored by git)

A change is printed as `RULE: old -> new markers` (DRC) or
`CELL: old -> new status` (LVS) and the run exits with code 1. After adding
or fixing rules, review the differences and then rerun with `--update`.

## Testcases

| Name                  | Input                                   | How                                    |
|-----------------------|-----------------------------------------|----------------------------------------|
| `drc_stdcell_H7CR`    | `ics55_LLSC_H7CR.gds` (regular Vt)      | every cell abutted with FILLER4        |
| `drc_stdcell_H7CH`    | `ics55_LLSC_H7CH.gds` (high Vt)         | every cell abutted with FILLER4        |
| `drc_stdcell_H7CL`    | `ics55_LLSC_H7CL.gds` (low Vt)          | every cell abutted with FILLER4        |
| `drc_stdcell_H7CR_M2` | `ics55_LLSC_H7CR_M2.gds` (M2 variant)   | every cell abutted with FILLER4        |
| `drc_stdcell_9TSVT`   | `ICsprout55_9TSVT_basic.gds` (9T, std Vt) | vendor top cell as is                |
| `drc_stdcell_9THVT`   | `ICsprout55_9THVT_basic.gds` (9T, high Vt) | vendor top cell as is               |
| `drc_stdcell_9TLVT`   | `ICsprout55_9TLVT_basic.gds` (9T, low Vt) | vendor top cell as is                |
| `drc_io`              | `ICSIOA_N55_3P3_1P6M1TM.gds`            | top cell `P65_1233_1P6M` as is         |
| `lvs_stdcell_H7CR`    | H7CR GDS + CDL                          | all cells under `ALL`, `tapless=true`  |
| `lvs_stdcell_H7CH`    | H7CH GDS + CDL                          | all cells under `ALL`, `tapless=true`  |
| `lvs_stdcell_H7CL`    | H7CL GDS + CDL                          | all cells under `ALL`, `tapless=true`  |
| `lvs_stdcell_H7C*_M2` | `_M2` GDS (MET2 pins, used by LibreLane) + CDL | as above                       |
| `lvs_io`              | IO GDS + `ICSIOA_N55_3P3.cdl`           | one run per cell, implicit supply nets |
| `ant_vehicle`         | `antenna/ant_test.gds` (15 antenna cases) | `ics55_antenna.drc`; golden = what Calibre reports |
| `ant_stdcell_H7CR_M2` | `ics55_LLSC_H7CR_M2.gds`                | `ics55_antenna.drc`, cells abutted with FILLER4 (no findings) |

The antenna test layout is made by `hacking/svrf2klayout/tests/antenna/mk_antenna_test.py`
(also `run_calibre.py` / `compare.py` there to re-check it against Calibre).

DRC: the 7-track standard cell libraries have one top cell per standard cell, so
`wrap_lib.py` places them all under a new top cell `ALL`. Each cell gets a
filler on both sides (aligned with the 351/12 boundary) because NW, NP and PP
extend past the cell edge and only become full width when abutted. Without
fillers there are ~400 false NW1_W_1 markers per library.

The private 9-track libraries (`ICsprout55_9T{S,H,L}VT_basic`) ship a single top
cell that already holds all 719 cells, spaced so that the well and implant
overhang does not interact, so they are checked as they are. They are only in
`libs.ref` when `install.sh` found the vendor directory; their testcases print
`SKIP` when the GDS is missing.

LVS standard cells: `lvs_wrap.py` places the cells in a grid (not touching)
under `ALL` and writes a matching schematic `.SUBCKT ALL` with one instance per
cell, so each cell is compared as its own circuit pair. The cells are tapless,
hence `-rd tapless=true` (the well nets of every cell are tied to VSS / VDD).

LVS IO: each IO cell that has a schematic is run as its own top cell, with
`-rd implicit_nets="VDDIO VSSIO VDD VSS"` because the supply rails of a
standalone IO cell come in pieces that connect through the neighbouring cells.

## Known baseline results

### DRC

`ics55.drc` is generated from the Calibre deck (`hacking/svrf2klayout`) with the
Calibre values and the complete rule set, so the golden files hold what the
libraries really violate when they are checked standalone. Nothing is relaxed
or waived.

| Testcase | Markers | Rules | Largest contributors |
|----------|---------|-------|----------------------|
| `drc_stdcell_H7C{R,H,L}` | 98843 | 39 | CT_EN_4a_4b_4c 34889, LU_S_2_NTAP 14705, LU_S_2_PTAP 14069, CT_S_4 13969, NP_EN_3 4950, PP_EN_3 4585, MET1_S_4 2846, MET1_A_1 2227, MET1_W_2 1703, MET1_S_5 1304 |
| `drc_stdcell_H7CR_M2`    | 101371 | 42 | as above plus V1_EN_2a_2b_2c 2198, M2_A_1 328, V1_S_3 2 |
| `drc_stdcell_9T{S,H,L}VT` | 24862 / 24863 / 24863 | 13 | LU_S_2_NTAP 12611, LU_S_2_PTAP 10828, NW1_R_1 717, density minima |
| `drc_io`                 | 3701 | 57 | SAB_S_5 720, SAB_S_6 422, CT_EN_4d 408, SAB_R_1 398, SAB_S_4 360, PO_S_11 268, POLYres_S_2 222 |

What is behind them:

- `LU_S_2_NTAP` / `LU_S_2_PTAP` (latch-up, distance to the next well tap): the
  cells have no taps and the test layouts contain no tap cells. Expected for a
  library check; a placed design with tap cells clears them.
- `*_D_*_min` (minimum density): the test layout is not a filled chip.
- `NW1_R_1`: one marker per cell, also a consequence of the untapped wells.
- 7-track libraries only: contact enclosure / spacing (`CT_EN_*`, `CT_S_*`),
  implant enclosure (`NP_EN_3`, `PP_EN_3`), MET1 spacing / width / area and the
  poly rules. Calibre reports the same rules on these cells; the 9-track
  libraries have none of them.
- IO: mostly the SAB / poly resistor / RDL rules of the ESD and pad structures,
  plus the 0.005/0.01um spacer cells `P65_1233_FILLER0005` / `FILLER001`, whose
  layers are only complete when abutted to the pads.

Agreement with Calibre 2012.2 (details in `hacking/svrf2klayout/README.md` and
`hacking/svrf2klayout/tests/results/`): on the H7CR library 49 of the 60 firing
rules have identical markers and on the IO library 68 of 71; the others differ
by a few markers. Known ones in the goldens: `PO_S_1` (3 markers on SDFFSQX1/2/3
that Calibre does not report: two corners of the same PO polygon measured
through its interior), `CT_EN_4a_4b_4c`, `PO_S_14`, `PO_S_15`, `PO_S_2`,
`MET1_S_4`, `MET1_S_5`, `LU_S_2_PTAP` (std cells) and `RV_EN_1_2`, `RV_EN_3_4`,
`T4M2_D_3` (IO). The 9-track libraries were not run through Calibre.

Six rules (NW1_W_1, NW1_S_1, ACT_S_1, PO_A_1, MET1_A_1, Mn_A_1) were relaxed
in an earlier hand-written deck to let the 7-track cells pass. They are at the
Calibre values now; for the record, the 7-track geometry behind them is: NW
steps of 0.36-0.462um in 14 flip-flop / mux / adder cells, NW notches of
0.409-0.46um, AA spacing of 0.105um, PO areas of 0.0388-0.03995um2 in 113
cells, M1 pins of 0.027-0.031um2 in 714 cells and M2 pins of 0.038um2 in the
`_M2` library.

### LVS

IO: all 23 cells match: the 13 cells with devices, and the corner / spacer
cells, which have empty subcircuits in the installed CDL (added by
`hacking/cdl_convert.py --lef`) and no devices, so only the overall verdict is
checked. The library top cell `P65_1233_1P6M` has no schematic and is not run.

Standard cells: 759 of 777 cells match in each Vt library, for both the plain
and the `_M2` layouts (the 8 FILL* cells
without devices are not compared). The 18 others differ between the vendor CDL
and the layout; the same cells fail in H7CR, H7CH and H7CL. The comparison uses
the Calibre tolerance of 0.1% on W/L, so Calibre should flag them as well:

| Cells | Difference |
|-------|------------|
| ADDFX1P4, ADDHX1P4, AND2X0P7, AND2X1P4, AND2X8, AND2X12, AND2X16, AND3X0P7, AND3X1P4, AND4X0P7, AND4X1P4, MUX4X4, TBUFX8 | W off by 0.001-0.04um (CDL widths not on the 5nm layout grid) |
| INVX16 | NMOS/PMOS widths swapped (layout N=3.04 P=2.4, CDL N=2.4 P=3.04) |
| INVX7, OAI33X0P5 | W clearly different (e.g. INVX7 layout N=1.2 P=1.52, CDL N=1.05 P=1.33) |
| NAND3BBX0P5, NAND3BBX0P7 | NMOS series stack in a different order (layout C next to Y, CDL C next to VSS) |

## Tools

- `run_regression.py` the regression runner
- `wrap_lib.py <lib.gds> <out.gds> [FILLER]` build the DRC wrapper layout
- `summary.py <report.lyrdb>` DRC markers per rule and the cells they fall in
- `items.py <report.lyrdb> RULE1,RULE2 [n]` print DRC marker geometries of some rules
- `lvs_wrap.py <lib.gds> <lib.cdl> <out.gds> <out.cdl>` build the LVS wrapper layout + schematic
- `lvs_summary.py <report.lvsdb> [--all]` LVS match status per circuit
