#!/usr/bin/env python3
"""Summarize a KLayout DRC report database (lyrdb): markers per rule and the cells they fall in.

With the wrapper layout (wrap_lib.py), markers that KLayout reports in the
wrapper top cell (they depend on geometry outside one cell, e.g. a neighbour or
the implant of the row across the rail) are assigned to the cells whose
boundary (351/12) they overlap: one cell -> that cell, two cells -> "A|B"
(names sorted), none or more than two (density windows, latch-up regions) ->
the top cell. FILLER<n> cells do not count.

Usage:
  python3 summary.py <report.lyrdb> [wrapper.gds [TOPCELL]]
"""

import collections
import re
import sys

import klayout.db as db
import klayout.rdb as rdb

FILLER_RE = re.compile(r'FILLER\d')


def _value_box(v):
    """Bounding box (um) of the geometry of an rdb value, or None."""
    if v.is_polygon():
        return v.polygon().bbox()
    if v.is_box():
        return v.box()
    if v.is_edge_pair():
        return v.edge_pair().bbox()
    if v.is_edge():
        return v.edge().bbox()
    if v.is_path():
        return v.path().bbox()
    return None


class Attributor:
    """Maps a marker box in the wrapper top cell to the cell (or pair) it belongs to."""

    def __init__(self, gds, topcell='ALL'):
        self.layout = db.Layout()
        self.layout.read(gds)
        self.top = self.layout.cell(topcell)
        self.topcell = topcell
        bnd = self.layout.find_layer(351, 12)
        self.cell_bnd = {}   # cell index -> boundary box in the cell
        for ci in self.top.each_child_cell():
            c = self.layout.cell(ci)
            b = c.bbox_per_layer(bnd) if bnd is not None else db.Box()
            self.cell_bnd[ci] = b if not b.empty() else c.bbox()

    def __call__(self, dbox):
        dbu = self.layout.dbu
        box = db.Box(round(dbox.left / dbu), round(dbox.bottom / dbu),
                     round(dbox.right / dbu), round(dbox.top / dbu))
        if box.width() == 0 or box.height() == 0:
            box = box.enlarged(1, 1)
        names = set()
        for inst in self.top.each_overlapping_inst(box):
            name = inst.cell.name
            if FILLER_RE.match(name):
                continue
            b = self.cell_bnd[inst.cell_index].transformed(inst.trans)
            if b.overlaps(box):
                names.add(name)
                if len(names) > 2:
                    return self.topcell
        if not names:
            return self.topcell
        return '|'.join(sorted(names))


def summarize(path, wrapper=None, topcell='ALL'):
    """Return {rule: Counter(cell or "A|B" -> markers)} for every rule with markers."""
    rep = rdb.ReportDatabase("")
    rep.load(path)
    attr = Attributor(wrapper, topcell) if wrapper else None
    result = {}
    for cat in rep.each_category():
        if not cat.num_items():
            continue
        cnt = collections.Counter()
        for it in rep.each_item_per_category(cat.rdb_id()):
            cell = rep.cell_by_id(it.cell_id()).name()
            if attr and cell == topcell:
                for v in it.each_value():
                    b = _value_box(v)
                    if b is not None:
                        cell = attr(b)
                        break
            cnt[cell] += 1
        result[cat.name()] = cnt
    return result


def main(path, wrapper=None, topcell='ALL'):
    for rule, cells in summarize(path, wrapper, topcell).items():
        examples = ', '.join(c for c, _ in cells.most_common(4))
        print(f"{sum(cells.values()):6d}  {rule:16s} cells={len(cells):4d}  e.g. {examples}")


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3, 4):
        sys.exit(__doc__)
    main(*sys.argv[1:])
