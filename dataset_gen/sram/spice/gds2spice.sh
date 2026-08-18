#!/bin/bash
#
# gds2spice.sh — GDS to SPICE conversion via ICV + icv_nettran + StarXtract
#                (node-aware version; supersedes 20_wd_spice/20_col_spice copies)
#
# Usage:
#   ./gds2spice.sh --node <N> <gds_file_or_cell> [cellname] [--keep]
#                  [--outdir <dir>]
#
# Arguments:
#   --node N  : technology node (20 | 16 | 10 | 7 | 5, "nm" suffix optional)
#   gds_file_or_cell :
#       path to a GDS file, OR a bare cell name resolved against
#       TECH_<N>nm/<name>/01_gds/<name>.gds and then the node's SRAM
#       library store  tech_libs/techlib_<N>nm/sram/gds/<name>.gds
#   cellname  : top-cell name (default: GDS basename without .gds)
#   --keep    : keep the intermediate work directory even on success
#   --outdir  : where the keepers land (default: TECH_<N>nm/<cell>/02_pex;
#               the decoder flow passes <cell>/04_pex)
#
# Node collateral comes from the shared dataset_gen/tech_libs/ tree, resolved
# via catalog.json (scripts/tech_paths.py): filenames are declared in
# techlib_<N>nm/sram/node.env. Tech files (NXTGRD, LAYOUT_TF) live in the
# techlib root ONLY; the SRAM-specific ICV/StarRC setup (LVS runset, map,
# template) lives in the sram/ pack ONLY.
#
# Output (per config, in the outdir):
#   <cell>.sp             — SPICE netlist (icv_nettran)
#   <cell>.spef           — parasitics (StarXtract)
#   <cell>.RESULTS        — ICV LVS summary
#   <cell>.LAYOUT_ERRORS  — ICV violation report
#
# Intermediates live in <outdir>/work_<timestamp>/ and are DELETED
# automatically on success (use --keep to retain). On failure the directory
# is kept for debugging.

set -e
set -o pipefail

# ── Helpers ──────────────────────────────────────────────────────────────────

usage() {
    echo "Usage: $0 --node <20|16|10|7|5> <gds_file> [cellname] [--keep] [--outdir <dir>]"
    exit 1
}

die() { echo "Error: $*" >&2; exit 1; }

banner() {
    echo ""
    echo "================================================================"
    echo "  $*"
    echo "================================================================"
}

# 20|20nm|07|7nm... -> canonical directory name like "07nm"
normalize_node() {
    local n="${1%nm}"
    n=$((10#$n)) 2>/dev/null || die "Bad node spec: $1"
    printf "%02dnm" "$n"
}

# ── Argument parsing ─────────────────────────────────────────────────────────

NODE=""
KEEP=0
OUTDIR_OVR=""
POS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --node) NODE="$2"; shift 2 ;;
        --keep) KEEP=1; shift ;;
        --outdir) OUTDIR_OVR="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) POS+=("$1"); shift ;;
    esac
done

[ -n "$NODE" ]        || usage
[ ${#POS[@]} -ge 1 ]  || usage

# ── Node environment (shared tech_libs, via catalog.json) ────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRAM_DIR="$(realpath "$SCRIPT_DIR/..")"
NN="$(normalize_node "$NODE")"
TECH_NODE_DIR="$SRAM_DIR/TECH_$NN"

eval "$(python3 "$SCRIPT_DIR/scripts/tech_paths.py" --node "$NODE")" \
    || die "tech_paths.py failed for node $NODE"
[ -n "$TECH_SRAM" ] || die \
"node $NODE has no SRAM library (no sramdir in tech_libs/catalog.json)"

[ -f "$TECH_SRAM/node.env" ] || die "Missing $TECH_SRAM/node.env"
# shellcheck disable=SC1091
source "$TECH_SRAM/node.env"

# ── Resolve GDS: explicit path, config store, or the SRAM library store ─────

GDS_ARG="${POS[0]}"
BARE="${GDS_ARG%.gds}"
if [ -f "$GDS_ARG" ]; then
    GDS_FILE="$(realpath "$GDS_ARG")"
elif [ -f "$TECH_NODE_DIR/$BARE/01_gds/$BARE.gds" ]; then
    GDS_FILE="$TECH_NODE_DIR/$BARE/01_gds/$BARE.gds"
elif [ -f "$TECH_SRAM/gds/$BARE.gds" ]; then
    GDS_FILE="$TECH_SRAM/gds/$BARE.gds"
else
    die "GDS not found: '$GDS_ARG' (no such file, no $TECH_NODE_DIR/$BARE/01_gds/$BARE.gds, no $TECH_SRAM/gds/$BARE.gds)"
fi

CELLNAME="${POS[1]:-$(basename "$GDS_FILE" .gds)}"

# ── Collateral files: tech files from the techlib root, SRAM-specific setup
#    from the sram/ pack — one authoritative location each, no fallbacks.
# LAYOUT_TF is not consumed by the automated steps (kept for interactive
# Custom Compiler work) but must be present so every run dir is self-contained.

resolve_in() {  # resolve_in <dir> <filename>
    [ -s "$1/$2" ] && echo "$1/$2" || die "Missing/empty collateral file: $1/$2"
}

NEEDED=()
for f in "$NXTGRD" "$LAYOUT_TF"; do
    NEEDED+=("$(resolve_in "$TECH_LIB_DIR" "$f")")
done
for f in "$LVS_RS" "$STARRC_MAP" "$STRC_TEMPLATE"; do
    NEEDED+=("$(resolve_in "$TECH_SRAM" "$f")")
done

# ── Directory setup ──────────────────────────────────────────────────────────

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUTDIR_OVR:-$TECH_NODE_DIR/$CELLNAME/02_pex}"
RUN_DIR="$OUT_DIR/work_${TIMESTAMP}"

mkdir -p "$RUN_DIR"

trap '[ -d "$RUN_DIR" ] && echo "" && echo "FAILED — work directory kept for debugging: $RUN_DIR"' ERR

banner "GDS -> SPICE  |  node: $NODE_NAME  |  cell: $CELLNAME"
echo "  GDS file : $GDS_FILE"
echo "  Run dir  : $RUN_DIR"
echo "  Output   : $OUT_DIR"

# ── Populate run directory (symlinks by basename — the StarRC template
#    references NXTGRD/MAPPING_FILE by these exact names) ────────────────────

for f in "${NEEDED[@]}"; do
    ln -sf "$f" "$RUN_DIR/$(basename "$f")"
done

ln -sf "$GDS_FILE" "$RUN_DIR/${CELLNAME}.gds"

# Per-run StarXtract runset from the node's template
sed "s/@CELLNAME@/${CELLNAME}/g" "$TECH_SRAM/$STRC_TEMPLATE" \
    > "$RUN_DIR/${CELLNAME}.strc"

cd "$RUN_DIR"

# ── Step 1: ICV — extract netlist from GDS ──────────────────────────────────

banner "Step 1: ICV netlist extraction"
icv -i "${CELLNAME}.gds" -c "${CELLNAME}" -ex "$LVS_RS" \
    2>&1 | tee icv.log

if [ -f "${CELLNAME}.RESULTS" ]; then
    head -2 "${CELLNAME}.RESULTS" | grep -i "RESULTS" || true
fi

# ICV may write <cell>.net or <cell>.net.gz depending on version.
NET_FILE="${CELLNAME}.net"
if [ ! -f "$NET_FILE" ]; then
    if [ -f "${NET_FILE}.gz" ]; then
        echo "Decompressing ${NET_FILE}.gz"
        gunzip -kf "${NET_FILE}.gz"
    else
        die "ICV did not produce ${NET_FILE} or ${NET_FILE}.gz"
    fi
fi

# ── Step 2: icv_nettran — convert ICV netlist to SPICE ──────────────────────

banner "Step 2: icv_nettran — ICV -> SPICE"
icv_nettran -icv "${NET_FILE}" -outName "${CELLNAME}.sp" -outType SPICE \
    2>&1 | tee icv_nettran.log

[ -f "${CELLNAME}.sp" ] || die "icv_nettran did not produce ${CELLNAME}.sp"

# ── Step 3: StarXtract — parasitic RC extraction ────────────────────────────

banner "Step 3: StarXtract — RC extraction"
StarXtract "${CELLNAME}.strc" \
    2>&1 | tee starxtract.log

[ -f "${CELLNAME}.spef" ] || die "StarXtract did not produce ${CELLNAME}.spef"

# ── Collect outputs ──────────────────────────────────────────────────────────

banner "Collecting outputs -> $OUT_DIR"

for ext in sp spef RESULTS LAYOUT_ERRORS; do
    if [ -f "${CELLNAME}.${ext}" ]; then
        cp "${CELLNAME}.${ext}" "$OUT_DIR/"
        echo "  Saved: $OUT_DIR/${CELLNAME}.${ext}"
    fi
done

if grep -q "NOT CLEAN" "$OUT_DIR/${CELLNAME}.RESULTS" 2>/dev/null; then
    echo ""
    echo "  WARNING: ICV reports NOT CLEAN — check $OUT_DIR/${CELLNAME}.LAYOUT_ERRORS"
fi

# ── Cleanup ──────────────────────────────────────────────────────────────────

trap - ERR
cd "$SCRIPT_DIR"

if [ "$KEEP" = "1" ]; then
    echo ""
    echo "  Intermediates kept (--keep): $RUN_DIR"
else
    rm -rf "$RUN_DIR"
    echo ""
    echo "  Work directory removed (use --keep to retain intermediates)."
fi

banner "Done"
echo "  SPICE netlist  : $OUT_DIR/${CELLNAME}.sp"
echo "  SPEF parasitic : $OUT_DIR/${CELLNAME}.spef"
