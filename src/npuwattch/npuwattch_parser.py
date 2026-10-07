"""NPUWattch argument parser.

This module parses the command-line arguments of NPUWattch for four modes:

- Flatten mode converts an Accelergy v0.4 YAML file to the flattened format.
- Estimator mode calculates the energy of a native description.
- Harness mode makes the description and the activity rows from the files
  of a simulator, then calculates the energy.
- Training mode trains the MLP models of an estimator.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class NPUWattchArgumentParser(argparse.ArgumentParser):
    """An ArgumentParser that prints an NPUWattch error line before the argparse
    error message."""

    def error(self, message: str) -> None:
        self._print_message(
            "[ERROR] Incomplete argument. Please refer to the error message below:\n",
            sys.stderr,
        )
        super().error(message)


@dataclass(frozen=True)
class NPUWattchArgs:
    """The parsed command-line arguments."""
    # Estimator mode
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

    # Harness mode: --harness NAME and the named inputs of that harness.
    # The flags come from the HARNESS_SPEC declarations (npuwattch_harness.registry
    # cli_flags). `harness_inputs` is input name -> path and `harness_options`
    # is option name -> value, for the flags that the user gave.
    harness: Optional[str] = None
    harness_inputs: Dict[str, Path] = field(default_factory=dict)
    harness_options: Dict[str, Any] = field(default_factory=dict)
    out_dir: Optional[Path] = None
    # Vectorless runs: the fraction of random switching for the VECTORLESS
    # estimate. None selects energy.DEFAULT_VECTORLESS_ACTIVITY (0.25).
    vectorless_activity: Optional[float] = None
    # Print the instance hierarchy (report.tree) of the design.
    tree: bool = False
    # Show f_max, the critical paths, and the clock-range warnings.
    show_fmax: bool = False
    # Write the HTML/JSON PPA report (manual §8) to this directory.
    report_dir: Optional[Path] = None
    node: str = "7nm"
    #: True if --node is on the command line (False for the 7nm default).
    node_explicit: bool = False
    transistor: str = "hp"          # hp | lp
    corner: str = "TT"              # TT | SS | FF
    voltage_offset_V: float = 0.0   # nominal Vdd
    temperature_C: float = 25.0
    clock_mhz: Optional[float] = None   # None: use the harness log


def build_arg_parser() -> argparse.ArgumentParser:
    from npuwattch._version import __version__

    parser = NPUWattchArgumentParser(
        prog="npuwattch",
        description="NPUWattch - Neural Processing Unit Power/Area/Timing Estimator",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"npuwattch {__version__}",
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
    # Shared input / output (the mode sets the meaning)
    # =========================================================================
    io_group = parser.add_argument_group("Input / Output")

    io_group.add_argument(
        "-i", "--input", "--input_yaml",
        dest="input_path",
        help="Input path: YAML to flatten (-f only; harness mode uses the "
             "named inputs of the harness).",
    )

    io_group.add_argument(
        "-o", "--out", "--output_yaml",
        dest="output_path",
        help="Output path: flattened YAML (-f, default <input>_flattened.yaml), "
             "or a directory to write the harness's native description.yaml + activity.csv (--harness).",
    )

    # =========================================================================
    # Estimator mode arguments
    # =========================================================================
    estimator_group = parser.add_argument_group("Estimator Mode Options")

    estimator_group.add_argument(
        "-d", "--description",
        dest="description_files",
        help="Native NPUWattch description YAML ('npuwattch:' root, §3.1). "
             "A simulator's own architecture file (e.g. an Accelergy/"
             "Timeloop YAML) is a harness input: see --harness.",
    )

    estimator_group.add_argument(
        "-l", "--log",
        dest="activity_logs",
        nargs="+",
        help="One or more activity log files (e.g., activity_log.txt).",
    )
    estimator_group.add_argument(
        "--vectorless-activity",
        dest="vectorless_activity",
        type=float,
        help="Vectorless runs only (-d without -l, or a harness run "
             "without its activity input): fraction of random switching assumed for the "
             "VECTORLESS estimate, in (0, 1] (default 0.25; crossbar-family "
             "primitives use their measured valid25 mode instead).",
    )
    parser.add_argument(
        "--tree",
        dest="tree",
        action="store_true",
        help="Print the instance-hierarchy tree of the modeled architecture "
             "(estimator + harness modes; Accelergy descriptions show their "
             "declared hierarchy, native/harness inputs the reconstructed one).",
    )
    parser.add_argument(
        "--fmax",
        dest="show_fmax",
        action="store_true",
        help="Show timing: the f_max check and the critical path of each "
             "component in the report, and the clock-range warnings of the "
             "logic models (off by default).",
    )
    parser.add_argument(
        "--report",
        dest="report_dir",
        metavar="DIR",
        help="Write the self-contained HTML PPA report (report.html) and its "
             "machine-readable mirror (report.json) to DIR (native estimator "
             "and harness modes).",
    )

    # =========================================================================
    # Harness mode arguments
    # =========================================================================
    harness_group = parser.add_argument_group("Harness Mode Options")

    harness_flags = _harness_flags()
    harness_names = sorted({name for entry in harness_flags.values()
                            for name in entry["by_harness"]})
    harness_group.add_argument(
        "--harness",
        dest="harness",
        help="Select a simulator harness"
             + (f" ({', '.join(harness_names)})" if harness_names else "")
             + " and synthesize the native NPUWattch description + activity "
               "from its named inputs.",
    )
    # One flag for each input and option that a harness declares in its
    # HARNESS_SPEC. The parser has no knowledge of a specific harness.
    for flag, entry in harness_flags.items():
        harness_group.add_argument(
            flag,
            dest=entry["dest"],
            choices=entry["choices"],
            help=entry["help"].replace("%", "%%"),
        )

    # Technology and PVT for harness mode. The defaults are nominal: hp, TT,
    # nominal Vdd, 25C. Only a flag on the command line changes them.
    tech_group = parser.add_argument_group(
        "Technology / PVT (harness mode; defaults = hp / TT / nominal Vdd / 25C)"
    )
    tech_group.add_argument(
        "--node", dest="node", default=None,
        help="Technology node, continuous, e.g. 7nm or 12.5nm (default: 7nm). "
             "Characterized nodes are 5/7/10/16/20nm; anything between is "
             "log-interpolated, anything up to ±50%% beyond the range "
             "(2.5-30nm) is extrapolated with a WARNING, and anything outside "
             "that envelope is clamped to it with a WARNING (CLI + report).",
    )
    tech_group.add_argument(
        "--transistor", dest="transistor", default="hp", choices=["hp", "lp"],
        help="Transistor flavor (default: hp).",
    )
    tech_group.add_argument(
        "--corner", dest="corner", default="TT", choices=["TT", "SS", "FF"],
        help="Process corner (default: TT).",
    )
    tech_group.add_argument(
        "--voltage-offset", dest="voltage_offset_V", type=float, default=0.0,
        help="Vdd offset from nominal in V, -0.15..+0.15 (default: 0.0 = nominal).",
    )
    tech_group.add_argument(
        "--temperature", dest="temperature_C", type=float, default=25.0,
        help="Temperature in C (default: 25).",
    )
    tech_group.add_argument(
        "--clock-mhz", dest="clock_mhz", type=float, default=None,
        help="Clock frequency in MHz. Precedence: this flag > the harness log's core "
             "frequency > 200 MHz default (so the log is used when present).",
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


def _harness_flags() -> Dict[str, Dict[str, Any]]:
    """The CLI flags that the harnesses declare (``npuwattch_harness.registry.cli_flags``).

    If the registry cannot be imported, the result is empty. A broken harness
    plugin must not make the other modes of the CLI unusable.
    """
    try:
        from npuwattch_harness.registry import cli_flags
        return cli_flags()
    except Exception:
        return {}


def _harness_info(name: str):
    """The ``HarnessInfo`` of ``name``, or ``None`` if it is unknown.

    ``run_harness`` reports an unknown name with the list of available
    harnesses. Thus the parser does not reject the name here.
    """
    try:
        from npuwattch_harness import available_harnesses
        return available_harnesses().get(name)
    except Exception:
        return None


def parse_args(argv: Optional[List[str]] = None) -> NPUWattchArgs:
    """Parse and check the command-line arguments."""
    parser = build_arg_parser()
    ns = parser.parse_args(argv)

    # Defaults
    desc: List[Path] = []
    logs: List[Path] = []
    in_yaml: Optional[Path] = None
    out_yaml: Optional[Path] = None
    train_csv: Optional[Path] = None
    train_output: Optional[Path] = None
    harness_inputs: Dict[str, Path] = {}
    harness_options: Dict[str, Any] = {}
    out_dir: Optional[Path] = None

    # The harness flags that the user gave: flag -> (entry, value).
    flags = _harness_flags()
    given = {flag: (entry, getattr(ns, entry["dest"]))
             for flag, entry in flags.items()
             if getattr(ns, entry["dest"], None) is not None}
    given_names = {entry["name"] for entry, _ in given.values()}
    info = _harness_info(ns.harness) if ns.harness else None

    if ns.harness and ns.description_files:
        parser.error("--harness and -d/--description are mutually exclusive")
    if not ns.harness and given:
        parser.error(f"{'/'.join(given)} require(s) --harness")
    for flag, (entry, _) in given.items():
        for decl in entry["by_harness"].values():
            needed = decl.get("requires")
            if needed and needed not in given_names:
                needed_flag = next(
                    (f for f, e in flags.items() if e["name"] == needed), needed)
                parser.error(f"{flag} requires {needed_flag}")
    if ns.vectorless_activity is not None:
        if ns.flatten or ns.train or ns.activity_logs:
            parser.error(
                "--vectorless-activity applies only to vectorless runs: -d "
                "WITHOUT -l, or a harness with no activity reader "
                "(it replaces the missing activity log)")
        for flag, (entry, _) in given.items():
            if any(decl.get("provides_activity")
                   for decl in entry["by_harness"].values()):
                parser.error(
                    f"--vectorless-activity: {flag} provides real activity; "
                    f"the flag applies only to vectorless runs (-d without "
                    f"-l, or a harness run without {flag})")
        if ns.harness and info is not None and not info.synthesizes_activity:
            parser.error(
                f"--vectorless-activity: the {ns.harness!r} harness reads real "
                f"activity from its logs; the flag applies only to vectorless "
                f"runs (-d without -l, or a harness that has no activity input)")
        if not (0.0 < ns.vectorless_activity <= 1.0):
            parser.error(
                f"--vectorless-activity must be in (0, 1], got {ns.vectorless_activity}")

    # Check the arguments that each mode requires.
    if ns.flatten:
        # Flatten mode
        if not ns.input_path:
            parser.error("Flattener mode (-f/--flatten) requires -i/--input")

        in_yaml = Path(ns.input_path)

        if ns.output_path:
            out_yaml = Path(ns.output_path)
        else:
            out_yaml = in_yaml.parent / f"{in_yaml.stem}_flattened{in_yaml.suffix}"

    elif ns.harness:
        # Harness mode: each input is a named path. -i is not a harness input.
        required = ([decl.get("flag") for decl in info.inputs.values()
                     if decl.get("required", True)] if info else [])
        if ns.input_path:
            hint = f" (or {info.usage_hint})" if info and info.usage_hint else ""
            parser.error(
                "-i is not a harness input; pass the named inputs of the "
                f"harness: {' '.join(required) or 'see --help'}{hint}")
        if info is not None:
            # Fail early if a required input is missing. `run_harness` does
            # the complete check (unknown inputs, path kinds).
            missing = [
                f"{decl['flag']} ({decl.get('hint', '')})".strip()
                for decl in info.inputs.values()
                if decl.get("required", True) and decl.get("flag")
                and decl["flag"] not in given]
            if missing:
                parser.error(
                    f"Harness mode (--harness {ns.harness}) requires "
                    + "; ".join(missing))
        for flag, (entry, value) in given.items():
            if not entry["is_option"]:
                # An input that the selected harness does not declare stays
                # in the dict: `run_harness` rejects it by name.
                harness_inputs[entry["name"]] = Path(value)
            elif info is None or ns.harness in entry["by_harness"]:
                harness_options[entry["name"]] = value
            else:
                parser.error(
                    f"{flag} is not an option of the {ns.harness!r} harness")
        out_dir = Path(ns.output_path) if ns.output_path else None

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
        harness=ns.harness,
        harness_inputs=harness_inputs,
        harness_options=harness_options,
        out_dir=out_dir,
        vectorless_activity=ns.vectorless_activity,
        tree=bool(ns.tree),
        show_fmax=bool(ns.show_fmax),
        report_dir=Path(ns.report_dir) if ns.report_dir else None,
        node=ns.node or "7nm",
        node_explicit=ns.node is not None,
        transistor=ns.transistor,
        corner=ns.corner,
        voltage_offset_V=ns.voltage_offset_V,
        temperature_C=ns.temperature_C,
        clock_mhz=ns.clock_mhz,
    )


def load_description_files(paths: List[Path]) -> list[dict]:
    """Load the YAML description files."""
    loaded: list[dict] = []
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            loaded.append(yaml.safe_load(f) or {})
    return loaded
