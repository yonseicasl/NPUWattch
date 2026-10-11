"""NPUWattch console application.

This module is the entry point of the NPUWattch CLI. The CLI has four modes:

1. Flatten mode converts an Accelergy v0.4 YAML file to the flattened format.
2. Estimator mode calculates the energy of a native description (``-d``).
3. Harness mode makes the description and the activity rows from the files
   of a simulator (``--harness``), then calculates the energy.
4. Training mode trains the MLP models of an estimator.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List, Optional

from npuwattch.banner import print_banner
from npuwattch.diagnostics import (
    INFO,
    WARNING,
    Diagnostic,
    NPUWattchError,
    as_diagnostic,
    critical,
    emit,
    error,
    info,
    warning,
)
import npuwattch.npuwattch_tables as tbl
from npuwattch.npuwattch_parser import (
    parse_args,
    load_description_files,
)
from npuwattch.npuwattch_estimator_host import EstimatorHost
from npuwattch.user_components import user_components_of
from npuwattch_harness.timeloop.accelergy_flattener import flatten_accelergy_v04_yaml


#: The default clock frequency, in MHz. A run uses it if --clock-mhz, the
#: description, and the log give no clock.
DEFAULT_HARNESS_CLOCK_MHZ = 200.0


def _emit_messages(messages: Iterable, level: str = WARNING) -> None:
    """Print a list of deferred messages (warnings or notes).

    A :class:`Diagnostic` prints with its own code and level. A plain
    ``str`` (from a plugin that does not use the catalog yet) gets the
    generic entry of ``level``. Thus each printed line has a code.
    """
    for m in messages:
        as_diagnostic(m, level).emit()


def _emit_exception(e: BaseException, fallback: Diagnostic) -> None:
    """Print the line of an exception that stops the run.

    An exception with a catalog entry prints its own line. Any other
    exception prints ``fallback``, the message that the call site made from
    its text.
    """
    if isinstance(e, NPUWattchError) and e.number is not None:
        emit(e)
    else:
        fallback.emit()


def _run_flattener(args) -> int:
    """Run the flatten mode."""
    flatten_accelergy_v04_yaml(
        input_yaml=str(args.input_yaml),
        output_yaml=str(args.output_yaml),
        print_tree=(args.verbose >= 1 or args.tree),
    )
    return 0


def _print_tree(root, source: str) -> None:
    """Print the instance hierarchy (``report.tree``) for ``--tree``."""
    from npuwattch.report import render_text

    info(1001, source=source).emit()
    print(tbl.rule("-"))
    print(render_text(root))
    print(tbl.rule("-"))


#: The training script of each estimator. These standalone scripts make the
#: released models. Each script controls the group split, the adaptive loss,
#: and the four checkpoint files (manual §5). The CLI shows the script if an
#: estimator declares no `train_*` entrypoint.
_TRAINERS = {
    "logic": "src/npuwattch_estimators/logic/train_logic.py",
    "sram": "src/npuwattch_estimators/sram/train_sram.py",
}


def _run_training(args, host: EstimatorHost) -> int:
    """Run the training mode."""
    spec = host.get_spec(args.train_estimator) or {}
    entrypoints = spec.get("entrypoints") or {}
    if not any(k.startswith("train") for k in entrypoints):
        script = _TRAINERS.get(args.train_estimator)
        error(1002, estimator=args.train_estimator).emit()
        if script:
            info(1003, script=script).emit()
        return 1

    info(1004).emit()
    info(1005, estimator=args.train_estimator).emit()
    info(1006, model_type=args.train_model_type).emit()
    info(1007, path=args.train_csv).emit()
    info(1008, epochs=args.train_epochs, batch_size=args.train_batch_size,
         lr=args.train_lr).emit()
    print("=" * 80)  # nw-lint: text

    result, train_error = host.train_model(
        module_name=args.train_estimator,
        model_type=args.train_model_type,
        csv_file=str(args.train_csv),
        output_path=str(args.train_output) if args.train_output else None,
        epochs=args.train_epochs,
        batch_size=args.train_batch_size,
        lr=args.train_lr,
    )

    if train_error:
        error(1009, error=getattr(train_error, "text", None) or train_error).emit()
        return 1

    info(1010).emit()
    return 0

def _resolve_tech_node(chain, tech):
    """Apply the continuous node axis to the provider chain (manual §6.2).

    The new chain answers a query for each node that can be parsed. It uses
    the characterized nodes as anchors.

    Interpolation in the characterized range gives a note. Extrapolation and
    a clamp to the envelope give warnings. This function prints the notes and
    the warnings. The caller also gives the warnings
    (``NodeResolution.warnings``) to the report.

    Raises ``NodeError`` (a ``ValueError``) if the node cannot be parsed. The
    callers change this into a CLI error.
    """
    from npuwattch.energy import apply_node_scaling

    chain, resolution = apply_node_scaling(chain, tech)
    if resolution is not None:
        _emit_messages(resolution.notes, INFO)
        _emit_messages(resolution.warnings, WARNING)
    return chain, resolution


def _run_native_estimator(args, description) -> int:
    """Run the native path: ``-d description.yaml [-l activity.csv]``, then §6.

    A native description (``npuwattch:`` root) contains all the data of the
    design. The technology, the PVT values, and the clock come from its
    ``technology:`` and ``clock:`` blocks. The technology flags of the CLI
    apply only to harness mode. The energy calculation is ``aggregate_native``,
    which the harness path also uses.

    Without ``-l`` the run is a **VECTORLESS** estimate. The activity is
    synthetic, at 25 % of random switching (manual §6).
    ``--vectorless-activity`` changes this fraction.
    """
    from npuwattch.energy import (
        DEFAULT_VECTORLESS_ACTIVITY,
        TechContext,
        aggregate_native,
        build_provider,
        read_activity_csv,
        vectorless_activity_rows,
    )

    info(1011).emit()

    if args.tree:
        # The tree is only a view. A failure here gives a warning, and the
        # energy calculation continues.
        try:
            from npuwattch.report import tree_from_native
            _print_tree(tree_from_native(description),
                        "flat native description; dot-grouped")
        except Exception as e:
            warning(1012, error=e).emit()

    if len(args.activity_logs) > 1:
        error(1013, count=len(args.activity_logs),
              paths=", ".join(str(p) for p in args.activity_logs)).emit()
        return 1

    nw = description.get("npuwattch", {})
    t = nw.get("technology") or {}
    tech = TechContext(
        node=t.get("node", "7nm"),
        transistor=t.get("transistor", "hp"),
        corner=t.get("corner", "TT"),
        voltage_offset_V=float(t.get("voltage_offset_V", 0.0)),
        temperature_C=float(t.get("temperature_C", 25.0)),
        clock_mhz=(nw.get("clock") or {}).get("frequency_MHz"),
    )
    info(1014, node=tech.node, transistor=tech.transistor, corner=tech.corner,
         voltage_offset_V=tech.voltage_offset_V,
         temperature_C=tech.temperature_C).emit()

    if args.activity_logs:
        activity_path = Path(args.activity_logs[0])
        try:
            rows, total_cycles = read_activity_csv(activity_path)
        except Exception as e:
            error(1015, path=activity_path, error=e).emit()
            return 1
        if total_cycles:
            info(1017, path=activity_path, rows=len(rows),
                 total_cycles=total_cycles).emit()
        else:
            info(1016, path=activity_path, rows=len(rows)).emit()
    else:
        activity = (args.vectorless_activity
                    if args.vectorless_activity is not None
                    else DEFAULT_VECTORLESS_ACTIVITY)
        try:
            rows, notes = vectorless_activity_rows(description, activity=activity)
        except ValueError as e:
            _emit_exception(e, error(1018, error=e))
            return 1
        _emit_messages(notes, INFO)

    naming_warnings: List[str] = []
    try:
        chain = build_provider(verbose=args.verbose,
                               user_components=user_components_of(description))
        chain, node_res = _resolve_tech_node(chain, tech)
        run_energy = aggregate_native(
            description, rows, chain.provider, tech,
            default_clock_mhz=DEFAULT_HARNESS_CLOCK_MHZ,
            warnings=naming_warnings,
            clock_check=args.show_fmax,
        )
    except ValueError as e:                 # catalog errors and user input
        _emit_exception(e, error(1018, error=e))
        return 1
    except Exception as e:
        _emit_exception(e, critical(1019, error=e))
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        return 1

    _emit_messages(naming_warnings, WARNING)
    extra_tag = None
    if not args.activity_logs:
        pct = (args.vectorless_activity
               if args.vectorless_activity is not None
               else DEFAULT_VECTORLESS_ACTIVITY)
        extra_tag = f"VECTORLESS ({pct:.0%} of random)"
    _print_run_energy(run_energy, chain, extra_tag=extra_tag,
                      verbose=args.verbose)

    desc_path = Path(args.description_files[0])
    try:
        from npuwattch.report import tree_from_native
        hierarchy = tree_from_native(description)
    except Exception as e:                       # only a view: the run continues
        hierarchy = None
        naming_warnings.append(warning(1020, error=e))
    vectorless = None
    if not args.activity_logs:
        vectorless = (args.vectorless_activity
                      if args.vectorless_activity is not None
                      else DEFAULT_VECTORLESS_ACTIVITY)
    inputs = [(desc_path.name, desc_path)]
    if args.activity_logs:
        act_path = Path(args.activity_logs[0])
        inputs.append((act_path.name, act_path))
    _maybe_write_report(
        args, run=run_energy, description=description, tech=tech, chain=chain,
        rows=rows, hierarchy=hierarchy,
        warnings=[*naming_warnings,
                  *(node_res.warnings if node_res is not None else ())],
        design_name=desc_path.stem,
        activity_source=(str(args.activity_logs[0]) if args.activity_logs
                         else f"vectorless default ({vectorless:.0%} of random)"),
        vectorless=vectorless, inputs=inputs, node_resolution=node_res,
    )
    return 0


def _run_estimator(args) -> int:
    """Run the estimator mode, which accepts only a native description.

    ``-d`` takes a native NPUWattch description (``npuwattch:`` root, §3.1).
    An Accelergy/Timeloop description (``architecture:`` root) is a harness
    input. Give it to ``--harness timeloop --arch-yaml``. Thus each input
    type has one flag, as for all harnesses.
    """
    info(1021).emit()
    print(tbl.rule("="))

    if not args.description_files:
        error(1115).emit()
        return 1
    desc_path = Path(args.description_files[0])
    if len(args.description_files) > 1:
        error(1022, count=len(args.description_files)).emit()
        return 1
    if not desc_path.is_file():
        error(1023, path=desc_path).emit()
        return 1
    # A native description is plain YAML with an `npuwattch:` root. A file
    # with an `architecture:` root, or with the `!Container`/`!Component`
    # tags of Accelergy, is an input of the timeloop harness. This mode does
    # not run such a file. It prints the correct command.
    try:
        content = (load_description_files([desc_path]) or [{}])[0]
    except Exception:
        content = None
    if isinstance(content, dict) and "npuwattch" in content:
        return _run_native_estimator(args, content)
    error(1024, path=desc_path).emit()
    info(1025, path=desc_path).emit()
    return 1


def _run_harness(args) -> int:
    """Run the harness mode.

    The selected harness makes a native description and activity rows from
    the files of a simulator. Then the energy calculation is the same §6
    calculation as in ``-d``/``-l`` mode.

    ``energy.provider_factory`` builds the provider chain.
    """
    from npuwattch.arch_synth import write_arch
    from npuwattch.energy import TechContext, aggregate_native, build_provider
    from npuwattch_harness import HarnessError, get_harness, run_harness

    info(1026, harness=args.harness).emit()
    print(tbl.rule("="))

    tech = TechContext(
        node=args.node,
        transistor=args.transistor,
        corner=args.corner,
        voltage_offset_V=args.voltage_offset_V,
        temperature_C=args.temperature_C,
        clock_mhz=args.clock_mhz,
    )

    # The parser made `harness_inputs` and `harness_options` from the flags
    # that the harnesses declare (HARNESS_SPEC). They contain only the flags
    # that the user gave. The registry rejects an input that the selected
    # harness does not declare, thus a flag of a different harness is an
    # error and is not ignored.
    harness_inputs = dict(args.harness_inputs)
    # Options that each ingest accepts through **opts. The parser rejects
    # --vectorless-activity for a run that reads real activity.
    opts = {"default_clock_mhz": DEFAULT_HARNESS_CLOCK_MHZ,
            "verbose": args.verbose,
            "node_explicit": args.node_explicit,
            **args.harness_options}
    if args.vectorless_activity is not None:
        opts["vectorless_activity"] = args.vectorless_activity
    try:
        # Clock priority: --clock-mhz (in tech), then the harness log, then
        # the 200 MHz default.
        emitted = run_harness(args.harness, harness_inputs, tech, **opts)
    except (HarnessError, NPUWattchError) as e:   # a catalog error
        _emit_exception(e, error(1018, error=e))
        return 1
    except Exception as e:
        _emit_exception(e, critical(1027, error=e))
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        return 1

    if args.tree:
        if emitted.hierarchy is not None:
            _print_tree(emitted.hierarchy,
                        emitted.tree_source or "reconstructed from the run's model")
        else:
            warning(1028).emit()

    # Print the warnings of the harness (for example, activity that it cannot
    # interpret). Then print the notes: the exclusions that the projection
    # declares (waivers, out_of_scope).
    _emit_messages(emitted.warnings, WARNING)
    _emit_messages(emitted.notes, INFO)

    # Provenance of each window: the kind, the source of the dtype, and the
    # main counters. One line for each window is too much for the default
    # output of a large model. Thus the lines are printed only at -v 2 or
    # more. report.json always contains them.
    if args.verbose >= 2 and emitted.window_provenance:
        info(1029, count=len(emitted.window_provenance)).emit()
        for p in emitted.window_provenance:
            print(f"         window {p['window']}: {p['kernel']}  "  # nw-lint: text
                  f"kind={p['kind']}  dtype={p['dtype']} ({p['dtype_source']})  "
                  f"systolic={p['systolic_active_cycles']}  "
                  f"vector={p['vector_active_cycles']}  sfu={p['sfu_ops']}  "
                  f"dram_reqs={p['dram_requests']}  cycles={p['exec_cycles']}")

    # If --out is given, write the native description and the activity CSV.
    if args.out_dir is not None:
        desc_path, act_path = write_arch(emitted, args.out_dir)
        info(1030, path=desc_path).emit()
        info(1031, path=act_path).emit()

    # §6: calculate the energy from the description and its activity rows.
    energy_warnings: List[str] = []
    try:
        chain = build_provider(
            verbose=args.verbose,
            user_components=user_components_of(emitted.description))
        chain, node_res = _resolve_tech_node(chain, tech)
        run_energy = aggregate_native(
            emitted.description, emitted.activity_rows, chain.provider, tech,
            default_clock_mhz=DEFAULT_HARNESS_CLOCK_MHZ,
            window_labels=emitted.window_labels,
            warnings=energy_warnings,
            clock_check=args.show_fmax,
        )
    except ValueError as e:
        _emit_exception(e, error(1018, error=e))
        return 1
    _emit_messages(energy_warnings, WARNING)
    # If a harness makes synthetic activity, each output must show
    # VECTORLESS.
    vectorless = emitted.vectorless_activity
    _print_run_energy(
        run_energy, chain, verbose=args.verbose,
        extra_tag=(None if vectorless is None
                   else f"VECTORLESS ({vectorless:.0%} of random)"),
        window_provenance=emitted.window_provenance)

    # Provenance: each named input that the user gave, in the order of the
    # HARNESS_SPEC declaration. Directories come first, as labels. A file
    # input is embedded in the report. An input of kind "path" can be a
    # directory (for example, per-layer stats), which stays a label.
    declared = get_harness(args.harness).inputs
    inputs = [(f"{name}: {harness_inputs[name]}", None)
              for name, decl in declared.items()
              if name in harness_inputs and decl.get("kind", "dir") == "dir"]
    design_name = args.harness
    for name, decl in declared.items():
        if name not in harness_inputs:
            continue
        path = Path(harness_inputs[name])
        if decl.get("kind", "dir") != "dir":
            inputs.append((path.name, path) if path.is_file()
                          else (f"{name}: {path}", None))
        # The input that declares `names_design` gives the design name.
        if decl.get("names_design") == "parent":
            design_name = path.resolve().parent.name
        elif decl.get("names_design") == "stem":
            design_name = path.stem
    _maybe_write_report(
        args, run=run_energy, description=emitted.description, tech=tech,
        chain=chain, rows=emitted.activity_rows, hierarchy=emitted.hierarchy,
        warnings=[*emitted.warnings, *energy_warnings,
                  *(node_res.warnings if node_res is not None else ())],
        notes=emitted.notes, node_resolution=node_res,
        design_name=design_name,
        activity_source=(f"{args.harness} harness (simulator logs)"
                         if vectorless is None else
                         f"{args.harness} harness, vectorless default "
                         f"({vectorless:.0%} of random)"),
        vectorless=vectorless, inputs=inputs,
        window_provenance=emitted.window_provenance,
    )
    return 0


def _maybe_write_report(args, *, run, description, tech, chain, rows,
                        hierarchy, warnings, design_name, activity_source,
                        vectorless=None, inputs=(), notes=(),
                        window_provenance=(), node_resolution=None) -> None:
    """Write report.html and report.json if ``--report DIR`` is given.

    The report is only presentation. A failure here gives a warning and does
    not change the console results. ``--tree`` obeys the same rule.
    """
    if args.report_dir is None:
        return
    try:
        from npuwattch.report import build_context, write_report

        ctx = build_context(
            run, description, tech=tech, design_name=design_name,
            activity_source=activity_source, chain=chain, hierarchy=hierarchy,
            warnings=warnings, notes=notes, activity_rows=rows, inputs=inputs,
            vectorless=vectorless, window_provenance=window_provenance,
            node_resolution=node_resolution, timing=args.show_fmax,
        )
        html_path, json_path = write_report(ctx, args.report_dir)
        info(1032, path=html_path).emit()
        info(1033, path=json_path).emit()
    except Exception as e:
        warning(1034, error=e).emit()
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()


def _print_window_energy(run, verbose: int = 0,
                         window_provenance=None) -> None:
    """Print the §6 energy of each window.

    The table has one line for each window. The run total is the sum of
    these lines. Then a matrix shows the dynamic energy of each component in
    each window. The matrix does not show a component that has only leakage.
    The energy summary shows it.

    ``window_provenance`` (harness runs) adds a ``kind`` column: mac, fused,
    or non_mac. If non-MAC kernels are present, it also adds a line with the
    GEMM and non-GEMM subtotals. This line shows the energy that is outside
    the systolic array.

    Terminology: a window is one time interval of the activity (manual
    §3.3). ``WindowEnergy.label`` gives its name. Examples of a window are a
    gem5 periodic dump, a Timeloop layer, and the vectorless synthetic
    interval. In the PyTorchSim harness, one kernel is one window. Thus the
    printed text of such a run uses the word "kernel". ``window_provenance``
    is present only for such a run. The schema names and the code names use
    ``window``.
    """
    n = len(run.windows)
    kinds = {}
    if window_provenance:
        kinds = {p["window"]: p["kind"] for p in window_provenance}
    term = "kernel" if window_provenance else "window"
    print("\n" + tbl.rule("="))  # nw-lint: text
    info(1035, term=term, count=n, noun=term if n == 1 else f"{term}s").emit()

    table = tbl.make_table()
    cols = [("#", "right"), (term, "left")]
    if kinds:
        cols.append(("kind", "left"))
    cols += [("cycles", "right"), ("dyn (pJ)", "right"), ("leak (pJ)", "right"),
             ("total (pJ)", "right"), ("avg power (mW)", "right")]
    tbl.add_columns(table, cols)
    for i, w in enumerate(run.windows):
        row = [str(i), w.label]
        if kinds:
            row.append(kinds.get(i, "?"))
        row += [f"{w.exec_cycles}", f"{w.dyn_energy_pJ:.4g}",
                f"{w.leak_energy_pJ:.4g}", f"{w.total_energy_pJ:.4g}",
                f"{w.avg_power_mW:.4g}"]
        table.add_row(*row)
    tbl.print_table(table)

    if kinds and any(k == "non_mac" for k in kinds.values()):
        mac_tot = sum(w.total_energy_pJ for i, w in enumerate(run.windows)
                      if kinds.get(i) != "non_mac")
        non_tot = sum(w.total_energy_pJ for i, w in enumerate(run.windows)
                      if kinds.get(i) == "non_mac")
        total = mac_tot + non_tot
        pct = (100.0 * non_tot / total) if total else 0.0
        n_non = sum(1 for k in kinds.values() if k == "non_mac")
        info(1036, gemm_pJ=mac_tot, gemm_windows=n - n_non,
             non_gemm_pJ=non_tot, non_gemm_windows=n_non, percent=pct).emit()
    _print_window_component_matrix(run, term=term)


def _print_window_component_matrix(run, term: str = "window") -> None:
    """Print the dynamic energy (pJ) of each component in each window.

    The rows are components and the columns are windows. The columns are
    divided into groups, thus each table fits the console width. ``term`` is
    the printed word for a window (see ``_print_window_energy``)."""
    if not run.windows:
        return
    all_names = list(run.windows[0].components)
    active = [name for name in all_names
              if any(w.components[name].dyn_energy_pJ for w in run.windows)]
    if not active:
        return
    info(1037, term=term).emit()

    short, prefix = tbl.strip_common_prefix(active)
    cells = {
        name: [f"{w.components[name].dyn_energy_pJ:.4g}"
               if w.components[name].dyn_energy_pJ else "-"
               for w in run.windows]
        for name in active
    }
    # Divide the window columns into groups that fit the console. The widths
    # come from the data, thus a long name makes its column wider.
    name_w = max([len("component")] + [len(s) for s in short])
    col_w = max([len(w.label) for w in run.windows]
                + [len(c) for row in cells.values() for c in row])
    per_chunk = tbl.column_capacity(name_w, col_w)

    if prefix:
        print(tbl.note(f"component names relative to '{prefix}'"))
    for start in range(0, len(run.windows), per_chunk):
        chunk = list(enumerate(run.windows))[start:start + per_chunk]
        table = tbl.make_table()
        tbl.add_columns(table, [("component", "left")]
                        + [(w.label, "right") for _, w in chunk])
        for name, label in zip(active, short):
            table.add_row(label, *[cells[name][i] for i, _ in chunk])
        tbl.print_table(table)
    idle = len(all_names) - len(active)
    if idle:
        info(1038, count=idle).emit()


def _print_run_energy(run, chain=None, extra_tag=None, verbose: int = 0,
                      window_provenance=None) -> None:
    """Print the §6 energy summary: one row for each component, then the
    run totals.

    The summary shows the source of the values of each primitive:

    - calibrated: a trained estimator (logic, sram).
    - constant: a table constant (`hbm`, `d2dlink`).
    - user: a component of the user component library.
    """
    _print_window_energy(run, verbose=verbose,
                         window_provenance=window_provenance)

    calibrated_prims = tuple(getattr(chain, "calibrated_primitives", ()) or ())
    constant_prims = tuple(getattr(chain, "constant_primitives", ()) or ())
    user_prims = tuple(getattr(chain, "user_primitives", ()) or ())

    per_comp: dict = {}
    for w in run.windows:
        for name, c in w.components.items():
            agg = per_comp.get(name)
            if agg is None:
                per_comp[name] = [c.primitive, c.instances, c.dyn_energy_pJ,
                                  c.leak_energy_pJ, c.area_um2]
            else:
                agg[2] += c.dyn_energy_pJ
                agg[3] += c.leak_energy_pJ

    prims = {v[0] for v in per_comp.values()}
    users = prims & set(user_prims)
    hits = (prims - users) & set(calibrated_prims)
    consts = (prims - users - hits) & set(constant_prims)
    others = prims - users - hits - consts
    if prims and not (users or consts or others):
        tag = "calibrated"
    else:
        parts = []
        if hits:
            parts.append(f"calibrated: {', '.join(sorted(hits))}")
        if consts:
            parts.append(f"constant: {', '.join(sorted(consts))}")
        if users:
            parts.append(f"user: {', '.join(sorted(users))}")
        if others:
            parts.append(f"uncalibrated: {', '.join(sorted(others))}")
        tag = "PARTIAL — " + "; ".join(parts)

    print("\n" + tbl.rule("="))  # nw-lint: text
    if extra_tag:
        tag = f"{extra_tag} — {tag}"
    info(1039, tag=tag).emit()

    short, prefix = tbl.strip_common_prefix(list(per_comp))
    if prefix:
        print(tbl.note(f"component names relative to '{prefix}'"))
    table = tbl.make_table()
    tbl.add_columns(table, [("component", "left"), ("model", "right"),
                            ("instances", "right"), ("dyn (pJ)", "right"),
                            ("leak (pJ)", "right"), ("area (um2)", "right")])
    for label, (prim, inst, dyn, leak, area) in zip(short, per_comp.values()):
        mark = ("user" if prim in user_prims
                else "cal" if prim in calibrated_prims
                else "const" if prim in constant_prims else "uncal")
        table.add_row(label, mark, f"{inst}", f"{dyn:.4g}", f"{leak:.4g}",
                      f"{area:.4g}")
    tbl.print_table(table)

    # DRAM energy for each command type (the §6 split by mode): activation,
    # transfer, and refresh. Activation and transfer are the terms of the
    # DRAM simulator. Refresh is an NPUWattch addition. The line is printed
    # only if the run has energy in these modes. A vectorless run charges
    # hbm in the `random` mode, thus it prints no line.
    dram_names = [name for name, v in per_comp.items() if v[0] == "hbm"]
    dram_modes: dict = {}
    for w in run.windows:
        for name in dram_names:
            for mode, e in w.components[name].dyn_by_mode.items():
                dram_modes[mode] = dram_modes.get(mode, 0.0) + e
    act = dram_modes.get("activate", 0.0)
    rd, wr = dram_modes.get("read", 0.0), dram_modes.get("write", 0.0)
    ref = dram_modes.get("refresh", 0.0)
    dram_tot = act + rd + wr + ref
    if dram_tot > 0:
        print(tbl.rule("-"))
        info(1040, components=", ".join(dram_names), activate_pJ=act,
             activate_pct=100 * act / dram_tot, transfer_pJ=rd + wr,
             transfer_pct=100 * (rd + wr) / dram_tot, read_pJ=rd, write_pJ=wr,
             refresh_pJ=ref, refresh_pct=100 * ref / dram_tot).emit()
    print(tbl.rule("-"))
    print(f"total energy = {run.total_energy_pJ:.4g} pJ "  # nw-lint: text
          f"(dyn {run.dyn_energy_pJ:.4g} + leak {run.leak_energy_pJ:.4g}); "
          f"avg power = {run.avg_power_mW:.4g} mW; exec = {run.exec_time_s:.4g} s")
    if calibrated_prims:
        print("calibrated primitives available: "  # nw-lint: text
              f"{', '.join(calibrated_prims)}")
    _emit_messages(getattr(chain, "notes", ()) or (), WARNING)
    print(tbl.rule("="))


def _print_catalog(prefix: str) -> int:
    """Print the message catalog for ``--list-messages [PREFIX]``."""
    from npuwattch import diagnostics

    rows = diagnostics.listing(prefix)
    for e, level in rows:
        owner = f" [{e.kind}]" if e.is_exception else ""
        print(f"{e.code:<9} {level:<8} {e.template}{owner}")  # nw-lint: text
    print(f"{len(rows)} message(s)")  # nw-lint: text
    return 0


def _print_message_summary() -> None:
    """Print the message summary at the end of a run (EDA style).

    One INFO line gives the count of each level. Then one row for each
    WARNING, ERROR and CRITICAL code gives the number of its messages."""
    from npuwattch import diagnostics

    s = diagnostics.summary()
    n = s["by_level"]
    counts = dict(critical=n["CRITICAL"], error=n["ERROR"],
                  warning=n["WARNING"], info=n["INFO"])
    suppressed = s["suppressed"]
    print(tbl.rule("-"))
    if suppressed:
        info(1903, **counts, suppressed=sum(suppressed.values()),
             codes=", ".join(f"{c} x{k}" for c, k in suppressed.items())).emit()
    else:
        info(1902, **counts).emit()
    for code, rec in s["by_code"].items():
        print(f"    {code:<9} {rec['level']:<8} x{rec['count']}")  # nw-lint: text


def main(argv: Optional[List[str]] = None) -> int:
    """Run the NPUWattch CLI and return the exit code."""
    from npuwattch import diagnostics

    print_banner()
    diagnostics.reset()

    argv_list: List[str] = list(sys.argv[1:] if argv is None else argv)

    try:
        args = parse_args(argv_list)
    except SystemExit as e:
        return 0 if (e.code == 0) else 1

    if args.list_messages is not None:
        return _print_catalog(args.list_messages)
    if args.explain is not None:
        try:
            print(diagnostics.explain(args.explain))  # nw-lint: text
        except ValueError as e:
            error(1904, problem=e).emit()
            return 1
        return 0
    diagnostics.suppress(args.suppress)

    try:
        # Training mode uses the estimator host.
        if args.train:
            host = EstimatorHost(verbose=args.verbose)
            host.scan_estimators()
            return _run_training(args, host)

        # Select the mode.
        if args.flatten:
            return _run_flattener(args)

        if args.harness:
            return _run_harness(args)

        return _run_estimator(args)
    finally:
        _print_message_summary()


if __name__ == "__main__":
    raise SystemExit(main())