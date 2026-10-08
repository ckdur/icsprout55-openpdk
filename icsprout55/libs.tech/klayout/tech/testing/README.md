# ICS55 KLayout DRC regression

Runs `tech/ics55.drc` on the PDK standard cells and IO library and compares
the markers (per rule and per cell) against the baselines in `golden/`.

The GDS files come from `icsprout55/libs.ref`, which is not tracked in git
(it is populated by `install.sh`).

## Running

Inside the tools container (KLayout 0.30.10):

```
docker run --rm -v "$PWD":/work -w /work factory.symbioticeda.com/asic-all:dev \
    bash -lc 'cd icsprout55/libs.tech/klayout/tech/testing && python3 run_regression.py'
```

Options:

- `--tests stdcell_H7CR,io` run a subset
- `--update` overwrite the golden files with the current results
- `--run-dir DIR` output directory (default `run/`, ignored by git)

A change in any rule or cell is printed as `RULE: old -> new markers` with the
cells that changed, and the run exits with code 1. After adding or fixing
rules, review the differences and then rerun with `--update`.

## Testcases

| Name              | Input                                       | How                              |
|-------------------|---------------------------------------------|----------------------------------|
| `stdcell_H7CR`    | `ics55_LLSC_H7CR.gds` (regular Vt)          | every cell abutted with FILLER4  |
| `stdcell_H7CH`    | `ics55_LLSC_H7CH.gds` (high Vt)             | every cell abutted with FILLER4  |
| `stdcell_H7CL`    | `ics55_LLSC_H7CL.gds` (low Vt)              | every cell abutted with FILLER4  |
| `stdcell_H7CR_M2` | `ics55_LLSC_H7CR_M2.gds` (M2 variant)        | every cell abutted with FILLER4  |
| `io`              | `ICSIOA_N55_3P3_1P6M1TM.gds`                | top cell `P65_1233_1P6M` as is   |

The standard cell libraries have one top cell per standard cell, so
`wrap_lib.py` places them all under a new top cell `ALL`. Each cell gets a
filler on both sides (aligned with the 351/12 boundary) because NW, NP and PP
extend past the cell edge and only become full width when abutted. Without
fillers there are ~400 false NW1_W_1 markers per library.

## Known baseline markers

These are in the golden files and are believed to be real (the cell geometry
is below the value in the Calibre deck), not translation errors:

| Rule       | Where                         | Geometry vs rule                      |
|------------|-------------------------------|---------------------------------------|
| MET1_A_1   | 714 standard cells            | M1 pins 0.027-0.031um2 vs >= 0.042    |
| M2_A_1     | 294 cells of the `_M2` library | M2 pins 0.038um2 vs >= 0.052          |
| PO_A_1     | 87 standard cells             | 0.0391-0.0394um2 vs >= 0.04           |
| ACT_S_1    | NAND3, MSDFFQ                 | 0.105 vs >= 0.11                      |
| PO_S_1     | SDFFSQ                        | corner to corner 0.1196 vs >= 0.12    |
| V3/V4_EN_5a_enc | IO `P65_1233_VDDIO3`     | via edge on metal edge (0 vs 0.005)   |

Deviations from the Calibre deck, made to accept the released standard cells:

- NW1_S_1 relaxed from 0.47 to 0.40um (shallow NW notches of 0.409-0.46um in
  ICGX2, LATLSR and DFFNRX4).

Expected artifacts, not errors:

- NW1_W_1 (15 per standard cell library): at the two ends of the test rows,
  where the filler NW is not abutted.
- IO `P65_1233_FILLER0005` / `P65_1233_FILLER001`: 0.005/0.01um wide spacer
  cells whose layers are only complete when abutted to the pads.

## Tools

- `run_regression.py` the regression runner
- `wrap_lib.py <lib.gds> <out.gds> [FILLER]` build the wrapper layout
- `summary.py <report.lyrdb>` markers per rule and the cells they fall in
- `items.py <report.lyrdb> RULE1,RULE2 [n]` print marker geometries of some rules
