#!/bin/bash
# Antenna check / repair demo: long input wires on minimum inverters.
#   bash run.sh            antenna repair on (DIODE_CELL): no violations expected
#   bash run.sh norepair   repair off: OpenROAD and KLayout report the violations
#                          (the antenna checkers then fail the run, by design)
export PDK_ROOT=$(realpath ${PWD}/../)
export PDK=icsprout55
export PYTHONPATH=$PDK_ROOT/$PDK/libs.tech/librelane${PYTHONPATH:+:$PYTHONPATH}
if [ "$1" = norepair ]; then
  librelane --pdk icsprout55 config.json --run-tag norepair --manual-pdk --overwrite -c RUN_ANTENNA_REPAIR=0 -c DRT_ANTENNA_REPAIR_ITERS=0
else
  librelane --pdk icsprout55 config.json --run-tag repair --manual-pdk --overwrite
fi
