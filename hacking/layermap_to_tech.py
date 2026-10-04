from collections import defaultdict
from natsort import natsorted
import re

def parse_layermap(filename, tech_formal_name="1P6M_5Ic_1T4Mc_RDL1"):
    planes = set()
    types = []
    gds_mappings = []
    layers_seen = set()
    styles = {}
    plane_cnt = 1
    style_cnt = 1
    done = set()

    routing = {}
    cut = {}


    xPoly = 1
    yMetal = 0
    mIc = 0
    eT2Mc = 0
    fT4Mc = 0
    gT8Mc = 0

    for statement in tech_formal_name.split("_"):
        match = re.search(r"(?P<p_val>\d+)P(?P<m_val>\d+)M", statement)
        if match:
            xPoly = int(match.group("p_val"))
            yMetal = int(match.group("m_val"))
            continue
        match = re.search(r"(?P<m_val>\d+)Ic", statement)
        if match:
            mIc = int(match.group("m_val"))
            continue
        match = re.search(r"(?P<e_val>\d+)T2Mc", statement)
        if match:
            eT2Mc = int(match.group("e_val"))
            continue
        match = re.search(r"(?P<f_val>\d+)T4Mc", statement)
        if match:
            fT4Mc = int(match.group("f_val"))
            continue
        match = re.search(r"(?P<g_val>\d+)T8Mc", statement)
        if match:
            gT8Mc = int(match.group("g_val"))
            continue

    startT2Mc = mIc + 1
    startT4Mc = startT2Mc + eT2Mc
    startT8Mc = startT4Mc + fT4Mc
    startRDL = startT8Mc + gT8Mc
    assert startRDL == (yMetal+1), "Mismatch in metal layer counts"
        

    # Formulate the contacts and drc sections
    contacts = ["ct act met1"]
    drc = []
    drc.append("style drc variants (fast),(full),(routing)")
    drc.append("scalefactor 10")
    # drc.append("cifstyle drc")
    drc.append("")
    drc.append("variants (fast),(full)")
    drc.append("")
    drc.append("width act 100 \"dummy act width\"")
    drc.append("width poly 100 \"dummy poly width\"")

    for i in range(0, mIc):
        if i == (mIc-1):
            if eT2Mc == 1:
                contacts.append(f"via{i+1} met{i+1} t2m2")
            elif eT2Mc == 2:
                contacts.append(f"via{i+1} met{i+1} t2m1")
            elif fT4Mc == 1:
                contacts.append(f"via{i+1} met{i+1} t4m2")
            elif fT4Mc == 2:
                contacts.append(f"via{i+1} met{i+1} t4m1")
            elif gT8Mc == 1:
                contacts.append(f"via{i+1} met{i+1} t8m2")
            elif gT8Mc == 2:
                contacts.append(f"via{i+1} met{i+1} t8m1")
            else:
                contacts.append(f"via{i+1} met{i+1} rdl")  # Actually, not possible, but ok
        else:
            contacts.append(f"via{i+1} met{i+1} met{i+2}")

        drc.append(f"width m{i+1} 100 \"dummy metal{i+1} width\"")


    # The following is hardcoded. TODO: Do something more ingelligent
    cntvia = mIc + 1
    if eT2Mc == 1:
        if fT4Mc == 1:
            contacts.append(f"via{cntvia} t2m2 t4m2")
        elif gT8Mc == 1:
            contacts.append(f"via{cntvia} t2m2 t8m2")
        else:
            contacts.append(f"via{cntvia} t2m2 rdl")
        cntvia += 1
        drc.append(f"width t2m2 100 \"dummy t2m2 width\"")
    if eT2Mc == 2:
        contacts.append(f"via{cntvia} t2m1 t2m2")
        cntvia += 1
        contacts.append(f"via{cntvia} t2m2 rdl")
        cntvia += 1
        drc.append(f"width t2m1 100 \"dummy t2m1 width\"")
        drc.append(f"width t2m2 100 \"dummy t2m2 width\"")
    if fT4Mc == 1:
        if gT8Mc == 1:
            contacts.append(f"via{cntvia} t4m2 t8m2")
        else:
            contacts.append(f"via{cntvia} t4m2 rdl")
        cntvia += 1
        drc.append(f"width t4m2 100 \"dummy t4m2 width\"")
    if fT4Mc == 2:
        contacts.append(f"via{cntvia} t4m1 t4m2")
        cntvia += 1
        contacts.append(f"via{cntvia} t4m2 rdl")
        cntvia += 1
        drc.append(f"width t4m1 100 \"dummy t4m1 width\"")
        drc.append(f"width t4m2 100 \"dummy t4m2 width\"")
    if gT8Mc == 1:
        contacts.append(f"via{cntvia} t8m2 rdl")
        cntvia += 1
        drc.append(f"width t8m2 100 \"dummy t8m2 width\"")
    if gT8Mc == 2:
        contacts.append(f"via{cntvia} t8m1 t8m2")
        cntvia += 1
        contacts.append(f"via{cntvia} t8m2 rdl")
        cntvia += 1
        drc.append(f"width t8m1 100 \"dummy t8m1 width\"")
        drc.append(f"width t8m2 100 \"dummy t8m2 width\"")
    contacts.append("stackable")
    drc.append(f"width rdl 100 \"dummy rdl width\"")
    
    with open(filename, "r") as f:

        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                layer_name = parts[0]
                layer_type = parts[1]
                gds_num = parts[2]
                gds_type = parts[3]
                if layer_name == "NAME":
                    continue  # Skip names

                if int(gds_num) > 255:
                    continue # What?
                
                # Format layer name for Magic types
                magic_layer = layer_name.lower() if layer_type.lower() == "drawing" else f"{layer_name.lower()}_{layer_type.lower()}"
                layer_name_ext = layer_name if layer_type.lower() == "drawing" else f"{layer_name}_{layer_type}"

                if magic_layer in layers_seen:
                    continue  # Skip duplicates based on Magic layer name
                layers_seen.add(magic_layer)
                if (gds_num, gds_type) in done:
                    continue  # Skip duplicates based on GDS number and type
                done.add((gds_num, gds_type))

                layer_to_forms = {
                    "ACT": "pdiffusion",
                    "NW": "ndiffusion",
                    "NP": "implant1",
                    "PP": "implant2",
                    "POLY": "polysilicon",
                    "CT": "implant4",
                    "DIEAREA": "comment",
                    "AP": "overglass",
                    "RPOLY": "metal8",
                }

                layer_to_plane = {
                    "ACT": "pact",
                    "NW": "pact",
                    "NP": "pact",
                    "PP": "pact",
                    "POLY": "ppoly",
                    "CT": "pact",
                }

                form_types = magic_layer  # Default form type is the magic layer name
                style = f"l{magic_layer}"  # Assign a unique style name
                style = style if style not in styles.keys() else f"l{style_cnt}"
                style_cnt += 1

                # Infer the style. 
                form_m = None
                form_v = None
                form_ov = None

                # Do the plane for default layers.
                if layer_name in layer_to_plane.keys():
                    plane = layer_to_plane[layer_name]
                else:
                    plane = "pzzlast"  # plane = f"p{layer_name.lower()}"

                def getActualNum(layer_name):
                    num = int(layer_name[3:]) if layer_name[3:].isdigit() else 1
                    if "T2M" in layer_name:
                        num = (num-1) if eT2Mc != 1 else int(not (num-1))  # 1 is 0 and 0 is 1
                    elif "T4M" in layer_name:
                        num = (num-1) if fT4Mc != 1 else int(not (num-1))  # 1 is 0 and 0 is 1
                    elif "T8M" in layer_name:
                        num = (num-1) if gT8Mc != 1 else int(not (num-1))  # 1 is 0 and 0 is 1
                    elif layer_name == "RDL":
                        num = 0
                    elif "T2V" in layer_name:
                        num = (num-1) if eT2Mc != 1 else int(not (num-1))  # 1 is 0 and 0 is 1
                    elif "T4V" in layer_name:
                        num = (num-1) if fT4Mc != 1 else int(not (num-1))  # 1 is 0 and 0 is 1
                    elif "T8V" in layer_name:
                        num = (num-1) if gT8Mc != 1 else int(not (num-1))  # 1 is 0 and 0 is 1
                    elif layer_name == "RV":
                        num = 0
                    return num

                #  .. for metals
                if "MET" in layer_name:
                    met_num = getActualNum(layer_name)
                    form = f"metal{met_num}"
                    form_m = f"m{met_num}"
                    plane = f"pmet{met_num}"
                    if met_num > mIc:
                        continue # Skip this metal. Probably described as TxMx
                elif "T2M" in layer_name:
                    t2m_num = getActualNum(layer_name)
                    form = f"metal{startT2Mc + t2m_num}"
                    form_m = f"m{startT2Mc + t2m_num}"
                    plane = f"pmet{startT2Mc + t2m_num}"
                    if t2m_num >= eT2Mc:
                        continue # Skip this metal. Non-existent
                elif "T4M" in layer_name:
                    t4m_num = getActualNum(layer_name)
                    form = f"metal{startT4Mc + t4m_num}"
                    form_m = f"m{startT4Mc + t4m_num}"
                    plane = f"pmet{startT4Mc + t4m_num}"
                    if t4m_num >= fT4Mc:
                        continue # Skip this metal. Non-existent
                elif "T8M" in layer_name:
                    t8m_num = getActualNum(layer_name)
                    form = f"metal{startT8Mc + t8m_num}"
                    form_m = f"m{startT8Mc + t8m_num}"
                    plane = f"pmet{startT8Mc + t8m_num}"
                    if t8m_num >= gT8Mc:
                        continue # Skip this metal. Non-existent
                elif layer_name == "RDL":
                    form = f"metal{startRDL}"
                    form_m = f"m{startRDL}"
                    plane = f"pmet{startRDL}"

                #  .. for vias
                elif "VIA" in layer_name:
                    via_num = getActualNum(layer_name)
                    form = f"metal{via_num} metal{via_num+1} via{via_num}" if layer_type.lower() == "drawing" else f"via{via_num}"
                    form_v = f"via{via_num}"
                    form_ov = f"m{via_num},m{via_num+1}"
                    plane = f"pmet{via_num}"
                    if via_num > (mIc-1):
                        continue # Skip this via. Probably described as TxVx
                elif "T2V" in layer_name:
                    t2v_num = getActualNum(layer_name)
                    form = f"metal{startT2Mc + t2v_num - 1} metal{startT2Mc + t2v_num} via{startT2Mc + t2v_num - 1}" if layer_type.lower() == "drawing" else f"via{startT2Mc + t2v_num - 1}"
                    form_v = f"via{startT2Mc + t2v_num - 1}"
                    form_ov = f"m{startT2Mc + t2v_num - 1},m{startT2Mc + t2v_num}"
                    plane = f"pmet{startT2Mc + t2v_num - 1}"
                    if t2v_num >= (eT2Mc):
                        continue # Skip this via. Non-existent
                elif "T4V" in layer_name:
                    t4v_num = getActualNum(layer_name)
                    form = f"metal{startT4Mc + t4v_num - 1} metal{startT4Mc + t4v_num} via{startT4Mc + t4v_num - 1}" if layer_type.lower() == "drawing" else f"via{startT4Mc + t4v_num - 1}"
                    form_v = f"via{startT4Mc + t4v_num - 1}"
                    form_ov = f"m{startT4Mc + t4v_num - 1},m{startT4Mc + t4v_num}"
                    plane = f"pmet{startT4Mc + t4v_num - 1}"
                    if t4v_num >= (fT4Mc):
                        continue # Skip this via. Non-existent
                elif "T8V" in layer_name:
                    t8v_num = getActualNum(layer_name)
                    form = f"metal{startT8Mc + t8v_num - 1} metal{startT8Mc + t8v_num} via{startT8Mc + t8v_num - 1}" if layer_type.lower() == "drawing" else f"via{startT8Mc + t8v_num - 1}"
                    form_v = f"via{startT8Mc + t8v_num - 1}"
                    form_ov = f"m{startT8Mc + t8v_num - 1},m{startT8Mc + t8v_num}"
                    plane = f"pmet{startT8Mc + t8v_num - 1}"
                    if t8v_num >= (gT8Mc):
                        continue # Skip this via. Non-existent
                elif layer_name == "RV":
                    form = f"metal{startRDL-1} metal{startRDL} via{startRDL-1}"
                    form_v = f"via{startRDL-1}"
                    form_ov = f"m{startRDL-1},m{startRDL}"
                    plane = f"pmet{startRDL-1}"

                # ... for anything else
                elif layer_name in layer_to_forms.keys():
                    form = layer_to_forms[layer_name]
                else:
                    form = "comment"

                if layer_name == "POLY" and layer_type.lower() == "drawing":
                    style = "poly"

                if form is not None and form_m is not None and layer_type.lower() == "drawing" and magic_layer != form_m:
                    form_types = f"{magic_layer},{form_m}"
                if form is not None and form_v is not None and layer_type.lower() == "drawing" and magic_layer != form_v:
                    form_types = f"{magic_layer},{form_v}"

                planes.add(plane)
                styles[style] = form
                types.append((form_types, plane, layer_name_ext, style))
                gds_mappings.append((magic_layer, gds_num, gds_type, style))

                if form_m is not None and layer_name_ext == layer_name:
                    routing[layer_name_ext] = form_m
                if form_v is not None and layer_name_ext == layer_name:
                    cut[layer_name_ext] = (form_v, form_ov)

    return natsorted(list(planes)), types, gds_mappings, styles, routing, cut, contacts, drc

def generate_tech_file(planes, types, gds_mappings, styles, routing, cut, contacts, drc, tech_name="ics55"):
    lines = []
    
    # 1. Tech Header
    lines.append("tech")
    lines.append(f"  {tech_name}")
    lines.append("end")
    lines.append("")

    # 2. Planes Section
    lines.append("planes")
    for p in planes:
        lines.append(f"  {p}")
    lines.append("end")
    lines.append("")

    # 3. Types Section
    lines.append("types")
    for layer, plane, layer_name, style in types:
        if layer == style:
            lines.append(f"  {plane} {layer}")
        else:
            lines.append(f"  {plane} {layer},{style}")
    lines.append("end")
    lines.append("")

    # 4. Contact/Via Placeholders (Barebones requirement for Magic structure)
    lines.append("contact")
    for contact in contacts:
        lines.append(f"  {contact}")
    lines.append("end")
    lines.append("")

    lines.append("styles")
    lines.append("  styletype	mos")
    for style, form in styles.items():
        lines.append(f"  {style} {form}")
    lines.append("end")
    lines.append("")

    lines.append("compose")
    lines.append("end")
    lines.append("")

    lines.append("connect")
    lines.append("end")
    lines.append("")

    # 5. CIF/GDS Output Mapping Section
    lines.append("cifoutput")
    lines.append("  style gdsii")
    lines.append("  scalefactor 1 nanometers")
    lines.append("")
    for layer, gds_num, gds_type, style in gds_mappings:
        lines.append(f"  layer {layer} {layer}")
        # lines.append(f"    bloat-all 0")
        lines.append(f"    calma {gds_num} {gds_type}")
    lines.append("end")
    lines.append("")

    # 6. CIF/GDS Input Mapping Section
    lines.append("cifinput")
    lines.append("  style gdsii")
    lines.append("  scalefactor 1 nanometers")
    lines.append("")
    for layer, gds_num, gds_type, style in gds_mappings:
        lines.append(f"  layer {style} {layer}")
    lines.append("")
    for layer, gds_num, gds_type, style in gds_mappings:
        lines.append(f"  calma {layer} {gds_num} {gds_type}")
    lines.append("end")
    lines.append("")

    lines.append("drc")
    for rule in drc:
        lines.append(f"  {rule}")
    lines.append("end")
    lines.append("")

    lines.append("extract")
    lines.append("  style default")
    for i, p in enumerate(planes):
        lines.append(f"  planeorder {p} {i}")
    lines.append("end")
    lines.append("")

    lines.append("lef")
    lines.append("  masterslice poly POLY")
    for layer, form in natsorted(routing.items()):
        lines.append(f"  routing {form} {layer}")
    for layer, (form_v, form_ov) in natsorted(cut.items()):
        lines.append(f"  cut {form_v} {layer}")
    for layer, form in natsorted(routing.items()):
        lines.append(f"  obs {form} {layer}")
    for layer, (form_v, form_ov) in natsorted(cut.items()):
        lines.append(f"  obs {form_ov} {layer}")
    lines.append("end")
    lines.append("")

    return "\n".join(lines)

if __name__ == "__main__":
    planes, types, gds_mappings, styles, routing, cut, contacts, drc = parse_layermap("../icsprout55-pdk/techfile/icsprout55.layermap")
    tech_content = generate_tech_file(planes, types, gds_mappings, styles, routing, cut, contacts, drc)

    print(tech_content)
