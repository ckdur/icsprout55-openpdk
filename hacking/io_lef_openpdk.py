#!/usr/bin/env python3
"""OpenROAD fixes applied to the IO LEF ICSIOA_N55_3P3_1P6M1TM_openpdk.lef (in place, idempotent).

1. MET5 shapes of the IO signal pins become MET5 obstructions of the same cell.
   The signal pins are stacked on MET2-MET5 at the core edge of the pad. With
   RT_MAX_LAYER MET4, OpenROAD 26Q4 detailed routing still builds access points
   on the MET5 shapes, finds them outside its routing grid ("initMazeIdx_ap no
   idx ... MET5") and aborts. MET2-MET4 stay pins; MET5 stays blocked.

2. The 1 um deep supply stubs at the core edge of the power pads (MET4 / MET5,
   the core ring layers) are split into overlapping 4 um segments. pdngen
   (add_pdn_ring -connect_to_pads) makes one strap per pin rectangle, as wide as
   the rectangle or the ring, and drops a strap that a stripe of the other
   supply crosses (the stripes run out to the outer ring when the straps are
   cut). One 49 um stub gives one 10 um strap that is lost for most stripe
   offsets, so the pad stays unconnected; the segments give one strap each and
   the ones between the stripes survive. The segments overlap, so the pin still
   covers exactly the drawn metal.

Usage: python3 hacking/io_lef_openpdk.py hacking/ICSIOA_N55_3P3_1P6M1TM_openpdk.lef
"""
import re
import sys

SEG, STEP = 4.0, 3.0          # stub segment length and pitch (um)
STUB_LAYERS = ("MET4", "MET5")
SKIP_CELLS = re.compile(r"CORNER|FILLER|CUT")


def fmt(v):
    return f"{round(v, 3):g}"


def fix(lines):
    out = []
    macro = pin = use = layer = None
    in_obs = False
    obs_met5 = []           # moved signal pin shapes of the current macro
    skip_layer = False
    moved = split = 0
    for line in lines:
        s = line.strip()
        t = s.split()
        if line.startswith("MACRO "):
            macro, obs_met5 = t[1], []
        elif line.startswith("  PIN "):
            pin, use = t[1], None
        elif line.startswith("  END ") and pin and t[1:2] == [pin]:
            pin = None
        elif line.startswith("  OBS"):
            in_obs, pin = True, None
        elif line.rstrip() == "  END" and in_obs:
            in_obs = False
            if obs_met5:
                out.append("    LAYER MET5 ;\n")
                out.extend(obs_met5)
        elif line.startswith("    USE ") and pin:
            use = t[1]

        if t[:1] == ["LAYER"]:
            layer = t[1]
            skip_layer = bool(pin) and use == "SIGNAL" and layer == "MET5"
            if skip_layer:
                continue
        elif skip_layer and t[:1] in (["RECT"], ["POLYGON"]):
            obs_met5.append("      " + s + "\n")
            moved += 1
            continue
        elif t[:1] not in (["RECT"], ["POLYGON"]):
            skip_layer = False

        m = re.match(r"(\s*)RECT (\S+) (\S+) (\S+) (\S+) ;", line)
        if (m and pin and use in ("POWER", "GROUND") and layer in STUB_LAYERS
                and not SKIP_CELLS.search(macro)
                and float(m.group(3)) == 109 and float(m.group(5)) == 110
                and float(m.group(4)) - float(m.group(2)) > SEG + 1e-6):
            x1, x2 = float(m.group(2)), float(m.group(4))
            x = x1
            while True:
                xe = min(x + SEG, x2)
                out.append(f"{m.group(1)}RECT {fmt(xe - SEG if xe == x2 else x)} 109 {fmt(xe)} 110 ;\n")
                if xe >= x2:
                    break
                x += STEP
            split += 1
            continue
        out.append(line)
    return out, moved, split


def main():
    path = sys.argv[1]
    with open(path) as f:
        lines = f.readlines()
    out, moved, split = fix(lines)
    with open(path, "w") as f:
        f.writelines(out)
    print(f"{path}: {moved} signal pin MET5 shapes moved to OBS, {split} supply stubs split")


if __name__ == "__main__":
    main()
