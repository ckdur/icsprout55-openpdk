#!/usr/bin/env python3
"""Run the expanded Calibre antenna runset on the antenna test vehicle; print per rule the
cases that fail and the accumulated values (.rpt). Usage: run_calibre.py [gds] [top]"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import calibre_run as C
gds = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'ant_test.gds')
top = sys.argv[2] if len(sys.argv) > 2 else 'ANT'
deck = open(os.path.join(HERE, '..', '..', 'ICsprout_CalANT_expanded.svrf'), encoding='latin-1').read()
deck = re.sub(r'^\s*(LAYOUT (PATH|PRIMARY|SYSTEM)|DRC (RESULTS DATABASE|SUMMARY REPORT|MAXIMUM)).*$', '', deck, flags=re.M)
work = os.path.join(HERE, 'cal')
prec, res = C.run_calibre(deck, gds, top, workdir=work)
cases = json.load(open(os.path.join(HERE, 'cases.json'))) if top == 'ANT' else []
def case_of(x):
    return min(cases, key=lambda c: abs(c['x'] - x))['name'] if cases else str(x)
out = {}
for rule, items in sorted(res.items()):
    for kind, pts in items:
        xs = [p[0] for p in pts] if kind == 'p' else [pts[0][0]]
        out.setdefault(rule, []).append(case_of(min(xs)))
json.dump(out, open(os.path.join(HERE, 'calibre_result.json'), 'w'), indent=1, sort_keys=True)
for r, v in out.items():
    print('%-16s %s' % (r, ' '.join(v)))
