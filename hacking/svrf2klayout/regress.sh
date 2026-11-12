#!/bin/bash
# Run icsprout55/libs.tech/klayout/tech/testing/run_regression.py inside the docker image
# (it needs klayout and the klayout python module): regress.sh [--tests a,b] [--update] [--run-dir DIR]
R=$(realpath $(dirname $0)/../..)
exec docker run --rm -u $UID -v /etc/passwd:/etc/passwd:ro -v $HOME:$HOME -v /tmp:/tmp -v /tmp/claude-1000:/tmp/claude-1000 \
  -w $R/icsprout55/libs.tech/klayout/tech/testing ${KLAYOUT_IMAGE:-factory.symbioticeda.com/asic-all:dev} \
  python3 run_regression.py "$@"
