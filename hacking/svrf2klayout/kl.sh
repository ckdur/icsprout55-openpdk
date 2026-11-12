#!/bin/bash
# klayout through docker
exec docker run --rm -u $UID -v /etc/passwd:/etc/passwd:ro -v $HOME:$HOME -v /tmp:/tmp -v /tmp/claude-1000:/tmp/claude-1000 -w "$PWD" ${KLAYOUT_IMAGE:-factory.symbioticeda.com/asic-all:dev} klayout "$@"
