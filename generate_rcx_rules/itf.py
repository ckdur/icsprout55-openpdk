"""Minimal StarRC ITF reader for the ICsprout 55LLULP stacks.

Turns the top-down DIELECTRIC / CONDUCTOR / VIA list of an ITF into a bottom-up
planar cross-section:

* dielectrics stack from the substrate (z = 0) upwards, each starting on top of the
  previous one; ``MEASURED_FROM = <diel>`` makes the dielectric end ``THICKNESS``
  above the top of ``<diel>`` (ILD1b1 above GOX), ``MEASURED_FROM = TOP_OF_CHIP``
  on a conformal dielectric is taken as its planar (field) thickness;
* a conductor sits on the top of the dielectric listed right below it and is
  embedded in the dielectrics listed above it.

Conformal coatings (TW_T / SW_T) are not modelled: they only appear around poly,
which is not an OpenRCX layer, and around RDL (passivation), where the planar field
thickness is used instead.
"""

import re
from dataclasses import dataclass, field


@dataclass
class Dielectric:
    name: str
    zb: float
    zt: float
    er: float


@dataclass
class Conductor:
    name: str
    zb: float
    t: float
    wmin: float
    smin: float
    rpsq: float
    crt1: float = 0.0
    crt2: float = 0.0
    layer_type: str = ""

    @property
    def zt(self):
        return self.zb + self.t


@dataclass
class Via:
    name: str
    frm: str
    to: str
    rpv: float
    area: float = 0.0


@dataclass
class Stack:
    technology: str
    temperature: float
    half_node: float
    dielectrics: list = field(default_factory=list)
    conductors: dict = field(default_factory=dict)
    vias: dict = field(default_factory=dict)

    @property
    def top(self):
        return self.dielectrics[-1].zt

    def er_at(self, z):
        """Relative permittivity at height z (air above the stack)."""
        for d in self.dielectrics:
            if d.zb <= z < d.zt:
                return d.er
        return 1.0


_ITEM = re.compile(r"\b(DIELECTRIC|CONDUCTOR|VIA)\s+(\S+)\s*\{([^}]*)\}", re.S)
_KV = re.compile(r"([A-Z_0-9]+)\s*=\s*([^\s]+)")


def _num(v):
    return float(v)


def read_itf(path):
    text = open(path, encoding="latin-1").read().replace("\r", "")
    text = re.sub(r"\$.*", "", text)  # ITF comments
    head = dict(_KV.findall(text.split("DIELECTRIC", 1)[0]))
    st = Stack(
        technology=head.get("TECHNOLOGY", "?"),
        temperature=float(head.get("GLOBAL_TEMPERATURE", 25)),
        half_node=float(head.get("HALF_NODE_SCALE_FACTOR", 1.0)),
    )
    items = [(k, n, dict(_KV.findall(b))) for k, n, b in _ITEM.findall(text)]

    layered = [it for it in items if it[0] != "VIA"]
    z = 0.0
    tops = {}
    pending = []  # conductors placed on the current z
    for kind, name, p in reversed(layered):
        if kind == "CONDUCTOR":
            c = Conductor(
                name=name,
                zb=z,
                t=_num(p["THICKNESS"]),
                wmin=_num(p.get("WMIN", 0)),
                smin=_num(p.get("SMIN", 0)),
                rpsq=_num(p.get("RPSQ", 0)),
                crt1=_num(p.get("CRT1", 0)),
                crt2=_num(p.get("CRT2", 0)),
                layer_type=p.get("LAYER_TYPE", ""),
            )
            st.conductors[name] = c
            continue
        t = _num(p["THICKNESS"])
        mf = p.get("MEASURED_FROM")
        if mf and mf != "TOP_OF_CHIP":
            zt = tops[mf] + t
        else:
            zt = z + t
        if zt <= z:  # zero-thickness side wall spacers
            tops[name] = z
            continue
        st.dielectrics.append(Dielectric(name, z, zt, _num(p["ER"])))
        tops[name] = zt
        z = zt

    for kind, name, p in items:
        if kind == "VIA":
            st.vias[name] = Via(name, p["FROM"], p["TO"], _num(p["RPV"]), _num(p.get("AREA", 0)))
    return st


if __name__ == "__main__":
    import sys

    s = read_itf(sys.argv[1])
    print(s.technology, "T =", s.temperature, "half node =", s.half_node)
    for d in s.dielectrics:
        print(f"  D {d.name:8s} {d.zb:7.4f} .. {d.zt:7.4f}  er {d.er}")
    for c in s.conductors.values():
        print(f"  C {c.name:8s} {c.zb:7.4f} .. {c.zt:7.4f}  wmin {c.wmin} smin {c.smin} rpsq {c.rpsq}")
    for v in s.vias.values():
        print(f"  V {v.name:8s} {v.frm}->{v.to} rpv {v.rpv}")
