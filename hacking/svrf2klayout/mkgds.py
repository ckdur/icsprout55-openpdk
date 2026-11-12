"""Write a GDS file from a JSON description.

Usable both as a KLayout macro (klayout -b -r mkgds.py -rd spec=.. -rd out=..)
and with the pip 'klayout' module (python mkgds.py spec.json out.gds).

JSON format:
{ "top": "TOP", "dbu": 0.001,
  "cells": { "TOP": { "shapes": [ [layer, datatype, [[x,y],...]] | [layer, datatype, "box", x1,y1,x2,y2]
                                  | [layer, texttype, "text", "string", x, y] ],
                      "insts": [ ["CELL", dx, dy] ] } } }
coordinates in microns
"""
import json
import sys

try:
    import pya as db
except ImportError:
    import klayout.db as db


def build(spec):
    ly = db.Layout()
    ly.dbu = spec.get('dbu', 0.001)
    cells = {}
    for name in spec['cells']:
        cells[name] = ly.create_cell(name)
    layers = {}

    def li(l, d):
        if (l, d) not in layers:
            layers[(l, d)] = ly.layer(l, d)
        return layers[(l, d)]

    for name, c in spec['cells'].items():
        cell = cells[name]
        for s in c.get('shapes', []):
            l, d = s[0], s[1]
            if s[2] == 'box':
                x1, y1, x2, y2 = s[3:7]
                cell.shapes(li(l, d)).insert(db.DBox(x1, y1, x2, y2))
            elif s[2] == 'text':
                cell.shapes(li(l, d)).insert(db.DText(s[3], db.DTrans(db.DVector(s[4], s[5]))))
            else:
                pts = [db.DPoint(p[0], p[1]) for p in s[2]]
                cell.shapes(li(l, d)).insert(db.DPolygon(pts))
        for ins in c.get('insts', []):
            sub = cells[ins[0]]
            cell.insert(db.DCellInstArray(sub.cell_index(), db.DTrans(db.DVector(ins[1], ins[2]))))
    return ly


def main(spec_path, out):
    with open(spec_path) as f:
        spec = json.load(f)
    ly = build(spec)
    ly.write(out)


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        main(sys.argv[1], sys.argv[2])
    else:
        main(spec, out)  # noqa: F821  (set by klayout -rd)
