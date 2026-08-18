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
make 1v1 1v2 3v1 3v2

# Run FasterCap

# 1-Wire All Patterns       
#make 1v1_fc 1v2_fc
# 2-Wire OverUnder Patterns : 
#make 2v1_fc_overUnder 2v2_fc_overUnder
# 3-Wire Over Patterns      : 
#make 3v1_fc_over3 3v2_fc_over3
# 3-Wire M3oM2uM6 Patterns  : 
#make 3v2_fc_M3oM2uM6

# We require the following:
make 1v2_fc 3v1_fc_over3 3v2_fc_over3 3v2_fc_M3oM2uM6

# Parse it
make 


#openroad -exit -no_splash ./generate_patterns.tcl
#openroad -exit -no_splash ./generate_rules.tcl
