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
    RUN_DIR="$SCRIPT_DIR/../02_pnr/$RUN_ARG"
fi

if [ ! -d "$RUN_DIR" ]; then
    echo "Error: run directory not found: $RUN_DIR"
    exit 1
fi
RUN_DIR="$(cd "$RUN_DIR" && pwd)"

if [ ! -f "$RUN_DIR/02_pnr.tcl" ]; then
    echo "Error: $RUN_DIR/02_pnr.tcl not found"
    exit 1
fi

cd "$RUN_DIR"

tcl_var() {
    awk -v name="$1" '$1 == "set" && $2 == name {gsub(/^"/, "", $3); gsub(/"$/, "", $3); print $3; exit}' 02_pnr.tcl
}

TOP_MODULE="$(tcl_var maindesign)"
TECH_FILE="$(tcl_var Tech_file)"

if [ -z "$TOP_MODULE" ]; then
    echo "Error: could not find maindesign in $RUN_DIR/02_pnr.tcl"
    exit 1
fi

if [ -z "$TECH_FILE" ]; then
    echo "Error: could not find Tech_file in $RUN_DIR/02_pnr.tcl"
    exit 1
fi

if [[ "$TECH_FILE" != /* ]]; then
    TECH_FILE="$RUN_DIR/$TECH_FILE"
fi

if [ ! -f "$TECH_FILE" ]; then
    echo "Error: technology file not found: $TECH_FILE"
    exit 1
fi

if grep -Eq 'Layer[[:space:]]+"metal1"' "$TECH_FILE"; then
    LAYER_PREFIX="metal"
elif grep -Eq 'Layer[[:space:]]+"M1"' "$TECH_FILE"; then
    LAYER_PREFIX="M"
else
    echo "Error: could not detect metal layer naming convention in $TECH_FILE"
    exit 1
fi

MAX_LAYER="$(
    grep -Eo 'Layer[[:space:]]+"(metal|M)[0-9]+"' "$TECH_FILE" \
        | sed -E 's/.*(metal|M)([0-9]+)".*/\2/' \
        | sort -n \
        | tail -1
)"
if [ -z "$MAX_LAYER" ]; then
    echo "Error: could not detect routing layer count in $TECH_FILE"
    exit 1
fi

layer_name() {
    if [ "$LAYER_PREFIX" = "metal" ]; then
        printf 'metal%s' "$1"
    else
        printf 'M%s' "$1"
    fi
}

horizontal_layers=()
vertical_layers=()
for ((layer = 1; layer <= MAX_LAYER; layer++)); do
    if ((layer % 2 == 1)); then
        horizontal_layers+=("$(layer_name "$layer")")
    else
        vertical_layers+=("$(layer_name "$layer")")
    fi
done

M1_LAYER="$(layer_name 1)"
HORIZONTAL_LAYERS="${horizontal_layers[*]}"
VERTICAL_LAYERS="${vertical_layers[*]}"
LAYER_SNIPPET=".pnr_layer_script.tcl"

{
    echo "set m1_layer \"$M1_LAYER\""
    echo "set horizontal_layers {$HORIZONTAL_LAYERS}"
    echo "set vertical_layers {$VERTICAL_LAYERS}"
} > "$LAYER_SNIPPET"

if ! grep -q '#START_OF_PNR_LAYER_SCRIPT' 02_pnr.tcl || ! grep -q '#END_OF_PNR_LAYER_SCRIPT' 02_pnr.tcl; then
    echo "Error: 02_pnr.tcl is missing PnR layer injection markers"
    exit 1
fi

awk '
    FILENAME == ARGV[1] {
        layer_lines[++layer_count] = $0
        next
    }
    $0 ~ /#START_OF_PNR_LAYER_SCRIPT/ {
        print
        for (i = 1; i <= layer_count; i++) {
            print layer_lines[i]
        }
        in_layer_block = 1
        next
    }
    $0 ~ /#END_OF_PNR_LAYER_SCRIPT/ {
        in_layer_block = 0
        print
        next
    }
    !in_layer_block {
        print
    }
' "$LAYER_SNIPPET" 02_pnr.tcl > 02_pnr.tcl.tmp
mv 02_pnr.tcl.tmp 02_pnr.tcl
rm -f "$LAYER_SNIPPET"

echo "Using routing layers:"
echo "  m1_layer:          $M1_LAYER"
echo "  horizontal_layers: $HORIZONTAL_LAYERS"
echo "  vertical_layers:   $VERTICAL_LAYERS"

set +e
icc2_shell -f 02_pnr.tcl 2>&1 | tee pnr.log
ICC2_STATUS="${PIPESTATUS[0]}"
set -e

if [ "$ICC2_STATUS" -ne 0 ]; then
    echo "Error: icc2_shell exited with status $ICC2_STATUS"
    exit "$ICC2_STATUS"
fi

if grep -Eq '^[[:space:]]*(Error:|Fatal:)' pnr.log; then
    echo "Error: pnr.log contains Error/Fatal messages"
    exit 2
fi

if [ ! -f "${TOP_MODULE}_icc2.v" ]; then
    echo "Error: missing output ${TOP_MODULE}_icc2.v"
    exit 3
fi

if [ ! -f "${TOP_MODULE}.sdf" ]; then
    echo "Error: missing output ${TOP_MODULE}.sdf"
    exit 4
fi

if [ ! -f "${TOP_MODULE}.gds" ]; then
    echo "Error: missing output ${TOP_MODULE}.gds"
    exit 5
fi

if [ ! -f "${TOP_MODULE}.def" ]; then
    echo "Error: missing output ${TOP_MODULE}.def"
    exit 6
fi

echo "PnR completed successfully: $RUN_DIR"
