#!/usr/bin/env python3
"""Place every top cell of a library GDS under a new top cell "ALL".

Two layouts:

- abut (default, needs a filler cell): like a placed design. The cells are
  packed into rows of about equal width and abut each other directly (using
  the 351/12 cell boundary); every other row is mirrored so neighbouring rows
  share their rail and well / implant edge. Each row starts and ends with the
  filler, is padded with fillers to the common row width, and a row of fillers
  is added below and above, so no library cell sits at the edge of the block.
  Every other cell of a row is mirrored left / right, as a placer does, so
  cells also meet with their edges reversed. The FILLER<n> cells of the family
  of the filler are not placed as cells.
- grid (--grid): every cell on its own with a gap of GAP_UM around it, so cells
  do not interact (LVS wrapper). With a filler, each cell is abutted between
  two fillers and every FILL* cell is skipped (the former DRC wrapper).

Options of the abutted layout, to vary which cells become neighbours:
  --order name|reverse|shuffle=SEED   order of the cells in the rows (default name)
  --no-flip                           do not mirror every other cell left / right

Usage:
  python3 wrap_lib.py <library.gds> <out.gds> [FILLER_CELL] [--grid] [--order O] [--no-flip]
"""

import math
import random
import re
import sys

import klayout.db as db

GAP_UM = 10.0


def _boundary_fn(layout):
    bnd = layout.find_layer(351, 12)

    def boundary(c):
        b = c.bbox_per_layer(bnd) if bnd is not None else db.Box()
        return b if not b.empty() else c.bbox()
    return boundary


def _filler_family(layout, filler, boundary):
    """FILLER<n> cells with the same prefix / suffix as filler, widest first."""
    m = re.fullmatch(r'(\D+?)\d+(.*)', filler)
    if not m:
        return [layout.cell(filler)]
    pat = re.compile(re.escape(m.group(1)) + r'\d+' + re.escape(m.group(2)))
    fam = [c for c in layout.top_cells() if pat.fullmatch(c.name)]
    return sorted(fam, key=lambda c: -boundary(c).width())


def wrap_grid(layout, top, filler, boundary):
    tops = sorted((c for c in layout.top_cells() if c.name != 'ALL'), key=lambda c: c.name)
    gap = int(GAP_UM / layout.dbu)
    ncol = int(math.ceil(math.sqrt(len(tops))))
    fc = layout.cell(filler) if filler else None
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
    return len(tops)


def wrap_abut(layout, top, filler, boundary, order='name', flip=True):
    fillers = _filler_family(layout, filler, boundary)
    skip = {c.name for c in fillers}
    fc = layout.cell(filler)
    cells = sorted((c for c in layout.top_cells() if c.name != 'ALL' and c.name not in skip),
                   key=lambda c: c.name)
    if order == 'reverse':
        cells.reverse()
    elif order.startswith('shuffle='):
        random.Random(int(order.split('=', 1)[1])).shuffle(cells)
    elif order != 'name':
        sys.exit(f'Unknown order {order}')
    h = boundary(fc).height()
    odd = [c.name for c in cells if boundary(c).height() != h]
    if odd:
        sys.exit(f'Cells with another height than {filler}: {", ".join(odd)}')

    # Rows of about equal width, block roughly square
    total = sum(boundary(c).width() for c in cells)
    target = max(math.sqrt(total * h), max(boundary(c).width() for c in cells))
    rows, row, w = [], [], 0
    for c in cells:
        cw = boundary(c).width()
        if row and w + cw > target:
            rows.append(row)
            row, w = [], 0
        row.append(c)
        w += cw
    if row:
        rows.append(row)
    place_rows(layout, top, filler, boundary,
               [[(c, flip and j % 2 == 1) for j, c in enumerate(r)] for r in rows])
    return len(cells)


def place_rows(layout, top, filler, boundary, rows):
    """Place rows of (cell, mirrored left / right) abutted, each row between two
    fillers, padded with the filler family, a filler row below and above, every
    other row mirrored. Returns [(y, [(instance, x_left, x_right), ...]), ...]
    per row in dbu."""
    fillers = _filler_family(layout, filler, boundary)
    fc = layout.cell(filler)
    fw = boundary(fc).width()
    h = boundary(fc).height()
    width = max(sum(boundary(c).width() for c, _ in r) for r in rows) + 2 * fw
    placed = []

    def place(c, x, k, fx=False):
        """Cell c with its boundary at x in row k (row 0 at y=0, odd rows mirrored),
        mirrored left / right with fx."""
        bb = boundary(c)
        y = k * h
        dx = x + bb.right if fx else x - bb.left
        if k % 2:
            t = db.Trans(db.Trans.R180 if fx else db.Trans.M0, dx, y + bb.top)
        else:
            t = db.Trans(db.Trans.M90 if fx else db.Trans.R0, dx, y - bb.bottom)
        inst = top.insert(db.CellInstArray(c.cell_index(), t))
        placed.append((inst, x, x + bb.width()))
        return x + bb.width()

    def pad(x, k):
        """Fill row k from x up to the block width with the filler family."""
        for f in fillers:
            fwid = boundary(f).width()
            while width - x >= fwid:
                x = place(f, x, k)
        if x != width:
            sys.exit(f'Row {k}: {(width - x) * layout.dbu:.3f} um left that no filler fits')

    result = []
    pad(0, 0)
    for k, r in enumerate(rows, start=1):
        x = place(fc, 0, k)
        placed.clear()
        for c, fx in r:
            x = place(c, x, k, fx)
        result.append((k * h, list(placed)))
        x = place(fc, x, k)
        pad(x, k)
    pad(0, len(rows) + 1)
    return result


def wrap(src, dst, filler=None, grid=False, order='name', flip=True):
    layout = db.Layout()
    layout.read(src)
    if filler and layout.cell(filler) is None:
        sys.exit(f'Filler cell {filler} not found in {src}')
    if not grid and not filler:
        sys.exit('The abutted wrapper needs a filler cell (or use --grid)')
    boundary = _boundary_fn(layout)
    top = layout.create_cell('ALL')
    if grid:
        n = wrap_grid(layout, top, filler, boundary)
        how = f' (grid, abutted with {filler})' if filler else ' (grid)'
    else:
        n = wrap_abut(layout, top, filler, boundary, order, flip)
        how = f' (abutted rows, filler {filler}, order {order}{", flipped" if flip else ""})'
    layout.write(dst)
    print(f'{src}: {n} cells -> {dst}{how}')


if __name__ == '__main__':
    args = sys.argv[1:]
    use_grid = '--grid' in args
    if use_grid:
        args.remove('--grid')
    use_flip = '--no-flip' not in args
    if not use_flip:
        args.remove('--no-flip')
    cell_order = 'name'
    if '--order' in args:
        k = args.index('--order')
        cell_order = args[k + 1]
        del args[k:k + 2]
    if len(args) not in (2, 3):
        sys.exit(__doc__)
    wrap(*args, grid=use_grid, order=cell_order, flip=use_flip)
