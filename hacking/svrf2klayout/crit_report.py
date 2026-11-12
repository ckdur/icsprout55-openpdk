#!/usr/bin/env python3
"""
crit_report.py WORKDIR TILES.json [out.md]

WORKDIR is a compare.py work directory run on the critical GDS.
For every rule with critical tiles, counts the markers of that rule inside
each tile for Calibre and KLayout and classifies:
  CRITICAL-OK : Calibre triggers on fail tile, not on pass tile, KLayout identical
  AGREE       : KLayout behaves like Calibre on all tiles (but Calibre itself
                does not show the clean pass/fail pattern, e.g. witness incomplete)
  DIFF        : KLayout and Calibre differ on at least one tile
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calibre_run as C  # noqa: E402
import klayout_run as K  # noqa: E402
import compare as M  # noqa: E402


def inside(bb, t):
    return bb[0] >= t[0] - 0.001 and bb[1] >= t[1] - 0.001 and bb[2] <= t[2] + 0.001 and bb[3] <= t[3] + 0.001


def main():
    w, tf = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    tiles = json.load(open(tf))
    _, cal = C.parse_ascii_db(os.path.join(w, 'cal', 'out.db'))
    kl = K.parse_lyrdb(os.path.join(w, 'kl.lyrdb'))
    rows = []
    summ = {'CRITICAL-OK': 0, 'AGREE': 0, 'DIFF': 0}
    for rule, tl in sorted(tiles.items()):
        cm = [tuple(x / 1000.0 for x in b) for b in M.cal_markers(cal.get(rule, []))]
        km = [tuple(x / 1000.0 for x in b) for b in M.kl_markers(kl.get(rule, []))]
        res = []
        same = True
        crit = True
        for kind, x1, y1, x2, y2 in tl:
            t = (x1, y1, x2, y2)
            nc = sum(1 for b in cm if inside(b, t))
            nk = sum(1 for b in km if inside(b, t))
            res.append((kind, nc, nk))
            if (nc > 0) != (nk > 0):
                same = False
            if kind == 'pass' and nc > 0:
                crit = False
            if kind == 'fail' and nc == 0:
                crit = False
        cls = 'DIFF' if not same else ('CRITICAL-OK' if crit else 'AGREE')
        summ[cls] += 1
        rows.append((rule, cls, res))
    lines = ['| rule | result | pass tile (cal/kl) | fail tile (cal/kl) |', '|---|---|---|---|']
    for rule, cls, res in rows:
        p = ' '.join('%d/%d' % (a, b) for k, a, b in res if k == 'pass')
        f = ' '.join('%d/%d' % (a, b) for k, a, b in res if k == 'fail')
        lines.append('| %s | %s | %s | %s |' % (rule, cls, p, f))
    txt = '\n'.join(lines)
    if out:
        open(out, 'w').write(txt + '\n')
    for rule, cls, res in rows:
        if cls == 'DIFF':
            print('DIFF', rule, res)
    print(summ)


if __name__ == '__main__':
    main()
