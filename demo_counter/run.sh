#!/bin/bash

# Just to put an example of how to run librelane with the icsprout55 PDK
export PDK_ROOT=$(realpath ${PWD}/../)
export PDK=icsprout55
# PDK LibreLane plugin (ICS55.KLayoutLVS step)
export PYTHONPATH=$PDK_ROOT/$PDK/libs.tech/librelane${PYTHONPATH:+:$PYTHONPATH}
librelane --pdk icsprout55 config.json --run-tag debug_ics --manual-pdk --overwrite

# To use the private 9-track standard cells instead of the default 7-track
# library (installed by install.sh / "make openpdk" from ../../pdk/ICsprout_55LLULP1225_STD_0818):
# librelane --pdk icsprout55 --scl ICsprout55_9TSVT_basic config.json --run-tag debug_ics_svt --manual-pdk --overwrite

# To contrast with the IHP PDK, you can run the following command:
# librelane --pdk ihp-sg13g2 config.json --run-tag debug_ihp
