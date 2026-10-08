#!/usr/bin/env python3
"""Build a layout + schematic pair to run LVS on a whole cell library at once.

The layout gets a new top cell "ALL" with every top cell of the library placed
in a grid (cells do not touch). The schematic is the library CDL plus a
.SUBCKT ALL that instantiates every cell with its own nets, so each cell is
compared as its own circuit pair.

Pins named in --shared (default VSS) use one common net in ALL: the substrate
is a single global net in the extracted layout, and with -rd tapless=true it is
joined to VSS inside every cell.

Usage:
  python3 lvs_wrap.py <library.gds> <library.cdl> <out.gds> <out.cdl> [--shared VSS,...]
"""

import re
import sys

import klayout.db as db

from wrap_lib import wrap


def subckt_pins(cdl_path):
    """Return {cell name: [pins]} from the .SUBCKT lines of a CDL (continuations joined)."""
    pins = {}
    lines = []
    with open(cdl_path, encoding='latin-1') as f:
        for line in f:
            if line.startswith('+') and lines:
                lines[-1] += ' ' + line[1:].strip()
            else:
                lines.append(line.rstrip('\n'))
    for line in lines:
        toks = line.split()
        if toks and toks[0].upper() == '.SUBCKT':
            pins.setdefault(toks[1].upper(), [t for t in toks[2:] if '=' not in t])
    return pins


def main(gds, cdl, out_gds, out_cdl, shared=('VSS',)):
    wrap(gds, out_gds)
    layout = db.Layout()
    layout.read(out_gds)
    cells = sorted(layout.cell(ci).name for ci in layout.cell('ALL').each_child_cell())
    pins = subckt_pins(cdl)
    with open(cdl, encoding='latin-1') as f:
        text = f.read()
    inst = []
    missing = []
    for i, name in enumerate(cells):
        if name.upper() not in pins:
            missing.append(name)
            continue
        nets = ' '.join(p if p.upper() in shared else f'I{i}_{re.sub(r"[^A-Za-z0-9_]", "_", p)}'
                        for p in pins[name.upper()])
        inst.append(f'XI{i} {nets} {name}')
    with open(out_cdl, 'w') as f:
        f.write(text)
        f.write('\n.SUBCKT ALL\n' + '\n'.join(inst) + '\n.ENDS\n')
    print(f'{out_cdl}: {len(inst)} instances' + (f', no schematic for {", ".join(missing)}' if missing else ''))


if __name__ == '__main__':
    args = sys.argv[1:]
    shared_pins = ('VSS',)
    if '--shared' in args:
        k = args.index('--shared')
        shared_pins = tuple(p.upper() for p in args[k + 1].split(','))
        del args[k:k + 2]
    if len(args) != 4:
        sys.exit(__doc__)
    main(*args, shared=shared_pins)
