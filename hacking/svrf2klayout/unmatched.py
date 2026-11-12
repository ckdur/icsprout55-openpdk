#!/usr/bin/env python3
"""unmatched.py WORKDIR RULE [N]: print unmatched markers on both sides"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calibre_run as C, klayout_run as K, compare as M
w, r = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
_, cal = C.parse_ascii_db(os.path.join(w, 'cal', 'out.db'))
kl = K.parse_lyrdb(os.path.join(w, 'kl.lyrdb'))
c = M.cal_markers(cal.get(r, [])); k = M.kl_markers(kl.get(r, []))
print('-- calibre only')
i = 0
for g, b in zip(cal.get(r, []), c):
    if not M.match([b], k, 5)[0]:
        print('  ', g); i += 1
        if i >= n: break
print('-- klayout only')
i = 0
for g, b in zip(kl.get(r, []), k):
    if not M.match([b], c, 5)[0]:
        print('  ', g); i += 1
        if i >= n: break
