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

    # Harness mode (--harness NAME + that harness's named inputs); tech/PVT
    # defaults = nominal. PyTorchSim writes its two result sets to separate
    # locations, so each is its own explicit flag — there is no umbrella "-i".
    # Which flags a given harness requires is declared in its HARNESS_SPEC and
    # checked against the registry, not hardcoded here.
    harness: Optional[str] = None
    togsim_dir: Optional[Path] = None
    gem5_dir: Optional[Path] = None
    config_yml: Optional[Path] = None
    booksim_dir: Optional[Path] = None
    energy_table: Optional[Path] = None
    arch_yaml: Optional[Path] = None
    # Timeloop harness activity: a timeloop-model/mapper .stats.txt (or a
    # directory of per-layer stats files), the optional level→component map,
    # and the multi-layer handling (None → the harness default, "windows").
    timeloop_stats: Optional[Path] = None
    stats_map: Optional[Path] = None
    stats_mode: Optional[str] = None
    out_dir: Optional[Path] = None
    # Estimator mode, -d without -l: fraction of random switching for the
    # VECTORLESS estimate (None → energy.DEFAULT_VECTORLESS_ACTIVITY = 0.25).
    vectorless_activity: Optional[float] = None
    # Print the instance-hierarchy tree (report.tree) of the modeled arch.
    tree: bool = False
    # Write the HTML/JSON PPA report (manual §8) to this directory.
    report_dir: Optional[Path] = None
    node: str = "7nm"
    transistor: str = "hp"          # hp | lp
    corner: str = "TT"              # TT | SS | FF
    voltage_offset_V: float = 0.0   # nominal Vdd
    temperature_C: float = 25.0
    clock_mhz: Optional[float] = None   # None → from the harness log


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
    # Shared input / output (meaning depends on mode)
    # =========================================================================
    io_group = parser.add_argument_group("Input / Output")

    io_group.add_argument(
        "-i", "--input", "--input_yaml",
        dest="input_path",
        help="Input path: YAML to flatten (-f only; harness mode uses "
             "--togsim-dir/--gem5-dir).",
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
             "Accelergy/Timeloop architecture YAMLs are a harness input: "
             "--harness timeloop --arch-yaml <file>.",
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
        help="Vectorless runs only (-d without -l, or --harness timeloop "
             "WITHOUT --stats): fraction of random switching assumed for the "
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

    harness_group.add_argument(
        "--harness",
        dest="harness",
        help="Select a simulator harness (e.g. 'pytorchsim') and synthesize the "
             "native NPUWattch description + activity from its named inputs.",
    )
    harness_group.add_argument(
        "--togsim-dir",
        dest="togsim_dir",
        help="PyTorchSim harness: directory holding the run's FINAL TOGSim logs "
             "(the root togsim_results/; outputs/<hash>/togsim_result/ are "
             "autotune candidates, not results). Required with --harness pytorchsim.",
    )
    harness_group.add_argument(
        "--config-yml",
        dest="config_yml",
        help="PyTorchSim harness (optional): the run's config.yml. The log "
             "header wins; this fills gaps in damaged headers and cross-checks "
             "the pairing (disagreements are warned).",
    )
    harness_group.add_argument(
        "--gem5-dir",
        dest="gem5_dir",
        help="PyTorchSim harness: directory holding the per-kernel gem5/codegen "
             "dirs (raw run: outputs/; author bundle: gem5_outputs/). Required "
             "with --harness pytorchsim.",
    )
    harness_group.add_argument(
        "--booksim-dir",
        dest="booksim_dir",
        help="PyTorchSim harness (optional): the run's booksim2_config/ "
             "directory. Needed only for anynet NoC topologies (their .net "
             "network file); fly NoCs are self-contained in the log.",
    )
    harness_group.add_argument(
        "--energy-table",
        dest="energy_table",
        help="PyTorchSim harness (optional): the run's DRAM energy-cost table "
             "yml (the config's energy_cost_table_path, e.g. hbm2.yml). Its "
             "constants replace the dram compound's built-in ones; without it "
             "the built-in cited HBM2 constants are charged.",
    )
    harness_group.add_argument(
        "--arch-yaml",
        dest="arch_yaml",
        help="Timeloop harness: the Accelergy/Timeloop architecture YAML "
             "(v0.4, 'architecture:' root). Required with --harness timeloop — "
             "the only route for such files; -d takes native descriptions only.",
    )
    harness_group.add_argument(
        "--stats",
        dest="timeloop_stats",
        help="Timeloop harness (optional): a timeloop-model/mapper .stats.txt "
             "file, or a directory of per-layer stats files (sorted by name = "
             "layer order). Provides real activity (reads/fills+updates/"
             "Computes); without it the run is the labeled VECTORLESS "
             "estimate.",
    )
    harness_group.add_argument(
        "--stats-map",
        dest="stats_map",
        help="Timeloop harness (with --stats): YAML mapping stats level names "
             "to description components ('levels: {LevelName: component}') "
             "and dropping levels deliberately ('ignore: [DRAM]'). Levels "
             "matching a component name (or its dotted leaf) need no entry.",
    )
    harness_group.add_argument(
        "--stats-mode",
        dest="stats_mode",
        choices=["windows", "aggregate"],
        help="Timeloop harness (with --stats): how a DIRECTORY of per-layer "
             "stats files is combined — 'windows' (default) keeps one window "
             "per layer (per-layer energy over time in the report), "
             "'aggregate' sums counts into a single window.",
    )

    # Technology / PVT for harness mode. Defaults are nominal — only an explicitly
    # passed flag overrides them (hp / TT / nominal Vdd / 25C).
    tech_group = parser.add_argument_group(
        "Technology / PVT (harness mode; defaults = hp / TT / nominal Vdd / 25C)"
    )
    tech_group.add_argument(
        "--node", dest="node", default="7nm",
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


def _harness_synthesizes_activity(name: str) -> bool:
    """Whether harness ``name`` declares ``synthesizes_activity`` (no activity
    reader — runs are VECTORLESS, so ``--vectorless-activity`` applies).

    Same fallback contract as ``_check_harness_inputs``: registry import
    failure or an unknown name → permissive here, ``run_harness`` is the
    authority downstream.
    """
    try:
        from npuwattch.harness import available_harnesses
        info = available_harnesses().get(name)
    except Exception:
        return True
    return True if info is None else info.synthesizes_activity


def _check_harness_inputs(parser, ns) -> None:
    """Fail early when the selected harness's required inputs are missing.

    The requirement lives in the harness's ``HARNESS_SPEC``, so a new harness
    (``timeloop`` needs ``--arch-yaml``, not ``--togsim-dir``) is validated
    correctly without touching this parser. If the registry cannot be imported
    the check is skipped — ``run_harness`` validates authoritatively anyway, and
    a broken plugin must not make the CLI unusable.
    """
    try:
        from npuwattch.harness import available_harnesses
        info = available_harnesses().get(ns.harness)
    except Exception:
        return
    if info is None:
        return                            # unknown name → run_harness lists them
    missing = []
    for decl in info.inputs.values():
        flag = decl.get("flag")
        if not decl.get("required", True) or not flag:
            continue
        if not getattr(ns, flag.lstrip("-").replace("-", "_"), None):
            missing.append(f"{flag} ({decl.get('hint', '')})".strip())
    if missing:
        parser.error(
            f"Harness mode (--harness {ns.harness}) requires "
            + "; ".join(missing))


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
    togsim_dir: Optional[Path] = None
    gem5_dir: Optional[Path] = None
    config_yml: Optional[Path] = None
    booksim_dir: Optional[Path] = None
    energy_table: Optional[Path] = None
    arch_yaml: Optional[Path] = None
    timeloop_stats: Optional[Path] = None
    stats_map: Optional[Path] = None
    out_dir: Optional[Path] = None

    if ns.harness and ns.description_files:
        parser.error("--harness and -d/--description are mutually exclusive")
    if not ns.harness and (ns.togsim_dir or ns.gem5_dir or ns.config_yml
                           or ns.booksim_dir or ns.energy_table or ns.arch_yaml
                           or ns.timeloop_stats or ns.stats_map
                           or ns.stats_mode):
        parser.error(
            "--togsim-dir/--gem5-dir/--config-yml/--booksim-dir/--energy-table"
            "/--arch-yaml/--stats/--stats-map/--stats-mode require --harness")
    if (ns.stats_map or ns.stats_mode) and not ns.timeloop_stats:
        parser.error(
            "--stats-map/--stats-mode shape how the Timeloop stats are read; "
            "they require --stats")
    if ns.vectorless_activity is not None:
        if ns.flatten or ns.train or ns.activity_logs:
            parser.error(
                "--vectorless-activity applies only to vectorless runs: -d "
                "WITHOUT -l, or a harness with no activity reader "
                "(it replaces the missing activity log)")
        if ns.timeloop_stats:
            parser.error(
                "--vectorless-activity: --stats provides real Timeloop "
                "activity; the flag applies only to vectorless runs "
                "(-d without -l, or --harness timeloop WITHOUT --stats)")
        if ns.harness and not _harness_synthesizes_activity(ns.harness):
            parser.error(
                f"--vectorless-activity: the {ns.harness!r} harness reads real "
                f"activity from its logs; the flag applies only to vectorless "
                f"runs (-d without -l, or --harness timeloop without --stats)")
        if not (0.0 < ns.vectorless_activity <= 1.0):
            parser.error(
                f"--vectorless-activity must be in (0, 1], got {ns.vectorless_activity}")

    # Validate mode-specific required arguments
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
        # Harness mode: inputs are explicit named directories; -i is retired here
        # (PyTorchSim's two result sets live in separate locations).
        if ns.input_path:
            parser.error(
                "-i is not a harness input; pass --togsim-dir <togsim_results/> "
                "and --gem5-dir <outputs/ | gem5_outputs/> (or use run.sh to "
                "auto-locate both under one root)"
            )
        _check_harness_inputs(parser, ns)
        togsim_dir = Path(ns.togsim_dir) if ns.togsim_dir else None
        gem5_dir = Path(ns.gem5_dir) if ns.gem5_dir else None
        config_yml = Path(ns.config_yml) if ns.config_yml else None
        booksim_dir = Path(ns.booksim_dir) if ns.booksim_dir else None
        energy_table = Path(ns.energy_table) if ns.energy_table else None
        arch_yaml = Path(ns.arch_yaml) if ns.arch_yaml else None
        timeloop_stats = Path(ns.timeloop_stats) if ns.timeloop_stats else None
        stats_map = Path(ns.stats_map) if ns.stats_map else None
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
        togsim_dir=togsim_dir,
        gem5_dir=gem5_dir,
        config_yml=config_yml,
        booksim_dir=booksim_dir,
        energy_table=energy_table,
        arch_yaml=arch_yaml,
        timeloop_stats=timeloop_stats,
        stats_map=stats_map,
        stats_mode=ns.stats_mode,
        out_dir=out_dir,
        vectorless_activity=ns.vectorless_activity,
        tree=bool(ns.tree),
        report_dir=Path(ns.report_dir) if ns.report_dir else None,
        node=ns.node,
        transistor=ns.transistor,
        corner=ns.corner,
        voltage_offset_V=ns.voltage_offset_V,
        temperature_C=ns.temperature_C,
        clock_mhz=ns.clock_mhz,
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