"""KLayout macro: replace cells of $gds by same-named cells from $lib; write $out.
(used to re-stream a design with the *_M2.gds standard cell variant)"""
import pya
ly = pya.Layout(); ly.read(gds)
lib = pya.Layout(); lib.read(lib_gds)
n = 0
for c in list(ly.each_cell()):
    lc = lib.cell(c.name)
    if lc is None or c.name == top:
        continue
    c.clear()
    c.copy_tree(lc)
    n += 1
ly.write(out)
print("replaced", n)
