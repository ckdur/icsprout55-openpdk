#!/usr/bin/env python3
"""Rewrite the geometry of a cell LEF from a (fixed) GDS.

The vendor LEF is the template: for every macro whose cell is in the GDS (and
in --cells, if given), SIZE, the PORT geometry of every pin and the OBS are
regenerated from the layout; everything else (CLASS, SITE, SYMMETRY, pin
DIRECTION / USE, antenna data, ...) is kept. Macros of other cells are copied.

Pin geometry, like the vendor LEFs:
  --pins m1 (plain LEF): the MET1 shape under the pin label (81/2).
  --pins m2 (_ecos LEF): signal pins: the MET2 shape under the label (82/6),
      the VIA1 in it and the MET1 shapes under those vias; power pins: the
      MET1 shape under the label (81/2).
OBS: MET1 that is not part of a pin (and MET2 / VIA1 not in a pin, if any).

Usage:
  python3 lef_from_gds.py <template.lef> <cells.gds> <out.lef> --pins m1|m2 [--cells A,B]
"""

import argparse
import re
import sys

import klayout.db as db

M1, M2, V1, BND = (81, 1), (82, 1), (91, 1), (351, 12)
LABEL = {'m1': {M1: [(81, 2), (81, 6)]}, 'm2': {M2: [(82, 6), (82, 2)], M1: [(81, 2), (81, 6)]}}
LEFNAME = {M1: 'MET1', M2: 'MET2', V1: 'VIA1'}


def fmt(v):
    s = f'{v:.4f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def rects(region, dbu):
    """Rectangles covering a Manhattan region (maximal horizontal slabs)."""
    out = []
    for p in region.merged().each():
        for t in p.decompose_trapezoids(db.Polygon.TD_htrapezoids):
            b = t.bbox()
            out.append((b.left * dbu, b.bottom * dbu, b.right * dbu, b.top * dbu))
    return out


def cell_geometry(layout, cell, pins_mode):
    """{pin: {layer: Region}}, {layer: Region} obs, size (w, h) in um."""
    dbu = layout.dbu

    def reg(lay):
        li = layout.find_layer(*lay)
        return db.Region(cell.begin_shapes_rec(li)).merged() if li is not None else db.Region()
    m1, m2, v1 = reg(M1), reg(M2), reg(V1)
    bnd = reg(BND).bbox()
    labels = {}
    for base, tl in LABEL[pins_mode].items():
        for lay in tl:
            li = layout.find_layer(*lay)
            if li is None:
                continue
            for s in cell.shapes(li).each():
                if s.is_text():
                    labels.setdefault(s.text.string, []).append((base, db.Point(s.text.x, s.text.y)))
    pins = {}
    for name, locs in labels.items():
        # signal pins of the _ecos view are on MET2, the rails on MET1
        if pins_mode == 'm2' and any(b == M2 for b, _ in locs):
            locs = [l for l in locs if l[0] == M2]
        geo = {}
        for base, pt in locs:
            src = {M1: m1, M2: m2}[base]
            hit = src.interacting(db.Region(db.Box(pt.x - 1, pt.y - 1, pt.x + 1, pt.y + 1)))
            if hit.is_empty():
                continue
            geo[base] = geo.get(base, db.Region()) + hit
            if base == M2:
                vias = v1.interacting(hit)
                geo[V1] = geo.get(V1, db.Region()) + vias
                geo[M1] = geo.get(M1, db.Region()) + m1.interacting(vias)
        if geo:
            pins[name] = {l: r.merged() for l, r in geo.items()}
    used = {M1: db.Region(), M2: db.Region(), V1: db.Region()}
    for geo in pins.values():
        for l, r in geo.items():
            used[l] += r
    obs = {M1: m1 - used[M1], M2: m2 - used[M2], V1: v1 - used[V1]}
    return pins, obs, ((bnd.right - bnd.left) * dbu, (bnd.top - bnd.bottom) * dbu), (bnd.left * dbu, bnd.bottom * dbu)


def port_text(geo, dbu, ox, oy, indent='      '):
    out = []
    for lay in (M1, M2, V1):
        if lay in geo and not geo[lay].is_empty():
            out.append(f'{indent}LAYER {LEFNAME[lay]} ;')
            for x1, y1, x2, y2 in rects(geo[lay], dbu):
                out.append(f'{indent}  RECT {fmt(x1 - ox)} {fmt(y1 - oy)} {fmt(x2 - ox)} {fmt(y2 - oy)} ;')
    return out


def rewrite_macro(text, layout, cell, pins_mode):
    dbu = layout.dbu
    pins, obs, (w, h), (ox, oy) = cell_geometry(layout, cell, pins_mode)
    lines = text.split('\n')
    out = []
    i = 0
    cur_pin = None
    missing = []
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s.startswith('SIZE '):
            out.append(re.sub(r'SIZE .*;', f'SIZE {fmt(w)} BY {fmt(h)} ;', ln))
        elif s.startswith('PIN '):
            cur_pin = s.split()[1]
            out.append(ln)
        elif s == 'PORT':
            # replace the port body
            out.append(ln)
            j = i + 1
            while lines[j].strip() != 'END':
                j += 1
            geo = pins.get(cur_pin)
            if geo:
                out.extend(port_text(geo, dbu, ox, oy))
            else:
                missing.append(cur_pin)
                out.extend(lines[i + 1:j])
            out.append(lines[j])
            i = j
        elif s == 'OBS':
            out.append(ln)
            j = i + 1
            while lines[j].strip() != 'END':
                j += 1
            out.extend(port_text(obs, dbu, ox, oy, '    '))
            out.append(lines[j])
            i = j
        else:
            out.append(ln)
        i += 1
    return '\n'.join(out), missing


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('template')
    p.add_argument('gds')
    p.add_argument('out')
    p.add_argument('--pins', choices=('m1', 'm2'), required=True)
    p.add_argument('--cells')
    a = p.parse_args()
    layout = db.Layout()
    layout.read(a.gds)
    only = set(a.cells.split(',')) if a.cells else None
    text = open(a.template).read()
    parts = re.split(r'(?m)^(MACRO \S+\s*\n.*?^END \S+\s*$)', text, flags=re.S)
    out, n, warn = [], 0, []
    for part in parts:
        m = re.match(r'MACRO (\S+)', part)
        if m and layout.cell(m.group(1)) is not None and (only is None or m.group(1) in only):
            new, missing = rewrite_macro(part, layout, layout.cell(m.group(1)), a.pins)
            out.append(new)
            n += 1
            if missing:
                warn.append(f'{m.group(1)}: {",".join(missing)}')
        else:
            out.append(part)
    open(a.out, 'w').write(''.join(out))
    print(f'{a.out}: {n} macros rewritten from {a.gds}')
    for w in warn:
        print(f'  pins kept from the template (no label / shape found): {w}')


if __name__ == '__main__':
    main()
