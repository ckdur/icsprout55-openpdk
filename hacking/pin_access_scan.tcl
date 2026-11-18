# Pin access of every cell of a library: which signal pins the OpenROAD detailed router finds
# no access point for (DRT-0073 in a real design).
#   TECH_LEF=.. CELL_LEF=.. SITE=.. [SKIP="FILL* TAPCELL ..."] \
#     openroad -exit -no_splash hacking/pin_access_scan.tcl > scan.log
#   grep DRT-0073 scan.log | sed -E 's/.*\((\w+)\)\..*/\1/' | sort -u      (the cells)
# Every cell is placed twice, in a row of orientation N and one of FS (the two row orientations
# of a placed design), with a net on each signal pin; pin_access then reports
# "DRT-0073 No access point for <cell>_<orient>/<pin> (<cell>)" for every pin it cannot reach.

read_lef $::env(TECH_LEF)
read_lef $::env(CELL_LEF)

set db [ord::get_db]
set tech [$db getTech]
set lib [lindex [$db getLibs] end]
set site [$lib findSite $::env(SITE)]
if { $site == "NULL" } { error "site $::env(SITE) not found" }
set sw [$site getWidth]
set sh [$site getHeight]

set chip [odb::dbChip_create $db $tech]
set block [odb::dbBlock_create $chip "scan"]
$block setDefUnits [$tech getDbUnitsPerMicron]

set skip {}
if { [info exists ::env(SKIP)] } { set skip $::env(SKIP) }
set masters {}
foreach m [$lib getMasters] {
    set n [$m getName]
    set s 0
    foreach p $skip { if { [string match $p $n] } { set s 1 } }
    if { !$s } { lappend masters $m }
}

# rows of up to ~100 um, cells spaced by 2 sites; row pairs N / FS
set gap [expr 2 * $sw]
set maxw [expr 100 * [$tech getDbUnitsPerMicron]]
set x 0
set row 0
set placed {}
set nnet 0
foreach orient {R0 MX} {
    if { $x > 0 } { set x 0; incr row }
    foreach m $masters {
        if { $x + [$m getWidth] > $maxw } { set x 0; incr row }
        set y [expr $row * $sh]
        set inst [odb::dbInst_create $block $m "[$m getName]_$orient"]
        set o [expr { $row % 2 ? "MX" : "R0" }]
        if { $orient == "MX" } { set o [expr { $row % 2 ? "R0" : "MX" }] }
        $inst setOrient $o
        if { $o == "MX" } { $inst setLocation $x [expr $y + $sh] } else { $inst setLocation $x $y }
        $inst setPlacementStatus PLACED
        foreach it [$inst getITerms] {
            set mt [$it getMTerm]
            if { [$mt getSigType] != "SIGNAL" } continue
            set net [odb::dbNet_create $block "n[incr nnet]"]
            $it connect $net
        }
        lappend placed $inst
        set x [expr $x + [$m getWidth] + $gap]
    }
}
set nrows [expr $row + 1]
set width [expr $maxw + 4 * $sw]
for { set r 0 } { $r < $nrows } { incr r } {
    set o [expr { $r % 2 ? "MX" : "R0" }]
    odb::dbRow_create $block "row$r" $site 0 [expr $r * $sh] $o HORIZONTAL [expr $width / $sw] $sw
}
$block setDieArea [odb::new_Rect [expr -2 * $sw] [expr -2 * $sh] [expr $width] [expr ($nrows + 2) * $sh]]

# tracks as in libs.tech/librelane/<lib>/tracks.info (0.2 um, offset 0)
foreach l {MET1 MET2 MET3 MET4 MET5} {
    set layer [$tech findLayer $l]
    set grid [odb::dbTrackGrid_create $block $layer]
    set p [expr int(0.2 * [$tech getDbUnitsPerMicron])]
    set die [$block getDieArea]
    $grid addGridPatternX [$die xMin] [expr ([$die xMax] - [$die xMin]) / $p + 1] $p
    $grid addGridPatternY [$die yMin] [expr ([$die yMax] - [$die yMin]) / $p + 1] $p
}

set_routing_layers -signal MET1-MET4
# DRT-0073 for each pin without access point, then an error: collected from the log by the caller
if { [catch { pin_access } err] } { puts "pin_access_scan: pin_access: $err" }

puts "pin_access_scan: [llength $masters] cells placed"
