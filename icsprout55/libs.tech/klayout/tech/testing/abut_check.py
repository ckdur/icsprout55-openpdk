#!/usr/bin/env python3
"""Check every possible left / right abutment of the cells of a standard cell library.

A placer may put any cell side next to any other (cells are mirrored left /
right), so a library is only abutment clean if every pair of cell sides is. The
regression's wrapper (wrap_lib.py) samples one arrangement; this script covers
all pairs without placing all ~10^6 of them, by splitting the interactions
across the seam by the kind of shapes involved. A shape near a cell side either
crosses (or touches) the cell boundary (NW, NP / PP, the M1 rails) or lies
inside the cell (everything else):

- half: shapes inside both cells. A spacing rule S can only be violated across
  the seam if the two shapes are less than S apart, i.e. one of them is closer
  than S/2 to the boundary. For the spacing rules of HALF_RULES (plain, wide,
  45 degree and line end variants, ignoring nets) the shapes of every side
  within S of the boundary are reduced to unique profiles and every pair of
  profiles is checked geometrically (KLayout separation check, euclidean or
  projection metric like the rule). Python only, seconds.
- nw: NW against NW (width / space / notch, 0.47 um). The NW within NW_UM of
  every side is reduced to unique profiles (a few dozen); every pair of profiles
  is placed face to face as a strip and run through the real DRC deck.
- cross: the shapes inside one cell against the boundary crossing layers of the
  other one (implant / well enclosure and spacing of AA, PO, gates, ...). Every
  unique profile of all layers within CROSS_UM of a side is placed against
  every unique profile of the crossing layers (NW, NP, PP clipped to CROSS_UM,
  the rails as full bands) of the other side, real DRC deck.
- verify: for every rule flagged above, up to --verify profile pairs are
  placed as real cells (abutted rows with fillers, like the regression) and run
  through the deck; only markers straddling the seam of the two cells count.

In the strip tests only markers that touch the seam count, and rules that also
fire on the filler / filler control pair are dropped (clipping artefacts and
context rules: floating well, density, latch-up). Not covered: rules between
shapes inside both cells that are not in HALF_RULES (they are listed by name as
"not covered" when a layer has inside shapes closer than 0.065 um to the
boundary), net dependent rules beyond "different nets" (assumed everywhere),
and anything vertical (rows above / below).

Output: a summary per test and rule, <run-dir>/abut_check.json with the
conflicting cell sides ("CELL:L" / "CELL:R" in the unmirrored cell, with the
number of sides they conflict with).

Usage:
  python3 abut_check.py <library.gds> [--filler FILLER4H7R] [--tests half,nw,cross,verify]
                        [--verify N] [--run-dir DIR]
"""

import argparse
import collections
import json
import sys
import time
from pathlib import Path

import klayout.db as db
import klayout.rdb as rdb

from check_cells import pick_filler
from run_regression import DRC_DECK, TESTING_DIR, run_klayout
from wrap_lib import _boundary_fn, place_rows

AA, PO, CT, M1, V1, M2, NW, NP, PP = (2, 1), (41, 1), (72, 1), (81, 1), (91, 1), (82, 1), (9, 1), (52, 1), (53, 1)
BOUNDARY = (351, 12)
RAIL_LAYERS = {M1}       # crossing shapes of these layers are full width bands (rails + stubs)
NW_UM = 0.47
CROSS_UM = 0.30          # largest implant / well rule to inside shapes (NP_S_5, PP_S_5: 0.30)
GAP_UM = 3.0             # between strip pairs (> NW1_S_2 / S_3 / S_5 distances)
EUCLID, PROJ = db.Metrics.Euclidian, db.Metrics.Projection

# name, layer A, layer B, space, condition on the A shape, metric, minimum run
# length (projection). Layers are (layer, datatype) or ('and', L1, L2).
# Conditions: None, ('wide', w) (shapes with a width > w somewhere), ('45',)
# (the 45 degree edges), ('end', w) (line ends: edges shorter than w with two
# convex 90 degree corners; the "dense line end" part of the rule is not
# checked, so this is conservative). Nets are ignored (different nets assumed).
HALF_RULES = [
    ('ACT_S_1', AA, AA, 0.11, None, EUCLID, 0),
    ('ACT_S_2', AA, AA, 0.125, ('wide', 0.2), PROJ, 0.3),
    ('ACT_S_3', AA, AA, 0.18, ('45',), EUCLID, 0),
    ('PO_S_1', PO, PO, 0.12, None, EUCLID, 0),
    ('PO_S_2', PO, PO, 0.18, ('wide', 0.13), PROJ, 0.181),
    ('PO_S_6', PO, PO, 0.18, ('45',), EUCLID, 0),
    ('PO_S_9', PO, PO, 0.14, ('end', 0.09), PROJ, 0),
    ('PO_S_11', PO, AA, 0.05, None, EUCLID, 0),
    ('CT_S_1', CT, CT, 0.11, None, EUCLID, 0),
    ('CT_S_2', CT, CT, 0.12, None, EUCLID, 0),
    ('CT_S_3', ('and', CT, PO), AA, 0.065, None, EUCLID, 0),
    ('CT_S_4', PO, ('and', CT, AA), 0.055, None, EUCLID, 0),
    ('MET1_S_1', M1, M1, 0.09, None, EUCLID, 0),
    ('MET1_S_2', M1, M1, 0.15, ('wide', 0.42), PROJ, 0.42),
    ('MET1_S_4', M1, M1, 0.19, ('45',), EUCLID, 0),
    ('MET1_S_5', M1, M1, 0.11, ('end', 0.11), PROJ, 0),
    ('V1_S_1', V1, V1, 0.11, None, EUCLID, 0),
    ('V1_S_3', V1, V1, 0.13, None, PROJ, 0),
    ('M2_S_1', M2, M2, 0.10, None, EUCLID, 0),
    ('M2_S_2', M2, M2, 0.15, ('wide', 0.42), PROJ, 0.42),
    ('M2_S_4', M2, M2, 0.19, ('45',), EUCLID, 0),
    ('M2_S_5', M2, M2, 0.12, ('end', 0.12), PROJ, 0),
    ('NW1_S_1', NW, NW, 0.47, None, EUCLID, 0),
    ('NP_S_1', NP, NP, 0.18, None, PROJ, 0),
    ('PP_S_1', PP, PP, 0.18, None, PROJ, 0),
]
UNCOVERED_UM = 0.065     # inside shapes closer than this on a layer without HALF_RULES are reported

BIG = 10 ** 7


def key_of(regions):
    """Hashable profile of {layer: Region} (normalized coordinates)."""
    return tuple(sorted((lay, tuple(sorted(str(p) for p in r.each())))
                        for lay, r in regions.items() if not r.is_empty()))


def clip(r, d):
    return r & db.Region(db.Box(-d, -BIG, 0, BIG))


class Side:
    """One side of a cell, normalized: boundary at x = 0, cell inside x < 0, bottom at y = 0."""

    def __init__(self, cell, side, layers, boundary, dbu):
        self.cell = cell.name
        self.side = side
        self.name = f'{cell.name}:{side}'
        bb = boundary
        if side == 'R':
            t = db.Trans(-bb.right, -bb.bottom)
        else:
            t = db.Trans(db.Trans.M90, bb.left, -bb.bottom)
        line = db.Region(db.Box(-1, -BIG, 1, BIG))
        self.full, self.cross, self.inside = {}, {}, {}
        for lay, li in layers.items():
            r = db.Region(cell.begin_shapes_rec(li)).merged().transformed(t)
            if r.is_empty():
                continue
            self.full[lay] = r
            if lay in RAIL_LAYERS:
                bands = db.Region()
                for p in (r & line).each():
                    b = p.bbox()
                    bands.insert(db.Box(-BIG, b.bottom, BIG, b.top))
                c = r & bands
                ins = r - bands
            else:
                c = r.interacting(line)
                ins = r - c
            if not c.is_empty():
                self.cross[lay] = c
            if not ins.is_empty():
                self.inside[lay] = ins

    def inside_layer(self, spec):
        if isinstance(spec, tuple) and spec and spec[0] == 'and':
            a, b = self.inside.get(spec[1]), self.inside.get(spec[2])
            return (a & b) if a is not None and b is not None else db.Region()
        return self.inside.get(spec, db.Region())


def load_sides(gds):
    layout = db.Layout()
    layout.read(gds)
    boundary = _boundary_fn(layout)
    bnd = layout.find_layer(*BOUNDARY)
    layers = {}
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        if li != bnd:
            layers[(info.layer, info.datatype)] = li
    sides = []
    for c in sorted(layout.top_cells(), key=lambda c: c.name):
        if c.name == 'ALL' or bnd is None or c.bbox_per_layer(bnd).empty():
            continue
        bb = boundary(c)
        for s in 'LR':
            sides.append(Side(c, s, layers, bb, layout.dbu))
    return layout, sides


def mirror(r):
    return r.transformed(db.Trans(db.Trans.M90, 0, 0))


class Result:
    """Conflicting side pairs per rule of one test."""

    def __init__(self):
        self.pairs = collections.defaultdict(list)   # rule -> [(sides A, sides B, rep A, rep B)]

    def add(self, rule, sides_a, sides_b):
        self.pairs[rule].append((sides_a, sides_b))

    def to_json(self):
        out = {}
        for rule, lst in sorted(self.pairs.items()):
            cnt = collections.Counter()
            seen = set()
            n = 0
            for sa, sb in lst:
                for a in sa:
                    for b in sb:
                        if (a.name, b.name) in seen or (b.name, a.name) in seen:
                            continue
                        seen.add((a.name, b.name))
                        n += 1
                        cnt[a.name] += 1
                        if b.name != a.name:
                            cnt[b.name] += 1
            out[rule] = {'profile_pairs': len(lst), 'side_pairs': n,
                         'cells': len({s.split(':')[0] for s in cnt}),
                         'sides': dict(cnt.most_common())}
        return out


# --- half: geometric check of inside shapes --------------------------------

def line_ends(r, w):
    """Edges shorter than w between two convex 90 degree corners (hull only)."""
    out = db.Edges()
    for p in r.each():
        pts = list(p.each_point_hull())
        n = len(pts)
        area2 = sum(pts[i].x * pts[(i + 1) % n].y - pts[(i + 1) % n].x * pts[i].y for i in range(n))

        def convex(a, b, c):
            u, v = b - a, c - b
            return u.x * v.x + u.y * v.y == 0 and (u.x * v.y - u.y * v.x) * area2 > 0
        for i in range(n):
            a, b, c, d = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
            e = db.Edge(b, c)
            if e.length() < w and convex(a, b, c) and convex(b, c, d):
                out.insert(e)
    return out


def test_half(sides, dbu):
    res = Result()
    uncovered = {}
    covered_layers = set()
    for name, la, lb, s_um, cond, metric, run_um in HALF_RULES:
        for spec in (la, lb):
            covered_layers.update(spec[1:] if spec[0] == 'and' else [spec])
        s = round(s_um / dbu)
        strip = db.Region(db.Box(-s, -BIG, 0, BIG))
        kw = {'metrics': metric}
        if run_um:
            kw['min_projection'] = round(run_um / dbu)
        prof_a, prof_b = {}, {}
        for sd in sides:
            ra = sd.inside_layer(la)
            if not ra.is_empty():
                if cond is None:
                    ea = (ra & strip).edges()
                elif cond[0] == 'wide':
                    ra = ra.interacting(ra.sized(-(round(cond[1] / dbu) // 2)))
                    ea = (ra & strip).edges()
                elif cond[0] == '45':
                    ea = ra.edges().with_angle(db.Edges.DiagonalEdges, False) & strip
                else:
                    ea = line_ends(ra, round(cond[1] / dbu)) & strip
                if not ea.is_empty():
                    prof_a.setdefault(str(sorted(str(e) for e in ea.each())), [ea, -ea.bbox().right, []])[2].append(sd)
            rb = sd.inside_layer(lb) & strip
            if not rb.is_empty():
                prof_b.setdefault(key_of({0: rb}), [mirror(rb).edges(), -rb.bbox().right, []])[2].append(sd)
        for ea, da, sa in prof_a.values():
            for eb, db_, sb in prof_b.values():
                if da + db_ >= s:
                    continue
                if not ea.separation_check(eb, s, **kw).is_empty():
                    res.add(name, sa, sb)
    # layers with inside shapes very close to the boundary but no rule above
    lim = round(UNCOVERED_UM / dbu)
    for sd in sides:
        for lay, r in sd.inside.items():
            if lay in covered_layers:
                continue
            near = clip(r, lim)
            if not near.is_empty():
                uncovered.setdefault(f'{lay[0]}/{lay[1]}', []).append(sd.name)
    return res, uncovered


# --- strip tests with the real deck ----------------------------------------

def strip_drc(pairs, run, tag, dbu):
    """pairs: [(regions A, regions B, payload)], B regions already mirrored to x > 0.
    Writes the strips, runs the deck and returns {pair index: set(rules)} for
    markers touching the seam."""
    gap = round(GAP_UM / dbu)
    wmax = max(max((r.bbox().width() for r in ra.values()), default=0) for ra, _, _ in pairs)
    wmax = max(wmax, max(max((r.bbox().width() for r in rb.values()), default=0) for _, rb, _ in pairs))
    hmax = max(max((r.bbox().height() for r in list(ra.values()) + list(rb.values())), default=0)
               for ra, rb, _ in pairs)
    hmin = min(min((r.bbox().bottom for r in list(ra.values()) + list(rb.values())), default=0)
               for ra, rb, _ in pairs)
    px, py = 2 * wmax + gap, hmax + gap
    ncol = max(1, int(len(pairs) ** 0.5))
    layout = db.Layout()
    layout.dbu = dbu
    top = layout.create_cell('ALL')
    lidx = {}
    seams = []
    for k, (ra, rb, _) in enumerate(pairs):
        x0, y0 = (k % ncol) * px + wmax, (k // ncol) * py - hmin
        seams.append((x0, y0))
        t = db.Trans(x0, y0)
        for regs in (ra, rb):
            for lay, r in regs.items():
                if lay not in lidx:
                    lidx[lay] = layout.layer(*lay)
                top.shapes(lidx[lay]).insert(r.transformed(t))
    gds = run / f'{tag}.gds'
    report = run / f'{tag}.lyrdb'
    layout.write(str(gds))
    t0 = time.time()
    run_klayout(['-r', str(DRC_DECK), '-rd', f'input={gds}', '-rd', 'topcell=ALL',
                 '-rd', f'report={report}', '-rd', f'log={run / (tag + ".log")}'])
    print(f'  [{tag}] {len(pairs)} strip pairs, DRC {time.time() - t0:.0f} s')
    hits = collections.defaultdict(set)
    rep = rdb.ReportDatabase('')
    rep.load(str(report))
    for cat in rep.each_category():
        if not cat.num_items():
            continue
        for it in rep.each_item_per_category(cat.rdb_id()):
            for v in it.each_value():
                b = _value_box(v)
                if b is None:
                    continue
                b = db.Box(round(b.left / dbu), round(b.bottom / dbu), round(b.right / dbu), round(b.top / dbu))
                cx, cy = (b.left + b.right) // 2, (b.bottom + b.top) // 2
                col, row = int(cx // px), int(cy // py)
                k = row * ncol + col
                if col < 0 or col >= ncol or not 0 <= k < len(pairs):
                    continue
                x0, y0 = seams[k]
                if b.left - 1 <= x0 <= b.right + 1:
                    hits[k].add(cat.name())
                break
    return hits


def _value_box(v):
    from summary import _value_box as vb
    return vb(v)


def run_strip_test(tag, profiles_a, profiles_b, control, ordered, run, dbu, res):
    """profiles_*: {key: (regions, [sides])}; control: (key A, key B)."""
    keys_a, keys_b = list(profiles_a), list(profiles_b)
    combos = [control]
    for i, ka in enumerate(keys_a):
        for j, kb in enumerate(keys_b):
            if not ordered and j < i:
                continue
            if (ka, kb) != control:
                combos.append((ka, kb))
    pairs = [(profiles_a[ka][0], {l: mirror(r) for l, r in profiles_b[kb][0].items()}, (ka, kb))
             for ka, kb in combos]
    hits = strip_drc(pairs, run, tag, dbu)
    excluded = sorted(hits.get(0, set()))
    for k, rules in hits.items():
        if k == 0:
            continue
        ka, kb = combos[k]
        for rule in rules:
            if rule not in excluded:
                res.add(rule, profiles_a[ka][1], profiles_b[kb][1])
    return excluded, len(combos)


def profiles(sides, fn):
    out = {}
    for sd in sides:
        regs = {l: r for l, r in fn(sd).items() if not r.is_empty()}
        k = key_of(regs)
        out.setdefault(k, (regs, []))[1].append(sd)
    return out


def find_key(profs, side_name):
    for k, (_, lst) in profs.items():
        if any(s.name == side_name for s in lst):
            return k
    sys.exit(f'{side_name} not in the profiles')


# --- verify with real cells -------------------------------------------------

def verify(gds, filler, results, n_per_rule, run):
    layout = db.Layout()
    layout.read(gds)
    boundary = _boundary_fn(layout)
    dbu = layout.dbu
    rows, meta = [], []
    for test, res in results.items():
        for rule, lst in sorted(res.pairs.items()):
            for sa, sb in lst[:n_per_rule]:
                a, b = sa[0], sb[0]
                # A shows its side on the right, B on the left
                rows.append([(layout.cell(a.cell), a.side == 'L'), (layout.cell(b.cell), b.side == 'R')])
                meta.append((test, rule, a.name, b.name))
    if not rows:
        return {}
    top = layout.create_cell('ALL')
    placed = place_rows(layout, top, filler, boundary, rows)
    h = boundary(layout.cell(filler)).height()
    gds_out, report = run / 'verify.gds', run / 'verify.lyrdb'
    layout.write(str(gds_out))
    t0 = time.time()
    run_klayout(['-r', str(DRC_DECK), '-rd', f'input={gds_out}', '-rd', 'topcell=ALL',
                 '-rd', f'report={report}', '-rd', f'log={run / "verify.log"}'])
    print(f'  [verify] {len(rows)} cell pairs, DRC {time.time() - t0:.0f} s')
    found = collections.defaultdict(set)    # row -> rules at its seam
    rep = rdb.ReportDatabase('')
    rep.load(str(report))
    for cat in rep.each_category():
        if not cat.num_items():
            continue
        for it in rep.each_item_per_category(cat.rdb_id()):
            for v in it.each_value():
                b = _value_box(v)
                if b is None:
                    continue
                b = db.Box(round(b.left / dbu), round(b.bottom / dbu), round(b.right / dbu), round(b.top / dbu))
                if b.width() > 4 * h:      # density windows and the like
                    break
                for k in range(max(0, b.bottom // h - 2), min(len(rows), b.top // h + 1)):
                    y, insts = placed[k]
                    (_, ax0, ax1), (_, bx0, bx1) = insts
                    if b.top >= y and b.bottom <= y + h and b.left - 1 <= ax1 <= b.right + 1 \
                            and b.right > ax0 and b.left < bx1:
                        found[k].add(cat.name())
                break
    out = {}
    for k, (test, rule, a, b) in enumerate(meta):
        e = out.setdefault(f'{test}:{rule}', {'tested': 0, 'confirmed': 0, 'confirmed_pairs': [],
                                               'not_confirmed': [], 'other_rules': collections.Counter()})
        e['tested'] += 1
        if rule in found[k]:
            e['confirmed'] += 1
            e['confirmed_pairs'].append(f'{a}|{b}')
        else:
            e['not_confirmed'].append(f'{a}|{b}')
        for r in found[k] - {rule}:
            e['other_rules'][r] += 1
    for e in out.values():
        e['other_rules'] = dict(e['other_rules'])
    return out


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('gds')
    p.add_argument('--filler')
    p.add_argument('--tests', default='half,nw,cross,verify')
    p.add_argument('--verify', type=int, default=20, help='profile pairs per rule placed as real cells')
    p.add_argument('--run-dir', default=str(TESTING_DIR / 'run' / 'abut_check'))
    a = p.parse_args()
    tests = set(a.tests.split(','))
    run = Path(a.run_dir)
    run.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    layout, sides = load_sides(a.gds)
    dbu = layout.dbu
    filler = a.filler or pick_filler(layout)
    print(f'{a.gds}: {len(sides) // 2} cells, {len(sides)} sides, filler {filler} ({time.time() - t0:.0f} s)')
    ctrl = (f'{filler}:R', f'{filler}:L')
    results, report = {}, {}

    if 'half' in tests:
        res, uncovered = test_half(sides, dbu)
        results['half'] = res
        report['half'] = {'rules': res.to_json(), 'not_covered_layers': {l: len(s) for l, s in uncovered.items()}}
        print(f'  [half] done ({time.time() - t0:.0f} s)')

    if 'nw' in tests:
        d = round(NW_UM / dbu)
        profs = profiles(sides, lambda sd: {NW: clip(sd.full.get(NW, db.Region()), d)})
        ctrl_k = (find_key(profs, ctrl[0]), find_key(profs, ctrl[1]))
        res = Result()
        excl, n = run_strip_test('nw', profs, profs, ctrl_k, False, run, dbu, res)
        results['nw'] = res
        report['nw'] = {'profiles': len(profs), 'strip_pairs': n, 'excluded_rules': excl, 'rules': res.to_json()}

    if 'cross' in tests:
        d = round(CROSS_UM / dbu)
        prof_a = profiles(sides, lambda sd: {l: clip(r, d) for l, r in sd.full.items()})
        prof_b = profiles(sides, lambda sd: {l: clip(r, d) for l, r in sd.cross.items()})
        ctrl_k = (find_key(prof_a, ctrl[0]), find_key(prof_b, ctrl[1]))
        res = Result()
        excl, n = run_strip_test('cross', prof_a, prof_b, ctrl_k, True, run, dbu, res)
        results['cross'] = res
        report['cross'] = {'profiles_inside': len(prof_a), 'profiles_crossing': len(prof_b),
                           'strip_pairs': n, 'excluded_rules': excl, 'rules': res.to_json()}

    if 'verify' in tests and results:
        report['verify'] = verify(a.gds, filler, results, a.verify, run)

    out = run / 'abut_check.json'
    out.write_text(json.dumps(report, indent=1))
    print(f'Result ({time.time() - t0:.0f} s, details in {out}):')
    for test, r in report.items():
        if test == 'verify':
            continue
        extra = {k: v for k, v in r.items() if k not in ('rules', 'excluded_rules')}
        print(f' {test}: {extra}')
        if r.get('excluded_rules'):
            print(f'   dropped (fire on {ctrl[0]}|{ctrl[1]}): {", ".join(r["excluded_rules"])}')
        for rule, e in r['rules'].items():
            v = report.get('verify', {}).get(f'{test}:{rule}')
            vs = f'  verified {v["confirmed"]}/{v["tested"]}' if v else ''
            ex = ', '.join(list(e['sides'])[:4])
            print(f'   {rule:16s} side pairs {e["side_pairs"]:7d}  sides {len(e["sides"]):4d}  cells {e["cells"]:4d}{vs}  e.g. {ex}')


if __name__ == '__main__':
    main()
