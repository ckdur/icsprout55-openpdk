#!/usr/bin/env python3
"""Summarize a KLayout LVS database (lvsdb): match status of every circuit pair.

Usage:
  python3 lvs_summary.py <report.lvsdb> [--all]

Prints the counts per status and the circuits that do not match
(with --all, every circuit).
"""

import collections
import sys

import klayout.db as db

STATUS = {getattr(db.NetlistCrossReference, k): k.lower()
          for k in ('Match', 'MatchWithWarning', 'Mismatch', 'NoMatch', 'Skipped')}


def circuit_status(path):
    """Return {circuit name: status} for every circuit pair of the LVS database."""
    lvs = db.LayoutVsSchematic()
    lvs.read(path)
    result = {}
    for cp in lvs.xref().each_circuit_pair():
        a, b = cp.first(), cp.second()
        name = (a or b).name
        if not a:
            name += ' (schematic only)'
        elif not b:
            name += ' (layout only)'
        result[name] = STATUS.get(cp.status(), 'none')
    return result


def main(path, show_all):
    status = circuit_status(path)
    for st, n in collections.Counter(status.values()).most_common():
        print(f'{n:6d}  {st}')
    for name, st in sorted(status.items()):
        if show_all or st != 'match':
            print(f'  {st:20s} {name}')


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(sys.argv[1], '--all' in sys.argv[2:])
