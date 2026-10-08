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

# KLayout DRC / LVS regression on the std cells and IO (≈1 min, run in the container)
cd icsprout55/libs.tech/klayout/tech/testing
python3 run_regression.py                         # all testcases, exit 1 on any change vs golden/
python3 run_regression.py --tests drc_stdcell_H7CR,lvs_io   # subset
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

## Architecture

- `icsprout55/libs.tech/librelane/config.tcl` — LibreLane PDK config (std cell lib `ics55_LLSC_H7C{R,H,L}`, IO lib
  `ICsprout_55LLULP1233_IO_251013`). Important pairing: `CELL_LEFS` uses the `_ecos` cell LEF whose signal pins are on
  MET2, so `CELL_GDS` must be the matching `*_M2.gds` (the plain GDS only has MET1 pins → every routed pin is open).
- `icsprout55/libs.tech/librelane/librelane_plugin_ics55/` — LibreLane plugin (discovered via `PYTHONPATH`, set in the
  demo `run.sh`). Provides step `ICS55.KLayoutLVS`, because upstream `KLayout.LVS` only runs for IHP PDKs. Designs use
  `"-Netgen.LVS": OpenROAD.WriteCDL` + `Netgen.LVS: ICS55.KLayoutLVS`; Magic DRC/extraction/LVS are disabled.
- `icsprout55/libs.tech/klayout/tech/` — KLayout DRC (`ics55.drc`) and LVS (`ics55.lvs`) decks, translated by hand from
  the vendor Calibre runsets in `icsprout55-pdk/pv/{DRC,LVS}/`. Structure follows the IHP sg13g2 KLayout decks:
  - `rule_decks/layers_def.drc` and `rule_decks/lvs/layers_def.lvs` are GENERATED from the Calibre `LAYER MAP`
    blocks by `hacking/calibre_layers_to_klayout_drc.py` (variable = Calibre layer name lowercased). Don't hand-edit.
  - `rule_decks/derived_layers.drc`, `rule_decks/{feol,beol}/*.drc`, `rule_decks/lvs/*.lvs` are hand translations;
    each rule/derivation keeps the original Calibre statement as a comment and uses the Calibre rule name.
  - Several DRC values are deliberately relaxed to accept the released std cells; each carries a `NOTE:` comment and
    an `(orig: …)` in the rule description. The list is in `testing/README.md`.
  - Metal stack is fixed to the Calibre default: 6 metals, 1 top metal (M1–M5, T4V2, T4M2).
  - `rule_decks/README.md` and `rule_decks/lvs/README.md` document the SVRF→KLayout mapping and LVS behaviour
    (global substrate + SUBCKTLVS islands, tapless option, label ports, shorted-pin joining, split gates).
- `testing/` — regression: `wrap_lib.py`/`lvs_wrap.py` place a whole library under a top cell `ALL` (DRC: each cell
  abutted between fillers; LVS: grid + matching `.SUBCKT ALL`), IO LVS runs per cell. Results are compared against
  `golden/*.json`; known remaining findings are explained in `testing/README.md`.
- `hacking/` — reverse-engineering and generator scripts that feed the PDK:
  - `cdl_convert.py` produces the installed (LVS-ready) CDLs from the vendor CDLs (strips CDL `/` and `$` annotations,
    dedups helper subckts, declares `nw/pw/nl/pl` params, prefixes private helper subckts per library so std cell
    `NAND2` and IO `nand2` don't collide; `--lef` adds empty subckts for physical-only IO cells needed by
    OpenROAD `write_cdl`). `install.sh` runs it instead of copying.
  - `cdl_to_spice.py` makes the ngspice netlists; `layermap*_to_*.py` generate `.lyp`/magic tech from `hacking/layermap`.
  - `NOTES.md` documents how RCX parameters were recovered from the ECOS binaries.
- `icsprout55/libs.tech/ngspice` / `hspice` — device models (ngspice copies adapted from hspice).
- `generate_rcx_rules/` — OpenRCX rule generation (Makefile driven, needs `openroad`); current `rcx.rules` are placeholders.

## Known gaps

- Full-chip KLayout LVS (`demo_chip`) is disabled: layer derivation is far too slow on the filled chip.
- KLayout DRC on the demos still reports library-intrinsic findings, so the demo configs set
  `ERROR_ON_KLAYOUT_DRC: false`; LVS errors still fail the flow.
- 18 std cells per Vt library differ between vendor CDL and layout (listed in `testing/README.md`).
- The standard cell library has no endcap cells; OpenROAD `tapcell` inserts no taps in rows shorter than
  `FP_TAPCELL_DIST` (15 µm), so tiny dies need absolute sizing.
