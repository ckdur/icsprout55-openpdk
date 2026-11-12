#!/usr/bin/env python3
"""
Generate critical-shape test layouts from an SVRF deck.

For each rule check whose output is (after unwrapping NOT INSIDE / NOT /
AND filters) a dimensional check INT/EXT/ENC or AREA with a "<" constraint,
two tiles are generated:
   pass : geometry exactly at the limit       -> rule must NOT trigger
   fail : geometry DELTA below the limit      -> rule must trigger
Derived layers are realised by drawing a "witness": a set of drawn shapes
on input layers that makes the derived layer contain the requested shape.

  gen_critical.py expanded.svrf out_dir

Writes out_dir/critical.json (mkgds spec) and out_dir/tiles.json
(rule -> list of [kind, x1, y1, x2, y2]).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import svrf_parse as P  # noqa: E402
from svrf2klayout import Gen  # noqa: E402

DELTA = 0.005


class NoWitness(Exception):
    pass


def box(x1, y1, x2, y2):
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def grow(b, d):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def center_sq(b, s):
    cx = (b[0] + b[2]) / 2
    cy = (b[1] + b[3]) / 2
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


class Witness:
    def __init__(self, gen, defines):
        self.g = gen
        self.defines = defines
        self.local = {}

    def specs(self, name):
        return self.g.layer_specs(name)

    def resolve(self, name):
        u = name.upper()
        if u in self.local:
            return self.local[u]
        if u in self.g.global_defs:
            return self.g.global_defs[u]
        return None

    def w(self, n, b, depth=0):
        """return list of (l, d, box) drawing so that n contains box b"""
        if depth > 40:
            raise NoWitness('depth')
        op = n.op
        if op == 'name':
            nm = n.kw['name']
            d = self.resolve(nm)
            if d is not None:
                return self.w(d, b, depth + 1)
            sp = self.specs(nm)
            if not sp:
                raise NoWitness('no input layer %s' % nm)
            l, dt = sp[0]
            return [(l, dt, b)]
        if op in ('copy', 'bracket'):
            return self.w(n.args[0], b, depth + 1)
        if op == 'nary':
            if n.kw['op_'] == 'OR':
                return self.w(n.args[0], b, depth + 1)
            if n.kw['op_'] == 'AND':
                r = []
                for a in n.args:
                    r += self.w(a, b, depth + 1)
                return r
            raise NoWitness('nary')
        if op == 'bool':
            o = n.kw['op_']
            if o == 'OR':
                return self.w(n.args[0], b, depth + 1)
            if o == 'AND':
                return self.w(n.args[0], b, depth + 1) + self.w(n.args[1], b, depth + 1)
            if o == 'NOT':
                return self.w(n.args[0], b, depth + 1)
            raise NoWitness('xor')
        if op == 'sel':
            k = n.kw['kind']
            neg = n.kw.get('neg')
            base = self.w(n.args[0], b, depth + 1)
            if neg:
                return base
            cons = n.kw.get('cons') or []
            cnt = 1
            for c, v in cons:
                if c in ('>', '>='):
                    cnt = int(v) + (1 if c == '>' else 0)
                if c == '==':
                    cnt = int(v)
            if cnt < 1:
                cnt = 1
            if k in ('interact', 'enclose'):
                r = list(base)
                s = min(b[2] - b[0], b[3] - b[1]) / (2 * cnt + 1)
                for i in range(cnt):
                    x1 = b[0] + s * (2 * i + 1)
                    sb = (x1, b[1] + s * 0.5, x1 + s * 0.8, b[1] + s * 1.3) if cnt > 1 else center_sq(b, s)
                    r += self.w(n.args[1], sb, depth + 1)
                return r
            if k == 'inside':
                return base + self.w(n.args[1], grow(b, 0.5), depth + 1)
            if k == 'outside':
                return base
            if k == 'touch':
                h = b[3] - b[1]
                return base + self.w(n.args[1], (b[2], b[1], b[2] + h, b[3]), depth + 1)
            if k == 'cut':
                return base + self.w(n.args[1], (b[0] - 0.2, b[1], (b[0] + b[2]) / 2, b[3]), depth + 1)
            raise NoWitness('sel %s' % k)
        if op == 'size':
            return self.w(n.args[0], b, depth + 1)
        if op in ('with_width', 'area', 'rectangle', 'enclose_rect', 'holes'):
            if op == 'holes':
                raise NoWitness('holes')
            return self.w(n.args[0], b, depth + 1)
        raise NoWitness(op)


def core_check(n):
    """unwrap filters around a check; returns the check node or None"""
    while True:
        if n.op == 'check' or n.op == 'area':
            return n
        if n.op == 'sel' and n.kw.get('neg'):
            n = n.args[0]
            continue
        if n.op == 'bool' and n.kw['op_'] in ('NOT', 'AND'):
            n = n.args[0]
            continue
        if n.op == 'esel' and n.kw.get('neg'):
            n = n.args[0]
            continue
        return None


def limit(cons):
    for op, v in cons:
        if op == '<':
            return v
    return None


class Tiles:
    def __init__(self):
        self.shapes = []
        self.tiles = {}
        self.x = 0.0
        self.y = 0.0
        self.rowh = 0.0
        self.maxw = 2000.0

    def place(self, rule, kind, shapes, size):
        # shapes are in local coords inside (0,0,size,size)
        if self.x + size > self.maxw:
            self.x = 0.0
            self.y += self.rowh + 2.0
            self.rowh = 0.0
        ox, oy = self.x, self.y
        for l, d, b in shapes:
            self.shapes.append([l, d, 'box', round(b[0] + ox, 3), round(b[1] + oy, 3),
                                round(b[2] + ox, 3), round(b[3] + oy, 3)])
        self.tiles.setdefault(rule, []).append([kind, ox, oy, ox + size, oy + size])
        self.x += size + 2.0
        self.rowh = max(self.rowh, size)


def gen_check_tiles(W, rule, chk, T):
    if chk.op == 'area':
        v = limit(chk.kw['cons'])
        if v is None:
            return False
        a = chk.args[0]
        for kind, area in (('pass', v), ('fail', v * 0.8)):
            w = 0.5 if area > 0.25 else math.sqrt(area)
            h = area / w
            h = math.ceil(h * 1000) / 1000.0 if kind == 'pass' else math.floor(h * 1000) / 1000.0
            sz = max(4.0, h * 3 + 2)
            b = (1.0, 1.0, 1.0 + w, 1.0 + h)
            T.place(rule, kind, W.w(a, b), sz)
        return True
    kind = chk.kw['kind']
    v = limit(chk.kw['cons'])
    if v is None or v <= 0 or v > 50:
        return False
    if chk.kw.get('abut') and any(op == '==' for op, x in chk.kw['abut']):
        return False
    if chk.kw.get('intersecting'):
        return False
    args = chk.args
    L = max(2.0, 3 * v)
    sz = max(6.0, 8 * v + 4)
    m = 1.0 + v  # margin
    for tk, d in (('pass', v), ('fail', round(v - DELTA, 4))):
        if d <= 0:
            continue
        shapes = []
        if kind == 'int' and len(args) == 1:
            b = (m, m, m + d, m + L)
            shapes = W.w(args[0], b)
        elif kind == 'ext' and len(args) == 1:
            w0 = max(v, 0.5)
            b1 = (m, m, m + w0, m + L)
            b2 = (m + w0 + d, m, m + 2 * w0 + d, m + L)
            shapes = W.w(args[0], b1) + W.w(args[0], b2)
        elif kind == 'ext':
            w0 = max(v, 0.5)
            b1 = (m, m, m + w0, m + L)
            b2 = (m + w0 + d, m, m + 2 * w0 + d, m + L)
            shapes = W.w(args[0], b1) + W.w(args[1], b2)
        elif kind == 'enc':
            # inner args[0] enclosed by outer args[1]; tight on the right side
            big = max(v, 0.5) * 3
            ob = (m, m, m + 2 * big + d, m + 2 * big + L)
            ib = (m + big, m + big, m + big + d * 0 + max(v, 0.2), m + big + L)
            ib = (ob[2] - d - max(v, 0.2), m + big, ob[2] - d, m + big + L)
            shapes = W.w(args[1], ob) + W.w(args[0], ib)
            sz = max(sz, ob[2] + m, ob[3] + m)
        elif kind == 'int':
            w0 = max(v, 0.5) * 2
            b1 = (m, m, m + w0, m + L)
            b2 = (m + w0 - d, m, m + 2 * w0 - d, m + L)
            shapes = W.w(args[0], b1) + W.w(args[1], b2)
        else:
            return False
        T.place(rule, tk, shapes, sz)
    return True


def main():
    svrf, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    deck = P.Deck(svrf)
    g = Gen(deck)
    defines = {}
    W = Witness(g, defines)
    T = Tiles()
    stats = {'rules': 0, 'covered': 0, 'skipped': {}}
    covered = []

    def visit(stmts, active=True):
        for s in stmts:
            if s[0] == 'define':
                defines[s[1].upper()] = s[2]
            elif s[0] == 'ifdef':
                _, nm, val, neg, body, other = s
                v = defines.get(nm.upper())
                cond = v is not None and (val is None or str(v).upper() == str(val).upper())
                if neg:
                    cond = not cond
                visit(body if cond else other, active)
            elif s[0] == 'rule':
                stats['rules'] += 1
                name, body = s[1], s[3]
                W.local = {}
                P.walk_stmts(body, lambda q, p: W.local.setdefault(q[1].upper(), q[2]) if q[0] == 'assign' else None)
                ok = False
                why = 'no simple check'
                outs = []
                P.walk_stmts(body, lambda q, p: outs.append(q[1]) if q[0] == 'out' else None)
                for e in outs:
                    chk = core_check(e)
                    if chk is None:
                        continue
                    try:
                        if gen_check_tiles(W, name, chk, T):
                            ok = True
                            break
                    except NoWitness as ex:
                        why = 'no witness: %s' % ex
                if ok:
                    stats['covered'] += 1
                    covered.append(name)
                else:
                    stats['skipped'][name] = why

    visit(deck.stmts)
    spec = {'top': 'CRIT', 'cells': {'CRIT': {'shapes': T.shapes}}}
    json.dump(spec, open(os.path.join(out, 'critical.json'), 'w'))
    json.dump(T.tiles, open(os.path.join(out, 'tiles.json'), 'w'), indent=0)
    json.dump(stats, open(os.path.join(out, 'stats.json'), 'w'), indent=1)
    print('rules: %d, with generated critical tiles: %d' % (stats['rules'], stats['covered']))


if __name__ == '__main__':
    main()
