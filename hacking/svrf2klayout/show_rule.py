#!/usr/bin/env python3
"""show_rule.py WORKDIR RULE [N] : print markers from calibre and klayout"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calibre_run as C, klayout_run as K
w, rule = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
_, cal = C.parse_ascii_db(os.path.join(w, 'cal', 'out.db'))
kl = K.parse_lyrdb(os.path.join(w, 'kl.lyrdb'))
print('CALIBRE', len(cal.get(rule, [])))
for g in cal.get(rule, [])[:n]: print('  ', g)
print('KLAYOUT', len(kl.get(rule, [])))
for g in kl.get(rule, [])[:n]: print('  ', g)
