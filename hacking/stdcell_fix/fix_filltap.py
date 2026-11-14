#!/usr/bin/env python3
"""Hand fix of the 7-track tap cell FILLTAPH7R (legalize.py cannot: its
implant islands are narrower than the implant width rules it models).

The tap has an opposite implant island under each pickup: PP around the P+
pickup in the NP band (substrate side), NP around the N+ pickup in the PP band
(well side). They meet corner to corner at the well edge (y = 0.615, the row
contract). Vendor findings and fix:

  PP_A_1    P+ island 0.20 x 0.51 = 0.102 um2 (>= 0.12). It cannot be taller
            (well edge above; the island of a tap in the mirrored row below
            needs PP_S_1 0.18 across the rail) and in a 0.4 um cell it cannot be
            wider: a neighbour gate is as close as 0.2 to its cell side and
            PP_S_5 / NP_EX_1 want 0.30 between the island and an NMOS gate
            (PP_EX_1 for the N+ island and PMOS gates; the 0.24 wide islands of
            the first fix violated them next to ~240 of the usable cells, found by
            testing/abut_check.py). So the cell grows to two sites (0.8 um),
            the islands are 0.24 x 0.51 / 0.24 x 0.68, 0.28 from either side.
  ACT_S_8   P+ pickup AA 0.12 from NW (>= 0.15): AA top 0.495 -> 0.450, the
            contacts 0.02 lower, AA 0.03 beyond the contacts in x (CT_EN_2b)
  ACT_EN_1  N+ AA enclosed 0.12 by NW (>= 0.15): AA bottom 0.735 -> 0.765

Growing: everything crossing the cell (boundary, rails, NW, implant bands) is
stretched at the centre, the pickups, contacts and the M1 between the rails
move to the new centre. The LEF macro (SIZE 0.8) comes from lef_from_gds.py.
Usage: fix_filltap.py <in.gds> <out.gds> [cell]   (both GDS views)
"""
import sys
import klayout.db as db

AA, CT, NP, PP, M1, NW, BND = (2, 1), (72, 1), (52, 1), (53, 1), (81, 1), (9, 1), (351, 12)
W0, GROW = 400, 400          # vendor width, growth (one site)
XS = W0 // 2                 # stretch line
RAIL_LO, RAIL_HI = 80, 1320  # M1 rails: y below / above
BIG = 10 ** 6


def stretch(r):
    """Region r stretched by GROW at x = XS."""
    left = r & db.Region(db.Box(-BIG, -BIG, XS, BIG))
    right = (r & db.Region(db.Box(XS, -BIG, BIG, BIG))).moved(GROW, 0)
    bridge = db.Region()
    for p in (r & db.Region(db.Box(XS - 1, -BIG, XS + 1, BIG))).each():
        b = p.bbox()
        bridge.insert(db.Box(XS, b.bottom, XS + GROW, b.top))
    return (left + right + bridge).merged()


def fix(layout, cell):
    w = W0 + GROW
    mid = GROW // 2          # shift of the content to the new centre
    li = {k: layout.find_layer(*k) for k in (AA, CT, NP, PP, M1, NW, BND)}
    reg = {k: db.Region(cell.shapes(i)).merged() for k, i in li.items() if i is not None}
    # pickups: P+ (below the well edge), N+ (above)
    aa = db.Region()
    for p in reg[AA].each():
        b = p.bbox()
        aa.insert(db.Box(125, 130, 275, 450) if b.top <= 615 else db.Box(b.left, 765, b.right, b.top))
    ct = db.Region()
    for p in reg[CT].each():
        b = p.bbox()
        ct.insert(b.moved(0, -20) if b.top <= 615 else b)
    rails = db.Region(db.Box(-BIG, -BIG, BIG, RAIL_LO)) + db.Region(db.Box(-BIG, RAIL_HI, BIG, BIG))
    m1 = (stretch(reg[M1] & rails) + (reg[M1] - rails).moved(mid, 0)).merged()
    # implants: stretch the bands, then replace the old islands by centred ones
    pp_s, np_s = stretch(reg[PP]), stretch(reg[NP])
    lo_old = pp_s & db.Region(db.Box(0, 0, w, 615))
    hi_old = np_s & db.Region(db.Box(0, 615, w, 1400))
    lo_new = db.Region(db.Box(w // 2 - 120, 105, w // 2 + 120, 615))
    hi_new = db.Region(db.Box(w // 2 - 120, 615, w // 2 + 120, 1295))
    pp = ((pp_s - lo_old) + hi_old - hi_new + lo_new).merged()
    np_ = ((np_s - hi_old) + lo_old - lo_new + hi_new).merged()
    new = {AA: aa.moved(mid, 0), CT: ct.moved(mid, 0), M1: m1, PP: pp, NP: np_,
           NW: stretch(reg[NW]), BND: db.Region(db.Box(0, 0, w, 1400))}
    for k, r in new.items():
        cell.shapes(li[k]).clear(db.Shapes.SPolygons | db.Shapes.SBoxes | db.Shapes.SPaths)
        cell.shapes(li[k]).insert(r)
    # rail labels at the centre, the well / substrate labels stay at x = 0
    for i in layout.layer_indexes():
        for s in list(cell.shapes(i).each(db.Shapes.STexts)):
            t = s.text
            if t.x == XS:
                s.text = t.moved(mid, 0)


def main():
    src, dst = sys.argv[1:3]
    name = sys.argv[3] if len(sys.argv) > 3 else 'FILLTAPH7R'
    lay = db.Layout()
    lay.read(src)
    c = lay.cell(name)
    if c.child_cells():
        sys.exit(f'{name}: expected a flat cell')
    if db.Region(c.shapes(lay.find_layer(*BND))).bbox().width() != W0:
        sys.exit(f'{name}: expected the vendor cell ({W0} wide)')
    fix(lay, c)
    lay.write(dst)


if __name__ == '__main__':
    main()
