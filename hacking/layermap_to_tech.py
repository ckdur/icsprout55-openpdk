from collections import defaultdict

def parse_layermap(filename):
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
    
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                layer_name = parts[0]
                layer_type = parts[1].split(",")
                gds_num = parts[2]
                gds_type = parts[3]
                if layer_name == "NAME":
                    continue  # Skip names

                if int(gds_num) > 255:
                    continue # What?
                
                # Format layer name for Magic types
                if "NET" in layer_type or "VIA" in layer_type:
                    magic_layer = layer_name.lower()
                    layer_name_ext = layer_name
                elif "PIN" in layer_type:
                    magic_layer = f"{layer_name.lower()}_pin"
                    layer_name_ext =  f"{layer_name}_pin"
                elif "FILL" in layer_type:
                    magic_layer = f"{layer_name.lower()}_fill"
                    layer_name_ext = f"{layer_name}_fill"
                elif "LEFOBS" in layer_type:
                    magic_layer = f"{layer_name.lower()}_obs"
                    layer_name_ext = f"{layer_name}_obs"
                else:
                    magic_layer = layer_name.lower()
                    layer_name_ext = layer_name

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

                plane = f"p{plane_cnt}"  # Assign a unique plane name
                plane_cnt += 1
                style = f"l{style_cnt}"  # Assign a unique style name
                style_cnt += 1

                # Infer the style. 
                form_m = None
                form_v = None
                form_ov = None
                if "MET" in layer_name or layer_name in ["RDL", "T4M2"]:
                    form = f"metal{layer_name[-1]}"  # e.g., metal1, metal2, etc.
                    form_m = f"m{layer_name[-1]}"
                    if layer_name == "T4M2":
                        form = "metal6"
                        form_m = "m6"
                    if layer_name == "RDL":
                        form = "metal7"
                        form_m = "m7"
                    if layer_name_ext == layer_name:
                        style = form_m  # Overwrite style
                    
                elif "VIA" in layer_name or layer_name in ["T4V2", "RV"]:
                    via_num = int(layer_name[-1]) if layer_name[-1].isdigit() else 1
                    form = f"metal{via_num} metal{via_num+1} via{via_num}"
                    form_v = f"via{via_num}"
                    form_ov = f"m{via_num},m{via_num+1}"
                    if layer_name == "T4V2":
                        form = "metal5 metal6 via5"
                        form_v = "via5"
                        form_ov = f"m5,m6"
                    if layer_name == "RV":
                        form = "metal6 metal7 via6"
                        form_v = "via6"
                        form_ov = f"m6,m7"
                    if layer_name_ext == layer_name:
                        style = form_v  # Overwrite style

                elif layer_name in layer_to_forms.keys():
                    form = layer_to_forms[layer_name]
                else:
                    form = "comment"

                if layer_name == "POLY":
                    style = "poly"

                planes.add(plane)
                styles[style] = form
                types.append((magic_layer, plane, layer_name_ext, style))
                gds_mappings.append((magic_layer, gds_num, gds_type, style))

                if form_m is not None and layer_name_ext == layer_name:
                    routing[layer_name_ext] = form_m
                if form_v is not None and layer_name_ext == layer_name:
                    cut[layer_name_ext] = (form_v, form_ov)

    return sorted(list(planes)), types, gds_mappings, styles, routing, cut

def generate_tech_file(planes, types, gds_mappings, styles, routing, cut, tech_name="ics55"):
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
    lines.append("  scalefactor 0.5 nanometers")
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
    lines.append("  scalefactor 0.5 nanometers")
    lines.append("")
    for layer, gds_num, gds_type, style in gds_mappings:
        lines.append(f"  layer {style} {layer}")
    lines.append("")
    for layer, gds_num, gds_type, style in gds_mappings:
        lines.append(f"  calma {layer} {gds_num} {gds_type}")
    lines.append("end")

    lines.append("lef")
    lines.append("  masterslice poly POLY")
    for layer, form in sorted(routing.items()):
        lines.append(f"  routing {form} {layer}")
    for layer, (form_v, form_ov) in sorted(cut.items()):
        lines.append(f"  cut {form_v} {layer}")
    for layer, form in sorted(routing.items()):
        lines.append(f"  obs {form} {layer}")
    for layer, (form_v, form_ov) in sorted(cut.items()):
        lines.append(f"  obs {form_ov} {layer}")
    lines.append("end")
    lines.append("")

    lines.append("drc")
    lines.append("end")
    lines.append("")

    lines.append("extract")
    lines.append("  style default")
    for i, p in enumerate(planes):
        lines.append(f"  planeorder {p} {i}")
    lines.append("end")
    lines.append("")

    return "\n".join(lines)

if __name__ == "__main__":
    planes, types, gds_mappings, styles, routing, cut = parse_layermap("layermap")
    tech_content = generate_tech_file(planes, types, gds_mappings, styles, routing, cut, tech_name="ics55")

    with open("ics55.tech", "w", encoding="utf-8") as f:
        f.write(tech_content)
        
    print("Successfully generated barebones ics55.tech!")