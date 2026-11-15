# KLayout deep mode: Edges#inside_part / #outside_part vs. the boolean operators.
#   klayout -b -r tests/deep_edge_parts.rb        (exit 1 if the runtime formulas differ from flat)
#
# A box in a child cell, instantiated inside / on the boundary of / across / outside a polygon that
# exists in the top cell only. With KLayout 0.30.12, deep inside_part returns nothing and
# outside_part every edge for the instances that are covered; flat and the boolean forms
# (e & b) - b.edges / (e - b) + (e & b.edges) used by svrf_runtime.rb (sv_ein / sv_eout) are right.

ly = RBA::Layout::new
ly.dbu = 0.001
top = ly.create_cell("TOP")
c = ly.create_cell("C")
l1 = ly.layer(1, 0)
l2 = ly.layer(2, 0)
c.shapes(l1).insert(RBA::Box::new(0, 0, 2000, 380))
# inside touching b's left edge, outside touching it, straddling, inside, outside
[[0, 0], [-2000, 10000], [-1000, 20000], [5000, 30000], [-9000, 40000]].each do |x, y|
  top.insert(RBA::CellInstArray::new(c.cell_index, RBA::Trans::new(x, y)))
end
top.shapes(l2).insert(RBA::Box::new(0, -5000, 60000, 80000))

def flat_strs(e)
  e = e.dup
  e.flatten if e.respond_to?(:flatten)
  e.merged.each.collect(&:to_s).sort
end

res = {}
[false, true].each do |deep|
  dss = deep ? RBA::DeepShapeStore::new : nil
  a = deep ? RBA::Region::new(top.begin_shapes_rec(l1), dss) : RBA::Region::new(top.begin_shapes_rec(l1))
  b = deep ? RBA::Region::new(top.begin_shapes_rec(l2), dss) : RBA::Region::new(top.begin_shapes_rec(l2))
  e = a.edges
  res[deep] = {
    "inside_part" => flat_strs(e.inside_part(b)),
    "outside_part" => flat_strs(e.outside_part(b)),
    "ein" => flat_strs((e & b) - b.edges),
    "eout" => flat_strs((e - b) + (e & b.edges)),
  }
end

ref_in = res[false]["inside_part"]
ref_out = res[false]["outside_part"]
ok = true
[false, true].each do |deep|
  m = deep ? "deep" : "flat"
  r = res[deep]
  puts "#{m}: inside_part #{r['inside_part'].size} outside_part #{r['outside_part'].size} " \
       "ein #{r['ein'].size} eout #{r['eout'].size} (flat reference #{ref_in.size} / #{ref_out.size})"
  ok &&= (r["ein"] == ref_in && r["eout"] == ref_out)
end
bug = res[true]["inside_part"] != ref_in
puts "deep inside_part / outside_part #{bug ? 'still differ from flat (KLayout bug present)' : 'agree with flat'}"
puts(ok ? "runtime formulas: OK" : "runtime formulas: MISMATCH")
exit(ok ? 0 : 1)
