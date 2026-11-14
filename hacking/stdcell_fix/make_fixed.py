#!/usr/bin/env python3
"""Build the fixed 7-track libraries (GDS + LEF) from the vendor ones.

  1. fix_lib.py on ics55_LLSC_H7CR (both GDS views migrated together), with
     and without the poly extension across the implant edge
     (legalize.cross_implant_edge); every result is checked: KLayout DRC
     (abutted rows, like the regression) and per cell LVS of the _M2 view
  2. per cell the better variant (usable, else fewer markers)
  3. feedback rounds: the cells that still have DRC markers are legalized
     again from their result with the markers as constraints
     (fix_lib.py --markers), checked, and taken where they improved
  4. a cell is usable if it was legalized, has no DRC marker besides the
     context rules (latch-up without taps, floating well, density) and its LVS
     result is not worse than the original's; the other cells keep their
     original layout and are listed in <out>/<lib>/unusable.cells. The tap cell
     FILLTAP, which legalize.py cannot migrate, is fixed by hand (fix_filltap.py,
     grown to two sites)
  5. H7CH / H7CL: the usable H7CR cells with the Vt layers copied from their
     NP / PP (derive_vt.py), the others copied; both are checked (DRC, _M2 view)
     and a usable cell with a Vt rule marker becomes unusable in all three
     libraries (then 4. / 5. again)
  6. LEFs (plain, _ant, _ecos) of every library: macro geometry of the usable
     cells rewritten from the fixed GDS (lef_from_gds.py); the liberty files
     are not touched

Run in the tool container from the repository root (vendor views from the icsprout55-pdk
submodule, the converted CDL from libs.ref, i.e. after install.sh):
  python3 hacking/stdcell_fix/make_fixed.py <out_dir> [--jobs N] [--rounds 3] [--max-grow 3]

Output: <out>/<lib>/gds/<lib>{,_M2}.gds, <out>/<lib>/lef/<lib>{,_ant,_ecos}.lef,
<out>/<lib>/unusable.cells, <out>/report.json; intermediate results in <out>/work
(an existing step result there is reused).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import klayout.db as db

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TESTING = ROOT / 'icsprout55/libs.tech/klayout/tech/testing'
REF = ROOT / 'icsprout55/libs.ref'          # the converted CDL
VENDOR = ROOT / 'icsprout55-pdk/IP/STD_cell/ics55_LLSC_H7C_V1p10C100'   # the vendor GDS / LEF
LIBS = {'ics55_LLSC_H7CR': 'H7R', 'ics55_LLSC_H7CH': 'H7H', 'ics55_LLSC_H7CL': 'H7L'}
R = 'ics55_LLSC_H7CR'
TAP = 'FILLTAPH7R'
VIEWS = ('', '_M2')
sys.path.insert(0, str(HERE))
import classify  # noqa: E402
import markers  # noqa: E402

VT_RULES = ('NVT', 'PVT')   # Vt layer rules (H7CH: NVT3 / PVT3, H7CL: NVT1 / PVT1)


def run(cmd, cwd=ROOT, log=None):
    print('+', ' '.join(str(c) for c in cmd), flush=True)
    with open(log, 'w') if log else open('/dev/null', 'w') as f:
        r = subprocess.run([str(c) for c in cmd], cwd=cwd, stdout=f if log else None, stderr=subprocess.STDOUT)
    if r.returncode:
        sys.exit(f'failed: {cmd}')


def check(gds, run_dir, log):
    if not (Path(run_dir) / 'lvs.lvsdb').exists():
        cdl = REF / R / 'cdl' / f'{R}.cdl'
        run([sys.executable, '-u', 'check_cells.py', gds, 'all', '--cdl', cdl, '--run-dir', run_dir],
            cwd=TESTING, log=log)


def fix(work, name, extra, a):
    d = work / name
    if not (d / 'fix_report.json').exists():
        src = extra.pop('src', None) or VENDOR / R / 'gds'
        run([sys.executable, HERE / 'fix_lib.py', src / f'{R}.gds', src / f'{R}_M2.gds', d,
             '--jobs', a.jobs, '--max-grow', a.max_grow] + extra.get('args', []), log=work / f'{name}.log')
    check(d / f'{R}_M2.gds', work / f'cc_{name}', work / f'cc_{name}.log')
    return d


def evaluate(fix_dir, cc_dir, orig_lvs):
    res = classify.main(fix_dir / 'fix_report.json', cc_dir)
    for name, r in res.items():
        # physical only cells (FILLER) have no CDL subcircuit: n/a like the original
        orig = orig_lvs.get(name)
        lvs_ok = r['lvs'] == 'match' or r['lvs'] == orig or (orig is None and r['lvs'] == 'n/a')
        r['usable'] = r['fix'] == 'ok' and not r['drc'] and lvs_ok
        r['lvs_ok'] = lvs_ok
        r['markers'] = sum(r['drc'].values())
    return res


def better(new, old):
    """new result better than old (both legalized)."""
    if new['fix'] != 'ok':
        return False
    if old['fix'] != 'ok' or new['usable'] and not old['usable']:
        return True
    if old['usable']:
        return False
    if new['lvs_ok'] != old['lvs_ok']:
        return new['lvs_ok']
    return new['markers'] < old['markers']


def merge(choice, out_dir):
    """choice: {cell: fix dir}; writes both views and the fix report into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    srcs = sorted(set(choice.values()))
    for view in VIEWS:
        lays = {}
        for s in srcs:
            lays[s] = db.Layout()
            lays[s].read(str(s / f'{R}{view}.gds'))
        out = db.Layout()
        out.dbu = lays[srcs[0]].dbu
        for name in sorted(choice):
            out.create_cell(name).copy_tree(lays[choice[name]].cell(name))
        out.write(str(out_dir / f'{R}{view}.gds'))
    reps = {s: json.loads((s / 'fix_report.json').read_text()) for s in srcs}
    rep = {n: dict(reps[s][n], src=s.name) for n, s in choice.items()}
    (out_dir / 'fix_report.json').write_text(json.dumps(rep, indent=1, sort_keys=True))


def replace_cells(src_gds, orig_gds, out_gds, cells):
    """out = src with the given cells taken from orig."""
    lay, orig = db.Layout(), db.Layout()
    lay.read(str(src_gds))
    orig.read(str(orig_gds))
    for name in cells:
        c = lay.cell(name)
        c.clear()
        c.copy_tree(orig.cell(name))
    lay.write(str(out_gds))


def assemble(out, unusable):
    """Steps 4 and 5: the fixed H7CR with the unusable cells back to the original
    layout and the hand fixed tap, then the Vt variants."""
    for lib in LIBS:
        (out / lib / 'gds').mkdir(parents=True, exist_ok=True)
        (out / lib / 'lef').mkdir(parents=True, exist_ok=True)
    cur = out / 'work' / 'final'
    for view in VIEWS:
        gds = out / R / 'gds' / f'{R}{view}.gds'
        replace_cells(cur / f'{R}{view}.gds', VENDOR / R / 'gds' / f'{R}{view}.gds', gds, unusable + [TAP])
        run([sys.executable, HERE / 'fix_filltap.py', gds, gds, TAP])
    for lib, suf in LIBS.items():
        if lib == R:
            continue
        for view in VIEWS:
            run([sys.executable, HERE / 'derive_vt.py', out / R / 'gds' / f'{R}{view}.gds',
                 VENDOR / R / 'gds' / f'{R}{view}.gds', VENDOR / lib / 'gds' / f'{lib}{view}.gds',
                 out / lib / 'gds' / f'{lib}{view}.gds', suf,
                 '--keep', ','.join(n[:-3] + suf for n in unusable)])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('out')
    p.add_argument('--jobs', type=int, default=16)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--max-grow', type=int, default=3)
    a = p.parse_args()
    out = Path(a.out).resolve()
    work = out / 'work'
    work.mkdir(parents=True, exist_ok=True)

    # LVS baseline: the original layout
    check(VENDOR / R / 'gds' / f'{R}_M2.gds', work / 'cc_orig', work / 'cc_orig.log')
    orig_lvs = classify.circuit_status(str(work / 'cc_orig' / 'lvs.lvsdb'))

    # 1. / 2. variants, the better one per cell
    variants = {'fix_cross': [], 'fix_nocross': ['--no-cross']}
    best, src = {}, {}
    for name, args in variants.items():
        d = fix(work, name, {'args': args}, a)
        res = evaluate(d, work / f'cc_{name}', orig_lvs)
        n = sum(r['usable'] for r in res.values())
        print(f'{name}: {n} usable')
        for cell, r in res.items():
            if cell not in best or better(r, best[cell]):
                best[cell], src[cell] = r, d
    cur = work / 'round0'
    if not (cur / 'fix_report.json').exists():
        merge(src, cur)
    check(cur / f'{R}_M2.gds', work / 'cc_round0', work / 'cc_round0.log')
    best = evaluate(cur, work / 'cc_round0', orig_lvs)
    print(f'round 0: {sum(r["usable"] for r in best.values())} usable')

    # 3. marker feedback
    for k in range(1, a.rounds + 1):
        prev_cc = work / f'cc_round{k - 1}'
        todo = [c for c, r in best.items() if r['fix'] == 'ok' and not r['usable'] and r['drc']]
        if not todo:
            break
        name = f'refix{k}'
        d = fix(work, name, {'src': cur, 'args': ['--markers', prev_cc, '--prev', cur / 'fix_report.json']}, a)
        res = evaluate(d, work / f'cc_{name}', orig_lvs)
        choice = {c: cur for c in best}
        gained = 0
        for c in todo:
            if better(res[c], best[c]):
                choice[c] = d
                gained += res[c]['usable']
        nxt = work / f'round{k}'
        if not (nxt / 'fix_report.json').exists():
            merge(choice, nxt)
        check(nxt / f'{R}_M2.gds', work / f'cc_round{k}', work / f'cc_round{k}.log')
        best = evaluate(nxt, work / f'cc_round{k}', orig_lvs)
        cur = nxt
        print(f'round {k}: {gained} cells became usable in the refix, {sum(r["usable"] for r in best.values())} usable')

    final = work / 'final'
    if final.is_symlink() or final.exists():
        final.unlink()
    final.symlink_to(cur.name)
    usable = sorted(c for c, r in best.items() if r['usable'])
    unusable = sorted(c for c, r in best.items() if not r['usable'])
    report = {c: dict(r, lvs_orig=orig_lvs.get(c)) for c, r in best.items()}
    print(f'{len(usable)} usable, {len(unusable)} unusable')

    # 4. / 5. assemble the libraries; a usable cell whose Vt layers (H7CH / H7CL,
    # copies of NP / PP) still violate a Vt rule (stricter than the NP / PP ones in
    # places) becomes unusable in all three, and the libraries are assembled again
    if TAP in unusable:
        unusable.remove(TAP)
        usable = sorted(usable + [TAP])
        # checked separately (DRC clean, also against every usable cell side)
        report[TAP].update(usable=True, fix='hand (fix_filltap.py)', grow=1, drc_orig=report[TAP]['drc'],
                           drc={}, markers=0, msg='hand fix, grown by one site')
        print(f'{TAP}: hand fix, {len(usable)} usable')
    for k in range(3):
        assemble(out, unusable)
        bad = {}
        for lib, suf in LIBS.items():
            if lib == R:
                continue
            cc = work / f'cc_vt{k}_{lib}'
            if not (cc / 'drc.lyrdb').exists():
                run([sys.executable, '-u', 'check_cells.py', out / lib / 'gds' / f'{lib}_M2.gds', 'all',
                     '--run-dir', cc], cwd=TESTING, log=work / f'cc_vt{k}_{lib}.log')
            for cell, lst in markers.boxes(str(cc)).items():
                rules = sorted({rule for rule, _ in lst if rule.startswith(VT_RULES)})
                name = cell[:-3] + 'H7R'
                if rules and name in usable and name != TAP:
                    bad.setdefault(name, set()).update(rules)
        if not bad:
            break
        for name, rules in sorted(bad.items()):
            usable.remove(name)
            unusable.append(name)
            report[name].update(usable=False, drc_vt=sorted(rules))
        unusable.sort()
        print(f'Vt check {k}: {len(bad)} more unusable ({", ".join(sorted(bad))}), {len(usable)} usable')
    # 6. LEFs
    for lib, suf in LIBS.items():
        cells = ','.join(n[:-3] + suf for n in usable)
        for lef, view, pins in (('', '', 'm1'), ('_ant', '', 'm1'), ('_ecos', '_M2', 'm2')):
            run([sys.executable, HERE / 'lef_from_gds.py', VENDOR / lib / 'lef' / f'{lib}{lef}.lef',
                 out / lib / 'gds' / f'{lib}{view}.gds', out / lib / 'lef' / f'{lib}{lef}.lef',
                 '--pins', pins, '--cells', cells])
        (out / lib / 'unusable.cells').write_text(''.join(n[:-3] + suf + '\n' for n in unusable))
    (out / 'report.json').write_text(json.dumps(report, indent=1, sort_keys=True, default=str))


if __name__ == '__main__':
    main()
