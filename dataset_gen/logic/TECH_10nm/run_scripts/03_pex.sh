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
    RUN_DIR="$SCRIPT_DIR/../03_pex/$RUN_ARG"
fi

if [ ! -d "$RUN_DIR" ]; then
    echo "Error: run directory not found: $RUN_DIR"
    exit 1
fi
RUN_DIR="$(cd "$RUN_DIR" && pwd)"

if [ ! -f "$RUN_DIR/03_pex.strc" ]; then
    echo "Error: $RUN_DIR/03_pex.strc not found"
    exit 1
fi

cd "$RUN_DIR"

NETLIST_FILE="$(awk -F: 'toupper($1) ~ /^[[:space:]]*NETLIST_FILE[[:space:]]*$/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' 03_pex.strc)"
NDM_DATABASE="$(awk -F: 'toupper($1) ~ /^[[:space:]]*NDM_DATABASE[[:space:]]*$/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' 03_pex.strc)"

if [ -z "$NETLIST_FILE" ]; then
    echo "Error: could not find NETLIST_FILE in $RUN_DIR/03_pex.strc"
    exit 1
fi

if [ -z "$NDM_DATABASE" ]; then
    echo "Error: could not find NDM_DATABASE in $RUN_DIR/03_pex.strc"
    exit 1
fi

if [[ "$NDM_DATABASE" != /* ]]; then
    NDM_DATABASE="$RUN_DIR/$NDM_DATABASE"
fi

if [ ! -e "$NDM_DATABASE" ]; then
    echo "Error: NDM database not found: $NDM_DATABASE"
    exit 1
fi

set +e
StarXtract 03_pex.strc 2>&1 | tee pex.log
STARRC_STATUS="${PIPESTATUS[0]}"
set -e

if [ "$STARRC_STATUS" -ne 0 ]; then
    echo "Error: StarXtract exited with status $STARRC_STATUS"
    exit "$STARRC_STATUS"
fi

if grep -Eiq '^[[:space:]]*(Error:|Fatal:|ERROR|FATAL)' pex.log; then
    echo "Error: pex.log contains Error/Fatal messages"
    exit 2
fi

if [[ "$NETLIST_FILE" != /* ]]; then
    NETLIST_FILE="$RUN_DIR/$NETLIST_FILE"
fi

if [ ! -f "$NETLIST_FILE" ]; then
    echo "Error: missing output $NETLIST_FILE"
    exit 3
fi

echo "PEX completed successfully: $RUN_DIR"
