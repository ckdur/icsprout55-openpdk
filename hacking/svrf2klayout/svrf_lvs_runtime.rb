# ============================================================================
# SVRF LVS runtime for KLayout (used together with svrf_runtime.rb)
#
# Implements Calibre "DEVICE" statements with a generic device extractor:
# every polygon of the seed layer becomes a device; pins are found from the
# pin layer shapes touching the seed shape (or covering it for well pins).
# ============================================================================

$sv_devices = {}      # key -> spec
$sv_dev_order = []
$sv_attach = []
$sv_filters = []

def sv_filter(type, model, mode)
  $sv_filters << [type, model, mode]
end
$sv_custom_classes = {}   # name -> [kind, nterm]  (for the SPICE reader)

WELL_PIN_RE = /well|^dnw$|pnp_col|bulk|mom_nw|mom_pw|psub/i

def sv_attach(text_specs, target)
  $sv_attach << [text_specs, target]
end

# kind of device class from the Calibre element type
def sv_dev_kind(type, pins)
  t = type.upcase
  names = pins.collect { |l, p| p.to_s.upcase }
  return :mos if t =~ /^M[NPD]?$/
  return :diode if t == "D"
  return :bjt if t == "Q"
  return :res3 if names.include?("SUB") && t =~ /^RE_/
  return :res if t =~ /^RE_/
  return :cap3 if names.size >= 3
  :cap
end

def sv_device(type, model, seed, pins, macro)
  kind = sv_dev_kind(type, pins)
  cname = model || type
  sig = pins.collect { |l, p| (l.upcase == seed.upcase ? "@SEED" : l.upcase) + ":" + p.to_s.upcase }.join(",")
  key = [type.upcase, cname, sig].join("|")
  if $sv_devices[key]
    $sv_devices[key][:seeds] << seed unless $sv_devices[key][:seeds].include?(seed)
  else
    $sv_devices[key] = { :type => type, :name => cname, :kind => kind, :seeds => [seed], :pins => pins,
                         :macro => macro, :seed0 => seed }
    $sv_dev_order << key
  end
  if kind == :res || kind == :res3 || kind == :cap || kind == :cap3
    $sv_custom_classes[cname.upcase] = [kind, pins.size]
  end
end

def sv_make_class(kind, name)
  c = case kind
      when :mos then RBA::DeviceClassMOS4Transistor::new
      when :diode then RBA::DeviceClassDiode::new
      when :bjt then RBA::DeviceClassBJT3Transistor::new
      when :res then RBA::DeviceClassResistor::new
      when :res3 then RBA::DeviceClassResistorWithBulk::new
      when :cap then RBA::DeviceClassCapacitor::new
      when :cap3 then RBA::DeviceClassCapacitorWithBulk::new
      end
  c.name = name
  c
end

# terminal name of the KLayout class for a Calibre pin name
def sv_term_name(kind, pin, index)
  p = pin.to_s.upcase
  case kind
  when :mos
    return p if %w(S D G B).include?(p)
    return %w(G S D B)[index]
  when :diode
    return "A" if p == "POS" || p == "P" || p == "A"
    return "C"
  when :bjt
    return p if %w(C B E).include?(p)
    return %w(C B E)[index]
  when :res, :res3
    return "A" if p == "POS"
    return "B" if p == "NEG"
    return "W"
  when :cap, :cap3
    return "A" if p == "POS" || index == 0
    return "B" if p == "NEG" || index == 1
    return "W"
  end
end

class SvDeviceExtractor < RBA::GenericDeviceExtractor

  # pins: array of [layer_key, pin_name, mode]  mode: :seed, :adjacent, :cover
  def initialize(name, kind, pins, macro)
    @kind = kind
    @pins = pins
    @macro = macro.to_s.upcase
    @lkeys = ["SEED"]
    pins.each { |lk, pn, mode| @lkeys << lk unless mode == :seed || @lkeys.include?(lk) }
    create
    self.name = name
  end

  def layer_keys
    @lkeys
  end

  def setup
    @lkeys.each { |k| define_layer(k, k) }
    c = case @kind
        when :mos then RBA::DeviceClassMOS4Transistor::new
        when :diode then RBA::DeviceClassDiode::new
        when :bjt then RBA::DeviceClassBJT3Transistor::new
        when :res then RBA::DeviceClassResistor::new
        when :res3 then RBA::DeviceClassResistorWithBulk::new
        when :cap then RBA::DeviceClassCapacitor::new
        when :cap3 then RBA::DeviceClassCapacitorWithBulk::new
        end
    c.name = self.name
    register_device_class(c)
  end

  def get_connectivity(layout, layers)
    conn = RBA::Connectivity::new
    conn.connect(layers[0], layers[0])
    @pins.each do |lk, pn, mode|
      next unless mode == :adjacent
      conn.connect(layers[0], layers[@lkeys.index(lk)])
    end
    conn
  end

  def extract_devices(lg)
    seeds = lg[0].merged
    dbu = sdbu
    seeds.each do |sp|
      sr = RBA::Region::new(sp)
      # candidates per adjacent layer
      cands = {}
      @pins.each do |lk, pn, mode|
        next unless mode == :adjacent
        next if cands[lk]
        r = lg[@lkeys.index(lk)].merged.interacting(sr)
        # require edge contact (not only a corner)
        polys = []
        se = sr.edges
        r.each do |p|
          co = (RBA::Region::new(p).edges & se).length
          ov = (RBA::Region::new(p) & sr).area
          polys << [p, co] if co > 0 || ov > 0
        end
        polys.sort_by! { |p, co| [p.bbox.left, p.bbox.bottom] }
        cands[lk] = polys
      end
      used = Hash.new(0)
      terms = []
      ok = true
      @pins.each_with_index do |(lk, pn, mode), i|
        if mode == :seed
          terms << [i, 0, sp]
        elsif mode == :cover
          terms << [i, @lkeys.index(lk), sp]
        else
          c = cands[lk]
          if c.empty?
            ok = false
            break
          end
          k = [used[lk], c.size - 1].min
          used[lk] += 1
          terms << [i, @lkeys.index(lk), c[k][0]]
        end
      end
      next unless ok
      dev = create_device
      area = sp.area * dbu * dbu
      perim = sp.perimeter * dbu
      # coincident perimeter with the first adjacent layer
      pco = 0.0
      first_adj = @pins.find { |lk, pn, mode| mode == :adjacent }
      if first_adj
        pco = cands[first_adj[0]].inject(0) { |s, pc| s + pc[1] } * dbu
      end
      case @kind
      when :mos
        w = (@macro == "MOS_ESD_LVS") ? pco : pco / 2.0
        w = perim / 4.0 if w <= 0
        dev.set_parameter("W", w)
        dev.set_parameter("L", area / w)
      when :diode
        dev.set_parameter("A", area)
        dev.set_parameter("P", perim)
      when :bjt
        dev.set_parameter("AE", area)
        dev.set_parameter("PE", perim)
      when :res, :res3
        w = pco / 2.0
        w = perim / 4.0 if w <= 0
        l = area / w
        dev.set_parameter("W", w)
        dev.set_parameter("L", l)
        dev.set_parameter("R", l / w)
        dev.set_parameter("A", area)
        dev.set_parameter("P", perim)
      when :cap, :cap3
        dev.set_parameter("A", area)
        dev.set_parameter("P", perim)
        dev.set_parameter("C", area)
      end
      cls = dev.device_class
      terms.each do |i, li, poly|
        tn = sv_term_name_local(@pins[i][1], i)
        tid = cls.terminal_id(tn)
        define_terminal(dev, tid, li, poly)
      end
    end
  end

  def sv_term_name_local(pin, index)
    p = pin.to_s.upcase
    case @kind
    when :mos
      return p if %w(S D G B).include?(p)
      return %w(G S D B)[index]
    when :diode
      return (p == "POS" || p == "P" || p == "A") ? "A" : "C"
    when :bjt
      return p if %w(C B E).include?(p)
      return %w(C B E)[index]
    when :res, :res3
      return "A" if p == "POS"
      return "B" if p == "NEG"
      return "W"
    else
      return "A" if p == "POS" || index == 0
      return "B" if p == "NEG" || index == 1
      return "W"
    end
  end
end

# SPICE reader which understands CDL style netlists
class SvSpiceReader < RBA::NetlistSpiceReaderDelegate

  def initialize(custom)
    @custom = custom
  end

  def start(netlist)
    @nl = netlist
  end

  def wants_subcircuit(name)
    @custom.has_key?(name.upcase)
  end

  def control_statement(line)
    false
  end

  def parse_element(s, element)
    # remove CDL "/" separators and $ comments/props
    s = s.gsub(/\s\/\s/, " ").gsub(/\$\S*=\S+/, "").gsub(/\$\[[^\]]*\]/, "").gsub(/\$[A-Za-z_.]+/, "")
    super(s, element)
  end

  def element(circuit, el, name, model, value, nets, params)
    if el == "X" && @custom.has_key?(model.upcase)
      kind, nterm = @custom[model.upcase]
      cls = circuit.netlist.device_class_by_name(model) rescue nil
      if cls.nil?
        cls = case kind
              when :res then RBA::DeviceClassResistor::new
              when :res3 then RBA::DeviceClassResistorWithBulk::new
              when :cap then RBA::DeviceClassCapacitor::new
              else RBA::DeviceClassCapacitorWithBulk::new
              end
        cls.name = model
        circuit.netlist.add(cls)
      end
      dev = circuit.create_device(cls, name)
      tn = (kind == :res || kind == :res3) ? %w(A B W) : %w(A B W)
      nets.each_with_index do |n, i|
        break if i >= tn.size
        next unless cls.has_terminal?(tn[i])
        dev.connect_terminal(tn[i], n)
      end
      w = (params["W"] || 0.0) * 1e6
      l = (params["L"] || 0.0) * 1e6
      if kind == :res || kind == :res3
        dev.set_parameter("W", w)
        dev.set_parameter("L", l)
        dev.set_parameter("R", w > 0 ? l / w : 0.0)
      end
      m = params["M"] || params["MR"]
      return true
    end
    if el == "D"
      # CDL diodes: AREA / PJ
      ok = super(circuit, el, name, model, value, nets, params)
      return ok
    end
    super(circuit, el, name, model, value, nets, params)
  end
end

def sv_lvs_extract
  g = $sv_G
  # Evaluate all layers first: derived layers must exist before the first
  # connect statement is issued.
  names = []
  $sv_connects.each { |layers, via| names += layers; names << via if via }
  $sv_attach.each { |specs, target| names << target }
  $sv_devices.each { |k, spec| names += spec[:seeds]; spec[:pins].each { |l, p| names << l } }
  names.uniq.each do |n|
    begin
      sv_p(g[n])
    rescue => ex
    end
  end
  # connectivity
  n_ok = 0
  $sv_connects.each do |layers, via|
    begin
      ls = layers.collect { |n| sv_p(g[n]) }
      if via
        v = sv_p(g[via])
        ls.each { |l| connect(l, v) }
      else
        (1...ls.size).each { |i| connect(ls[0], ls[i]) }
      end
      n_ok += 1
    rescue => ex
      log("SVRF LVS: skipping CONNECT #{layers.join(' ')}#{via ? ' BY ' + via : ''}: #{ex}")
    end
  end
  $sv_netter_ready = true
  # labels
  $sv_attach.each do |specs, target|
    begin
      t = sv_p(g[target])
      specs.each do |l, d|
        connect(t, labels(l, d))
      end
    rescue => ex
      log("SVRF LVS: skipping ATTACH to #{target}: #{ex}")
    end
  end
  # devices
  $sv_dev_order.each do |key|
    spec = $sv_devices[key]
    begin
      seeds = spec[:seeds].collect { |s| sv_p(g[s]) }
      seed = seeds[0]
      if seeds.size > 1
        seeds[1..-1].each { |s| seed = seed | s }
        seeds.each { |s| connect(seed, s) }
      end
      next if seed.is_empty?
      counts = Hash.new(0)
      spec[:pins].each { |l, p| counts[l.upcase] += 1 }
      pins = []
      layers = { "SEED" => seed }
      spec[:pins].each do |l, p|
        lu = l.upcase
        if spec[:seeds].collect { |s| s.upcase }.include?(lu)
          pins << ["SEED", p, :seed]
        else
          mode = (counts[lu] == 1 && lu =~ WELL_PIN_RE) ? :cover : :adjacent
          pins << [lu, p, mode]
          layers[lu] ||= sv_p(g[l])
        end
      end
      ex = SvDeviceExtractor::new(spec[:name], spec[:kind], pins, spec[:macro])
      extract_devices(ex, layers)
    rescue => e
      log("SVRF LVS: skipping DEVICE #{spec[:type]}(#{spec[:name]}): #{e}")
    end
  end
end


# ---------------------------------------------------------------------------
# LVS REDUCE SPLIT GATES: parallel series stacks of MOS devices with the same
# gate nets (in the same order) between the same end nets are merged into a
# single stack (widths are added).
# ---------------------------------------------------------------------------
def sv_reduce_split_gates(nl)
  nmerged = 0
  nl.each_circuit do |c|
    changed = true
    while changed
      changed = false
      # internal stack nodes: nets with exactly two MOS S/D terminals
      inner = {}
      c.each_net do |n|
        next unless n.pin_count == 0 && n.subcircuit_pin_count == 0 && n.terminal_count == 2
        ok = true
        n.each_terminal do |t|
          cls = t.device.device_class
          ok = false unless cls.is_a?(RBA::DeviceClassMOS3Transistor)
          tn = cls.terminal_definition(t.terminal_id).name
          ok = false unless tn == "S" || tn == "D"
        end
        inner[n.cluster_id] = n if ok
      end
      next if inner.empty?
      sd = lambda do |d|
        cls = d.device_class
        [d.net_for_terminal(cls.terminal_id("S")), d.net_for_terminal(cls.terminal_id("D"))]
      end
      # build chains starting at devices having one non-inner end
      visited = {}
      chains = {}
      c.each_device do |d0|
        next unless d0.device_class.is_a?(RBA::DeviceClassMOS3Transistor)
        next if visited[d0.id]
        a, b = sd.call(d0)
        next if a.nil? || b.nil?
        ia = inner[a.cluster_id]
        ib = inner[b.cluster_id]
        next if ia && ib          # middle of a chain
        next if !ia && !ib        # no stack
        start = ia ? b : a
        devs = [d0]
        cur = ia ? a : b
        prev = d0
        valid = true
        while inner[cur.cluster_id]
          nxt = nil
          cur.each_terminal { |t| nxt = t.device if t.device.id != prev.id }
          if nxt.nil? || nxt.device_class.id != d0.device_class.id
            valid = false
            break
          end
          x, y = sd.call(nxt)
          devs << nxt
          prev = nxt
          cur = (x.cluster_id == cur.cluster_id) ? y : x
          break if devs.size > 64
        end
        next unless valid
        stop = cur
        devs.each { |d| visited[d.id] = true }
        cls = d0.device_class
        gid = cls.terminal_id("G")
        bid = cls.has_terminal?("B") ? cls.terminal_id("B") : nil
        gates = devs.collect { |d| g = d.net_for_terminal(gid); [g ? g.cluster_id : -1, (d.parameter("L") * 1e4).round] }
        if start.cluster_id > stop.cluster_id
          start, stop = stop, start
          devs = devs.reverse
          gates = gates.reverse
        elsif start.cluster_id == stop.cluster_id
          next
        end
        bn = bid ? devs[0].net_for_terminal(bid) : nil
        key = [cls.id, start.cluster_id, stop.cluster_id, bn ? bn.cluster_id : -1, gates]
        (chains[key] ||= []) << devs
      end
      chains.each do |key, list|
        next if list.size < 2
        keep = list[0]
        list[1..-1].each do |other|
          other.each_with_index do |d, i|
            keep[i].set_parameter("W", keep[i].parameter("W") + d.parameter("W"))
            c.remove_device(d)
          end
          nmerged += 1
        end
        changed = true
      end
      c.purge_nets if changed
    end
  end
  nmerged
end
