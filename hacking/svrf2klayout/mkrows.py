"""KLayout macro: one LVS test row per cell: top cell T_<cell> = tap + cell + tap.
  -rd lib_gds=... -rd lef=... -rd lib_cdl=... -rd tap=FILLTAPH7R -rd out=rows.gds -rd cdl_out=rows.cdl
  [-rd only=regex]"""
import re
import pya

lef_txt = open(lef).read()
sizes = {}
for m in re.finditer(r'MACRO\s+(\S+)(.*?)END\s+\1', lef_txt, re.S):
    s = re.search(r'SIZE\s+([\d.]+)\s+BY\s+([\d.]+)', m.group(2))
    if s:
        sizes[m.group(1)] = (float(s.group(1)), float(s.group(2)))
pins = {}
for line in open(lib_cdl, encoding='latin-1'):
    m = re.match(r'\s*\.subckt\s+(\S+)(.*)', line, re.I)
    if m and m.group(1) not in pins:
        pins[m.group(1)] = [p for p in m.group(2).split() if '=' not in p]
lib = pya.Layout(); lib.read(lib_gds)
ly = pya.Layout(); ly.dbu = lib.dbu
rx = re.compile(only) if 'only' in globals() else None
cdl = []
names = []
for n in sorted(sizes):
    if n == tap or n not in pins or lib.cell(n) is None:
        continue
    if rx and not rx.search(n):
        continue
    top = ly.create_cell("T_" + n)
    names.append(n)
    x = 0.0
    ports = []
    lines = []
    for i, cn in enumerate([tap, n, tap]):
        lc = lib.cell(cn)
        c = ly.cell(cn)
        if c is None:
            c = ly.create_cell(cn)
            c.copy_tree(lc)
        top.insert(pya.DCellInstArray(c.cell_index(), pya.DTrans(pya.DVector(x, 0))))
        nets = []
        for p in pins[cn]:
            if p in ('VDD', 'VSS', 'VNW', 'VPW'):
                nets.append({'VNW': 'VDD', 'VPW': 'VSS'}.get(p, p))
                continue
            nets.append(p)
            done = False
            for li in lib.layer_indexes():
                info = lib.get_info(li)
                if info.layer not in (81, 82):
                    continue
                for s in lc.shapes(li).each():
                    if s.is_text() and s.text.string == p and not done:
                        t = s.dtext
                        top.shapes(ly.layer(info.layer, 6)).insert(pya.DText(p, pya.DTrans(pya.DVector(t.x + x, t.y))))
                        done = True
            if done:
                ports.append(p)
        if i == 0:
            for li in lib.layer_indexes():
                info = lib.get_info(li)
                if info.layer == 81 and info.datatype == 6:
                    for s in lc.shapes(li).each():
                        if s.is_text() and s.text.string in ('VDD', 'VSS'):
                            t = s.dtext
                            top.shapes(ly.layer(81, 6)).insert(pya.DText(s.text.string, pya.DTrans(pya.DVector(t.x, t.y))))
        if cn != tap:  # the tap cell has no devices (empty subckt)
            lines.append('XI%d %s %s' % (i, ' '.join(nets), cn))
        x += sizes[cn][0]
    cdl.append('.SUBCKT T_%s VDD VSS %s' % (n, ' '.join(ports)))
    cdl += lines
    cdl.append('.ENDS')
ly.write(out)
with open(cdl_out, 'w') as f:
    f.write(open(lib_cdl, encoding='latin-1').read())
    f.write('\n' + '\n'.join(cdl) + '\n')
with open(cdl_out + '.cells', 'w') as f:
    f.write('\n'.join(names) + '\n')
print("tops", len(names))
