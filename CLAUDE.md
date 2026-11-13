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
  MET2, so `CELL_GDS` must be the matching `*_M2.gds` (the plain GDS only has MET1 pins → every routed pin is open).
  The cell LEF/GDS pair and the liberty file names are picked per standard cell family (`regexp` on
  `STD_CELL_LIBRARY`); the technology LEF (`N551P6M_ecos.lef`) is the same for both families.
- Two standard cell families are supported:
  - `ics55_LLSC_H7C{R,H,L}` — 7-track, public, from the `icsprout55-pdk` submodule. Default (`H7CR`). Shared
    configuration in `libs.tech/librelane/ics55_LLSC_H7C_common.tcl`, sourced by each library's `config.tcl`;
    the three Vt flavours differ only in the cell name suffix (`H7R`/`H7H`/`H7L`). Each has
    `synth_exclude.cells` / `pnr_exclude.cells`, the 18 cells whose layout does not match their CDL.
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
  covers both, and keeps the Magic extracted SPICE view.
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
  - `ics55_antenna.drc`: the vendor antenna runset (`pv/DRC/*.ant`) through the same generator (incremental
    connectivity, per gate `ACCUMULATE`, diode allowance; runs flat). LibreLane `KLAYOUT_ANTENNA_RUNSET`.
    Semantics settled on `hacking/svrf2klayout/tests/antenna` (identical to Calibre on all 23 firing rules).
  - `rule_decks/` holds the earlier hand translation; it is no longer included by the decks.
- `testing/` — regression: `wrap_lib.py`/`lvs_wrap.py` place a whole library under a top cell `ALL` (DRC: each cell
  abutted between fillers; LVS: grid + matching `.SUBCKT ALL`), IO LVS runs per cell. Results are compared against
  `golden/*.json`; known remaining findings are explained in `testing/README.md`.
- `hacking/` — reverse-engineering and generator scripts that feed the PDK:
  - `ICSIOA_N55_3P3_1P6M1TM_openpdk.lef` is the vendor IO `_ecos` LEF with the pad terminals moved to RDL;
    `PAD_LEFS` points at it (installed next to the vendor LEFs, not over them).
  - `cdl_convert.py` produces the installed (LVS-ready) CDLs from the vendor CDLs (strips CDL `/` and `$` annotations,
    dedups helper subckts, declares `nw/pw/nl/pl` params, prefixes private helper subckts per library so std cell
    `NAND2` and IO `nand2` don't collide; `--lef` adds empty subckts for physical-only IO cells needed by
    OpenROAD `write_cdl`). `install.sh` runs it instead of copying.
  - `cdl_to_spice.py` makes the ngspice netlists; `layermap*_to_lyp.py` generate the `.lyp` from `hacking/layermap`.
  - `NOTES.md` documents how RCX parameters were recovered from the ECOS binaries.
- `icsprout55/libs.tech/ngspice` / `hspice` — device models (ngspice copies adapted from hspice).
- `generate_rcx_rules/` — OpenRCX rules from the vendor StarRC ITF (`../pdk/.../StarRC/ITF`, same data as
  `hacking/decrypted_output/kItf*`): `itf2rcx.py` field solves every OpenRCX context with FasterCap 2D
  (drawn dimensions × the ITF 0.9 half node shrink) into `libs.tech/librelane/rcx/ics55_{typ,rcworst,rcbest}.rules`
  (`nom_*` / `max_*` / `min_*`) and `rcx/layers_rc.tcl`; `itf2lef.py` writes the per corner tech LEFs
  `N551P6M_ecos{,_max,_min}.lef` (resistance, since LibreLane extracts with `-lef_res`). Solutions are kept in
  `solutions/*.csv` (`--from-csv` regenerates without solving, a full solve is ~4 h per corner).
  Method and validation in `generate_rcx_rules/README.md`. The old `Makefile` flow is superseded.

## Known gaps

- Full-chip KLayout LVS (`demo_chip`) is disabled: layer derivation is far too slow on the filled chip.
- With the container's LibreLane 3.0.16, `Odb.CustomIOPlacement` makes the IO pins span the whole die (default pin
  length from the layer min AREA comes out ~10^6 too long when `IO_PIN_H_LENGTH` / `IO_PIN_V_LENGTH` are unset):
  `OpenROAD.IRDropReport` then fails with `PSM-0069` and `KLayout.Render` writes a zero-height image.
  `demo_counter` sets both lengths to 1 um and completes (2026-11-13, Netgen and KLayout LVS clean).
- RCX: Cbest / Cworst ITF corners are not generated (no STA corner uses them).
- `demo_chip` reaches `final/` but exits non-zero on a deferred `Checker.PowerGridViolations`: PSM reports
  `PSM-0025 VDD/VSS does not contain any terminals` because `VSRC_LOC_FILES` is unset (the grid itself passes,
  `PSM-0040 All shapes on net VDD are connected`). Set `VSRC_LOC_FILES` to clear it.
- KLayout DRC on the demos reports library-intrinsic findings with the 7-track libraries, so the demo configs set
  `ERROR_ON_KLAYOUT_DRC: false`; LVS errors still fail the flow. The demos have not been re-run through LibreLane
  since the decks became the generated ones (full rule set), so earlier marker counts no longer apply.
- 18 std cells per Vt library differ between vendor CDL and layout (listed in `testing/README.md`). Per cell, 15
  more have a series stack in another order than the CDL (NAND2X0P5 ...; KLayout per cell and netgen agree, the
  KLayout library-wrapper regression misses them, list in `hacking/magic/README.md`).
- Magic: GDS layers > 255 need `hacking/magic/magic_gds.py`; netgen has no split-gate reduction, so LibreLane LVS with
  `MAGIC_EXT_USE_GDS: true` fails on cells with split stacks (the default abstract extraction is fine); Magic DRC
  covers ~160 Calibre rules, no RECTANGLE ENCLOSURE via rules, no antenna, no density.
- The standard cell library has no endcap cells; OpenROAD `tapcell` inserts no taps in rows shorter than
  `FP_TAPCELL_DIST` (15 µm), so tiny dies need absolute sizing.
- No decap insertion for the 9-track libraries (`DECAP_CELLS` empty). OpenROAD fill insertion runs after detailed
  routing and is not routing aware, and the `FILLCAP*` / `GFILL*` cells have their internal nodes on MET1, so they
  short to whatever MET1 the router already put in the gap. The plain `FILL*` cells have no devices and no MET1
  outside the rails. The same hazard exists for `FILLCAP*H7R` in the 7-track libraries, it just does not trigger on
  the demos.
