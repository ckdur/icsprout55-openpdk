#!/usr/bin/env python3
"""
Translate a (TVF-expanded) Calibre SVRF DRC deck into a KLayout DRC deck.

Usage:
  svrf2klayout.py expanded.svrf out.drc [--name ICS55]

The generated deck embeds svrf_runtime.rb, which implements the SVRF
operations on top of the KLayout DRC DSL. Rules are executed lazily: derived
layers are evaluated on first use and cached.

Run-time variables (klayout -rd):
  input, topcell, report, log     (files; log is optional)
  thr / threads                   number of threads
  select / unselect               regexp of rule names to run / skip
  flat                            "1" -> flat mode (default deep)
  densityRules                    "False" disables density rules
  <SWITCH>=<value>                override any #DEFINE switch (e.g. OPEN_RECOMMENDED_ON=YES)
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import svrf_parse as P  # noqa: E402


def rb_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('#', '\\#') + '"'


def rb_num(v):
    if v == int(v) and abs(v) < 1e12:
        return '%d.0' % int(v)
    return repr(float(v))


def rb_cons(c):
    if not c:
        return '[]'
    return '[' + ', '.join('[%s, %s]' % (rb_str(op), rb_num(v)) for op, v in c) + ']'


class Gen:
    def __init__(self, deck):
        self.deck = deck
        self.layer_numbers = {}   # name -> [numbers]
        self.num_poly = {}        # number -> [(l,d)]
        self.num_text = {}        # number -> [(l,t)]
        self.unsupported = []
        self.out = []
        self.rule_names = []
        self.warnings = []
        self.text_layers = set()
        self._collect_layers(deck.stmts)
        self._collect_text_usage(deck.stmts)
        self.conn_layers = set()
        self.global_defs = {}
        self.local_defs = {}

        def fc(s, p):
            if s[0] == 'connect':
                for x in s[2]:
                    self.conn_layers.add(x.upper())
                if s[3]:
                    self.conn_layers.add(s[3].upper())
            elif s[0] == 'assign' and not any(q[0] == 'rule' for q in p):
                self.global_defs.setdefault(s[1].upper(), s[2])
        P.walk_stmts(deck.stmts, fc)

    def net_base(self, n, depth=0):
        """name of a layer in the connectivity from which n derives"""
        if depth > 50 or not isinstance(n, P.Node):
            return None
        if n.op == 'name':
            nm = n.kw['name'].upper()
            if nm in self.conn_layers:
                return n.kw['name']
            d = self.local_defs.get(nm) or self.global_defs.get(nm)
            return self.net_base(d, depth + 1) if d is not None else None
        if n.op == 'stamp':
            return self.net_base(n.args[1], depth + 1)
        if n.op in ('bool', 'nary', 'sel', 'copy', 'bracket', 'size', 'with_width', 'area', 'rectangle',
                    'holes', 'enclose_rect', 'net_area_ratio', 'esel'):
            return self.net_base(n.args[0], depth + 1) if n.args else None
        return None

    # -- layer bookkeeping --
    def _collect_layers(self, stmts):
        def f(s, p):
            if s[0] == 'layermap':
                _, gl, kind, gd, num = s
                if kind == 'DATATYPE':
                    self.num_poly.setdefault(num, []).append((gl, gd))
                else:
                    self.num_text.setdefault(num, []).append((gl, gd))
            elif s[0] == 'layer':
                self.layer_numbers[s[1].upper()] = s[2]
        P.walk_stmts(stmts, f)

    def _collect_text_usage(self, stmts):
        def visit(n):
            if not isinstance(n, P.Node):
                return
            if n.op == 'with_text':
                t = n.args[1]
                if t.op == 'name':
                    self.text_layers.add(t.kw['name'].upper())
            for a in n.args:
                visit(a)
            for v in n.kw.values():
                if isinstance(v, P.Node):
                    visit(v)

        def f(s, p):
            if s[0] in ('assign',):
                visit(s[2])
            elif s[0] == 'out':
                visit(s[1])
        P.walk_stmts(stmts, f)

    def layer_specs(self, name, text=False):
        nums = self.layer_numbers.get(name.upper(), [])
        specs = []
        for n in nums:
            m = self.num_text if text else self.num_poly
            if n in m:
                specs.extend(m[n])
            elif not text and n not in self.num_text:
                # unmapped number: GDS layer n datatype 0
                specs.append((n, 0))
        return specs

    # -- expression codegen --
    def expr(self, n, sc):
        m = getattr(self, 'x_' + n.op, None)
        if m is None:
            raise NotImplementedError('op %s' % n.op)
        return m(n, sc)

    def x_name(self, n, sc):
        return '%s[%s]' % (sc, rb_str(n.kw['name']))

    def x_bracket(self, n, sc):
        return self.expr(n.args[0], sc)

    def x_str(self, n, sc):
        return rb_str(n.kw['value'])

    def x_copy(self, n, sc):
        return self.expr(n.args[0], sc)

    def x_bool(self, n, sc):
        op = n.kw['op_']
        if len(n.args) > 2:
            return 'sv_nary(%s, %s)' % (rb_str(op), ', '.join(self.expr(a, sc) for a in n.args))
        return 'sv_bool(%s, %s, %s)' % (rb_str(op), self.expr(n.args[0], sc), self.expr(n.args[1], sc))

    def x_nary(self, n, sc):
        return 'sv_nary(%s, %s)' % (rb_str(n.kw['op_']), ', '.join(self.expr(a, sc) for a in n.args))

    def x_edge_or(self, n, sc):
        return 'sv_edge_or(%s, %s)' % (self.expr(n.args[0], sc), self.expr(n.args[1], sc))

    def _opts(self, d):
        parts = []
        for k, v in d.items():
            if isinstance(v, P.Node):
                vs = self._cur_expr(v)
            elif isinstance(v, bool):
                vs = 'true' if v else 'false'
            elif isinstance(v, (int, float)):
                vs = rb_num(v)
            elif isinstance(v, str) and k == 'bases':
                vs = v
            elif isinstance(v, str):
                vs = rb_str(v)
            elif isinstance(v, list):
                if v and isinstance(v[0], tuple) and len(v[0]) == 2 and isinstance(v[0][0], str):
                    vs = rb_cons(v)
                else:
                    vs = repr(v)
            elif v is None:
                vs = 'nil'
            else:
                vs = repr(v)
            parts.append(':%s => %s' % (k, vs))
        return '{' + ', '.join(parts) + '}'

    def x_sel(self, n, sc):
        kw = {k: v for k, v in n.kw.items() if k in ('singular', 'by_net')}
        return 'sv_sel_any(%s, %s, %s, %s, %s, %s)' % (
            rb_str(n.kw['kind']), self.expr(n.args[0], sc), self.expr(n.args[1], sc),
            rb_cons(n.kw.get('cons')), 'true' if n.kw.get('neg') else 'false', self._opts(kw))

    def x_esel(self, n, sc):
        return 'sv_esel(%s, %s, %s, %s, %s)' % (
            rb_str(n.kw['kind']), self.expr(n.args[0], sc), self.expr(n.args[1], sc),
            rb_cons(n.kw.get('cons')), 'true' if n.kw.get('neg') else 'false')

    def x_size(self, n, sc):
        kw = dict(n.kw)
        d = kw.pop('d')
        self._sc = sc
        return 'sv_size(%s, %s, %s)' % (self.expr(n.args[0], sc), rb_num(d), self._opts(kw))

    def _cur_expr(self, v):
        return self.expr(v, self._sc)

    def x_check(self, n, sc):
        kw = dict(n.kw)
        kind = kw.pop('kind')
        cons = kw.pop('cons')
        args = n.args
        out = None
        if args[0].op == 'bracket':
            out = 1
        if len(args) > 1 and args[1].op == 'bracket':
            out = 2
        if out:
            kw['out'] = out
        if 'connected' in kw:
            ba = self.net_base(args[0])
            bb = self.net_base(args[1]) if len(args) > 1 else None
            if ba:
                kw['netbase_a'] = P.Name(ba)
            if bb:
                kw['netbase_b'] = P.Name(bb)
        self._sc = sc
        a = self.expr(args[0], sc)
        b = self.expr(args[1], sc) if len(args) > 1 else 'nil'
        return 'sv_check(%s, %s, %s, %s, %s)' % (rb_str(kind), a, b, rb_cons(cons), self._opts(kw))

    def x_area(self, n, sc):
        return 'sv_area(%s, %s, %s)' % (self.expr(n.args[0], sc), rb_cons(n.kw['cons']),
                                        'true' if n.kw.get('neg') else 'false')

    def x_perimeter(self, n, sc):
        return 'sv_perimeter(%s, %s, %s)' % (self.expr(n.args[0], sc), rb_cons(n.kw['cons']),
                                             'true' if n.kw.get('neg') else 'false')

    def x_length(self, n, sc):
        return 'sv_length(%s, %s, %s)' % (self.expr(n.args[0], sc), rb_cons(n.kw['cons']),
                                          'true' if n.kw.get('neg') else 'false')

    def x_angle(self, n, sc):
        return 'sv_angle(%s, %s, %s)' % (self.expr(n.args[0], sc), rb_cons(n.kw['cons']),
                                         'true' if n.kw.get('neg') else 'false')

    def x_holes(self, n, sc):
        self._sc = sc
        return 'sv_holes(%s, %s)' % (self.expr(n.args[0], sc), self._opts(n.kw))

    def x_donut(self, n, sc):
        return 'sv_donut(%s, %s, %s)' % (self.expr(n.args[0], sc), rb_cons(n.kw.get('cons')),
                                         'true' if n.kw.get('neg') else 'false')

    def x_extent(self, n, sc):
        layers = list(n.kw.get('layers') or [])
        ign = set(x.upper() for x in (n.kw.get('ignore') or []))
        if not layers and ign:
            # all original layers except the ignored ones
            layers = [nm for nm in self.layer_numbers if nm not in ign and self.layer_specs(nm)]
        if layers:
            ls = []
            for l in layers:
                if isinstance(l, P.Node):
                    ls.append(self.expr(l, sc))
                elif l.upper() not in ign:
                    ls.append('%s[%s]' % (sc, rb_str(l)))
            return 'sv_extent({:layers => [%s]})' % ', '.join(ls)
        return 'sv_extent()'

    def x_extents(self, n, sc):
        return 'sv_extents(%s)' % self.expr(n.args[0], sc)

    def x_expand_edge(self, n, sc):
        self._sc = sc
        return 'sv_expand_edge(%s, %s)' % (self.expr(n.args[0], sc), self._opts(n.kw))

    def x_convex_edge(self, n, sc):
        self._sc = sc
        return 'sv_convex_edge(%s, %s)' % (self.expr(n.args[0], sc), self._opts(n.kw))

    def x_with_width(self, n, sc):
        return 'sv_with_width(%s, %s, %s)' % (self.expr(n.args[0], sc), rb_cons(n.kw['cons']),
                                              'true' if n.kw.get('neg') else 'false')

    def x_with_text(self, n, sc):
        t = n.args[1]
        if t.op == 'name':
            specs = self.layer_specs(t.kw['name'], text=True)
            tl = 'sv_text(%s)' % repr([list(s) for s in specs])
        else:
            raise NotImplementedError('WITH TEXT on derived text layer')
        return 'sv_with_text(%s, %s, %s, %s)' % (self.expr(n.args[0], sc), tl, rb_str(n.kw['pattern']),
                                                 'true' if n.kw.get('neg') else 'false')

    def x_rectangle(self, n, sc):
        self._sc = sc
        return 'sv_rectangle(%s, %s)' % (self.expr(n.args[0], sc), self._opts(n.kw))

    def x_enclose_rect(self, n, sc):
        kw = dict(n.kw)
        w = kw.pop('w')
        l = kw.pop('l')
        self._sc = sc
        return 'sv_enclose_rect(%s, %s, %s, %s)' % (self.expr(n.args[0], sc), rb_num(w), rb_num(l), self._opts(kw))

    def x_rect_enc(self, n, sc):
        goods = '[' + ', '.join('[' + ', '.join('[%s, %s]' % (rb_num(v), 'true' if o else 'false') for v, o in g)
                                + ']' for g in n.kw['goods']) + ']'
        kw = {k: v for k, v in n.kw.items() if k not in ('goods', 'bads')}
        self._sc = sc
        return 'sv_rect_enc(%s, %s, %s, %s)' % (self.expr(n.args[0], sc), self.expr(n.args[1], sc), goods,
                                               self._opts(kw))

    def x_density(self, n, sc):
        kw = dict(n.kw)
        cons = kw.pop('cons')
        if 'inside_of_box' in kw:
            kw['inside_of_box'] = list(kw['inside_of_box'])
        self._sc = sc
        return 'sv_density([%s], %s, %s)' % (', '.join(self.expr(a, sc) for a in n.args), rb_cons(cons),
                                             self._opts(kw))

    def x_dfm_space(self, n, sc):
        kw = dict(n.kw)
        cons = kw.pop('cons')
        return 'sv_dfm_space([%s], %s, %s)' % (', '.join(self.expr(a, sc) for a in n.args), rb_cons(cons),
                                               self._opts(kw))

    def x_dfm_copy(self, n, sc):
        return 'sv_dfm_copy(%s, %s)' % (self.expr(n.args[0], sc), rb_str(n.kw.get('mode') or ''))

    def x_dfm_property(self, n, sc):
        props = '[' + ', '.join('[%s, %s]' % (rb_str(e), rb_cons(c)) for e, c in n.kw.get('props')) + ']'
        return 'sv_dfm_property([%s], %s)' % (', '.join(self.expr(a, sc) for a in n.args), props)

    def x_net_area_ratio(self, n, sc):
        kw = dict(n.kw)
        cons = kw.pop('cons')
        expr = kw.pop('expr')
        bases = [self.net_base(a) for a in n.args]
        kw['bases'] = '[' + ', '.join(('%s[%s]' % (sc, rb_str(b))) if b else 'nil' for b in bases) + ']'
        self._sc = sc
        return 'sv_net_area_ratio([%s], %s, %s, %s)' % (', '.join(self.expr(a, sc) for a in n.args),
                                                        rb_str(expr) if expr else 'nil', rb_cons(cons),
                                                        self._opts(kw))

    def x_stamp(self, n, sc):
        b = self.net_base(n.args[1])
        return 'sv_stamp(%s, %s, %s)' % (self.expr(n.args[0], sc), self.expr(n.args[1], sc),
                                         ('%s[%s]' % (sc, rb_str(b))) if b else 'nil')

    def x_drawn(self, n, sc):
        specs = sorted(set(tuple(x) for nm in self.layer_numbers for x in self.layer_specs(nm)))
        return 'sv_drawn(%s, [%s])' % (rb_str(n.kw['kind']), ', '.join('sv_input([[%d, %d]])' % x for x in specs))

    def x_area_ratio(self, n, sc):
        raise NotImplementedError('AREA RATIO')

    # -- statements --
    def emit(self, s, ind=0):
        self.out.append('  ' * ind + s)

    def gen_stmts(self, stmts, ind, sc, in_rule=False):
        for s in stmts:
            k = s[0]
            if k == 'define':
                self.emit('sv_define(%s, %s)' % (rb_str(s[1]), rb_str(s[2])), ind)
            elif k == 'ifdef':
                _, name, val, neg, body, other = s
                cond = 'sv_ifdef(%s, %s)' % (rb_str(name), rb_str(val) if val is not None else 'nil')
                if neg:
                    cond = '!' + cond
                self.emit('if %s' % cond, ind)
                self.gen_stmts(body, ind + 1, sc, in_rule)
                if other:
                    self.emit('else', ind)
                    self.gen_stmts(other, ind + 1, sc, in_rule)
                self.emit('end', ind)
            elif k == 'layer':
                name = s[1]
                specs = self.layer_specs(name)
                self.emit('%s.define(%s) { sv_input(%s) }' % (sc, rb_str(name), repr([list(x) for x in specs])),
                          ind)
            elif k in ('layermap', 'layermap_range', 'variable', 'directive', 'error'):
                if k == 'error':
                    self.warnings.append(s)
                    self.emit('# PARSE ERROR: %s' % s[2], ind)
                continue
            elif k == 'assign':
                name, e = s[1], s[2]
                try:
                    code = self.expr(e, sc)
                    self.emit('%s.define(%s) { %s }' % (sc, rb_str(name), code), ind)
                except NotImplementedError as ex:
                    self.unsupported.append((name, str(ex)))
                    self.emit('%s.define(%s) { raise "SVRF unsupported: %s" }' % (sc, rb_str(name), str(ex)), ind)
            elif k == 'connect':
                _, soft, layers, via = s
                self.emit('sv_connect(%s, %s)' % ('[' + ', '.join(rb_str(x) for x in layers) + ']',
                                                  rb_str(via) if via else 'nil'), ind)
            elif k == 'rule':
                _, name, comments, body, ln = s
                desc = ' '.join(comments)
                self.rule_names.append(name)
                self.emit('sv_rule(%s, %s) do |outs|' % (rb_str(name), rb_str(desc)), ind)
                self.emit('s = SvScope.new(self, $sv_G, %s)' % rb_str(name), ind + 1)
                self.local_defs = {}
                P.walk_stmts(body, lambda q, pth: self.local_defs.setdefault(q[1].upper(), q[2])
                             if q[0] == 'assign' else None)
                self.gen_stmts(body, ind + 1, 's', in_rule=True)
                self.emit('end', ind)
            elif k == 'out':
                e = s[1]
                try:
                    code = self.expr(e, sc)
                    self.emit('outs << proc { %s }' % code, ind)
                except NotImplementedError as ex:
                    self.unsupported.append(('out@%d' % s[2], str(ex)))
                    self.emit('raise "SVRF unsupported: %s"' % str(ex), ind)
            else:
                raise RuntimeError('unknown stmt %s' % k)


PRELUDE = r'''# frozen_string_literal: false
# ============================================================================
# KLayout DRC deck for {name}
#
# AUTOMATICALLY GENERATED by hacking/svrf2klayout/svrf2klayout.py from the
# Calibre SVRF deck {src}
# Do not edit by hand: edit the translator/runtime and regenerate.
# ============================================================================

require 'time'
require 'logger'

$sv_exec_start = Time.now

if $input
  if $topcell
    source($input, $topcell)
  else
    source($input)
  end
end

if $report
  report("{name} DRC (translated from Calibre)", $report)
else
  report("{name} DRC (translated from Calibre)")
end

$sv_flat = ($flat.to_s == "1" || $flat.to_s.downcase == "true")
if $sv_flat
  flat
else
  deep
end

nthr = ($threads || $thr || "4").to_i
threads(nthr)
verbose(false)

# -rd log=<file>: also write the log messages to a file
if $log
  $sv_logf = File.open($log, "w")
  def log(msg, indent = 0)
    puts msg
    $sv_logf.puts(msg)
    $sv_logf.flush
  end
end

$sv_verbose = ($sv_verbose_flag.to_s == "1")
$sv_strict = ($strict.to_s == "1")
$sv_select = $select ? Regexp.new($select) : nil
$sv_unselect = $unselect ? Regexp.new($unselect) : nil
$sv_failed = []

# #DEFINE overrides from the command line (-rd NAME=VALUE)
$sv_defines = {{}}
$sv_overrides = {{}}
$sv_switches = {{}}
{overrides}
if $densityRules && $densityRules.to_s.downcase == "false"
  $sv_overrides["DENSITY_RULES"] = "NO"
end

'''

POSTLUDE = r'''
$sv_G_scope_done = true
if $dump
  $dump.split(",").each do |n|
    next if n.include?(":")
    begin
      l = $sv_G[n]
      if $sv_flat
        d = l.data.dup; d.flatten; l = sv_w(d)
      end
      l.output("DUMP_#{n}", "debug dump of #{n}")
    rescue => ex
      log("dump #{n} failed: #{ex}")
    end
  end
end
nrules = sv_run_rules
log("SVRF: #{nrules} rules executed, #{$sv_failed.size} failed")
$sv_failed.each { |n, m| log("  FAILED #{n}: #{m}") }
log("SVRF: total runtime #{'%.1f' % (Time.now - $sv_exec_start)} s")
'''


def generate(svrf, out, name='ICS55', runtime=None):
    deck = P.Deck(svrf)
    if deck.errors:
        for e in deck.errors:
            print('parse error:', e, file=sys.stderr)
    g = Gen(deck)
    g.gen_stmts(deck.stmts, 0, '$sv_G')
    # defines that may be overridden
    defines = []

    def f(s, p):
        if s[0] == 'define':
            defines.append(s[1])
    P.walk_stmts(deck.stmts, f)
    ov = []
    for d in sorted(set(x.upper() for x in defines)):
        var = d
        ov.append('$sv_overrides[%s] = $%s.to_s if defined?($%s) && $%s' % (rb_str(d), var, var, var))
    rt = open(runtime or os.path.join(HERE, 'svrf_runtime.rb')).read()
    text = PRELUDE.format(name=name, src=os.path.basename(svrf), overrides='\n'.join(ov))
    text += rt + '\n'
    text += '$sv_G = SvScope.new(self, nil, "GLOBAL")\n'
    text += '\n'.join(g.out) + '\n'
    text += POSTLUDE
    with open(out, 'w') as f:
        f.write(text)
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('svrf')
    ap.add_argument('out')
    ap.add_argument('--name', default='ICS55')
    a = ap.parse_args()
    g = generate(a.svrf, a.out, a.name)
    print('rules: %d, unsupported constructs: %d' % (len(g.rule_names), len(g.unsupported)))
    for u in g.unsupported:
        print('  unsupported:', u)


if __name__ == '__main__':
    main()
