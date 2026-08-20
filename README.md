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

This is a list of known features that ECOS offer, but they are not totally implemented:

- Implement DRC in both Magic and Klayout. This repository puts a placeholder with just checking the width of 
  MET1. ECOS can support all the DRC written in the technology LEF file, mainly width, spacing, and enclosures.
  Go [here](https://github.com/openecos-projects/ecc-tools/tree/main/src/operation/iDRC) for more info.
- RCX true translation. This repository used the `FasterCap` offered from `OpenROAD`, but this repository contains
  the hacked-out StarRC files. the idea is to translate the files found in `hacking/decrypted_output/` into
  OpenRCX format. For now, the RCX will be VERY imprecise for two reasons:
  - Dielectric epsilons, distances, and metal thicknesses are not specified anywhere. Put some arbritary values.
  - The FasterCap implementation has the precision of their solver into 10% instead of 1% for faster convergence.
- LVS implementation. No idea how to do it for Magic, and librelane flow doesn't support Klayout by default.
  for now it is unimplemented.

## Missing PDK features

These are the missing PDK pieces for reliable implementation:

- Spice models.
- A complete DRC document (at least), or the Klayout/Magic implementation of full DRC.
- The layermap, or the cross-section of the fabrication, or the table of layers with GDS layer and datatype.

It seems they won't release those unless they are available in ECOS first.

## How to use this repository:

First, we download the PDK and organize them into a OpenPDK infrastructure

```bash
bash ./install.sh
```

Next, you need to set the `PDK_ROOT` and `PDK` environment variables:

```bash
export PDK_ROOT=$(pwd)
export PDK=icsprout55
```

Finally, you can use the librelane flow. You can use the included `counter` example:

```bash
librelane --pdk icsprout55 config.json --run-tag debug_ics
```

It is important to disable `Netgen.LVS` and `Checker.LVS` as LVS is not supported.
