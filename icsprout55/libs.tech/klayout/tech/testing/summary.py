#!/usr/bin/env python3
"""Summarize a KLayout DRC report database (lyrdb): markers per rule and the cells they fall in.

Usage:
  python3 summary.py <report.lyrdb>
"""

import collections
import sys

import klayout.rdb as rdb


def summarize(path):
    """Return {rule: Counter(cell -> markers)} for every rule with markers."""
    db = rdb.ReportDatabase("")
    db.load(path)
    result = {}
    for cat in db.each_category():
        if not cat.num_items():
            continue
        result[cat.name()] = collections.Counter(
            db.cell_by_id(it.cell_id()).name()
            for it in db.each_item_per_category(cat.rdb_id()))
    return result


def main(path):
    for rule, cells in summarize(path).items():
        examples = ', '.join(c for c, _ in cells.most_common(4))
        print(f"{sum(cells.values()):6d}  {rule:16s} cells={len(cells):4d}  e.g. {examples}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
