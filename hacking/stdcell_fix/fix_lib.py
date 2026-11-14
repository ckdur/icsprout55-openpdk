#!/usr/bin/env python3
"""Fix the 7-track standard cell layouts with legalize.py.

Both views are migrated together, so they stay identical: the _M2 GDS (with
V1 and the MET2 pins) plus the pin labels of the plain GDS (MET1 pins). Writes
<out>/<lib>.gds and <out>/<lib>_M2.gds and <out>/fix_report.json (per cell:
ok / grown sites / failure reason).

Refix (--markers RUN --prev REPORT): the inputs are an earlier fix_lib result,
the cells with DRC markers in the check_cells.py run RUN are legalized again
from that result with the markers as extra constraints (legalize.Fix), within
the growth left (--max-grow minus the sites already grown). Cells that do not
legalize again keep the earlier result.

--no-cross: without legalize.cross_implant_edge.

Every legalized cell then gets its NP / PP boundary re-solved as a step line
(implant.py; cells whose vendor boundary meets the modelled rules keep it).

Usage:
  python3 fix_lib.py <lib.gds> <lib_M2.gds> <out_dir> [--cells A,B] [--jobs N] [--max-grow 3]
                     [--no-cross] [--markers RUN --prev fix_report.json]
"""

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import klayout.db as db

sys.path.insert(0, str(Path(__file__).resolve().parent))
import legalize as lg   # noqa: E402
import implant          # noqa: E402

PLAIN_ONLY = 1000     # datatype offset for the labels of the plain GDS during the fix
M2_ONLY = {(91, 1)}   # plus every 82/x layer


def m2_only(lay):
    return lay in M2_ONLY or lay[0] == 82


def load_union(plain, m2, name, cross=True):
    """Cell geometry of the _M2 view plus the labels only the plain view has."""
    lm = db.Layout()
    lm.read(m2)
    lp = db.Layout()
    lp.read(plain)
    cell = lg.Cell.from_layout(lm, lm.cell(name), cross=cross)
    have = {(lay, t.string, t.x, t.y) for lay, t in cell.texts}
    pc = lp.cell(name)
    for li in lp.layer_indexes():
        info = lp.get_info(li)
        lay = (info.layer, info.datatype)
        for s in pc.shapes(li).each():
            if s.is_text() and (lay, s.text.string, s.text.x, s.text.y) not in have:
                cell.texts.append(((lay[0], lay[1] + PLAIN_ONLY), s.text))
    return cell


def work(args):
    plain, m2, names, max_grow, cross, marks, prev = args
    out = []
    for name in names:
        t0 = time.time()
        extra = {}
        try:
            # the refix input already has the poly extension
            cell = load_union(plain, m2, name, cross=cross and prev is None)
            g0 = 0
            n_cross = n_jog = 0
            attempts = [(cell, 0, 0)]
            if cross and prev is None:
                # fallback: only the extensions that keep the poly spacing
                strict = load_union(plain, m2, name, cross=False)
                lg.cross_implant_edge(strict.layers, strict=True)
                attempts.append((strict, 0, 0))
            boxes = []
            if prev is not None:
                boxes = [(r, db.Box(*b)) for r, b in marks.get(name, [])]
                g0 = prev[name]['grow'] or 0
                # NP_EN_3 / PP_EN_3 at a poly end that cannot move away: the poly
                # across the implant edge, else a step in the implant edge
                en3 = [(r, b) for r, b in boxes if r in ('NP_EN_3', 'PP_EN_3')]
                if en3:
                    c1 = lg.Cell(dict(cell.layers), list(cell.texts), cell.bnd)
                    n1 = lg.cross_implant_edge(c1.layers, only=db.Region([b for _, b in en3]))
                    c2 = lg.Cell(dict(cell.layers), list(cell.texts), cell.bnd)
                    n2 = lg.implant_jog(c2.layers, en3)
                    attempts = ([(c1, n1, 0)] if n1 else []) + ([(c2, 0, n2)] if n2 else []) + attempts
            for c, n_cross, n_jog in attempts:
                # the EN_3 markers are dealt with by the extension / step
                use = [m for m in boxes if not (n_cross or n_jog) or m[0] not in ('NP_EN_3', 'PP_EN_3')]
                fixes, skipped = lg.fixes_from_markers(c, use) if prev is not None else ((), [])
                new, grow, msg = lg.legalize(c, max_grow=max_grow - g0, fixes=fixes)
                if new is not None:
                    break
            if new is not None:
                grow += g0
                # the NP / PP boundary as a step line (implant.py)
                lay2, v0, v1 = implant.solve(new.layers, new.bnd)
                if lay2 is not None:
                    new = lg.Cell(lay2, new.texts, new.bnd)
                    extra['implant'] = [round(float(v0)), round(float(v1))]
            if prev is not None:
                extra.update({'markers': len(boxes), 'fixes': len(fixes), 'unhandled': sorted(set(skipped)),
                              'crossed': n_cross, 'jogs': n_jog})
        except Exception as e:     # keep going, report the cell
            new, grow, msg = None, None, f'error: {e!r}'
        res = {'status': 'ok' if new else 'failed', 'grow': grow, 'msg': msg, 'time': round(time.time() - t0, 1)}
        res.update(extra)
        geo = None
        if new:
            geo = ({f'{l[0]}/{l[1]}': [str(p) for p in r.each()] for l, r in new.layers.items()},
                   [(l, t.string, t.x, t.y, t.size, int(t.halign), int(t.valign)) for l, t in new.texts])
        out.append((name, res, geo))
    return out


def write(geos, names_all, plain, m2, out_dir, lib):
    for view, src in (('', plain), ('_M2', m2)):
        src_l = db.Layout()
        src_l.read(src)
        lay = db.Layout()
        lay.dbu = src_l.dbu
        for name in names_all:
            c = lay.create_cell(name)
            g = geos.get(name)
            if g is None:      # not fixed: copy the original
                c.copy_tree(src_l.cell(name))
                continue
            polys, texts = g
            for key, plist in polys.items():
                l, d = map(int, key.split('/'))
                if view == '' and m2_only((l, d)):
                    continue
                li = lay.layer(l, d)
                for ps in plist:
                    c.shapes(li).insert(db.Polygon.from_s(ps))
            for (l, d), s, x, y, size, ha, va in texts:
                if d >= PLAIN_ONLY:
                    if view == '_M2':
                        continue
                    d -= PLAIN_ONLY
                elif view == '' and m2_only((l, d)):
                    continue
                t = db.Text(s, db.Trans(x, y))
                t.size = size
                t.halign, t.valign = ha, va
                c.shapes(lay.layer(l, d)).insert(t)
        path = Path(out_dir) / f'{lib}{view}.gds'
        lay.write(str(path))
        print(f'wrote {path}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('plain')
    p.add_argument('m2')
    p.add_argument('out')
    p.add_argument('--cells')
    p.add_argument('--jobs', type=int, default=mp.cpu_count())
    p.add_argument('--max-grow', type=int, default=3)
    p.add_argument('--no-cross', action='store_true')
    p.add_argument('--markers')
    p.add_argument('--prev')
    a = p.parse_args()
    marks, prev = {}, None
    if a.markers:
        import markers as mk
        prev = json.loads(Path(a.prev).read_text())
        marks = {c: [(r, (b.left, b.bottom, b.right, b.top)) for r, b in l]
                 for c, l in mk.boxes(a.markers).items()}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lib = Path(a.plain).stem
    l = db.Layout()
    l.read(a.m2)
    names_all = sorted(c.name for c in l.top_cells())
    names = a.cells.split(',') if a.cells else names_all
    if a.cells and prev is None:
        names_all = names
    if prev is not None:
        names = [n for n in names if prev.get(n, {}).get('status') == 'ok' and marks.get(n)]
    if not names:
        sys.exit('no cells')
    chunks = [names[i::a.jobs] for i in range(a.jobs) if names[i::a.jobs]]
    t0 = time.time()
    report, geos = {}, {}
    with mp.Pool(len(chunks)) as pool:
        for part in pool.imap_unordered(work, [(a.plain, a.m2, c, a.max_grow, not a.no_cross, marks, prev)
                                               for c in chunks]):
            for name, res, geo in part:
                report[name] = res
                if geo:
                    geos[name] = geo
    if prev is not None:
        print(f'refix: {sum(r["status"] == "ok" for r in report.values())} of {len(report)} cells with markers '
              f'legalized again')
        for n, r in sorted(report.items()):
            if r['status'] != 'ok':
                print(f'  kept {n}: {r["msg"]}')
        rep = {n: dict(r) for n, r in prev.items()}
        for n, r in report.items():
            if r['status'] == 'ok':
                rep[n] = r
            else:
                rep[n]['refix'] = r['msg']
        write(geos, names_all, a.plain, a.m2, out, lib)
        (out / 'fix_report.json').write_text(json.dumps(rep, indent=1, sort_keys=True))
        return
    ok = [n for n, r in report.items() if r['status'] == 'ok']
    grown = {n: r['grow'] for n, r in report.items() if r['status'] == 'ok' and r['grow']}
    print(f'{len(ok)} of {len(report)} cells legalized ({len(grown)} grown) in {time.time() - t0:.0f} s')
    for n, r in sorted(report.items()):
        if r['status'] != 'ok':
            print(f'  FAILED {n}: {r["msg"]}')
    write(geos, names_all, a.plain, a.m2, out, lib)
    (out / 'fix_report.json').write_text(json.dumps(report, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
