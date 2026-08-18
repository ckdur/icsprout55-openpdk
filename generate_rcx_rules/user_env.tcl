############################
# DATA GENERATION SETTINGS 
############################

# Variables that point to the LEF files
# NEEDS to be changed for different tech.
set TECH_LEF $::env(PDK_ROOT)/$::env(PDK)/libs.ref/prtech/techLEF/N551P6M_ecos.lef
set ::env(STD_CELL_LIBRARY) "ics55_LLSC_H7CR"
set scl_dir "$::env(PDK_ROOT)/$::env(PDK)/libs.ref/$::env(STD_CELL_LIBRARY)"
set MACRO_LEF $scl_dir/lef/ics55_LLSC_H7CR_ecos.lef

# This is just an example of the parasitics of the 
# patterns that is used for Demo purposes.
# NEEDS to be changed for different tech.
set golden_spef generate_pattern.spefok

# Technology Node 
set PROCESS_NODE 55

# Process corner
# NEEDS to be changed for different corners.
set CORNER rcx

# The file name and location of the custom RC tech file
# The name is subject to change
set extRules $::env(PDK_ROOT)/$::env(PDK)/libs.tech/librelane/$::env(STD_CELL_LIBRARY)/${CORNER}.rules
