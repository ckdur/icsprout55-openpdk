set current_folder [file dirname [file normalize [info script]]]

# Pad IO sites
set ::env(PAD_SITE_NAME) "IOSite"
set ::env(PAD_CORNER_SITE_NAME) "IOCorner"

# Set IO pad information
set ::env(PAD_CELLS) [dict create]
dict set ::env(PAD_CELLS) "P65_1233_PBMUX" "65, 130"
dict set ::env(PAD_CELLS) "P65_1233_PWE" "130, 130"
dict set ::env(PAD_CELLS) "P65_1233_V*" "65, 130"
dict set ::env(PAD_CELLS) "P65_1233_PAR*" "65, 130"
dict set ::env(PAD_CELLS) "P65_1233_CUT" "65, 130"
set ::env(PAD_CORNER) "P65_1233_CORNER"
set ::env(PAD_FILLERS) "\
    P65_1233_FILLER0005\
    P65_1233_FILLER001\
    P65_1233_FILLER01\
    P65_1233_FILLER1\
    P65_1233_FILLER2\
    P65_1233_FILLER5\
    P65_1233_FILLER10\
    P65_1233_FILLER20\
    P65_1233_FILLER50\
"

# Pad bondpad information (if needed)
# The bonds are actually inside of the IO
set ::env(PAD_BONDPAD_NAME) ""
set ::env(PAD_BONDPAD_WIDTH) "0"
set ::env(PAD_BONDPAD_HEIGHT) "0"
set ::env(PAD_BONDPAD_OFFSETS) [dict create]

# Pad io terminals (if needed)
#set ::env(PAD_PLACE_IO_TERMINALS)

# Sealring offset
# NOTE: Sealring is included in the IO as well
set ::env(PAD_EDGE_SPACING) "0"

# set ::env(KLAYOUT_SEALRING_SCRIPT) "/dev/null"
