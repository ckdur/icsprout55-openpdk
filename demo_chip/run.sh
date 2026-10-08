#!/bin/bash

# Just to put an example of how to run librelane with the icsprout55 PDK
export PDK_ROOT=$(realpath ${PWD}/../)
export PDK=icsprout55
# PDK LibreLane plugin (ICS55.KLayoutLVS step)
export PYTHONPATH=$PDK_ROOT/$PDK/libs.tech/librelane${PYTHONPATH:+:$PYTHONPATH}
librelane --pdk icsprout55 config.yaml --run-tag debug_ics --manual-pdk --overwrite

# For debugging in openroad
# librelane --pdk icsprout55 config.yaml --run-tag debug_ics --manual-pdk --flow OpenInOpenROAD
