#!/usr/bin/env python3
"""Per-cell Magic extraction + Netgen LVS of a whole library against its SPICE view.

Usage (from the repo root, inside the asic-all container or with magic/netgen on PATH):
  python3 hacking/magic/testing/lvs_lib.py <lib> [--cells A,B] [--out DIR] [--jobs N]

<lib> is one of the libraries below. The result table (one line per cell: match / mismatch /
error and the netgen verdict) goes to <out>/<lib>.txt and the summary to stdout.

Tap-less cells: the 7-track library and the IO cells have no well taps of their own, the CDL
ties the wells to the supplies. As in the KLayout regression (tapless=true) the wells are
tied to the rails before comparing: the extracted substrate node becomes VSS and the n-well
node VDD (7-track: the well is named by its VNW label).
"""

import argparse
import concurrent.futures as cf
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import reduce_split_gates  # noqa: E402
import lvs_netlist  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
PDK = os.path.join(ROOT, 'icsprout55')
TECH = os.path.join(PDK, 'libs.tech', 'magic', 'ics55.tech')
SETUP = os.path.join(PDK, 'libs.tech', 'netgen', 'ics55_setup.tcl')
REF = os.path.join(PDK, 'libs.ref')

LIBS = {
    'ics55_LLSC_H7CR': dict(gds='ics55_LLSC_H7CR/gds/ics55_LLSC_H7CR_M2.gds',
                            spice='ics55_LLSC_H7CR/spice/ics55_LLSC_H7CR.spice',
                            tie={'VSUBS': 'VSS', 'VNW': 'VDD', r'w_\w+#': 'VDD'}),
    'ics55_LLSC_H7CR_M1': dict(gds='ics55_LLSC_H7CR/gds/ics55_LLSC_H7CR.gds',
                               spice='ics55_LLSC_H7CR/spice/ics55_LLSC_H7CR.spice',
                               tie={'VSUBS': 'VSS', 'VNW': 'VDD', r'w_\w+#': 'VDD'}),
    'ICsprout55_9TSVT_basic': dict(gds='ICsprout55_9TSVT_basic/gds/ICsprout55_9TSVT_basic.gds',
                                   spice='ICsprout55_9TSVT_basic/spice/ICsprout55_9TSVT_basic.spice',
                                   # well pins: the WELTXT / SUBTXT labels (GDS 388 / 387)
                                   # are beyond what Magic reads, so the nodes are named here
                                   tie={'VSUBS': 'VPW', r'w_\w+#': 'VNW'}, ports=['VNW', 'VPW']),
    'IO': dict(gds='ICsprout_55LLULP1233_IO_251013/gds/ICSIOA_N55_3P3_1P6M1TM.gds',
               spice='ICsprout_55LLULP1233_IO_251013/spice/ICSIOA_N55_3P3.spice',
               tie={}),
}


def subckts(path):
    names = []
    for line in open(path, encoding='latin-1'):
        m = re.match(r'\s*\.subckt\s+(\S+)', line, re.I)
        if m:
            names.append(m.group(1))
    return names


def extract(lib, cells, out):
    """One Magic run extracting every cell of the library into out/<cell>.spice. The GDS is
    first converted to the Magic layer numbering (markers above GDS layer 255)."""
    gds = os.path.join(out, 'magic.gds')
    subprocess.run([sys.executable, os.path.join(HERE, '..', 'magic_gds.py'),
                    os.path.join(REF, LIBS[lib]['gds']), gds], check=True)
    tcl = os.path.join(out, 'extract.tcl')
    with open(tcl, 'w') as f:
        f.write('tech load %s\n' % TECH)
        f.write('set SUB VSUBS\n')
        f.write('gds read %s\n' % gds)
        f.write('set cells {%s}\n' % ' '.join(cells))
        f.write('extract path %s\n' % out)
        f.write('foreach c $cells {\n')
        f.write('  if {[catch {load $c} err]} {puts "LOADFAIL $c"; continue}\n')
        f.write('  extract all\n')
        f.write('  ext2spice lvs\n')
        f.write('  ext2spice -p %s -o %s/$c.spice $c\n' % (out, out))
        f.write('}\n')
        f.write('quit -noprompt\n')
    log = os.path.join(out, 'extract.log')
    with open(log, 'w') as lf:
        subprocess.run(['magic', '-dnull', '-noconsole', '-norcfile', tcl],
                       stdout=lf, stderr=subprocess.STDOUT, cwd=out)


def tie(path, mapping, ports=()):
    if not mapping and not ports:
        return
    text = open(path).read()
    for a, b in mapping.items():
        rx = a if '\\' in a else re.escape(a)
        text = re.sub(r'(?<![\w#])%s(?![\w#])' % rx, b, text)
    # tied nodes may now appear twice on the .subckt line
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.lower().startswith('.subckt'):
            parts = line.split()
            seen, keep = set(), []
            for p in parts + list(ports):
                if p in seen:
                    continue
                seen.add(p)
                keep.append(p)
            lines[i] = ' '.join(keep)
    open(path, 'w').write('\n'.join(lines))


def reduce_file(src, dst):
    lines = open(src, encoding='latin-1').readlines()
    out, n = reduce_split_gates.reduce_text(lines)
    with open(dst, 'w') as f:
        f.writelines(out)
    return n


def lvs(lib, cell, out, ref, reduce):
    sp = os.path.join(out, cell + '.spice')
    if not os.path.exists(sp):
        return cell, 'nolayout', 'cell not in the GDS'
    import shutil
    shutil.copy(sp, sp + '.orig')
    tie(sp, LIBS[lib]['tie'], LIBS[lib].get('ports', ()))
    if reduce:
        reduce_file(sp, sp)
    rpt = os.path.join(out, cell + '.lvs')
    r = subprocess.run(['netgen', '-batch', 'lvs', '%s %s' % (sp, cell), '%s %s' % (ref, cell),
                        SETUP, rpt], capture_output=True, text=True, cwd=out)
    txt = open(rpt).read() if os.path.exists(rpt) else ''
    allout = r.stdout + txt
    if 'has no elements and/or nodes' in allout:
        return cell, 'empty', ''
    if 'Property errors were found' in allout:
        return cell, 'property', ''
    if 'Final result: Circuits match uniquely' in allout:
        return cell, 'match', ''
    m = re.search(r'Final result:\s*(.*)', allout)
    return cell, 'mismatch', m.group(1).strip() if m else 'see report'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('lib', choices=sorted(LIBS))
    ap.add_argument('--cells')
    ap.add_argument('--out')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--no-reduce', action='store_true',
                    help='do not apply the split gate reduction (Calibre LVS REDUCE SPLIT GATES)')
    a = ap.parse_args()
    out = os.path.abspath(a.out or os.path.join('/tmp', 'magic_lvs_' + a.lib))
    os.makedirs(out, exist_ok=True)
    ref = os.path.join(REF, LIBS[a.lib]['spice'])
    cells = a.cells.split(',') if a.cells else subckts(ref)
    # only cells that exist in the GDS (the spice view also holds helper subcircuits)
    extract(a.lib, cells, out)
    # reference: parametrised helper subcircuits inlined (+ split gate reduction)
    rref = os.path.join(out, 'reference_lvs.spice')
    lines, _, _ = lvs_netlist.make(open(ref, encoding='latin-1').readlines(), not a.no_reduce)
    with open(rref, 'w') as f:
        f.writelines(lines)
    ref = rref
    results = []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for res in ex.map(lambda c: lvs(a.lib, c, out, ref, not a.no_reduce), cells):
            results.append(res)
    with open(os.path.join(out, a.lib + '.txt'), 'w') as f:
        for c, v, d in sorted(results):
            f.write('%-28s %-9s %s\n' % (c, v, d))
    cnt = {}
    for _, v, _ in results:
        cnt[v] = cnt.get(v, 0) + 1
    print(a.lib, ' '.join('%s=%d' % kv for kv in sorted(cnt.items())), '->', out)


if __name__ == '__main__':
    main()
