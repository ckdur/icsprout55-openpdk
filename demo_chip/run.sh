#!/bin/bash

# Just to put an example of how to run librelane with the icsprout55 PDK
export PDK_ROOT=${HOME}/Documents/SymbioticEDA/icsprout55-openpdk
export PDK=icsprout55
librelane --pdk icsprout55 config.yaml --run-tag debug_ics --manual-pdk

# For debugging in openroad
librelane --pdk icsprout55 config.yaml --run-tag debug_ics --manual-pdk --flow OpenInOpenROAD