#!/bin/bash
# run_batch.sh — run a list of SRAM characterization jobs end-to-end
#                (array flow + the matching decoder per configuration).
#
# Usage:
#   ./run_batch.sh [jobs.csv] [--dry-run] [--no-collect] [--stop-on-fail]
#                  [--no-dec]
#
# Job list (CSV, '#' comments and the header line ignored):
#   node,rows,cols,wd,toggle_rate,vdd_V,temp_C,pex
#     node        20|16|10|7|5                                (required)
#     rows        bitcells per column                         (required)
#     cols        columns = word width                        (required)
#     wd          write-driver strength S; blank = smallest strength with
#                 clean write margin for this row count (phase-2 map:
#                 ceil(rows/8) rounded up to the node unit, floor X4 at 5nm)
#     toggle_rate fraction of columns flipping in the toggle-write op;
#                 blank = 1.0
#     vdd_V       supply override; blank = node nominal (from the node's
#                 tech_libs .../sram/node.env). The dataset's
#                 voltage_offset_V is measured against nominal.
#     temp_C      temperature override; blank = node.env TEMP (25)
#     pex         1 = post-layout (SPEF back-annotation, default), 0 = pre
#
# For each job the script builds whatever collateral is missing —
# wd ladder (gen_wd.py, when strength > the node unit), column GDS
# (gen_col.py), array GDS + area sidecar (gen_array.py),
# extraction (gds2spice.sh) — then simulates via run_array.sh, and runs the
# matching DECODER characterization (decoder/run_decoder.sh --reuse-gds;
# needs dc_shell/icc2_shell licenses).  The decoder depends only on
# (node, rows, cols, vdd, temp, pex) — duplicate points in the list (e.g. a
# toggle-rate sweep) run it once; --reuse-gds skips DC/ICC2/PEX when the
# collateral already exists from an earlier batch, so only the HSPICE sim
# repeats.  --no-dec skips the decoder stage entirely.
#
# Afterwards collect_array.py rebuilds datasets/sram_array.csv and
# collect_decoder.py rebuilds sram_decoder.csv + joins the decoder area
# into the array sheet (latest run per config key wins).  Jobs run
# sequentially (one HSPICE license); a failed job is logged and the batch
# continues unless --stop-on-fail.
#
# Site setup: copy site.env.example to site.env (git-ignored) and set
# PYTHON_GDSTK to a python3 with gdstk — needed to generate missing GDS,
# to resolve blank wd fields, and for the decoder std-cell merge.  Logs
# land in autosweep/logs/.

set -o pipefail

die() { echo "Error: $*" >&2; exit 1; }

BATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
SRAM="$(realpath "$BATCH_DIR/..")"
SP="$SRAM/spice"
ARR="$SRAM/array"
DEC="$SRAM/decoder"
[ -d "$SP" ] && [ -d "$ARR" ] && [ -d "$DEC" ] \
    || die "expected sibling spice/, array/ and decoder/ dirs"

# shellcheck disable=SC1091
[ -f "$BATCH_DIR/site.env" ] && source "$BATCH_DIR/site.env"
PY="${PYTHON_GDSTK:-python3}"
# run_decoder.sh needs a gdstk python for the std-cell merge
[ -n "$PYTHON_GDSTK" ] && export PYTHON_GDSTK

JOBS="$BATCH_DIR/jobs.csv"
DRY=0
COLLECT=1
STOP=0
RUN_DEC=1
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)      DRY=1; shift ;;
        --no-collect)   COLLECT=0; shift ;;
        --stop-on-fail) STOP=1; shift ;;
        --no-dec)       RUN_DEC=0; shift ;;
        -h|--help) sed -n '2,44p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) JOBS="$1"; shift ;;
    esac
done
[ -f "$JOBS" ] || die "no job list: $JOBS"

LOG_DIR="$BATCH_DIR/logs"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"

trim() { echo "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'; }

default_wd() {  # node rows -> strength from the phase-2 performance map
    "$PY" -c "
import sys
sys.path.insert(0, '$ARR/scripts')
from gen_col import NODE_SPECS, norm_node
from gen_array import default_wd
print(default_wd(NODE_SPECS[norm_node('$1')], $2))"
}

unit_wd() {  # node -> the node's unit driver strength (library wd_X<u>.gds)
    "$PY" -c "
import sys
sys.path.insert(0, '$ARR/scripts')
from gen_col import NODE_SPECS, norm_node
print(NODE_SPECS[norm_node('$1')].wd_unit)"
}

n_jobs=0; n_pass=0; n_fail=0; n_dec=0
FAILED=()
declare -A DEC_DONE   # decoder points already simulated this invocation

while IFS=, read -r f_node f_rows f_cols f_wd f_tr f_vdd f_temp f_pex; do
    node="$(trim "$f_node")"
    case "$node" in ""|\#*|node) continue ;; esac
    rows="$(trim "$f_rows")"; cols="$(trim "$f_cols")"
    wd="$(trim "$f_wd")";     tr="$(trim "$f_tr")"
    vdd="$(trim "$f_vdd")";   temp="$(trim "$f_temp")"
    pex="$(trim "$f_pex")"
    [ -n "$rows" ] && [ -n "$cols" ] || { echo "SKIP malformed line: $f_node,$f_rows,$f_cols,..."; continue; }
    tr="${tr:-1.0}"; pex="${pex:-1}"
    n_jobs=$((n_jobs + 1))

    if [ -z "$wd" ]; then
        wd="$(default_wd "$node" "$rows")" \
            || { echo "JOB $n_jobs FAIL: cannot resolve default wd (set PYTHON_GDSTK in site.env)"; n_fail=$((n_fail+1)); FAILED+=("$n_jobs"); [ "$STOP" = 1 ] && break; continue; }
    fi
    dir="$(printf "%02dnm" "$((10#${node%nm}))")"
    col="column_X${wd}_${rows}"
    arr="array_X${wd}_${rows}x${cols}"
    tag="${dir}_${arr}_tr${tr}_v${vdd:-nom}_t${temp:-nom}"
    log="$LOG_DIR/${tag}_${STAMP}.log"

    TECH="$SRAM/TECH_$dir"
    todo=()
    if [ ! -f "$TECH/$col/01_gds/$col.gds" ]; then
        # gen_col needs the wd_X<wd> ladder: generated unless <wd> is the
        # node's unit strength (which lives in the tech_libs SRAM library)
        unit="$(unit_wd "$node")" \
            || { echo "JOB $n_jobs FAIL: cannot resolve node unit wd (set PYTHON_GDSTK in site.env)"; n_fail=$((n_fail+1)); FAILED+=("$n_jobs"); [ "$STOP" = 1 ] && break; continue; }
        if [ "$wd" != "$unit" ] && [ ! -f "$TECH/wd_X${wd}/01_gds/wd_X${wd}.gds" ]; then
            todo+=("gen_wd")
        fi
        todo+=("gen_col")
    fi
    { [ -f "$TECH/$arr/01_gds/$arr.gds" ] && [ -f "$TECH/$arr/01_gds/$arr.json" ]; } || todo+=("gen_array")
    if [ "$pex" = 1 ]; then
        { [ -f "$TECH/$arr/02_pex/$arr.sp" ] && [ -f "$TECH/$arr/02_pex/$arr.spef" ]; } || todo+=("extract")
    else
        [ -f "$TECH/$arr/02_pex/$arr.sp" ] || todo+=("extract")
    fi
    todo+=("simulate")

    # decoder point: (node, rows, cols, vdd, temp, pex) — toggle-independent,
    # so duplicate points in the list run it only once per invocation
    dec_key="${dir}_${rows}x${cols}_v${vdd:-nom}_t${temp:-nom}_p${pex}"
    if [ "$RUN_DEC" = 1 ] && [ -z "${DEC_DONE[$dec_key]}" ]; then
        todo+=("decoder")
    fi

    echo "JOB $n_jobs: $tag  [${todo[*]}]"
    if [ "$DRY" = 1 ]; then
        n_pass=$((n_pass + 1))
        case " ${todo[*]} " in *" decoder "*) DEC_DONE[$dec_key]=1 ;; esac
        continue
    fi

    RUN_ARGS=(--node "$node" "$arr" --toggle "$tr")
    [ "$pex" = 1 ]  && RUN_ARGS+=(--pex)
    [ -n "$vdd" ]   && RUN_ARGS+=(--vdd "$vdd")
    [ -n "$temp" ]  && RUN_ARGS+=(--temp "$temp")

    DEC_ARGS=(--node "$node" --rows "$rows" --cols "$cols" --reuse-gds)
    [ "$pex" = 0 ]  && DEC_ARGS+=(--no-pex)
    [ -n "$vdd" ]   && DEC_ARGS+=(--vdd "$vdd")
    [ -n "$temp" ]  && DEC_ARGS+=(--temp "$temp")

    ok=1
    {
        for step in "${todo[@]}"; do
            case "$step" in
                gen_wd)    "$PY" "$ARR/scripts/gen_wd.py" --node "$node" "X$wd" || { ok=0; break; } ;;
                gen_col)   "$PY" "$ARR/scripts/gen_col.py" --node "$node" --rows "$rows" --wd "$wd" || { ok=0; break; } ;;
                gen_array) "$PY" "$ARR/scripts/gen_array.py" --node "$node" --rows "$rows" --wd "$wd" --cols "$cols" --force || { ok=0; break; } ;;
                extract)   (cd "$SP" && ./gds2spice.sh --node "$node" "$arr") || { ok=0; break; } ;;
                simulate)  (cd "$ARR" && ./run_array.sh "${RUN_ARGS[@]}") || { ok=0; break; } ;;
                decoder)   "$DEC/run_decoder.sh" "${DEC_ARGS[@]}" || { ok=0; break; } ;;
            esac
        done
    } >> "$log" 2>&1

    if [ "$ok" = 1 ]; then
        n_pass=$((n_pass + 1))
        case " ${todo[*]} " in *" decoder "*)
            DEC_DONE[$dec_key]=1; n_dec=$((n_dec + 1)) ;;
        esac
        echo "  PASS  ($(grep -c "array_measures: PASS" "$log")x measures ok)  log: $log"
    else
        n_fail=$((n_fail + 1)); FAILED+=("$n_jobs:$tag")
        echo "  FAIL  — see $log (tail):"
        tail -5 "$log" | sed 's/^/    /'
        [ "$STOP" = 1 ] && break
    fi
done < "$JOBS"

echo
echo "batch: $n_jobs job(s) — $n_pass pass, $n_fail fail ($n_dec decoder point(s) run)"
[ "$n_fail" -gt 0 ] && printf 'batch: failed: %s\n' "${FAILED[@]}"

if [ "$COLLECT" = 1 ] && [ "$DRY" = 0 ] && [ "$n_pass" -gt 0 ]; then
    python3 "$ARR/scripts/collect_array.py" --skip-bad
    # decoder sheet + area join into the array sheet (after collect_array
    # so the join always sees the fresh rows)
    if [ "$RUN_DEC" = 1 ] && [ "$n_dec" -gt 0 ]; then
        python3 "$DEC/scripts/collect_decoder.py" \
            || echo "warning: collect_decoder failed — sram_decoder.csv/area join not refreshed"
    fi
fi
[ "$n_fail" -eq 0 ]
