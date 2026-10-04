"""PyTorchSim ingest: one PyTorchSim run -> one NPUWattch description and its
activity.

:func:`ingest` is the entry point that the harness registry calls.
:func:`synthesize_run` does the work in these steps:

1. Read the run into kernel windows (``activity.read_run``).
2. Select the representative MAC configuration of the run.
3. Emit one component for each physical instance of each compound element,
   and write the DRAM energy constants (``dram.set_constants``).
4. Bind the activity of each window to the components
   (``activity.bind_window``, ``instances.expand_bounds``).
5. Build the activity rows, the coverage messages, the hierarchy view, and
   the provenance record of each window.

The emitter functions that all harnesses use (``build_description``,
``build_activity``) are in ``npuwattch.arch_synth``.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from npuwattch.arch_synth import (
    EmittedArch,
    _coverage_messages,
    _emit_per_instance,
    build_activity,
    build_description,
)
from ..compounds import Compound, CompoundBundleError, resolve_compound
from .activity import KernelWindow, bind_window, read_run
from ..run_inputs import (
    attach_user_components,
    find_definition,
    load_user_library,
)
from .definitions import VOCABULARY, load_definitions
from .dram import select_table, set_constants
from .hierarchy import build_hierarchy
from .instances import expand_bounds
from .mac_config import MacConfig, fallback_fp32_mac_config
from .run_config import config_conflicts, load_config_yml

__all__ = ["ingest", "synthesize_run"]


def ingest(inputs: Mapping[str, Path], tech: Any, **opts: Any) -> EmittedArch:
    """Harness entry point: the named inputs of one run -> ``EmittedArch``.

    ``inputs`` contains ``togsim`` and ``gem5`` (the two result directories of
    PyTorchSim). It can also contain:

    * ``config``: the ``config.yml`` of the run. The log header has priority.
      The file supplies keys that a damaged header does not have.
    * ``booksim``: the ``booksim2_config/`` directory. An ``anynet`` NoC
      topology needs its ``.net`` file from this directory.
    * ``energy_table``: the DRAM energy table of the run.
    * ``compound_components``, ``projection``, ``user_components``: the
      definition files of the design. The default of each is the file with
      the fixed name in the run directory, which is the directory that
      contains ``togsim_results/`` (``npuwattch_harness.run_inputs``).
    """
    # These options are for the console. `synthesize_run` does not use them.
    opts.pop("verbose", None)
    opts.pop("node_explicit", None)
    config = inputs.get("config")
    booksim = inputs.get("booksim")
    energy_table = inputs.get("energy_table")
    run_dir = Path(inputs["togsim"]).resolve().parent
    library_path = find_definition(inputs, "user_components", run_dir)
    library = load_user_library(library_path)
    emitted = synthesize_run(
        Path(inputs["togsim"]), Path(inputs["gem5"]), tech,
        bundle=load_definitions(run_dir, inputs),
        base_config=load_config_yml(config) if config else None,
        booksim_dir=Path(booksim) if booksim else None,
        energy_table=select_table(energy_table),
        **opts)
    # The compounds of a PyTorchSim design use no user component at this
    # time. Thus each library component gives the note "parsed, but not used".
    attach_user_components(emitted.description, library, library_path,
                           emitted.notes)
    return emitted


# ---------------------------------------------------------------------------
# Checks of the run configuration
# ---------------------------------------------------------------------------

# The core types of PyTorchSim are in ARCHITECTURE_SPEC §6
# (`CoreType { WS_MESH, STONNE }`). This harness models only `ws_mesh`, the
# dense weight-stationary systolic array. The STONNE `SparseCore` is not in
# the scope of v1.0. The `heterogeneous` type mixes the two types in one run.
_SUPPORTED_CORE_TYPES = ("ws_mesh",)


def _unsupported_core_types(config: Mapping[str, Any]) -> List[str]:
    """Return the core types of a run configuration that this harness does
    not model.

    A run with only ws_mesh cores does not have the ``core_type`` key, because
    ws_mesh is the default. Thus a missing key means a systolic core. A key
    that starts with ``stonne_`` (for example, ``stonne_config_path``) also
    identifies a STONNE or heterogeneous configuration.

    This check follows ARCHITECTURE_SPEC §6. It was not tested with a STONNE
    run.
    """
    found: List[str] = []
    declared = config.get("core_type")
    if declared is not None:
        types = declared if isinstance(declared, (list, tuple)) else [declared]
        for t in types:
            if str(t) not in _SUPPORTED_CORE_TYPES and str(t) not in found:
                found.append(str(t))
    if any(str(k).startswith("stonne_") for k in config) and "stonne" not in found:
        found.append("stonne")
    return found


def _l2d_enabled(config: Mapping[str, Any]) -> bool:
    """Return True if the run configuration enables the optional L2 data
    cache.

    ``l2d_type: datacache`` enables the cache (ARCHITECTURE_SPEC §3).
    ``l2d_type: none`` disables it.

    If there is no ``l2d_type`` key, the function looks for other ``l2d_*``
    keys. If it finds one, it returns True. An unnecessary warning is better
    than a large on-chip SRAM that the results exclude without a message.
    """
    l2d_type = config.get("l2d_type")
    if l2d_type is not None:
        return str(l2d_type).strip().lower() not in ("", "none")
    return any(str(k).startswith("l2d_") for k in config)


def _pick_clock(
    explicit: Optional[float],
    tech_clock: Optional[float],
    log_clock: Optional[float],
    default: Optional[float],
) -> Optional[float]:
    """Select the clock frequency in MHz.

    The sources have this priority:

    1. ``explicit``: the value that the caller gives.
    2. ``tech_clock``: the value of the ``TechContext``.
    3. ``log_clock``: ``core_freq_mhz`` from the log. A PyTorchSim log always
       has this key.
    4. ``default``: for example, the 200 MHz of the CLI.

    Return ``None`` only if all sources are missing or zero.
    """
    for cand in (explicit, tech_clock, log_clock, default):
        if cand:
            return float(cand)
    return None


# ---------------------------------------------------------------------------
# Steps of synthesize_run
# ---------------------------------------------------------------------------

def _representative_mac(
    windows: Sequence[KernelWindow], compound: Compound,
    warnings: List[str], notes: List[str],
) -> Tuple[MacConfig, Dict[str, Any]]:
    """Select the MAC configuration that describes the physical array.

    The physical array is the same for all kernels of a run. Thus the first
    MAC kernel gives the configuration. A kernel without a MAC (softmax,
    layernorm, elementwise) uses the datatype of that kernel. If the run has
    no MAC kernel, the function assumes fp32 and gives a warning.

    Return the configuration and the resolved elements of ``compound``.
    """
    lanes0 = windows[0].lanes
    mac_windows = [w for w in windows if w.mac_config is not None]
    if mac_windows:
        rep = mac_windows[0]
        rep_mac = rep.mac_config
        non_mac = [w for w in windows if w.mac_config is None]
        if non_mac:
            notes.append(
                f"{len(non_mac)} non-MAC kernel window(s) charged on the "
                f"non-systolic compounds only (no systolic activity); the "
                f"vfu/spads datapath dtype ({rep_mac.operand_dtype.canonical}) "
                f"is borrowed from MAC kernel {rep.kernel_hash} — the physical "
                f"array is uniform within a run"
            )
    else:
        rep_mac = fallback_fp32_mac_config(lanes0)
        warnings.append(
            "run has no MAC kernel: non-MAC windows are charged at an ASSUMED "
            "fp32 (e8m23) datapath for the templated vfu/spads elements — no "
            "kernel in this run evidences the real dtype"
        )
    resolved0 = resolve_compound(compound, rep_mac)
    for w in windows:
        if w.lanes != lanes0:
            raise ValueError(
                f"inconsistent lanes across kernels ({lanes0} vs {w.lanes}); "
                "the physical array must be uniform within a run"
            )
    # A later kernel can use a different configuration (for example, a run
    # with fp and int kernels). The description uses the first kernel. The
    # activity of each kernel stays correct.
    for w in mac_windows[1:]:
        rw = resolve_compound(compound, w.mac_config)
        if set(rw) != set(resolved0):
            warnings.append(f"kernel {w.kernel_hash} has a different element set; using {mac_windows[0].kernel_hash}")
        elif any(rw[e].config != resolved0[e].config for e in resolved0):
            warnings.append(
                f"kernel {w.kernel_hash} reconfigures the array "
                f"(config differs from {mac_windows[0].kernel_hash}); description uses the first"
            )
    return rep_mac, resolved0


def _emit_components(
    bundle: Any, projection: Any, compound: Compound,
    resolved0: Mapping[str, Any], rep_mac: MacConfig,
    extra_symbols: Mapping[str, int], *,
    num_cores: int, arrays_per_core: int, warnings: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], List[Compound],
           Dict[str, Dict[str, Any]]]:
    """Emit the components of the MAC compound and of all other compounds.

    The function emits one component for each physical instance
    (``core0.array0.pe``, ``core0.vmem``, ...).

    Return ``(components, maps, aux_compounds, aux_resolved)``:

    * ``maps`` contains the element tables that ``build_activity`` and
      ``expand_bounds`` use: ``class``, ``name``, ``word_bits``, ``ports``,
      and ``per``.
    * ``aux_compounds`` are the compounds, other than the MAC compound, that
      the projection drives (for example, ``spads``).
    * ``aux_resolved`` contains the resolved elements of each of them.
    """
    (components, cls, names, word_bits, ports, per) = _emit_per_instance(
        resolved0, num_cores=num_cores, arrays_per_core=arrays_per_core,
        warnings=warnings)

    aux_compounds: List[Compound] = []
    aux_resolved: Dict[str, Dict[str, Any]] = {}
    for cname in projection.compounds:
        if cname == compound.name or cname not in bundle.compounds:
            continue
        aux = bundle.compound(cname)
        aux_compounds.append(aux)
        resolved_aux: Dict[str, Any] = {}
        aux_resolved[cname] = resolved_aux
        # Resolve one element at a time. If the configuration of this run
        # does not have a symbol that an element uses, skip only that element.
        for ename, el in aux.elements.items():
            try:
                one = resolve_compound(
                    Compound(name=aux.name,
                             select_primitive_by=aux.select_primitive_by,
                             elements={ename: el},
                             default_mode=aux.default_mode),
                    rep_mac, extra_symbols,
                )
                resolved_aux[ename] = one[ename]
            except CompoundBundleError as e:
                warnings.append(f"{cname}.{ename}: not emitted — {e}")
        aux_comps, acls, anames, wb, pb, aper = _emit_per_instance(
            resolved_aux, num_cores=num_cores, arrays_per_core=arrays_per_core,
            warnings=warnings)
        components.extend(aux_comps)
        cls.update(acls)
        names.update(anames)
        word_bits.update(wb)
        ports.update(pb)
        per.update(aper)

    maps = {"class": cls, "name": names, "word_bits": word_bits,
            "ports": ports, "per": per}
    return components, maps, aux_compounds, aux_resolved


def _window_provenance(windows: Sequence[KernelWindow],
                       rep_mac: MacConfig) -> List[Dict[str, Any]]:
    """Build the provenance record of each window from the parsed data.

    ``kind`` is one of these values:

    * ``mac``: the window has its own MAC configuration.
    * ``fused``: a MAC window that also has SFU or vector activity.
    * ``non_mac``: the window has no MAC configuration. Its datatype comes
      from the representative MAC configuration.
    """
    mac_windows = [w for w in windows if w.mac_config is not None]
    provenance: List[Dict[str, Any]] = []
    for i, w in enumerate(windows):
        s = w.stats or {}
        sys_c = int(s.get("systolic_active_cycles", 0) or 0)
        vec_c = int(s.get("vector_active_cycles", 0) or 0)
        sfu = int(sum(s.get(k, 0) or 0
                      for k in VOCABULARY.stats["sfu_instructions"]))
        if w.mac_config is None:
            kind = "non_mac"
            dtype_source = (f"borrowed:{mac_windows[0].kernel_hash}"
                            if mac_windows else "fallback_fp32")
            dtype = rep_mac.operand_dtype.canonical
        else:
            kind = "fused" if sys_c and (vec_c or sfu) else "mac"
            dtype_source = "own"
            dtype = w.mac_config.operand_dtype.canonical
        provenance.append({
            "window": i,
            "kernel": w.kernel_hash,
            "kind": kind,
            "dtype": dtype,
            "dtype_source": dtype_source,
            "systolic_active_cycles": sys_c,
            "vector_active_cycles": vec_c,
            "sfu_ops": sfu,
            "dram_requests": int(s.get("dram_requests", 0) or 0),
            "exec_cycles": w.exec_cycles,
        })
    return provenance


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def synthesize_run(
    togsim_dir: Path,
    gem5_dir: Path,
    tech: Any,
    *,
    compound_name: str = "systolic_mac",
    bundle: Any = None,
    num_arrays: Optional[int] = None,
    clock_mhz: Optional[float] = None,
    default_clock_mhz: Optional[float] = None,
    prefix: str = "systolic",
    base_config: Optional[Mapping[str, Any]] = None,
    booksim_dir: Optional[Path] = None,
    energy_table: Any = None,
) -> EmittedArch:
    """Read one PyTorchSim run and emit its description and activity.

    ``togsim_dir`` contains the TOGSim logs. ``gem5_dir`` contains the gem5
    and codegen outputs of each kernel. PyTorchSim writes them to two
    different directories.

    Optional inputs:

    * ``base_config``: the ``config.yml`` of the run. The header of each log
      has priority. The file supplies missing keys. A key with two different
      values gives a warning.
    * ``booksim_dir``: the ``booksim2_config/`` directory. An ``anynet`` NoC
      needs its ``.net`` file. Without the file, the NoC is not modeled and
      the run gives a warning.
    * ``energy_table``: the ``EnergyTable`` of ``--energy-table``. If it is
      ``None``, the ``hbm`` components get the constants of the default
      table.

    Errors and messages:

    * An incorrect compound or projection raises an error.
    * Activity that no projection action uses gives a warning. If the
      projection declares the exclusion (``waivers``, ``out_of_scope``), the
      message is a note.
    """
    if bundle is None:
        # The default is the definition files in the run directory.
        bundle = load_definitions(Path(togsim_dir).resolve().parent)
    compound = bundle.compound(compound_name)
    projection = bundle.projection("pytorchsim")

    # Step 1: read the run. A window without a MAC kernel stays in the list,
    # because the compounds other than the systolic array use its activity.
    windows = read_run(togsim_dir, gem5_dir, base_config=base_config,
                       booksim_dir=booksim_dir,
                       expected_dram_table=(energy_table.name
                                            if energy_table else None))

    # An integration that is planned but not built gives a warning.
    warnings: List[str] = [
        f"pending third-party integration (not implemented — this energy is "
        f"NOT included): {t}"
        for t in getattr(projection, "third_party_pending", ())
    ]
    # The declared scope limits are the first notes.
    notes: List[str] = list(projection.out_of_scope)
    for w in windows:
        warnings.extend(
            x if x.startswith(w.kernel_hash) else f"{w.kernel_hash}: {x}"
            for x in w.warnings
        )

    # Step 2: the representative MAC configuration.
    rep_mac, resolved0 = _representative_mac(windows, compound, warnings, notes)

    cfg0 = windows[0].config or {}
    if base_config:
        warnings.extend(config_conflicts(base_config, cfg0))
    for core_type in _unsupported_core_types(cfg0):
        warnings.append(
            f"unsupported core_type {core_type!r}: this harness models only the "
            "'ws_mesh' (systolic) core. STONNE/heterogeneous cores (ARCHITECTURE_SPEC "
            "§6) are out of v1.0 scope — their activity and energy are NOT included "
            "in these results"
        )
    if _l2d_enabled(cfg0):
        warnings.append(
            f"config enables an L2 data cache (l2d_type="
            f"{cfg0.get('l2d_type')!r}): not modeled — outside the sanctioned "
            "energy scope (vector unit + VMEM + systolic array + on-chip NoC), "
            "and it is a large on-chip SRAM, so its energy is NOT included in "
            "these results"
        )
    if num_arrays is None:
        num_arrays = int(cfg0.get("num_cores", 1)) * int(cfg0.get("num_systolic_array_per_core", 1))
    clk = _pick_clock(
        clock_mhz, getattr(tech, "clock_mhz", None), cfg0.get("core_freq_mhz"), default_clock_mhz
    )
    if not clk:
        raise ValueError(
            "no clock frequency; pass clock_mhz/default_clock_mhz, set TechContext.clock_mhz, "
            "or ensure the log has core_freq_mhz"
        )

    num_cores = int(cfg0.get("num_cores", 1))
    if num_arrays % max(1, num_cores):
        warnings.append(
            f"num_arrays={num_arrays} is not divisible by num_cores={num_cores}; "
            f"the per-instance split treats the run as a single core")
        num_cores = 1
    arrays_per_core = max(1, num_arrays // max(1, num_cores))
    # The compounds can use each integer key of the run configuration as a
    # symbol in an expression (for example, the `capacity_kbit` of the spads).
    extra_symbols = {k: v for k, v in cfg0.items()
                     if isinstance(v, int) and not isinstance(v, bool)}

    # Step 3: the description. `build_description` gives the header.
    description = build_description(
        {}, tech, num_arrays=num_arrays, clock_mhz=float(clk), prefix=prefix,
        warnings=warnings, num_cores=num_cores,
    )
    components, maps, aux_compounds, aux_resolved = _emit_components(
        bundle, projection, compound, resolved0, rep_mac, extra_symbols,
        num_cores=num_cores, arrays_per_core=arrays_per_core,
        warnings=warnings)
    description["npuwattch"]["components"].extend(components)
    set_constants(description, energy_table, notes, warnings)

    # Step 4: bind the activity. A window without a MAC kernel uses the
    # representative MAC configuration. `build_activity` reads the operand
    # datatype from it to convert bytes and vectors to memory words.
    eff_windows = [w if w.mac_config is not None
                   else dc_replace(w, mac_config=rep_mac) for w in windows]
    bound_per_window = []
    seen_notes: set = set()
    for w in eff_windows:
        skipped: List[str] = []
        bounds = sum((bind_window(w, projection, c, bundle.primitive_modes,
                                  skipped=skipped)
                      for c in aux_compounds),
                     bind_window(w, projection, compound,
                                 bundle.primitive_modes, skipped=skipped))
        bounds, split_notes = expand_bounds(
            w, bounds, maps["per"],
            num_cores=num_cores, arrays_per_core=arrays_per_core)
        bound_per_window.append(bounds)
        for msg in skipped + split_notes:   # report each message one time
            if msg not in seen_notes:
                seen_notes.add(msg)
                warnings.append(msg)

    # Step 5: activity rows, coverage messages, hierarchy view, provenance.
    rows, total_cycles, act_warn = build_activity(
        eff_windows, bound_per_window, maps["class"], prefix=prefix,
        exec_cycles=[w.exec_cycles for w in windows],
        name_by_element=maps["name"],
        word_bits_by_element=maps["word_bits"],
        ports_by_element=maps["ports"],
    )
    warnings.extend(act_warn)
    cov_warnings, cov_notes = _coverage_messages(windows, bound_per_window, projection)
    warnings.extend(cov_warnings)
    notes.extend(cov_notes)

    try:
        hierarchy = build_hierarchy(
            description, resolved0, aux_resolved,
            num_cores=num_cores, arrays_per_core=arrays_per_core,
        )
    except Exception as e:           # the view must not stop the run
        warnings.append(f"hierarchy view unavailable: {e}")
        hierarchy = None

    return EmittedArch(
        description=description,
        activity_rows=rows,
        total_cycles=total_cycles,
        warnings=warnings,
        notes=notes,
        hierarchy=hierarchy,
        window_labels=[w.kernel_hash for w in windows],
        window_provenance=_window_provenance(windows, rep_mac),
    )
