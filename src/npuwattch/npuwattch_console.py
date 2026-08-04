"""NPUWattch Console Application.

This is the main entry point for the NPUWattch CLI tool.
Supports three modes:
1. Flatten mode: Convert Accelergy v0.4 YAML to flattened format
2. Estimator mode: Run energy/area/timing estimation on architecture
3. Training mode: Train MLP models for estimation
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import npuwattch.npuwattch_messages as msg
from npuwattch.npuwattch_parser import (
    parse_args,
    load_description_files,
    load_activity_logs,
)
from npuwattch.npuwattch_estimator_host import EstimatorHost
from npuwattch.yaml_flattener_accelergy_v4 import flatten_accelergy_v04_yaml
from npuwattch.npuwattch_db import build_database, NPUWattchDatabase, ComponentEntry


#: Harness-mode clock fallback when neither --clock-mhz nor the log provides one.
DEFAULT_HARNESS_CLOCK_MHZ = 200.0


def _run_flattener(args) -> int:
    """Run YAML flattener mode."""
    flatten_accelergy_v04_yaml(
        input_yaml=str(args.input_yaml),
        output_yaml=str(args.output_yaml),
        print_tree=(args.verbose >= 1 or args.tree),
    )
    return 0


def _print_tree(root, source: str) -> None:
    """Render the instance-hierarchy view (report.tree) for --tree."""
    from npuwattch.report import render_text

    print(f"[INFO] Instance hierarchy ({source}):")
    print("-" * 100)
    print(render_text(root))
    print("-" * 100)


def _run_training(args, host: EstimatorHost) -> int:
    """Run model training mode."""
    print(f"[INFO] Starting training mode")
    print(f"[INFO] Estimator: {args.train_estimator}")
    print(f"[INFO] Model type: {args.train_model_type}")
    print(f"[INFO] Training data: {args.train_csv}")
    print(f"[INFO] Epochs: {args.train_epochs}, Batch size: {args.train_batch_size}, LR: {args.train_lr}")
    print("=" * 80)

    result, error = host.train_model(
        module_name=args.train_estimator,
        model_type=args.train_model_type,
        csv_file=str(args.train_csv),
        output_path=str(args.train_output) if args.train_output else None,
        epochs=args.train_epochs,
        batch_size=args.train_batch_size,
        lr=args.train_lr,
    )

    if error:
        print(f"[ERROR] Training failed: {error}")
        return 1

    print("[INFO] Training completed successfully!")
    return 0

def _run_native_estimator(args, description) -> int:
    """Direct native path: `-d description.yaml (npuwattch:) [-l activity.csv]` → §6.

    The native description is self-contained — technology/PVT and clock come from its
    own ``technology:``/``clock:`` blocks, not from the harness-mode CLI flags (those
    exist because a harness has no description yet). Energy uses the same
    ``aggregate_native`` core the harness path uses. Without ``-l`` the run is a
    **VECTORLESS** estimate: synthetic activity at 25 % of random switching
    (``--vectorless-activity`` overrides; manual §6).
    """
    from npuwattch.energy import (
        DEFAULT_VECTORLESS_ACTIVITY,
        TechContext,
        aggregate_native,
        build_provider,
        read_activity_csv,
        vectorless_activity_rows,
    )

    print("[INFO] Native NPUWattch description detected (§3.1)")

    if args.tree:
        # The tree is a VIEW: it must never block the run (per-component energy
        # accounting below is what actually matters). Failure → warn, continue.
        try:
            from npuwattch.report import tree_from_native
            _print_tree(tree_from_native(description),
                        "flat native description; dot-grouped")
        except Exception as e:
            print(f"[WARNING] --tree: hierarchy view unavailable: {e}")

    if len(args.activity_logs) > 1:
        print(f"[ERROR] Native mode expects exactly one activity CSV, got "
              f"{len(args.activity_logs)}: {', '.join(str(p) for p in args.activity_logs)}")
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
    print(f"[INFO] Technology: {tech.node} / {tech.transistor} / {tech.corner} / "
          f"{tech.voltage_offset_V:+.3f} V / {tech.temperature_C} C")

    if args.activity_logs:
        activity_path = Path(args.activity_logs[0])
        try:
            rows, total_cycles = read_activity_csv(activity_path)
        except Exception as e:
            print(f"[ERROR] Failed to read activity CSV {activity_path}: {e}")
            return 1
        print(f"[INFO] Activity: {activity_path} ({len(rows)} rows"
              f"{f', total_cycles={total_cycles}' if total_cycles else ''})")
    else:
        activity = (args.vectorless_activity
                    if args.vectorless_activity is not None
                    else DEFAULT_VECTORLESS_ACTIVITY)
        try:
            rows, notes = vectorless_activity_rows(description, activity=activity)
        except ValueError as e:
            print(f"[ERROR] {e}")
            return 1
        for note in notes:
            print(f"[INFO] {note}")

    naming_warnings: List[str] = []
    try:
        chain = build_provider(verbose=args.verbose)
        run_energy = aggregate_native(
            description, rows, chain.provider, tech,
            default_clock_mhz=DEFAULT_HARNESS_CLOCK_MHZ,
            warnings=naming_warnings,
        )
    except Exception as e:
        print(f"[ERROR] Energy aggregation failed: {e}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        return 1

    for w in naming_warnings:
        print(f"[WARNING] {w}")
    extra_tag = None
    if not args.activity_logs:
        pct = (args.vectorless_activity
               if args.vectorless_activity is not None
               else DEFAULT_VECTORLESS_ACTIVITY)
        extra_tag = f"VECTORLESS ({pct:.0%} of random)"
    _print_run_energy(run_energy, chain, extra_tag=extra_tag,
                      verbose=args.verbose)

    desc_path = Path(args.description_files[0])
    hierarchy = None
    try:
        from npuwattch.report import tree_from_native
        hierarchy = tree_from_native(description)
    except Exception as e:                       # view only — never fatal
        naming_warnings.append(f"hierarchy view unavailable: {e}")
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
        rows=rows, hierarchy=hierarchy, warnings=naming_warnings,
        design_name=desc_path.stem,
        activity_source=(str(args.activity_logs[0]) if args.activity_logs
                         else f"vectorless default ({vectorless:.0%} of random)"),
        vectorless=vectorless, inputs=inputs,
    )
    return 0


def _run_estimator(args) -> int:
    """Run estimator (normal) mode."""
    print("[INFO] Starting estimator mode")
    print("=" * 100)

    # Native NPUWattch description (`npuwattch:` root) takes the native §6 path.
    # Accelergy-style (`architecture:` root) keeps the legacy flatten+estimate path
    # until it moves under `--harness timeloop`.
    if args.description_files:
        try:
            loaded = load_description_files([Path(args.description_files[0])])
        except Exception as e:
            print(f"[ERROR] Failed to read description {args.description_files[0]}: {e}")
            return 1
        content = loaded[0] if loaded else {}
        if isinstance(content, dict) and "npuwattch" in content:
            return _run_native_estimator(args, content)
        print("[INFO] Accelergy-style description detected "
              "(this path moves under --harness timeloop in a future release).")
        if args.report_dir is not None:
            print("[WARNING] --report requires the native §6 path (native "
                  "description or --harness); ignored for the legacy Accelergy "
                  "flow.")

    # Initialize estimator host
    host = EstimatorHost(verbose=args.verbose)
    host.scan_estimators()

    try:
        # Process each description file
        flattened_files: List[Path] = []
        databases: List[NPUWattchDatabase] = []

        for desc_file in args.description_files:
            desc_path = Path(desc_file)
            flattened_path = desc_path.parent / f"{desc_path.stem}_flattened{desc_path.suffix}"

            if args.tree:
                # Harness-owned builder: the Accelergy path belongs to the
                # (future) Timeloop harness, so its tree builder lives there.
                # NB the declared hierarchy itself is NOT just this view — the
                # flatten+estimate below keeps every declared component's own
                # identity/energy; only the tree display is optional.
                try:
                    from npuwattch.harness.timeloop.tree import tree_from_accelergy
                    _print_tree(tree_from_accelergy(desc_path),
                                "declared in the Accelergy description")
                except Exception as e:
                    print(f"[WARNING] --tree: hierarchy view unavailable: {e}")

            # Flatten the YAML
            print(f"[INFO] Flattening {desc_path}...")
            flatten_accelergy_v04_yaml(
                input_yaml=str(desc_path),
                output_yaml=str(flattened_path),
                print_tree=(args.verbose >= 1),
            )
            flattened_files.append(flattened_path)

            # Build database
            db = build_database(
                yaml_path=flattened_path,
                verbose=args.verbose,
            )
            databases.append(db)

        # Report available estimators
        if args.verbose >= 1:
            host.report_to_console()

        # Run estimation on each database
        host.estimate_databases(databases)

        print("\n[INFO] Estimation completed.")
        return 0

    except Exception as e:
        print(f"[ERROR] Estimation failed: {e}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        return 1


def _run_harness(args) -> int:
    """Run harness mode: a simulator run directory → native NPUWattch description +
    activity (via the selected harness) → the same §6 core as ``-d``/``-l`` mode.

    Energy uses the composed provider chain (calibrated estimators over a
    placeholder base). The HTML/JSON report (R1) is still pending.
    """
    from npuwattch.arch_synth import write_arch
    from npuwattch.energy import TechContext, aggregate_native, build_provider
    from npuwattch.harness import HarnessError, run_harness

    print(f"[INFO] Harness mode: {args.harness}")
    print("=" * 100)

    tech = TechContext(
        node=args.node,
        transistor=args.transistor,
        corner=args.corner,
        voltage_offset_V=args.voltage_offset_V,
        temperature_C=args.temperature_C,
        clock_mhz=args.clock_mhz,
    )

    try:
        # Clock precedence: --clock-mhz (in tech) > harness log > 200 MHz fallback.
        emitted = run_harness(
            args.harness,
            {"togsim": args.togsim_dir, "gem5": args.gem5_dir,
             "config": args.config_yml, "booksim": args.booksim_dir},
            tech,
            default_clock_mhz=DEFAULT_HARNESS_CLOCK_MHZ,
        )
    except HarnessError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Harness ingest failed: {e}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        return 1

    if args.tree:
        if emitted.hierarchy is not None:
            _print_tree(emitted.hierarchy, "reconstructed from the run's model")
        else:
            print("[WARNING] --tree: no hierarchy view for this run "
                  "(the emitter's warnings below say why); energy accounting "
                  "is unaffected")

    # Surface the emitter's gate warnings (uninterpreted activity, reconfig, etc.),
    # then the INFO tier: exclusions the projection declares (waivers/out_of_scope).
    for w in emitted.warnings:
        print(f"[WARNING] {w}")
    for n in emitted.notes:
        print(f"[INFO] {n}")

    # Per-kernel provenance (parsed data: kind / dtype origin / headline
    # counters). One line per kernel is too chatty for the default output of a
    # many-kernel model run, so it sits at -v>=2 (the per-window-detail tier);
    # report.json carries it unconditionally.
    if args.verbose >= 2 and emitted.window_provenance:
        print(f"[INFO] Per-kernel provenance "
              f"({len(emitted.window_provenance)} kernel(s)):")
        for p in emitted.window_provenance:
            print(f"[INFO]   window {p['window']}: {p['kernel']}  "
                  f"kind={p['kind']}  dtype={p['dtype']} ({p['dtype_source']})  "
                  f"systolic={p['systolic_active_cycles']}  "
                  f"vector={p['vector_active_cycles']}  sfu={p['sfu_ops']}  "
                  f"dram_reqs={p['dram_requests']}  cycles={p['exec_cycles']}")

    # Optionally persist the native artifacts for inspection / re-runs.
    if args.out_dir is not None:
        desc_path, act_path = write_arch(emitted, args.out_dir)
        print(f"[INFO] Wrote native description: {desc_path}")
        print(f"[INFO] Wrote native activity:    {act_path}")

    # §6: aggregate the native activity into energy through the core path, using
    # whatever calibrated estimators exist over a placeholder base (today: sram).
    chain = build_provider(verbose=args.verbose)
    run_energy = aggregate_native(
        emitted.description, emitted.activity_rows, chain.provider, tech,
        default_clock_mhz=DEFAULT_HARNESS_CLOCK_MHZ,
        window_labels=emitted.window_labels,
    )
    _print_run_energy(run_energy, chain, verbose=args.verbose,
                      window_provenance=emitted.window_provenance)

    run_root = Path(args.togsim_dir).resolve().parent if args.togsim_dir else None
    inputs = [(f"togsim: {args.togsim_dir}", None),
              (f"gem5: {args.gem5_dir}", None)]
    if args.config_yml:
        inputs.append((Path(args.config_yml).name, Path(args.config_yml)))
    _maybe_write_report(
        args, run=run_energy, description=emitted.description, tech=tech,
        chain=chain, rows=emitted.activity_rows, hierarchy=emitted.hierarchy,
        warnings=emitted.warnings, notes=emitted.notes,
        design_name=(run_root.name if run_root is not None else args.harness),
        activity_source=f"{args.harness} harness (simulator logs)",
        inputs=inputs,
        window_provenance=emitted.window_provenance,
    )
    return 0


def _maybe_write_report(args, *, run, description, tech, chain, rows,
                        hierarchy, warnings, design_name, activity_source,
                        vectorless=None, inputs=(), notes=(),
                        window_provenance=()) -> None:
    """Write report.html + report.json when ``--report DIR`` was given.

    Report generation is presentation: a failure here warns and leaves the
    (already printed) console results untouched, mirroring the --tree contract.
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
        )
        html_path, json_path = write_report(ctx, args.report_dir)
        print(f"[INFO] Wrote report:      {html_path}")
        print(f"[INFO] Wrote report data: {json_path}")
    except Exception as e:
        print(f"[WARNING] --report: report generation failed: {e}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()


def _print_window_energy(run, verbose: int = 0,
                         window_provenance=None) -> None:
    """Per-window (per-kernel) §6 energy: one line per window, the run total
    below being exactly their accumulation, then a component × window matrix
    of dynamic energy (idle, leakage-only components are omitted from the
    matrix — they are visible in the accumulated summary).

    ``window_provenance`` (harness runs): adds a ``kind`` column
    (mac/fused/non_mac) and, when non-MAC kernels are present, GEMM vs
    non-GEMM subtotal lines — the "how much energy is outside the systolic
    array" split a DSE comparison needs at a glance.

    TERMINOLOGY (user decision 2026-07-31, after a PyTorchSim-authors meeting
    asked "what is a window?"): ``window`` is the CORE's harness-neutral term —
    a time interval of the §3.3 activity trace (gem5 periodic dumps, Timeloop
    layers, the vectorless synthetic interval are all windows but NOT kernels).
    In the PyTorchSim harness one kernel == one window by construction, so
    END-USER text for those runs says "kernel" (the presence of
    ``window_provenance`` is exactly the marker of such a run); schema/code
    identifiers stay ``window``.
    """
    n = len(run.windows)
    kinds = {}
    if window_provenance:
        kinds = {p["window"]: p["kind"] for p in window_provenance}
    term = "kernel" if window_provenance else "window"
    kcol = 9 if kinds else 0
    print("\n" + "=" * 100)
    print(f"[INFO] Per-{term} energy ({n} {term}{'s' if n != 1 else ''})")
    print("-" * 100)
    khdr = f"{'kind':<{kcol}}" if kinds else ""
    print(f"{'#':<8}{'kernel':<15}{khdr}{'cycles':>10}{'dyn (pJ)':>16}"
          f"{'leak (pJ)':>16}{'total (pJ)':>16}{'avg power (mW)':>17}")
    for i, w in enumerate(run.windows):
        kcell = f"{kinds.get(i, '?'):<{kcol}}" if kinds else ""
        print(f"{i:<8}{w.kernel_hash:<15}{kcell}{w.exec_cycles:>10}"
              f"{w.dyn_energy_pJ:>16.4g}{w.leak_energy_pJ:>16.4g}"
              f"{w.total_energy_pJ:>16.4g}{w.avg_power_mW:>17.4g}")
    if kinds and any(k == "non_mac" for k in kinds.values()):
        mac_tot = sum(w.total_energy_pJ for i, w in enumerate(run.windows)
                      if kinds.get(i) != "non_mac")
        non_tot = sum(w.total_energy_pJ for i, w in enumerate(run.windows)
                      if kinds.get(i) == "non_mac")
        total = mac_tot + non_tot
        pct = (100.0 * non_tot / total) if total else 0.0
        n_non = sum(1 for k in kinds.values() if k == "non_mac")
        print("-" * 100)
        print(f"[INFO] GEMM kernels (mac/fused): {mac_tot:.4g} pJ "
              f"({n - n_non} window(s)); non-GEMM kernels: {non_tot:.4g} pJ "
              f"({n_non} window(s), {pct:.1f}% of total)")
    print("-" * 100)
    _print_window_component_matrix(run, term=term)


def _print_window_component_matrix(run, term: str = "window") -> None:
    """Per-kernel component energy: component rows × window columns (dynamic
    pJ), chunked into column groups so the table stays inside the console
    width. Kernel-level component energy was a user request (2026-07-21).
    ``term`` follows the window/kernel terminology rule (see
    ``_print_window_energy``)."""
    if not run.windows:
        return
    all_names = list(run.windows[0].components)
    active = [name for name in all_names
              if any(w.components[name].dyn_energy_pJ for w in run.windows)]
    if not active:
        return
    name_w, col_w = 28, 12
    per_chunk = max(1, (100 - name_w) // col_w)
    print(f"[INFO] Per-{term} component energy (dynamic, pJ)")
    print("-" * 100)
    for start in range(0, len(run.windows), per_chunk):
        chunk = run.windows[start:start + per_chunk]
        header = "".join(f"{w.kernel_hash[:11]:>{col_w}}" for w in chunk)
        print(f"{'component':<{name_w}}{header}")
        for name in active:
            cells = "".join(
                f"{w.components[name].dyn_energy_pJ:>{col_w}.4g}"
                if w.components[name].dyn_energy_pJ else f"{'-':>{col_w}}"
                for w in chunk)
            print(f"{name:<{name_w}}{cells}")
        if start + per_chunk < len(run.windows):
            print()
    idle = len(all_names) - len(active)
    if idle:
        print(f"({idle} component(s) with no dynamic activity omitted — "
              f"leakage in the summary below)")
    print("-" * 100)


def _print_run_energy(run, chain=None, extra_tag=None, verbose: int = 0,
                      window_provenance=None) -> None:
    """Print a compact §6 energy summary (per-component + run totals).

    Calibration is reported **per component**, since it arrives per primitive:
    today only `sram` has trained models, so a systolic run is all placeholder
    while a description with an SRAM buffer is partly real. Analytic-constant
    primitives (`d2dlink`, a literature pJ/bit) get their own `const` bucket —
    they are neither calibrated nor placeholder.
    """
    _print_window_energy(run, verbose=verbose,
                         window_provenance=window_provenance)

    calibrated_prims = tuple(getattr(chain, "calibrated_primitives", ()) or ())
    constant_prims = tuple(getattr(chain, "constant_primitives", ()) or ())

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
    hits = prims & set(calibrated_prims)
    consts = (prims - hits) & set(constant_prims)
    stubs = prims - hits - consts
    if prims and not stubs and not consts:
        tag = "calibrated"
    elif hits or consts:
        parts = []
        if hits:
            parts.append(f"calibrated: {', '.join(sorted(hits))}")
        if consts:
            parts.append(f"constant: {', '.join(sorted(consts))}")
        if stubs:
            parts.append(f"placeholder: {', '.join(sorted(stubs))}")
        tag = "PARTIAL — " + "; ".join(parts)
    else:
        tag = "FIRST-ORDER (uncalibrated placeholder)"

    print("\n" + "=" * 100)
    if extra_tag:
        tag = f"{extra_tag} — {tag}"
    print(f"[INFO] Energy summary — {tag}")
    print("-" * 100)
    print(f"{'component':<26}{'model':>7}{'instances':>11}"
          f"{'dyn (pJ)':>18}{'leak (pJ)':>18}{'area (um2)':>16}")
    for name, (prim, inst, dyn, leak, area) in per_comp.items():
        mark = ("cal" if prim in calibrated_prims
                else "const" if prim in constant_prims else "stub")
        print(f"{name:<26}{mark:>7}{inst:>11}{dyn:>18.4g}{leak:>18.4g}{area:>16.4g}")
    print("-" * 100)
    print(f"total energy = {run.total_energy_pJ:.4g} pJ "
          f"(dyn {run.dyn_energy_pJ:.4g} + leak {run.leak_energy_pJ:.4g}); "
          f"avg power = {run.avg_power_mW:.4g} mW; exec = {run.exec_time_s:.4g} s")
    if calibrated_prims:
        print(f"calibrated primitives available: {', '.join(calibrated_prims)}")
    for note in getattr(chain, "notes", ()) or ():
        print(f"[WARNING] {note}")
    print("=" * 100)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for NPUWattch CLI."""
    msg._print_intro()

    argv_list: List[str] = list(sys.argv[1:] if argv is None else argv)

    try:
        args = parse_args(argv_list)
    except SystemExit as e:
        return 0 if (e.code == 0) else 1

    # Initialize estimator host for training mode
    if args.train:
        host = EstimatorHost(verbose=args.verbose)
        host.scan_estimators()
        return _run_training(args, host)

    # Mode dispatch
    if args.flatten:
        return _run_flattener(args)

    if args.harness:
        return _run_harness(args)

    return _run_estimator(args)


if __name__ == "__main__":
    raise SystemExit(main())