#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import json
import sys


if sys.version_info < (3, 9):
    raise SystemExit("autosweep.py requires Python 3.9 or newer. Try python3.11 autosweep.py.")


from autocommon import summarize_scoreboard  # noqa: E402
from autopex import run_pex_from_manifest  # noqa: E402
from autopnr import run_pnr_from_manifest  # noqa: E402
from autopwr import run_power_from_manifest  # noqa: E402
from autortl import generate_rtl_from_manifest  # noqa: E402
from autosim import run_simulation_from_manifest  # noqa: E402
from autosynth import run_synthesis_from_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage NW_logic autosweep workflow.")
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
        "stage",
        nargs="?",
        default="all",
        choices=["all", "rtl", "rtl-gen", "syn", "pnr", "pex", "sim", "logic-sim", "pwr", "05_pwr", "scoreboard"],
        help="workflow stage to run",
    )
    args = parser.parse_args()

    if args.stage == "scoreboard":
        print(json.dumps(summarize_scoreboard(), indent=2, sort_keys=True))
        return 0

    if args.stage in {"all", "rtl", "rtl-gen"}:
        generate_rtl_from_manifest()
    if args.stage in {"all", "syn"}:
        run_synthesis_from_manifest(verbose=args.verbose)
    if args.stage in {"all", "pnr"}:
        run_pnr_from_manifest(verbose=args.verbose)
    if args.stage in {"all", "pex"}:
        run_pex_from_manifest(verbose=args.verbose)
    if args.stage in {"all", "sim", "logic-sim"}:
        run_simulation_from_manifest(verbose=args.verbose)
    if args.stage in {"all", "pwr", "05_pwr"}:
        run_power_from_manifest(verbose=args.verbose, vectored=args.vectored)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
