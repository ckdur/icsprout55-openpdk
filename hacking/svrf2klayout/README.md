# svrf2klayout — Calibre SVRF → KLayout DRC/LVS for ICS55

The KLayout decks `icsprout55/libs.tech/klayout/tech/ics55.drc` and `ics55.lvs`
are **generated** from the public Calibre decks in `icsprout55-pdk/pv/`.
Do not edit them by hand; change the translator or runtime here and regenerate.

## Regenerating

```bash
. 616cad                                   # Calibre on PATH (only needed to re-expand the TVF decks)
calibre -E ICsprout_CalDRC_expanded.svrf -drc ../../icsprout55-pdk/pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc
calibre -E ICsprout_CalLVS_expanded.svrf -lvs ../../icsprout55-pdk/pv/LVS/ICsprout_CalLVS_55LLULP1233_REV1_0_OS.lvs
# (both stop with "cannot open *.gds" after writing the expanded file - that is fine)

python3 svrf2klayout.py     ICsprout_CalDRC_expanded.svrf ../../icsprout55/libs.tech/klayout/tech/ics55.drc
python3 svrf2klayout_lvs.py ICsprout_CalLVS_expanded.svrf ../../icsprout55/libs.tech/klayout/tech/ics55.lvs
```

The same two files are copied to `../icsprout55-pdk/klayout/tech/` (the PDK fork).

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

## Running the decks

DRC (`klayout -b -r ics55.drc -rd ...`): `input`, `topcell`, `report`, `thr`/`threads`,
`flat=1`, `select=<regex>`, `unselect=<regex>`, `densityRules=False`, `dump=LAYER[,RULE:LAYER]`,
and any deck switch, e.g. `-rd OPEN_RECOMMENDED_ON=YES`.

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
