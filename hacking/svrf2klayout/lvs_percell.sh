#!/bin/bash
# lvs_percell.sh DECK ROWS.gds ROWS.cdl OUTDIR [jobs]  -> per-cell verdicts of Calibre and KLayout
H=$(dirname $(realpath $0)); D=$(realpath $1); G=$(realpath $2); C=$(realpath $3); O=$(realpath -m $4); J=${5:-8}
mkdir -p $O/kl $O/cal
cat $C.cells | xargs -P $J -I{} bash -c "$H/runlvs.sh $D $G T_{} $C $O/kl/{} > $O/kl/{}.res 2>&1"
cat $C.cells | xargs -P 4 -I{} bash -c "$H/calibre_lvs.sh $G T_{} $C $O/cal/{} 2>&1 | grep -c ' CORRECT ' > $O/cal/{}.res; rm -rf $O/cal/{}/svdb"
for c in $(cat $C.cells); do echo "$c cal=$(cat $O/cal/$c.res) kl=$(cat $O/kl/$c.res)"; done > $O/summary.txt
awk '{print $2, $3}' $O/summary.txt | sort | uniq -c
