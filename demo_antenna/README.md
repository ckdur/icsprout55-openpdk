# demo_antenna

Antenna check and repair on purpose: 8 inputs on the west edge of a 3000 x 200 um die drive
minimum inverters (`INVX0P5H7R`, instantiated) without port buffers or resizer repairs, the
outputs leave on the east edge. The long input wires (no diffusion on the net until a diode is
added) exceed the cumulative metal / gate area limit of the vendor antenna runset (AR_5_10, 5000).

```bash
bash run.sh            # repair on: OpenROAD repair_antennas inserts ANT2H7R diodes
bash run.sh norepair   # RUN_ANTENNA_REPAIR=0, DRT_ANTENNA_REPAIR_ITERS=0: the violations stay
```

What it checks (tech LEF antenna rules from `hacking/svrf2klayout/ant2lef.py`, cell pin data
from Magic in `<lib>_ecos_openpdk.lef`, diode cell liberty `<lib>_antenna.lib`):
OpenROAD check_antennas and the KLayout antenna deck (`KLayout.Antenna`) must agree, before and
after repair, and the diodes must pass LVS (Netgen and KLayout).
