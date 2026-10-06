#!/bin/sh
# Run all ngspice demos. Results (CSV) go to out/.
set -e
cd "$(dirname "$0")"
mkdir -p out
for sp in mos_iv.sp inv_vtc.sp ringosc.sp stdcell_ringosc.sp stdcell_dff.sp; do
    echo "=== $sp"
    ngspice -b "$sp" 2>&1 | tee "out/${sp%.sp}.log" \
        | grep -E "^(Idsat|vm |gain_max|Period|iavg|Clock-to-Q)|[Ee]rror" || true
done
