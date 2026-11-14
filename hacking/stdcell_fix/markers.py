#!/usr/bin/env python3
"""DRC markers of a check_cells.py run, per cell, in cell coordinates (dbu).

Markers KLayout reports in a library cell are in its coordinates already;
markers in the wrapper top cell (seam, row across the rail) are mapped into
every non-filler cell whose boundary they overlap (inverse instance
transformation), so a marker on the seam of A|B is listed for A and for B.
Context rules (latch-up, floating well, density) are dropped.

  markers(run_dir) -> {cell: [(rule, kind, geometry)]}
  kind 'ep': db.EdgePair, 'poly': db.Polygon, 'edge': db.Edge

Usage: python3 markers.py <run dir> [cell ...]     (prints them)
"""

import collections
import sys
from pathlib import Path

import klayout.db as db
import klayout.rdb as rdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify import CONTEXT  # noqa: E402

FILLER = 'FILLER'


def _geo(v, dbu):
    t = db.CplxTrans(dbu).inverted()
    if v.is_edge_pair():
        return 'ep', v.edge_pair().transformed(t)
    if v.is_polygon():
        return 'poly', v.polygon().transformed(t)
    if v.is_box():
        return 'poly', db.Polygon(v.box().transformed(t))
    if v.is_edge():
        return 'edge', v.edge().transformed(t)
    return None, None


def _group_edges(edges):
    """Edge markers (region checks report the outline of the violating gap as
    separate edges): chains of touching edges -> their bounding boxes."""
    n = len(edges)
    par = list(range(n))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    pts = {}
    for i, e in enumerate(edges):
        for p in (e.p1, e.p2):
            j = pts.setdefault((p.x, p.y), i)
            par[find(j)] = find(i)
    boxes = {}
    for i, e in enumerate(edges):
        r = find(i)
        boxes[r] = boxes.get(r, db.Box()) + e.bbox()
    return list(boxes.values())


def boxes(run_dir, topcell='ALL'):
    """{cell: [(rule, db.Box)]}: one box per violation (polygon marker bbox,
    or a chain of edge markers)."""
    out = {}
    for cell, items in markers(run_dir, topcell).items():
        res, edges = [], collections.defaultdict(list)
        for rule, kind, g in items:
            if kind == 'edge':
                edges[rule].append(g)
            else:
                res.append((rule, g.bbox()))
        for rule, es in edges.items():
            res += [(rule, b) for b in _group_edges(es)]
        out[cell] = res
    return out


def markers(run_dir, topcell='ALL'):
    run_dir = Path(run_dir)
    lay = db.Layout()
    lay.read(str(run_dir / 'drc_wrap.gds'))
    dbu = lay.dbu
    top = lay.cell(topcell)
    bnd = lay.find_layer(351, 12)
    cbnd = {}
    for ci in top.each_child_cell():
        c = lay.cell(ci)
        b = c.bbox_per_layer(bnd)
        cbnd[ci] = b if not b.empty() else c.bbox()
    rep = rdb.ReportDatabase('')
    rep.load(str(run_dir / 'drc.lyrdb'))
    out = collections.defaultdict(list)
    for cat in rep.each_category():
        if not cat.num_items() or CONTEXT.match(cat.name()):
            continue
        rule = cat.name()
        for it in rep.each_item_per_category(cat.rdb_id()):
            cell = rep.cell_by_id(it.cell_id()).name()
            for v in it.each_value():
                kind, g = _geo(v, dbu)
                if kind is None:
                    continue
                if cell != topcell:
                    out[cell].append((rule, kind, g))
                    continue
                box = g.bbox().enlarged(1, 1)
                for inst in top.each_overlapping_inst(box):
                    if inst.cell.name.startswith(FILLER):
                        continue
                    if not cbnd[inst.cell_index].transformed(inst.trans).overlaps(box):
                        continue
                    out[inst.cell.name].append((rule, kind, g.transformed(inst.trans.inverted())))
    return out


if __name__ == '__main__':
    m = markers(sys.argv[1])
    for cell in sys.argv[2:] or sorted(m):
        for rule, kind, g in m.get(cell, []):
            print(cell, rule, kind, g)
