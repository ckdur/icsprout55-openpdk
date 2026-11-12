#!/bin/bash
# calibre_lvs.sh GDS TOP CDL OUTDIR  -> runs Calibre LVS with the expanded deck; prints result summary
H=$(dirname $(realpath $0)); G=$(realpath $1); T=$2; C=$(realpath $3); O=$(realpath -m $4)
mkdir -p $O; cd $O
sed -e "s|^SOURCE PATH .*|SOURCE PATH \"$C\"|" -e "s|^SOURCE PRIMARY .*|SOURCE PRIMARY \"$T\"|" \
    -e "s|^LAYOUT PATH .*|LAYOUT PATH \"$G\"|" -e "s|^LAYOUT PRIMARY .*|LAYOUT PRIMARY \"$T\"|" \
    $H/ICsprout_CalLVS_expanded.svrf > rules.svrf
source /usr/local/bin/616cad >/dev/null 2>&1
calibre -lvs -hier -spice $T.cal.sp rules.svrf > calibre.log 2>&1
grep -m1 -A12 "OVERALL COMPARISON RESULTS" lvs.rep | grep -v "^\s*$" | head -10
grep -i "^ERROR" calibre.log | head -5
