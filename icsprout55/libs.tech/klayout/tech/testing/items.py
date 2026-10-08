#!/usr/bin/env python3
"""Print the marker geometries of some rules from a KLayout DRC report database (lyrdb).

Usage:
  python3 items.py <report.lyrdb> <RULE1,RULE2,...> [max markers per rule, default 4]
"""

import sys

import klayout.db  # noqa: F401  (binds the geometry types returned by rdb values)
import klayout.rdb as rdb


def main(path, rules, nmax):
    db = rdb.ReportDatabase("")
    db.load(path)
    for cat in db.each_category():
        if cat.name() not in rules:
            continue
        print('==', cat.name(), cat.description)
        for i, it in enumerate(db.each_item_per_category(cat.rdb_id())):
            if i >= nmax:
                break
            for v in it.each_value():
                s = v.string()
                if v.is_polygon():
                    p = v.polygon()
                    s = f"area={p.area():.5f} bbox={p.bbox()} {s[:80]}"
                print('  ', db.cell_by_id(it.cell_id()).name(), s[:200])


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2].split(','), int(sys.argv[3]) if len(sys.argv) == 4 else 4)
