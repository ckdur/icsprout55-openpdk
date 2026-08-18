#################################################
# Desc: This script is used to create the RC 
#       table used for OpenRCX parasitic 
#       calculation. It takes the patterns layout
#       parasitics from reference extractor (SPEF)
#       and convert it to Extraction
#       Rules file (RC Table).
#       
# Input:  - tech_Lef
#         - patterns.spef
#
# Output: - <extRules>.rules
#
##################################################

source user_env.tcl

read_lef $TECH_LEF

# Read the patterns design
read_def EXT/patterns.def

write_rules \
  -action write_patterns \
  -dir fastercap_dir

catch

extract_parasitics -ext_model_file $TECH_LEF -lef_res
write_spef $ext_dir/patterns.spef

# Read the parasitics of the patterns
#bench_read_spef $golden_spef

# Convert the parasitics into 
write_rules -file $extRules -db

exit
