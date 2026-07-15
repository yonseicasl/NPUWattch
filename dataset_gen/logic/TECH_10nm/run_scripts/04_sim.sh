#!/bin/bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <run_dir_or_run_name> [simv-plusargs...]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ARG="$1"
shift
SIMV_EXTRA_ARGS=("$@")

if [[ "$RUN_ARG" = /* ]] || [[ "$RUN_ARG" == */* ]]; then
    RUN_DIR="$RUN_ARG"
else
    RUN_DIR="$SCRIPT_DIR/../04_sim/$RUN_ARG"
fi

if [ ! -d "$RUN_DIR" ]; then
    echo "Error: run directory not found: $RUN_DIR"
    exit 1
fi
RUN_DIR="$(cd "$RUN_DIR" && pwd)"

cd "$RUN_DIR"

if [ ! -f 04_sim.f ]; then
    echo "Error: $RUN_DIR/04_sim.f not found"
    exit 1
fi

if [ -n "${STD_CELL_MODELS_F:-}" ]; then
    if [ ! -f "$STD_CELL_MODELS_F" ]; then
        echo "Error: STD_CELL_MODELS_F does not exist: $STD_CELL_MODELS_F"
        exit 1
    fi
    cp "$STD_CELL_MODELS_F" stdcell_models.f
fi

if [ -n "${STD_CELL_MODELS:-}" ]; then
    printf '%s\n' "$STD_CELL_MODELS" | tr ':' '\n' > stdcell_models.f
fi

if [ ! -f stdcell_models.f ]; then
    echo "Error: stdcell_models.f not found"
    exit 1
fi

MODEL_COUNT="$(
    awk '
        /^[[:space:]]*$/ {next}
        /^[[:space:]]*(\/\/|#)/ {next}
        {count++}
        END {print count + 0}
    ' stdcell_models.f
)"
if [ "$MODEL_COUNT" -eq 0 ]; then
    echo "Error: no Verilog standard-cell simulation models were listed in stdcell_models.f"
    echo "       Add model paths to stdcell_models.f, or set STD_CELL_MODELS_F / STD_CELL_MODELS."
    exit 2
fi

while IFS= read -r model_file; do
    model_file="${model_file%%//*}"
    model_file="${model_file#"${model_file%%[![:space:]]*}"}"
    model_file="${model_file%"${model_file##*[![:space:]]}"}"
    [ -z "$model_file" ] && continue
    [[ "$model_file" == \#* ]] && continue
    if [ ! -f "$model_file" ]; then
        echo "Error: standard-cell model file not found: $model_file"
        exit 2
    fi
done < stdcell_models.f

if [ -n "${VCS_HOME:-}" ]; then
    VCS_ROOT="${VCS_HOME%/linux}"
    if [ "$VCS_ROOT" != "$VCS_HOME" ] && [ -x "$VCS_ROOT/linux64/bin/vcs1" ]; then
        export VCS_HOME="$VCS_ROOT"
    fi
fi

set +e
vcs -full64 -sverilog -timescale=1ns/1ps +notimingcheck -debug_access+all -f 04_sim.f -l vcs_compile.log -o simv
VCS_STATUS="$?"
set -e

if [ "$VCS_STATUS" -ne 0 ]; then
    echo "Error: VCS compile exited with status $VCS_STATUS"
    exit "$VCS_STATUS"
fi

if grep -Eq '^[[:space:]]*(Error-|Error:|Fatal:)' vcs_compile.log; then
    echo "Error: vcs_compile.log contains Error/Fatal messages"
    exit 3
fi

set +e
./simv -l sim.log "${SIMV_EXTRA_ARGS[@]}"
SIM_STATUS="$?"
set -e

if [ "$SIM_STATUS" -ne 0 ]; then
    echo "Error: simv exited with status $SIM_STATUS"
    exit "$SIM_STATUS"
fi

if grep -Eq '^[[:space:]]*(Error-|Error:|Fatal:)' sim.log || grep -q ' FAIL' sim.log; then
    echo "Error: sim.log contains failure messages"
    exit 4
fi

if ! grep -q ' PASS' sim.log; then
    echo "Error: sim.log does not contain a PASS marker"
    exit 5
fi

if [ ! -f sim.vcd ]; then
    echo "Error: missing output sim.vcd"
    exit 6
fi

# The TB's power-phase toggle window; this is the activity file the vectored
# PrimeTime run consumes (autopwr prefers sim.saif over sim.vcd).
if [ ! -f sim.saif ]; then
    echo "Error: missing output sim.saif"
    exit 6
fi

echo "Gate-level simulation completed successfully: $RUN_DIR"
