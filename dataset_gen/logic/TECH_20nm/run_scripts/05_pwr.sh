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
    RUN_DIR="$SCRIPT_DIR/../05_pwr/$RUN_ARG"
fi

if [ ! -d "$RUN_DIR" ]; then
    echo "Error: run directory not found: $RUN_DIR"
    exit 1
fi
RUN_DIR="$(cd "$RUN_DIR" && pwd)"

if [ ! -f "$RUN_DIR/05_pwr.tcl" ]; then
    echo "Error: $RUN_DIR/05_pwr.tcl not found"
    exit 1
fi

cd "$RUN_DIR"

set +e
pt_shell -f 05_pwr.tcl 2>&1 | tee pwr.log
PT_STATUS="${PIPESTATUS[0]}"
set -e

if [ "$PT_STATUS" -ne 0 ]; then
    echo "Error: pt_shell exited with status $PT_STATUS"
    exit "$PT_STATUS"
fi

if grep -Eq '^[[:space:]]*Fatal:|PrimeTime is not enabled|Checkout of .PrimeTime. license failed' pwr.log; then
    echo "Error: pwr.log contains fatal/license failure messages"
    exit 2
fi

if ! grep -Eiq 'report_power|Report[[:space:]]*:[[:space:]]*power' pwr.log; then
    echo "Error: pwr.log does not contain report_power output"
    exit 2
fi

cp pwr.log power.rpt

echo "PrimeTime power completed successfully: $RUN_DIR"
