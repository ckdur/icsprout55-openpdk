import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

# Palette of default styling configurations for layers
LAYER_PALETTE = {
    "ACT":     {"frame": "#00FF00", "fill": "#00FF00", "dither": "I1",  "style": "C2"},
    "NW":      {"frame": "#268C6B", "fill": "#268C6B", "dither": "I1",  "style": "C1"},
    "POLY":    {"frame": "#BF4026", "fill": "#BF4026", "dither": "I2",  "style": "C1"},
    "RPOLY":   {"frame": "#BF4026", "fill": "#BF4026", "dither": "I2",  "style": "C1"},
    "CT":      {"frame": "#00FFFF", "fill": "#00FFFF", "dither": "I3",  "style": "C1"},
    "NP":      {"frame": "#00CC66", "fill": "#00CC66", "dither": "I1",  "style": "C0"},
    "PP":      {"frame": "#CCB899", "fill": "#CCB899", "dither": "I1",  "style": "C1"},
    "MET1":    {"frame": "#39BFFF", "fill": "#39BFFF", "dither": "I3",  "style": "C1"},
    "VIA1":    {"frame": "#CCCCFF", "fill": "#CCCCFF", "dither": "I3",  "style": "C8"},
    "MET2":    {"frame": "#CCCCD9", "fill": "#CCCCD9", "dither": "I3",  "style": "C0"},
    "VIA2":    {"frame": "#FF3736", "fill": "#FF3736", "dither": "I3",  "style": "C8"},
    "MET3":    {"frame": "#D80000", "fill": "#D80000", "dither": "I3",  "style": "C0"},
    "VIA3":    {"frame": "#9BA940", "fill": "#9BA940", "dither": "I3",  "style": "C8"},
    "MET4":    {"frame": "#93E837", "fill": "#93E837", "dither": "I3",  "style": "C1"},
    "VIA4":    {"frame": "#DEAC5E", "fill": "#DEAC5E", "dither": "I3",  "style": "C8"},
    "MET5":    {"frame": "#DCD146", "fill": "#DCD146", "dither": "I3",  "style": "C0"},
    "T4V2":    {"frame": "#FFE6BF", "fill": "#FFE6BF", "dither": "I3",  "style": "C8"},
    "T4M2":    {"frame": "#FFE6BF", "fill": "#FFE6BF", "dither": "I3",  "style": "C0"},
    "RV":      {"frame": "#FF8000", "fill": "#FF8000", "dither": "I3",  "style": "C8"},
    "RDL":     {"frame": "#FF8000", "fill": "#FF8000", "dither": "I3",  "style": "C0"},
    "AP":      {"frame": "#E68000", "fill": "#E68000", "dither": "I1",  "style": "C0"},
    "DIEAREA": {"frame": "#FFFFFF", "fill": "#FFFFFF", "dither": "I1",  "style": "C0"},
}

DEFAULT_STYLE = {"frame": "#808080", "fill": "#808080", "dither": "I1", "style": "C0"}

def parse_layermap(filename):
    entries = []
    done = set()
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
                
                # Format name according to type (e.g. MET1.pin vs MET1.drawing)
                if "NET" in layer_type or "VIA" in layer_type:
                    suffix = "drawing"
                elif "PIN" in layer_type:
                    suffix = "pin"
                elif "FILL" in layer_type:
                    suffix = "filler"
                elif "LEFOBS" in layer_type:
                    suffix = "obs"
                else:
                    suffix = "drawing"

                if (gds_num, gds_type) in done:
                    continue  # Skip duplicates based on GDS number and type
                done.add((gds_num, gds_type))
                full_name = f"{layer_name}.{suffix}"
                entries.append((full_name, layer_name, gds_num, gds_type))
    return entries

def build_lyp_xml(entries):
    root = ET.Element("layer-properties")
    
    for full_name, base_name, layer, datatype in entries:
        style = LAYER_PALETTE.get(base_name, DEFAULT_STYLE)
        
        prop = ET.SubElement(root, "properties")
        
        ET.SubElement(prop, "frame-color").text = style["frame"]
        ET.SubElement(prop, "fill-color").text = style["fill"]
        ET.SubElement(prop, "frame-brightness").text = "0"
        ET.SubElement(prop, "fill-brightness").text = "0"
        ET.SubElement(prop, "dither-pattern").text = style["dither"]
        ET.SubElement(prop, "line-style").text = style["style"]
        ET.SubElement(prop, "valid").text = "true"
        ET.SubElement(prop, "visible").text = "true"
        ET.SubElement(prop, "transparent").text = "false"
        ET.SubElement(prop, "width").text = "1"
        ET.SubElement(prop, "marked").text = "false"
        ET.SubElement(prop, "animation").text = "0"
        ET.SubElement(prop, "name").text = full_name
        ET.SubElement(prop, "source").text = f"{layer}/{datatype}"

    # Pretty format XML output
    raw_xml = ET.tostring(root, encoding="utf-8")
    parsed_xml = minidom.parseString(raw_xml)
    return parsed_xml.toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")

if __name__ == "__main__":
    entries = parse_layermap("layermap")
    lyp_content = build_lyp_xml(entries)
    
    with open("ics55.lyp", "w", encoding="utf-8") as f:
        f.write(lyp_content)
        
    print("Successfully generated ics55.lyp!")
