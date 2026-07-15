#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import json
import sys


if sys.version_info < (3, 9):
    raise SystemExit("run_batch.py requires Python 3.9 or newer. Try python3.11 run_batch.py.")


from autocollect import collect_from_manifest  # noqa: E402
from autocommon import summarize_scoreboard  # noqa: E402
from autopex import run_pex_from_manifest  # noqa: E402
from autoprobe import generate_sweep_manifest, run_probe  # noqa: E402
from autopnr import run_pnr_from_manifest  # noqa: E402
from autopwr import run_power_from_manifest  # noqa: E402
from autortl import generate_rtl_from_manifest  # noqa: E402
from autosim import run_simulation_from_manifest  # noqa: E402
from autosweeprun import run_sweep  # noqa: E402
from autosynth import run_synthesis_from_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the logic autosweep workflow.")
    parser.add_argument(
        "-verbose",
        action="store_true",
        help="stream the currently running Synopsys tool output to stdout while also saving the log",
    )
    parser.add_argument(
        "-vectored",
        action="store_true",
        help="use gate-level simulation activity for 05_pwr instead of default unvectored activity",
    )
    parser.add_argument(
        "-jobs-per-node",
        dest="jobs_per_node",
        type=int,
        default=1,
        help="concurrent jobs per node worker in the EDA stages (default 1; "
        "total concurrent tools = nodes x this, bounded by EDA license seats)",
    )
    parser.add_argument(
        "-nodes",
        dest="nodes",
        default=None,
        help="comma-separated node filter for the probe/gen-jobs/sweep stages, "
        "e.g. -nodes 3 or -nodes 20,16. Use it to bring up a newly added node "
        "without re-running finished ones (default: probe/gen-jobs cover "
        "sweep_spec.SWEEP_NODES; sweep runs every manifest row)",
    )
    parser.add_argument(
        "stage",
        nargs="?",
        default="all",
        choices=[
            "all",
            "rtl",
            "rtl-gen",
            "syn",
            "pnr",
            "pex",
            "sim",
            "logic-sim",
            "pwr",
            "05_pwr",
            "collect",
            "data-collection",
            "scoreboard",
            "probe",
            "gen-jobs",
            "sweep",
        ],
        help="workflow stage to run (probe/gen-jobs/sweep drive the dataset sweep)",
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

    if args.stage == "scoreboard":
        print(json.dumps(summarize_scoreboard(), indent=2, sort_keys=True))
        return 0

    if args.stage == "probe":
        run_probe(jobs_per_node=args.jobs_per_node, nodes=nodes)
        return 0
    if args.stage == "gen-jobs":
        generate_sweep_manifest(nodes=nodes)
        return 0
    if args.stage == "sweep":
        run_sweep(jobs_per_node=args.jobs_per_node, nodes=nodes)
        return 0

    if args.stage in {"all", "rtl", "rtl-gen"}:
        generate_rtl_from_manifest()
    if args.stage in {"all", "syn"}:
        run_synthesis_from_manifest(verbose=args.verbose, jobs_per_node=args.jobs_per_node)
    if args.stage in {"all", "pnr"}:
        run_pnr_from_manifest(verbose=args.verbose, jobs_per_node=args.jobs_per_node)
    if args.stage in {"all", "pex"}:
        run_pex_from_manifest(verbose=args.verbose, jobs_per_node=args.jobs_per_node)
    if args.stage in {"all", "sim", "logic-sim"}:
        run_simulation_from_manifest(verbose=args.verbose, jobs_per_node=args.jobs_per_node)
    if args.stage in {"all", "pwr", "05_pwr"}:
        run_power_from_manifest(
            verbose=args.verbose, vectored=args.vectored, jobs_per_node=args.jobs_per_node
        )
    if args.stage in {"all", "collect", "data-collection"}:
        collect_from_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
