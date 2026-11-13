#!/usr/bin/env python3
"""Antenna test vehicle: one isolated structure per case, to settle the semantics of the
Calibre antenna runset (NET AREA RATIO, ACCUMULATE, diode allowance) by running Calibre and
the KLayout deck on the same layout.

Usage: mk_antenna_test.py out.gds  (writes out.gds and prints the cases as JSON)

Every case is a core NMOS (gate 0.06 x 0.5 um = 0.03 um2) whose poly goes to a contact pad;
the gate net is then built up with metal / vias of the given areas. Cases are 300 um apart.
"""

import json
import sys

import klayout.db as db

L = {'ACT': (2, 1), 'NP': (52, 1), 'PP': (53, 1), 'POLY': (41, 1), 'CT': (72, 1),
     'MET1': (81, 1), 'VIA1': (91, 1), 'MET2': (82, 1), 'VIA2': (92, 1), 'MET3': (83, 1),
     'DGOX': (27, 1), 'NW': (9, 1), 'VIA3': (93, 1), 'MET4': (84, 1), 'VIA4': (94, 1),
     'MET5': (85, 1), 'T4V2': (113, 1), 'T4M2': (103, 1), 'RV': (120, 1), 'RDL': (123, 1)}

GATE_W = 500     # nm (diffusion width)
GATE_L = 60


def nm(v):
    return int(round(v))


class Builder:
    def __init__(self):
        self.ly = db.Layout()
        self.ly.dbu = 0.001
        self.top = self.ly.create_cell('ANT')
        self.li = {k: self.ly.layer(*v) for k, v in L.items()}

    def box(self, layer, x1, y1, x2, y2):
        self.top.shapes(self.li[layer]).insert(db.Box(nm(x1), nm(y1), nm(x2), nm(y2)))

    def nmos(self, x, y, dgox=False):
        """gate at (x..x+60, y..y+500); returns the poly pad contact centre"""
        self.box('ACT', x - 300, y, x + GATE_L + 300, y + GATE_W)
        self.box('NP', x - 500, y - 200, x + GATE_L + 500, y + GATE_W + 200)
        self.box('POLY', x, y - 130, x + GATE_L, y + GATE_W + 300)
        self.box('POLY', x - 50, y + GATE_W + 300, x + GATE_L + 50, y + GATE_W + 460)
        if dgox:
            self.box('DGOX', x - 800, y - 600, x + GATE_L + 800, y + GATE_W + 900)
        cx, cy = x + GATE_L / 2, y + GATE_W + 380
        self.box('CT', cx - 45, cy - 45, cx + 45, cy + 45)
        return cx, cy

    def diode(self, x, y, area_um2):
        """n+ diffusion of the given area with a contact, returns the contact centre"""
        w = 1000.0 if area_um2 >= 0.5 else 300.0
        h = area_um2 * 1e6 / w
        self.box('ACT', x, y, x + w, y + h)
        self.box('NP', x - 200, y - 200, x + w + 200, y + h + 200)
        cx, cy = x + w / 2, y + min(300, h / 2)
        self.box('CT', cx - 45, cy - 45, cx + 45, cy + 45)
        return cx, cy

    def wire(self, layer, x, y, area_um2, width=1000):
        """metal strip of area_um2 starting at (x,y) going up, covering the point"""
        length = area_um2 * 1e6 / width
        self.box(layer, x - width / 2, y - 100, x + width / 2, y - 100 + length)
        return y - 100 + length

    def via(self, layer, x, y):
        self.box(layer, x - 45, y - 45, x + 45, y + 45)


def main(out):
    b = Builder()
    ga = GATE_L * GATE_W / 1e6  # 0.03 um2
    cases = []
    x0 = 0

    def place():
        nonlocal x0
        x0 += 300000
        return x0, 0

    # M1 ratio 6000 / 4000 without diode (AR_5_10_M1 > 5000)
    for r in (6000, 4000):
        x, y = place()
        cx, cy = b.nmos(x, y)
        b.wire('MET1', cx, cy, r * ga)
        cases.append(dict(name='m1_%d' % r, x=x, expect='AR_5_10_M1' if r > 5000 else None))
    # M1 ratio 6000 with a 0.5 um2 diode on the net (allowance 500*0.5 + 38000)
    x, y = place()
    cx, cy = b.nmos(x, y)
    top = b.wire('MET1', cx, cy, 6000 * ga)
    dx, dy = b.diode(x + 3000, cy - 300, 0.5)     # diode contact at the height of the poly contact
    b.box('MET1', cx - 500, cy - 100, dx + 500, dy + 100)
    cases.append(dict(name='m1_6000_diode', x=x, expect=None))
    # same with a 0.1 um2 diode and ratio 50000: limit 5000 + 38000 + 500*0.1 = 43050 -> flagged
    x, y = place()
    cx, cy = b.nmos(x, y)
    top = b.wire('MET1', cx, cy, 50000 * ga)
    dx, dy = b.diode(x + 3000, cy - 300, 0.1)
    b.box('MET1', cx - 500, cy - 100, dx + 500, dy + 100)
    cases.append(dict(name='m1_50000_diode', x=x, expect='AR_5_10_M1'))
    # accumulation: M1 ratio 3000 + M2 ratio 3000 -> 6000 at M2
    x, y = place()
    cx, cy = b.nmos(x, y)
    top = b.wire('MET1', cx, cy, 3000 * ga)
    b.via('VIA1', cx, top - 500)
    b.wire('MET2', cx, top - 500, 3000 * ga)
    cases.append(dict(name='acc_m1_3000_m2_3000', x=x, expect='AR_5_10_M2 if accumulated'))
    # accumulation per gate: gate A M1 4500, gate B M1 100, joined on M2 (ratio 1000 over 2 gates)
    x, y = place()
    ax, ay = b.nmos(x, y)
    atop = b.wire('MET1', ax, ay, 4500 * ga)
    bx, by = b.nmos(x + 20000, y)
    btop = b.wire('MET1', bx, by, 100 * ga)
    b.via('VIA1', ax, ay + 300)
    b.via('VIA1', bx, by + 300)
    m2 = 1000 * 2 * ga
    w = 1000
    b.box('MET2', ax - 500, ay, bx + 500, ay + 1000)
    extra = m2 - (bx - ax + 1000) * 1000 / 1e6
    b.wire('MET2', bx, ay + 1100, max(extra, 0.1))
    cases.append(dict(name='acc_per_gate', x=x, expect='gate A only if per gate'))
    # poly ratio 300 (AR_1 > 250) : poly strip 0.5 um wide
    x, y = place()
    b.box('ACT', x - 300, y, x + GATE_L + 300, y + GATE_W)
    b.box('NP', x - 500, y - 200, x + GATE_L + 500, y + GATE_W + 200)
    b.box('POLY', x, y - 130, x + GATE_L, y + GATE_W + 300)
    plen = (300 * ga - 0.06 * 0.93) / 0.5
    b.box('POLY', x - 220, y + GATE_W + 300, x + 280, y + GATE_W + 300 + plen * 1000)
    cases.append(dict(name='po_300', x=x, expect='AR_1'))
    # 1.8 V (DGOX) gate, M1 ratio 1500 (AR18_5_10_M1 > 1000)
    x, y = place()
    cx, cy = b.nmos(x, y, dgox=True)
    b.wire('MET1', cx, cy, 1500 * ga)
    cases.append(dict(name='m1_1500_dgox', x=x, expect='AR18_5_10_M1'))
    # poly perimeter: 0.06 x 100 um poly line -> AR_2 ratio 667 (> 500), AR_1 ratio 200 (< 250)
    x, y = place()
    b.box('ACT', x - 300, y, x + GATE_L + 300, y + GATE_W)
    b.box('NP', x - 500, y - 200, x + GATE_L + 500, y + GATE_W + 200)
    b.box('POLY', x, y - 130, x + GATE_L, y + GATE_W + 100000)
    cases.append(dict(name='po_perim', x=x, expect='AR_2'))
    # 7 x 7 contacts on the poly pad: CT ratio 13 (AR_3 > 10)
    x, y = place()
    b.box('ACT', x - 300, y, x + GATE_L + 300, y + GATE_W)
    b.box('NP', x - 500, y - 200, x + GATE_L + 500, y + GATE_W + 200)
    b.box('POLY', x, y - 130, x + GATE_L, y + GATE_W + 300)
    b.box('POLY', x - 1000, y + GATE_W + 300, x + 1500, y + GATE_W + 2800)
    for i in range(7):
        for j in range(7):
            b.via('CT', x - 700 + i * 300, y + GATE_W + 600 + j * 300)
    cases.append(dict(name='ct_49', x=x, expect='AR_3'))
    # via arrays on M1 -> M2: 9x9 VIA1 ratio 21.9 (AR_4 > 20), 15x15 VIA1 ratio 61 (AR_4, AR_6_9 > 50)
    for n in (9, 15):
        x, y = place()
        cx, cy = b.nmos(x, y)
        b.box('MET1', cx - 500, cy - 100, cx + 300 * n + 500, cy + 300 * n + 500)
        b.box('MET2', cx - 500, cy - 100, cx + 300 * n + 500, cy + 300 * n + 500)
        for i in range(n):
            for j in range(n):
                b.via('VIA1', cx + 200 + i * 300, cy + 200 + j * 300)
        cases.append(dict(name='via1_%dx%d' % (n, n), x=x, expect='AR_4_VIA1'))
    # full stack to RV / RDL: RV 3 x 3 um (AR_7_11_core ratio 300 > 200), RDL 10 x 10 um
    # (AR_8_12 perimeter 40 * 1.595 / 0.03 = 2127 > 1000)
    x, y = place()
    cx, cy = b.nmos(x, y)
    for lay in ('MET1', 'MET2', 'MET3', 'MET4', 'MET5'):
        b.box(lay, cx - 500, cy - 500, cx + 500, cy + 500)
    for v in ('VIA1', 'VIA2', 'VIA3', 'VIA4'):
        b.via(v, cx, cy)
    b.box('T4V2', cx - 180, cy - 180, cx + 180, cy + 180)
    b.box('T4M2', cx - 2500, cy - 2500, cx + 2500, cy + 2500)
    b.box('RV', cx - 1500, cy - 1500, cx + 1500, cy + 1500)
    b.box('RDL', cx - 5000, cy - 5000, cx + 5000, cy + 5000)
    cases.append(dict(name='stack_rdl', x=x, expect='AR_7_11_core AR_8_12'))
    b.ly.write(out)
    print(json.dumps(cases, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
