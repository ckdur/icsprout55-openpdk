"""KLayout macro: build an LVS test row.
  -rd lib_gds=...  -rd lef=...  -rd cells=A,B,C  -rd out=row.gds -rd cdl_out=row.cdl -rd lib_cdl=...
Places the cells abutted (widths from the LEF) in top cell TROW, labels the
rails on MET1 (81/6) and every signal pin (label text <inst>_<pin> on the
pin layer found in the cell), and writes the matching CDL."""
import re
import pya

lef_txt = open(lef).read()
sizes = {}
for m in re.finditer(r'MACRO\s+(\S+)(.*?)END\s+\1', lef_txt, re.S):
    s = re.search(r'SIZE\s+([\d.]+)\s+BY\s+([\d.]+)', m.group(2))
    if s:
        sizes[m.group(1)] = (float(s.group(1)), float(s.group(2)))

pins = {}
cur = None
for line in open(lib_cdl, encoding='latin-1'):
    m = re.match(r'\s*\.subckt\s+(\S+)(.*)', line, re.I)
    if m and m.group(1) not in pins:
        pins[m.group(1)] = [p for p in m.group(2).split() if '=' not in p]

lib = pya.Layout(); lib.read(lib_gds)
ly = pya.Layout(); ly.dbu = lib.dbu
top = ly.create_cell("TROW")
x = 0.0
names = cells.split(',')
l81t = ly.layer(81, 6)
cdl = ['.SUBCKT TROW VDD VSS']
ports = []
for i, n in enumerate(names):
    lc = lib.cell(n)
    c = ly.cell(n)
    if c is None:
        c = ly.create_cell(n)
        c.copy_tree(lc)
    top.insert(pya.DCellInstArray(c.cell_index(), pya.DTrans(pya.DVector(x, 0))))
    nets = []
    for p in pins[n]:
        if p in ('VDD', 'VSS', 'VNW', 'VPW'):
            nets.append({'VNW': 'VDD', 'VPW': 'VSS'}.get(p, p))
            continue
        net = 'I%d_%s' % (i, p)
        nets.append(net)
        # find the label of that pin in the cell and copy it to the top
        found = False
        for li in lc.layout().layer_indexes():
            for s in lc.shapes(li).each():
                if s.is_text() and s.text.string == p and not found:
                    info = lc.layout().get_info(li)
                    if info.layer in (81, 82):
                        tl = ly.layer(info.layer, 6)
                        t = s.dtext
                        top.shapes(tl).insert(pya.DText(net, pya.DTrans(pya.DVector(t.x + x, t.y))))
                        found = True
        if found:
            ports.append(net)
    cdl.append('XI%d %s %s' % (i, ' '.join(nets), n))
    x += sizes[n][0]
# rail labels: copy VDD/VSS label positions from first cell
lc = lib.cell(names[0])
for li in lc.layout().layer_indexes():
    info = lc.layout().get_info(li)
    if info.layer == 81 and info.datatype == 6:
        for s in lc.shapes(li).each():
            if s.is_text() and s.text.string in ('VDD', 'VSS'):
                t = s.dtext
                top.shapes(l81t).insert(pya.DText(s.text.string, pya.DTrans(pya.DVector(t.x, t.y))))
cdl[0] += ' ' + ' '.join(ports)
cdl.append('.ENDS')
ly.write(out)
with open(cdl_out, 'w') as f:
    f.write('\n'.join(cdl) + '\n')
    f.write(open(lib_cdl, encoding='latin-1').read())
print("row width", x, "ports", len(ports))
