#!/usr/bin/env python3
"""
Parser for (TVF-expanded) Calibre SVRF rule decks.

Produces a list of top-level statements:
  ('define', name, value)                 #DEFINE
  ('ifdef', name, value, neg, body, else) #IFDEF / #IFNDEF blocks
  ('layermap', gds_layer, kind, gds_type, number)
  ('layer', name, [numbers])
  ('assign', name, expr)                  derived layer
  ('connect', soft, [layers], via)        CONNECT / SCONNECT
  ('rule', name, [comments], [stmts])     rule check (stmts are assign/out)
  ('out', expr)                           output statement in rule
  ('variable', name, value)
  ('directive', text)                     anything else (ignored)

Expressions are Node objects (see class Node).
"""

import re
import sys


class ParseError(Exception):
    pass


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r'''
    (?P<ws>[ \t\r]+)
  | (?P<str>"[^"]*")
  | (?P<op><=|>=|==|!=|<|>|=)
  | (?P<num>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)
  | (?P<word>[A-Za-z_?][A-Za-z0-9_:?.$]*)
  | (?P<punct>[()\[\]{}+\-*/,@!])
  | (?P<other>.)
''', re.VERBOSE)


class Tok:
    __slots__ = ('t', 'v', 'line')

    def __init__(self, t, v, line):
        self.t = t
        self.v = v
        self.line = line

    @property
    def u(self):
        return self.v.upper() if self.t == 'word' else self.v

    def __repr__(self):
        return '%s:%r' % (self.t, self.v)


def strip_comments(text):
    # remove /* */ comments and // comments (outside of strings)
    out = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if text.startswith('/*', i):
            j = text.find('*/', i + 2)
            if j < 0:
                j = n
            # keep newlines to preserve line numbers
            out.append('\n' * text.count('\n', i, j))
            i = j + 2
            continue
        if text.startswith('//', i):
            j = text.find('\n', i)
            if j < 0:
                j = n
            i = j
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def tokenize_line(s, lineno):
    toks = []
    pos = 0
    while pos < len(s):
        m = TOKEN_RE.match(s, pos)
        if not m:
            raise ParseError('line %d: cannot tokenize at %r' % (lineno, s[pos:pos + 20]))
        pos = m.end()
        k = m.lastgroup
        if k == 'ws':
            continue
        toks.append(Tok(k, m.group(k), lineno))
    return toks


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------

class Node:
    """op: string; args: list of Node; kw: dict of options"""

    def __init__(self, op, args=None, **kw):
        self.op = op
        self.args = args or []
        self.kw = kw

    def __repr__(self):
        s = self.op
        if self.op == 'name':
            return 'N(%s)' % self.kw['name']
        if self.op == 'num':
            return '%g' % self.kw['value']
        a = ', '.join(repr(x) for x in self.args)
        k = ', '.join('%s=%r' % (kk, vv) for kk, vv in self.kw.items())
        return '%s(%s%s%s)' % (s, a, '; ' if k and a else '', k)


def Name(n):
    return Node('name', name=n)


# Keywords that start a prefix operation
PREFIX_OPS = {
    'COPY', 'OR', 'AND', 'XOR', 'NOT', 'SIZE', 'EXT', 'EXTERNAL', 'INT',
    'INTERNAL', 'ENC', 'ENCLOSURE', 'AREA', 'LENGTH', 'ANGLE', 'HOLES',
    'DONUT', 'EXTENT', 'EXTENTS', 'EXPAND', 'CONVEX', 'WITH', 'RECTANGLE',
    'ENCLOSE', 'DENSITY', 'DFM', 'NET', 'STAMP', 'DRAWN', 'RECTANGLES',
    'PERIMETER', 'VERTEX', 'GROW', 'SHRINK', 'SHIFT', 'MERGE',
}

# Binary keywords (after a left operand)
BIN_BOOL = {'AND', 'OR', 'XOR', 'NOT'}
BIN_SEL = {'INTERACT', 'INSIDE', 'OUTSIDE', 'TOUCH', 'ENCLOSE', 'CUT'}

CMP = {'<', '<=', '>', '>=', '==', '!='}


class ExprParser:
    def __init__(self, toks, variables=None):
        self.toks = toks
        self.i = 0
        self.variables = variables or {}

    # -- helpers --
    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def pu(self, k=0):
        t = self.peek(k)
        return t.u if t is not None else None

    def next(self):
        t = self.peek()
        if t is None:
            raise ParseError('unexpected end of expression')
        self.i += 1
        return t

    def expect_word(self, w):
        t = self.next()
        if t.u != w:
            raise ParseError('line %d: expected %s, got %r' % (t.line, w, t.v))
        return t

    def accept(self, *words):
        """accept a sequence of words if they match"""
        for k, w in enumerate(words):
            if self.pu(k) != w:
                return False
        self.i += len(words)
        return True

    def at_end(self):
        return self.i >= len(self.toks)

    def error(self, msg):
        t = self.peek()
        ln = t.line if t else (self.toks[-1].line if self.toks else 0)
        ctx = ' '.join(x.v for x in self.toks[max(0, self.i - 6):self.i + 6])
        raise ParseError('line %d: %s  [near: %s]' % (ln, msg, ctx))

    # -- numbers / constraints --
    def is_value_start(self):
        t = self.peek()
        if t is None:
            return False
        if t.t == 'num':
            return True
        if t.v == '-' and self.peek(1) is not None and self.peek(1).t == 'num':
            return True
        if t.v == '(':
            # parenthesized arithmetic: ( num ...
            t1 = self.peek(1)
            return t1 is not None and (t1.t == 'num' or (t1.t == 'word' and t1.v in self.variables))
        if t.t == 'word' and t.v in self.variables:
            return True
        return False

    def parse_value(self):
        """parse an arithmetic value expression -> float"""
        return self._arith_add()

    def _arith_add(self):
        v = self._arith_mul()
        while self.peek() is not None and self.peek().v in ('+', '-'):
            op = self.next().v
            w = self._arith_mul()
            v = v + w if op == '+' else v - w
        return v

    def _arith_mul(self):
        v = self._arith_atom()
        while self.peek() is not None and self.peek().v in ('*', '/'):
            op = self.next().v
            w = self._arith_atom()
            v = v * w if op == '*' else v / w
        return v

    def _arith_atom(self):
        t = self.next()
        if t.v == '-':
            return -self._arith_atom()
        if t.t == 'num':
            return float(t.v)
        if t.v == '(':
            v = self._arith_add()
            if self.next().v != ')':
                self.error('expected )')
            return v
        if t.t == 'word' and t.v in self.variables:
            return float(self.variables[t.v])
        self.error('expected number, got %r' % t.v)

    def is_constraint_start(self):
        t = self.peek()
        return t is not None and t.t == 'op' and t.v in CMP

    def parse_constraint(self, optional=True):
        cons = []
        while self.is_constraint_start():
            op = self.next().v
            val = self.parse_value()
            cons.append((op, val))
        if not cons and not optional:
            self.error('expected constraint')
        return cons

    # -- expression grammar --
    def parse_statement_expr(self):
        e = self.parse_expr()
        if not self.at_end():
            self.error('trailing tokens')
        return e

    def parse_expr(self):
        left = self.parse_unary()
        while not self.at_end():
            t = self.peek()
            u = t.u
            if t.v in (')', ']'):
                break
            nxt = self.parse_infix(left)
            if nxt is None:
                break
            left = nxt
        return left

    def parse_infix(self, left):
        u = self.pu()
        neg = False
        save = self.i
        if u == 'NOT' and self.pu(1) in (BIN_SEL | {'COIN', 'COINCIDENT', 'WITH', 'RECTANGLE', 'ENCLOSE'}):
            # NOT INTERACT etc., NOT WITH EDGE, NOT WITH WIDTH ...
            if self.pu(1) == 'WITH' and self.pu(2) != 'EDGE':
                # postfix NOT WITH WIDTH / NOT WITH TEXT
                return self.parse_prefix_op(first=left)
            if self.pu(1) == 'RECTANGLE':
                return self.parse_prefix_op(first=left)
            if self.pu(1) == 'ENCLOSE' and self.pu(2) == 'RECTANGLE':
                return self.parse_prefix_op(first=left)
            neg = True
            self.i += 1
            u = self.pu()
        if u == 'OR' and self.pu(1) == 'EDGE' and not neg:
            self.i += 2
            right = self.parse_unary()
            return Node('edge_or', [left, right])
        if u in BIN_BOOL and not neg:
            self.i += 1
            right = self.parse_unary()
            return Node('bool', [left, right], op_=u)
        if u in BIN_SEL:
            self.i += 1
            if u == 'ENCLOSE' and self.pu() == 'RECTANGLE':
                self.i = save
                return self.parse_prefix_op(first=left)
            edge = False
            side = None
            if u in ('INSIDE', 'OUTSIDE') and self.pu() == 'EDGE':
                self.i += 1
                return self._edge_sel(left, u.lower() + '_edge', neg)
            if u == 'TOUCH':
                if self.pu() == 'EDGE':
                    self.i += 1
                    return self._edge_sel(left, 'touch_edge', neg)
                if self.pu() in ('INSIDE', 'OUTSIDE') and self.pu(1) == 'EDGE':
                    side = self.next().u.lower()
                    self.i += 1
                    return self._edge_sel(left, 'touch_%s_edge' % side, neg)
            right = self.parse_unary()
            cons = self.parse_constraint()
            opts = {}
            while True:
                if self.accept('SINGULAR', 'ONLY'):
                    opts['singular'] = 'only'
                elif self.accept('SINGULAR', 'ALSO'):
                    opts['singular'] = 'also'
                elif self.accept('SINGULAR'):
                    opts['singular'] = 'also'
                elif self.accept('BY', 'NET'):
                    opts['by_net'] = True
                elif self.accept('EVEN'):
                    opts['even'] = True
                elif self.accept('ODD'):
                    opts['odd'] = True
                else:
                    break
            return Node('sel', [left, right], kind=u.lower(), neg=neg, cons=cons, **opts)
        if u in ('COIN', 'COINCIDENT'):
            self.i += 1
            side = None
            if self.pu() in ('INSIDE', 'OUTSIDE'):
                side = self.next().u.lower()
            self.expect_word('EDGE')
            kind = 'coin' if side is None else 'coin_' + side
            return self._edge_sel(left, kind, neg)
        if u == 'WITH' and self.pu(1) == 'EDGE':
            self.i += 2
            return self._edge_sel(left, 'with_edge', neg)
        if not neg and u in PREFIX_OPS and u not in BIN_BOOL:
            # postfix form of a unary operation: "X WITH WIDTH < 1", "X CONVEX EDGE < 2"
            return self.parse_prefix_op(first=left)
        if neg:
            self.i = save
        return None

    def _edge_sel(self, left, kind, neg):
        right = self.parse_unary()
        cons = self.parse_constraint()
        opts = {}
        if self.accept('ENDPOINT', 'ONLY'):
            opts['endpoint'] = 'only'
        elif self.accept('ENDPOINT', 'ALSO'):
            opts['endpoint'] = 'also'
        return Node('esel', [left, right], kind=kind, neg=neg, cons=cons, **opts)

    def parse_unary(self):
        t = self.peek()
        if t is None:
            self.error('expected operand')
        u = t.u
        pb = self.try_prefix_binary()
        if pb is not None:
            return pb
        if u in PREFIX_OPS:
            # Avoid treating layer names that clash with keywords as ops when
            # they are followed by something that cannot be an operand.
            n = self.parse_prefix_op()
            if n is not None:
                return n
        return self.parse_primary()

    def try_prefix_binary(self):
        """prefix forms of binary ops: 'TOUCH A B', 'NOT INTERACT A B',
        'INSIDE EDGE A B', 'COIN EDGE A B', ..."""
        save = self.i
        neg = False
        if self.pu() == 'NOT' and self.pu(1) in (BIN_SEL | {'COIN', 'COINCIDENT'}):
            neg = True
            self.i += 1
        u = self.pu()
        kind = None
        if u in ('INSIDE', 'OUTSIDE') and self.pu(1) == 'EDGE':
            self.i += 2
            kind = ('esel', u.lower() + '_edge')
        elif u in ('COIN', 'COINCIDENT'):
            self.i += 1
            side = None
            if self.pu() in ('INSIDE', 'OUTSIDE'):
                side = self.next().u.lower()
            self.expect_word('EDGE')
            kind = ('esel', 'coin' if side is None else 'coin_' + side)
        elif u == 'TOUCH' and self.pu(1) == 'EDGE':
            self.i += 2
            kind = ('esel', 'touch_edge')
        elif u == 'TOUCH' and self.pu(1) in ('INSIDE', 'OUTSIDE') and self.pu(2) == 'EDGE':
            kind = ('esel', 'touch_%s_edge' % self.pu(1).lower())
            self.i += 3
        elif u in BIN_SEL and not (u == 'ENCLOSE' and self.pu(1) == 'RECTANGLE'):
            # need two operands following
            t1 = self.peek(1)
            if t1 is None or not (t1.t == 'word' or t1.v == '('):
                self.i = save
                return None
            self.i += 1
            kind = ('sel', u.lower())
        else:
            self.i = save
            return None
        a = self.parse_operand()
        b = self.parse_operand()
        cons = self.parse_constraint()
        opts = {}
        while True:
            if self.accept('SINGULAR', 'ONLY'):
                opts['singular'] = 'only'
            elif self.accept('SINGULAR', 'ALSO') or self.accept('SINGULAR'):
                opts['singular'] = 'also'
            elif self.accept('BY', 'NET'):
                opts['by_net'] = True
            else:
                break
        return Node(kind[0], [a, b], kind=kind[1], neg=neg, cons=cons, **opts)

    def parse_primary(self):
        t = self.next()
        if t.v == '(':
            e = self.parse_expr()
            if self.next().v != ')':
                self.error('expected )')
            return e
        if t.v == '[':
            e = self.parse_expr()
            if self.next().v != ']':
                self.error('expected ]')
            return Node('bracket', [e])
        if t.t == 'word':
            return Name(t.v)
        if t.t == 'str':
            return Node('str', value=t.v[1:-1])
        self.error('unexpected token %r' % t.v)

    def parse_operand(self):
        """operand of a prefix operation: a primary (name, (expr), [expr])"""
        t = self.peek()
        if t is None:
            self.error('expected operand')
        if t.v in ('(', '['):
            return self.parse_primary()
        if t.t == 'word':
            if t.u in ('COPY',) or (t.u in PREFIX_OPS and t.u not in ('EMPTY',) and self._looks_like_op()):
                return self.parse_prefix_op()
            self.i += 1
            return Name(t.v)
        self.error('expected operand')

    def _looks_like_op(self):
        # used to decide if a keyword-named token is an operation in operand position
        u = self.pu()
        u1 = self.pu(1)
        if u in ('AREA', 'LENGTH', 'ANGLE', 'HOLES', 'DONUT', 'EXTENTS', 'COPY', 'SIZE', 'EXT', 'INT', 'ENC',
                 'DENSITY', 'STAMP'):
            return u1 is not None and u1 not in (')',)
        if u in ('EXPAND', 'CONVEX'):
            return u1 == 'EDGE'
        if u == 'WITH':
            return u1 in ('WIDTH', 'TEXT', 'EDGE')
        if u == 'RECTANGLE':
            return True
        if u == 'ENCLOSE':
            return u1 == 'RECTANGLE'
        if u == 'NET':
            return u1 == 'AREA'
        if u == 'DRAWN':
            return True
        if u == 'EXTENT':
            return True
        if u == 'DFM':
            return True
        return False

    def maybe_operand(self):
        t = self.peek()
        if t is None:
            return None
        if t.v in ('(', '['):
            # could be arithmetic value, e.g. (1.5 + 0.01) - only in BY context
            return self.parse_primary()
        if t.t == 'word' and t.u not in OPTION_WORDS:
            self.i += 1
            return Name(t.v)
        return None

    def parse_prefix_op(self, first=None):
        """parse a prefix operation; if first is given it is the first operand
        (postfix form like 'X WITH WIDTH < 1')."""
        save = self.i
        u = self.pu()
        neg = False
        if u == 'NOT' and first is not None:
            neg = True
            self.i += 1
            u = self.pu()

        def operand():
            nonlocal first
            if first is not None:
                f = first
                first = None
                return f
            return self.parse_operand()

        if u == 'COPY':
            self.i += 1
            return Node('copy', [operand()])
        if u in ('OR', 'AND', 'XOR', 'NOT') and first is None:
            self.i += 1
            if u == 'NOT':
                # prefix NOT with RECTANGLE / WITH etc.
                if self.pu() == 'RECTANGLE' or (self.pu() == 'ENCLOSE' and self.pu(1) == 'RECTANGLE') \
                        or (self.pu() == 'WITH' and self.pu(1) in ('WIDTH', 'TEXT')) \
                        or self.pu() in ('LENGTH', 'ANGLE', 'DONUT', 'INSIDE', 'OUTSIDE', 'INTERACT', 'TOUCH',
                                         'ENCLOSE', 'CUT'):
                    n = self.parse_prefix_op_neg()
                    return n
            ops = []
            while not self.at_end() and self.peek().v not in (')', ']'):
                t = self.peek()
                if t.t == 'word' and t.u in OPTION_WORDS:
                    break
                if t.t == 'op':
                    break
                ops.append(self.parse_operand())
            if len(ops) < 1:
                self.error('prefix %s needs operands' % u)
            if u == 'NOT':
                return Node('bool', ops, op_='NOT')
            if u == 'AND' and len(ops) == 1:
                # "AND X" with a single operand = merged copy
                return Node('copy', ops)
            res = ops[0]
            if len(ops) == 1:
                return Node('copy', ops)
            return Node('nary', ops, op_=u)
        if u == 'SIZE':
            self.i += 1
            a = operand()
            self.expect_word('BY')
            d = self.parse_value()
            kw = {}
            while not self.at_end():
                if self.accept('INSIDE', 'OF'):
                    kw['inside_of'] = self.parse_operand()
                elif self.accept('OUTSIDE', 'OF'):
                    kw['outside_of'] = self.parse_operand()
                elif self.accept('STEP'):
                    kw['step'] = self.parse_value()
                elif self.accept('OVERUNDER'):
                    kw['mode'] = 'overunder'
                elif self.accept('UNDEROVER'):
                    kw['mode'] = 'underover'
                elif self.accept('TRUNCATE'):
                    kw['truncate'] = self.parse_value()
                elif self.accept('BEVEL'):
                    kw['bevel'] = self.parse_value()
                else:
                    break
            return Node('size', [a], d=d, **kw)
        if u in ('EXT', 'EXTERNAL', 'INT', 'INTERNAL', 'ENC', 'ENCLOSURE'):
            self.i += 1
            kind = {'EXTERNAL': 'EXT', 'INTERNAL': 'INT', 'ENCLOSURE': 'ENC'}.get(u, u).lower()
            a = operand()
            b = None
            if not self.is_constraint_start():
                b = self.parse_operand()
            cons = self.parse_constraint(optional=False)
            opts = self.parse_check_options()
            args = [a] if b is None else [a, b]
            return Node('check', args, kind=kind, cons=cons, **opts)
        if u == 'AREA' and self.pu(1) == 'RATIO':
            self.i += 2
            a = operand()
            b = self.parse_operand()
            cons = self.parse_constraint(optional=False)
            return Node('area_ratio', [a, b], cons=cons)
        if u in ('AREA', 'PERIMETER'):
            self.i += 1
            a = operand()
            cons = self.parse_constraint(optional=False)
            return Node(u.lower(), [a], cons=cons, neg=neg)
        if u in ('LENGTH', 'ANGLE'):
            self.i += 1
            a = operand()
            cons = self.parse_constraint(optional=False)
            return Node(u.lower(), [a], cons=cons, neg=neg)
        if u == 'HOLES':
            self.i += 1
            a = operand()
            kw = {}
            while True:
                if self.accept('INNER'):
                    kw['inner'] = True
                elif self.pu() == 'EMPTY' and (self.peek(1) is None or self.peek(1).v in (')',) or
                                                self.pu(1) in OPTION_WORDS or self.pu(1) in BIN_BOOL or
                                                self.pu(1) in BIN_SEL):
                    self.i += 1
                    kw['empty'] = True
                elif self.is_constraint_start():
                    kw['cons'] = self.parse_constraint()
                else:
                    break
            return Node('holes', [a], **kw)
        if u == 'DONUT':
            self.i += 1
            a = operand()
            cons = self.parse_constraint()
            return Node('donut', [a], cons=cons, neg=neg)
        if u == 'EXTENTS':
            self.i += 1
            a = operand()
            return Node('extents', [a])
        if u == 'EXTENT':
            self.i += 1
            kw = {}
            layers = []
            if self.accept('DRAWN'):
                kw['drawn'] = True
                if self.accept('ORIGINAL'):
                    kw['original'] = True
            ignore = []
            mode = layers
            while not self.at_end() and self.peek().v not in (')',):
                if self.accept('IGNORE'):
                    mode = ignore
                    continue
                t = self.peek()
                if t.t != 'word' or t.u in BIN_BOOL or t.u in BIN_SEL:
                    break
                self.i += 1
                mode.append(t.v)
            if first is not None:
                layers.insert(0, first)
            return Node('extent', [], layers=layers, ignore=ignore, **kw)
        if u == 'EXPAND' and self.pu(1) == 'EDGE':
            self.i += 2
            a = operand()
            kw = {}
            while True:
                if self.accept('INSIDE', 'BY'):
                    kw['inside'] = self.parse_value()
                elif self.accept('OUTSIDE', 'BY'):
                    kw['outside'] = self.parse_value()
                elif self.accept('EXTEND', 'BY'):
                    kw['extend'] = self.parse_value()
                elif self.accept('CORNER', 'FILL'):
                    kw['corner_fill'] = True
                elif self.accept('BY'):
                    v = self.parse_value()
                    kw['inside'] = v
                    kw['outside'] = v
                else:
                    break
            return Node('expand_edge', [a], **kw)
        if u == 'CONVEX' and self.pu(1) == 'EDGE':
            self.i += 2
            a = operand()
            kw = {}
            if self.accept('ANGLE1'):
                kw['angle1'] = self.parse_constraint(optional=False)
                self.expect_word('ANGLE2')
                kw['angle2'] = self.parse_constraint(optional=False)
                if self.accept('WITH', 'LENGTH'):
                    kw['length'] = self.parse_constraint(optional=False)
            else:
                kw['count'] = self.parse_constraint(optional=False)
                if self.accept('WITH', 'LENGTH'):
                    kw['length'] = self.parse_constraint(optional=False)
            return Node('convex_edge', [a], **kw)
        if u == 'WITH' and self.pu(1) == 'WIDTH':
            self.i += 2
            a = operand()
            cons = self.parse_constraint(optional=False)
            return Node('with_width', [a], cons=cons, neg=neg)
        if u == 'WITH' and self.pu(1) == 'TEXT':
            self.i += 2
            a = operand()
            t = self.next()
            pat = t.v[1:-1] if t.t == 'str' else t.v
            nt = self.peek()
            if nt is not None and nt.t == 'word' and nt.u not in OPTION_WORDS:
                tl = self.parse_operand()
            else:
                tl = a  # text on the layer itself
            kw = {}
            if self.accept('PRIMARY', 'ONLY'):
                kw['primary_only'] = True
            return Node('with_text', [a, tl], pattern=pat, neg=neg, **kw)
        if u == 'RECTANGLE' and self.pu(1) in ('ENC', 'ENCLOSURE'):
            self.i += 2
            a = operand()
            b = self.parse_operand()
            opts = self.parse_check_options()
            goods = []
            while self.accept('GOOD'):
                vals = []
                while self.is_value_start() and len(vals) < 4:
                    v = self.parse_value()
                    opp = False
                    if self.accept('OPPOSITE'):
                        opp = True
                        if self.accept('EXTENDED'):
                            self.parse_value()
                    vals.append((v, opp))
                goods.append(vals)
            bad = []
            while self.accept('BAD'):
                vals = []
                while self.is_value_start() and len(vals) < 4:
                    v = self.parse_value()
                    opp = bool(self.accept('OPPOSITE'))
                    vals.append((v, opp))
                bad.append(vals)
            return Node('rect_enc', [a, b], goods=goods, bads=bad, **opts)
        if u == 'RECTANGLE':
            self.i += 1
            a = operand()
            kw = {}
            if self.is_constraint_start():
                kw['w'] = self.parse_constraint()
                if self.accept('BY'):
                    kw['l'] = self.parse_constraint(optional=False)
            while True:
                if self.accept('ASPECT'):
                    kw['aspect'] = self.parse_constraint(optional=False)
                elif self.accept('ORTHOGONAL', 'ONLY'):
                    kw['ortho'] = True
                else:
                    break
            return Node('rectangle', [a], neg=neg, **kw)
        if u == 'ENCLOSE' and self.pu(1) == 'RECTANGLE':
            self.i += 2
            a = operand()
            w = self.parse_value()
            l = self.parse_value() if self.is_value_start() else w
            kw = {}
            if self.accept('ORTHOGONAL', 'ONLY'):
                kw['ortho'] = True
            return Node('enclose_rect', [a], w=w, l=l, neg=neg, **kw)
        if u == 'DENSITY':
            self.i += 1
            layers = [operand()]
            while not self.at_end() and not self.is_constraint_start():
                layers.append(self.parse_operand())
            cons = self.parse_constraint(optional=False)
            kw = {}
            while not self.at_end() and self.peek().v not in (')',):
                if self.accept('WINDOW'):
                    kw['window'] = self.parse_value()
                    if self.is_value_start():
                        kw['window_y'] = self.parse_value()
                elif self.accept('STEP'):
                    kw['step'] = self.parse_value()
                    if self.is_value_start():
                        kw['step_y'] = self.parse_value()
                elif self.accept('BACKUP'):
                    kw['backup'] = True
                elif self.accept('TRUNCATE'):
                    kw['truncate'] = True
                elif self.accept('IGNORE'):
                    kw['ignore'] = True
                elif self.accept('WRAP'):
                    kw['wrap'] = True
                elif self.accept('GRADIENT'):
                    kw['gradient'] = self.parse_constraint(optional=False)
                    if self.accept('ABSOLUTE'):
                        kw['absolute'] = True
                    elif self.accept('RELATIVE'):
                        kw['relative'] = True
                elif self.accept('INSIDE', 'OF', 'LAYER'):
                    kw['inside_of_layer'] = self.parse_operand()
                elif self.accept('INSIDE', 'OF', 'EXTENT'):
                    kw['inside_of_extent'] = True
                elif self.accept('INSIDE', 'OF'):
                    x1 = self.parse_value(); y1 = self.parse_value()
                    x2 = self.parse_value(); y2 = self.parse_value()
                    kw['inside_of_box'] = (x1, y1, x2, y2)
                elif self.accept('PRINT'):
                    if self.accept('ONLY'):
                        pass
                    self.next()
                elif self.accept('RDB'):
                    if self.accept('ONLY'):
                        pass
                    self.next()
                elif self.accept('MAG'):
                    self.parse_value()
                elif self.accept('CENTERS'):
                    kw['centers'] = True
                else:
                    self.error('unknown DENSITY option')
            return Node('density', layers, cons=cons, **kw)
        if u == 'DFM':
            self.i += 1
            if self.accept('COPY'):
                a = self.parse_operand()
                mode = None
                if self.accept('EDGE'):
                    mode = 'edge'
                elif self.accept('REGION'):
                    mode = 'region'
                elif self.accept('CELL', 'LIST'):
                    mode = 'cell'
                    self.next()
                return Node('dfm_copy', [a], mode=mode)
            if self.accept('SPACE'):
                a = operand()
                b = None
                if not self.is_constraint_start():
                    b = self.parse_operand()
                cons = self.parse_constraint(optional=False)
                kw = {}
                while not self.at_end() and self.peek().v not in (')',):
                    if self.accept('BY', 'INT'):
                        kw['by'] = 'int'
                    elif self.accept('BY', 'EXT'):
                        kw['by'] = 'ext'
                    elif self.accept('BY', 'ENC'):
                        kw['by'] = 'enc'
                    elif self.accept('ALL'):
                        kw['all'] = True
                    elif self.accept('HORIZONTAL'):
                        kw['horizontal'] = True
                    elif self.accept('VERTICAL'):
                        kw['vertical'] = True
                    else:
                        self.error('unknown DFM SPACE option')
                args = [a] if b is None else [a, b]
                return Node('dfm_space', args, cons=cons, **kw)
            if self.accept('PROPERTY'):
                layers = [self.parse_operand()]
                while not self.at_end() and self.peek().t == 'word' and self.pu() not in OPTION_WORDS:
                    layers.append(self.parse_operand())
                kw = {}
                while self.accept('OVERLAP') or self.accept('ABUT') or self.accept('ALSO') or \
                        self.accept('MULTI') or self.accept('NODAL'):
                    pass
                props = []
                while self.peek() is not None and self.peek().v == '[':
                    # [NAME = expr] constraint
                    self.next()
                    depth = 1
                    toks = []
                    while depth:
                        t = self.next()
                        if t.v == '[':
                            depth += 1
                        elif t.v == ']':
                            depth -= 1
                            if depth == 0:
                                break
                        toks.append(t.v)
                    cons = self.parse_constraint()
                    props.append((' '.join(toks), cons))
                return Node('dfm_property', layers, props=props)
            self.error('unsupported DFM operation')
        if u == 'NET' and self.pu(1) == 'AREA' and self.pu(2) == 'RATIO':
            self.i += 3
            a = operand()
            layers = []
            while not self.at_end() and not self.is_constraint_start() and self.peek().v != '[':
                layers.append(self.parse_operand())
            expr = None
            if self.peek() is not None and self.peek().v == '[':
                self.next()
                depth = 1
                toks = []
                while True:
                    t = self.next()
                    if t.v == '[':
                        depth += 1
                    elif t.v == ']':
                        depth -= 1
                        if depth == 0:
                            break
                    toks.append(t.v)
                expr = ' '.join(toks)
            cons = self.parse_constraint(optional=False)
            kw = {}
            while not self.at_end() and self.peek().v not in (')',):
                if self.accept('RDB'):
                    if self.accept('ONLY'):
                        pass
                    self.next()
                    while not self.at_end() and self.peek().t == 'word' and self.pu() not in OPTION_WORDS:
                        self.next()
                elif self.accept('ACCUMULATE'):
                    kw['accumulate'] = True
                elif self.accept('INSIDE', 'OF', 'LAYER'):
                    kw['inside_of_layer'] = self.parse_operand()
                else:
                    break
            return Node('net_area_ratio', [a] + layers, expr=expr, cons=cons, **kw)
        if u == 'STAMP':
            self.i += 1
            a = operand()
            self.expect_word('BY')
            b = self.parse_operand()
            return Node('stamp', [a, b])
        if u == 'DRAWN':
            self.i += 1
            k = self.next().u
            return Node('drawn', [], kind=k.lower())
        if u == 'RECTANGLES':
            self.error('RECTANGLES not supported')
        if u in ('GROW', 'SHRINK', 'SHIFT', 'MERGE', 'VERTEX'):
            self.error('%s not supported' % u)
        # Not an op after all
        self.i = save
        if first is not None:
            return None
        return None

    def parse_prefix_op_neg(self):
        """after a prefix NOT; parse the following op as negated"""
        u = self.pu()
        n = self.parse_prefix_op()
        if n is None:
            self.error('bad NOT prefix op')
        n.kw['neg'] = not n.kw.get('neg', False)
        return n

    def parse_check_options(self):
        o = {}
        while not self.at_end():
            t = self.peek()
            if t.v in (')', ']'):
                break
            if self.accept('ABUT'):
                if self.is_constraint_start():
                    o['abut'] = self.parse_constraint()
                else:
                    o['abut'] = [('<', 180.0)]
            elif self.accept('SINGULAR'):
                o['singular'] = True
                if self.accept('ALSO'):
                    pass
                elif self.accept('ONLY'):
                    o['singular'] = 'only'
            elif self.accept('REGION'):
                o['region'] = True
                if self.accept('EXTENTS'):
                    o['region'] = 'extents'
                elif self.accept('CENTERLINE'):
                    o['region'] = 'centerline'
            elif self.accept('OPPOSITE'):
                o['metric'] = 'opposite'
                if self.accept('EXTENDED'):
                    o['metric'] = 'opposite_extended'
                    o['opp_ext'] = self.parse_value()
                elif self.accept('SYMMETRIC'):
                    o['metric'] = 'opposite_symmetric'
                elif self.accept('FSYMMETRIC'):
                    o['metric'] = 'opposite_fsymmetric'
            elif self.accept('SQUARE'):
                o['metric'] = 'square'
            elif self.accept('PROJECTING') or self.accept('PROJ'):
                o['projecting'] = self.parse_constraint()
            elif self.accept('NOT', 'PROJECTING') or self.accept('NOT', 'PROJ'):
                o['not_projecting'] = True
            elif self.accept('PARALLEL', 'ONLY') or self.accept('PARA', 'ONLY'):
                o['parallel'] = 'only'
            elif self.accept('PARALLEL', 'ALSO') or self.accept('PARA', 'ALSO'):
                o['parallel'] = 'also'
            elif self.accept('NOT', 'PARALLEL') or self.accept('NOT', 'PARA'):
                o['parallel'] = 'not'
            elif self.accept('PERPENDICULAR', 'ONLY') or self.accept('PERP', 'ONLY'):
                o['perp'] = 'only'
            elif self.accept('PERPENDICULAR', 'ALSO') or self.accept('PERP', 'ALSO'):
                o['perp'] = 'also'
            elif self.accept('NOT', 'PERPENDICULAR') or self.accept('NOT', 'PERP'):
                o['perp'] = 'not'
            elif self.accept('INTERSECTING', 'ONLY'):
                o['intersecting'] = 'only'
            elif self.accept('INTERSECTING', 'ALSO'):
                o['intersecting'] = 'also'
            elif self.accept('NOT', 'INTERSECTING'):
                o['intersecting'] = 'not'
            elif self.accept('NOT', 'CONNECTED'):
                o['connected'] = False
            elif self.accept('CONNECTED'):
                o['connected'] = True
            elif self.accept('MEASURE', 'ALL'):
                o['measure_all'] = True
            elif self.accept('MEASURE', 'COINCIDENT'):
                o['measure_coincident'] = True
            elif self.accept('OVERLAP'):
                o['overlap'] = True
            elif self.accept('OUTSIDE', 'ALSO'):
                o['outside_also'] = True
            elif self.accept('INSIDE', 'ALSO'):
                o['inside_also'] = True
            elif self.accept('ANGLED'):
                o['angled'] = self.parse_constraint(optional=False)
            elif self.accept('NOTCH'):
                o['notch'] = True
            elif self.accept('SPACE'):
                o['space'] = True
            elif self.accept('EXCLUDE', 'SHIELDED'):
                o['exclude_shielded'] = True
                if self.is_value_start():
                    o['shield_count'] = self.parse_value()
            elif self.accept('ACUTE', 'ALSO'):
                o['acute'] = 'also'
            elif self.accept('ACUTE', 'ONLY'):
                o['acute'] = 'only'
            elif self.accept('NOT', 'ACUTE'):
                o['acute'] = 'not'
            elif self.accept('OBTUSE', 'ALSO'):
                o['obtuse'] = 'also'
            elif self.accept('OBTUSE', 'ONLY'):
                o['obtuse'] = 'only'
            elif self.accept('NOT', 'OBTUSE'):
                o['obtuse'] = 'not'
            elif self.accept('ORTHOGONAL', 'ONLY'):
                o['ortho'] = True
            elif self.accept('CORNER', 'TO', 'EDGE'):
                o['corner_to_edge'] = True
            else:
                break
        return o


OPTION_WORDS = {
    'ABUT', 'SINGULAR', 'REGION', 'OPPOSITE', 'SQUARE', 'PROJECTING', 'PROJ', 'PARALLEL', 'PARA',
    'PERPENDICULAR', 'PERP', 'INTERSECTING', 'CONNECTED', 'MEASURE', 'OVERLAP', 'ANGLED', 'NOTCH',
    'SPACE', 'EXCLUDE', 'ACUTE', 'OBTUSE', 'BY', 'INSIDE', 'OUTSIDE', 'STEP', 'WINDOW', 'BACKUP',
    'PRINT', 'GRADIENT', 'GOOD', 'BAD', 'ASPECT', 'ORTHOGONAL', 'INNER', 'TRUNCATE', 'BEVEL',
    'OVERUNDER', 'UNDEROVER', 'RDB', 'IGNORE', 'ONLY', 'ALSO', 'ANGLE1', 'ANGLE2', 'EXTEND', 'CORNER',
    'NOT', 'AND', 'OR', 'XOR', 'INTERACT', 'TOUCH', 'ENCLOSE', 'CUT', 'COIN', 'COINCIDENT', 'WITH',
    'ACCUMULATE',
}


# ---------------------------------------------------------------------------
# Statement level
# ---------------------------------------------------------------------------

CONT_START = {'GOOD', 'BAD'}


def logical_lines(text):
    """yield (lineno, tokens) logical statements; joins lines while paren depth > 0
    and joins lines starting with continuation keywords."""
    lines = text.split('\n')
    out = []
    cur = None
    depth = 0
    for idx, raw in enumerate(lines):
        ln = idx + 1
        s = raw.strip()
        if not s:
            continue
        if s.startswith('@'):
            if cur is not None and depth == 0:
                out.append(cur)
                cur = None
            out.append((ln, [Tok('comment', s[1:].strip(), ln)]))
            continue
        toks = tokenize_line(s, ln)
        if not toks:
            continue
        is_cont = (cur is not None and depth == 0 and toks[0].t == 'word' and toks[0].u in CONT_START
                   and len(toks) > 1 and (toks[1].t == 'num' or toks[1].v == '-'))
        if cur is not None and (depth > 0 or is_cont):
            cur[1].extend(toks)
        else:
            if cur is not None:
                out.append(cur)
            cur = (ln, list(toks))
        for t in toks:
            if t.v in ('(', '['):
                depth += 1
            elif t.v in (')', ']'):
                depth -= 1
        if depth < 0:
            depth = 0
    if cur is not None:
        out.append(cur)
    return out


class DeckParser:
    def __init__(self, text, defines=None):
        self.text = strip_comments(text)
        self.variables = {}
        self.macros = {}
        self.errors = []
        self.stmts = None

    def parse(self):
        lines = logical_lines(self.text)
        self.lines = lines
        self.pos = 0
        self.stmts = self._parse_block(top=True)
        return self.stmts

    def _peek_line(self):
        return self.lines[self.pos] if self.pos < len(self.lines) else None

    def _parse_block(self, top=False, in_rule=False, end_on=None):
        res = []
        while self.pos < len(self.lines):
            ln, toks = self.lines[self.pos]
            t0 = toks[0]
            if t0.t == 'comment':
                self.pos += 1
                if in_rule:
                    res.append(('comment', t0.v))
                continue
            # preprocessor
            if t0.v == '#' or (t0.t == 'word' and False):
                pass
            first = toks[0].v
            if first == '}':
                if in_rule:
                    # end of rule; leave remaining tokens (unlikely)
                    self.pos += 1
                    if len(toks) > 1:
                        self.errors.append((ln, 'tokens after }'))
                    return res
                self.pos += 1
                continue
            pre = self._preproc(ln, toks)
            if pre is not None:
                kind = pre[0]
                if kind in ('else', 'endif'):
                    if end_on is not None:
                        return res, kind
                    self.errors.append((ln, 'unbalanced #%s' % kind))
                    self.pos += 1
                    continue
                self.pos += 1
                if kind == 'define':
                    res.append(pre)
                    continue
                if kind == 'ifdef':
                    body, how = self._parse_block(in_rule=in_rule, end_on=True)
                    other = []
                    if how == 'else':
                        self.pos += 1
                        other, how = self._parse_block(in_rule=in_rule, end_on=True)
                    self.pos += 1  # consume #ENDIF
                    res.append(('ifdef', pre[1], pre[2], pre[3], body, other))
                    continue
                if kind == 'other':
                    continue
            try:
                st = self._statement(ln, toks, in_rule)
            except ParseError as e:
                self.errors.append((ln, str(e)))
                st = ('error', ln, ' '.join(t.v for t in toks), str(e))
                self.pos += 1
            if st is None:
                continue
            if isinstance(st, list):
                res.extend(st)
            else:
                res.append(st)
        if end_on is not None:
            return res, 'eof'
        return res

    def _preproc(self, ln, toks):
        # '#' isn't a token char; handle via raw word starting with '#'
        return None

    def _statement(self, ln, toks, in_rule):
        u0 = toks[0].u
        # rule check start: NAME { ...
        if len(toks) >= 2 and toks[1].v == '{' and toks[0].t == 'word' and toks[-1].v == '}':
            # one-line rule: NAME { expr }
            self.pos += 1
            name = toks[0].v
            inner = toks[2:-1]
            stmts = []
            if inner:
                stmts.append(self._simple_statement(ln, inner, True))
            return ('rule', name, [], stmts, ln)
        if len(toks) >= 2 and toks[1].v == '{' and toks[0].t == 'word':
            self.pos += 1
            name = toks[0].v
            body = self._parse_block(in_rule=True)
            comments = [b[1] for b in body if b[0] == 'comment']
            stmts = [b for b in body if b[0] != 'comment']
            return ('rule', name, comments, stmts, ln)
        if len(toks) == 1 and toks[0].t == 'word' and self.pos + 1 < len(self.lines) \
                and self.lines[self.pos + 1][1][0].v == '{' and len(self.lines[self.pos + 1][1]) == 1:
            self.pos += 2
            name = toks[0].v
            body = self._parse_block(in_rule=True)
            comments = [b[1] for b in body if b[0] == 'comment']
            stmts = [b for b in body if b[0] != 'comment']
            return ('rule', name, comments, stmts, ln)
        if u0 == 'DMACRO':
            # DMACRO name args { body }
            name = toks[1].v
            args = []
            k = 2
            while k < len(toks) and toks[k].v != '{':
                args.append(toks[k].v)
                k += 1
            self.pos += 1
            body_lines = []
            depth = 1
            while self.pos < len(self.lines):
                l2, t2 = self.lines[self.pos]
                self.pos += 1
                if t2[0].v == '}' and len(t2) == 1:
                    break
                body_lines.append((l2, t2))
            self.macros[name.upper()] = (args, body_lines)
            return None
        if u0 == 'CMACRO':
            self.pos += 1
            name = toks[1].v.upper()
            if name in getattr(self, 'prop_macros', ()):
                return ('directive', 'CMACRO ' + ' '.join(t.v for t in toks[1:]))
            if name not in self.macros:
                raise ParseError('unknown macro %s' % name)
            args, body = self.macros[name]
            vals = toks[2:]
            if len(vals) != len(args):
                raise ParseError('macro %s arg count' % name)
            sub = {a: v for a, v in zip(args, vals)}
            res = []
            for l2, t2 in body:
                nt = []
                for t in t2:
                    if t.t == 'word' and t.v in sub:
                        r = sub[t.v]
                        nt.append(Tok(r.t, r.v, l2))
                    else:
                        nt.append(t)
                if nt[0].t == 'comment':
                    res.append(('comment', nt[0].v))
                    continue
                res.append(self._simple_statement(l2, nt, in_rule))
            return res
        self.pos += 1
        return self._simple_statement(ln, toks, in_rule)

    def _device(self, ln, toks):
        # DEVICE type[(model)] seed pin(NAME)... <aux>... [CMACRO name args...] [NETLIST ELEMENT x] [(swap)]
        k = 1
        dtype = toks[k].v
        k += 1
        model = None
        if k < len(toks) and toks[k].v == '(':
            model = toks[k + 1].v
            k += 3
        seed = toks[k].v
        k += 1
        pins = []
        aux = []
        macro = None
        extra = {}
        while k < len(toks):
            t = toks[k]
            if t.u == 'CMACRO':
                k += 1
                mname = toks[k].v
                k += 1
                margs = []
                while k < len(toks) and toks[k].u not in ('NETLIST', 'TEXT') and toks[k].v != '[':
                    margs.append(toks[k].v)
                    k += 1
                macro = (mname, margs)
                continue
            if t.u == 'NETLIST':
                # NETLIST ELEMENT X / NETLIST MODEL name
                extra[toks[k + 1].u.lower()] = toks[k + 2].v
                k += 3
                continue
            if t.v == '<':
                aux.append(toks[k + 1].v)
                k += 3
                continue
            if t.v == '(' and k + 2 < len(toks) and toks[k + 2].v == ')' and not pins:
                k += 3
                continue
            if t.v == '(':
                # swap list (A B) -> skip
                while k < len(toks) and toks[k].v != ')':
                    k += 1
                k += 1
                continue
            if t.v == '[':
                depth = 0
                while k < len(toks):
                    if toks[k].v == '[':
                        depth += 1
                    elif toks[k].v == ']':
                        depth -= 1
                        if depth == 0:
                            k += 1
                            break
                    k += 1
                extra['has_property_block'] = True
                continue
            if t.t == 'word' and k + 3 < len(toks) + 1 and k + 1 < len(toks) and toks[k + 1].v == '(':
                pins.append((t.v, toks[k + 2].v))
                k += 4
                continue
            if t.t == 'word':
                pins.append((t.v, None))
                k += 1
                continue
            k += 1
        return ('device', dtype, model, seed, pins, aux, macro, extra, ln)

    def _simple_statement(self, ln, toks, in_rule):
        u0 = toks[0].u
        if u0 == 'LAYER' and len(toks) >= 2 and toks[1].u == 'MAP':
            # LAYER MAP l DATATYPE|TEXTTYPE d n
            gl = int(toks[2].v)
            kind = toks[3].u
            # constraint forms are not supported here
            if toks[4].t == 'num':
                gd = int(toks[4].v)
                num = int(toks[5].v)
                return ('layermap', gl, kind, gd, num)
            # range: >= a <= b n
            p = ExprParser(toks[4:])
            cons = p.parse_constraint()
            num = int(p.next().v)
            return ('layermap_range', gl, kind, cons, num)
        if u0 == 'LAYER' and len(toks) >= 3:
            name = toks[1].v
            nums = []
            for t in toks[2:]:
                nums.append(int(t.v))
            return ('layer', name, nums)
        if u0 in ('CONNECT', 'SCONNECT'):
            parts = [t.v for t in toks[1:]]
            via = None
            if 'BY' in [p.upper() for p in parts]:
                k = [p.upper() for p in parts].index('BY')
                via = parts[k + 1]
                parts = parts[:k]
            extra = {}
            return ('connect', u0 == 'SCONNECT', parts, via)
        if u0 == 'DEVICE':
            return self._device(ln, toks)
        if u0 == 'TEXT' and len(toks) > 2 and toks[1].u == 'LAYER':
            names = []
            att = []
            k = 2
            while k < len(toks) and toks[k].u != 'ATTACH':
                names.append(toks[k].v)
                k += 1
            res = [('text_layer', names)]
            while k < len(toks) and toks[k].u == 'ATTACH':
                res.append(('attach', toks[k + 1].v, toks[k + 2].v))
                k += 3
            return res
        if u0 == 'ATTACH':
            return ('attach', toks[1].v, toks[2].v)
        if u0 == 'PORT' and len(toks) > 3 and toks[1].u == 'LAYER' and toks[2].u == 'TEXT':
            return ('port_text', [t.v for t in toks[3:]])
        if u0 == 'VARIABLE':
            name = toks[1].v
            val = ' '.join(t.v for t in toks[2:])
            try:
                self.variables[name] = float(val)
            except ValueError:
                self.variables[name] = val
            return ('variable', name, val)
        if u0 in ('GROUP', 'LAYOUT', 'DRC', 'FLAG', 'PRECISION', 'RESOLUTION', 'TEXT', 'LVS', 'LABEL',
                  'VIRTUAL', 'SOURCE', 'MASK', 'ERC', 'TITLE', 'UNIT', 'SVRF', 'PEX', 'DFM', 'PORT',
                  'TRACE', 'INCLUDE', 'DISCONNECT'):
            if u0 == 'DFM' and len(toks) > 1 and toks[1].u in ('COPY', 'SPACE', 'PROPERTY'):
                pass
            else:
                return ('directive', ' '.join(t.v for t in toks))
        if toks[0].t == 'word' and len(toks) >= 2 and toks[1].v == '=':
            name = toks[0].v
            p = ExprParser(toks[2:], self.variables)
            e = p.parse_statement_expr()
            return ('assign', name, e, ln)
        if toks[0].u == 'SETLAYER' and len(toks) >= 3 and toks[2].v == '=':
            name = toks[1].v
            p = ExprParser(toks[3:], self.variables)
            e = p.parse_statement_expr()
            return ('assign', name, e, ln)
        if in_rule:
            tk = toks
            if toks[0].u == 'OUTLAYER':
                tk = toks[1:]
            p = ExprParser(tk, self.variables)
            e = p.parse_statement_expr()
            return ('out', e, ln)
        raise ParseError('unrecognized statement: %s' % ' '.join(t.v for t in toks[:8]))


def preprocess_hash(text):
    """Convert '#DEFINE', '#IFDEF' lines into marker tokens that the line parser
    recognizes.  We do this by handling them before tokenization."""
    return text


class Deck:
    def __init__(self, path):
        raw = open(path, encoding='latin-1').read()
        self.raw = raw
        self.parser = DeckParser(raw)
        # handle preprocessor in a custom pass
        self.stmts = self._parse_with_preproc(self.parser)
        self.errors = self.parser.errors
        self.macros = self.parser.macros
        self.variables = self.parser.variables

    def _parse_with_preproc(self, p):
        text = p.text
        # Blank out DMACRO blocks holding device property programs ("[ ... ]"):
        # they are not layer operations. Their names are kept in prop_macros.
        p.prop_macros = set()
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            m = re.match(r'\s*DMACRO\s+(\w+)', lines[i])
            if m:
                j = i + 1
                while j < len(lines) and lines[j].strip() != '}':
                    j += 1
                body = '\n'.join(lines[i + 1:j])
                if '[' in body:
                    p.prop_macros.add(m.group(1).upper())
                    for k in range(i, min(j + 1, len(lines))):
                        lines[k] = ''
                i = j + 1
                continue
            i += 1
        text = '\n'.join(lines)
        # Replace preprocessor lines with sentinel words
        out_lines = []
        for line in text.split('\n'):
            s = line.strip()
            m = re.match(r'#(DEFINE|IFDEF|IFNDEF|ELSE|ENDIF|UNDEFINE)\b(.*)$', s, re.I)
            if m:
                kw = m.group(1).upper()
                rest = m.group(2).split()
                out_lines.append('__PP_%s %s' % (kw, ' '.join('"%s"' % r for r in rest)))
            else:
                out_lines.append(line)
        p.text = '\n'.join(out_lines)

        def _preproc(ln, toks):
            t0 = toks[0]
            if t0.t == 'word' and t0.v.startswith('__PP_'):
                kw = t0.v[5:]
                args = [t.v.strip('"') for t in toks[1:]]
                if kw == 'DEFINE':
                    return ('define', args[0], args[1] if len(args) > 1 else '')
                if kw in ('IFDEF', 'IFNDEF'):
                    return ('ifdef', args[0], args[1] if len(args) > 1 else None, kw == 'IFNDEF')
                if kw == 'ELSE':
                    return ('else',)
                if kw == 'ENDIF':
                    return ('endif',)
                return ('other',)
            return None

        p._preproc = _preproc
        return p.parse()


def walk_stmts(stmts, fn, path=()):
    for s in stmts:
        fn(s, path)
        if s[0] == 'ifdef':
            walk_stmts(s[4], fn, path + ((s[1], s[2], s[3], True),))
            walk_stmts(s[5], fn, path + ((s[1], s[2], s[3], False),))
        elif s[0] == 'rule':
            walk_stmts(s[3], fn, path + (('rule', s[1]),))


if __name__ == '__main__':
    d = Deck(sys.argv[1])
    for e in d.errors:
        print('ERROR', e)
    cnt = {}

    def f(s, p):
        cnt[s[0]] = cnt.get(s[0], 0) + 1

    walk_stmts(d.stmts, f)
    print(cnt)
