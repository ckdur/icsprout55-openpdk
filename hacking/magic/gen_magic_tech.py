#!/usr/bin/env python3
"""Generate the Magic technology file for ICsprout 55 (icsprout55/libs.tech/magic/ics55.tech).

Usage:
  gen_magic_tech.py [--out ics55.tech] [--drc drc_section.txt]

Sources (nothing in the output is typed in by hand):
  * GDS layer numbers: the vendor Calibre LVS runset (LAYER MAP / LAYER statements).
  * Device recognition: the layer derivations of that runset (see DEVICES below, each
    entry names the Calibre derived layer it reproduces).
  * Sheet / via resistance and capacitance: the vendor StarRC ITF (typical corner) and the
    FasterCap 2D solutions of WP1 (generate_rcx_rules/solutions/TYP.csv).
  * DRC: the rule section produced by svrf2magic_drc.py from the expanded Calibre DRC deck
    (passed with --drc; without it the tech file has an empty DRC section).

Type model
  Device layers (diffusion, gates, taps, diodes, contacts, poly resistors) are Magic types on
  the active plane, derived from ACT / POLY / CT and the implant, oxide, Vt and marker layers
  exactly as the Calibre LVS deck derives its device seed layers. In addition every implant /
  oxide / Vt / marker layer that the LVS or DRC deck uses is kept literally as a type on a
  plane of its own, so GDS output reproduces it and the generated DRC rules can refer to it.
"""

import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
LVS_RUNSET = os.path.join(ROOT, 'icsprout55-pdk', 'pv', 'LVS', 'ICsprout_CalLVS_55LLULP1233_REV1_0_OS.lvs')
ITF_TYP = os.path.join(ROOT, 'hacking', 'decrypted_output', 'kItfTyp.txt')
CAP_CSV = os.path.join(ROOT, 'generate_rcx_rules', 'solutions', 'TYP.csv')
TECH_LEF = os.path.join(ROOT, 'icsprout55', 'libs.tech', 'librelane', 'N551P6M_ecos.lef')


def lef_width_spacing(path=TECH_LEF):
    """{LEF layer: (WIDTH, SPACING)} in um from the technology LEF."""
    out, name, w, sp = {}, None, None, None
    for line in open(path):
        t = line.split()
        if not t:
            continue
        if t[0] == 'LAYER' and len(t) == 2:
            name, w, sp = t[1], None, None
        elif t[0] == 'WIDTH' and name:
            w = float(t[1])
        elif t[0] == 'SPACING' and name and sp is None and len(t) == 3:
            sp = float(t[1])
        elif t[0] == 'END' and len(t) == 2 and t[1] == name:
            if w:
                out[name] = (w, sp)
            name = None
    return out

sys.path.insert(0, os.path.join(ROOT, 'generate_rcx_rules'))


# ------------------------------------------------------------------------------------------
# GDS layer numbers from the Calibre runset
# ------------------------------------------------------------------------------------------

def read_layer_map(path):
    """Returns {calibre_layer_name: [(layer, datatype), ...]} (datatype and texttype merged)."""
    num2gds = {}
    name2num = {}
    for line in open(path, encoding='latin-1'):
        m = re.match(r'\s*LAYER\s+MAP\s+(\d+)\s+(DATATYPE|TEXTTYPE)\s+(\d+)\s+(\d+)', line)
        if m:
            num2gds.setdefault(int(m.group(4)), set()).add((int(m.group(1)), int(m.group(3))))
            continue
        m = re.match(r'\s*LAYER\s+([A-Za-z]\w*)\s+((?:\d+\s*)+)$', line)
        if m and m.group(1).upper() != 'MAP':
            name2num.setdefault(m.group(1), [])
            name2num[m.group(1)] += [int(x) for x in m.group(2).split()]
    out = {}
    for name, nums in name2num.items():
        g = set()
        for n in nums:
            g |= num2gds.get(n, set())
        if g:
            out[name] = sorted(g)
    return out


def magic_gds(layer, datatype):
    """Magic (8.3) only accepts GDS layer / datatype numbers 0..255. The marker layers of this
    PDK above that are read and written under (layer - 256, datatype + 100), which no PDK layer
    uses; hacking/magic/magic_gds.py converts a GDS file into this numbering."""
    if layer > 255 or datatype > 255:
        return (layer - 256 if layer > 255 else layer, datatype + 100)
    return (layer, datatype)


# ------------------------------------------------------------------------------------------
# Process description (names are the Calibre layer names of the LVS runset)
# ------------------------------------------------------------------------------------------

# Marker / implant layers kept literally: (magic type, Calibre layer, display style).
# One plane each, named after the type.
MARKERS = [
    ('nimp',    'NP',       'nselect2'),
    ('pimp',    'PP',       'pselect2'),
    ('nvt1',    'NVT1',     'implant1'),
    ('pvt1',    'PVT1',     'implant2'),
    ('nvt3',    'NVT3',     'implant3'),
    ('pvt3',    'PVT3',     'implant4'),
    ('dgox',    'DGOX',     'hvndiff_mask'),
    ('tgox',    'TGOX',     'hvpdiff_mask'),
    ('sab',     'SAB',      'silicide_block'),
    ('hrp',     'HRP',      'poly_resist_stripes'),
    ('hrpblk',  'HRPBLK',   'poly_resist_stripes'),
    ('esd',     'ESD',      'implant1'),
    ('npd',     'NPD',      'implant2'),
    ('psubmk',  'PSUB',     'implant3'),
    ('diodemk', 'DIODE',    'implant4'),
    ('polyres', 'POLYres',  'poly_resist'),
    ('actres',  'ACTres',   'implant1'),
    ('odmk',    'OD',       'implant2'),
    ('udmk',    'UD',       'implant3'),
    ('ulldmk',  'ULLD',     'implant4'),
    ('sramall', 'SRAMALL',  'implant1'),
    ('bjtmk',   'BJT',      'implant2'),
    ('ldmosmk', 'LDMOS',    'implant3'),
    ('varammk', 'VARAM',    'implant4'),
    ('esdioe',  'ESDIOE',   'implant1'),
    ('esdiot',  'ESDIOT',   'implant2'),
    ('subckt',  'SUBCKTLVS', 'implant3'),
    ('nodrc',   'NODRC',    'check_paint'),
    ('lvsoff',  'NOLVS',    'check_paint'),
    ('ioarea',  'IO',       'comment'),
    ('corearea', 'CORE',    'comment'),
]

# Routing stack (Calibre default: 6 metals, 1 top metal).
# (magic type, plane, Calibre drawing layer, dummy, resistor marker, text layer, LEF name, style)
METALS = [
    ('m1', 'metal1', 'MET1', 'MET1dm', 'MET1res', 'MET1text', 'MET1', 'metal1'),
    ('m2', 'metal2', 'MET2', 'MET2dm', 'MET2res', 'MET2text', 'MET2', 'metal2'),
    ('m3', 'metal3', 'MET3', 'MET3dm', 'MET3res', 'MET3text', 'MET3', 'metal3'),
    ('m4', 'metal4', 'MET4', 'MET4dm', 'MET4res', 'MET4text', 'MET4', 'metal4'),
    ('m5', 'metal5', 'MET5', 'MET5dm', 'MET5res', 'MET5text', 'MET5', 'metal5'),
    ('m6', 'metal6', 'T4M2', 'T4M2dm', 'T4M2res', 'T4M2text', 'T4M2', 'metal6'),
    ('m7', 'metal7', 'RDL',  None,     None,      'RDLtext',  'RDL',  'metal7'),
]
# (magic type, Calibre layers, lower metal, upper metal, LEF name, ITF via, style)
VIAS = [
    ('via1', ['VIA1', 'VIA1bar'], 'm1', 'm2', 'VIA1', 'V1', 'via1'),
    ('via2', ['VIA2', 'VIA2bar'], 'm2', 'm3', 'VIA2', 'V2', 'via2'),
    ('via3', ['VIA3', 'VIA3bar'], 'm3', 'm4', 'VIA3', 'V3', 'via3'),
    ('via4', ['VIA4', 'VIA4bar'], 'm4', 'm5', 'VIA4', 'V4', 'via4'),
    ('via5', ['T4V2', 'T4V2bar'], 'm5', 'm6', 'T4V2', 'TV', 'via5'),
    ('via6', ['RV'],              'm6', 'm7', 'RV',   'RV', 'via6'),
]

# Active plane device layers. Each entry: magic type, conditions on the Calibre layers
# (AND of the listed layers, AND-NOT of the '!'-prefixed ones), contact type or None,
# style, comment with the Calibre layer it reproduces.
#
# Common building blocks (Calibre): gate = POLY AND ACT (not resistor poly),
# diffusion = ACT NOT POLY, nDif = AA AND NP, pDif = AA AND PP, nWell = NW NOT NW1res,
# thin oxide = NOT (DGOX OR TGOX), 3.3 V oxide (IO = TGOX_33) = TGOX.
# The IO option of the vendor deck is TGOX_33, so DGOX has no devices; DGOX gates are
# treated as core devices here (Calibre extracts nothing there).

RESPOLY = ['POLYres', 'HRPBLK']   # POLY touching either is resistor poly

# Calibre: resPOLY = PO AND ((POLYres NOT INTERACT SAB) OR (POLYres AND SAB) OR HRPBLK), i.e. a
# POLYres shape touching SAB is a resistor only inside SAB (the rest are its terminals), one
# not touching SAB is a silicided resistor. Magic's GDS input has no INTERACT; a POLYres
# region counts as "touching SAB" when it is within SAB_HALO (nm) of SAB.
SAB_HALO = 5000

# fets: (type, polarity, oxide, extra and, extra and-not, model, Calibre seed)
FETS = [
    ('nfet',      'n', 'core', [],       ['PSUB', 'NVT1', 'NVT3'], 'nm1p2_svt_lp', 'ncore_svt_gate'),
    ('nfetlvt',   'n', 'core', ['NVT1'], ['PSUB'],                 'nm1p2_lvt_lp', 'ncore_lvt_gate'),
    ('nfethvt',   'n', 'core', ['NVT3'], ['PSUB', 'NVT1'],         'nm1p2_hvt_lp', 'ncore_hvt_gate'),
    ('nfetnat',   'n', 'core', ['PSUB'], [],                       'nnat1p2_lp',   'ncore_nt_gate'),
    ('pfet',      'p', 'core', [],       ['PVT1', 'PVT3'],         'pm1p2_svt_lp', 'pcore_svt_gate'),
    ('pfetlvt',   'p', 'core', ['PVT1'], [],                       'pm1p2_lvt_lp', 'pcore_lvt_gate'),
    ('pfethvt',   'p', 'core', ['PVT3'], ['PVT1'],                 'pm1p2_hvt_lp', 'pcore_hvt_gate'),
    ('mvnfet',    'n', 'mv',   [],       ['PSUB'],                 'nm3p3_lp',     'nio2_gate'),
    ('mvnfetnat', 'n', 'mv',   ['PSUB'], [],                       'nnat3p3_lp',   'nio2_nt_gate'),
    ('mvpfet',    'p', 'mv',   [],       [],                       'pm3p3_lp',     'pio2_gate'),
]

# diffusions: (type, contact, polarity, well ('in' = inside NW, 'out'), oxide, and, and-not,
#              role, model, Calibre seed)
DIFFS = [
    # MOS source / drain
    ('ndiff',      'ndc',      'n', 'out', 'core', [], ['DIODE'], 'sd', None, 'nSD'),
    ('pdiff',      'pdc',      'p', 'in',  'core', [], ['DIODE'], 'sd', None, 'pSD'),
    ('mvndiff',    'mvndc',    'n', 'out', 'mv',   [], ['DIODE'], 'sd', None, 'nSD'),
    ('mvpdiff',    'mvpdc',    'p', 'in',  'mv',   [], ['DIODE'], 'sd', None, 'pSD'),
    # well / substrate taps
    ('nsd',        'nsc',      'n', 'in',  'core', [], [], 'ntap', None, 'nTap'),
    ('psd',        'psc',      'p', 'out', 'core', [], [], 'ptap', None, 'pTap'),
    ('mvnsd',      'mvnsc',    'n', 'in',  'mv',   [], [], 'ntap', None, 'nTap'),
    ('mvpsd',      'mvpsc',    'p', 'out', 'mv',   [], [], 'ptap', None, 'pTap'),
    # junction diodes (DIODE marker)
    ('ndiode',     'ndic',     'n', 'out', 'core', ['DIODE'], ['NVT1', 'NVT3', 'PSUB'], 'ndio',
     'dio_1p2_np_pw_lp', 'ndiocore_svt_diode'),
    ('ndiodelvt',  'ndiclvt',  'n', 'out', 'core', ['DIODE', 'NVT1'], ['PSUB'], 'ndio',
     'dio_1p2_np_pw_lvt_lp', 'ndiocore_lvt_diode'),
    ('ndiodehvt',  'ndichvt',  'n', 'out', 'core', ['DIODE', 'NVT3'], ['PSUB', 'NVT1'], 'ndio',
     'dio_1p2_np_pw_hvt_lp', 'ndiocore_hvt_diode'),
    ('pdiode',     'pdic',     'p', 'in',  'core', ['DIODE'], ['PVT1', 'PVT3', 'PSUB'], 'pdio',
     'dio_1p2_pp_nw_lp', 'pdiocore_svt_diode'),
    ('pdiodelvt',  'pdiclvt',  'p', 'in',  'core', ['DIODE', 'PVT1'], ['PSUB'], 'pdio',
     'dio_1p2_pp_nw_lvt_lp', 'pdiocore_lvt_diode'),
    ('pdiodehvt',  'pdichvt',  'p', 'in',  'core', ['DIODE', 'PVT3'], ['PSUB', 'PVT1'], 'pdio',
     'dio_1p2_pp_nw_hvt_lp', 'pdiocore_hvt_diode'),
    ('mvndiode',   'mvndic',   'n', 'out', 'mv',   ['DIODE'], ['PSUB'], 'ndio',
     'dio_3p3_np_pw_lp', 'ndioio2_diode'),
    ('mvpdiode',   'mvpdic',   'p', 'in',  'mv',   ['DIODE'], ['PSUB'], 'pdio',
     'dio_3p3_pp_nw_lp', 'pdioio2_diode'),
]

# poly resistors: (type, and, and-not, model, Calibre seed)
POLYRES = [
    ('rnpo',    ['POLYres', 'NP'],        ['sabhalo', 'HRPBLK'],    're_npo_2t',     'rnpo_2T'),
    ('rppo',    ['POLYres', 'PP'],        ['sabhalo', 'HRPBLK'],    're_ppo_2t',     'rppo_2T'),
    ('rnposab', ['POLYres', 'NP', 'SAB'], ['HRPBLK'],               're_npo_sab_2t', 'rnposab_2T'),
    ('rpposab', ['POLYres', 'PP', 'SAB'], ['HRP', 'HRPBLK'],        're_ppo_sab_2t', 'rpposab_2T'),
    ('rhrpo',   ['HRPBLK'],               [],                       're_hrpo_2t',    'rhrpo_2T'),
]

DIFF_STYLE = {'n': 'ndiffusion', 'p': 'pdiffusion'}
MVDIFF_STYLE = {'n': 'mvndiff', 'p': 'mvpdiff'}


# ------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------

class Out:
    def __init__(self):
        self.lines = []

    def __call__(self, s=''):
        self.lines.append(s)

    def text(self):
        return '\n'.join(self.lines) + '\n'


def diff_conds(pol, well, ox):
    a = ['ACT', 'NP' if pol == 'n' else 'PP']
    n = ['POLY']
    a.append('NW') if well == 'in' else n.append('NW')
    if ox == 'mv':
        a.append('TGOX')
    else:
        n.append('TGOX')
    return a, n


def gate_conds(pol, ox):
    a = ['ACT', 'POLY', 'NP' if pol == 'n' else 'PP']
    n = list(RESPOLY)
    a.append('NW') if pol == 'p' else n.append('NW')
    if ox == 'mv':
        a.append('TGOX')
    else:
        n.append('TGOX')
    return a, n


def cif_layer(out, mtype, ands, nots, comment=None, extra=(), gds=None):
    """Writes one cifinput layer. Layers Magic cannot read (see read_layer_map) can never be
    present: an AND with one drops the whole layer, an AND-NOT with one is dropped."""
    if gds is not None:
        if any(a not in gds for a in ands):
            out(' # %s: not read (needs %s, GDS layer > 255)' % (
                mtype, ','.join(a for a in ands if a not in gds)))
            out()
            return False
        nots = [n for n in nots if n in gds]
    if comment:
        out(' # %s' % comment)
    out(' layer %s %s' % (mtype, ands[0]))
    for a in ands[1:]:
        out('  and %s' % a)
    for n in nots:
        out('  and-not %s' % n)
    for e in extra:
        out('  ' + e)
    out()
    return True


# ------------------------------------------------------------------------------------------
# Parasitics from the ITF and the FasterCap solutions
# ------------------------------------------------------------------------------------------

def parasitics():
    """Returns dict with sheet resistances (mOhm/sq), via R (mOhm), and caps (aF)."""
    import itf
    st = itf.read_itf(ITF_TYP)
    res = {}
    for name, c in st.conductors.items():
        res[name] = c.rpsq * 1000.0
    vres = {name: v.rpv * 1000.0 for name, v in st.vias.items()}

    # FasterCap table: metal index 1..7 (M1..M5, TM, RDL), under / over = plane index (0 none
    # = substrate below). ctot, cc, cg in fF/um.
    rows = []
    for r in csv.DictReader(open(CAP_CSV)):
        try:
            rows.append(dict(m=int(r['metal']), u=int(r['under']), o=int(r['over']),
                             w=float(r['w_drawn']), s=float(r['s_drawn'] or 'inf'),
                             cc=float(r['cc'] or 0), cg=float(r['cg'] or 0),
                             ctot=float(r['ctot'] or 0)))
        except ValueError:
            continue
    caps = {}
    for m in range(1, 8):
        for u in range(0, m):
            sel = [r for r in rows if r['m'] == m and r['u'] == u and r['o'] == 0]
            if not sel:
                continue
            ws = sorted(set(r['w'] for r in sel))
            # isolated line (largest spacing) at the two smallest widths -> area + fringe
            iso = {}
            for w in ws:
                cand = [r for r in sel if r['w'] == w]
                rmax = max(cand, key=lambda r: r['s'])
                iso[w] = rmax
            if len(ws) >= 2:
                w0, w1 = ws[0], ws[-1]
                c0 = iso[w0]['cg'] + 2 * iso[w0]['cc']
                c1 = iso[w1]['cg'] + 2 * iso[w1]['cc']
                area = (c1 - c0) / (w1 - w0)
                perim = (c0 - area * w0) / 2.0
            else:
                area, perim = 0.0, 0.0
            # coupling vs spacing at minimum width: cc(s) = K / (s + off)
            wmin = ws[0]
            pts = sorted((r['s'], r['cc']) for r in sel if r['w'] == wmin and r['s'] != float('inf'))
            K = off = 0.0
            if len(pts) >= 2:
                (s0, c0), (s1, c1) = pts[0], pts[min(len(pts) - 1, 3)]
                # c0 (s0 + off) = c1 (s1 + off)
                if c0 != c1:
                    off = (c1 * s1 - c0 * s0) / (c0 - c1)
                    K = c0 * (s0 + off)
            caps[(m, u)] = dict(area=area * 1000.0, perim=perim * 1000.0,
                                side=K * 1000.0, off=max(off, 0.0))
    return res, vres, caps, st


# ------------------------------------------------------------------------------------------
# Generation
# ------------------------------------------------------------------------------------------

def generate(drc=None):
    """drc: a svrf2magic_drc.Translator (or None for no DRC rules)."""
    gds_all = read_layer_map(LVS_RUNSET)
    gds = {k: sorted(set(magic_gds(*p) for p in v)) for k, v in gds_all.items()}
    remapped = sorted(k for k, v in gds_all.items() if any(magic_gds(*p) != p for p in v))
    MARKERS_ = [m for m in MARKERS if m[1] in gds]
    o = Out()

    contact_of = {}
    for d in DIFFS:
        contact_of[d[0]] = d[1]

    all_fets = [f[0] for f in FETS]
    nfets = [f[0] for f in FETS if f[1] == 'n']
    pfets = [f[0] for f in FETS if f[1] == 'p']
    diffs = [d[0] for d in DIFFS]
    diffconts = [d[1] for d in DIFFS]
    polyres = [p[0] for p in POLYRES]

    o('#------------------------------------------------------------------------------')
    o('# Magic technology file for ICsprout 55LLULP 1P6M (icsprout55)')
    o('#')
    o('# GENERATED by hacking/magic/gen_magic_tech.py from the vendor Calibre LVS runset,')
    o('# the StarRC ITF and the Calibre DRC deck. Do not edit; change the generator.')
    o('#')
    o('# Internal units: lambda = 10 nm, GDS grid down to 1 nm.')
    o('# Metal stack: MET1-MET5, T4M2 (top metal), RDL; vias VIA1-VIA4, T4V2, RV.')
    o('#')
    o('# Magic only handles GDS layer / datatype numbers up to 255. The Calibre layers below')
    o('# are above that; this file reads them as (layer - 256, datatype + 100), e.g. NODRC')
    o('# 357/12 as 101/112. Vendor GDS has to be converted with hacking/magic/magic_gds.py')
    o('# for Magic to see them (SUBCKTLVS substrate cuts, NODRC, PSUB native devices, HRPBLK,')
    o('# CHIPBLK boundary, WELTXT / SUBTXT well labels); in an unconverted GDS they are')
    o('# ignored. They are never written (GDS output from Magic does not contain them).')
    line = '#  '
    for n in remapped:
        if len(line) + len(n) > 90:
            o(line)
            line = '#  '
        line += ' ' + n
    o(line)
    o('#------------------------------------------------------------------------------')
    o('tech')
    o('  format 35')
    o('  ics55')
    o('end')
    o()
    o('version')
    o('  version 1.0')
    o('  description "ICsprout 55LLULP 1P6M, generated from the vendor Calibre and StarRC decks"')
    o('  requires magic-8.3.400')
    o('end')
    o()

    # ---------------------------------------------------------------- planes
    o('planes')
    o('  dwell,dw')
    o('  well,w')
    o('  active,a')
    for mt in METALS:
        o('  %s' % mt[1])
    o('  block,b')
    o('  comment,c')
    for m in MARKERS_:
        o('  %s' % m[0] + 'pl')
    o('end')
    o()

    # ---------------------------------------------------------------- types
    o('types')
    o('  dwell dnwell,dnw')
    o('  dwell isosub')
    o('  well nwell,nw')
    o('  well rnwell,rnw')
    o('  well pwell,pw')
    o()
    for f in FETS:
        o('  active %s' % f[0])
    for d in DIFFS:
        o('  active %s' % d[0])
    for d in DIFFS:
        o('  active %s' % d[1])
    o('  active poly,p')
    o('  active pc,polycont')
    o(' -active polyfill')
    o(' -active difffill')
    for p in POLYRES:
        o('  active %s' % p[0])
    o()
    for mt in METALS:
        t, pl = mt[0], mt[1]
        o('  %s %s,metal%s' % (pl, t, t[1:]))
        if mt[4]:
            o('  %s r%s' % (pl, t))
        if mt[3]:
            o(' -%s %sfill' % (pl, t))
        o(' -%s obs%s' % (pl, t))
    for v in VIAS:
        lower_plane = [mt[1] for mt in METALS if mt[0] == v[2]][0]
        o('  %s %s' % (lower_plane, v[0]))
    o()
    o('  block glass')
    o('  comment comment')
    o('  comment prbndry,boundary')
    for m in MARKERS_:
        o('  %spl %s' % (m[0], m[0]))
    o('end')
    o()

    # ---------------------------------------------------------------- contacts
    o('contact')
    o('  pc poly m1')
    for d in DIFFS:
        o('  %s %s m1' % (d[1], d[0]))
    for v in VIAS:
        o('  %s %s %s' % (v[0], v[2], v[3]))
    o('  stackable')
    o('end')
    o()

    # ---------------------------------------------------------------- aliases
    def star(lst):
        return ','.join('*' + x for x in lst)

    o('aliases')
    o('  allnwell      nwell,rnwell')
    o('  allpsub       space/w,pwell')
    o('  allwell       nwell,rnwell,pwell')
    o('  allnfets      %s' % ','.join(nfets))
    o('  allpfets      %s' % ','.join(pfets))
    o('  allfets       allnfets,allpfets')
    o('  allfetscore   %s' % ','.join(f[0] for f in FETS if f[2] == 'core'))
    o('  allfetsmv     %s' % ','.join(f[0] for f in FETS if f[2] == 'mv'))
    o('  allndiffnonfet %s' % star(d[0] for d in DIFFS if d[2] == 'n'))
    o('  allpdiffnonfet %s' % star(d[0] for d in DIFFS if d[2] == 'p'))
    o('  alldiffnonfet allndiffnonfet,allpdiffnonfet')
    o('  allnactive    allndiffnonfet,allnfets')
    o('  allpactive    allpdiffnonfet,allpfets')
    o('  allactive     alldiffnonfet,allfets')
    o('  alldiffcont   %s' % ','.join(diffconts))
    o('  allcont       alldiffcont,pc')
    o('  allpolyres    %s' % ','.join(polyres))
    o('  allpolynonres *poly,allfets')
    o('  allpoly       allpolynonres,allpolyres')
    o('  alltap        %s' % star(d[0] for d in DIFFS if d[7] in ('ntap', 'ptap')))
    for mt in METALS:
        t = mt[0]
        o('  all%s         *%s%s' % (t, t, (',r' + t) if mt[4] else ''))
    o('end')
    o()

    # ---------------------------------------------------------------- styles
    o('styles')
    o('  styletype mos')
    o('  dnwell cwell')
    o('  isosub comment')
    o('  nwell nwell')
    o('  rnwell nwell')
    o('  rnwell poly_resist_stripes')
    o('  pwell pwell')
    for f in FETS:
        o('  %s %s' % (f[0], 'ntransistor' if f[1] == 'n' else 'ptransistor'))
        if f[2] == 'mv':
            o('  %s %s' % (f[0], 'hvndiff_mask' if f[1] == 'n' else 'hvpdiff_mask'))
        if f[3]:
            o('  %s %s' % (f[0], 'ntransistor_stripes' if f[1] == 'n' else 'ptransistor_stripes'))
    for d in DIFFS:
        st = MVDIFF_STYLE[d[2]] if d[4] == 'mv' else DIFF_STYLE[d[2]]
        if d[7] == 'ntap' or d[7] == 'ptap':
            st = 'ndiff_in_nwell' if d[2] == 'n' else 'pdiff_in_pwell'
        o('  %s %s' % (d[0], st))
        if d[7] in ('ndio', 'pdio'):
            o('  %s implant4' % d[0])
        o('  %s %s' % (d[1], st))
        o('  %s metal1' % d[1])
        o('  %s contact_X\'es' % d[1])
    o('  poly polysilicon')
    o('  pc polysilicon')
    o('  pc metal1')
    o('  pc contact_X\'es')
    o('  polyfill poly_light')
    o('  difffill ndiffusion')
    for p in POLYRES:
        o('  %s poly_resist' % p[0])
        o('  %s poly_resist_stripes' % p[0])
    for mt in METALS:
        t = mt[0]
        o('  %s %s' % (t, mt[7]))
        if mt[4]:
            o('  r%s %s' % (t, mt[7]))
            o('  r%s poly_resist_stripes' % t)
        if mt[3]:
            o('  %sfill %s' % (t, mt[7]))
        o('  obs%s obs%s' % (t, mt[7]))
    for v in VIAS:
        lo = [mt for mt in METALS if mt[0] == v[2]][0]
        hi = [mt for mt in METALS if mt[0] == v[3]][0]
        o('  %s %s' % (v[0], lo[7]))
        o('  %s %s' % (v[0], hi[7]))
        o('  %s %s' % (v[0], v[6]))
    o('  glass overglass')
    o('  comment comment')
    o('  prbndry subcircuit')
    for m in MARKERS_:
        o('  %s %s' % (m[0], m[2]))
    o('end')
    o()

    # ---------------------------------------------------------------- compose
    o('compose')
    for f in FETS:
        dif = [d[0] for d in DIFFS if d[7] == 'sd' and d[2] == f[1] and d[4] == f[2]][0]
        if not f[3]:
            o('  compose %s poly %s' % (f[0], dif))
        else:
            o('  decompose %s poly %s' % (f[0], dif))
    o('  paint ndiff nwell pdiff')
    o('  paint ndc nwell pdc')
    o('  paint psd nwell nsd')
    o('  paint psc nwell nsc')
    o('  paint nfet nwell pfet')
    o('  paint pdiff pwell ndiff')
    o('  paint pdc pwell ndc')
    o('  paint nsd pwell psd')
    o('  paint nsc pwell psc')
    o('  paint pfet pwell nfet')
    for mt in METALS:
        o('  paint %s obs%s %s' % (mt[0], mt[0], mt[0]))
    o('end')
    o()

    # ---------------------------------------------------------------- connect
    o('connect')
    o('  nwell,rnwell,%s,dnwell nwell,rnwell,%s,dnwell' % (
        star(d[0] for d in DIFFS if d[7] == 'ntap'), star(d[0] for d in DIFFS if d[7] == 'ntap')))
    o('  pwell,%s pwell,%s' % (star(d[0] for d in DIFFS if d[7] == 'ptap'),
                               star(d[0] for d in DIFFS if d[7] == 'ptap')))
    o('  allndiffnonfet allndiffnonfet')
    o('  allpdiffnonfet allpdiffnonfet')
    # butted taps: a tap touching source / drain of the opposite type (silicided) connects
    o('  %s %s' % (star(d[0] for d in DIFFS if d[7] == 'ntap'),
                   star(d[0] for d in DIFFS if d[7] == 'sd' and d[2] == 'p')))
    o('  %s %s' % (star(d[0] for d in DIFFS if d[7] == 'ptap'),
                   star(d[0] for d in DIFFS if d[7] == 'sd' and d[2] == 'n')))
    o('  *poly,allfets *poly,allfets')
    for mt in METALS:
        t = mt[0]
        o('  *%s *%s' % (t, t))
    o('end')
    o()

    # ---------------------------------------------------------------- cifoutput
    o('cifoutput')
    o('style gdsii')
    o(' scalefactor 10 nanometers')
    o(' options calma-permissive-labels')
    o(' gridlimit 1')
    o()

    def calma(name):
        ld = gds[name][0]
        return ' calma %d %d' % ld

    def outlayer(name, types, ops=(), labels=None):
        if name in remapped:
            return
        o(' layer %s %s' % (name, types))
        for op in ops:
            o('  ' + op)
        if labels:
            o('  labels %s' % labels)
        o(' ' + calma(name))
        o()

    outlayer('DNW', 'dnwell')
    outlayer('NW', 'nwell,rnwell')
    outlayer('NW1res', 'rnwell')
    outlayer('ACT', 'allactive,alldiffcont')
    outlayer('POLY', 'allpoly,pc')
    outlayer('CT', 'allcont', ops=['squares 0 90 110'])
    for m in MARKERS_:
        if m[1] in gds:
            outlayer(m[1], m[0])
    for mt in METALS:
        t = mt[0]
        outlayer(mt[2], 'all%s' % t, labels='all%s' % t)
        if mt[4] and mt[4] in gds:
            outlayer(mt[4], 'r%s' % t)
        if mt[3] and mt[3] in gds:
            outlayer(mt[3], '%sfill' % t)
        if mt[5] and mt[5] in gds:
            o(' layer %s' % mt[5])
            o('  labels all%s port' % t)
            o(' ' + calma(mt[5]))
            o()
    for v in VIAS:
        outlayer(v[1][0], v[0])
    outlayer('CB', 'glass')
    if 'CHIPBLK' in gds:
        outlayer('CHIPBLK', 'prbndry')
    o()
    if drc is not None:
        o('#------------------------------------------------------------------------------')
        o('# derived layers of the translated Calibre DRC rules (svrf2magic_drc.py)')
        o('#------------------------------------------------------------------------------')
        o(drc.cif_style().rstrip())
    o('end')
    o()

    # ---------------------------------------------------------------- cifinput
    o('cifinput')
    o('style import')
    o(' scalefactor 10 nanometers')
    o(' gridlimit 1')
    o(' options ignore-unknown-layer-labels no-reconnect-labels')
    o()
    used = set()

    def note(*names):
        for n in names:
            used.add(n)

    o(' layer dnwell DNW')
    o()
    o(' layer rnwell NW')
    o('  and NW1res')
    o()
    o(' # labels drawn on NW (VNW of the 7-track cells) name the well, they are not pins;')
    o(' # WELTXT (well pin of the 9-track cells) is')
    o(' layer nwell NW')
    o('  and-not NW1res')
    o('  labels NW')
    o('  labels WELTXT port')
    o()
    o(' # Calibre cuts the substrate around SUBCKTLVS (sub2Ring): isolated substrate inside')
    o(' layer isosub SUBCKTLVS')
    o()
    o(' # pwell: substrate under the cell boundary (CHIPBLK) and inside SUBCKTLVS, the shape')
    o(' # that carries the substrate pin label SUBTXT (9-track VPW)')
    o(' layer pwell CHIPBLK,SUBCKTLVS')
    o('  and-not NW')
    o('  labels SUBTXT port')
    o()
    note('DNW', 'NW', 'NW1res', 'WELTXT', 'SUBCKTLVS', 'CHIPBLK', 'SUBTXT')

    o(' # ---- poly (ACT / POLY derived device layers follow Calibre: gate = POLY AND ACT)')
    o(' # resistor bodies: POLYres inside SAB, or POLYres away from SAB (silicided)')
    o(' templayer sabhalo SAB')
    o('  grow %d' % SAB_HALO)
    o()
    o(' templayer ressab POLY')
    o('  and POLYres')
    o('  and SAB')
    o()
    o(' templayer ressil POLY')
    o('  and POLYres')
    o('  and-not sabhalo')
    o()
    o(' layer poly POLY')
    o('  and-not ACT')
    o('  and-not ressab')
    o('  and-not ressil')
    if 'HRPBLK' in gds:
        o('  and-not HRPBLK')
    o()
    note('SAB', 'POLYres')
    avail = set(gds) | {'sabhalo', 'ressab', 'ressil'}
    o(' layer polyfill POLYdm')
    o()
    o(' layer difffill ACTdm')
    o()
    note('POLY', 'ACT', 'POLYdm', 'ACTdm')

    for p in POLYRES:
        a, n = ['POLY'] + p[1], ['ACT'] + p[2]
        if p[0] == 'rhrpo':
            a = ['POLY', 'HRPBLK']
        cif_layer(o, p[0], a, n, comment='%s (%s)' % (p[3], p[4]), gds=avail)
        note(*[x for x in a + n if x in gds])

    for d in DIFFS:
        a, n = diff_conds(d[2], d[3], d[4])
        a += d[5]
        n += d[6]
        cif_layer(o, d[0], a, n, comment='%s (Calibre %s)' % (d[8] or d[7], d[9]), gds=gds)
        note(*a)
        note(*n)

    for f in FETS:
        a, n = gate_conds(f[1], f[2])
        a += f[3]
        n += f[4]
        cif_layer(o, f[0], a, n, comment='%s (Calibre %s)' % (f[5], f[6]), gds=gds)
        note(*a)
        note(*n)

    o(' # ---- contacts (exact cuts)')
    for d in DIFFS:
        a, n = diff_conds(d[2], d[3], d[4])
        a = ['CT'] + a + d[5]
        n = n + d[6]
        cif_layer(o, d[1], a, n, gds=gds)
    cif_layer(o, 'pc', ['CT', 'POLY'], ['ACT'])
    note('CT')

    o(' # ---- metals and vias')
    for mt in METALS:
        t, layer, dm, rs, tx = mt[0], mt[2], mt[3], mt[4], mt[5]
        o(' layer %s %s' % (t, layer))
        if rs and rs in gds:
            o('  and-not %s' % rs)
        o('  labels %s port' % layer)
        if tx and tx in gds:
            o('  labels %s port' % tx)
        o()
        if rs and rs in gds:
            o(' layer r%s %s' % (t, layer))
            o('  and %s' % rs)
            o()
        if dm and dm in gds:
            o(' layer %sfill %s' % (t, dm))
            o()
        note(*[x for x in (layer, dm, rs, tx) if x])
    for v in VIAS:
        names = [x for x in v[1] if x in gds]
        o(' layer %s %s' % (v[0], ','.join(names)))
        o()
        note(*names)

    o(' layer glass CB')
    o()
    if 'CHIPBLK' in gds:
        o(' layer prbndry CHIPBLK')
        o()
        note('CHIPBLK')
    note('CB')

    o(' # ---- literal marker / implant layers')
    for m in MARKERS_:
        if m[1] in gds:
            o(' layer %s %s' % (m[0], m[1]))
            o()
            note(m[1])

    for name in sorted(used):
        if name not in gds:
            continue
        for (l, d) in gds[name]:
            o(' calma %s %d %d' % (name, l, d))
    o()
    o('end')
    o()

    # ---------------------------------------------------------------- mzrouter
    o('mzrouter')
    o('end')
    o()

    # ---------------------------------------------------------------- drc
    o('drc')
    o(' style drc variants (fast),(full),(routing)')
    o(' scalefactor 10')
    o()
    # Minimum width / spacing of every routing and cut layer from the technology LEF, in all
    # variants. Besides being checks, Magic's LEF / DEF reader takes the default wire width
    # of a layer from its width rule (without one, "def read" of a pin does not return).
    lws = lef_width_spacing()
    o(' # ---- LEF minimum width / spacing of the routing and cut layers (technology LEF)')
    o(' variants *')
    for mt in METALS:
        if mt[6] in lws:
            w, sp = lws[mt[6]]
            o(' width all%s %d "%s width < %%d (technology LEF)"' % (mt[0], round(w * 1000), mt[6]))
            if sp:
                o(' spacing all%s all%s %d touching_ok "%s spacing < %%d (technology LEF)"' % (
                    mt[0], mt[0], round(sp * 1000), mt[6]))
    for v in VIAS:
        if v[4] in lws:
            w, sp = lws[v[4]]
            o(' width %s %d "%s width < %%d (technology LEF)"' % (v[0], round(w * 1000), v[4]))
            if sp:
                o(' spacing %s %s %d touching_ok "%s spacing < %%d (technology LEF)"' % (
                    v[0], v[0], round(sp * 1000), v[4]))
    if 'CT' in lws:
        w, sp = lws['CT']
        o(' width allcont %d "CT width < %%d (technology LEF)"' % round(w * 1000))
        o(' spacing allcont allcont %d touching_ok "CT spacing < %%d (technology LEF)"' % round(sp * 1000))
    o()
    if drc is not None:
        o(' # Rules translated from the Calibre DRC deck by svrf2magic_drc.py; rule names and')
        o(' # values are the Calibre ones. Coverage: hacking/magic/drc_coverage.txt')
        for line in drc.summary().split('\n')[:2]:
            o(' # ' + line)
        o()
        o(drc.drc_section().rstrip())
    o('end')
    o()

    # ---------------------------------------------------------------- lef
    o('lef')
    o('  masterslice poly POLY')
    for mt in METALS:
        o('  routing %s %s' % (mt[0], mt[6]))
        o('  obs obs%s %s' % (mt[0], mt[6]))
    for v in VIAS:
        o('  cut %s %s' % (v[0], v[4]))
    o('end')
    o()

    # ---------------------------------------------------------------- extract
    res, vres, caps, st = parasitics()
    o('extract')
    o(' style ngspice variants (),(si)')
    o(' cscale 1')
    o(' variants ()')
    o(' lambda 1.0')
    o(' variants (si)')
    o(' lambda 1.0')
    o(' variants *')
    o(' units microns')
    o(' step 100')
    o(' sidehalo 2')
    o(' fringeshieldhalo 2')
    o()
    order = ['dwell', 'well', 'active'] + [mt[1] for mt in METALS] + ['block', 'comment'] + \
            [m[0] + 'pl' for m in MARKERS_]
    for i, pl in enumerate(order):
        o(' planeorder %s %d' % (pl, i))
    o()
    # heights from the ITF (bottom, thickness in um)
    cond = st.conductors
    o(' height dnwell -0.1 0.1')
    o(' height allwell 0.0 0.01')
    o(' height alldiffnonfet %.4f %.4f' % (cond['NDIFF'].zb, cond['NDIFF'].t))
    o(' height allpoly %.4f %.4f' % (cond['NPOLY'].zb, cond['NPOLY'].t))
    o(' height alldiffcont %.4f %.4f' % (cond['NDIFF'].zt, cond['M1'].zb - cond['NDIFF'].zt))
    o(' height pc %.4f %.4f' % (cond['NPOLY'].zt, cond['M1'].zb - cond['NPOLY'].zt))
    itf_metal = {'m1': 'M1', 'm2': 'M2', 'm3': 'M3', 'm4': 'M4', 'm5': 'M5', 'm6': 'TM', 'm7': 'RDL'}
    for mt in METALS:
        c = cond[itf_metal[mt[0]]]
        o(' height all%s %.4f %.4f' % (mt[0], c.zb, c.t))
    for v in VIAS:
        lo = cond[itf_metal[v[2]]]
        hi = cond[itf_metal[v[3]]]
        o(' height %s %.4f %.4f' % (v[0], lo.zt, hi.zb - lo.zt))
    o()
    o(' # diffusion that ties down gate antennas (LEF ANTENNADIFFAREA, antennacheck)')
    o(' tiedown alldiffnonfet')
    o()
    o(' substrate %s,space/w,pwell well $SUB -dnwell,isosub' %
      star(d[0] for d in DIFFS if d[7] == 'ptap'))
    o()
    o(' # sheet resistance (milliohm / square) and via resistance (milliohm) from the ITF')
    o(' resist (allnwell)/well 600000')
    o(' resist (%s)/active %d' % (star(d[0] for d in DIFFS if d[2] == 'n'), res['NDIFF']))
    o(' resist (%s)/active %d' % (star(d[0] for d in DIFFS if d[2] == 'p'), res['PDIFF']))
    o(' resist (allpolynonres)/active %d' % res['NPOLY'])
    for mt in METALS:
        o(' resist (all%s)/%s %d' % (mt[0], mt[1], round(res[itf_metal[mt[0]]])))
    o(' contact pc %d' % vres['CT_NP'])
    o(' contact alldiffcont %d' % vres['CT_ND'])
    for v in VIAS:
        o(' contact %s %d' % (v[0], vres[v[5]]))
    o()
    o(' # capacitance (aF/um^2, aF/um), fitted to the FasterCap 2D solutions of the ITF stack')
    idx = {mt[0]: i + 1 for i, mt in enumerate(METALS)}
    for mt in METALS:
        t, pl = mt[0], mt[1]
        m = idx[t]
        c0 = caps.get((m, 0))
        if not c0:
            continue
        o(' defaultareacap all%s %s %.2f' % (t, pl, c0['area']))
        o(' defaultperimeter all%s %s %.2f' % (t, pl, c0['perim']))
        if c0['side'] > 0:
            o(' defaultsidewall all%s %s %.2f %.4f' % (t, pl, c0['side'], c0['off']))
        for lo in METALS[:m - 1]:
            u = idx[lo[0]]
            cu = caps.get((m, u))
            if not cu:
                continue
            o(' defaultoverlap all%s %s all%s %s %.2f' % (t, pl, lo[0], lo[1], cu['area']))
            o(' defaultsideoverlap all%s %s all%s %s %.2f' % (t, pl, lo[0], lo[1], cu['perim']))
    o()
    o(' # devices')
    for f in FETS:
        sd = [d[0] for d in DIFFS if d[7] == 'sd' and d[2] == f[1] and d[4] == f[2]][0]
        sdt = '%s,%s' % (sd, contact_of[sd])
        sub = 'allnwell' if f[1] == 'p' else 'allpsub'
        o(' device msubcircuit %s %s %s %s %s error l=l w=w' % (f[5], f[0], sdt, sdt, sub))
    for d in DIFFS:
        if d[7] == 'ndio':
            o(' device ndiode %s *%s allpsub error a=area p=pj' % (d[8], d[0]))
        elif d[7] == 'pdio':
            o(' device pdiode %s *%s allnwell error a=area p=pj' % (d[8], d[0]))
    for p in POLYRES:
        o(' device rsubcircuit %s %s *poly l=l w=w' % (p[3], p[0]))
    o('end')
    o()

    o('wiring')
    o('end')
    o()
    o('router')
    o('end')
    o()
    o('plowing')
    o('end')
    o()
    o('plot')
    o('end')
    return o.text()


# ------------------------------------------------------------------------------------------
# Layer map for the DRC translation
# ------------------------------------------------------------------------------------------

def gds_type_map():
    """({(gds layer, datatype): Magic type list}, {type or alias: set of planes}).

    The GDS numbers are the vendor ones; the type list is what this tech file produces for
    that GDS layer (the drawn layer as the union of the device / routing types)."""
    gds = read_layer_map(LVS_RUNSET)
    names = {
        'ACT': 'allactive,alldiffcont', 'ACTdm': 'difffill', 'DNW': 'dnwell',
        'NW': 'nwell,rnwell', 'NW1res': 'rnwell', 'POLY': 'allpoly,pc', 'POLYdm': 'polyfill',
        'CT': 'allcont', 'CB': 'glass', 'CHIPBLK': 'prbndry',
    }
    for mt in METALS:
        names[mt[2]] = 'all%s' % mt[0]
        if mt[3]:
            names[mt[3]] = '%sfill' % mt[0]
        if mt[4]:
            names[mt[4]] = 'r%s' % mt[0]
    for v in VIAS:
        for l in v[1]:
            names[l] = v[0]
    for m in MARKERS:
        names[m[1]] = m[0]
    out = {}
    for n, t in names.items():
        for ld in gds.get(n, []):
            out[ld] = t
    # planes of every type and alias, from the generated types / contact / aliases sections
    text = generate(None)
    sec = None
    planes = {}
    residues = {}
    aliases = {}
    for line in text.split('\n'):
        w = line.split()
        if not w or w[0].startswith('#'):
            continue
        if len(w) == 1 and w[0] in ('types', 'contact', 'aliases', 'end'):
            sec = None if w[0] == 'end' else w[0]
            continue
        if sec == 'types' and len(w) == 2:
            pl = w[0].lstrip('-')
            for t in w[1].split(','):
                planes[t] = {pl}
        elif sec == 'contact' and len(w) >= 3:
            residues[w[0]] = w[1:]
        elif sec == 'aliases' and len(w) == 2:
            aliases[w[0]] = w[1].split(',')
    for c, rs in residues.items():
        planes[c] = set().union(*(planes.get(r, set()) for r in rs)) | planes.get(c, set())

    def expand(a, seen=()):
        out = set()
        for t in aliases.get(a, [a]):
            t0 = t.lstrip('*')
            if t0 in aliases and t0 not in seen:
                out |= expand(t0, seen + (t0,))
            else:
                out.add(t0)
                if t.startswith('*'):
                    out |= {c for c, rs in residues.items() if t0 in rs}
        return out
    for a in aliases:
        ts = expand(a)
        common = None
        for t in ts:
            p = planes.get(t, set())
            common = set(p) if common is None else common & p
        planes[a] = common or set()
    return out, planes


# ------------------------------------------------------------------------------------------
# Netgen setup
# ------------------------------------------------------------------------------------------

# Cells without devices that are in the layout but not in the LVS netlist of a design
# (fillers, well taps); netgen ignores them in the layout circuit.
PHYSICAL_ONLY_CELLS = [
    r'FILLER[0-9A-Z]*H7[RHL]',       # 7-track fillers
    r'FILLTAPH7[RHL]',               # 7-track well tap
    r'FILL[0-9]+_9T[SHL]VT',          # 9-track fillers
    r'TAPX1_9T[SHL]VT',               # 9-track well tap
]


def lvs_tolerances(path=LVS_RUNSET):
    """Calibre TRACE PROPERTY tolerances (VARIABLE mos_err ...), in percent."""
    tol = {}
    for line in open(path, encoding='latin-1'):
        m = re.match(r'\s*VARIABLE\s+(\w+)_err\s+([0-9.]+)', line)
        if m:
            tol[m.group(1)] = float(m.group(2))
    return tol


def generate_netgen():
    tol = lvs_tolerances()
    o = Out()
    o('#------------------------------------------------------------------------------')
    o('# Netgen setup for ICsprout 55LLULP (icsprout55)')
    o('#')
    o('# GENERATED by hacking/magic/gen_magic_tech.py together with the Magic tech file')
    o('# (same device list). Do not edit; change the generator.')
    o('#')
    o('# Circuit 1 is the Magic extracted layout, circuit 2 the reference netlist (the')
    o('# libs.ref/<lib>/spice/<lib>_lvs.spice views, see hacking/magic/lvs_netlist.py).')
    o('# Property tolerances are the TRACE PROPERTY ones of the Calibre LVS deck')
    o('# (mos_err %g %%, dio_err %g %%, res_err %g %%).' % (tol['mos'], tol['dio'], tol['res']))
    o('#------------------------------------------------------------------------------')
    o()
    o('permute default')
    o('property default')
    o('property parallel none')
    o()
    o('catch {format $env(NETGEN_COLUMNS)}')
    o()
    o('set cells1 [cells list -all -circuit1]')
    o('set cells2 [cells list -all -circuit2]')
    o()
    o('proc ics55_each {devices body} {')
    o('    upvar cells1 cells1 cells2 cells2')
    o('    foreach dev $devices {')
    o('        foreach c {1 2} {')
    o('            if {[lsearch [set cells$c] $dev] >= 0} {')
    o('                set circ "-circuit$c $dev"')
    o('                uplevel 1 [list set circ $circ]')
    o('                uplevel 1 $body')
    o('            }')
    o('        }')
    o('    }')
    o('}')
    o()
    mos = sorted(set(f[5] for f in FETS))
    o('# MOS (d g s b): source / drain swap, parallel devices merge by width')
    o('ics55_each {%s} {' % ' '.join(mos))
    o('    permute $circ 1 3')
    o('    property $circ parallel enable')
    o('    property $circ parallel {l critical}')
    o('    property $circ parallel {w add}')
    o('    property $circ tolerance {w %g} {l %g}' % (tol['mos'] / 100, tol['mos'] / 100))
    o('    property $circ delete as ad ps pd mult mr nf sa sb sd nrd nrs sca scb scc')
    o('}')
    o()
    dio = sorted(set(d[8] for d in DIFFS if d[8]))
    o('# junction diodes (.MODEL d): parallel devices merge by area / perimeter')
    o('ics55_each {%s} {' % ' '.join(dio))
    o('    property $circ parallel enable')
    o('    property $circ parallel {area add}')
    o('    property $circ parallel {pj add}')
    o('    property $circ tolerance {area %g} {pj %g}' % (tol['dio'] / 100, tol['dio'] / 100))
    o('    property $circ delete perim w l mult')
    o('}')
    o()
    res = sorted(set(p[3] for p in POLYRES))
    o('# poly resistors (n2 n1)')
    o('ics55_each {%s} {' % ' '.join(res))
    o('    permute $circ 1 2')
    o('    property $circ series enable')
    o('    property $circ series {w critical}')
    o('    property $circ series {l add}')
    o('    property $circ parallel enable')
    o('    property $circ parallel {l critical}')
    o('    property $circ parallel {w add}')
    o('    property $circ tolerance {l %g} {w %g}' % (tol['res'] / 100, tol['res'] / 100))
    o('    property $circ delete mult mr')
    o('}')
    o()
    o('# physical-only cells: present in the layout, absent from the LVS netlist')
    o('foreach cell $cells1 {')
    for rx in PHYSICAL_ONLY_CELLS:
        o('    if {[regexp {^%s$} $cell]} {ignore class "-circuit1 $cell"}' % rx)
    o('}')
    o('foreach cell $cells2 {')
    for rx in PHYSICAL_ONLY_CELLS:
        o('    if {[regexp {^%s$} $cell]} {ignore class "-circuit2 $cell"}' % rx)
    o('}')
    return o.text()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(ROOT, 'icsprout55', 'libs.tech', 'magic', 'ics55.tech'))
    ap.add_argument('--netgen', default=os.path.join(ROOT, 'icsprout55', 'libs.tech', 'netgen', 'ics55_setup.tcl'))
    ap.add_argument('--no-drc', action='store_true', help='leave the DRC section empty')
    ap.add_argument('--report', default=os.path.join(HERE, 'drc_coverage.txt'),
                    help='DRC translation coverage report')
    a = ap.parse_args()
    drc = None
    if not a.no_drc:
        import svrf2magic_drc
        drc = svrf2magic_drc.translate(*gds_type_map())
        with open(a.report, 'w') as f:
            f.write(drc.summary())
        print('\n'.join(drc.summary().split('\n')[:2]))
    text = generate(drc)
    with open(a.out, 'w') as f:
        f.write(text)
    print('wrote', a.out)
    if a.netgen:
        with open(a.netgen, 'w') as f:
            f.write(generate_netgen())
        print('wrote', a.netgen)


if __name__ == '__main__':
    main()
