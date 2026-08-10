#!/usr/bin/env python3
# NOTE: resolves to the ACTIVE python3 so `conda activate npuwattch` supplies
# jinja2 (rtl_gen) — a hardcoded python3.11 bypassed the env and failed on
# import. On this server the bare system python3 is 3.6 and dies on the
# `from __future__` line below; activate the env first.
"""One-way dataset sweep workflow:

    probe -> gen-jobs -> rtl -> sweep

probe measures per-config minimum periods (synthesis-only), gen-jobs derives
two clocks per config x node from them, rtl renders every RTL variant + TB,
and sweep pipelines each job through syn -> pnr -> pex -> sim -> pwr ->
collect with storage bounding.  The sweep self-corrects clocks that PnR
proves unachievable (rederived from measured slack, persisted back into the
manifest), so probe estimates never have to be perfect.

rerun-failed patches the manifest clocks for failures recorded by earlier
sweeps and retires the failure log; scoreboard summarizes progress.
"""
from __future__ import annotations

import argparse
import json
import sys


if sys.version_info < (3, 9):
    raise SystemExit(
        "run_batch.py requires Python 3.9+ with jinja2. Run `conda activate npuwattch` first."
    )


from autocommon import summarize_scoreboard  # noqa: E402
from autoprobe import generate_sweep_manifest, run_probe  # noqa: E402
from autortl import generate_rtl_from_manifest  # noqa: E402
from autosweeprun import rerun_failed, run_sweep  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "-jobs-per-node",
        dest="jobs_per_node",
        type=int,
        default=1,
        help="concurrent jobs per node worker for probe/sweep (default 1; "
        "total concurrent tools = nodes x this, bounded by EDA license seats)",
    )
    parser.add_argument(
        "-nodes",
        dest="nodes",
        default=None,
        help="comma-separated node filter for probe/gen-jobs/sweep, e.g. "
        "-nodes 3 or -nodes 20,16, to bring up a new node without re-running "
        "finished ones (default: probe/gen-jobs cover sweep_spec.SWEEP_NODES; "
        "sweep runs every manifest row)",
    )
    parser.add_argument(
        "stage",
        choices=["probe", "gen-jobs", "rtl", "sweep", "rerun-failed", "scoreboard"],
        help="workflow stage to run (one-way order: probe, gen-jobs, rtl, sweep)",
    )
    args = parser.parse_args()

    if args.jobs_per_node < 1:
        parser.error("-jobs-per-node must be >= 1")

    nodes: tuple[str, ...] | None = None
    if args.nodes:
        nodes = tuple(part.strip() for part in args.nodes.split(",") if part.strip())
        if not nodes:
            parser.error("-nodes needs a comma-separated node list, e.g. -nodes 20,16")
        if args.stage not in {"probe", "gen-jobs", "sweep"}:
            parser.error("-nodes only applies to the probe/gen-jobs/sweep stages")

    if args.stage == "probe":
        run_probe(jobs_per_node=args.jobs_per_node, nodes=nodes)
    elif args.stage == "gen-jobs":
        generate_sweep_manifest(nodes=nodes)
    elif args.stage == "rtl":
        generate_rtl_from_manifest()
    elif args.stage == "sweep":
        run_sweep(jobs_per_node=args.jobs_per_node, nodes=nodes)
    elif args.stage == "rerun-failed":
        rerun_failed()
    else:
        print(json.dumps(summarize_scoreboard(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
