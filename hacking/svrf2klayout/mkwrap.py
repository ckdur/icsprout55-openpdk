"""KLayout macro: place all top-level cells of $gds in a grid into cell WRAP; write $out"""
import pya
ly = pya.Layout(); ly.read(gds)
tops = [c for c in ly.top_cells()]
wrap = ly.create_cell("WRAP")
x = 0.0; y = 0.0; rowh = 0.0
maxw = float(width) if 'width' in globals() else 2000.0
sp = 30.0
for c in sorted(tops, key=lambda c: c.name):
    bb = c.dbbox()
    if bb.empty(): continue
    if x + bb.width() > maxw:
        x = 0.0; y += rowh + sp; rowh = 0.0
    wrap.insert(pya.DCellInstArray(c.cell_index(), pya.DTrans(pya.DVector(x - bb.left, y - bb.bottom))))
    x += bb.width() + sp; rowh = max(rowh, bb.height())
ly.write(out)
print("cells", len(tops))
