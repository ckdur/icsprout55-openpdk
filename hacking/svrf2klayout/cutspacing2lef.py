#!/usr/bin/env python3
"""Via array spacing rules of the Calibre DRC deck as LEF cut layer ADJACENTCUTS spacing.
Usage: cutspacing2lef.py <expanded.drc.svrf> <tech.lef> [<tech.lef> ...]   (files rewritten in place,
can be re-run; run after generate_rcx_rules/itf2lef.py rewrote them)

The deck checks the cuts of a via array with a larger spacing than single cuts (V1_S_2 .. V4_S_2,
CT_S_1a), in the form

    X = SIZE V4 BY a OVERUNDER       cuts closer than 2a form one array
    Y = SIZE X BY b UNDEROVER        only arrays of a certain size (3 x 3 and more)
    Z = V4 INSIDE Y
    EXT Z < s                        spacing in the array >= s

which is "SPACING s ADJACENTCUTS 3 WITHIN 2a" in LEF. The vendor LEF only has the single cut SPACING
(0.11): pdngen builds the PDN via arrays with it (5 x 5 cuts at 0.11, every one a V*_S_2 marker) and
ignores the VIARULE GENERATE pitch, but honours ADJACENTCUTS (4 x 4 at 0.13). Recommended rules
(T4V2_S_2) are left out, like in the default DRC run.
"""
import re
import sys

SVRF2LEF = {"CT": "CT", "V1": "VIA1", "V2": "VIA2", "V3": "VIA3", "V4": "VIA4", "T4V2": "T4V2"}
TAG = "(hacking/svrf2klayout/cutspacing2lef.py)"


def rules(svrf):
    out = {}
    for m in re.finditer(r"^(\w+)\s*\{(.*?)^\}", open(svrf).read(), re.S | re.M):
        name, body = m.group(1), m.group(2)
        if "recommended" in body.lower():
            continue
        ou = re.search(r"=\s*SIZE\s+(\w+)\s+BY\s+([\d.]+)\s+OVERUNDER", body)
        if not ou or ou.group(1) not in SVRF2LEF:
            continue
        cut = ou.group(1)
        if not re.search(r"=\s*SIZE\s+\w+\s+BY\s+[\d.]+\s+UNDEROVER", body) or \
                not re.search(r"=\s*%s\s+INSIDE\s+\w+" % cut, body):
            continue
        ext = re.search(r"EXT\s+\w+\s*<\s*([\d.]+)", body)
        if ext:
            out[SVRF2LEF[cut]] = (name, float(ext.group(1)), round(2 * float(ou.group(2)), 4))
    return out


def fix(text, rl):
    out, layer, n = [], None, 0
    for ln in text.split("\n"):
        t = ln.split()
        if TAG in ln:
            continue  # previous run
        if t[:1] == ["LAYER"] and len(t) == 2:
            layer = t[1]
        elif t[:1] == ["END"]:
            layer = None
        out.append(ln)
        if layer in rl and t[:1] == ["SPACING"] and len(t) == 3:  # the plain cut spacing
            name, s, w = rl[layer]
            out.append(f"  SPACING {s:g} ADJACENTCUTS 3 WITHIN {w:g} ;   # {name} {TAG}")
            n += 1
    return "\n".join(out), n


def main():
    rl = rules(sys.argv[1])
    for k, (name, s, w) in sorted(rl.items()):
        print(f"cutspacing2lef: {k:5s} {name:8s} SPACING {s:g} ADJACENTCUTS 3 WITHIN {w:g}")
    for path in sys.argv[2:]:
        text, n = fix(open(path).read(), rl)
        open(path, "w").write(text)
        print(f"{path}: {n} cut layers")


if __name__ == "__main__":
    main()
