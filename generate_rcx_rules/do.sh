#!/bin/bash

# Generate the inputs for FasterCap
# 1-Wire Patterns : to measure open ended wires in the layout
#make 1v1 1v2
# 2-Wire Patterns : to measure open ended wires on one side in the layout
#make 2v1 2v2
# 3-Wire Patterns : to measure total and coupling caps for the mid wire (#2)
#make 3v1 3v2
# 5-Wire Patterns : to measure total and coupling caps for the mid wire (#3)
#make 5v1 5v2

# We need only the following:
make 1v1 1v2 3v1

# Run FasterCap

# We base our extraction on whatever IHP did also
# They have: RESOVER OVER UNDER DIAGUNDER OVERUNDER 
# M2oM1uM3 M2oM1uM4 M2oM1uM5 M2oM1uM6 M2oM1uM7
# M3oM1uM4 M3oM1uM5 M3oM1uM6 M3oM1uM7
# (and so on...)

# We require the following
make 1v2_fc 3v1_fc

# Parse it
make parse

# Make the rcx model file
make gen

#openroad -exit -no_splash ./generate_patterns.tcl
#openroad -exit -no_splash ./generate_rules.tcl
