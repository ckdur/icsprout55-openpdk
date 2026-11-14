#!/usr/bin/env python3
"""DRC of the cells of a standard cell library at the edges of a row block.

NP / PP / NW of the 7-track cells extend past the cell boundary and are only
complete with a neighbour on all four sides, which the regression wrapper
(wrap_lib.py) always provides. In a placed design the cells at a row end and
in the top / bottom row of the core (or next to a macro) have no neighbour
there. This places every cell on its own, as placed (R0) and mirrored left /
right (MY), with gaps around it, between two endcap cells (or none), and with
a row of FILLER1 (mirrored, sharing the rail) above and / or below, then runs
tech/ics55.drc and lists the markers per cell ("A|B" for the cell and its
endcap / filler neighbour).

The PDK closes the rows with the plain fillers (LibreLane ENDCAP_CELL and
ENDCAP_HORIZONTAL_CELLS with ICS55.TapEndcapInsertion), which is
"--endcap FILLER1<suffix> --cover both" (the default).

Usage:
  python3 rowend_check.py <library.gds> [CELL1,CELL2,...|all] [--endcap CELL|none]
                          [--cover both|above|below|none] [--exclude FILE]
                          [--run-dir DIR]

  --exclude  file with cell names (one per line, e.g. stdcell_fixed/<lib>/unusable.cells)
             that are not checked
  --run-dir  default: testing/run/rowend_check
"""

import argparse
import math
import re
import sys
from pathlib import Path

import klayout.db as db

from run_regression import DRC_DECK, TESTING_DIR, run_klayout
from summary import summarize

GAP_UM = 6.0
CONTEXT = re.compile(r'LU_S_2.*|.*_D_\d+.*|NW1_R_1|CHIPEDGE.*')


def build(src, dst, cells, endcap, cover):
    layout = db.Layout()
    layout.read(src)
    bnd = layout.find_layer(351, 12)

    def box(c):
        b = c.bbox_per_layer(bnd) if bnd is not None else db.Box()
        return b if not b.empty() else c.bbox()

    fam = re.compile(r'FILLER\d+' + re.escape(re.fullmatch(r'\D+\d+(.*)', endcap or 'FILLER1').group(1))
                     if endcap else r'FILLER\d+\D.*')
    fill1 = next((c for c in layout.top_cells() if re.fullmatch(r'FILLER1\D.*', c.name)), None)
    if cover != 'none' and fill1 is None:
        sys.exit('No FILLER1 cell for the filler rows')
    ec = layout.cell(endcap) if endcap else None
    if endcap and ec is None:
        sys.exit(f'Endcap {endcap} not in {src}')
    top = layout.create_cell('ALL')
    eb = box(ec) if ec else db.Box()
    ew = eb.width() if ec else 0
    gap = int(GAP_UM / layout.dbu)
    todo = [layout.cell(n) for n in cells if not fam.fullmatch(n)]
    ncol = max(1, int(math.sqrt(2 * len(todo))))
    x = y = rowh = 0
    k = 0
    for c in todo:
        bb = box(c)
        h = bb.height()
        for mirrored in (False, True):
            cx = x + ew
            if ec:
                top.insert(db.CellInstArray(ec.cell_index(), db.Trans(x - eb.left, y - eb.bottom)))
                top.insert(db.CellInstArray(ec.cell_index(), db.Trans(cx + bb.width() - eb.left, y - eb.bottom)))
            if mirrored:
                t = db.Trans(db.Trans.M90, cx + bb.right, y - bb.bottom)
            else:
                t = db.Trans(db.Trans.R0, cx - bb.left, y - bb.bottom)
            top.insert(db.CellInstArray(c.cell_index(), t))
            if cover != 'none':
                fb = box(fill1)
                for xx in range(x, cx + bb.width() + ew, fb.width()):
                    if cover in ('both', 'above'):
                        top.insert(db.CellInstArray(fill1.cell_index(),
                                                    db.Trans(db.Trans.M0, xx - fb.left, y + 2 * h - fb.bottom)))
                    if cover in ('both', 'below'):
                        top.insert(db.CellInstArray(fill1.cell_index(),
                                                    db.Trans(db.Trans.M0, xx - fb.left, y + fb.bottom)))
            x = cx + bb.width() + ew + gap
            rowh = max(rowh, 3 * h)
            k += 1
            if k % ncol == 0:
                x = 0
                y += rowh + gap
                rowh = 0
    layout.write(dst)
    return len(todo)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('gds')
    p.add_argument('cells', nargs='?', default='all')
    p.add_argument('--endcap', help='default: FILLER1<suffix> of the library, "none" for no endcap')
    p.add_argument('--cover', default='both', choices=('both', 'above', 'below', 'none'))
    p.add_argument('--exclude')
    p.add_argument('--run-dir', default=str(TESTING_DIR / 'run' / 'rowend_check'))
    a = p.parse_args()

    run = Path(a.run_dir)
    run.mkdir(parents=True, exist_ok=True)
    layout = db.Layout()
    layout.read(a.gds)
    names = sorted(c.name for c in layout.top_cells())
    cells = names if a.cells == 'all' else a.cells.split(',')
    unknown = [c for c in cells if c not in names]
    if unknown:
        sys.exit(f'Not in {a.gds}: {", ".join(unknown)}')
    if a.exclude:
        skip = {l.strip() for l in open(a.exclude) if l.strip() and not l.startswith('#')}
        cells = [c for c in cells if c not in skip]
    if a.endcap == 'none':
        endcap = None
    elif a.endcap:
        endcap = a.endcap
    else:
        endcap = next((n for n in names if re.fullmatch(r'FILLER1\D.*', n)), None)
        if endcap is None:
            sys.exit('No FILLER1 cell in the library, pass --endcap')

    wrapper, report = run / 'rowend.gds', run / 'drc.lyrdb'
    n = build(a.gds, str(wrapper), cells, endcap, a.cover)
    print(f'{n} cells, endcap {endcap or "none"}, filler rows: {a.cover} -> {wrapper}')
    run_klayout(['-r', str(DRC_DECK), '-rd', f'input={wrapper}', '-rd', 'topcell=ALL',
                 '-rd', f'report={report}', '-rd', f'log={run / "drc.log"}'])
    res = summarize(str(report), str(wrapper))
    real = {r: c for r, c in res.items() if not CONTEXT.fullmatch(r)}
    print(f'DRC: {sum(sum(c.values()) for c in real.values())} markers besides latch-up / density / '
          f'NW1_R_1 ({report})')
    for rule, by_cell in sorted(real.items()):
        cells_txt = ', '.join(f'{c}:{k}' for c, k in by_cell.most_common(6))
        print(f'  {sum(by_cell.values()):6d}  {rule:18s} {len(by_cell):4d} cells  {cells_txt}')
    return 1 if real else 0


if __name__ == '__main__':
    sys.exit(main())
