# OpenRCX rules from the vendor StarRC ITF

The OpenRCX rules in `icsprout55/libs.tech/librelane/rcx/`, the per corner tech LEFs
`icsprout55/libs.tech/librelane/N551P6M_ecos{,_max,_min}.lef` and `rcx/layers_rc.tcl` (`LAYERS_RC`,
`VIAS_R`) are generated here from the StarRC ITF files of the vendor kit:

    ../pdk/ICsprout_55LLULP1225_1P6M_5Ic_1T4Mc_RDL1_v1p11/StarRC/ITF/ICsprout_55LLULP_StarRC_1P6M_5Ic_V1p1_<corner>.itf

(TYP, Cbest, Cworst, RCbest, RCworst). An ITF is the process cross-section that StarRC's field solver
takes as input: every dielectric (thickness, ER), every conductor (thickness, WMIN/SMIN, RPSQ, CRT1/CRT2)
and every via (RPV). `hacking/decrypted_output/kItf*.txt` (recovered from the ECOS `libircx_ics55.so`) are
the same files. The vendor's own `itf_to_ict.pl` conversion (`innovus/captbl/ict/*.ict` in the 9-track
kit) gives exactly the layer heights that `itf.py` computes.

## Files

- `itf.py` — ITF reader; builds the bottom-up planar stack (conductors sit on the dielectric below them,
  `MEASURED_FROM` handled, conformal coatings taken at their field thickness).
- `patterns.py` — writes a FasterCap 2D input for one cross-section (three parallel lines on a layer,
  optional ground planes on the layers below/above, substrate at z = 0, every dielectric interface), runs
  FasterCap and reads the last (converged) capacitance matrix.
- `itf2rcx.py` — solves every OpenRCX context (OVER u, UNDER o, OVER u UNDER o; widths 1–20× min,
  spacings 1–20× min up to 8 um, plus the isolated line) and writes the rules file; `--csv` keeps the
  solutions, `--from-csv` rewrites rules / Tcl without solving, `--tcl` writes `LAYERS_RC` / `VIAS_R`.
  Results are cached in `<csv>.cache` as they come, so an interrupted run resumes.
- `itf2lef.py` — copy of the vendor tech LEF with RPERSQ / cut / via resistances from the ITF at a
  temperature (OpenRCX runs with `-lef_res` in LibreLane, so SPEF resistance comes from the LEF).
- `solutions/<corner>.csv` — the FasterCap solutions used for the shipped rules (fF/um of physical length,
  drawn width/spacing).

The older `Makefile` / `do.sh` / `data/process` / `scripts/` flow (OpenRCX v2 pattern generation with a
guessed stack) is superseded and kept for reference.

## Commands

FasterCap 6.0.7 (`FastFieldSolvers`, `FasterCap_v2`), headless build; the CMake project does not pass the
wxWidgets flags to its sub-libraries, so give them globally (needs `libwxgtk3.2-dev`):

```bash
CXXFLAGS="$(wx-config --version=3.2 --cxxflags base)" cmake <FasterCap_v2>/FasterCap \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DFASTFIELDSOLVERS_HEADLESS=ON \
    -DCMAKE_EXE_LINKER_FLAGS="$(wx-config --version=3.2 --libs base)" \
    -DCMAKE_CXX_STANDARD_LIBRARIES="$(wx-config --version=3.2 --libs base)"
make
```

```bash
export FASTERCAP=/path/to/FasterCap
ITF=../../pdk/ICsprout_55LLULP1225_1P6M_5Ic_1T4Mc_RDL1_v1p11/StarRC/ITF/ICsprout_55LLULP_StarRC_1P6M_5Ic_V1p1
LT=../icsprout55/libs.tech/librelane
# rules (~4 h per corner on 32 cores; FasterCap uses 8 OpenMP threads per run, so -j = cores / 8)
python3 itf2rcx.py ${ITF}_TYP.itf     $LT/rcx/ics55_typ.rules     --csv solutions/TYP.csv     -j 4
python3 itf2rcx.py ${ITF}_RCworst.itf $LT/rcx/ics55_rcworst.rules --csv solutions/RCworst.csv -j 4
python3 itf2rcx.py ${ITF}_RCbest.itf  $LT/rcx/ics55_rcbest.rules  --csv solutions/RCbest.csv  -j 4
# LAYERS_RC / VIAS_R from the stored solutions
for c in "TYP nom 25" "RCworst max 125" "RCbest min -40"; do set -- $c
  python3 itf2rcx.py ${ITF}_$1.itf /dev/null --from-csv solutions/$1.csv --tcl /tmp/$1.tcl --glob "$2_*" --temp $3
done; cat /tmp/TYP.tcl /tmp/RCworst.tcl /tmp/RCbest.tcl > $LT/rcx/layers_rc.tcl
# tech LEFs
B=../icsprout55-pdk/prtech/techLEF/N551P6M_ecos.lef
python3 itf2lef.py $B ${ITF}_TYP.itf     25  $LT/N551P6M_ecos.lef
python3 itf2lef.py $B ${ITF}_RCworst.itf 125 $LT/N551P6M_ecos_max.lef
python3 itf2lef.py $B ${ITF}_RCbest.itf  -40 $LT/N551P6M_ecos_min.lef
```

## Method

- **Half node shrink.** The ITF has `HALF_NODE_SCALE_FACTOR = 0.9` (the xRC deck `PEX MAGNIFY 0.9`): layouts are
  drawn at 65 nm style dimensions (LEF MET2 width 0.1) and shrunk by 0.9 for extraction (ITF WMIN 0.09).
  The cross-sections are solved at drawn × 0.9; the rules are indexed by drawn width / spacing and give
  capacitance per drawn length (× 0.9). Sheet resistance is per square and unchanged.
- **Patterns.** Three lines of width w, spacing s; the middle one is excited. `cc` is its coupling to one
  neighbour, `fringe` half of the rest (substrate, planes, far lines), which is what OpenRCX adds per side
  (`extRCModel::readRCvalues`, `extMeasureRC::OverUnder`). The last row of every table is the isolated line
  (OpenRCX uses it for wires without neighbours). Neighbour layers are full ground planes. DIAGUNDER tables
  are not generated (DIAGMODEL off).
- **FasterCap.** Automatic mode (`-a`) is not used: on these inputs (long planes, 35–75 nm thin dielectric
  layers) it stops on under-refined meshes and was off by up to 40%. A fixed mesh `-m` scaled to the domain
  keeps the panel size at 0.04 um (× min width / 0.09 on TM / RDL); against a 5× finer mesh this is within
  0.5%. The lateral half extent is 4 um with a plane above, otherwise 3 × the line height (4 … 16 um), plus
  the pattern itself; an isolated TM line still changes by 2% from 8 to 16 um. `-f0.05` keeps the solver in
  core (FasterCap underestimates the free memory and its out-of-core mode fails on these inputs).

## Validation

- **Vendor Innovus cap table** (`ICsprout55_pr_techfile/innovus/captbl/captbl/*TYP.captbl`, BASIC table: line
  between full planes on the adjacent layers, physical units). FasterCap on the same geometry:

  | layer (environment) | w / s (um) | vendor Ctot / Cc (fF/um) | FasterCap Ctot / Cc |
  |---|---|---|---|
  | M2 (M1 / M3)  | 0.09 / 0.09 | 0.2422 / 0.0751 | 0.2425 / 0.0763 (converged mesh) |
  | TM (M5 / RDL) | 0.36 / 0.36 | 0.3019 / 0.1173 | 0.2991 / 0.1141 |
  | TM (M5 / RDL) | 0.36 / 1.08 | 0.1816 / 0.0310 | 0.1812 / 0.0309 |
  | TM (M5 / RDL) | 0.36 / iso  | 0.1667          | 0.1668          |

  The vendor table itself scatters by about 3% (e.g. M2 0.090 / 0.81: 0.1758 between two rows of 0.1696).
- **OpenRCX round trip.** 100 um MET2 lines, drawn 0.1 / 0.1, extracted with the TYP rules: middle line
  18.98 fF total, 8.78 fF to each neighbour, 1.42 fF ground; isolated line 5.48 fF; 91.5 Ω. Expected from the
  solutions (× 0.9 × 100 um): 18.97, 8.77, 1.42, 5.47 fF; 91.4 Ω. Same pattern on the other corners: RCworst
  (`_max` LEF, 125 C) 17.84 fF vs 17.82, 157 Ω; RCbest (`_min` LEF, −40 C) 20.13 fF vs 20.11, 52.7 Ω.

## Limitations

- 2D: line ends, vias and crossing wires are only seen through OpenRCX's own context handling.
- Conformal dielectrics (ILD1a over poly, PASS5/6 over RDL) are planar at their field thickness; RDL is only
  used for pad routes.
- OpenRCX picks the next lower table width (no interpolation across widths); widths beyond 20× min use
  the 20× table.
- Resistance: the tech LEF holds one value per layer per RC corner at the corner temperature (TYP 25 C,
  RCworst 125 C, RCbest −40 C), so e.g. a `max_*` corner at another temperature still uses 125 C.
- Calibre xRC was checked as a reference extractor: the vendor `XRC/rulefile/<corner>/rules.C` contains
  encrypted blocks that the local Calibre 2012.2 cannot decrypt, so it was not usable.
