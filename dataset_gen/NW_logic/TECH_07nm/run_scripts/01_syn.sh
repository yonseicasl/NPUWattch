#!/bin/bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <run_dir_or_run_name>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ARG="$1"

if [[ "$RUN_ARG" = /* ]] || [[ "$RUN_ARG" == */* ]]; then
    RUN_DIR="$RUN_ARG"
else
    RUN_DIR="$SCRIPT_DIR/../01_syn/$RUN_ARG"
fi

if [ ! -d "$RUN_DIR" ]; then
    echo "Error: run directory not found: $RUN_DIR"
    exit 1
fi
RUN_DIR="$(cd "$RUN_DIR" && pwd)"

if [ ! -f "$RUN_DIR/01_syn.tcl" ]; then
    echo "Error: $RUN_DIR/01_syn.tcl not found"
    exit 1
fi

cd "$RUN_DIR"
TOP_MODULE="$(awk '$1 == "set" && $2 == "topModule" {print $3; exit}' 01_syn.tcl)"
if [ -z "$TOP_MODULE" ]; then
    echo "Error: could not find topModule in $RUN_DIR/01_syn.tcl"
    exit 1
fi

set +e
dc_shell -f 01_syn.tcl | tee synthesis.log
DC_STATUS="${PIPESTATUS[0]}"
set -e

if [ "$DC_STATUS" -ne 0 ]; then
    echo "Error: dc_shell exited with status $DC_STATUS"
    exit "$DC_STATUS"
fi

if grep -Eq '^[[:space:]]*(Error:|Fatal:)' synthesis.log; then
    echo "Error: synthesis.log contains Error/Fatal messages"
    exit 2
fi

if [ ! -f "${TOP_MODULE}_syn.v" ]; then
    echo "Error: missing output ${TOP_MODULE}_syn.v"
    exit 3
fi

if [ ! -f "${TOP_MODULE}.sdc" ]; then
    echo "Error: missing output ${TOP_MODULE}.sdc"
    exit 4
fi

echo "Synthesis completed successfully: $RUN_DIR"
