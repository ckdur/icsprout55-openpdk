#!/usr/bin/env python3
"""Quick DRC (and optionally LVS) of a few cells of a standard cell library.

The listed cells are copied out of the library GDS (with the filler family),
placed in abutted rows like the regression does (wrap_lib.py) and checked with
tech/ics55.drc (markers listed per cell, "A|B" for a neighbour pair); with --cdl they are also compared one by one with tech/ics55.lvs
(lvs_wrap.py, -rd tapless=true). Takes seconds for a handful of cells.

Usage:
  python3 check_cells.py <library.gds> <CELL1,CELL2,...|all> [--cdl lib.cdl]
                         [--filler FILLER4H7R] [--run-dir DIR] [--items N]

  --filler   default: FILLER4<suffix> if the library has it, else the
             narrowest FILLER<n> cell
  --run-dir  default: testing/run/check_cells
  --items    also print the first N marker geometries of every rule
"""

import argparse
import re
import sys
from pathlib import Path

import klayout.db as db

from lvs_summary import circuit_status
from lvs_wrap import main as lvs_wrap
from run_regression import DRC_DECK, LVS_DECK, TESTING_DIR, run_klayout
from summary import summarize
from wrap_lib import wrap


def pick_filler(layout):
    fam = sorted((int(m.group(1)), c.name) for c in layout.top_cells()
                 if (m := re.fullmatch(r'FILLER(\d+)\D.*', c.name)))
    if not fam:
        sys.exit('No FILLER<n> cell in the library, pass --filler')
    four = [n for w, n in fam if w == 4]
    return four[0] if four else fam[0][1]


def extract(src, dst, cells, filler):
    """Write dst with only the given top cells and the filler family of src."""
    layout = db.Layout()
    layout.read(src)
    m = re.fullmatch(r'(\D+?)\d+(.*)', filler)
    fam = re.compile(re.escape(m.group(1)) + r'\d+' + re.escape(m.group(2))) if m else None
    names = {c.name for c in layout.top_cells()}
    unknown = [c for c in cells if c not in names]
    if unknown:
        sys.exit(f'Not in {src}: {", ".join(unknown)}')
    for c in list(layout.top_cells()):
        if c.name not in cells and c.name != filler and not (fam and fam.fullmatch(c.name)):
            layout.prune_cell(c.cell_index(), -1)
    layout.write(dst)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('gds')
    p.add_argument('cells')
    p.add_argument('--cdl')
    p.add_argument('--filler')
    p.add_argument('--run-dir', default=str(TESTING_DIR / 'run' / 'check_cells'))
    p.add_argument('--items', type=int, default=0)
    a = p.parse_args()

    run = Path(a.run_dir)
    run.mkdir(parents=True, exist_ok=True)
    layout = db.Layout()
    layout.read(a.gds)
    filler = a.filler or pick_filler(layout)
    if a.cells == 'all':
        cells = sorted(c.name for c in layout.top_cells())
    else:
        cells = a.cells.split(',')

    sub = run / 'cells.gds'
    extract(a.gds, str(sub), cells, filler)

    # DRC
    wrapper, report = run / 'drc_wrap.gds', run / 'drc.lyrdb'
    wrap(str(sub), str(wrapper), filler)
    run_klayout(['-r', str(DRC_DECK), '-rd', f'input={wrapper}', '-rd', 'topcell=ALL',
                 '-rd', f'report={report}', '-rd', f'log={run / "drc.log"}'])
    res = summarize(str(report), str(wrapper))
    print(f'DRC: {sum(sum(c.values()) for c in res.values())} markers ({report})')
    for rule, by_cell in sorted(res.items()):
        cells_txt = ', '.join(f'{c}:{n}' for c, n in by_cell.most_common(6))
        print(f'  {sum(by_cell.values()):6d}  {rule:18s} {cells_txt}')
    if a.items:
        from items import main as items
        items(str(report), set(res), a.items)

    # LVS
    if a.cdl:
        lvs_gds, lvs_cdl, lvsdb = run / 'lvs_wrap.gds', run / 'lvs_wrap.cdl', run / 'lvs.lvsdb'
        lvs_wrap(str(sub), a.cdl, str(lvs_gds), str(lvs_cdl))
        run_klayout(['-r', str(LVS_DECK), '-rd', f'input={lvs_gds}', '-rd', 'topcell=ALL',
                     '-rd', f'schematic={lvs_cdl}', '-rd', f'report={lvsdb}',
                     '-rd', f'log={run / "lvs.log"}', '-rd', 'tapless=true'])
        st = {c: s for c, s in circuit_status(str(lvsdb)).items() if c != 'ALL'}
        bad = {c: s for c, s in st.items() if s != 'match'}
        print(f'LVS: {len(st) - len(bad)} of {len(st)} cells match ({lvsdb})')
        for c, s in sorted(bad.items()):
            print(f'  {c}: {s}')


if __name__ == '__main__':
    main()
