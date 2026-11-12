#!/usr/bin/env python3
"""
Differential test: run the Calibre SVRF deck and the translated KLayout deck
on the same GDS and compare results rule by rule.

  compare.py --svrf expanded.svrf --drc ics55.drc --gds x.gds --top TOP --work dir
             [--select REGEX] [--skip-calibre] [--skip-klayout]

A Calibre marker is "matched" if some KLayout marker of the same rule has a
bounding box overlapping its bounding box (both grown by --tol dbu), and
vice versa.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calibre_run as C  # noqa: E402
import klayout_run as K  # noqa: E402


def calibre_deck(svrf_text, gds, top, db, select=None):
    t = svrf_text
    t = re.sub(r'^LAYOUT PRIMARY .*$', 'LAYOUT PRIMARY "%s"' % top, t, flags=re.M)
    t = re.sub(r'^LAYOUT PATH .*$', 'LAYOUT PATH "%s"' % os.path.abspath(gds), t, flags=re.M)
    t = re.sub(r'^DRC RESULTS DATABASE .*$', 'DRC RESULTS DATABASE "%s" ASCII' % db, t, flags=re.M)
    t = re.sub(r'^DRC SUMMARY REPORT .*$', 'DRC SUMMARY REPORT "%s.sum"' % db, t, flags=re.M)
    t = t.replace('DRC RESULTS DATABASE', 'DRC MAXIMUM RESULTS ALL\nDRC MAXIMUM VERTEX ALL\nDRC RESULTS DATABASE', 1)
    if select:
        t += '\nDRC SELECT CHECK %s\n' % select
    return t


def bbox(g):
    k, d = g
    if k == 'p':
        xs = [p[0] for p in d]
        ys = [p[1] for p in d]
    else:
        xs = [e[0] for e in d] + [e[2] for e in d]
        ys = [e[1] for e in d] + [e[3] for e in d]
    return (min(xs), min(ys), max(xs), max(ys))


def match(a, b, tol):
    """fraction of a markers overlapped by some b marker"""
    if not a:
        return 0, 0
    grid = {}
    G = 2000
    for i, bb in enumerate(b):
        for gx in range((bb[0] - tol) // G, (bb[2] + tol) // G + 1):
            for gy in range((bb[1] - tol) // G, (bb[3] + tol) // G + 1):
                grid.setdefault((gx, gy), []).append(bb)
    hit = 0
    for aa in a:
        found = False
        for gx in range((aa[0] - tol) // G, (aa[2] + tol) // G + 1):
            for gy in range((aa[1] - tol) // G, (aa[3] + tol) // G + 1):
                for bb in grid.get((gx, gy), []):
                    if bb[0] - tol <= aa[2] and aa[0] - tol <= bb[2] and bb[1] - tol <= aa[3] and aa[1] - tol <= bb[3]:
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            hit += 1
    return hit, len(a)


def cal_markers(items):
    out = []
    for k, d in items:
        if k == 'e' and len(d) > 1:
            out.append(bbox(('e', d)))
        else:
            out.append(bbox((k, d)))
    return out


def kl_markers(items):
    out = []
    for g in items:
        k, d = g
        out.append(bbox(('p' if k == 'p' else 'e', d)))
    return out


def compare(cal, kl, tol=5, rules=None):
    names = sorted(set(cal) | set(kl)) if rules is None else rules
    rows = []
    for n in names:
        c = cal_markers(cal.get(n, []))
        k = kl_markers(kl.get(n, []))
        hc, nc = match(c, k, tol)
        hk, nk = match(k, c, tol)
        ok = (hc == nc and hk == nk)
        rows.append((n, nc, nk, hc, hk, ok))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--svrf', required=True)
    ap.add_argument('--drc', required=True)
    ap.add_argument('--gds', required=True)
    ap.add_argument('--top', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--select')
    ap.add_argument('--skip-calibre', action='store_true')
    ap.add_argument('--skip-klayout', action='store_true')
    ap.add_argument('--tol', type=int, default=5)
    ap.add_argument('--rd', action='append', default=[])
    ap.add_argument('--all', action='store_true', help='print matching rules too')
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    work = os.path.abspath(a.work)
    cdb = os.path.join(work, 'cal', 'out.db')
    if not a.skip_calibre:
        txt = calibre_deck(open(a.svrf, encoding='latin-1').read(), a.gds, a.top, cdb)
        C.run_calibre(txt, a.gds, a.top, workdir=os.path.join(work, 'cal'), header=False)
    _, cal = C.parse_ascii_db(cdb)
    kdb = os.path.join(work, 'kl.lyrdb')
    if not a.skip_klayout:
        rd = {'input': os.path.abspath(a.gds), 'topcell': a.top, 'report': kdb, 'thr': '16', 'flat': '1'}
        if a.select:
            rd['select'] = a.select
        for x in a.rd:
            k, v = x.split('=', 1)
            rd[k] = v
        rc, log = K.run_klayout(a.drc, rd, cwd=work)
        open(os.path.join(work, 'kl.log'), 'w').write(log)
    kl = K.parse_lyrdb(kdb)
    rules = None
    if a.select:
        rx = re.compile(a.select)
        rules = sorted(n for n in set(cal) | set(kl) if rx.search(n))
    rows = compare(cal, kl, a.tol, rules)
    nbad = 0
    for n, nc, nk, hc, hk, ok in rows:
        if not ok:
            nbad += 1
        if not ok or a.all:
            print('%-28s cal=%5d kl=%5d  cal_matched=%5d kl_matched=%5d %s' % (n, nc, nk, hc, hk, 'OK' if ok else 'DIFF'))
    nact = sum(1 for r in rows if r[1] or r[2])
    print('rules compared: %d, with markers: %d, mismatching: %d' % (len(rows), nact, nbad))
    json.dump(rows, open(os.path.join(work, 'compare.json'), 'w'))


if __name__ == '__main__':
    main()
