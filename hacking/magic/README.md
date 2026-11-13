# Magic tech file and Netgen setup for icsprout55

`icsprout55/libs.tech/magic/ics55.tech` and `icsprout55/libs.tech/netgen/ics55_setup.tcl` are
**generated** by `gen_magic_tech.py`. Do not edit them; change the generator and regenerate:

```bash
python3 hacking/magic/gen_magic_tech.py      # writes both files and hacking/magic/drc_coverage.txt
```

Nothing in them is typed in by hand:

| part of the tech file | source |
|---|---|
| GDS layer numbers | LAYER MAP of the vendor Calibre LVS runset (`icsprout55-pdk/pv/LVS`) |
| device layers (gates, diffusion, taps, diodes, poly resistors) | the layer derivations of that runset (each Magic layer names the Calibre seed it reproduces) |
| sheet / via / contact resistance, layer heights | the StarRC ITF, typical corner (`hacking/decrypted_output/kItfTyp.txt`) |
| capacitance (area, fringe, sidewall, overlap) | fitted to the FasterCap 2D solutions of WP1 (`generate_rcx_rules/solutions/TYP.csv`) |
| DRC rules | translated from the expanded Calibre DRC deck by `svrf2magic_drc.py` |
| netgen property tolerances | `TRACE PROPERTY` tolerances of the Calibre LVS deck (`mos_err` etc., 0.1 %) |

## Type model

Device layers are Magic types on the `active` plane, derived from ACT / POLY / CT and the
implant, oxide and Vt markers exactly as the Calibre deck derives its seeds (IO option
`TGOX_33`: 3.3 V devices are TGOX):

| Magic type | model | Magic type | model |
|---|---|---|---|
| nfet / pfet | nm1p2_svt_lp / pm1p2_svt_lp | ndiode / pdiode | dio_1p2_np_pw_lp / dio_1p2_pp_nw_lp |
| nfetlvt / pfetlvt (NVT1/PVT1) | nm1p2_lvt_lp / pm1p2_lvt_lp | ndiodelvt / pdiodelvt | dio_1p2_*_lvt_lp |
| nfethvt / pfethvt (NVT3/PVT3) | nm1p2_hvt_lp / pm1p2_hvt_lp | ndiodehvt / pdiodehvt | dio_1p2_*_hvt_lp |
| nfetnat (PSUB) | nnat1p2_lp | mvndiode / mvpdiode | dio_3p3_np_pw_lp / dio_3p3_pp_nw_lp |
| mvnfet / mvpfet (TGOX) | nm3p3_lp / pm3p3_lp | rnpo, rppo, rnposab, rpposab, rhrpo | re_{n,p}po[_sab]_2t, re_hrpo_2t |
| mvnfetnat | nnat3p3_lp | | |

MOS are extracted as subcircuit calls (`X ... nm1p2_svt_lp w= l=`, like the ngspice models and the
`libs.ref/*/spice` views), diodes as `D` elements with `area` / `pj`, resistors as two-pin
subcircuits. In addition every implant / oxide / Vt / marker layer the decks use is kept
literally as a type on a plane of its own (`nimp`, `pimp`, `nvt1`, `tgox`, `sab`, `nodrc`, ...), so
GDS output reproduces it and DRC rules can refer to it. Contacts and vias are read as the exact
cuts.

Not covered (WP7): BJTs, varactors, MOM / MIM capacitors, well / diffusion / metal resistors,
SRAM and 2.5 V DGOX devices, LDMOS, ESD-specific devices.

Approximations:
- Calibre's resistor poly is `POLYres NOT INTERACT SAB` (silicided) or `POLYres AND SAB`.
  Magic's GDS input has no INTERACT, so POLYres within 5 um of SAB counts as touching it
  (`SAB_HALO` in the generator).
- DGOX (2.5 V oxide) has no devices in the vendor deck with `IO = TGOX_33`; gates there are
  extracted as core devices.

### GDS layers above 255

Magic (8.3) only accepts GDS layer / datatype numbers up to 255. The vendor marker layers above
that (CHIPBLK 351, NODRC 357, SUBCKTLVS 313, PSUB 261, HRPBLK 385, WELTXT 388 / SUBTXT 387, ...)
are read as `(layer - 256, datatype + 100)`. `magic_gds.py <in.gds> <out.gds>` converts a GDS
into that numbering; without the conversion those layers are simply not seen. What depends on
them:

- `SUBCKTLVS` cuts the substrate (Calibre `sub2Ring`): in Magic it is the isolating substrate
  type `isosub`. The IO cells need it (e.g. VSS1 and VSSIO of `P65_1233_VSS1` are separate
  substrate regions).
- `WELTXT` / `SUBTXT` carry the VNW / VPW pin labels of the 9-track cells.
- `PSUB` marks native devices, `HRPBLK` the high resistance poly, `NODRC` the DRC exemptions.

Magic never writes these layers. LibreLane's Magic steps read the unconverted GDS (or the LEF
abstracts); the flows below do not depend on them.

## Netgen

`ics55_setup.tcl`: source / drain permutation and parallel merging of the MOS (w added, l
critical), area / perimeter merging of the diodes, series / parallel merging of the resistors,
and the physical-only cells (fillers, well taps) ignored in the layout.

The reference netlists are `libs.ref/<lib>/spice/<lib>_lvs.spice`, made by `lvs_netlist.py` from
the spice views (install.sh):

- the vendor cells call parametrised helper subcircuits (`XI0 ... INV nw=210n pw=270n`);
  netgen does not pass parameters into a subcircuit, so they are inlined;
- the empty device stubs of the CDL (`.SUBCKT re_ppo_sab_2t POS NEG`) are dropped, so that the
  calls are black-box devices with numbered pins on both sides and the setup applies to them;
- split gates are reduced (`reduce_split_gates.py`, Calibre `LVS REDUCE SPLIT GATES YES`, as in
  the KLayout deck): the vendor layouts split wide series stacks into parallel legs while the
  CDL has one stack.

`reduce_split_gates.py` is applied to the extracted netlist by the library regression as well.
In a LibreLane flow with `MAGIC_EXT_USE_GDS: true` the extracted netlist is not reduced, so
cells with split stacks would fail; the default (abstract cells, connectivity check) is not
affected.

## Regressions

```bash
# inside the asic-all container, from the repo root
python3 hacking/magic/testing/lvs_lib.py ics55_LLSC_H7CR        # or ICsprout55_9TSVT_basic, IO, ics55_LLSC_H7CR_M1
python3 hacking/magic/testing/drc_lib.py stdcell_H7CR_M2        # or stdcell_9TSVT, io
```

`lvs_lib.py` extracts every cell with Magic and compares it with netgen against the `_lvs.spice`
view. Tap-less cells are tied to the rails before comparing, as the KLayout regression does with
`tapless=true` (7-track: substrate -> VSS, n-well -> VDD; 9-track: the wells are the VNW / VPW
pins). `drc_lib.py` wraps the library like the KLayout DRC regression and compares the markers of
every translated rule with the KLayout goldens.

Results (2026-11-13):

LVS (Magic extraction + netgen per cell, same verdicts with the MET1-pin and the `_M2` GDS):

| library | match | property | topology | not compared |
|---|---|---|---|---|
| ics55_LLSC_H7CR | 744 | 13 | 20 | 8 empty fillers |
| ICsprout55_9TSVT_basic | 711 | 0 | 0 | 8 empty fillers |
| IO (ICSIOA_N55_3P3) | 13 | 0 | 0 | |

- The 13 property mismatches are exactly the cells the KLayout regression lists for W
  (`testing/README.md`: ADDFX1P4, ADDHX1P4, AND*X0P7 / X1P4, INVX7, INVX16, MUX4X4, OAI33X0P5,
  TBUFX8), with the Calibre 0.1 % tolerance.
- Topology: AND2X8 / X12 / X16 and NAND3BBX0P5 / X0P7 are on the KLayout list too. The other 15
  (NAND2X0P5 / X6 / X8 / X12 / X16, AOI22X1-X6, AOI211X6, AOI2BB2X2 / X3, OAI33X3 / X4) have a
  series stack in another order than the CDL (e.g. NAND2X0P5: B next to VSS in the layout, next to
  Y in the CDL). KLayout reports the same when run per cell (`ics55.lvs -rd topcell=<cell>
  -rd tapless=true`); its library regression (all cells under one top) does not.

DRC (`drc_lib.py`, translated rules that fire in either tool):

| library | rule | KLayout | Magic |
|---|---|---|---|
| H7CR_M2 | ACT_S_1 | 19 | 19 (same cells) |
| H7CR_M2 | PO_A_1 | 113 | 113 (same cells) |
| H7CR_M2 | NW1_W_1 | 14 | 17 (row ends; KLayout counts them at the top) |
| H7CR_M2 | CT_EN_2b / 3 / 4, V1_EN_2 | 142 / 296 / 34889 / 2198 | 0: partly translated, cut enclosure (see below) |
| H7CR_M2 | MET1 width (technology LEF) | n/a | 1 |
| 9TSVT | (none) | 0 | 0 |

IO library (`drc_lib.py io`, ~1 h): a few rules agree (POLYres_EN_1 24 / 24, RDL_EN_2 13 / 13,
SAB_S_5 720 / 810, SAB_W_1 11 / 13), but most of the 49 firing rules are Magic only or inflated
(SAB_S_6 422 / 7863, SAB_EX_*, SAB_S_3, POLYres_EX_2, TG_*, T4V2_EN_5_EN_6, and the technology
LEF width / spacing baseline on RV, T4V2, RDL, T4M2, which the pad structures do not follow).
Likely causes: the dropped NODRC exemptions and the approximated SAB / resistor regions. Magic DRC
is not meaningful on the IO cells; use KLayout there.

`demo_counter` (LibreLane, Magic DRC on the full GDS): PO_A_1, PP_A_1 and NW1_W_1 as with KLayout.
Open: NP_W_1 / NP_S_1 / PP_W_1 / PP_S_1 (~290 tiles each) where FILLTAPH7R abuts the fillers, which
KLayout does not report; the implant strips there are >= 0.18 um, so probably a Magic hierarchy
interaction artefact (not yet confirmed).

## DRC translation

`svrf2magic_drc.py` (coverage per rule in `drc_coverage.txt`):

- native rules (variants `fast`, `full`): width / spacing / surround / area on layers that are
  unions of drawn layers;
- CIF rules (variant `full`): `cifwidth`, `cifspacing`, `cifarea`, and `cifmaxwidth ... 0
  bend_illegal` (layer must be empty) on derived layers. Derived layers are templayers of the CIF
  output style `drc`, built with and / and-not / or / grow / shrink / `bloat-all` (INTERACT,
  INSIDE, OUTSIDE, ENCLOSE) / `close` (HOLES). Magic allows 255 CIF layers per style; rules are
  taken cheapest first until the budget is used.
- skipped: edge operations, RECTANGLE (exact via sizes), WITH WIDTH, LENGTH, ANGLE, DENSITY,
  NET AREA RATIO (antenna), WITH TEXT, AREA as a selection, constrained INTERACT counts,
  CONNECTED spacing, PROJECTING / PARALLEL / ANGLED filters, rules beyond the CIF budget.
- Magic contact and via types always carry their metal, so "cut not enclosed by metal" cannot
  be seen; the RECTANGLE ENCLOSURE via rules (`V*_EN_2*`, `CT_EN_4*`) are not translated.
- Exemption wrappers (`... NOT INSIDE NODRC`) are dropped: Magic cannot exempt regions per rule.

KLayout stays the signoff DRC / LVS.
