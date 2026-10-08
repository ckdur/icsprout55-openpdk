#!/usr/bin/env python3
"""Place every top cell of a library GDS in a grid under a new top cell "ALL".

With a filler cell name as 3rd argument, each cell is abutted (using the
351/12 cell boundary) between two fillers, like in a placed row. This avoids
false NW/NP/PP errors from the well and implant overhang at the cell edges.

Usage:
  python3 wrap_lib.py <library.gds> <out.gds> [FILLER_CELL]
"""

import math
import sys

import klayout.db as db

GAP_UM = 10.0


def wrap(src, dst, filler=None):
    layout = db.Layout()
    layout.read(src)
    tops = sorted(layout.top_cells(), key=lambda c: c.name)
    top = layout.create_cell("ALL")
    bnd = layout.find_layer(351, 12)

    def boundary(c):
        b = c.bbox_per_layer(bnd) if bnd is not None else db.Box()
        return b if not b.empty() else c.bbox()

    gap = int(GAP_UM / layout.dbu)
    ncol = int(math.ceil(math.sqrt(len(tops))))
    fc = layout.cell(filler) if filler else None
    if filler and fc is None:
        sys.exit(f"Filler cell {filler} not found in {src}")
    fb = boundary(fc) if fc else db.Box()
    fw = fb.width() if fc else 0

    x = y = rowh = 0
    for i, c in enumerate(tops):
        if fc and c.name.startswith('FILL'):
            continue
        bb = boundary(c)
        cx = x + fw
        top.insert(db.CellInstArray(c.cell_index(), db.Trans(cx - bb.left, y - bb.bottom)))
        if fc:
            top.insert(db.CellInstArray(fc.cell_index(), db.Trans(x - fb.left, y - fb.bottom)))
            top.insert(db.CellInstArray(fc.cell_index(), db.Trans(cx + bb.width() - fb.left, y - fb.bottom)))
        x = cx + bb.width() + fw + gap
        rowh = max(rowh, bb.height())
        if (i + 1) % ncol == 0:
            x = 0
            y += rowh + gap
            rowh = 0
    layout.write(dst)
    print(f"{src}: {len(tops)} cells -> {dst}" + (f" (abutted with {filler})" if fc else ""))


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    wrap(*sys.argv[1:])
