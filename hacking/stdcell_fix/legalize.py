"""1D layout migration of a standard cell: move edges so a set of rules holds.

The cell is flattened into merged Manhattan polygons per layer (45 degree
edges are replaced first by the corner that adds area). A pass in x gives every
vertical edge a variable; for every pair of edges that see each other (closer
than WIN, overlapping in y or close enough for a euclidean spacing) the
relation in the original layout gives a difference constraint:

  R edge ... L edge   (gap)        x_b - x_a >= space(a, b)
  L edge ... R edge   (same shape) x_b - x_a >= width, or == for rigid shapes
                                   (CT, V1, gate length)
  L ... L / R ... R   (inner shape inside the outer one)
                                   x_b - x_a >= enclosure(outer, inner)
  coincident edges without a rule  x_b == x_a

The boundary (351/12) is fixed on the left, on the right at the requested cell
width; shapes keep their distance to the boundary (at most the half spacing of
their layer, V1 is pushed to half of V1_S_3). The LP (scipy HiGHS) minimizes
the total edge movement. The y pass is the same on the transposed cell, with
the rails, wells, implants, AA and boundary frozen (cell height, row contract
and transistor widths stay).

Enclosures with alternatives (CT / V1 by M1: two opposite sides 0.04 or all
sides 0.025 / 0.03, ...) get a mode per via chosen from the original layout
(smallest total deficit), so each pass only sees plain minimum values.
"""

import math

import numpy as np
import klayout.db as db
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

AA, PO, CT, M1, V1, M2 = (2, 1), (41, 1), (72, 1), (81, 1), (91, 1), (82, 1)
NW, NP, PP = (9, 1), (52, 1), (53, 1)
BND = (351, 12)
RIGID = {CT, V1}
FROZEN_Y = {NW, NP, PP, AA, BND, (21, 1), (22, 1)}
DEVICE = {AA, PO, CT, M1, V1, M2, NW, NP, PP}

UM = 1000   # dbu per um (cells use 1 nm)

WIDTH = {AA: 0.08, PO: 0.06, M1: 0.09, M2: 0.10, NP: 0.18, PP: 0.18, NW: 0.47}
SPACE = {
    (AA, AA): 0.11, (PO, PO): 0.12, (M1, M1): 0.09, (M2, M2): 0.10, (CT, CT): 0.11,
    (V1, V1): 0.11, (NP, NP): 0.18, (PP, PP): 0.18, (NW, NW): 0.47, (PO, AA): 0.05,
}
# outer, inner -> (base, opposite pair, all sides or None)
ENC_MODES = {
    (M1, CT): (0.0, 0.04, 0.025),
    (PO, CT): (0.01, 0.04, 0.025),
    (AA, CT): (0.015, 0.03, None),
    (M1, V1): (0.0, 0.04, 0.03),
    (M2, V1): (0.005, 0.02, None),
}
# outer, inner -> (value, forced); not forced: the original distance if smaller
# (conditional rules the table cannot express, e.g. NP_EN_3 exempts PO
# crossing the NP / PP edge)
ENC = {
    (AA, PO): (0.11, True),     # PO_EX_1 AA beyond gate
    (PO, AA): (0.14, False),    # PO_EX_2 gate beyond AA (exempt at PO bends: kept, not forced)
    (NP, PO): (0.15, False), (PP, PO): (0.15, False),   # NP_EN_3 / PP_EN_3
    (NP, AA): (0.12, False), (PP, AA): (0.12, False),   # NP_EN_2 / PP_EN_2 (N+ / P+ AA)
    (NW, AA): (0.15, False),                            # ACT_EN_1 / ACT_EN_2
}
# enclosures of AA that the deck measures corner to corner (euclidean): also
# between a step of the outer edge and the AA beside it
CORNER_ENC = {(NW, AA), (NP, AA), (PP, AA)}
# spacings that are kept (original distance if smaller): conditional on the
# implant type of the AA, which the table does not see
SPACE_KEEP = {(NP, AA): 0.12, (PP, AA): 0.12,      # NP_S_2 / PP_S_2
              (NW, AA): 0.15}                       # ACT_S_5 / ACT_S_8
# wide shapes: (layer): (width above which, run length above which, space)
WIDE = {AA: (0.2, 0.3, 0.125), PO: (0.13, 0.18, 0.18), M1: (0.42, 0.42, 0.15),
        M2: (0.42, 0.42, 0.15)}   # ACT_S_2, PO_S_2, MET1_S_2, M2_S_2
# Distance to the cell boundary: original distance, at most this (half of the
# spacing rule); FORCE_HALF layers get the full value even if they were closer.
HALF = {AA: 0.055, PO: 0.06, CT: 0.06, M1: 0.045, V1: 0.065, M2: 0.05}
FORCE_HALF = {V1}
NW_STEP = 0.32      # NW1_W_1 0.47 minus the 0.15 NW overhang past the boundary
# layer pairs whose order / overlap / coincident edges are kept (besides the rule tables)
RELATED = {frozenset(p) for p in [(AA, PO), (AA, NP), (AA, PP), (NW, AA), (NW, PP), (NW, NP), (NP, PP),
                                  (PO, NP), (PO, PP), (NW, PO), (AA, CT), (PO, CT), (M1, CT), (M1, V1),
                                  (M2, V1)]}
# poly / diffusion against implant / well edges: an edge never passes the
# other one (whether a poly end crosses the NP / PP edge decides NP_EN_3, ...)
ORDER = {frozenset(p) for p in [(PO, NP), (PO, PP), (AA, NP), (AA, PP), (AA, NW), (PO, NW)]}
OVERLAP = {frozenset(p) for p in [(AA, PO), (AA, NP), (AA, PP), (NW, AA), (NW, PP), (NW, NP)]}


def related(la, lb):
    return la == lb or frozenset((la, lb)) in RELATED or la not in DEVICE or lb not in DEVICE


# line ends (end edge shorter than w between two convex corners) facing a shape
# of the layer: space (MET1_S_5, PO_S_9, M2_S_5; conservative, the dense line
# end condition is not checked)
LINE_END = {M1: (0.11, 0.11), PO: (0.09, 0.14), M2: (0.12, 0.12)}
AREA = {M1: 0.042, M2: 0.052, PO: 0.04}     # MET1_A_1, M2_A_1, PO_A_1
SPACE_PROJ = {(NP, NP), (PP, PP)}    # OPPOSITE rules: no corner to corner spacing
WIN = 0.6
RAIL = 80          # dbu, rail half width
STAIR = 20         # dbu, staircase step for 45 degree well / implant edges
MAXMOVE = 0.4


def um(v):
    return int(round(v * UM))


class Contour:
    __slots__ = ('layer', 'poly', 'pts', 'hole')

    def __init__(self, layer, poly, pts, hole):
        self.layer, self.poly, self.pts, self.hole = layer, poly, pts, hole


class Edge:
    __slots__ = ('k', 'layer', 'poly', 'x', 'y1', 'y2', 'side', 'pidx', 'contour', 'fixed', 'end')

    def __init__(self, k, layer, poly, x, y1, y2, side, contour, pidx):
        self.k, self.layer, self.poly, self.x, self.y1, self.y2 = k, layer, poly, x, y1, y2
        self.side, self.contour, self.pidx = side, contour, pidx
        self.fixed = None
        self.end = False


def _diag_edges(p):
    return [e for e in p.each_edge() if e.p1.x != e.p2.x and e.p1.y != e.p2.y]


def _bands(p, wmax=250):
    """Pairs of parallel diagonal edges of p that form a band (a 45 degree
    wire piece): opposite direction, closer than wmax, overlapping."""
    ds = _diag_edges(p)
    out, used = [], set()
    for i, e in enumerate(ds):
        if i in used:
            continue
        best = None
        for j, f in enumerate(ds):
            if j == i or j in used:
                continue
            de, df = e.d(), f.d()
            if de.x * df.y - de.y * df.x != 0 or de.x * df.x + de.y * df.y >= 0:
                continue
            dist = abs(e.distance(f.p1))
            if dist > wmax:
                continue
            if best is None or dist < best[0]:
                best = (dist, j)
        if best:
            used.update((i, best[1]))
            out.append((e, ds[best[1]], best[0]))
    return out


def _path(c1, c2, w, via):
    """Manhattan path of width w from c1 over the points in via to c2."""
    pts = [c1] + via + [c2]
    r = db.Region()
    h = w // 2
    for a, b in zip(pts, pts[1:]):
        r.insert(db.Box(min(a.x, b.x) - h, min(a.y, b.y) - h, max(a.x, b.x) + h, max(a.y, b.y) + h))
    return r.merged()


def _staircase(cur, diag, others, step=10):
    """Polygon cur with the diagonal edge diag replaced by a staircase of
    step dbu along it (within step / sqrt(2) of the edge), on the side that
    keeps one polygon and does not touch others; None if neither does."""
    a, b = diag.p1, diag.p2
    n = max(1, abs(b.x - a.x) // step)
    sx, sy = (b.x - a.x) / n, (b.y - a.y) / n
    pts = list(cur.each_point_hull())
    i = next(k for k in range(len(pts)) if pts[k] == a and pts[(k + 1) % len(pts)] == b)
    for xfirst in (True, False):
        st = []
        for k in range(n):
            x0, y0 = round(a.x + k * sx), round(a.y + k * sy)
            x1, y1 = round(a.x + (k + 1) * sx), round(a.y + (k + 1) * sy)
            st.append(db.Point(x1, y0) if xfirst else db.Point(x0, y1))
            st.append(db.Point(x1, y1))
        st = st[:-1]          # the last point is b
        trial = db.Region(db.Polygon(pts[:i + 1] + st + pts[i + 1:])).merged()
        if trial.count() == 1 and others.interacting(trial).is_empty():
            return next(iter(trial.each()))
    return None


def _corner_fix(cur, others):
    """Replace the remaining diagonal edges of polygon cur by a corner (a
    staircase where neither corner fits)."""
    for _ in range(200):
        diag = next(iter(_diag_edges(cur)), None)
        if diag is None:
            return cur
        a, b = diag.p1, diag.p2
        add = cut = None
        for c in (db.Point(a.x, b.y), db.Point(b.x, a.y)):
            tri = db.Region(db.Polygon([a, c, b]))
            cen = db.Point(round((a.x + b.x + c.x) / 3), round((a.y + b.y + c.y) / 3))
            if cur.inside(cen):
                cut = tri
            else:
                add = tri
        nxt = None
        for cand, op in ((add, '+'), (cut, '-')):
            if cand is None:
                continue
            trial = ((db.Region(cur) + cand) if op == '+' else (db.Region(cur) - cand)).merged()
            if trial.count() == 1 and others.interacting(trial).is_empty():
                nxt = trial
                break
        if nxt is None:
            st = _staircase(cur, diag, others)
            if st is None:
                return cur
            cur = st
            continue
        cur = next(iter(nxt.each()))
    return cur


def _manhattan_poly(p, others, space):
    """Manhattan version of polygon p, keeping away from region others."""
    cur = db.Region(p)
    for e, f, dist in _bands(p):
        w = max(10, int(round(dist / 10.0)) * 10)
        quad = db.Region(db.Polygon([e.p1, e.p2, f.p1, f.p2]))
        # band ends: e.p1 pairs with f.p2, e.p2 with f.p1 (opposite directions)
        c1 = db.Point((e.p1.x + f.p2.x) // 2, (e.p1.y + f.p2.y) // 2)
        c2 = db.Point((e.p2.x + f.p1.x) // 2, (e.p2.y + f.p1.y) // 2)
        cands = []
        for via in ([db.Point(c2.x, c1.y)], [db.Point(c1.x, c2.y)]):
            cands.append((cur - quad) + _path(c1, c2, w, via))
        x0, x1 = sorted((c1.x, c2.x))
        for mx in range(x0 - w, x1 + w + 1, 10):
            cands.append((cur - quad) + _path(c1, c2, w, [db.Point(mx, c1.y), db.Point(mx, c2.y)]))
        y0, y1 = sorted((c1.y, c2.y))
        for my in range(y0 - w, y1 + w + 1, 10):
            cands.append((cur - quad) + _path(c1, c2, w, [db.Point(c1.x, my), db.Point(c2.x, my)]))
        # both corners filled (short jogs)
        fill = db.Region()
        for g in (e, f):
            for c in (db.Point(g.p1.x, g.p2.y), db.Point(g.p2.x, g.p1.y)):
                cen = db.Point(round((g.p1.x + g.p2.x + c.x) / 3), round((g.p1.y + g.p2.y + c.y) / 3))
                if not p.inside(cen):
                    fill.insert(db.Polygon([g.p1, c, g.p2]))
        cands.append(cur + fill)
        best = None
        for trial in cands:
            trial = trial.merged()
            if trial.count() != 1 or not others.interacting(trial).is_empty():
                continue
            q = next(iter(trial.each()))
            ndiag = len(_diag_edges(q))
            viol = 0
            if space:
                for chk, wt in ((trial.separation_check(others, space), 1), (trial.width_check(space), 10),
                                (trial.space_check(space), 1)):
                    for ep in chk.each():
                        d = space - ep.distance()
                        # vertical gaps are hard to make (fixed cell height); a too
                        # narrow shape of its own cannot be repaired by moving others
                        vert = ep.first.dy() == 0 and ep.second.dy() == 0
                        viol += d * (3 if vert else 1) * wt
            key = (viol, ndiag, q.num_points(), trial.area())
            if best is None or key < best[0]:
                best = (key, trial)
        if best:
            cur = best[1]
    return _corner_fix(next(iter(cur.merged().each())), others)


def manhattanize(region, space=0, rounds=3, stair=False):
    """Replace 45 degree geometry by Manhattan geometry. Bands (45 degree wire
    pieces) become a Manhattan path of the band width between the band ends
    (L or Z route, the one that keeps the most space to the other shapes);
    single diagonal edges become a corner (adding area unless that touches
    another shape, else cutting). Shapes never merge with others. In further
    rounds every diagonal shape is routed again against the others' results,
    so neighbouring 45 degree wires find positions that fit together.
    stair (well / implant edges): every diagonal edge becomes a staircase of
    STAIR steps along it instead, so the distances to the devices stay."""
    polys = list(region.each())
    diag = [k for k, p in enumerate(polys) if not p.is_rectilinear()]
    if not diag:
        return region.merged()
    if stair:
        res = list(polys)
        for k in diag:
            others = db.Region([res[j] for j in range(len(polys)) if j != k])
            cur = polys[k]
            for _ in range(200):
                d = next(iter(_diag_edges(cur)), None)
                if d is None:
                    break
                st = _staircase(cur, d, others, step=STAIR)
                if st is None:
                    cur = _corner_fix(cur, others)
                    break
                cur = st
            res[k] = cur
        return db.Region(res).merged()
    res = list(polys)
    for rnd in range(rounds):
        for k in diag:
            if rnd == 0:
                others = db.Region([res[j] for j in range(len(polys)) if j != k and (j < k or j not in diag)]) + \
                    db.Region([polys[j] for j in diag if j > k])
            else:
                others = db.Region([res[j] for j in range(len(polys)) if j != k])
            res[k] = _manhattan_poly(polys[k], others, space)
    return db.Region(res).merged()


def cross_implant_edge(layers, ext=20, only=None, strict=False):
    """NP_EN_3 / PP_EN_3: field poly closer than 0.15 to the NP / PP edge
    inside the cell is extended across it (poly crossing both implants is
    exempt, PO_CUT), if that does not touch other poly (strict: no other poly
    within the poly spacing either). only: a Region, just the poly ends that
    touch it (markers). Returns the number of extensions."""
    if not all(l in layers for l in (PO, NP, PP)):
        return 0
    po, aa, np_, pp = layers[PO], layers.get(AA, db.Region()), layers[NP], layers[PP]
    add = db.Region()
    for imp, other in ((np_, pp), (pp, np_)):
        fpo = po - aa
        cut = fpo.interacting(np_).interacting(pp)
        for ep in imp.enclosing_check(fpo - cut, 150, projection=True).each() \
                if False else imp.enclosing_check(fpo - cut, 150).each():
            ie, pe = ep.first, ep.second           # implant edge, poly edge
            if ie.dy() != 0 or pe.dy() != 0:
                continue                           # only the horizontal NP / PP edge
            if only is not None and only.interacting(db.Region(ep.bbox().enlarged(1, 1))).is_empty():
                continue
            y = ie.p1.y
            x1, x2 = sorted((pe.p1.x, pe.p2.x))
            # the other implant beyond the edge
            probe = db.Region(db.Box(x1, y - 2, x2, y + 2))
            if (probe & other).is_empty():
                continue
            yp = pe.p1.y
            box = db.Box(x1, min(yp, y + (ext if y > yp else -ext)), x2, max(yp, y + (ext if y > yp else -ext)))
            rect = db.Region(box)
            if not (rect.sized(1) & aa).is_empty():
                continue                           # a new gate
            # must not touch other poly (or another extension): that would join
            # two nets; a gap below the poly spacing is left to the legalizer
            near = um(SPACE[(PO, PO)]) - 1 if strict else 1
            if (po + add).merged().interacting(rect.sized(near)).count() != 1:
                continue
            add += rect
    if not add.is_empty():
        layers[PO] = (po + add).merged()
    return add.count()


def implant_jog(layers, marks, enc=150, wmin=180):
    """NP_EN_3 / PP_EN_3 markers (rule, box) between a poly end and the
    NP / PP edge that the poly cannot move away from (gate extension): a local
    step of the edge, the enclosing implant grows by the shortfall over the
    poly end +- a margin (the other implant loses it): as little as the
    euclidean enclosure of the poly corners and the implant width / notch
    (0.18) allow, so the step stays away from the gates of the other type
    (NP_EX_1 / PP_EX_1). Not where it would cover AA. Returns the number of
    steps."""
    if not all(l in layers for l in (PO, NP, PP)):
        return 0
    po, aa = layers[PO], layers.get(AA, db.Region())
    n = 0
    for rule, box in marks:
        if rule not in ('NP_EN_3', 'PP_EN_3'):
            continue
        grow, other = (NP, PP) if rule == 'NP_EN_3' else (PP, NP)
        h = box.height()
        if h >= enc or box.width() == 0:
            continue
        # which side the poly is on: the box edge covered by poly
        for yp, ye in ((box.top, box.bottom), (box.bottom, box.top)):
            # just inside the poly: beyond the box edge
            probe = db.Region(db.Box(box.left, yp if yp == box.top else yp - 1, box.right,
                                     yp + 1 if yp == box.top else yp))
            pe = po & probe
            if not pe.is_empty() and not (layers[grow] & db.Region(db.Box(box.left, ye - 1, box.right, ye + 1))).is_empty():
                break
        else:
            continue
        x1, x2 = pe.bbox().left, pe.bbox().right
        d = enc - h
        margin = max(int(math.ceil(math.sqrt(enc * enc - h * h))), int(math.ceil((wmin - (x2 - x1)) / 2))) + 1
        if yp > ye:      # poly above the edge: the implant grows downwards
            strip = db.Box(x1 - margin, ye - d, x2 + margin, ye)
        else:
            strip = db.Box(x1 - margin, ye, x2 + margin, ye + d)
        r = db.Region(strip)
        if not (r & aa).is_empty():
            continue
        layers[grow] = (layers[grow] + r).merged()
        layers[other] = (layers[other] - r).merged()
        n += 1
    return n


class Cell:
    """Flat, merged, Manhattan geometry of a cell, coordinates in dbu."""

    def __init__(self, layers, texts, bnd_box):
        self.layers = layers          # layer -> Region
        self.texts = texts            # [(layer, db.Text)]
        self.bnd = bnd_box

    @classmethod
    def from_layout(cls, layout, cell, cross=True):
        layers, texts = {}, []
        for li in layout.layer_indexes():
            info = layout.get_info(li)
            lay = (info.layer, info.datatype)
            r = db.Region(cell.begin_shapes_rec(li))
            if not r.is_empty():
                layers[lay] = manhattanize(r.merged(), um(SPACE.get((lay, lay), 0)), stair=lay in (NW, NP, PP))
            it = cell.begin_shapes_rec(li)
            while not it.at_end():
                s = it.shape()
                if s.is_text():
                    texts.append((lay, s.text.transformed(it.trans())))
                it.next()
        bnd = layers[BND].bbox()
        if cross:
            cross_implant_edge(layers)
        return cls(layers, texts, bnd)

    def transposed(self):
        t = db.Trans(db.Trans.M45, 0, 0)
        return Cell({l: r.transformed(t) for l, r in self.layers.items()},
                    [(l, x.transformed(t)) for l, x in self.texts], self.bnd.transformed(t))

    def write(self, layout, cell):
        cell.clear()
        for lay, r in self.layers.items():
            cell.shapes(layout.layer(*lay)).insert(r)
        for lay, t in self.texts:
            cell.shapes(layout.layer(*lay)).insert(t)


def measure_enc(box, outer, d=100):
    """Enclosure of box by region outer on left, right, bottom, top (dbu, capped at d)."""
    res = []
    for side in range(4):
        if side == 0:
            strip = db.Box(box.left - d, box.bottom, box.left, box.top)
        elif side == 1:
            strip = db.Box(box.right, box.bottom, box.right + d, box.top)
        elif side == 2:
            strip = db.Box(box.left, box.bottom - d, box.right, box.bottom)
        else:
            strip = db.Box(box.left, box.top, box.right, box.top + d)
        out = db.Region(strip) - outer
        if not (db.Region(box) - outer).is_empty():
            res.append(-1)
            continue
        if out.is_empty():
            res.append(d)
            continue
        bb = [p.bbox() for p in out.each()]
        if side == 0:
            res.append(box.left - max(b.right for b in bb))
        elif side == 1:
            res.append(min(b.left for b in bb) - box.right)
        elif side == 2:
            res.append(box.bottom - max(b.top for b in bb))
        else:
            res.append(min(b.bottom for b in bb) - box.top)
    return res


def choose_modes(cell):
    """{(outer layer, inner box): (x requirement, y requirement)} in dbu."""
    modes = {}
    for (outer, inner), (base, hi, allv) in ENC_MODES.items():
        if outer not in cell.layers or inner not in cell.layers:
            continue
        orr = cell.layers[outer]
        for n, p in enumerate(cell.layers[inner].each()):
            b = p.bbox()
            if not orr.interacting(db.Region(b)).count():
                continue
            l, r, bo, t = measure_enc(b, orr)
            cands = [((hi, base), um(hi) * 0 + sum(max(0, um(v) - e) for v, e in
                                                    ((hi, l), (hi, r), (base, bo), (base, t)))),
                     ((base, hi), sum(max(0, um(v) - e) for v, e in
                                      ((base, l), (base, r), (hi, bo), (hi, t))))]
            if allv is not None:
                cands.append(((allv, allv), sum(max(0, um(allv) - e) for e in (l, r, bo, t))))
            cands.sort(key=lambda c: c[1])
            modes[(outer, inner, n)] = Mode([(um(vx), um(vy)) for (vx, vy), _ in cands])
    # small shapes: stretched along the long axis first, else the other one
    for lay, amin in AREA.items():
        if lay not in cell.layers:
            continue
        a2 = um(amin) * um(1)
        for n, p in enumerate(cell.layers[lay].each()):
            if p.area() >= 1.5 * a2:
                continue          # (shapes near the minimum too: other rules may shrink them)
            b = p.bbox()
            if b.left <= cell.bnd.left or b.right >= cell.bnd.right:
                continue          # crossing the boundary (rails): merged with the neighbours
            modes[('area', lay, n)] = Mode(['y', 'x'] if b.height() >= b.width() else ['x', 'y'])
    return modes


class Mode:
    """Enclosure alternatives of one via (x, y requirement), best first."""

    def __init__(self, cands):
        self.cands, self.i = cands, 0

    def get(self):
        return self.cands[self.i]

    def relax(self, axis):
        """Switch to the next alternative that needs less on axis; False if none."""
        if isinstance(self.cands[0], str):       # area: axis to stretch
            if self.i + 1 < len(self.cands):
                self.i += 1
                return True
            return False
        k = 0 if axis == 'x' else 1
        cur = self.cands[self.i][k]
        for j in range(len(self.cands)):
            if j != self.i and self.cands[j][k] < cur:
                self.i = j
                return True
        return False


# DRC markers of a checked fixed cell fed back as constraints (make_fixed.py):
# rule -> (layers, value um); None: the two shapes must not overlap (PP_R_1)
MARKER_RULES = {
    'ACT_S_1': ({AA}, 0.11), 'ACT_S_2': ({AA}, 0.125), 'ACT_S_5': ({NW, AA}, 0.15),
    'ACT_EN_1': ({NW, AA}, 0.15), 'ACT_EN_2': ({NW, AA}, 0.15),
    'PO_S_1': ({PO}, 0.12), 'PO_S_2': ({PO}, 0.18), 'PO_S_3': ({PO}, 0.13), 'PO_S_9': ({PO}, 0.14),
    'PO_S_14': ({AA, PO}, 0.10), 'PO_S_15': ({AA, PO}, 0.10),
    'PO_EX_1': ({AA, PO}, 0.11), 'PO_EX_2': ({PO, AA}, 0.14),
    'NP_EN_3': ({NP, PO}, 0.15), 'PP_EN_3': ({PP, PO}, 0.15),
    'NP_EX_1_EX_1a': ({NP, PO}, 0.16), 'PP_EX_1_EX_1a': ({PP, PO}, 0.16),
    'PP_R_1': ({PP, NP}, None),
    'CT_S_4': ({CT, PO}, 0.055),
    'MET1_S_1': ({M1}, 0.09), 'MET1_S_2': ({M1}, 0.15), 'MET1_S_5': ({M1}, 0.11),
    'V1_S_1': ({V1}, 0.11), 'V1_S_3': ({V1}, 0.13),
    'M2_S_1': ({M2}, 0.10), 'M2_S_5': ({M2}, 0.12),
}


class Fix:
    """A marker as a constraint between two edges of one axis (pass
    coordinates: x, or y on the transposed cell): b - a >= v (collapse: a >= b).
    a, b: [layer, position, lo, hi]; positions follow the passes."""

    def __init__(self, axis, rule, a, b, v, collapse=False):
        self.axis, self.rule, self.a, self.b, self.v, self.collapse = axis, rule, a, b, v, collapse

    def copy(self):
        return Fix(self.axis, self.rule, list(self.a), list(self.b), self.v, self.collapse)

    def __repr__(self):
        return f'{self.rule} {self.axis} {self.a} {self.b} {self.v}{" collapse" if self.collapse else ""}'


def _axis_edges(cell):
    out = []
    for lay, r in cell.layers.items():
        for p in r.each():
            for pts in [list(p.each_point_hull())] + [list(p.each_point_hole(h)) for h in range(p.holes())]:
                m = len(pts)
                for i in range(m):
                    a, b = pts[i], pts[(i + 1) % m]
                    if a.x == b.x and a.y != b.y:
                        out.append((lay, a.x, min(a.y, b.y), max(a.y, b.y)))
    return out


def _fix_axis(E, bnd, b, layers, v, rule, axis):
    """(Fix, overlap) for marker box b (pass coordinates) or None."""
    lo, hi = b.bottom, b.top

    def at(x):
        c = [(min(e[3], hi) - max(e[2], lo), e) for e in E if e[0] in layers and e[1] == x
             and e[2] <= hi and e[3] >= lo]
        return max(c, key=lambda t: t[0]) if c else None
    x1, x2 = b.left, b.right
    half = None if v is None else int(math.ceil(um(v) / 2))
    if x1 < bnd.left < x2 and half:
        A, B = (0, (BND, bnd.left, bnd.bottom, bnd.top)), at(x2)
        val = half
    elif x1 < bnd.right < x2 and half:
        A, B = at(x1), (0, (BND, bnd.right, bnd.bottom, bnd.top))
        val = half
    elif x1 == x2:
        if v is None:
            return None
        A = at(x1)
        if A is None:
            return None
        c = [(abs(e[1] - x1), min(e[3], hi) - max(e[2], lo), e) for e in E if e[0] in layers
             and 0 < abs(e[1] - x1) < um(v) and min(e[3], hi) - max(e[2], lo) > 0]
        if not c:
            return None
        _, ov, e = min(c, key=lambda t: t[0])
        B = (ov, e)
        if e[1] < x1:
            A, B = B, A
        val = um(v)
    else:
        A, B = at(x1), at(x2)
        val = None if v is None else um(v)
    if A is None or B is None or A[1] is B[1]:
        return None
    if len(layers - {BND}) == 2 and BND not in (A[1][0], B[1][0]) and A[1][0] == B[1][0]:
        return None          # a two layer rule is between edges of both layers
    if axis == 'y' and A[1][0] in FROZEN_Y and B[1][0] in FROZEN_Y:
        return None
    ov = min(A[0], B[0]) if A[1][0] != BND and B[1][0] != BND else max(A[0], B[0])
    f = Fix(axis, rule, list(A[1]), list(B[1]), 0 if val is None else val, collapse=val is None)
    return f, ov


def fixes_from_markers(cell, marks):
    """[(rule, db.Box in cell coordinates)] -> ([Fix], [unhandled rule])."""
    t = db.Trans(db.Trans.M45, 0, 0)
    tc = cell.transposed()
    E = {'x': _axis_edges(cell), 'y': _axis_edges(tc)}
    bnd = {'x': cell.bnd, 'y': tc.bnd}
    fixes, skipped = [], []
    for rule, box in marks:
        if rule not in MARKER_RULES:
            skipped.append(rule)
            continue
        layers, v = MARKER_RULES[rule]
        layers = set(layers) | {BND}
        cand = []
        for axis in ('x', 'y'):
            b = box if axis == 'x' else box.transformed(t)
            r = _fix_axis(E[axis], bnd[axis], b, layers, v, rule, axis)
            if r:
                cand.append((r[1], axis == 'x', r[0]))
        good = [c for c in cand if c[0] > 0]
        if good:
            fixes.append(max(good, key=lambda c: (c[0], c[1]))[2])
            continue
        fx = next((c[2] for c in cand if c[1]), None)
        if fx is not None and v is not None and box.height() < um(v):
            # corner to corner: the x distance that gives the euclidean value
            h = box.height()
            fx.v = int(math.ceil(math.sqrt(um(v) ** 2 - h * h)))
            fixes.append(fx)
        elif cand:
            fixes.append(cand[0][2])
        else:
            skipped.append(rule)
    return fixes, skipped


class Pass:
    def __init__(self, cell, modes, axis, width, frozen=(), freeze=None, hints=(), fixes=()):
        """axis 'x' or 'y' (cell already transposed for 'y'); width: new boundary
        right edge position (dbu) for x, None for y (fixed)."""
        self.cell, self.modes, self.axis = cell, modes, axis
        self.frozen = set(frozen)
        self.freeze = freeze or (lambda p, e: False)
        self.hints = list(hints)
        self.fixes = [f for f in fixes if f.axis == axis]
        self.fix_edges = []
        self.edges, self.contours = [], []
        self.polys = {}                # (layer, n) -> db.Polygon
        self.bnd = cell.bnd
        self.width = width if width is not None else self.bnd.right
        self.grow = self.width - self.bnd.right
        for lay, r in cell.layers.items():
            for n, p in enumerate(r.each()):
                self.polys[(lay, n)] = p
                pts = list(p.each_point_hull())
                self._contour(lay, n, pts, False)
                for h in range(p.holes()):
                    self._contour(lay, n, list(p.each_point_hole(h)), True)
        self.layer_regions = cell.layers
        # tags
        self.ct_on_aa = set()
        if CT in cell.layers and AA in cell.layers:
            for n, p in enumerate(cell.layers[CT].each()):
                if cell.layers[AA].interacting(db.Region(p)).count():
                    self.ct_on_aa.add(n)
        self.wide = set()
        for lay, (wmin, _, _) in WIDE.items():
            if lay in cell.layers:
                for n, p in enumerate(cell.layers[lay].each()):
                    if not db.Region(p).sized(-(um(wmin) // 2 + 1)).is_empty():
                        self.wide.add((lay, n))
        self.m1_of = {}
        if M1 in cell.layers:
            m1 = list(cell.layers[M1].each())
            for lay in (CT, V1):
                if lay in cell.layers:
                    for n, p in enumerate(cell.layers[lay].each()):
                        b = p.bbox().center()
                        self.m1_of[(lay, n)] = next((k for k, q in enumerate(m1) if q.inside(b)), -1 - n)

    def _contour(self, lay, n, pts, hole):
        c = Contour(lay, n, pts, hole)
        self.contours.append(c)
        p = self.polys[(lay, n)]
        m = len(pts)
        for i in range(m):
            a, b = pts[i], pts[(i + 1) % m]
            if a.x != b.x:
                continue
            y1, y2 = min(a.y, b.y), max(a.y, b.y)
            side = 'L' if p.inside(db.Point(a.x + 1, (y1 + y2) // 2)) else 'R'
            e = Edge(len(self.edges), lay, n, a.x, y1, y2, side, c, (i, (i + 1) % m))
            if lay in LINE_END and y2 - y1 < um(LINE_END[lay][0]):
                # both neighbouring edges go to the inside: a line end
                pa, pb = pts[i - 1], pts[(i + 2) % m]
                inward = (lambda q: q.x > a.x) if side == 'L' else (lambda q: q.x < a.x)
                e.end = inward(pa) and inward(pb)
            self.edges.append(e)

    def is_gate(self, a, b, ylo, yhi):
        """PO edges a (L) and b (R) bound a gate: the AA between them is all
        covered by poly (a strap over several fingers is not)."""
        box = db.Region(db.Box(a.x, ylo, b.x, yhi))
        on_aa = box & self.layer_regions[AA]
        if on_aa.is_empty():
            return False
        return (on_aa - self.layer_regions[PO]).is_empty()

    def inside(self, lay, n, x, y):
        return self.polys[(lay, n)].inside(db.Point(x, y))

    def inside_layer(self, lay, x, y):
        r = self.layer_regions.get(lay)
        if r is None:
            return False
        return not r.interacting(db.Region(db.Box(x, y, x + 1, y + 1))).is_empty()

    # -- relations ----------------------------------------------------------
    def space(self, a, b, ymid):
        la, lb = a.layer, b.layer
        key = (la, lb) if (la, lb) in SPACE else (lb, la)
        if {la, lb} == {PO, CT}:
            ct = a if la == CT else b
            return um(0.055) if ct.poly in self.ct_on_aa else None
        if {la, lb} == {CT, AA}:
            ct = a if la == CT else b
            return um(0.065) if ct.poly not in self.ct_on_aa else None
        if key not in SPACE:
            kk = (la, lb) if (la, lb) in SPACE_KEEP else (lb, la)
            if kk in SPACE_KEEP:
                # kept: the original (euclidean) distance, at most the rule
                g = max(b.y1 - a.y2, a.y1 - b.y2, 0)
                return min(um(SPACE_KEEP[kk]), int(math.hypot(b.x - a.x, g)))
            return None
        v = SPACE[key]
        cond = 0
        if la == lb and la in WIDE:
            wmin, run, ws = WIDE[la]
            ylo, yhi = max(a.y1, b.y1), min(a.y2, b.y2)
            if yhi - ylo > um(run) and ((la, a.poly) in self.wide or (lb, b.poly) in self.wide):
                cond = max(cond, ws)
        if la == lb == PO and AA in self.layer_regions and b.x - a.x > 2:
            ylo, yhi = max(a.y1, b.y1), min(a.y2, b.y2)
            if ylo < yhi and not self.layer_regions[AA].interacting(
                    db.Region(db.Box(a.x + 1, ylo, b.x - 1, yhi))).is_empty():
                v = 0.13
        if la == lb and la in LINE_END and (a.end or b.end) and max(a.y1, b.y1) < min(a.y2, b.y2):
            cond = max(cond, LINE_END[la][1])
        if la == lb and la in (CT, V1) and self.m1_of.get((la, a.poly)) != self.m1_of.get((lb, b.poly)):
            v = 0.12 if la == CT else 0.13
        self._cond = um(cond) if cond > v else 0
        return um(v)

    def enclosure(self, outer, inner):
        """outer, inner: edges; value in dbu or None."""
        key = (outer.layer, inner.layer)
        if key in ENC_MODES:
            m = self.modes.get((outer.layer, inner.layer, inner.poly))
            if m is None:
                return um(ENC_MODES[key][0])
            return m.get()[1 if self.axis == 'y' else 0]
        if key in ENC:
            v, force = ENC[key]
            v = um(v) if force else min(um(v), abs(inner.x - outer.x))
            # outer edge beyond the cell top / bottom (implant across the rail):
            # the mirrored row continues the same implant, measure from the
            # boundary (y pass only: a left / right neighbour can differ)
            if self.axis == 'y':
                if outer.x <= self.bnd.left:
                    v = min(v, max(0, inner.x - self.bnd.left))
                elif outer.x >= self.bnd.right:
                    v = min(v, max(0, self.bnd.right - inner.x))
            return v
        return None

    def area_constraints(self, cons):
        """Shapes below the minimum area: a cheap target to stretch in both
        passes (split over x and y as room allows); legalize() checks the
        final areas."""
        amin_of = {lay: um(a) * um(1) for lay, a in AREA.items()}
        by_poly = {}
        for e in self.edges:
            if e.layer in amin_of:
                by_poly.setdefault((e.layer, e.poly), []).append(e)
        for (lay, n), es in by_poly.items():
            if ('area', lay, n) not in self.modes:
                continue
            p = self.polys[(lay, n)]
            if p.area() >= amin_of[lay]:
                continue
            lo = min(es, key=lambda e: e.x)
            hi = max(es, key=lambda e: e.x)
            end = min(lo.y2 - lo.y1, hi.y2 - hi.y1)
            need = hi.x - lo.x + int(math.ceil((amin_of[lay] - p.area()) / max(end, 1)))
            cons.append((lo, hi, need, False, ('cond', f'area {lay[0]}/{lay[1]}')))

    def hint_constraints(self, cons):
        """x separation of shape ends that the y pass could not space apart:
        (layer, poly A, point A, poly B, point B, distance), A left of B."""
        if not self.hints:
            return
        by_poly = {}
        for e in self.edges:
            by_poly.setdefault((e.layer, e.poly), []).append(e)

        def at(lay, n, pt):
            return next((e for e in by_poly.get((lay, n), ()) if e.x == pt[0] and e.y1 <= pt[1] <= e.y2), None)
        for lay, na, pa, nb, pb, d in self.hints:
            ea, eb = at(lay, na, pa), at(lay, nb, pb)
            if ea is not None and eb is not None:
                cons.append((ea, eb, d, False, ('cond', f'space {lay}-{lay} x hint')))

    def fix_constraints(self, cons, tol=60):
        """Marker constraints (hard): the edges found again by layer, position
        and range (ranges are not tracked through the other axis' passes)."""
        def match(s):
            lay, x, lo, hi = s
            c = [(min(e.y2, hi + tol) - max(e.y1, lo - tol), e) for e in self.edges
                 if e.layer == lay and e.x == x and e.y1 <= hi + tol and e.y2 >= lo - tol]
            return max(c, key=lambda t: t[0])[1] if c else None
        self.fix_edges = []
        for f in self.fixes:
            ea, eb = match(f.a), match(f.b)
            if ea is None or eb is None or ea is eb:
                continue
            self.fix_edges.append((f, ea, eb))
            if f.collapse:
                cons.append((eb, ea, 0, False, f'marker {f.rule}'))
            else:
                tag = f'space marker {f.rule}' if ea.layer == eb.layer and ea.layer != BND else f'marker {f.rule}'
                cons.append((ea, eb, f.v, False, tag))

    def update_fixes(self, xs):
        for f, ea, eb in self.fix_edges:
            f.a[1], f.b[1] = int(xs[ea.k]), int(xs[eb.k])

    def constraints(self):
        cons = []     # (a, b, value, eq, tag)
        self.area_constraints(cons)
        self.hint_constraints(cons)
        self.fix_constraints(cons)
        E = sorted(self.edges, key=lambda e: e.x)
        win = um(WIN)
        xs = [e.x for e in E]
        n = len(E)
        bl, br = self.bnd.left, self.bnd.right
        j0 = 0
        for i, a in enumerate(E):
            j = i + 1
            while j < n and xs[j] - a.x <= win:
                b = E[j]
                j += 1
                self.pair(a, b, cons)
                if b.x == a.x:
                    self.pair(b, a, cons)
        return cons

    def pair(self, a, b, cons):
        d0 = b.x - a.x
        g = max(b.y1 - a.y2, a.y1 - b.y2)
        la, lb = a.layer, b.layer
        if la == BND or lb == BND:
            self.pair_bnd(a, b, d0, g, cons)
            return
        if g >= um(0.5):
            return
        outside = not (self.bnd.left < a.x < self.bnd.right and self.bnd.left < b.x < self.bnd.right)
        ylo, yhi = max(a.y1, b.y1), min(a.y2, b.y2)
        ymid = (ylo + yhi) // 2
        same = la == lb and a.poly == b.poly
        if same and g >= 0 and a.side == 'L' and b.side == 'R' and la in WIDTH and g < um(WIDTH[la]) \
                and la not in RIGID:
            # corner to corner width across a step of one shape
            w = um(WIDTH[la])
            v = int(math.ceil(math.sqrt(w * w - g * g)))
            ya, yb = (a.y1, b.y2) if a.y1 >= b.y2 else (a.y2, b.y1)
            if self.inside(la, a.poly, (a.x + b.x) // 2, (ya + yb) // 2):
                cons.append((a, b, min(v, d0) if outside else v, False, f'width {la}'))
            return
        if same and g >= 0 and a.side == b.side and g < um(WIDTH.get(la, 0.1)):
            # edges of one shape that do not overlap in y must not pass each
            # other either, or a thin piece appears between them; directly
            # adjacent M1 ones (a step, g == 0: nothing in between) only keep
            # their order, so a staircase (45 degree replacement) can flatten
            cons.append((a, b, 0 if g == 0 and la == M1 else min(d0, um(WIDTH.get(la, 0.1))), False))
            return
        if a.side == b.side and la != lb and self.enc_pair(a, b, g, ymid, cons):
            return
        if self.axis == 'y' and g < 0 and la != lb and frozenset((la, lb)) in ORDER and not outside:
            cons.append((a, b, min(d0, 1), d0 == 0))
        if a.side == 'R' and b.side == 'L':
            s = self.space(a, b, ymid) if (la == lb or la in DEVICE and lb in DEVICE) else None
            if s is not None and g > 0 and (la, lb) in SPACE_PROJ:
                return
            if la == lb and d0 == 0:
                return      # shape touching itself / another one (butted implants)
            if s is not None:
                if g >= s:
                    return
                if g > 0:
                    # corner to corner: not if the space between the corners is inside
                    ya, yb = (a.y1, b.y2) if a.y1 >= b.y2 else (a.y2, b.y1)
                    mx, my = (a.x + b.x) // 2, (ya + yb) // 2
                    if self.inside_layer(la, mx, my) or self.inside_layer(lb, mx, my):
                        return
                    s = int(math.ceil(math.sqrt(s * s - g * g)))
                cond = getattr(self, '_cond', 0)
                self._cond = 0
                if outside:
                    s = min(s, d0)
                    cond = 0
                cons.append((a, b, s, False, f'space {la}-{lb}'))
                if cond > s and g < 0:
                    # conditional rule (line end, wide shape): not closer than
                    # now, the full value only if it costs little
                    if min(cond, d0) > s:
                        cons.append((a, b, min(cond, d0), False, None))
                    cons.append((a, b, cond, False, ('cond', f'space {la}-{lb} cond')))
            elif d0 == 0 and g < 0 and related(la, lb):
                cons.append((a, b, 0, True))
            return
        if g >= 0:
            return
        if a.side == 'L' and b.side == 'R':
            if same:
                mid = (a.x + b.x) // 2
                if not self.inside(la, a.poly, mid, ymid):
                    return
                if la in RIGID:
                    cons.append((a, b, d0, True))
                elif la == PO and AA in self.layer_regions and self.is_gate(a, b, ylo, yhi):
                    cons.append((a, b, d0, True))
                elif la in WIDTH:
                    w = um(WIDTH[la])
                    cons.append((a, b, min(w, d0) if outside else w, False, f'width {la}'))
                else:
                    cons.append((a, b, min(d0, um(0.1)), False))
            elif frozenset((la, lb)) in OVERLAP:
                cons.append((a, b, min(d0, um(0.12)), False))
            elif la != lb and (la not in DEVICE or lb not in DEVICE):
                cons.append((a, b, 0, False))
            return
        if a.side == b.side and la != lb and related(la, lb) and not (
                (la, lb) in ENC or (lb, la) in ENC or (la, lb) in ENC_MODES or (lb, la) in ENC_MODES):
            # no rule: keep an inner shape inside (probe just inside the inner edge)
            if a.side == 'L':
                outer, inner, px = a, b, b.x + 1
            else:
                outer, inner, px = b, a, a.x - 1
            if self.inside(outer.layer, outer.poly, px, ymid):
                cons.append((a, b, 0, d0 == 0))

    def enc_pair(self, a, b, g, ymid, cons):
        """Enclosure rule between two same side edges; True if one applies.
        Outer / inner come from the rule tables, the direction from the side,
        so an edge that already crossed the other is pulled back."""
        for outer, inner in ((a, b), (b, a)):
            key = (outer.layer, inner.layer)
            if key not in ENC_MODES and key not in ENC:
                continue
            m = self.modes.get((outer.layer, inner.layer, inner.poly))
            if g >= 0 and key in CORNER_ENC:
                # well / implant around AA beside it (a step of the outer
                # edge): euclidean, the x distance for the y gap g
                v, force = ENC[key]
                v = um(v)
                if g >= v or (inner.side == 'L') != (outer.x <= inner.x):
                    return False
                px = (outer.x + inner.x) // 2 if outer.x != inner.x else \
                    (inner.x + 1 if inner.side == 'L' else inner.x - 1)
                if not self.inside(outer.layer, outer.poly, px, (inner.y1 + inner.y2) // 2):
                    return False
                vc = int(math.ceil(math.sqrt(v * v - g * g)))
                if not force:
                    vc = min(vc, abs(outer.x - inner.x))
                if vc > 0:
                    pair = (outer, inner) if inner.side == 'L' else (inner, outer)
                    cons.append(pair + (vc, False, f'enc {outer.layer}/{inner.layer} corner'))
                return True
            if g >= 0:
                # beside the inner shape: only for rigid inner shapes (their
                # corner must stay enclosed), closer than the enclosure across
                if key not in ENC_MODES:
                    return False
                across = m.get()[0 if self.axis == 'y' else 1] if m else um(ENC_MODES[key][0])
                if g >= max(across, 1):
                    return False
            # outer edge on the outside of the inner one (L: left of it, R: right)
            if (inner.side == 'L') != (outer.x <= inner.x) and outer.x != inner.x:
                continue
            iy = (inner.y1 + inner.y2) // 2 if g >= 0 else ymid
            if outer.x == inner.x:
                px = inner.x + 1 if inner.side == 'L' else inner.x - 1
            else:
                px = (outer.x + inner.x) // 2
            if not self.inside(outer.layer, outer.poly, px, iy):
                continue
            v = self.enclosure(outer, inner)
            tag = ('mode', (outer.layer, inner.layer, inner.poly)) if m else f'enc {outer.layer}/{inner.layer}'
            if inner.side == 'L':
                cons.append((outer, inner, v, False, tag))     # x_inner - x_outer >= v
            else:
                cons.append((inner, outer, v, False, tag))     # x_outer - x_inner >= v
            return True
        return False

    def pair_bnd(self, a, b, d0, g, cons):
        if g >= 0:
            return
        if a.layer == BND and b.layer == BND:
            return
        e, bnd = (b, a) if a.layer == BND else (a, b)
        if d0 == 0:
            cons.append((a, b, 0, True))
            return
        lay = e.layer
        if lay == NW and self.axis == 'x' and self.bnd.left < e.x < self.bnd.right:
            # NW steps (the well edge changing level) next to a side: with the
            # NW overhang of the cell, a neighbour can make the NW narrower
            # than NW1_W_1 across the seam unless the step is far enough in
            v = um(NW_STEP)
            if a.layer == BND and a.side == 'L':
                cons.append((a, b, v, False, 'half NW step'))
            elif b.layer == BND and b.side == 'R':
                cons.append((a, b, v, False, 'half NW step'))
            return
        if lay not in HALF:
            if a.layer == BND and a.side == 'L' and b.side == 'L' or \
                    b.layer == BND and b.side == 'R' and a.side == 'R':
                cons.append((a, b, 0, False))
            return
        h = um(HALF[lay])
        v = h if lay in FORCE_HALF else min(d0, h)
        if lay in WIDE and self.axis == 'x' and (lay, e.poly) in self.wide and e.y2 - e.y1 > um(WIDE[lay][1]):
            # wide shape along the side (ACT_S_2, PO_S_2, ...): the neighbour's
            # shape can be wide too, so half the wide spacing, also if closer now
            v = max(v, int(math.ceil(um(WIDE[lay][2]) / 2 / 5)) * 5)
        if a.layer == BND and a.side == 'L' and b.side == 'L':
            cons.append((a, b, v, False, f'half {lay}'))
        elif b.layer == BND and b.side == 'R' and a.side == 'R':
            cons.append((a, b, v, False, f'half {lay}'))

    # -- solve ----------------------------------------------------------------
    def solve(self, extra=()):
        n = len(self.edges)
        bl, br = self.bnd.left, self.bnd.right
        lo = np.empty(n)
        hi = np.empty(n)
        mm = um(MAXMOVE)
        for e in self.edges:
            if e.layer in self.frozen or e.x <= bl or (self.axis == 'y' and e.x >= br) or self.freeze(self, e):
                v = e.x if e.x < br or self.axis == 'y' else e.x + self.grow
                lo[e.k] = hi[e.k] = v
            elif e.x >= br:
                lo[e.k] = hi[e.k] = e.x + self.grow
            else:
                lo[e.k] = e.x - mm
                hi[e.k] = e.x + mm + self.grow
        cons = [c if len(c) == 5 else c + (None,) for c in self.constraints() + list(extra)]
        x0 = np.array([e.x + (self.grow if e.x >= br else 0) for e in self.edges], dtype=float)
        soft = [i for i, (a, b, v, eq, tag) in enumerate(cons)
                if tag is not None and not eq and v > x0[b.k] - x0[a.k]]
        def wt(tag):
            if isinstance(tag, tuple) and tag[0] == 'cond':
                return 300.0 if tag[1].startswith('area') else 200.0
            return 1000.0
        weight = np.array([wt(cons[i][4]) for i in soft])
        m = len(soft)
        softcol = {i: 2 * n + j for j, i in enumerate(soft)}
        rows, cols, vals, rhs = [], [], [], []
        eq_rows, eq_cols, eq_vals, eq_rhs = [], [], [], []
        r = q = 0
        for i, (a, b, v, eq, tag) in enumerate(cons):
            if eq:
                eq_rows += [q, q]
                eq_cols += [b.k, a.k]
                eq_vals += [1, -1]
                eq_rhs.append(v)
                q += 1
            else:
                # x_a - x_b (- s) <= -v
                rows += [r, r]
                cols += [a.k, b.k]
                vals += [1, -1]
                if i in softcol:
                    rows.append(r)
                    cols.append(softcol[i])
                    vals.append(-1)
                rhs.append(-v)
                r += 1
        # |x - x0| <= t : x - t <= x0 ; -x - t <= -x0
        for e in self.edges:
            rows += [r, r]
            cols += [e.k, n + e.k]
            vals += [1, -1]
            rhs.append(x0[e.k])
            r += 1
            rows += [r, r]
            cols += [e.k, n + e.k]
            vals += [-1, -1]
            rhs.append(-x0[e.k])
            r += 1
        nv = 2 * n + m
        A = coo_matrix((vals, (rows, cols)), shape=(r, nv)).tocsr()
        Aeq = coo_matrix((eq_vals, (eq_rows, eq_cols)), shape=(q, nv)).tocsr() if q else None
        c = np.concatenate([np.zeros(n), np.ones(n), weight])
        bounds = [(lo[k], hi[k]) for k in range(n)] + [(0, None)] * (n + m)
        res = linprog(c, A_ub=A, b_ub=np.array(rhs, dtype=float), A_eq=Aeq,
                      b_eq=np.array(eq_rhs, dtype=float) if q else None, bounds=bounds, method='highs')
        if res.status != 0:
            self.residual = [('hard constraints infeasible', None, None, 0)]
            return None, cons
        xs = np.round(res.x[:n]).astype(int)
        self.xs = xs
        self.residual = []
        self.cond_residual = []
        for i in soft:
            a, b, v, eq, tag = cons[i]
            short = v - (xs[b.k] - xs[a.k])
            if short > 0:
                if isinstance(tag, tuple) and tag[0] == 'cond':
                    self.cond_residual.append((tag, a, b, short))
                else:
                    self.residual.append((tag, a, b, short))
        return xs, cons

    def apply(self, xs):
        """New Cell with the solved edge positions."""
        newx = {}
        for e in self.edges:
            c = e.contour
            for i in e.pidx:
                newx[(id(c), i)] = int(xs[e.k])
        layers = {}
        by_poly = {}
        for c in self.contours:
            pts = [db.Point(newx.get((id(c), i), p.x), p.y) for i, p in enumerate(c.pts)]
            by_poly.setdefault((c.layer, c.poly), []).append((c.hole, pts))
        for (lay, n), parts in by_poly.items():
            hull = [p for h, p in parts if not h][0]
            poly = db.Polygon(hull)
            for h, p in parts:
                if h:
                    poly.insert_hole(p)
            layers.setdefault(lay, db.Region()).insert(poly)
        # texts: interpolate between the nearest edges left / right at the text y
        texts = []
        for lay, t in self.cell.texts:
            x, y = t.x, t.y
            # the shape the label is on (pin layer l/d -> drawing l/1, plain view
            # labels have datatype + 1000): interpolate between its own edges
            base = (lay[0], 1)
            cand = self.edges
            for (pl, n), poly in self.polys.items():
                if pl == base and poly.inside(db.Point(x, y)):
                    cand = [e for e in self.edges if e.layer == pl and e.poly == n]
                    break
            left = max((e for e in cand if e.y1 <= y <= e.y2 and e.x <= x), key=lambda e: e.x, default=None)
            right = min((e for e in cand if e.y1 <= y <= e.y2 and e.x >= x), key=lambda e: e.x, default=None)
            if left is not None and right is not None and right.x > left.x:
                nx = xs[left.k] + (x - left.x) * (xs[right.k] - xs[left.k]) / (right.x - left.x)
            elif left is not None:
                nx = x + xs[left.k] - left.x
            elif right is not None:
                nx = x + xs[right.k] - right.x
            else:
                nx = x
            nt = db.Text(t)
            nt.x = int(round(nx))
            texts.append((lay, nt))
        bnd = db.Box(self.bnd.left, self.bnd.bottom, self.width, self.bnd.top)
        return Cell(layers, texts, bnd)


def check_topology(old, new):
    """Same number of polygons per layer and every polygon still valid."""
    for lay, r in old.layers.items():
        nr = new.layers.get(lay, db.Region())
        if r.count() != nr.merged().count():
            return f'{lay[0]}/{lay[1]}: {r.count()} -> {nr.merged().count()} polygons'
        if any(not p.is_rectilinear() for p in nr.each()):
            return f'{lay[0]}/{lay[1]}: polygon broken'
    return None


def describe(residual, limit=6):
    out = []
    for tag, a, b, short in residual[:limit]:
        if a is None:
            out.append(str(tag))
            continue
        if isinstance(tag, tuple) and tag[0] == 'cond':
            t = tag[1]
        elif isinstance(tag, tuple) and tag[1][0] == 'area':
            t = f'area {tag[1][1][0]}/{tag[1][1][1]}'
        elif isinstance(tag, tuple):
            t = f'{tag[1][1][0]}/{tag[1][1][1]} enc by {tag[1][0][0]}/{tag[1][0][1]}'
        else:
            t = tag
        out.append(f'{t} short {short} at {a.layer[0]}/{a.layer[1]}@{a.x}..{b.layer[0]}/{b.layer[1]}@{b.x}')
    return '; '.join(out) + (f' (+{len(residual) - limit})' if len(residual) > limit else '')


def make_hints(p):
    """x hints from the y pass residual (transposed): M1 / M2 / PO shapes whose
    horizontal edges are too close vertically -> their facing ends apart in x."""
    out = []
    for tag, a, b, short in p.residual:
        if not (isinstance(tag, str) and tag.startswith('space')) or a.layer != b.layer:
            continue
        lay = a.layer
        gap = abs(int(p.xs[b.k]) - int(p.xs[a.k]))
        sp = gap + short if 'marker' in tag else um(SPACE.get((lay, lay), 0))
        if not sp or gap >= sp:
            continue
        d = int(math.ceil(math.sqrt(sp * sp - gap * gap)))
        ya, yb = int(p.xs[a.k]), int(p.xs[b.k])
        if (a.y1 + a.y2) <= (b.y1 + b.y2):
            out.append((lay, a.poly, (a.y2, ya), b.poly, (b.y1, yb), d))
        else:
            out.append((lay, b.poly, (b.y2, yb), a.poly, (a.y1, ya), d))
    return out


def run_pass(cur, modes, axis, width, mode_rounds=6, hints=(), fixes=()):
    """One pass with mode switching; returns (new Cell, residual, mode switches, pass)."""
    n_switch = 0
    for _ in range(mode_rounds):
        if axis == 'x':
            p = Pass(cur, modes, 'x', width, hints=hints, fixes=fixes)
        else:
            p = Pass(cur.transposed(), modes, 'y', None, frozen=FROZEN_Y, freeze=rail_edge, fixes=fixes)
        xs, _ = p.solve()
        if xs is None:
            return None, p.residual, n_switch, p
        switched = False
        for tag, a, b, short in p.residual:
            if isinstance(tag, tuple) and tag[0] == 'mode' and modes[tag[1]].relax(axis):
                switched = True
        if not switched or not p.residual:
            break
        n_switch += 1
    p.update_fixes(xs)
    new = p.apply(xs)
    return (new if axis == 'x' else new.transposed()), p.residual, n_switch, p


def legalize(cell, site=200, max_grow=3, passes=6, fixes=()):
    """Returns (new Cell or None, grown sites, message). fixes: [Fix] from
    the DRC markers of an earlier result (cell is then that result)."""
    w0 = cell.bnd.right
    best = None
    first = ''
    for grow in range(max_grow + 1):
        modes = choose_modes(cell)
        cur = cell
        msg = ''
        hints = []
        fx = [f.copy() for f in fixes]
        for it in range(passes):
            cur, res_x, _, _ = run_pass(cur, modes, 'x', w0 + grow * site, hints=hints, fixes=fx)
            if cur is None:
                msg = 'x: ' + describe(res_x)
                break
            cur, res_y, sw_y, py = run_pass(cur, modes, 'y', None, fixes=fx)
            if cur is None:
                msg = 'y: ' + describe(res_y)
                break
            new_hints = make_hints(py)
            hints = hints + new_hints
            if sw_y and not res_y:
                res_x = [('mode switched in y, x again', None, None, 0)]
            bad = check_topology(cell, cur)
            if bad:
                msg = f'topology changed ({bad})'
                cur = None
                break
            small = area_short(cur, modes)
            if small:
                res_y = res_y + [(f'area {l[0]}/{l[1]} short {d} nm2', None, None, 0) for l, d in small[:4]]
            if not res_x and not res_y:
                break
            msg = ('x: ' + describe(res_x) + ' ' if res_x else '') + ('y: ' + describe(res_y) if res_y else '')
            # the next pass starts from the corrected cell (modes may have changed)
        if cur is not None and not res_x and not res_y:
            return cur, grow, 'ok' if grow == 0 else f'ok (original width: {first})'
        if grow == 0:
            first = msg
        best = msg
    return None, None, best


def area_short(cell, modes):
    """[(layer, missing area)] of the shapes with an area requirement."""
    out = []
    for lay, amin in AREA.items():
        a2 = um(amin) * um(1)
        if lay not in cell.layers:
            continue
        for n, p in enumerate(cell.layers[lay].each()):
            if ('area', lay, n) in modes and p.area() < a2:
                out.append((lay, a2 - p.area()))
    return out


def rail_edge(p, e):
    """y pass (transposed): the M1 rail edges stay (within RAIL of the cell bottom / top)."""
    return e.layer == M1 and (e.x <= p.bnd.left + RAIL or e.x >= p.bnd.right - RAIL)


def diagnose(p, cons):
    """Bellman-Ford on the constraint graph (longest paths from a source fixing
    the bounds); returns the edges of a positive cycle, i.e. conflicting
    constraints, as text."""
    n = len(p.edges)
    S = n
    bl, br = p.bnd.left, p.bnd.right
    mm = um(MAXMOVE)
    arcs = []      # (u, v, w, label): x_v >= x_u + w
    for e in p.edges:
        if e.layer in p.frozen or e.x <= bl or (p.axis == 'y' and e.x >= br) or p.freeze(p, e):
            v = e.x if e.x < br or p.axis == 'y' else e.x + p.grow
            lo = hi = v
        elif e.x >= br:
            lo = hi = e.x + p.grow
        else:
            lo, hi = e.x - mm, e.x + mm + p.grow
        arcs.append((S, e.k, lo, f'bound lo {lo}'))
        arcs.append((e.k, S, -hi, f'bound hi {hi}'))
    for a, b, v, eq in cons:
        arcs.append((a.k, b.k, v, 'eq' if eq else 'ge'))
        if eq:
            arcs.append((b.k, a.k, -v, 'eq'))
    dist = [-10 ** 12] * (n + 1)
    pred = [None] * (n + 1)
    dist[S] = 0
    last = None
    for _ in range(n + 1):
        last = None
        for i, (u, v, w, _) in enumerate(arcs):
            if dist[u] > -10 ** 12 and dist[u] + w > dist[v]:
                dist[v] = dist[u] + w
                pred[v] = i
                last = v
        if last is None:
            return 'no positive cycle found'
    v = last
    for _ in range(n + 1):
        v = arcs[pred[v]][0]
    cyc, u = [], v
    while True:
        i = pred[u]
        cyc.append(arcs[i])
        u = arcs[i][0]
        if u == v:
            break
    def name(k):
        if k == S:
            return 'SRC'
        e = p.edges[k]
        return f'{e.layer[0]}/{e.layer[1]}#{e.poly}{e.side}@{e.x}[{e.y1},{e.y2}]'
    return '\n'.join(f'  {name(u)} -> {name(v)} >= {w} ({lab})' for u, v, w, lab in reversed(cyc))
