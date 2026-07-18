#!/bin/bash
# reset_old_pdk.sh — one-time reset after the 2026-07-17 PDK refresh.
#
# Every sweep artifact produced with the pre-refresh libraries is stale AND
# poisons the resume logic of the new sweep:
#   - autosweep/probe_results.tsv : probe skips "ok" rows -> old-cell T_min
#     would silently set the new sweep's clocks
#   - datasets/logic_*.csv        : sweep skips jobs whose rows exist
#   - autosweep/jobs (+ .prev)    : manifest derived from the old probe
#   - rtl_gen/rtl/*               : generated TBs predate +nw_power_mode --
#     an old TB ignores the plusarg and would SILENTLY measure random
#     activity under any mode label
#
# This script archives the small text state to old_pdk_<stamp>.tar.gz, then
# deletes it together with the EDA work trees (via clean_all.sh) and the
# obsolete add_stim_mode.sh migration helper.  Run it ONCE, before
# `run_batch.py probe` on the new libraries.

set -euo pipefail
cd "$(dirname "$0")"

STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="old_pdk_${STAMP}.tar.gz"

to_archive=()
for f in autosweep/probe_results.tsv autosweep/jobs autosweep/jobs.prev \
         autosweep/scoreboard.jsonl autosweep/sweep_failures.tsv; do
    [ -e "$f" ] && to_archive+=("$f")
done
compgen -G "datasets/logic_*.csv" > /dev/null && to_archive+=(datasets/logic_*.csv)
[ -d sweep_reports ] && to_archive+=(sweep_reports)

if [ ${#to_archive[@]} -gt 0 ]; then
    tar czf "$ARCHIVE" "${to_archive[@]}"
    echo "archived ${#to_archive[@]} item group(s) -> $ARCHIVE"
    rm -rf "${to_archive[@]}"
else
    echo "nothing to archive (already reset?)"
fi

# generated RTL/TB variants + all TECH_*nm stage run dirs (keeps run_scripts)
./clean_all.sh
echo "cleaned rtl_gen/rtl and TECH_*nm stage dirs"

# migration helper for the pre-refresh datasets -- moot now that they are gone
rm -f add_stim_mode.sh

echo "reset complete. Next: cp autosweep/jobs_pilot autosweep/jobs && \\"
echo "  cd autosweep && ./run_batch.py rtl && ./run_batch.py sweep -jobs-per-node 2"
