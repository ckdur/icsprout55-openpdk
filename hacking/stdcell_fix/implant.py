#!/usr/bin/env python3
"""NP / PP boundary of a 7-track cell as a step line, solved per column.

In the 7-track cells NP (bottom, NMOS) and PP (top, PMOS) meet along one
boundary y = b(x) between the N+ and P+ diffusion. legalize.py keeps the
implants frozen in y; the rules on that boundary often cannot all hold at
the vendor height (a poly end of one type, the implant extension beyond the
gate of the other type and the facing poly end share one column). Here the
boundary inside the cell is chosen anew as a piecewise constant function on a
5 nm column grid (dynamic programming), every column constrained by the
Calibre rules (values from the runset):

  NP_EN_2 / PP_S_2   b >= N+ AA top + 0.12 (euclidean at the AA corners)
  PP_EN_2 / NP_S_2   b <= P+ AA bottom - 0.12
  NP_EX_1 (SNP_68)   b >= AA top + 0.16 within 0.2 of an NMOS gate end on the
                     AA edge (only where the AA edge faces the boundary)
  PP_EX_1            b <= AA bottom - 0.16 near PMOS gate ends
  NP_EN_3 / PP_EN_3  a field poly piece (PO NOT AA) touching both implants
                     (PO_CUT, touching counts) is exempt as a whole: one that
                     crosses the vendor boundary keeps crossing there (lo <= b
                     <= hi); any other is per column enclosed by 0.15
                     (euclidean) on either side or crossing
  (poly end growth)  a piece that still violates may have its end grown
                     until it touches the boundary (then PO_CUT), where the
                     poly spacing 0.12 to other poly, 0.05 to AA and 0.055
                     to contacts allow; kept if the solution gets better
  NP/PP_W_1, _S_1    every step of the boundary at least 0.18 wide (0.18 run
                     length; the runs at the cell sides are kept at the vendor
                     height for 0.09, so the abutment contract holds)

NP_S_5 / PP_S_5 (implant to the other type's gate 0.3) and the source /
drain part of SNP_68 only see vertical implant edges within the AA height,
which the AA bounds keep the boundary out of.

Cost: per column, a violated constraint (W_EXIST; the AA / gate bounds that
hold at the vendor height are hard) and its depth, then the movement from
the vendor boundary, then the number of steps. Columns: the 5 nm grid plus
the x of the vendor boundary steps; only changed columns are rewritten. A cell whose implants are not
one NP-below / PP-above interface in the boundary band is left alone.

  solve(layers, bnd) -> (new layers or None, violation before, after)
Usage: python3 implant.py <in.gds> <out.gds> [cell,cell...]   (prints the result)
"""

import bisect
import sys

import numpy as np
import klayout.db as db

AA, PO, CT, NP, PP = (2, 1), (41, 1), (72, 1), (52, 1), (53, 1)
STEP = 5             # dbu, column pitch and boundary grid
RUN = 180            # NP_W_1 / PP_W_1 / NP_S_1 / PP_S_1
SIDE = 90            # vendor height kept at the cell sides
ENC_AA, ENC_GATE, ENC_PO = 120, 160, 150
GATE_EXT = 200       # SNP_68 ENC_EXTENSION
ENC_VT = 150         # Vt layer (= NP / PP) from an AA edge with a gate end
CROSS = 0            # a poly piece crosses if lo <= b <= hi (touching interacts)
W_VIOL, W_MOVE, W_STEP = 1000.0, 1.0 / 1000, 20.0
W_EXIST, W_HARD = 2e5, 1e9   # per violated constraint and dbu of column width
EXT_MAX = 300        # poly end growth to the boundary: at most, and the spacing
S_PO, S_AA, S_CT = 120, 50, 55   # kept to other poly (PO_S_1), AA, contacts (CT_S_4)
DIRTY = 100          # modelled violation of a column with NP / PP overlap or gap


def _clip_cols(region, cuts, ylo, yhi):
    """Per column (cuts[j] .. cuts[j + 1]) the list of (lo, hi) y intervals of
    region, sampled at the column centre."""
    out = []
    for x1, x2 in zip(cuts, cuts[1:]):
        xm = (x1 + x2) // 2
        r = region & db.Region(db.Box(xm, ylo, xm + 1, yhi))
        out.append(sorted((p.bbox().bottom, p.bbox().top) for p in r.merged().each()))
    return out


def _profile(layers, bnd):
    """(cuts, b0, dirty, ylo, yhi) of the NP / PP interface, or None if the
    implants are not a single NP-below / PP-above interface in the band.
    Columns: the STEP grid plus the x of the vendor boundary steps (so the
    columns that stay keep their exact geometry). dirty: columns where NP and
    PP overlap (PP_R_1) or leave a gap; b0 is then the middle and the column
    is always rewritten."""
    np_, pp = layers.get(NP), layers.get(PP)
    if np_ is None or pp is None:
        return None
    inner = db.Region(db.Box(bnd.left, bnd.bottom + 100, bnd.right, bnd.top - 100))
    coin = (np_.edges() & pp.edges()) & inner
    ys = [e.p1.y for e in coin.each() if e.dy() == 0]
    if not ys:
        return None
    ylo, yhi = min(ys) - 250, max(ys) + 250
    band = db.Region(db.Box(bnd.left, ylo, bnd.right, yhi))
    cuts = set(range(bnd.left, bnd.right, STEP)) | {bnd.right}
    for r in (np_, pp):
        for e in (r & band).edges().each():
            if e.dx() == 0 and bnd.left < e.p1.x < bnd.right:
                cuts.add(e.p1.x)
    cuts = sorted(cuts)
    b0, dirty = [], []
    for iv_n, iv_p in zip(_clip_cols(np_ & band, cuts, ylo, yhi), _clip_cols(pp & band, cuts, ylo, yhi)):
        if len(iv_n) != 1 or len(iv_p) != 1 or iv_n[0][0] != ylo or iv_p[0][1] != yhi:
            return None
        lo, hi = iv_n[0][1], iv_p[0][0]
        dirty.append(lo != hi)
        b0.append(lo if lo == hi else int(round((lo + hi) / 2 / STEP)) * STEP)
    return cuts, np.array(b0), np.array(dirty), ylo, yhi


def _room(layers, piece, x1, x2, y, down):
    """How far (dbu) the end of a poly piece at y over [x1, x2] can grow
    (down or up) keeping the poly spacing to other poly, off AA and off
    contacts."""
    po, aa, ct = layers[PO], layers.get(AA, db.Region()), layers.get(CT, db.Region())
    room = EXT_MAX
    for reg, sp in ((po - db.Region(piece), S_PO), (aa, S_AA), (ct, S_CT)):
        win = db.Box(x1 - sp, y - EXT_MAX - sp, x2 + sp, y) if down else \
            db.Box(x1 - sp, y, x2 + sp, y + EXT_MAX + sp)
        hit = (reg & db.Region(win)).bbox()
        if not hit.empty():
            room = min(room, (y - hit.top if down else hit.bottom - y) - sp)
    return max(0, room // STEP * STEP)


def _constraints(layers, cuts, b0, ylo, yhi):
    """Per column lists of (kind, a, hard, piece): 'lo' b >= a, 'hi' b <= a,
    'cross' lo <= b <= hi, 'po' (lo, hi, c) the poly piece choice; returns
    (cons, frozen mask, pieces). The AA / gate bounds the vendor boundary
    meets are hard. pieces: the poly pieces that do not cross the vendor
    boundary, with the room to grow their end to it."""
    n = len(cuts) - 1
    cons = [[] for _ in range(n)]
    frozen = np.zeros(n, bool)
    aa = layers.get(AA, db.Region())
    po = layers.get(PO, db.Region())
    np_, pp = layers[NP], layers[PP]
    near = db.Region(db.Box(cuts[0] - 1000, ylo - 400, cuts[-1] + 1000, yhi + 400))

    def cols(x1, x2):
        """Columns overlapping [x1, x2)."""
        return range(max(0, bisect.bisect_right(cuts, x1) - 1), min(n, bisect.bisect_left(cuts, x2)))

    def add_zone(x1, x2, dist, fn):
        """fn(column, c) for the columns within dist of [x1, x2] (c: the
        remaining euclidean distance beyond the ends, dist inside)."""
        for j in cols(x1 - dist, x2 + dist):
            # the column point nearest to the shape (a step can sit at either end)
            dx = max(0, x1 - cuts[j + 1], cuts[j] - x2)
            if dx >= dist:
                continue
            fn(j, int(np.ceil(np.sqrt(dist * dist - dx * dx))) if dx > 0 else dist)

    # AA: N+ (below the boundary) / P+ (above), straddling: frozen
    for p in (aa & near).merged().each():
        b = p.bbox()
        r = db.Region(p)
        in_n, in_p = not (r & np_).is_empty(), not (r & pp).is_empty()
        if in_n and in_p:
            for j in cols(b.left - ENC_AA, b.right + ENC_AA):
                frozen[j] = True
            continue
        if (in_n and b.top < ylo - ENC_GATE) or (not in_n and b.bottom > yhi + ENC_GATE):
            continue
        gates = [g.bbox() for g in (r & po).merged().each()]
        # the AA edges facing the boundary: top edges of N+ AA (inside below),
        # bottom edges of P+ AA; euclidean from each edge
        for e in p.each_edge():
            if e.dy() != 0:
                continue
            ey, ex1, ex2 = e.p1.y, min(e.p1.x, e.p2.x), max(e.p1.x, e.p2.x)
            if in_n != p.inside(db.Point((ex1 + ex2) // 2, ey - 1)):
                continue
            kind, sgn = ('lo', 1) if in_n else ('hi', -1)
            add_zone(ex1, ex2, ENC_AA,
                     lambda j, c, t=ey, k=kind, s=sgn: cons[j].append((k, t + s * c, None, None)))
            # SNP_68: gate ends on this edge, 0.16 within 0.2 of the gate
            on_edge = [gb for gb in gates
                       if (gb.top if in_n else gb.bottom) == ey and gb.right > ex1 and gb.left < ex2]
            for gb in on_edge:
                for j in cols(max(ex1, gb.left - GATE_EXT), min(ex2, gb.right + GATE_EXT)):
                    cons[j].append((kind, ey + sgn * ENC_GATE, None, None))
            # the Vt layers of H7CH / H7CL are copies of NP / PP (derive_vt.py):
            # NVT3/PVT3/NVT1/PVT1 _EX_2 / _S_3 want 0.15 from an AA edge a gate
            # ends on, along all of it (projection)
            if on_edge:
                for j in cols(ex1, ex2):
                    cons[j].append((kind, ey + sgn * ENC_VT, None, None))
    # field poly pieces near the band
    pieces = []
    for p in ((po - aa) & near).merged().each():
        b = p.bbox()
        if b.top < ylo - ENC_PO or b.bottom > yhi + ENC_PO:
            continue
        r = db.Region(p)
        ext = {}       # per column y extent of the piece
        for j in cols(b.left, b.right):
            iv = (r & db.Region(db.Box(cuts[j], b.bottom, cuts[j + 1], b.top))).bbox()
            if not iv.empty():
                ext[j] = (iv.bottom, iv.top)
        if not ext:
            continue
        js = sorted(ext)
        # crossing (or touching) the vendor boundary: PO_CUT, exempt as a
        # whole; it only has to keep crossing there
        crossing = [j for j in js if ext[j][0] <= b0[j] <= ext[j][1]]
        if crossing:
            for j in crossing:
                cons[j].append(('cross', ext[j], None, None))
            continue
        pid = len(pieces)

        def piece(j, c, ext=ext, js=js, pid=pid):
            k = min(js, key=lambda i: abs(i - j))
            lo, hi = ext[k]
            cons[j].append(('po', (lo, hi, c), None, pid))
        add_zone(b.left, b.right, ENC_PO, piece)
        # the end facing the boundary (bottom of a piece above it, top of one
        # below) and the room to grow it until it touches the boundary
        above = b.bottom >= max(b0[j] for j in js)
        y = b.bottom if above else b.top
        xe = [x for e in p.each_edge() if e.dy() == 0 and e.p1.y == y for x in (e.p1.x, e.p2.x)]
        x1, x2 = min(xe), max(xe)
        pieces.append(dict(poly=p, down=above, y=y, x1=x1, x2=x2, cols=list(cols(x1, x2)),
                           room=_room(layers, p, x1, x2, y, above)))
    # cell sides: vendor height
    for j in range(n):
        if cuts[j + 1] <= cuts[0] + SIDE or cuts[j] >= cuts[-1] - SIDE:
            frozen[j] = True
    # hard: the AA / gate bounds that hold at the vendor height
    for j, cs in enumerate(cons):
        cons[j] = [(k, a, k in ('lo', 'hi') and _viol(k, a, np.array([b0[j]]))[0] == 0, pid)
                   for k, a, _, pid in cs]
    return cons, frozen, pieces


def _viol(kind, a, v):
    """Distance (dbu) of boundary heights v (array) from the allowed set."""
    if kind == 'lo':
        return np.maximum(0, a - v)
    if kind == 'hi':
        return np.maximum(0, v - a)
    if kind == 'cross':
        lo, hi = a
        return np.maximum(0, lo - v) + np.maximum(0, v - hi)
    lo, hi, c = a
    d_below = np.maximum(0, v - (lo - c))          # piece above the boundary
    d_above = np.maximum(0, (hi + c) - v)          # piece below the boundary
    # touching counts (INTERACT): lo <= b <= hi
    d_cross = np.maximum(0, (lo + CROSS) - v) + np.maximum(0, v - (hi - CROSS))
    return np.minimum(np.minimum(d_below, d_above), d_cross)


def _candidates(cons, b0):
    vals = set(int(v) for v in b0)
    for cs in cons:
        for kind, a, *_ in cs:
            if kind == 'lo':
                vals.add(int(np.ceil(a / STEP)) * STEP)
            elif kind == 'hi':
                vals.add(int(np.floor(a / STEP)) * STEP)
            elif kind == 'cross':
                lo, hi = a
                vals.add(int(np.ceil(lo / STEP)) * STEP)
                vals.add(int(np.floor(hi / STEP)) * STEP)
            else:
                lo, hi, c = a
                if c == ENC_PO:
                    vals.add(int(np.floor((lo - c) / STEP)) * STEP)
                    vals.add(int(np.ceil((hi + c) / STEP)) * STEP)
                    vals.add(int(np.ceil(lo / STEP)) * STEP)
                    vals.add(int(np.floor(hi / STEP)) * STEP)
    return np.array(sorted(vals))


def _cost_matrix(cons, frozen, cuts, b0, V):
    """cost[j, v] and the modelled violation viol[j, v] (dbu, per column)."""
    n = len(b0)
    w = np.diff(np.array(cuts, dtype=float))
    viol = np.zeros((n, len(V)))
    pen = np.zeros((n, len(V)))
    for j, cs in enumerate(cons):
        for kind, a, hard, _ in cs:
            d = _viol(kind, a, V)
            viol[j] += d
            pen[j] += np.where(d > 0, W_HARD if hard else W_EXIST, 0)
    move = np.abs(V[None, :] - b0[:, None])
    cost = (viol * W_VIOL + pen + move * W_MOVE) * w[:, None]
    cost[frozen] = np.where(V[None, :] == b0[frozen][:, None], 0, 1e15)
    return cost, viol


def _dp(cost, cuts):
    """Piecewise constant choice per column minimising cost; interior runs at
    least RUN long (the first and last runs are not restricted). Returns the
    value index per column."""
    n, m = cost.shape
    cuts = np.array(cuts)
    P = np.vstack([np.zeros(m), np.cumsum(cost, axis=0)])     # P[j] = sum cost[0:j]
    f = np.full((n + 1, m), np.inf)
    f[0] = 0
    back = np.full((n + 1, m), -1, dtype=np.int64)     # -1: extended, else start * m + previous

    def best_excl(row):
        order = np.argsort(row)
        b1, b2 = order[0], order[1] if m > 1 else order[0]
        res, arg = np.full(m, row[b1]), np.full(m, b1)
        res[b1], arg[b1] = row[b2], b2
        return res, arg
    for j in range(1, n + 1):
        f[j] = f[j - 1] + cost[j - 1]
        # a new run starting at i (>= 1) ends here with the minimum length
        i = int(np.searchsorted(cuts, cuts[j] - RUN, side='right')) - 1
        if i >= 1 and (j == n or cuts[j] - cuts[i] >= RUN):
            be, arg = best_excl(f[i])
            new = be + (P[j] - P[i]) + W_STEP
            better = new < f[j]
            f[j] = np.where(better, new, f[j])
            back[j] = np.where(better, i * m + arg, back[j])
    # the last run may be short
    final = f[n].copy()
    fin_back = np.full(m, -1, dtype=np.int64)
    for i in range(1, n):
        if cuts[n] - cuts[i] >= RUN:
            continue
        be, arg = best_excl(f[i])
        new = be + (P[n] - P[i]) + W_STEP
        better = new < final
        final = np.where(better, new, final)
        fin_back = np.where(better, i * m + arg, fin_back)
    v = int(np.argmin(final))
    out = np.zeros(n, dtype=np.int64)
    j = n
    if fin_back[v] >= 0:
        i, u = divmod(int(fin_back[v]), m)
        out[i:n] = v
        j, v = i, u
    while j > 0:
        bk = back[j][v]
        if bk < 0:
            out[j - 1] = v
            j -= 1
        else:
            i, u = divmod(int(bk), m)
            out[i:j] = v
            j, v = i, u
    return out


def _total(cons, b):
    return sum(_viol(k, a, np.array([b[j]]))[0] for j, cs in enumerate(cons) for k, a, *_ in cs)


def _run(cons, frozen, cuts, b0):
    V = _candidates(cons, b0)
    V = V[(V > _run.ylo) & (V < _run.yhi)]
    cost, viol = _cost_matrix(cons, frozen, cuts, b0, V)
    sel = _dp(cost, cuts)
    return V[sel], float(cost[np.arange(len(sel)), sel].sum())


def solve(layers, bnd):
    """New layers (NP / PP, and PO where a poly end grows to the boundary)
    or None; modelled violation before and after (dbu summed over the
    columns)."""
    prof = _profile(layers, bnd)
    if prof is None:
        return None, None, None
    cuts, b0, dirty, ylo, yhi = prof
    cons, frozen, pieces = _constraints(layers, cuts, b0, ylo, yhi)
    dirty = dirty & ~frozen
    v0 = _total(cons, b0) + DIRTY * int(dirty.sum())
    if v0 == 0:
        return None, 0, 0
    _run.ylo, _run.yhi = ylo, yhi
    b, c = _run(cons, frozen, cuts, b0)
    v1 = _total(cons, b)
    # pieces still violated: their end grown until it touches the boundary
    # (PO_CUT), if the solution with that gets better
    grown = []
    for pid, pc in enumerate(pieces):
        if not pc['room'] or not pc['cols']:
            continue
        mine = sum(_viol(k, a, np.array([b[j]]))[0] for j, cs in enumerate(cons) for k, a, _, q in cs if q == pid)
        if not mine:
            continue
        y, r = pc['y'], pc['room']
        iv = (y - r, y) if pc['down'] else (y, y + r)
        trial = [[e for e in cs if e[3] != pid] for cs in cons]
        for j in pc['cols']:
            trial[j].append(('cross', iv, False, pid))
        b2, c2 = _run(trial, frozen, cuts, b0)
        v2 = _total(trial, b2)
        if v2 < v1:
            cons, b, v1 = trial, b2, v2
            grown.append(pid)
    if v1 >= v0:
        return None, v0, v1
    # new NP / PP inside the band, only in the columns that change (the
    # others keep their exact geometry)
    below, above, band = db.Region(), db.Region(), db.Region()
    for j in range(len(b)):
        if b[j] != b0[j] or dirty[j]:
            x1, x2 = cuts[j], cuts[j + 1]
            below.insert(db.Box(x1, ylo, x2, int(b[j])))
            above.insert(db.Box(x1, int(b[j]), x2, yhi))
            band.insert(db.Box(x1, ylo, x2, yhi))
    out = dict(layers)
    out[NP] = ((layers[NP] - band) + below).merged()
    out[PP] = ((layers[PP] - band) + above).merged()
    ext = db.Region()
    for pid in grown:
        pc = pieces[pid]
        y = pc['y']
        if pc['down']:
            t = max(int(b[j]) for j in pc['cols'])
            if t < y:
                ext.insert(db.Box(pc['x1'], t, pc['x2'], y))
        else:
            t = min(int(b[j]) for j in pc['cols'])
            if t > y:
                ext.insert(db.Box(pc['x1'], y, pc['x2'], t))
    if not ext.is_empty():
        out[PO] = (layers[PO] + ext).merged()
    return out, v0, v1


def main():
    src, dst = sys.argv[1:3]
    lay = db.Layout()
    lay.read(src)
    names = sys.argv[3].split(',') if len(sys.argv) > 3 else [c.name for c in lay.top_cells()]
    bl = lay.find_layer(351, 12)
    for name in names:
        c = lay.cell(name)
        layers = {}
        for k in (AA, PO, CT, NP, PP):
            li = lay.find_layer(*k)
            if li is not None:
                layers[k] = db.Region(c.begin_shapes_rec(li)).merged()
        bnd = db.Region(c.begin_shapes_rec(bl)).bbox()
        new, v0, v1 = solve(layers, bnd)
        grew = new is not None and new[PO] is not layers[PO]
        print(f'{name}: violation {v0} -> {v1}' + ('' if new else ' (unchanged)') + (' poly grown' if grew else ''))
        if new:
            for k in (NP, PP, PO):
                if new[k] is layers[k]:
                    continue
                li = lay.find_layer(*k)
                c.shapes(li).clear()
                c.shapes(li).insert(new[k])
    lay.write(dst)


if __name__ == '__main__':
    main()
