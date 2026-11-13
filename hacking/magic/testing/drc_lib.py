#!/usr/bin/env python3
"""Magic DRC of a whole library, compared rule by rule with the KLayout regression goldens.

Usage (repo root, inside the asic-all container):
  python3 hacking/magic/testing/drc_lib.py <lib> [--out DIR] [--style "drc(full)"]

The library is wrapped exactly like the KLayout regression (testing/wrap_lib.py: every cell
abutted between fillers under a top cell ALL), converted to the Magic layer numbering
(magic_gds.py) and checked with Magic. The error boxes of every rule are merged into
markers and compared with icsprout55/libs.tech/klayout/tech/testing/golden/drc_<lib>.json.
Rules the Magic tech file does not translate are not listed (see hacking/magic/drc_coverage.txt).

Output: <out>/<lib>_magic_drc.json (rule -> count, cells) and a comparison table on stdout.
"""

import argparse
import json
import os
import re
import subprocess
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
PDK = os.path.join(ROOT, 'icsprout55')
TECH = os.path.join(PDK, 'libs.tech', 'magic', 'ics55.tech')
KTEST = os.path.join(PDK, 'libs.tech', 'klayout', 'tech', 'testing')
REF = os.path.join(PDK, 'libs.ref')

LIBS = {
    'stdcell_H7CR_M2': ('ics55_LLSC_H7CR/gds/ics55_LLSC_H7CR_M2.gds', 'FILLER1H7R'),
    'stdcell_H7CR': ('ics55_LLSC_H7CR/gds/ics55_LLSC_H7CR.gds', 'FILLER1H7R'),
    'stdcell_9TSVT': ('ICsprout55_9TSVT_basic/gds/ICsprout55_9TSVT_basic.gds', 'FILL1_9TSVT'),
    'io': ('ICsprout_55LLULP1233_IO_251013/gds/ICSIOA_N55_3P3_1P6M1TM.gds', None),
}


def magic_run(gds, top, style, out):
    tcl = os.path.join(out, 'drc.tcl')
    res = os.path.join(out, 'drc_boxes.txt')
    with open(tcl, 'w') as f:
        f.write('''tech load %s
gds read %s
load %s
select top cell
drc style %s
drc euclidean on
drc check
drc catchup
set fo [open %s w]
set scale [cif scale out]
foreach {why boxes} [drc listall why] {
    foreach b $boxes {
        puts $fo "$why\\t[expr {[lindex $b 0]*$scale}] [expr {[lindex $b 1]*$scale}] [expr {[lindex $b 2]*$scale}] [expr {[lindex $b 3]*$scale}]"
    }
}
close $fo
quit -noprompt
''' % (TECH, gds, top, style, res))
    with open(os.path.join(out, 'drc.log'), 'w') as lf:
        subprocess.run(['magic', '-dnull', '-noconsole', '-norcfile', tcl], stdout=lf,
                       stderr=subprocess.STDOUT, cwd=out)
    return res


def cell_boxes(gds, top):
    ly = db.Layout()
    ly.read(gds)
    t = ly.cell(top)
    out = []
    for inst in t.each_inst():
        out.append((inst.cell.name, inst.bbox()))
    return out, ly.dbu


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('lib', choices=sorted(LIBS))
    ap.add_argument('--out')
    ap.add_argument('--style', default='drc(full)')
    ap.add_argument('--reuse', action='store_true', help='reuse the Magic result of a previous run')
    a = ap.parse_args()
    out = os.path.abspath(a.out or '/tmp/magic_drc_' + a.lib)
    os.makedirs(out, exist_ok=True)
    src, filler = LIBS[a.lib]
    wrapped = os.path.join(out, 'wrapped.gds')
    cmd = [sys.executable, os.path.join(KTEST, 'wrap_lib.py'), os.path.join(REF, src), wrapped]
    if filler:
        cmd.append(filler)
    subprocess.run(cmd, check=True)
    mgds = os.path.join(out, 'wrapped_magic.gds')
    subprocess.run([sys.executable, os.path.join(HERE, '..', 'magic_gds.py'), wrapped, mgds], check=True)
    res = os.path.join(out, 'drc_boxes.txt')
    if not (a.reuse and os.path.exists(res)):
        res = magic_run(mgds, 'ALL', a.style, out)

    insts, dbu = cell_boxes(wrapped, 'ALL')
    per = {}
    for line in open(res):
        why, coords = line.rstrip('\n').split('\t')
        x1, y1, x2, y2 = [float(v) for v in coords.split()]
        rule = why.split(':')[0].strip()
        # cif scale out: magic internal units -> centimicrons? normalise to dbu (nm)
        per.setdefault(rule, []).append((x1, y1, x2, y2))
    result = {}
    for rule, boxes in per.items():
        r = db.Region()
        for x1, y1, x2, y2 in boxes:
            r.insert(db.Box(int(round(x1 * 1000)), int(round(y1 * 1000)), int(round(x2 * 1000)), int(round(y2 * 1000))))
        r.merge()
        cells = {}
        for p in r.each():
            c = p.bbox().center()
            name = 'ALL'
            for cn, bb in insts:
                if bb.contains(c):
                    name = cn
                    break
            cells[name] = cells.get(name, 0) + 1
        result[rule] = {'count': r.count(), 'cells': cells}
    json.dump(result, open(os.path.join(out, a.lib + '_magic_drc.json'), 'w'), indent=1, sort_keys=True)

    golden = json.load(open(os.path.join(KTEST, 'golden', 'drc_%s.json' % a.lib)))
    cov = {}
    for line in open(os.path.join(HERE, '..', 'drc_coverage.txt')):
        m = re.match(r'^(\S+)\s+(ok|partial|skipped|never)\b', line)
        if m:
            cov[m.group(1)] = m.group(2)
    rows = []
    for rule in sorted(set(golden) | set(result)):
        st = cov.get(rule, '?')
        if st in ('skipped', 'never') and rule not in result:
            continue
        g = golden.get(rule, {}).get('count', 0)
        m = result.get(rule, {}).get('count', 0)
        gc = set(golden.get(rule, {}).get('cells', {}))
        mc = set(result.get(rule, {}).get('cells', {}))
        verdict = 'same' if g == m and gc == mc else ('cells' if gc == mc else 'DIFF')
        if g == 0 and m == 0:
            continue
        rows.append((rule, st, g, m, verdict, len(gc - mc), len(mc - gc)))
    print('%-22s %-8s %8s %8s  %-5s %s' % ('rule', 'magic', 'klayout', 'magic', '', 'cells only kl / only magic'))
    for r in rows:
        print('%-22s %-8s %8d %8d  %-5s %d / %d' % r)
    same = sum(1 for r in rows if r[4] != 'DIFF')
    print('%d rules firing, %d agree on the cells' % (len(rows), same))


if __name__ == '__main__':
    main()
