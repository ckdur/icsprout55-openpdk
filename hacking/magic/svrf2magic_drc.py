#!/usr/bin/env python3
"""Translate the (TVF-expanded) Calibre SVRF DRC deck into Magic DRC rules.

Used by gen_magic_tech.py (translate()); run alone it prints the coverage report:
  svrf2magic_drc.py [--report out.txt]

Magic's rule language is much smaller than SVRF, so only part of the deck translates:

  * native rules (all variants): width / spacing / surround / area on layers that are a
    union of drawn layers, i.e. Magic type sets;
  * CIF rules (variant "full"): cifwidth / cifspacing / cifmaxwidth (zero-width = the error
    layer must be empty) on derived layers. Derived layers are templayers of the CIF style
    "drc", built with and / and-not / or / grow / shrink / bloat-all (INTERACT, INSIDE,
    OUTSIDE, ENCLOSE) / close (HOLES). Magic allows at most 255 CIF layers per style, so
    rules are taken cheapest first until that budget is used;
  * everything else (edge operations, RECTANGLE, WITH WIDTH, LENGTH, ANGLE, DENSITY, NET
    AREA RATIO, WITH TEXT, AREA selections, constrained INTERACT counts, CONNECTED spacing,
    PROJECTING / PARALLEL / ANGLED filters ...) is skipped and listed in the report.

Rule names and values are the Calibre ones. Exemption wrappers ("... NOT INSIDE NODRC")
around a check are dropped (Magic cannot exempt regions per rule), so a translated rule may
flag inside such regions where Calibre does not.
"""

import argparse
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'hacking', 'svrf2klayout'))
import svrf_parse as P  # noqa: E402

DRC_DECK = os.path.join(ROOT, 'hacking', 'svrf2klayout', 'ICsprout_CalDRC_expanded.svrf')
CIF_BUDGET = 250          # Magic: at most 255 CIF layers per style
UM = 1000.0               # DRC scalefactor 10 with lambda 10 nm: values in nm


class Unsupported(Exception):
    pass


class Empty(Exception):
    """the layer expression is always empty in Magic (uses a layer Magic does not have)"""


def nm(v):
    return int(round(v * UM))


# ------------------------------------------------------------------------------------------
# Deck flattening (#IFDEF evaluated with the deck's own #DEFINEs)
# ------------------------------------------------------------------------------------------

def flatten(stmts, env, out):
    for s in stmts:
        k = s[0]
        if k == 'define':
            env[s[1]] = s[2]
        elif k == 'ifdef':
            name, val, negated = s[1], s[2], s[3]
            hit = name in env and (val is None or env[name].upper() == str(val).upper())
            if negated:
                hit = not hit
            flatten(s[4] if hit else s[5], env, out)
        elif k == 'rule':
            body = []
            flatten(s[3], env, body)
            out.append(('rule', s[1], s[2], body, s[4]))
        else:
            out.append(s)
    return out


# ------------------------------------------------------------------------------------------
# Expressions
# ------------------------------------------------------------------------------------------

class Ctx:
    """CIF templayer allocation for one translation attempt; the layers get their final
    names (c<n>, shared between rules) when the rule is committed."""
    seq = 0

    def __init__(self, tr):
        Ctx.seq += 1
        self.id = Ctx.seq
        self.tr = tr
        self.new = []            # (name, lines) in definition order
        self.newkeys = {}

    def layer(self, key, lines):
        if key in self.newkeys:
            return self.newkeys[key]
        name = 't%d_%d' % (self.id, len(self.new))
        self.new.append((name, lines))
        self.newkeys[key] = name
        return name


class Translator:
    def __init__(self, deck_path, gds_types, planes):
        """gds_types: {(layer, datatype): magic type list}; planes: {type or alias: set of
        planes} (native width / spacing rules need all types on one plane)."""
        self.planes = planes
        self.deck = P.Deck(deck_path)
        env = {}
        self.stmts = flatten(self.deck.stmts, env, [])
        self.env = env
        # primary layers
        num2gds = collections.defaultdict(set)
        self.primary = {}
        for s in self.stmts:
            if s[0] == 'layermap' and s[2] == 'DATATYPE':
                num2gds[s[4]].add((s[1], s[3]))
        for s in self.stmts:
            if s[0] == 'layer':
                types, missing = [], []
                for n in s[2]:
                    for ld in num2gds.get(n, {(n, 0)}):
                        t = gds_types.get(ld)
                        (types.append(t) if t else missing.append(ld))
                self.primary[s[1].upper()] = (','.join(sorted(set(','.join(types).split(',')))) if types else None)
        self.defs = {}
        for s in self.stmts:
            if s[0] == 'assign':
                self.defs[s[1].upper()] = s[2]
        self.cif_layers = []     # (name, lines)
        self.cif_memo = {}
        self.native = []
        self.cif_rules = []
        self.report = []

    # -- type-set (native) evaluation: union of primary layers --------------------------
    def types_of(self, n, local, depth=0):
        if depth > 80:
            raise Unsupported('recursion')
        if n.op == 'name':
            nmu = n.kw['name'].upper()
            if nmu in local:
                return self.types_of(local[nmu], local, depth + 1)
            if nmu in self.primary:
                if self.primary[nmu] is None:
                    raise Empty(nmu)
                return set(self.primary[nmu].split(','))
            if nmu in self.defs:
                return self.types_of(self.defs[nmu], {}, depth + 1)
            raise Unsupported('undefined layer %s' % nmu)
        if n.op == 'copy' and len(n.args) == 1:
            return self.types_of(n.args[0], local, depth + 1)
        if (n.op == 'bool' and n.kw.get('op_') == 'OR') or (n.op == 'nary' and n.kw.get('op_') == 'OR') \
                or (n.op == 'copy' and len(n.args) > 1):
            out = set()
            for a in n.args:
                try:
                    out |= self.types_of(a, local, depth + 1)
                except Empty:
                    pass
            if not out:
                raise Empty('or')
            return out
        raise Unsupported('not a type set')

    # -- CIF evaluation --------------------------------------------------------------------
    def cif(self, n, local, ctx, depth=0):
        """Returns ('types', str) or ('layer', name)."""
        if depth > 80:
            raise Unsupported('recursion')
        try:
            return ('types', ','.join(sorted(self.types_of(n, local))))
        except Unsupported:
            pass
        op = n.op
        if op == 'name':
            nmu = n.kw['name'].upper()
            if nmu in local:
                return self.cif(local[nmu], local, ctx, depth + 1)
            if nmu in self.defs:
                return self.cif(self.defs[nmu], {}, ctx, depth + 1)
            raise Unsupported('undefined layer %s' % nmu)
        if op == 'copy':
            if len(n.args) == 1:
                return self.cif(n.args[0], local, ctx, depth + 1)
            return self.cif(P.Node('nary', n.args, op_='OR'), local, ctx, depth + 1)
        if op in ('bool', 'nary'):
            bop = n.kw.get('op_')
            if bop == 'OR':
                parts = []
                for a in n.args:
                    try:
                        parts.append(self.cif(a, local, ctx, depth + 1))
                    except Empty:
                        pass
                if not parts:
                    raise Empty('or')
                if len(parts) == 1:
                    return parts[0]
                lines = ['or %s' % p[1] for p in parts[1:]]
                return self._mk(ctx, parts[0][1], lines)
            if bop == 'AND':
                parts = [self.cif(a, local, ctx, depth + 1) for a in n.args]   # Empty propagates
                lines = ['and %s' % p[1] for p in parts[1:]]
                return self._mk(ctx, parts[0][1], lines)
            if bop == 'NOT':
                a = self.cif(n.args[0], local, ctx, depth + 1)
                lines = []
                for b in n.args[1:]:
                    try:
                        lines.append('and-not %s' % self.cif(b, local, ctx, depth + 1)[1])
                    except Empty:
                        pass
                if not lines:
                    return a
                return self._mk(ctx, a[1], lines)
            raise Unsupported('boolean %s' % bop)
        if op == 'size':
            if any(k in n.kw for k in ('inside_of', 'outside_of', 'step', 'truncate')):
                raise Unsupported('SIZE INSIDE OF / STEP / TRUNCATE')
            d = n.kw['d']
            if not isinstance(d, (int, float)):
                raise Unsupported('SIZE by expression')
            a = self.cif(n.args[0], local, ctx, depth + 1)
            g = nm(abs(d))
            mode = n.kw.get('mode')
            if mode == 'overunder':
                lines = ['grow %d' % g, 'shrink %d' % g]
            elif mode == 'underover':
                lines = ['shrink %d' % g, 'grow %d' % g]
            else:
                lines = ['grow %d' % g] if d > 0 else ['shrink %d' % g]
            return self._mk(ctx, a[1], lines)
        if op == 'holes':
            a = self.cif(n.args[0], local, ctx, depth + 1)
            return self._mk(ctx, a[1], ['close 1000000000000', 'and-not %s' % a[1]])
        if op == 'sel':
            if n.kw.get('cons'):
                raise Unsupported('selection with a count')
            if any(k in n.kw for k in ('singular', 'by_net', 'even', 'odd')):
                raise Unsupported('selection option')
            kind, neg = n.kw['kind'], n.kw.get('neg')
            a = self.cif(n.args[0], local, ctx, depth + 1)
            try:
                b = self.cif(n.args[1], local, ctx, depth + 1)
            except Empty:
                b = None
            if kind == 'interact':
                if b is None:
                    if neg:
                        return a
                    raise Empty('interact empty')
                hit = self._mk(ctx, None, ['bloat-all %s %s' % (b[1], a[1]), 'and %s' % a[1]])
                return self._mk(ctx, a[1], ['and-not %s' % hit[1]]) if neg else hit
            if kind in ('inside', 'outside'):
                if b is None:
                    if (kind == 'inside') == bool(neg):
                        return a
                    raise Empty('inside empty')
                part = self._mk(ctx, a[1], ['and-not %s' % b[1]] if kind == 'inside' else ['and %s' % b[1]])
                touched = self._mk(ctx, None, ['bloat-all %s %s' % (part[1], a[1]), 'and %s' % a[1]])
                return touched if neg else self._mk(ctx, a[1], ['and-not %s' % touched[1]])
            if kind == 'enclose':
                if b is None:
                    if neg:
                        return a
                    raise Empty('enclose empty')
                bout = self._mk(ctx, b[1], ['and-not %s' % a[1]])
                bcross = self._mk(ctx, None, ['bloat-all %s %s' % (bout[1], b[1]), 'and %s' % b[1]])
                binside = self._mk(ctx, b[1], ['and-not %s' % bcross[1]])
                hit = self._mk(ctx, None, ['bloat-all %s %s' % (binside[1], a[1]), 'and %s' % a[1]])
                return self._mk(ctx, a[1], ['and-not %s' % hit[1]]) if neg else hit
            raise Unsupported('selection %s' % kind)
        raise Unsupported(op if op != 'esel' else 'edge operation')

    def _mk(self, ctx, first, lines):
        head = 'templayer @ %s' % first if first else 'templayer @'
        key = (head, tuple(lines))
        name = ctx.layer(key, [head] + lines)
        return ('layer', name)

    # -- checks ----------------------------------------------------------------------------
    @staticmethod
    def limit(cons):
        """'< d' / '<= d' constraint -> distance in nm; anything else unsupported. A lower
        bound of 0 ('> 0 < d') is the same for Magic, which never flags zero distance."""
        cons = [c for c in cons if not (c[0] in ('>', '>=') and c[1] == 0)]
        if len(cons) == 1 and cons[0][0] in ('<', '<='):
            d = cons[0][1]
            if not isinstance(d, (int, float)):
                raise Unsupported('constraint expression')
            return nm(d) + (1 if cons[0][0] == '<=' else 0)
        raise Unsupported('constraint %s' % (cons,))

    BAD_OPTS = ('connected', 'projecting', 'not_projecting', 'parallel', 'perp', 'angled', 'notch',
                'space', 'exclude_shielded', 'acute', 'obtuse', 'ortho', 'corner_to_edge',
                'inside_also', 'measure_all', 'measure_coincident', 'overlap')

    def check(self, rule, n, local, msg):
        kind = n.kw['kind']
        for k in self.BAD_OPTS:
            if k in n.kw:
                raise Unsupported('%s option %s' % (kind.upper(), k))
        if n.kw.get('intersecting') == 'only':
            raise Unsupported('INTERSECTING ONLY')
        if n.kw.get('singular') == 'only':
            raise Unsupported('SINGULAR ONLY')
        if n.kw.get('metric', 'opposite') not in ('opposite', 'square', 'opposite_extended'):
            raise Unsupported('metric %s' % n.kw.get('metric'))
        d = self.limit(n.kw['cons'])
        args = n.args
        # native form
        try:
            tsets = [self.types_of(a, local) for a in args]
            if kind in ('int', 'ext') and not self.plane_of(set().union(*tsets)):
                raise Unsupported('types on several planes')
            ts = [','.join(sorted(t)) for t in tsets]
            if kind == 'int' and len(ts) == 1:
                return ('native', ['width %s %d \\\n\t"%s"' % (ts[0], d, msg)])
            if kind == 'ext' and len(ts) == 1:
                return ('native', ['spacing %s %s %d touching_ok \\\n\t"%s"' % (ts[0], ts[0], d, msg)])
            if kind == 'ext' and len(ts) == 2:
                return ('native', ['spacing %s %s %d touching_ok \\\n\t"%s"' % (ts[0], ts[1], d, msg)])
            if kind == 'enc' and len(ts) == 2 and not n.kw.get('outside_also'):
                return ('native', ['surround %s %s %d absence_ok \\\n\t"%s"' % (ts[0], ts[1], d, msg)])
        except Unsupported:
            pass
        ctx = Ctx(self)
        ops = [self.cif(a, local, ctx) for a in args]

        def as_layer(x):
            return x[1] if x[0] == 'layer' else self._mk(ctx, x[1], [])[1]

        if kind == 'int' and len(ops) == 1:
            return ('cif', ctx, ['cifwidth %s %d \\\n\t"%s"' % (as_layer(ops[0]), d, msg)])
        if kind == 'ext':
            if len(ops) == 2 and self.prims(args[0], local) & self.prims(args[1], local):
                # Magic's two-layer cifspacing is touching_illegal: shapes of one layer that
                # are part of the other (AA vs. AA inside TGOX) would all be flagged
                raise Unsupported('EXT between layers derived from the same drawn layer')
            a = as_layer(ops[0])
            b = as_layer(ops[1]) if len(ops) == 2 else a
            # Magic: touching_ok only between a layer and itself; for two layers it looks
            # outward from the edges of the first, so overlap inside it is not flagged
            adj = 'touching_ok' if a == b else 'touching_illegal'
            return ('cif', ctx, ['cifspacing %s %s %d %s \\\n\t"%s"' % (a, b, d, adj, msg)])
        if kind == 'enc' and len(ops) == 2:
            inner, outer = ops
            if n.kw.get('outside_also'):
                lines = ['grow %d' % d, 'and-not %s' % outer[1]]
                err = self._mk(ctx, inner[1], lines)
            else:
                part = self._mk(ctx, inner[1], ['and %s' % outer[1]])
                err = self._mk(ctx, part[1], ['grow %d' % d, 'and-not %s' % outer[1]])
            return ('cif', ctx, ['cifmaxwidth %s 0 bend_illegal \\\n\t"%s"' % (err[1], msg)])
        raise Unsupported('%s with %d operands' % (kind, len(ops)))

    def prims(self, n, local, depth=0):
        """drawn (primary) layers an expression is built from"""
        if depth > 80 or not isinstance(n, P.Node):
            return set()
        if n.op == 'name':
            nmu = n.kw['name'].upper()
            if nmu in local:
                return self.prims(local[nmu], local, depth + 1)
            if nmu in self.primary:
                return {nmu}
            if nmu in self.defs:
                return self.prims(self.defs[nmu], {}, depth + 1)
            return set()
        out = set()
        # only the first operand of a selection / NOT contributes shapes
        args = n.args[:1] if (n.op == 'sel' or (n.op == 'bool' and n.kw.get('op_') == 'NOT')) else n.args
        for a in args:
            out |= self.prims(a, local, depth + 1)
        return out

    def plane_of(self, types):
        """planes on which every type of the set is present (contacts are on all the planes
        of their residues)"""
        out = None
        for t in types:
            p = self.planes.get(t.lstrip('*'), set())
            out = set(p) if out is None else out & p
        return out or set()

    def area(self, n, local, msg):
        cons = n.kw['cons']
        if n.kw.get('neg') or not (len(cons) == 1 and cons[0][0] in ('<', '<=')):
            raise Unsupported('AREA constraint %s' % (cons,))
        a = cons[0][1] * UM * UM
        try:
            tset = self.types_of(n.args[0], local)
            if not self.plane_of(tset):
                raise Unsupported('AREA on several planes')
            ts = ','.join(sorted(tset))
            return ('native', ['area %s %d %d \\\n\t"%s"' % (ts, int(round(a)), max(1, int(a ** 0.5)), msg)])
        except Unsupported:
            pass
        ctx = Ctx(self)
        x = self.cif(n.args[0], local, ctx)
        lay = x[1] if x[0] == 'layer' else self._mk(ctx, x[1], [])[1]
        return ('cif', ctx, ['cifarea %s %d %d \\\n\t"%s"' % (lay, int(round(a)), max(1, int(a ** 0.5)), msg)])

    def output(self, rule, n, local, msg):
        # exemption wrappers around a check result: "<check> NOT INSIDE / NOT INTERACT <marker>"
        while n.op == 'sel' and n.kw.get('neg') and n.kw.get('kind') in ('inside', 'interact') \
                and not n.kw.get('cons') and n.args[0].op in ('check', 'sel', 'area'):
            n = n.args[0]
        if n.op == 'check':
            return self.check(rule, n, local, msg)
        if n.op == 'area' and not n.kw.get('neg'):
            return self.area(n, local, msg)
        # any other region expression: must be empty
        ctx = Ctx(self)
        r = self.cif(n, local, ctx)
        lay = r[1] if r[0] == 'layer' else self._mk(ctx, r[1], [])[1]
        return ('cif', ctx, ['cifmaxwidth %s 0 bend_illegal \\\n\t"%s"' % (lay, msg)])

    # -- driver ----------------------------------------------------------------------------
    def run(self, budget=CIF_BUDGET):
        pending = []
        nrules = 0
        for s in self.stmts:
            if s[0] != 'rule':
                continue
            nrules += 1
            name, comments, body = s[1], s[2], s[3]
            text = (comments[0] if comments else '').strip()
            text = re.sub(r'\s+', ' ', text).replace('"', "'").replace('\\', '/')[:110]
            msg = ('%s: %s' % (name, text)).replace('%', '%%')
            local = {}
            outs = []
            for st in body:
                if st[0] == 'assign':
                    local[st[1].upper()] = st[2]
                elif st[0] == 'out':
                    outs.append(st[1])
            if not outs:
                continue
            done, why = [], None
            for o in outs:
                try:
                    done.append(self.output(name, o, dict(local), msg))
                except Empty as e:
                    done.append(('empty', str(e)))
                except Unsupported as e:
                    why = str(e)
                except (KeyError, AttributeError, TypeError, IndexError) as e:
                    why = 'translator: %s' % e
            if why is not None and not any(d[0] in ('native', 'cif') for d in done):
                self.report.append((name, 'skipped', why))
                continue
            for d in done:
                if d[0] == 'native':
                    self.native.append((name, d[1]))
                elif d[0] == 'cif':
                    pending.append((len(d[1].new), name, d))
            status = 'partial' if why else 'ok'
            if all(d[0] == 'empty' for d in done):
                self.report.append((name, 'never', 'uses layers Magic does not read'))
            else:
                self.report.append((name, status, why or ''))
        # CIF rules, cheapest first, re-resolving shared layers as they get committed
        pending.sort(key=lambda x: x[0])
        dropped = set()
        for _, name, d in pending:
            ctx = d[1]
            # rename the attempt's layers onto the committed list (identical layers shared)
            sim, need = {}, 0
            for (lname, lines) in ctx.new:
                key = self._key(lines, sim)
                if key in self.cif_memo:
                    sim[lname] = self.cif_memo[key]
                else:
                    need += 1
                    sim[lname] = 'n%d' % need
            mapping = {}
            if len(self.cif_layers) + need > budget:
                dropped.add(name)
                continue
            for (lname, lines) in ctx.new:
                key = self._key(lines, mapping)
                if key in self.cif_memo:
                    mapping[lname] = self.cif_memo[key]
                    continue
                newname = 'c%d' % len(self.cif_layers)
                mapping[lname] = newname
                self.cif_memo[key] = newname
                self.cif_layers.append((newname, self._subst(lines, mapping)))
            self.cif_rules.append((name, self._subst(d[2], mapping)))
        for i, (name, st, why) in enumerate(self.report):
            if name in dropped:
                ncif = sum(1 for r in self.cif_rules if r[0] == name)
                nnat = sum(1 for r in self.native if r[0] == name)
                if ncif + nnat == 0:
                    self.report[i] = (name, 'skipped', 'CIF layer budget (255 per style)')
                else:
                    self.report[i] = (name, 'partial', 'CIF layer budget (255 per style)')
        self.nrules = nrules

    @staticmethod
    def _subst(lines, mapping):
        out = []
        for l in lines:
            out.append(re.sub(r'\bt\d+_\d+\b', lambda m: mapping.get(m.group(0), m.group(0)), l))
        return out

    def _key(self, lines, mapping):
        sub = self._subst(lines, mapping)
        return (sub[0].split()[0] + ' @' + (' ' + ' '.join(sub[0].split()[2:]) if len(sub[0].split()) > 2 else ''),
                tuple(sub[1:]))

    # -- output ----------------------------------------------------------------------------
    def cif_style(self):
        out = ['style drc', ' scalefactor 10 nanometers', ' gridlimit 1', '']
        for name, lines in self.cif_layers:
            head = lines[0].split()
            out.append(' templayer %s %s' % (name, ' '.join(head[2:])) if len(head) > 2 else ' templayer %s' % name)
            for l in lines[1:]:
                out.append('  ' + l)
        return '\n'.join(out) + '\n'

    def drc_section(self):
        out = [' cifstyle drc', '']
        out.append(' # ---- native rules (Calibre rules on unions of drawn layers)')
        out.append(' variants (fast),(full)')
        for name, rules in self.native:
            for r in rules:
                out.append(' ' + r)
        out.append('')
        out.append(' # ---- CIF rules on derived layers (style "drc" of cifoutput)')
        out.append(' variants (full)')
        for name, rules in self.cif_rules:
            for r in rules:
                out.append(' ' + r)
        out.append(' variants *')
        return '\n'.join(out) + '\n'

    def summary(self):
        c = collections.Counter(st for _, st, _ in self.report)
        why = collections.Counter(w for _, st, w in self.report if st == 'skipped')
        lines = ['Calibre rules: %d   translated fully: %d   partly: %d   skipped: %d   never apply: %d'
                 % (self.nrules, c['ok'], c['partial'], c['skipped'], c['never']),
                 'native Magic rules: %d   CIF rules: %d   CIF layers used: %d / 255'
                 % (sum(len(r) for _, r in self.native), len(self.cif_rules), len(self.cif_layers)),
                 '', 'skipped by reason:']
        for w, k in why.most_common():
            lines.append('  %4d  %s' % (k, w))
        lines.append('')
        for name, st, w in self.report:
            lines.append('%-28s %-8s %s' % (name, st, w))
        return '\n'.join(lines) + '\n'


def translate(gds_types, planes, deck=DRC_DECK):
    tr = Translator(deck, gds_types, planes)
    tr.run()
    return tr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--report')
    a = ap.parse_args()
    import gen_magic_tech as G
    tr = translate(*G.gds_type_map())
    s = tr.summary()
    if a.report:
        open(a.report, 'w').write(s)
    print('\n'.join(s.split('\n')[:12]))


if __name__ == '__main__':
    main()
