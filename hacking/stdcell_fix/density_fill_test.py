#!/usr/bin/env python3
"""Test layout for the density filler cells (density_fill.py).

  python3 density_fill_test.py LIB_GDS FILLDENS_GDS SUFFIX UNUSABLE OUT.gds [--baseline]

Every usable cell of the library is placed in a row between FILLDENS4 cells, once as is and
once mirrored (MY), and the rows alternate with rows made of FILLDENS64 / 16 / 4 only, mirrored like a
placed design (R0 / MX), so FILLDENS meets every cell on its left / right and every cell meets
FILLDENS above / below. With --baseline the FILLDENS cells are replaced by the FILLER cells of
the same width: the markers that only appear without --baseline come from FILLDENS.
"""
import argparse

try:
    import klayout.db as db
except ImportError:
    import pya as db

ROW_H = 1.4
ROW_W = 120.0

ap = argparse.ArgumentParser()
ap.add_argument("lib_gds")
ap.add_argument("fd_gds")
ap.add_argument("sfx")
ap.add_argument("unusable")
ap.add_argument("out")
ap.add_argument("--baseline", action="store_true")
a = ap.parse_args()

ly = db.Layout()
ly.read(a.lib_gds)
ly.read(a.fd_gds)
dbu = ly.dbu
pb = ly.layer(351, 12)
unus = set(l.strip() for l in open(a.unusable) if l.strip())


def width(c):
    b = db.Region(c.shapes(pb)).bbox()
    return (b if not b.empty() else c.bbox()).width() * dbu


fd = "FILLER%d" + a.sfx if a.baseline else "FILLDENS%d" + a.sfx
fd4, fd16, fd64 = ly.cell(fd % 4), ly.cell(fd % 16), ly.cell(fd % 64)
cells = sorted((c for c in ly.each_cell() if c.name.endswith(a.sfx) and c.name not in unus
                and not c.name.startswith("FILLDENS") and c.child_instances() == 0
                and not db.Region(c.shapes(pb)).is_empty()), key=lambda c: c.name)
top = ly.create_cell("ALL")


def place(c, x, row, mirror_y=False):
    y = row * ROW_H
    if row % 2:  # MX row: rails shared with the rows below / above
        t = db.DCplxTrans(1, 180 if mirror_y else 0, not mirror_y, x + (width(c) if mirror_y else 0), y + ROW_H)
    else:
        t = db.DCplxTrans(1, 0, mirror_y, x + (width(c) if mirror_y else 0), y) if not mirror_y else \
            db.DCplxTrans(1, 180, True, x + width(c), y)
    top.insert(db.DCellInstArray(c.cell_index(), t))


def filler_row(row, w):
    x = 0.0
    while x + 12.8 <= w + 1e-6:
        place(fd64, x, row)
        x += 12.8
    while x + 3.2 <= w + 1e-6:
        place(fd16, x, row)
        x += 3.2
    while x + 0.8 <= w + 1e-6:
        place(fd4, x, row)
        x += 0.8


row = 0
filler_row(row, ROW_W)
row += 1
items = [(c, False) for c in cells] + [(c, True) for c in cells]
x = 0.0
place(fd4, x, row)
x += 0.8
for c, m in items:
    w = width(c)
    if x + w + 0.8 > ROW_W:
        # close the row with fillers up to ROW_W (multiples of 0.8 only)
        while x + 0.8 <= ROW_W + 1e-6:
            place(fd4, x, row)
            x += 0.8
        row += 1
        filler_row(row, ROW_W)
        row += 1
        x = 0.0
        place(fd4, x, row)
        x += 0.8
    place(c, x, row, m)
    x += w
    place(fd4, x, row)
    x += 0.8
while x + 0.8 <= ROW_W + 1e-6:
    place(fd4, x, row)
    x += 0.8
row += 1
filler_row(row, ROW_W)
ly.write(a.out)
print("%s: %d cells, %d rows -> %s" % ("baseline" if a.baseline else "filldens", len(cells), row + 1, a.out))
