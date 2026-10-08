# ICS55 KLayout DRC / LVS regression

Runs `tech/ics55.drc` and `tech/ics55.lvs` on the PDK standard cells and IO
library and compares the results against the baselines in `golden/`:

- DRC: markers per rule and per cell
- LVS: match status per cell

The GDS and CDL files come from `icsprout55/libs.ref`, which is not tracked in
git (it is populated by `install.sh`).

## Running

Inside the tools container (KLayout 0.30.10), about one minute for everything:

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
| `drc_io`              | `ICSIOA_N55_3P3_1P6M1TM.gds`            | top cell `P65_1233_1P6M` as is         |
| `lvs_stdcell_H7CR`    | H7CR GDS + CDL                          | all cells under `ALL`, `tapless=true`  |
| `lvs_stdcell_H7CH`    | H7CH GDS + CDL                          | all cells under `ALL`, `tapless=true`  |
| `lvs_stdcell_H7CL`    | H7CL GDS + CDL                          | all cells under `ALL`, `tapless=true`  |
| `lvs_stdcell_H7C*_M2` | `_M2` GDS (MET2 pins, used by LibreLane) + CDL | as above                       |
| `lvs_io`              | IO GDS + `ICSIOA_N55_3P3.cdl`           | one run per cell, implicit supply nets |

DRC: the standard cell libraries have one top cell per standard cell, so
`wrap_lib.py` places them all under a new top cell `ALL`. Each cell gets a
filler on both sides (aligned with the 351/12 boundary) because NW, NP and PP
extend past the cell edge and only become full width when abutted. Without
fillers there are ~400 false NW1_W_1 markers per library.

LVS standard cells: `lvs_wrap.py` places the cells in a grid (not touching)
under `ALL` and writes a matching schematic `.SUBCKT ALL` with one instance per
cell, so each cell is compared as its own circuit pair. The cells are tapless,
hence `-rd tapless=true` (substrate joined to VSS, untapped wells to VDD).

LVS IO: each IO cell that has a schematic is run as its own top cell, with
`-rd implicit_nets="VDDIO VSSIO VDD VSS"` because the supply rails of a
standalone IO cell come in pieces that connect through the neighbouring cells.

## Known baseline results

### DRC

The standard cell libraries are clean against the deck (with the deviations
below). These are in the IO golden file and are believed to be real, not
translation errors:

| Rule       | Where                         | Geometry vs rule                      |
|------------|-------------------------------|---------------------------------------|
| V3/V4_EN_5a_enc | IO `P65_1233_VDDIO3`     | via edge on metal edge (0 vs 0.005)   |

Deviations from the Calibre deck, made to accept the released standard cells
(the rule descriptions in the report give the original value):

| Rule     | Calibre | Deck   | Reason |
|----------|---------|--------|--------|
| NW1_W_1  | 0.47    | 0.36   | narrow NW steps inside 14 cells, 0.36-0.462um: DFFSRX0P5/X1, SDFFSRX0P5/X1/X2, MUX4X3 (0.36); DFFSX0P5/X1/X2 (0.381); ADDHX1P4 (0.39); SDFFSRQX1/X2/X3 (0.438); DFFSRQX2 (0.453, 0.462). Not abutment: the legs at the cell edges disappear once abutted (the test puts a filler on both sides) |
| NW1_S_1  | 0.47    | 0.40   | shallow NW notches of 0.409-0.46um in ICGX2, LATLSR and DFFNRX4 |
| ACT_S_1  | 0.11    | 0.10   | AA spacing of 0.105 in NAND3, MSDFFQ |
| PO_A_1   | 0.04    | 0.0388 | PO areas of 0.0388-0.03995um2 in 113 cells (smallest in DFFSRX0P5/X1/X2) |
| MET1_A_1 | 0.042   | 0.027  | M1 pins of 0.027-0.031um2 in 714 cells |
| Mn_A_1   | 0.052   | 0.020  | M2 pins of 0.038um2 in the `_M2` library |

PO_S_1 keeps the Calibre value (0.12). Its former markers (SDFFSQ, and
OAI2BB2X6 / SDFFNQX3 / ICGX1 / DFFQX0P5 when it was 0.119) were two corners of
the same PO polygon measured through its interior; no two PO polygons of the
libraries are closer than 0.12um. `drop_inner` (ics55.drc) removes such results.
KLayout's euclidian space check only reports these corner pairs when they are
within about 1 dbu of the threshold, which is why the counts changed with the
value. The `transparent` mode is not an alternative: it measures through other
shapes and reports hundreds of gaps down to 0.06um.

Expected artifacts, not errors:

- IO `P65_1233_FILLER0005` / `P65_1233_FILLER001`: 0.005/0.01um wide spacer
  cells whose layers are only complete when abutted to the pads.

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
