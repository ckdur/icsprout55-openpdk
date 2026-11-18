#!/usr/bin/env python3
"""Density filler cells FILLDENS{4,8,16,32,64}<sfx> for the 7-track libraries.

  python3 density_fill.py [stdcell_fixed]        (KLayout python module needed: run in the container)

LibreLane puts filler cells on every free site of the standard cell rows, and dummy AA / PO
cannot be placed inside the rows (AADUM / PODUM: 0.3 from the NW boundary, 0.8 - 1.6 from AA
and PO), so the AA / PO density minima (ACT_D_1 >= 20 %, PO_D_2 >= 20 % in every 100 um
window, PO_D_1 >= 14 % globally) can only be met with cells. The design rule manual (3.3.43.1)
recommends exactly that: filler cells drawn with ACT / POLY for the standard cell areas.

Each cell is the library's FILLER<n> (rails, NW, NP / PP and, in H7CH / H7CL, the Vt layers,
so it abuts like a filler) plus, per 4 sites (0.8 um):
  - floating AA of the well's own type: N+ in the PW half (under NP), P+ in the NW half (under
    PP). Same-type diffusion is no junction and no device; diodes are only extracted under the
    DIODE marker (Calibre LVS).
  - two field poly lines that never cross AA (no gate), 0.13 wide (no PO_S_2 wide spacing,
    above the PO_S_9 line-end width).
  -> AA 25.6 %, PO 27 % of the cell area.
Distances (um, cell coordinates, row height 1.4, NW from 0.615):
  AA x 0.25-0.55; N+ y 0.07-0.465 (ACT_S_5 0.15 to NW, NP_EN_2 0.12), P+ y 0.765-1.33
  (ACT_EN_2 0.15 in NW, PP_EN_2 0.12); 0.07 from the top / bottom edge: ACT_S_2 0.125 to the AA
  of the next row (>= 0.055 from its edge); PO x 0.07-0.20 and 0.60-0.73, y 0.12-1.28
  (PO_S_11 0.05 to AA; PO_S_1 0.12 and ACT_S_1/2 to the shapes of any neighbour: the usable
  cells keep AA >= 0.055 and PO >= 0.06 from their boundary).
The poly crosses the NP / PP boundary like a gate does, so NP_EN_3 / PP_EN_3 do not apply.

Writes stdcell_fixed/<lib>/filldens/<lib>_filldens.{gds,lef,cdl} (the cells have no signal
pins, so the GDS serves both the MET1 and the _M2 pin views); install.sh copies them into
libs.ref and LibreLane adds them to CELL_GDS / CELL_LEFS / CELL_CDLS / CELL_SPICE_MODELS. Verified with Calibre DRC (every usable cell left / right,
mirrored rows above / below) and Calibre / KLayout LVS (no device).
"""
import gzip
import os
import re
import sys

try:
    import klayout.db as db
except ImportError:
    import pya as db

LIBS = {"ics55_LLSC_H7CR": "H7R", "ics55_LLSC_H7CH": "H7H", "ics55_LLSC_H7CL": "H7L"}
WIDTHS = [4, 8, 16, 32, 64]  # sites (0.2 um)
UNIT = 0.8                   # one AA block + two PO lines
AA = [(0.25, 0.07, 0.55, 0.465), (0.25, 0.765, 0.55, 1.33)]
PO = [(0.07, 0.12, 0.20, 1.28), (0.60, 0.12, 0.73, 1.28)]
AA_L, PO_L = (2, 1), (41, 1)


def name(n, sfx):
    return "FILLDENS%d%s" % (n, sfx)


def make_gds(src_path, out_path, sfx):
    """GDS with only the FILLDENS cells, built from the library's FILLER cells."""
    src = db.Layout()
    src.read(src_path)
    ly = db.Layout()
    ly.dbu = src.dbu
    dbu = ly.dbu
    for n in WIDTHS:
        f = src.cell("FILLER%d%s" % (n, sfx))
        if f is None:
            raise RuntimeError("%s: no FILLER%d%s" % (src_path, n, sfx))
        c = ly.create_cell(name(n, sfx))
        c.copy_tree(f)  # shapes of the filler (it has no sub cells)
        aa, po = ly.layer(*AA_L), ly.layer(*PO_L)
        for k in range(int(round(n * 0.2 / UNIT))):
            dx = k * UNIT
            for x1, y1, x2, y2 in AA:
                c.shapes(aa).insert(db.DBox(x1 + dx, y1, x2 + dx, y2).to_itype(dbu))
            for x1, y1, x2, y2 in PO:
                c.shapes(po).insert(db.DBox(x1 + dx, y1, x2 + dx, y2).to_itype(dbu))
    ly.write(out_path)


def make_lef(src_text, sfx):
    """Cell LEF with the FILLDENS macros: the FILLER macros renamed (same size, rails)."""
    out = ["VERSION 5.8 ;", 'BUSBITCHARS "[]" ;', 'DIVIDERCHAR "/" ;', ""]
    for n in WIDTHS:
        m = re.search(r"\nMACRO FILLER%d%s\n.*?\nEND FILLER%d%s\n" % (n, sfx, n, sfx), src_text, flags=re.S)
        if not m:
            raise RuntimeError("no MACRO FILLER%d%s" % (n, sfx))
        out.append(m.group(0).strip("\n").replace("FILLER%d%s" % (n, sfx), name(n, sfx)))
        out.append("")
    out.append("END LIBRARY")
    return "\n".join(out) + "\n"


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "stdcell_fixed")
    for lib, sfx in LIBS.items():
        d = os.path.join(root, lib)
        o = os.path.join(d, "filldens")
        os.makedirs(o, exist_ok=True)
        raw = os.path.join(o, "src.gds")
        with gzip.open(os.path.join(d, "gds", lib + ".gds.gz"), "rb") as f, open(raw, "wb") as w:
            w.write(f.read())
        make_gds(raw, os.path.join(o, lib + "_filldens.gds"), sfx)
        os.remove(raw)
        with gzip.open(os.path.join(d, "lef", lib + "_ecos.lef.gz"), "rt") as f:
            lef = make_lef(f.read(), sfx)
        with open(os.path.join(o, lib + "_filldens.lef"), "w") as f:
            f.write(lef)
        with open(os.path.join(o, lib + "_filldens.cdl"), "w") as f:
            f.write("* density filler cells (hacking/stdcell_fix/density_fill.py): no devices\n")
            for n in WIDTHS:
                f.write(".SUBCKT %s VDD VSS\n*.PININFO VDD:B VSS:B\n.ENDS\n\n" % name(n, sfx))
        print(lib, "->", o)


if __name__ == "__main__":
    main()
