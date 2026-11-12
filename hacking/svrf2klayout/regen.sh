#!/bin/bash
# regenerate the KLayout deck: regen.sh expanded.svrf out.drc
cd "$(dirname "$0")"
python3 svrf2klayout.py "$1" "$2" && ruby -c "$2" >/dev/null
