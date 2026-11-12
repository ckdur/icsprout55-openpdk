#!/usr/bin/env python3
"""
microtest.py RULES.svrf LAYOUT.gds [TOP] [--work DIR] [-v]

Run a small SVRF rule file (only LAYER statements and rule checks, no LAYOUT
directives) with Calibre, translate it with svrf2klayout and run it with
KLayout, then compare the results rule by rule.
"""
import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calibre_run as C  # noqa: E402
import klayout_run as K  # noqa: E402
import compare as M  # noqa: E402
import svrf2klayout as T  # noqa: E402


def run(rules, gds, top, work, verbose=False):
    os.makedirs(work, exist_ok=True)
    _, cal = C.run_calibre(open(rules).read(), gds, top, workdir=os.path.join(work, 'cal'))
    deck = os.path.join(work, 'deck.drc')
    T.generate(rules, deck, name='MICRO')
    kdb = os.path.join(work, 'kl.lyrdb')
    rc, log = K.run_klayout(deck, {'input': os.path.abspath(gds), 'topcell': top, 'report': kdb,
                                   'flat': '1', 'strict': '0'}, cwd=work)
    open(os.path.join(work, 'kl.log'), 'w').write(log)
    for l in log.split('\n'):
        if 'FAILED' in l or 'ERROR' in l:
            print(l)
    kl = K.parse_lyrdb(kdb)
    rows = M.compare(cal, kl, 2)
    bad = 0
    for n, nc, nk, hc, hk, ok in rows:
        if not ok:
            bad += 1
        print('%-20s cal=%4d kl=%4d %s' % (n, nc, nk, 'OK' if ok else 'DIFF'))
        if verbose or not ok:
            for g in cal.get(n, [])[:6]:
                print('     cal', g)
            for g in kl.get(n, [])[:6]:
                print('     kl ', g)
    return bad, rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('rules')
    ap.add_argument('gds')
    ap.add_argument('top', nargs='?', default='TOP')
    ap.add_argument('--work')
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    w = a.work or tempfile.mkdtemp(prefix='micro_')
    bad, _ = run(a.rules, a.gds, a.top, w, a.v)
    sys.exit(1 if bad else 0)
