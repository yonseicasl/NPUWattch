"""NPUWattch Argument Parser Module.

This module handles command-line argument parsing for NPUWattch, supporting:
- Flatten mode: Convert Accelergy v0.4 YAML to flattened format
- Estimator mode: Run energy/area/timing estimation on architecture
- Training mode: Train MLP models for estimation
"""

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
        self._print_message(
            "[ERROR] Incomplete argument. Please refer to the error message below:\n",
            sys.stderr,
        )
        super().error(message)


@dataclass(frozen=True)
class NPUWattchArgs:
    """Parsed command-line arguments."""
    # Normal execution mode
    description_files: List[Path]
    activity_logs: List[Path]

    # Flatten mode
    flatten: bool
    input_yaml: Optional[Path]
    output_yaml: Optional[Path]

    # Training mode
    train: bool
    train_estimator: Optional[str]
    train_model_type: Optional[str]
    train_csv: Optional[Path]
    train_output: Optional[Path]
    train_epochs: int
    train_batch_size: int
    train_lr: float

    verbose: int


def build_arg_parser() -> argparse.ArgumentParser:
    parser = NPUWattchArgumentParser(
        prog="npuwattch",
        description="NPUWattch - Neural Processing Unit Power/Area/Timing Estimator",
    )

    # =========================================================================
    # Mode selectors
    # =========================================================================
    mode_group = parser.add_argument_group("Mode Selection")

    mode_group.add_argument(
        "-f", "--flatten",
        action="store_true",
        help="Flatten an Accelergy v0.4 architecture YAML (use with -i/-o).",
    )

    mode_group.add_argument(
        "-t", "--train",
        action="store_true",
        help="Train an estimator model (use with --train-estimator, --train-type, --train-csv).",
    )

    # =========================================================================
    # Flatten mode arguments
    # =========================================================================
    flatten_group = parser.add_argument_group("Flatten Mode Options")

    flatten_group.add_argument(
        "-i", "--input_yaml",
        dest="input_yaml",
        help="Input YAML to flatten (used with -f).",
    )

    flatten_group.add_argument(
        "-o", "--output_yaml",
        dest="output_yaml",
        help="Output path for flattened YAML (used with -f). Defaults to <input>_flattened.yaml.",
    )

    # =========================================================================
    # Estimator mode arguments
    # =========================================================================
    estimator_group = parser.add_argument_group("Estimator Mode Options")

    estimator_group.add_argument(
        "-d", "--description",
        dest="description_files",
        help="YAML description file (e.g., architecture_description.yaml).",
    )

    estimator_group.add_argument(
        "-l", "--log",
        dest="activity_logs",
        nargs="+",
        help="One or more activity log files (e.g., activity_log.txt).",
    )

    # =========================================================================
    # Training mode arguments
    # =========================================================================
    train_group = parser.add_argument_group("Training Mode Options")

    train_group.add_argument(
        "--train-estimator",
        dest="train_estimator",
        help="Name of the estimator to train (e.g., 'regfile').",
    )

    train_group.add_argument(
        "--train-type",
        dest="train_model_type",
        choices=["energy", "area", "timing"],
        help="Type of model to train: 'energy', 'area', or 'timing'.",
    )

    train_group.add_argument(
        "--train-csv",
        dest="train_csv",
        help="Path to training data CSV file.",
    )

    train_group.add_argument(
        "--train-output",
        dest="train_output",
        help="Output path for trained model (.pth file).",
    )

    train_group.add_argument(
        "--epochs",
        dest="train_epochs",
        type=int,
        default=500,
        help="Number of training epochs (default: 500).",
    )

    train_group.add_argument(
        "--batch-size",
        dest="train_batch_size",
        type=int,
        default=10,
        help="Training batch size (default: 10).",
    )

    train_group.add_argument(
        "--lr",
        dest="train_lr",
        type=float,
        default=1e-3,
        help="Learning rate (default: 0.001).",
    )

    # =========================================================================
    # Common arguments
    # =========================================================================
    common_group = parser.add_argument_group("Common Options")

    common_group.add_argument(
        "-v", "--verbose",
        type=int,
        default=1,
        help="Verbosity level (0=quiet, 1=normal, 2=detailed).",
    )

    return parser


def parse_args(argv: Optional[List[str]] = None) -> NPUWattchArgs:
    """Parse command-line arguments and return validated NPUWattchArgs."""
    parser = build_arg_parser()
    ns = parser.parse_args(argv)

    # Initialize defaults
    desc: List[Path] = []
    logs: List[Path] = []
    in_yaml: Optional[Path] = None
    out_yaml: Optional[Path] = None
    train_csv: Optional[Path] = None
    train_output: Optional[Path] = None

    # Validate mode-specific required arguments
    if ns.flatten:
        # Flatten mode
        if not ns.input_yaml:
            parser.error("Flattener mode (-f/--flatten) requires -i/--input_yaml")

        in_yaml = Path(ns.input_yaml)

        if ns.output_yaml:
            out_yaml = Path(ns.output_yaml)
        else:
            out_yaml = in_yaml.parent / f"{in_yaml.stem}_flattened{in_yaml.suffix}"

    elif ns.train:
        # Training mode
        if not ns.train_estimator:
            parser.error("Training mode (-t/--train) requires --train-estimator")
        if not ns.train_model_type:
            parser.error("Training mode (-t/--train) requires --train-type")
        if not ns.train_csv:
            parser.error("Training mode (-t/--train) requires --train-csv")

        train_csv = Path(ns.train_csv)
        if ns.train_output:
            train_output = Path(ns.train_output)

    else:
        # Estimator mode (default)
        if not ns.description_files:
            parser.error("Estimator mode requires -d/--description")

        desc = [Path(ns.description_files)]
        logs = [Path(p) for p in (ns.activity_logs or [])]

    return NPUWattchArgs(
        description_files=desc,
        activity_logs=logs,
        flatten=bool(ns.flatten),
        input_yaml=in_yaml,
        output_yaml=out_yaml,
        train=bool(ns.train),
        train_estimator=ns.train_estimator,
        train_model_type=ns.train_model_type,
        train_csv=train_csv,
        train_output=train_output,
        train_epochs=ns.train_epochs,
        train_batch_size=ns.train_batch_size,
        train_lr=ns.train_lr,
        verbose=ns.verbose,
    )


def load_description_files(paths: List[Path]) -> list[dict]:
    """Load YAML description files."""
    loaded: list[dict] = []
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            loaded.append(yaml.safe_load(f) or {})
    return loaded


def load_activity_logs(paths: List[Path]) -> list[str]:
    """Load text activity log files."""
    lines: list[str] = []
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            lines.extend([ln.rstrip("\n") for ln in f])
    return lines