#!/bin/bash
# dbgrun.sh GDS TOP RULE DUMPS  -> runs only RULE (flat) and dumps layers
S=${SCRATCH:-/tmp}
GDS=$(realpath $1); TOP=$2; RULE=$3; DUMP=$4
OUT=$(mktemp -d)
$(dirname $0)/kl.sh -b -r ${DECK:-$S/ics55.drc} -rd input=$GDS -rd topcell=$TOP -rd report=$OUT/d.lyrdb -rd flat=1 -rd select="^($RULE)\$" -rd dump="$DUMP" > $OUT/log 2>&1
grep -i "fail\|error" $OUT/log
python3 -c "
import sys; sys.path.insert(0,'$(dirname $0)')
import klayout_run as K
r=K.parse_lyrdb('$OUT/d.lyrdb')
for k,v in r.items():
    print(k,len(v))
    for g in v[:${N:-6}]: print('   ',g)"
