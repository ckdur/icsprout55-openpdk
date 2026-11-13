#!/usr/bin/env python3
"""Write a tech LEF whose resistances come from a StarRC ITF at a given temperature.

OpenRCX is run with -lef_res by LibreLane, so wire and via resistance in the SPEF
come from the tech LEF of the extraction corner, not from the rules file.  This
rewrites, in a copy of the tech LEF:

  * routing layers  RESISTANCE RPERSQ  = RPSQ * (1 + CRT1 dT + CRT2 dT^2)
  * cut layers      RESISTANCE         = RPV (per cut; the ITF has no via TC)
  * VIA definitions RESISTANCE         = RPV / number of cuts

with dT = T - GLOBAL_TEMPERATURE.  Sheet resistance is per square and therefore
not affected by the half node shrink.

Usage: itf2lef.py <base.lef> <itf> <temperature C> <out.lef>
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import itf  # noqa: E402

ROUTING = {"MET1": "M1", "MET2": "M2", "MET3": "M3", "MET4": "M4", "MET5": "M5", "T4M2": "TM", "RDL": "RDL"}
CUTS = {"VIA1": "V1", "VIA2": "V2", "VIA3": "V3", "VIA4": "V4", "T4V2": "TV", "RV": "RV"}


def main():
    base, itf_path, temp, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    st = itf.read_itf(itf_path)
    dt = temp - st.temperature

    def rsq(name):
        c = st.conductors[ROUTING[name]]
        return c.rpsq * (1 + c.crt1 * dt + c.crt2 * dt * dt)

    lines = open(base).read().split("\n")
    res = []
    layer = None  # current LAYER block
    via = None  # current VIA block: [index of RESISTANCE line, cut layer, ncuts]
    cur_layer_in_via = None
    for ln in lines:
        t = ln.split()
        if t[:1] == ["LAYER"] and via is None:
            layer = t[1]
        elif t[:1] == ["END"] and layer is not None and t[1:2] == [layer]:
            if layer in CUTS and not any(
                re.match(r"\s*RESISTANCE\s", x) for x in res[layer_start:]
            ):
                res.insert(len(res), f"  RESISTANCE {st.vias[CUTS[layer]].rpv:g} ;")
            layer = None
        if t[:1] == ["VIA"] and len(t) >= 2 and layer is None:
            via = [None, None, 0]
            cur_layer_in_via = None
        if via is not None:
            if t[:1] == ["RESISTANCE"]:
                via[0] = len(res)
            elif t[:1] == ["LAYER"]:
                cur_layer_in_via = t[1]
                if cur_layer_in_via in CUTS:
                    via[1] = cur_layer_in_via
            elif t[:1] == ["RECT"] and cur_layer_in_via in CUTS:
                via[2] += 1
            elif t[:1] == ["END"]:
                if via[0] is not None and via[1] is not None and via[2]:
                    r = st.vias[CUTS[via[1]]].rpv / via[2]
                    res[via[0]] = re.sub(r"RESISTANCE\s+[\d.eE+-]+", f"RESISTANCE {r:g}", res[via[0]])
                via = None
        if layer is not None and t[:2] == ["RESISTANCE", "RPERSQ"] and layer in ROUTING:
            ln = re.sub(r"RPERSQ\s+[\d.eE+-]+", f"RPERSQ {rsq(layer):.6g}", ln)
        elif layer in CUTS and t[:1] == ["RESISTANCE"]:
            ln = re.sub(r"RESISTANCE\s+[\d.eE+-]+", f"RESISTANCE {st.vias[CUTS[layer]].rpv:g}", ln)
        if t[:1] == ["LAYER"] and via is None:
            layer_start = len(res)
        res.append(ln)
    hdr = (
        f"# Resistances from {st.technology} at {temp:g} C "
        f"(generate_rcx_rules/itf2lef.py, base {os.path.basename(base)})"
    )
    open(out, "w").write(hdr + "\n" + "\n".join(res))


if __name__ == "__main__":
    main()
