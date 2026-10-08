# ICSprout 55nm (ICS55/ics55) general purpose Open-Source Implementation

ICSprout 55nm (Technically called  `ICsprout 55LLULP 1P6M`) is an Open-Source PDK released 
recently for preview purposes, with the latest files released at late Jul - early Aug/2026.


## Credits

Credit to:

- For PDK development:
    - **ICsprout Integrated Circuit Co. (ICsprout)**
    - **College of Integrated Circuits Zhejiang University**
- For Open-Source maintaining (repository maintainers, etc.)
    - **ECOS Team, Institute of Computing Technology, Chinese Academy of Sciences (ECOS Team)**

## Why the existence of this repository?

Although the ECOS Team claims the release of ICS55 is Open-Source, is tightly implemented
in the ECOS Open-Source ecosystem. Originally, you need to use the following tools:

- *iEDA, Intrastructure and tools from Netlist to GDS.* It hosts all the algorithms and tools,
  containing but not limited to: 
  - iCTS: Clock Tree Synthesis
  - iDRC: Design Rule Check (Width, spacing, and enclosures only)
  - iEMIR: EM and IR extraction
  - iFP: Floorplaning and Placement tool
  - iLVS: Layout-vs-Schematic (block-level)
  - iRCX: RC extraction
  - iRT: Global and Detail Router
  - iSTA: Static Timing Analysis
  - iZH: Antenna, Fanout, Filler and Metal Filler engines
  
  These only contains the actual algorithms, and will be exported into libraries.

  Download and build from here:
  [https://github.com/openecos-projects/ecc-tools](https://github.com/openecos-projects/ecc-tools)

- *ECOS Chip Compiler (ECC):* A tool to make RTL-to-GDS design flow. Contains the actual CLI interface.
  This tool can be accessed using Python (via the chipcompiler package) or directly using tcl scripts.
  
  Download and build from here:
  [https://github.com/openecos-projects/ecc](https://github.com/openecos-projects/ecc)

- *ECOS frontend*, and its dependencies will contain the actual GUI elements.

  Download from here:
  [https://github.com/openecos-projects/ecc-fe](https://github.com/openecos-projects/ecc-fe)

- *ECOS Studio:* The GUI for the ECC tool. It will offer a very-informative GUI for building ASICs.
  It facilitates the implementation of the following PDKs: `sky130`, `ihp-sg13g2`, and `ics55`.
  
  Download and build from here:
  [https://github.com/openecos-projects/ecos-studio](https://github.com/openecos-projects/ecos-studio)

With this ecosystem explained, some of the implementations of the PDKs are harcoded into the software.
Specially regarding ICS55, the RCX extraction and the Signoff (and therefore everything related to these steps)
are actually closed to the public. It may be related to the fact that RCX files are written originally for StarRC.
I am more inclined to believe that this is a way to boost the usage of their EDA tools.

**I definitely encourage the usage of the ECOS software**. It is by principle open-source, and it is compatible
with the existing OpenPDKs. **What I am against** is making the new releases of the ICS55 PDK tied to a single
piece of software. This is why Open-Source exists in principle (according to me, at least)

So, I offer this repository to implement the same RTL-to-GDS, but using the regular librelane Open-Source flow.

## Missing features

This is a list of known features that ECOS offer, and their state in this repository:

- DRC. KLayout DRC (`icsprout55/libs.tech/klayout/tech/ics55.drc`) is a partial translation of the vendor Calibre
  runset (`icsprout55-pdk/pv/DRC`): widths, spaces, areas and the basic via enclosures of the main FEOL layers,
  M1-M5, the vias and the top metal. Density, connectivity-based rules, antenna and dummy fill are not translated yet.
  A few values are relaxed so the released standard cells pass; each one is marked in the deck and listed in
  `icsprout55/libs.tech/klayout/tech/testing/README.md`. Magic DRC is a placeholder and is not used.
- LVS. KLayout LVS (`icsprout55/libs.tech/klayout/tech/ics55.lvs`) is translated from the vendor Calibre runset
  (`icsprout55-pdk/pv/LVS`). It extracts the devices used by the standard cells and the IO library (core svt/hvt/lvt
  and 3.3V MOS, diodes, poly resistors). LibreLane only runs KLayout LVS for the IHP PDKs, so this PDK ships a
  LibreLane plugin with the step `ICS55.KLayoutLVS` (see below). Magic/Netgen LVS is not supported.
  Full-chip LVS (`demo_chip`) is disabled for now, it is too slow on a chip with fill.
- RCX true translation. This repository used the `FasterCap` offered from `OpenROAD`, but this repository contains
  the hacked-out StarRC files. the idea is to translate the files found in `hacking/decrypted_output/` into
  OpenRCX format. For now, the RCX will be VERY imprecise for two reasons:
  - Dielectric epsilons, distances, and metal thicknesses are not specified anywhere. Put some arbritary values.
  - The FasterCap implementation has the precision of their solver into 10% instead of 1% for faster convergence.

## Missing PDK features

The vendor PDK (`icsprout55-pdk`) now includes the SPICE models (HSPICE, adapted for ngspice in
`icsprout55/libs.tech/ngspice`, see `demo_sim`) and the Calibre DRC/LVS runsets, whose layer maps give the GDS
layer and datatype of every layer. Still missing for a reliable implementation:

- A complete DRC document, to check the translated rules against.
- The cross-section of the fabrication (dielectrics, metal thicknesses) for RCX.

## How to use this repository:

First, we download the PDK and organize them into a OpenPDK infrastructure

```bash
bash ./install.sh
```

Besides copying the vendor libraries, `install.sh` converts their CDL netlists into LVS-ready ones
(`hacking/cdl_convert.py`) and generates ngspice netlists of the standard cells (`hacking/cdl_to_spice.py`).

Next, you need to set the `PDK_ROOT` and `PDK` environment variables:

```bash
export PDK_ROOT=$(pwd)
export PDK=icsprout55
```

Finally, you can use the librelane flow. You can use the included `counter` example (`demo_counter/run.sh`):

```bash
export PYTHONPATH=$PDK_ROOT/$PDK/libs.tech/librelane${PYTHONPATH:+:$PYTHONPATH}
librelane --pdk icsprout55 config.json --run-tag debug_ics --manual-pdk
```

The `PYTHONPATH` entry loads the PDK LibreLane plugin. To use KLayout LVS and skip the Magic verifications, the
design config needs these substitutions (as in `demo_counter/config.json`):

```json
"meta": {
  "substituting_steps": {
    "Magic.DRC": null,
    "Checker.MagicDRC": null,
    "Magic.SpiceExtraction": null,
    "Checker.IllegalOverlap": null,
    "KLayout.XOR": null,
    "Checker.XOR": null,
    "-Netgen.LVS": "OpenROAD.WriteCDL",
    "Netgen.LVS": "ICS55.KLayoutLVS"
  }
}
```

`Checker.LVS` then checks the KLayout LVS result. KLayout DRC still reports some findings of the standard cells
themselves (see `icsprout55/libs.tech/klayout/tech/testing/README.md`), so the demos set
`ERROR_ON_KLAYOUT_DRC: false`.

`demo_chip` is a full chip with a pad ring that uses the `counter` as a macro, so run `demo_counter` first.

The DRC and LVS decks have a regression on the standard cells and the IO library:

```bash
cd icsprout55/libs.tech/klayout/tech/testing
python3 run_regression.py
```

All the tools are available in the `factory.symbioticeda.com/asic-all:dev` container, e.g.:

```bash
docker run --rm -v "$PWD":/work -w /work/demo_counter factory.symbioticeda.com/asic-all:dev bash -lc 'bash run.sh'
```
