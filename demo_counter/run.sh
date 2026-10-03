#!/bin/bash

# Just to put an example of how to run librelane with the icsprout55 PDK
export PDK_ROOT=${HOME}/Documents/SymbioticEDA/icsprout55-openpdk
export PDK=icsprout55
librelane --pdk icsprout55 config.json --run-tag debug_ics --manual-pdk

# To contrast with the IHP PDK, you can run the following command:
librelane --pdk ihp-sg13g2 config.json --run-tag debug_ihp
