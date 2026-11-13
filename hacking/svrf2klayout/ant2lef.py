#!/usr/bin/env python3
"""Antenna rules of the Calibre antenna runset written into technology LEFs.

Usage: ant2lef.py <expanded.ant.svrf> <tech.lef> [<tech.lef> ...]   (files rewritten in place)

Every NET AREA RATIO check of the expanded runset (ICsprout_CalANT_expanded.svrf) has the form

    NET AREA RATIO ... GATE > v [ AREA(X)/AREA(GATE) - (AREA(X_DIO)*a + !!AREA(X_DIO)*b) ] [ACCUMULATE]

(or PERIMETER(X)*t/AREA(GATE) for the side wall checks). With the semantics settled against
Calibre (README, "Antenna deck"): without diode the limit is v, with a diode of area A it is
v + b + a*A. In LEF terms, per layer X and gate oxide:

    accumulated      ANTENNACUMAREARATIO v ; ANTENNACUMDIFFAREARATIO PWL ((0 v+b) (100 v+b+100a)) ;
    single layer     ANTENNAAREARATIO v ;    ANTENNADIFFAREARATIO    PWL (...) ;
    side wall        ANTENNASIDEAREARATIO v ; ANTENNADIFFSIDEAREARATIO PWL (...) ; THICKNESS t

GATE -> ANTENNAMODEL OXIDE1, GATE18 (DGOX 1.8 V) -> OXIDE2. Not written: the poly and
contact ratios of POLY (a MASTERSLICE layer, no routing there), and the RV check against
GATE1825 (thick oxide pad drivers): the KLayout antenna deck covers them.
Existing antenna statements of a layer are replaced, so the script can be re-run.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import svrf_parse as P  # noqa: E402

# runset layer -> LEF layer
LEF_LAYER = {'CT1': 'CT', 'M1': 'MET1', 'M2': 'MET2', 'M3': 'MET3', 'M4': 'MET4', 'M5': 'MET5',
             'T4M2': 'T4M2', 'VIA1': 'VIA1', 'VIA2': 'VIA2', 'VIA3': 'VIA3', 'VIA4': 'VIA4',
             'T4V2': 'T4V2', 'RDV': 'RV', 'RDL': 'RDL'}
OXIDE = {'GATE': 'OXIDE1', 'GATE18': 'OXIDE2'}
PWL_X = 100.0

RX = re.compile(r'^(AREA|PERIMETER) \( (\w+) \)(?: \* ([0-9.]+))? / AREA \( (\w+) \)'
                r'(?: - \( AREA \( (\w+) \) \* ([0-9.]+) \+ ! ! AREA \( \5 \) \* ([0-9.]+) \))?$')


def rules(path):
    """[(rule, lef layer, oxide, kind, v, a, b, thickness)]"""
    d = P.Deck(path)
    out = []

    def f(s, pth):
        if s[0] not in ('out', 'assign'):
            return
        n = s[1] if s[0] == 'out' else s[2]
        if not isinstance(n, P.Node) or n.op != 'net_area_ratio' or not n.kw.get('expr'):
            return
        rule = [x[1] for x in pth if x[0] == 'rule']
        if not rule:
            return                       # AC<n> accumulation layers
        m = RX.match(' '.join(n.kw['expr'].split()))
        cons = n.kw['cons']
        if not m or len(cons) != 1 or cons[0][0] != '>':
            print('ant2lef: skipped %s: %s' % (rule[0], n.kw['expr']), file=sys.stderr)
            return
        what, x, thick, gate, dio, a, b = m.groups()
        if x not in LEF_LAYER or gate not in OXIDE:
            print('ant2lef: skipped %s (%s / %s)' % (rule[0], x, gate), file=sys.stderr)
            return
        acc = bool(n.kw.get('accumulate'))
        kind = 'side' if what == 'PERIMETER' else ('cum' if acc else 'area')
        out.append((rule[0], LEF_LAYER[x], OXIDE[gate], kind, cons[0][1],
                    float(a) if a else None, float(b) if b else None, float(thick) if thick else None))
    P.walk_stmts(d.stmts, f)
    return out


KEYS = {'cum': ('ANTENNACUMAREARATIO', 'ANTENNACUMDIFFAREARATIO'),
        'area': ('ANTENNAAREARATIO', 'ANTENNADIFFAREARATIO'),
        'side': ('ANTENNASIDEAREARATIO', 'ANTENNADIFFSIDEAREARATIO')}


def layer_lines(rs):
    lines = []
    thick = None
    for ox in ('OXIDE1', 'OXIDE2'):
        sel = [r for r in rs if r[2] == ox]
        if not sel:
            continue
        lines.append('  ANTENNAMODEL %s ;' % ox)
        for rule, _, _, kind, v, a, b, t in sel:
            k1, k2 = KEYS[kind]
            lines.append('  %s %g ;   # %s' % (k1, v, rule))
            if a is not None:
                lines.append('  %s PWL ( ( 0 %g ) ( %g %g ) ) ;' % (k2, v + b, PWL_X, v + b + a * PWL_X))
            if t:
                thick = t
    return lines, thick


def rewrite(lef, rs):
    by_layer = {}
    for r in rs:
        by_layer.setdefault(r[1], []).append(r)
    src = open(lef).read().split('\n')
    out = []
    layer = None
    has_thick = False
    for ln in src:
        t = ln.split()
        if t[:1] == ['LAYER'] and len(t) == 2:
            layer = t[1]
            has_thick = False
        if layer and t and (t[0].startswith('ANTENNA') or (t[0] == '#' and 'antenna' in ln)):
            continue
        if layer and t and t[0] == 'THICKNESS':
            has_thick = True
        if layer and t[:1] == ['END'] and t[1:2] == [layer]:
            if layer in by_layer:
                lines, thick = layer_lines(by_layer[layer])
                if thick and not has_thick:
                    out.append('  THICKNESS %g ;   # antenna side wall thickness of the Calibre runset' % thick)
                out.append('  # antenna rules of the Calibre antenna runset (hacking/svrf2klayout/ant2lef.py)')
                out += lines
            layer = None
        out.append(ln)
    open(lef, 'w').write('\n'.join(out))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    rs = rules(sys.argv[1])
    for r in rs:
        print('ant2lef: %-16s %-5s %s %-4s > %-6g diode %s * A + %s' % (r[0], r[1], r[2], r[3], r[4], r[5], r[6]),
              file=sys.stderr)
    for lef in sys.argv[2:]:
        rewrite(lef, rs)
        print('ant2lef: wrote', lef, file=sys.stderr)


if __name__ == '__main__':
    main()
