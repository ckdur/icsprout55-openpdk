#!/bin/bash
# runlvs.sh DECK GDS TOP SCHEMATIC OUTDIR [extra -rd ...]
H=$(dirname $(realpath $0)); D=$(realpath $1); G=$(realpath $2); T=$3; SC=$(realpath $4); O=$(realpath -m $5); shift 5
mkdir -p $O; cd $O
$H/kl.sh -b -r $D -rd input=$G -rd topcell=$T -rd schematic=$SC -rd report=$O/$T.lvsdb -rd target_netlist=$O/$T.spice "$@" 2>&1 | grep -v "exec " > $O/$T.log
grep -c "Congratulations" $O/$T.log
