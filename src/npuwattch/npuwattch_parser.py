from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml



class NPUWattchArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that prepends a consistent banner before argparse's default error output."""

    def error(self, message: str) -> None:
        # Print the requested line first, then defer to argparse's default formatting.
        self._print_message(
            "[ERROR] Incomplete argument. Please refer to the error message below:\n",
            sys.stderr,
        )
        super().error(message)


@dataclass(frozen=True)
class NPUWattchArgs:
    # Normal execution mode (existing behavior)
    description_files: List[Path]
    activity_logs: List[Path]

    # Flatten mode (new behavior)
    flatten: bool
    input_yaml: Optional[Path]
    output_yaml: Optional[Path]

    verbose: int


def build_arg_parser() -> argparse.ArgumentParser:
    parser = NPUWattchArgumentParser(
        prog="npuwattch",
        description="NPUWattch CLI arguments description",
    )

    # Mode selector: flatten an Accelergy v0.4 architecture YAML into 'architecture.local'.
    parser.add_argument(
        "-f",
        "--flatten",
        action="store_true",
        help="Flatten an Accelergy v0.4 architecture YAML (use with -i/-o).",
    )
    parser.add_argument(
        "-i",
        "--input_yaml",
        dest="input_yaml",
        help="Input YAML to flatten (used with -f).",
    )
    parser.add_argument(
        "-o",
        "--output_yaml",
        dest="output_yaml",
        help="Output path for flattened YAML (used with -f). If not specified, defaults to <input>_flattened.yaml in the same directory.",
    )

    parser.add_argument(
        "-d", "--description",
        dest="description_files",
        help="YAML description file (e.g., architecture_description.yaml).",
    )
    parser.add_argument(
        "-l", "--log",
        dest="activity_logs",
        nargs="+",
        help="One or more activity log files (e.g., activity_log.txt).",
    )

    # Keep the CLI light: ~three options total.
    parser.add_argument(
        "-v", "--verbose",
        type=int,
        default=0,
        help="Verbosity level (0=quiet).",
    )

    return parser


def parse_args(argv: Optional[List[str]] = None) -> NPUWattchArgs:
    parser = build_arg_parser()
    ns = parser.parse_args(argv)

    # Validate mode-specific required arguments.
    if ns.flatten:
        if not ns.input_yaml:
            parser.error("Flattener mode -f/--flatten requires -i/--input_yaml")
        desc: List[Path] = []
        logs: List[Path] = []
        in_yaml = Path(ns.input_yaml)
        
        # If -o is not specified, create default output filename
        if ns.output_yaml:
            out_yaml = Path(ns.output_yaml)
        else:
            # Generate default output filename: input_flattened.yaml
            input_path = Path(ns.input_yaml)
            out_yaml = input_path.parent / f"{input_path.stem}_flattened{input_path.suffix}"
    else:
        if not ns.description_files:
            parser.error("Estimator mode requires -d/--description")
        # Wrap single description file in a list for consistency
        desc = [Path(ns.description_files)]
        logs = [Path(p) for p in (ns.activity_logs or [])]
        in_yaml = None
        out_yaml = None

    return NPUWattchArgs(
        description_files=desc,
        activity_logs=logs,
        flatten=bool(ns.flatten),
        input_yaml=in_yaml,
        output_yaml=out_yaml,
        verbose=ns.verbose,
    )


def load_description_files(paths: List[Path]) -> list[dict]:
    """Skeleton loader for YAML description files."""
    loaded: list[dict] = []
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            loaded.append(yaml.safe_load(f) or {})
    return loaded


def load_activity_logs(paths: List[Path]) -> list[str]:
    """Skeleton loader for text activity logs."""
    lines: list[str] = []
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            lines.extend([ln.rstrip("\n") for ln in f])
    return lines