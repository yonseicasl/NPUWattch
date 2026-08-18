#!/bin/bash
# run_decoder.sh -- full SRAM row-decoder characterization for one config:
#
#   RTL gen -> DC synthesis -> ICC2 PnR (array-pitch-matched floorplan)
#   -> GDS text-layer remap + rail labels -> ICV GDS2SPICE + StarRC PEX
#   (via spice/gds2spice.sh) -> HSPICE transient with array-WL RC loads.
#
# Usage:
#   ./run_decoder.sh --node <N> --rows <R> --cols <C>
#                    [--util 0.70] [--clk 10] [--vdd <V>] [--temp <C>]
#                    [--no-pex] [--reuse-gds] [--height-um <H>]
#
#   --util       floorplan target utilization (width = cell_area/(util*H)).
#                Default is auto: a row/node-aware value that keeps the
#                tall-narrow decoder die routable at any wordline count
#                (min(cap,C/rows); see the auto-util block below). Pass a
#                value to override.
#   --clk        DC clock period ns (default 10 = SRAM flow op cadence)
#   --reuse-gds  skip RTL/DC/ICC2/edit if TECH_<N>nm/dec_<R>x<C>/03_gds/
#                already holds the merged GDS (+ sidecar)
#   --height-um  override the die height (default: array sidecar height)
#
# Stage dirs (in creation order) under TECH_<N>nm/dec_<R>x<C>/:
#   01_syn (DC) -> 02_pnr (ICC2) -> 03_gds (remap/labels/merge + sidecar)
#   -> 04_pex (ICV+StarRC keepers) -> 05_sim/<run_id>/ (HSPICE)
#
# Requires: an array extraction at the node for the WL load
# (TECH_<N>nm/array_X*/02_pex/*.spef) and the array sidecar json for the
# height (see wl_load.py fallbacks).
#
# Tool env (override in decoder/site.env, git-ignored):
#   DC_ENV / ICC2_ENV : csh env scripts sourced before dc_shell/icc2_shell
#   GDT_DIR           : gds2gdt/gdt2gds location

set -e
set -o pipefail

usage() { sed -n '2,20p' "$0"; exit 1; }
die() { echo "Error: $*" >&2; exit 1; }
normalize_node() {
    local n="${1%nm}"
    n=$((10#$n)) 2>/dev/null || die "Bad node spec: $1"
    printf "%02dnm" "$n"
}

NODE="" ROWS="" COLS="" UTIL="" CLK_NS=10 PEX=1 REUSE=0
VDD_OVR="" TEMP_OVR="" H_OVR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --node) NODE="$2"; shift 2 ;;
        --rows) ROWS="$2"; shift 2 ;;
        --cols) COLS="$2"; shift 2 ;;
        --util) UTIL="$2"; shift 2 ;;
        --clk)  CLK_NS="$2"; shift 2 ;;
        --vdd)  VDD_OVR="$2"; shift 2 ;;
        --temp) TEMP_OVR="$2"; shift 2 ;;
        --no-pex) PEX=0; shift ;;
        --reuse-gds) REUSE=1; shift ;;
        --height-um) H_OVR="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) die "unknown arg: $1" ;;
    esac
done
[ -n "$NODE" ] && [ -n "$ROWS" ] && [ -n "$COLS" ] || usage

DEC_DIR="$(cd "$(dirname "$0")" && pwd)"
SRAM_DIR="$(realpath "$DEC_DIR/..")"
SPICE_DIR="$SRAM_DIR/spice"
SCRIPTS="$DEC_DIR/scripts"
NN="$(normalize_node "$NODE")"
TECH_NODE_DIR="$SRAM_DIR/TECH_$NN"

# ── row/node-aware default utilization ───────────────────────────────────────
# The pitch-matched decoder die grows tall-and-narrow with wordline count (H is
# fixed to the array pitch, so at fixed util the width barely changes and the
# M3/M5/M7 vertical tracks starve -> router gives up -> merged nets -> a dead
# short on wl0).  To keep it routable the utilization must fall ~1/rows.  The
# constants below are the tightest (narrowest) util verified to route+sim clean
# across an 8..512 WL sweep, backed off one step for margin (2026-07-14):
#   20/10nm : min(0.70, 14/rows)      16/07nm : min(0.70, 12/rows)
#   05nm    : min(0.45, 10/rows)      (5nm is the tightest; never start >0.45)
# Override any time with --util; an explicit value is honored verbatim.
if [ -z "$UTIL" ]; then
    case "$NN" in
        05nm)       ucap=0.45; ucon=10 ;;
        16nm|07nm)  ucap=0.70; ucon=12 ;;
        *)          ucap=0.70; ucon=14 ;;
    esac
    UTIL="$(awk -v r="$ROWS" -v c="$ucon" -v cap="$ucap" \
        'BEGIN{u=c/r; if(u>cap)u=cap; printf "%.4g", u}')"
    UTIL_AUTO=1
fi

# ── library collateral from the shared tech_libs catalog ─────────────────────
eval "$(python3 "$SPICE_DIR/scripts/tech_paths.py" --node "$NODE")" \
    || die "tech_paths.py failed for node $NODE"
[ -n "$TECH_SRAM" ] || die \
"node $NODE has no SRAM library (no sramdir in tech_libs/catalog.json)"
[ -n "$TECH_GDS" ] || die \
"node $NODE has no std-cell GDS store (no gdsdir in tech_libs/catalog.json)"
source "$TECH_SRAM/node.env"

# tool environment (site-overridable)
DC_ENV=~/sources/dc23.cshrc
ICC2_ENV=~/sources/icc2_23.12-SP4.cshrc
GDT_DIR=/usr/etc/GDT-4.0.4
DEC_LOAD_SCALE="${DEC_LOAD_SCALE:-1000}"   # pF -> DC lib cap unit (i3d .db: fF)
[ -f "$DEC_DIR/site.env" ] && source "$DEC_DIR/site.env"
export PATH="$PATH:$GDT_DIR"

VDD_NOM="$VDD"
[ -n "$VDD_OVR" ]  && VDD="$VDD_OVR"
[ -n "$TEMP_OVR" ] && TEMP="$TEMP_OVR"
VOFFSET="$(awk -v a="$VDD" -v b="$VDD_NOM" 'BEGIN{printf "%.4g", a-b}')"

TOP="dec_${ROWS}x${COLS}"
WORK="$TECH_NODE_DIR/$TOP"
GDS_OUT="$WORK/03_gds"
SIDColl="$GDS_OUT/${TOP}.json"

echo "Node    : $NODE_NAME  (VDD=${VDD}V, TEMP=${TEMP}C)"
echo "Decoder : $TOP  (util target $UTIL${UTIL_AUTO:+ auto:row-aware}, clk ${CLK_NS} ns)"

# ── WL load + array height from the array flow ──────────────────────────────
WLJSON="$WORK/wl_load.json"
mkdir -p "$WORK"
python3 "$SCRIPTS/wl_load.py" --tech-dir "$TECH_NODE_DIR" \
    --rows "$ROWS" --cols "$COLS" > "$WLJSON"
jsget() { python3 -c "import json,sys;print(json.load(open('$WLJSON'))['$1'])"; }
WL_CAP_FF="$(jsget wl_cap_fF)"
WL_RES="$(jsget wl_res_ohm)"
H_UM="${H_OVR:-$(jsget array_height_um)}"
echo "WL load : ${WL_CAP_FF} fF / ${WL_RES} ohm  ($(jsget src_spef) x$(jsget col_scale))"
echo "Height  : ${H_UM} um  ($( [ -n "$H_OVR" ] && echo override || jsget src_sidecar))"

if [ "$REUSE" = "1" ] && [ -s "$GDS_OUT/${TOP}.gds" ] && [ -s "$SIDColl" ]; then
    echo "=== Reusing existing $GDS_OUT/${TOP}.gds ==="
else
    # ── 1. RTL ───────────────────────────────────────────────────────────────
    rm -rf "$WORK/01_syn" "$WORK/02_pnr" "$WORK/03_gds"
    mkdir -p "$WORK/01_syn" "$WORK/02_pnr" "$WORK/03_gds"
    python3 "$SCRIPTS/gen_decoder_rtl.py" --rows "$ROWS" --cols "$COLS" \
        -o "$WORK/01_syn/${TOP}.v"

    # ── 2. DC synthesis ─────────────────────────────────────────────────────
    export DEC_TOP="$TOP" DEC_RTL="./${TOP}.v" DEC_DB="$TECH_DB"
    export DEC_CLK_NS="$CLK_NS" DEC_WL_LOAD_PF="$(awk -v c="$WL_CAP_FF" \
        'BEGIN{printf "%.6g", c/1000.0}')" DEC_LOAD_SCALE
    echo "=== DC synthesis ($TOP) ==="
    ( cd "$WORK/01_syn" && \
      csh -c "source $DC_ENV >& /dev/null; dc_shell -f $SCRIPTS/dc.tcl" \
        > dc.log 2>&1 ) || { tail -30 "$WORK/01_syn/dc.log"; die "DC failed"; }
    grep -q "^Error" "$WORK/01_syn/dc.log" && \
        { grep "^Error" "$WORK/01_syn/dc.log" | head; die "DC reported errors"; }
    [ -s "$WORK/01_syn/${TOP}_syn.v" ] || die "DC produced no ${TOP}_syn.v"

    CELL_AREA="$(awk '/^Total cell area:/{print $4}' "$WORK/01_syn/area.rpt")"
    echo "DC done : cell area ${CELL_AREA} (DC units; ICC2 derives the width)"

    # ── 3. ICC2 PnR ──────────────────────────────────────────────────────────
    export DEC_NETLIST="../01_syn/${TOP}_syn.v" DEC_SDC="../01_syn/${TOP}.sdc"
    export DEC_NDM="$TECH_NDM" DEC_TECHFILE="$TECH_TF" DEC_TLUP="$TECH_TLUP"
    export DEC_LAYERMAP="$TECH_MAP" DEC_H_UM="$H_UM" DEC_UTIL="$UTIL"
    export DEC_ROWS="$ROWS"
    # strict in-pin via landings: was needed at 5nm ONLY while its NDM was
    # frame-only (tiny pins, internal wires 8 nm away -> off-pin via pads
    # shorted a DFF ckb wire); harmful at 20nm (merged decode nets).  The 5nm
    # NDM now carries real M0/M1 obstructions, so the router avoids those
    # landings natively -- strict is not only obsolete there but actively
    # generates "Diff net spacing" DRCs (6-11 per config at 5nm; turning it
    # off drops them to 0 with the sim result unchanged).  Default now OFF at
    # every node; override with DEC_PIN_VIA_STRICT=1 if an old frame-only NDM
    # is ever swapped back in.  See icc2.tcl.
    export DEC_PIN_VIA_STRICT="${DEC_PIN_VIA_STRICT:-0}"
    echo "=== ICC2 PnR ($TOP) ==="
    ( cd "$WORK/02_pnr" && \
      csh -c "source $ICC2_ENV >& /dev/null; icc2_shell -f $SCRIPTS/icc2.tcl" \
        > icc2.log 2>&1 ) || { tail -30 "$WORK/02_pnr/icc2.log"; die "ICC2 failed"; }
    [ -s "$WORK/02_pnr/${TOP}.gds" ]   || die "ICC2 produced no ${TOP}.gds"
    [ -s "$WORK/02_pnr/rails.json" ]   || die "ICC2 produced no rails.json"
    grep "^DECFP" "$WORK/02_pnr/icc2.log" || true

    # ── 4. GDS edit: text-layer remap + power-rail labels ───────────────────
    echo "=== GDS edit ($TOP) ==="
    cd "$WORK/03_gds"
    gds2gdt "../02_pnr/${TOP}.gds" "${TOP}.gdt"
    # strip width attributes from text records (gdt2gds rejects them; the
    # legacy flow's `s/w0.01/ /` did the same for its fixed pin size)
    sed -i -e '/^t{/s/ w[0-9.eE+-]*//g' -e 's/   / /g' "${TOP}.gdt"
    # ICC2 stream-out text numbering is identical at every node (incl. 5nm --
    # the "no remap at 5nm" convention applies to the custom SRAM GDT flow,
    # not to ICC2 output)
    sed -i -f "$SCRIPTS/text_layer_map.sed" "${TOP}.gdt"
    python3 "$SCRIPTS/label_rails.py" "${TOP}.gdt" "../02_pnr/rails.json" \
        "$TOP" "${TOP}_labeled.gdt"
    gdt2gds "${TOP}_labeled.gdt" "${TOP}_nocells.gds"
    # NDMs carry only frame views -> inject the real std-cell layouts from
    # the shared tech_libs GDS store (catalog gdsdir; needs gdstk => conda
    # python)
    PYTHON_GDSTK="${PYTHON_GDSTK:-$HOME/miniforge3/envs/npuwattch/bin/python3}"
    "$PYTHON_GDSTK" "$SCRIPTS/merge_stdcells.py" "${TOP}_nocells.gds" \
        "$TECH_GDS" -o "$GDS_OUT/${TOP}.gds"
    cd - > /dev/null

    # area sidecar (die box = layout-honest decoder area)
    python3 - "$WORK/02_pnr/dims.json" "$SIDColl" <<EOF
import json, sys
d = json.load(open(sys.argv[1]))
json.dump({"cell": "$TOP", "node": "$NODE_NAME",
           "rows": $ROWS, "cols": $COLS,
           "width_um": d["die_w_um"], "height_um": d["die_h_um"],
           "total_area_um2": d["die_area_um2"],
           "cell_area_um2": d["cell_area_um2"],
           "util_target": $UTIL,
           "util_achieved": round(d["cell_area_um2"] / d["die_area_um2"], 4)},
          open(sys.argv[2], "w"), indent=1)
print("sidecar:", sys.argv[2])
EOF
fi

# ── 5. LVS + PEX (shared, validated per-node extraction) ─────────────────────
PEX_DIR="$WORK/04_pex"
if [ "$REUSE" = "1" ] && [ -s "$PEX_DIR/${TOP}.sp" ] \
        && { [ "$PEX" = "0" ] || [ -s "$PEX_DIR/${TOP}.spef" ]; }; then
    echo "=== Reusing existing extraction $PEX_DIR/${TOP}.sp ==="
else
    echo "=== GDS2SPICE + StarRC ($TOP) ==="
    "$SPICE_DIR/gds2spice.sh" --node "$NODE" "$GDS_OUT/${TOP}.gds" "$TOP" \
        --outdir "$PEX_DIR"
fi

# ── 6. HSPICE transient ──────────────────────────────────────────────────────
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$WORK/05_sim/${TOP}_v${VDD}_t${TEMP}_${TIMESTAMP}"
mkdir -p "$RUN_DIR"
python3 "$SPICE_DIR/scripts/tie_bulk.py" "$PEX_DIR/${TOP}.sp" \
    "$RUN_DIR/${TOP}.sp"
[ "$PEX" = "1" ] && ln -sfr "$PEX_DIR/${TOP}.spef" "$RUN_DIR/${TOP}.spef"
ln -sfn "$TECH_SRAM/models" "$RUN_DIR/models"
cp "$SIDColl" "$RUN_DIR/area.json"
cp "$WLJSON" "$RUN_DIR/wl_load.json" 2>/dev/null || true

BA_ARG=(); [ "$PEX" = "1" ] && BA_ARG=(--ba "${TOP}.spef")
HDL_ARG=(); [ -n "${MODEL_HDL:-}" ] && HDL_ARG=(--hdl "$MODEL_HDL")
TB_FILE="$RUN_DIR/tb_${TOP}.sp"
python3 "$SCRIPTS/gen_dec_tb.py" "$RUN_DIR/${TOP}.sp" \
    --cellname "$TOP" --vdd "$VDD" --temp "$TEMP" --node "$NODE_NAME" \
    --wl-cap-ff "$WL_CAP_FF" --wl-res-ohm "$WL_RES" \
    "${BA_ARG[@]}" "${HDL_ARG[@]}" -o "$TB_FILE" | grep -v "^META"

cat > "$RUN_DIR/meta.json" <<EOF
{
 "cell": "$TOP", "node": "$NODE_NAME",
 "rows": $ROWS, "cols": $COLS,
 "vdd_V": $VDD, "temperature_C": $TEMP, "pex": $PEX,
 "transistor": "${FLAVOR:-hp}", "corner": "${CORNER:-TT}",
 "voltage_offset_V": ${VOFFSET:-0.0},
 "wl_cap_fF": $WL_CAP_FF, "wl_res_ohm": $WL_RES,
 "util_target": $UTIL, "clk_ns": $CLK_NS,
 "flow_run_id": "${TOP}_v${VDD}_t${TEMP}_${TIMESTAMP}"
}
EOF

cd "$RUN_DIR"
SUFFIX=""; [ "$PEX" = "1" ] && SUFFIX="_pex"
echo "=== HSPICE ($TOP$SUFFIX) ==="
hspice "$TB_FILE" -o "tb_${TOP}${SUFFIX}" 2>&1 | tee "sim.log" \
    | grep -Ei "error|warning: *(too|conv)|aborted|\*\*\*" || true
MT0="tb_${TOP}${SUFFIX}.mt0"
[ -f "$MT0" ] || die "no $MT0 produced -- see $RUN_DIR/sim.log"
echo
PYTHONPATH="$SRAM_DIR/array/scripts" python3 "$SCRIPTS/dec_measures.py" \
    "$MT0" --vdd "$VDD" --rows "$ROWS" -o "measures.csv"
echo "Results: $RUN_DIR"
