#!/usr/bin/env bash
# run.sh — locate a PyTorchSim run's two result sets under one root and invoke
# `npuwattch --harness pytorchsim` with them.
#
# PyTorchSim stores its results in separate locations (author guidance,
# 2026-07-20): final TOGSim logs in togsim_results/, per-kernel gem5/codegen
# outputs in outputs/ (raw run) or gem5_outputs/ (delivery bundle). The CLI
# takes each as an explicit flag; this wrapper is the convenience path for the
# common case where both live under a single root.
#
# Usage:
#   ./run.sh [-n] <root_dir> [extra npuwattch args...]
#
#   <root_dir>   directory containing togsim_results/ AND outputs/|gem5_outputs/
#   -n           dry-run: print the resolved npuwattch command, don't run it
#
# Everything after <root_dir> is passed through to npuwattch
# (e.g. --node 5nm --clock-mhz 1000 -o out/).

set -euo pipefail

die() { echo "[run.sh ERROR] $*" >&2; exit 1; }

DRYRUN=0
if [[ "${1:-}" == "-n" || "${1:-}" == "--dry-run" ]]; then
    DRYRUN=1
    shift
fi

ROOT="${1:-}"
[[ -n "$ROOT" ]] || die "usage: run.sh [-n] <root_dir> [npuwattch args...]"
[[ -d "$ROOT" ]] || die "not a directory: $ROOT"
shift

# --- TOGSim logs: the run's FINAL results live in <root>/togsim_results/ ------
TOGSIM="$ROOT/togsim_results"
if [[ ! -d "$TOGSIM" ]]; then
    if compgen -G "$ROOT/outputs/*/togsim_result" > /dev/null; then
        die "no $TOGSIM — only outputs/<hash>/togsim_result/ found, and those are \
autotune CANDIDATE logs, not final results. Point run.sh at the run root that \
holds togsim_results/."
    fi
    die "no togsim_results/ under $ROOT"
fi

# --- gem5/codegen outputs: outputs/ (raw run) XOR gem5_outputs/ (bundle) ------
GEM5=""
if [[ -d "$ROOT/outputs" && -d "$ROOT/gem5_outputs" ]]; then
    die "both outputs/ and gem5_outputs/ exist under $ROOT — ambiguous; pass \
--gem5-dir explicitly via: npuwattch --harness pytorchsim --togsim-dir $TOGSIM --gem5-dir <dir>"
elif [[ -d "$ROOT/gem5_outputs" ]]; then
    GEM5="$ROOT/gem5_outputs"
elif [[ -d "$ROOT/outputs" ]]; then
    GEM5="$ROOT/outputs"
else
    die "neither outputs/ nor gem5_outputs/ under $ROOT"
fi

CMD=(npuwattch --harness pytorchsim --togsim-dir "$TOGSIM" --gem5-dir "$GEM5")
[[ -f "$ROOT/config.yml" ]] && CMD+=(--config-yml "$ROOT/config.yml")
# BookSim configs (anynet NoCs need the .net network file from here).
[[ -d "$ROOT/booksim2_config" ]] && CMD+=(--booksim-dir "$ROOT/booksim2_config")
# DRAM energy table (the config's energy_cost_table_path; collect the run's
# energy_tables/ dir into the root). Exactly one yml → auto-added; several →
# ambiguous, pass --energy-table explicitly.
if [[ -d "$ROOT/energy_tables" ]]; then
    ETABLES=()
    while IFS= read -r f; do ETABLES+=("$f"); done \
        < <(compgen -G "$ROOT/energy_tables/*.yml" || true)
    if [[ ${#ETABLES[@]} -eq 1 ]]; then
        CMD+=(--energy-table "${ETABLES[0]}")
    elif [[ ${#ETABLES[@]} -gt 1 ]]; then
        echo "[run.sh] ${#ETABLES[@]} ymls in $ROOT/energy_tables/ — pass \
--energy-table explicitly to pick one" >&2
    fi
fi
CMD+=("$@")

if [[ "$DRYRUN" == 1 ]]; then
    echo "${CMD[@]}"
    exit 0
fi
exec "${CMD[@]}"
