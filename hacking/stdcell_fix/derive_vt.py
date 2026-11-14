#!/usr/bin/env python3
"""Derive the fixed HVT / LVT library from the fixed RVT one.

The three 7-track libraries have the same layout per cell except the Vt
implant layers, which in every vendor cell are copies of the N+ / P+ implants
(H7CH: 21/1 = NP, 22/1 = PP; H7CL: 17/1 = NP, 18/1 = PP). A fixed variant cell
is the fixed H7CR cell (renamed, suffix H7R -> H7H / H7L) plus, per Vt layer of
the variant, a copy of the implant it equals in the vendor cell, taken from the
fixed cell (so it follows the moved AA and the re-solved NP / PP boundary).
A Vt layer that equals neither implant keeps the variant's shapes, stretched to
the new cell width (points on or right of the original right boundary move).
Cells the fixed H7CR library does not have (or --keep) are copied unchanged
from the variant.

Usage:
  python3 derive_vt.py <fixed_H7CR.gds> <orig_H7CR.gds> <orig_variant.gds> <out.gds> <suffix> [--keep A,B]
"""

import argparse
import sys

import klayout.db as db

BND = (351, 12)
VT = [(17, 1), (18, 1), (19, 1), (20, 1), (21, 1), (22, 1)]
IMPLANTS = [(52, 1), (53, 1)]   # NP, PP


def bnd_box(layout, cell):
    li = layout.find_layer(*BND)
    return db.Region(cell.begin_shapes_rec(li)).bbox()


def stretch(poly, x_from, dx):
    pts = [db.Point(p.x + dx if p.x >= x_from else p.x, p.y) for p in poly.each_point_hull()]
    return db.Polygon(pts)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('fixed')
    p.add_argument('orig_r')
    p.add_argument('orig_v')
    p.add_argument('out')
    p.add_argument('suffix')          # H7H or H7L
    p.add_argument('--keep', default='')
    a = p.parse_args()
    keep = set(a.keep.split(',')) if a.keep else set()
    fx, orr, ov = db.Layout(), db.Layout(), db.Layout()
    fx.read(a.fixed)
    orr.read(a.orig_r)
    ov.read(a.orig_v)
    out = db.Layout()
    out.dbu = ov.dbu
    n_fixed = n_copied = n_copy = n_stretch = 0
    for vc in sorted(ov.top_cells(), key=lambda c: c.name):
        rname = vc.name[:-3] + 'H7R' if vc.name.endswith(a.suffix) else None
        fc = fx.cell(rname) if rname else None
        oc = orr.cell(rname) if rname else None
        c = out.create_cell(vc.name)
        if fc is None or oc is None or vc.name in keep:
            c.copy_tree(vc)
            n_copied += 1
            continue
        b0 = bnd_box(orr, oc)
        b1 = bnd_box(fx, fc)
        dx = b1.right - b0.right
        if bnd_box(ov, vc) != b0:
            sys.exit(f'{vc.name}: boundary differs from {rname}')
        # fixed RVT geometry (no Vt layers there)
        for li in fx.layer_indexes():
            info = fx.get_info(li)
            dst = out.layer(info.layer, info.datatype)
            it = fc.begin_shapes_rec(li)
            while not it.at_end():
                c.shapes(dst).insert(it.shape(), it.trans())
                it.next()
        # Vt layers: the fixed implant they copy in the vendor cell, else stretched
        for lay in VT:
            li = ov.find_layer(*lay)
            if li is None:
                continue
            vt = db.Region(vc.begin_shapes_rec(li)).merged()
            if vt.is_empty():
                continue
            dst = out.layer(*lay)
            imp = next((L for L in IMPLANTS if ov.find_layer(*L) is not None
                        and (vt ^ db.Region(vc.begin_shapes_rec(ov.find_layer(*L))).merged()).is_empty()), None)
            if imp is not None:
                c.shapes(dst).insert(db.Region(fc.begin_shapes_rec(fx.find_layer(*imp))).merged())
                n_copy += 1
            else:
                for poly in vt.each():
                    c.shapes(dst).insert(stretch(poly, b0.right, dx))
                n_stretch += 1
        n_fixed += 1
    out.write(a.out)
    print(f'{a.out}: {n_fixed} cells from {a.fixed} (Vt layers: {n_copy} from the implant, {n_stretch} stretched), '
          f'{n_copied} copied from {a.orig_v}')


if __name__ == '__main__':
    main()
