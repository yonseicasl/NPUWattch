#!/bin/bash
# run_wd.sh — Write driver SPICE simulation for any wd_X* cell (node-aware)
#
# Usage:
#   ./run_wd.sh --node <N> <cellname>          — pre-layout (HSPICE, no parasitics)
#   ./run_wd.sh --node <N> <cellname> --pex    — post-layout (HSPICE + SPEF ba_file)
#
# Examples:
#   ./run_wd.sh --node 20 wd_X8
#   ./run_wd.sh --node 16 wd_X16 --pex
#
# Reads <cell>.sp / <cell>.spef from TECH_<N>nm/<cell>/02_pex/ (run
# gds2spice.sh first); VDD / TEMP / BL_CAP and the model cards come from the
# node's SRAM library in tech_libs (techlib_<N>nm/sram/, via catalog.json).
#
# Each invocation creates an isolated run directory:
#   TECH_<N>nm/<cellname>/03_sim/<cellname>_<YYYYMMDD_HHMMSS>/
# Waveforms (.tr0) are the point of a behavior run, so nothing is deleted
# automatically here; use sram/clean_all.sh to purge old runs.

set -e
set -o pipefail

usage() {
    echo "Usage: $0 --node <20|16|10|7|5> <cellname> [--pex]"
    echo "  e.g.: $0 --node 20 wd_X8"
    echo "        $0 --node 20 wd_X4 --pex"
    exit 1
}
die() { echo "Error: $*" >&2; exit 1; }

normalize_node() {
    local n="${1%nm}"
    n=$((10#$n)) 2>/dev/null || die "Bad node spec: $1"
    printf "%02dnm" "$n"
}

# ── Argument parsing ─────────────────────────────────────────────────────────

NODE=""
PEX=0
POS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --node) NODE="$2"; shift 2 ;;
        --pex)  PEX=1; shift ;;
        -h|--help) usage ;;
        *) POS+=("$1"); shift ;;
    esac
done

[ -n "$NODE" ]       || usage
[ ${#POS[@]} -ge 1 ] || usage
CELLNAME="${POS[0]}"

# ── Node environment ─────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRAM_DIR="$(realpath "$SCRIPT_DIR/..")"
NN="$(normalize_node "$NODE")"

eval "$(python3 "$SRAM_DIR/spice/scripts/tech_paths.py" --node "$NODE")" \
    || die "tech_paths.py failed for node $NODE"
[ -n "$TECH_SRAM" ] || die \
"node $NODE has no SRAM library (no sramdir in tech_libs/catalog.json)"
[ -f "$TECH_SRAM/node.env" ] || die "Missing $TECH_SRAM/node.env"
# shellcheck disable=SC1091
source "$TECH_SRAM/node.env"

CFG_DIR="$SRAM_DIR/TECH_$NN/$CELLNAME"
OUT_DIR="$CFG_DIR/02_pex"
TEMPLATE="$SCRIPT_DIR/lib/tb_wd_template.sp"
TIE_BULK="$SRAM_DIR/spice/scripts/tie_bulk.py"

[ -f "$TEMPLATE" ] || die "Template not found: $TEMPLATE"
[ -f "$TIE_BULK" ] || die "tie_bulk.py not found: $TIE_BULK"

# Model cards must be real, not stubs
for f in nmos1.inc pmos1.inc; do
    [ -f "$TECH_SRAM/models/$f" ] || die "Missing model card: $TECH_SRAM/models/$f"
    [ -s "$TECH_SRAM/models/$f" ] || die \
"$TECH_SRAM/models/$f is an empty stub.
Copy the real $NODE_NAME model card in first (see array/README.md)."
done

# Resolve source sp (and spef when --pex) from out/
[ -f "$OUT_DIR/${CELLNAME}.sp" ] || die "Not found: $OUT_DIR/${CELLNAME}.sp (run gds2spice.sh first)"
if [ "$PEX" = "1" ]; then
    [ -f "$OUT_DIR/${CELLNAME}.spef" ] || die "Not found: $OUT_DIR/${CELLNAME}.spef (run gds2spice.sh first)"
fi

# ── Run directory ────────────────────────────────────────────────────────────

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$CFG_DIR/03_sim/${CELLNAME}_${TIMESTAMP}"
mkdir -p "$RUN_DIR"

echo "Node    : $NODE_NAME  (VDD=${VDD}V, TEMP=${TEMP}C, BL_CAP=${BL_CAP})"
echo "Run dir : $RUN_DIR"

# Tie bulk terminals (nmos1->VSS, pmos1->VDD) and copy to run directory
python3 "$TIE_BULK" "$OUT_DIR/${CELLNAME}.sp" "$RUN_DIR/${CELLNAME}.sp"
[ "$PEX" = "1" ] && ln -sfr "$OUT_DIR/${CELLNAME}.spef" "$RUN_DIR/${CELLNAME}.spef"
ln -sfn "$TECH_SRAM/models" "$RUN_DIR/models"

# Generate testbench from template into run directory.
# Post-layout uses HSPICE SPEF back-annotation via .option ba_file — the
# mechanism validated by the 20nm column flow (primesim -spef is not
# supported by the installed PrimeSim version).
if [ "$PEX" = "1" ]; then
    BA_LINE=".option ba_file='./${CELLNAME}.spef'"
else
    BA_LINE="* pre-layout run — no parasitic back-annotation"
fi

# DUT port order: read from the extracted .SUBCKT so the TB works for any
# cell port ordering/naming (e.g. the 10nm native cell uses
# "data write BL BLB VSS VDD"). Cell port names are mapped onto the
# canonical TB nets; unknown port names abort.
XDUT_PORTS=$(python3 - "$OUT_DIR/${CELLNAME}.sp" << 'PYEOF'
import re, sys
text = re.sub(r'\n\+', ' ', open(sys.argv[1]).read())
for line in text.splitlines():
    t = line.split()
    if t and t[0].upper() == '.SUBCKT':
        alias = {'BLB': 'BL_bar', 'blb': 'BL_bar'}
        known = {'BL', 'BL_bar', 'data', 'write', 'VDD', 'VSS'}
        ports = [alias.get(p, p) for p in t[2:]]
        bad = [p for p in ports if p not in known]
        if bad:
            sys.stderr.write('unknown DUT ports: %s\n' % bad)
            sys.exit(1)
        print(' '.join(ports))
        sys.exit(0)
sys.exit(1)
PYEOF
) || die "Could not derive DUT port order from $OUT_DIR/${CELLNAME}.sp"
echo "DUT ports: $XDUT_PORTS"

# Verilog-A model loading (BSIM-CMG at 5nm): node.env sets MODEL_HDL to a
# path under models/; empty means the card is a native .model (no .hdl).
if [ -n "${MODEL_HDL:-}" ]; then
    [ -f "$TECH_SRAM/models/$MODEL_HDL" ] || die "MODEL_HDL not found: $TECH_SRAM/models/$MODEL_HDL"
    HDL_LINE=".hdl './models/${MODEL_HDL}'"
else
    HDL_LINE="* (native .model card — no Verilog-A to load)"
fi

TB_FILE="$RUN_DIR/tb_${CELLNAME}.sp"
sed -e "s/@CELLNAME@/${CELLNAME}/g" \
    -e "s/@NODE@/${NODE_NAME}/g" \
    -e "s/@VDD@/${VDD}/g" \
    -e "s/@TEMP@/${TEMP}/g" \
    -e "s/@BL_CAP@/${BL_CAP}/g" \
    -e "s|@BA_LINE@|${BA_LINE}|g" \
    -e "s|@HDL_LINE@|${HDL_LINE}|g" \
    -e "s|@XDUT_PORTS@|${XDUT_PORTS}|g" \
    "$TEMPLATE" > "$TB_FILE"

cd "$RUN_DIR"

if [ "$PEX" = "1" ]; then
    echo "=== Post-layout: $CELLNAME (SPEF back-annotation via ba_file) ==="
    hspice "$TB_FILE" -o "tb_${CELLNAME}_pex" \
        2>&1 | tee "sim.log"
    echo "Done — results: $RUN_DIR/tb_${CELLNAME}_pex.*"
else
    echo "=== Pre-layout: $CELLNAME ==="
    hspice "$TB_FILE" -o "tb_${CELLNAME}" \
        2>&1 | tee "sim.log"
    echo "Done — results: $RUN_DIR/tb_${CELLNAME}.*"
fi

echo "To clean up old runs: $SRAM_DIR/clean_all.sh"
