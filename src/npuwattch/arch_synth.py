"""Arch-synthesis emitter — a harness run → a draft NPUWattch description.

**This is NPUWattch core, not a harness.** A harness (per simulator) owns two
things, authored by whoever introduces that simulator's log format: the *log
readers* (e.g. ``harness/pytorchsim/{mac_config,gem5_stats,togsim_log,activity}``)
and the *definition bundle* (``compounds/*.yaml`` + ``projections/<tool>.yaml``).
The emitter is the core authority that *interprets* those definitions against a
run and produces the two files the mainline reads. It therefore also acts as the
**gate**: a malformed/incomplete compound or projection surfaces here.

Gate behavior:
  * Structural/contract errors (unknown compound/element, uncharacterized
    stim_mode, unresolvable placeholder, unsupported primitive×mode) **hard-error**
    — they propagate out of ``synthesize_run`` from bundle validation and
    ``resolve_compound``/``bind_window``.
  * *Incomplete interpretation* — a window carries real activity (a nonzero stat)
    that no projection action consumes — cannot be told apart from an author
    intentionally ignoring a stat (coarser fidelity), so it is **not** fatal: every
    such stat is listed in ``EmittedArch.warnings``.

The emitter emits the two files the mainline core already reads:
  * a **native architecture description** (manual §3.1, ``npuwattch:`` root) —
    ``build_description`` / ``to_flattened`` (the latter lowers it to the flattened
    ``architecture: {local: [...]}`` form that ``npuwattch_db.build_database``
    consumes, matching the manual's "converted internally" note);
  * a **windowed activity table** (manual §3.3) — one row per
    (kernel-window × element × stim_mode). The base ``component,event,count``
    columns are exactly §3.3; we add one **optional ``mode`` column** carrying the
    stim_mode, because §6 dynamic energy is keyed by stim_mode (hold_b vs random
    differ a lot) and the coarse op/read/write event would lose it.

The emitter is **model-independent**: it emits *structure* (classes, counts,
attributes, event cycle-counts), never energy numbers.

``synthesize_run`` is the pytorchsim-specific one-call entry (mirrors
``energy.aggregate.analyze_run``); ``build_description`` / ``build_activity`` /
``to_flattened`` are tool-agnostic and operate on any harness's resolved-compound
+ bound-action output.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from npuwattch.naming import LEGACY_ALIASES, validate_attributes

__all__ = [
    "EmittedArch",
    "build_description",
    "build_activity",
    "to_flattened",
    "write_arch",
    "synthesize_run",
    "ACTIVITY_COLUMNS",
]

# Physical-component class for each compound primitive. The value is a class the
# mainline class-mapper resolves to a cluster/estimator (``register_file`` →
# regfile, ``intmac`` → intmac); ``fpmac``/``mxfpmac`` name their own clusters and
# get estimators in workstream D (flagged as uncalibrated until then).
PRIMITIVE_TO_CLASS: Dict[str, str] = {
    "intmac": "intmac",
    "fpmac": "fpmac",
    "mxfpmac": "mxfpmac",
    "regfile": "register_file",
    "arithmetic": "adder",
    "crossbar": "crossbar",
}

# stim_mode → §3.3 event, per component family.
_MEM_CLASSES = ("register_file", "regfile", "sram", "fifo", "hbm")
_LINK_CLASSES = ("crossbar", "noc", "wire", "d2dlink")
_MEM_MODE_EVENT = {"read": "read", "write": "write", "idle": "idle", "random": "write"}

# unit "flits" on a crossbar element: N flits at a partial-activity stim mode
# occupy N / (valid_fraction × ports) whole-crossbar cycles, keeping total
# dynamic energy proportional to the flit count (§3.9). Modes not listed are
# full-activity (fraction 1.0).
_XBAR_VALID_FRACTION = {"valid25": 0.25}

# Window stats that are timing/leakage inputs, not action activity to be charged
# by a projection — excluded from the "uninterpreted activity" coverage warning.
_META_STATS = frozenset({"total_exec_cycles", "numCycles"})

# SFU op-count stats (gem5 committedInstType classes) — summed for the
# per-window provenance record's "sfu_ops" headline number.
_SFU_STAT_KEYS = ("CustomVexp", "CustomVexp2", "CustomVerf", "CustomVtanh",
                  "CustomVsin", "CustomVcos")

# TERMINOLOGY — window vs kernel: "window" is the CORE's harness-neutral
# unit — a time interval [cycle_start, cycle_end] of the
# §3.3 activity trace. It is NOT a synonym for "kernel": gem5 periodic dumps,
# Timeloop layers, and the vectorless synthetic interval are windows without
# being kernels. The PyTorchSim harness maps one compiled kernel to one window
# BY CONSTRUCTION, so user-facing output for those runs (console, report) says
# "kernel" — the schema column below and code identifiers stay "window".
ACTIVITY_COLUMNS: Tuple[str, ...] = (
    "window", "cycle_start", "cycle_end", "component", "event", "mode", "count",
)


# ---------------------------------------------------------------------------
# result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EmittedArch:
    """The two emitted artifacts (as in-memory structures) plus provenance."""

    description: Dict[str, Any]                 # {"npuwattch": {...}}  (manual §3.1)
    activity_rows: List[Dict[str, Any]]         # manual §3.3 windowed rows (+mode)
    activity_columns: Tuple[str, ...] = ACTIVITY_COLUMNS
    total_cycles: int = 0
    warnings: List[str] = field(default_factory=list)
    #: INFO-tier messages: exclusions the projection DECLARES (its `waivers` /
    #: `out_of_scope` blocks). Deliberate and documented — kept apart from
    #: `warnings`, which then always means "possibly a gap" (uninterpreted
    #: activity, unmodeled hardware, degraded inference).
    notes: List[str] = field(default_factory=list)
    #: Instance-hierarchy view (report.tree.ArchTreeNode) — the factorized
    #: structure (cores × arrays × PEs, per-core spads, NoC) the flat
    #: description collapses into counts. Presentation only (CLI --tree, R1
    #: report); the §3.1 description stays flat.
    hierarchy: Optional[Any] = None
    #: Where ``hierarchy`` came from, for the --tree caption (e.g. "declared in
    #: the Accelergy description"). ``None`` → the console's generic
    #: "reconstructed from the run's model".
    tree_source: Optional[str] = None
    #: Kernel hash per activity window, in window order — provenance for the
    #: per-window energy display (the §3.3 CSV itself carries only indices).
    window_labels: List[str] = field(default_factory=list)
    #: Per-window provenance record (window order), built from the PARSED data:
    #: {"window", "kernel", "kind": mac|fused|non_mac, "dtype", "dtype_source":
    #: own|borrowed:<hash>|fallback_fp32, "systolic_active_cycles",
    #: "vector_active_cycles", "sfu_ops", "dram_requests", "exec_cycles"}.
    #: Console prints these at -v>=2; report.json carries them always.
    window_provenance: List[Dict[str, Any]] = field(default_factory=list)
    #: Set when the harness could not derive real activity and synthesized it
    #: instead — the fraction of random switching assumed (the Timeloop harness
    #: has no stats reader yet). The CLI/report label such a run VECTORLESS;
    #: ``None`` means the activity came from the simulator's own counters.
    vectorless_activity: Optional[float] = None


# ---------------------------------------------------------------------------
# attribute normalization (resolved-element config → §3.1 attributes)
# ---------------------------------------------------------------------------

def _mac_attributes(primitive: str, config: Mapping[str, Any]) -> Dict[str, Any]:
    cfg = dict(config) if isinstance(config, Mapping) else {}
    if primitive == "fpmac":
        exp, mant = cfg.get("exp_bits"), cfg.get("mantissa_bits")
        width = (1 + exp + mant) if isinstance(exp, int) and isinstance(mant, int) else None
        return {
            "number_format": "fp",
            "data_width": width,
            "exponent_bits": exp,
            "mantissa_bits": mant,
            "pipeline_stages": cfg.get("pipeline_stages"),
        }
    if primitive == "intmac":
        a = cfg.get("a_width")
        b = cfg.get("b_width", a)
        acc = cfg.get("acc_width")
        return {
            "number_format": "int",
            "data_width_a": a,
            "data_width_b": b,
            "data_width_out": cfg.get("out_width", acc),
            "data_width_acc": acc,
            "pipeline_stages": cfg.get("pipeline_stages"),
        }
    if primitive == "mxfpmac":
        return {"number_format": "mx", **_rename_to_canonical(cfg)}
    return {"number_format": primitive, **_rename_to_canonical(cfg)}


def _regfile_attributes(config: Mapping[str, Any]) -> Dict[str, Any]:
    cfg = dict(config) if isinstance(config, Mapping) else {}
    return {
        "data_width": cfg.get("width"),
        "mem_depth_per_bank": cfg.get("depth"),
        "mem_banks": cfg.get("n_banks", 1),
        "mem_r_ports": cfg.get("num_read_ports", 1),
        "mem_w_ports": cfg.get("num_write_ports", 1),
    }


def _rename_to_canonical(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    """Map a definition-bundle element config onto canonical attribute names.

    Bundle configs are authored in the RTL generator's vocabulary (``a_width``,
    ``num_inputs``, ``block_elems``…). The emitter is the boundary where that
    becomes NPUWattch's — downstream, only canonical names exist.
    """
    return {LEGACY_ALIASES.get(k, k): v for k, v in cfg.items()}


def _element_attributes(primitive: str, config: Mapping[str, Any]) -> Dict[str, Any]:
    if primitive in ("intmac", "fpmac", "mxfpmac"):
        attrs = _mac_attributes(primitive, config)
    elif primitive == "regfile":
        attrs = _regfile_attributes(config)
    else:
        attrs = _rename_to_canonical(config if isinstance(config, Mapping) else {})
    return {k: v for k, v in attrs.items() if v is not None}


def _components_for(
    resolved: Mapping[str, Any],
    *,
    num_arrays: int,
    num_cores: int,
    prefix: str,
    warnings: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, int]]:
    """Resolved elements → §3.1 components.

    Two element flavors:

    * ordinary primitives — one component, count × the element's ``per``
      multiplier (array / core / chip). A resolved count of 0 means the
      structure does not exist in this run (e.g. ``icnt_d2d`` on a
      single-chip fly network) and is skipped without a warning;
    * **capacity-specified sram** (config carries ``capacity_kbit`` or
      ``capacity_bit``) — expanded through the SRAM estimator's macro templates
      (``resolve_capacity``, §3.8 bank hierarchy) into a primary component
      (which carries the activity) and an optional leakage/area-only ``.tail``
      part.

    Returns ``(components, word_bits_by_element, ports_by_element)`` — the word
    width of each capacity element's primary part (bytes/vectors/flits unit
    conversion) and the port count of each crossbar element (flits → cycles).
    """
    multipliers = {"array": max(1, num_arrays), "core": max(1, num_cores), "chip": 1}
    components: List[Dict[str, Any]] = []
    word_bits: Dict[str, int] = {}
    ports: Dict[str, int] = {}
    for name, rel in resolved.items():
        instances = int(rel.count) * multipliers.get(rel.per, 1)
        if instances <= 0:
            continue
        cfg = rel.config if isinstance(rel.config, Mapping) else {}
        cap_keys = {"capacity_kbit", "capacity_bit"} & set(cfg)
        if rel.primitive == "sram" and cap_keys:
            if len(cap_keys) > 1:
                raise ValueError(
                    f"{name}: give capacity_kbit OR capacity_bit, not both"
                )
            capacity_bits = (int(cfg["capacity_bit"]) if "capacity_bit" in cfg
                             else int(cfg["capacity_kbit"]) * 1024)
            resolve_capacity = _sram_resolve_capacity()
            if resolve_capacity is None:
                if warnings is not None:
                    warnings.append(
                        f"{name}: SRAM estimator unavailable (estimators.sram not "
                        f"importable); capacity-specified element not emitted"
                    )
                continue
            parts, part_warns = resolve_capacity(capacity_bits)
            if warnings is not None:
                warnings.extend(f"{name}: {w}" for w in part_warns)
                if len(parts) > 1:
                    warnings.append(
                        f"{name}: traffic charged to the primary part; "
                        f"'{name}.tail' carries leakage/area only"
                    )
            for j, part in enumerate(parts):
                pname = name if j == 0 else f"{name}.tail"
                components.append(
                    _component(pname, "sram", part, instances, prefix, warnings)
                )
            word_bits[name] = int(parts[0]["data_width"])
        else:
            comp = _component(name, rel.primitive, rel.config, instances, prefix,
                              warnings)
            components.append(comp)
            n_in = comp["attributes"].get("net_inputs")
            if rel.primitive == "crossbar" and isinstance(n_in, int):
                ports[name] = n_in
    return components, word_bits, ports


def _emit_per_instance(
    relmap: Mapping[str, Any],
    *,
    num_cores: int,
    arrays_per_core: int,
    warnings: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, str],
           Dict[str, int], Dict[str, int], Dict[str, str]]:
    """Resolved elements → one §3.1 component per physical instance.

    Instead of one component whose ``count`` lumps every core/array together,
    each ``per: array`` element is emitted once per (core, array) as
    ``core{c}.array{a}.{element}`` and each ``per: core`` element once per core
    as ``core{c}.{element}``, both with the element's own per-instance count
    — reporting at the finest grain the source supports. ``per: chip``
    elements keep their plain name. Emission notes (capacity
    expansion, attribute gates) are recorded for the first instance only — the
    others are structurally identical.

    Returns ``(components, class_by_element, name_by_element,
    word_bits_by_element, ports_by_element, per_by_element)`` where the first
    five are keyed by the instance-qualified element name (what the expanded
    bound actions reference) and ``per_by_element`` by the plain element name
    (what pre-expansion bound actions reference).
    """
    by_domain: Dict[str, Dict[str, Any]] = {"array": {}, "core": {}, "chip": {}}
    for ename, rel in relmap.items():
        by_domain.get(rel.per, by_domain["chip"])[ename] = rel

    components: List[Dict[str, Any]] = []
    cls: Dict[str, str] = {}
    names: Dict[str, str] = {}
    word_bits: Dict[str, int] = {}
    ports: Dict[str, int] = {}

    def emit(elems: Dict[str, Any], iprefix: str, first: bool) -> None:
        comps, wb, pb = _components_for(
            elems, num_arrays=1, num_cores=1, prefix=iprefix,
            warnings=warnings if first else None,
        )
        components.extend(comps)
        for ename, rel in elems.items():
            q = f"{iprefix}.{ename}" if iprefix else ename
            cls[q] = PRIMITIVE_TO_CLASS.get(rel.primitive, rel.primitive)
            names[q] = q
        word_bits.update({(f"{iprefix}.{k}" if iprefix else k): v
                          for k, v in wb.items()})
        ports.update({(f"{iprefix}.{k}" if iprefix else k): v
                      for k, v in pb.items()})

    if by_domain["array"]:
        for c in range(max(1, num_cores)):
            for a in range(max(1, arrays_per_core)):
                emit(by_domain["array"], f"core{c}.array{a}", c == 0 and a == 0)
    if by_domain["core"]:
        for c in range(max(1, num_cores)):
            emit(by_domain["core"], f"core{c}", c == 0)
    if by_domain["chip"]:
        emit(by_domain["chip"], "", True)

    per_by_element = {ename: rel.per for ename, rel in relmap.items()}
    return components, cls, names, word_bits, ports, per_by_element


def _component(name: str, primitive: str, config: Mapping[str, Any],
               count: int, prefix: str,
               warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    full_name = f"{prefix}.{name}" if prefix else name
    attrs = _element_attributes(primitive, config)
    # Gate: what the emitter writes must already speak the estimators' vocabulary.
    # A bundle that resolves to a non-canonical attribute is a *definition* bug,
    # so this raises here rather than defaulting silently at estimate time.
    notes = validate_attributes(primitive, attrs, component=full_name)
    if warnings is not None:
        warnings.extend(notes)
    return {
        "name": full_name,
        "class": PRIMITIVE_TO_CLASS.get(primitive, primitive),
        "count": int(count),
        "attributes": attrs,
    }


# ---------------------------------------------------------------------------
# description (manual §3.1, native npuwattch:)
# ---------------------------------------------------------------------------

def build_description(
    resolved: Mapping[str, Any],
    tech: Any,
    *,
    num_arrays: int,
    clock_mhz: float,
    prefix: str = "systolic",
    version: str = "1.0",
    warnings: Optional[List[str]] = None,
    num_cores: int = 1,
) -> Dict[str, Any]:
    """Build the native ``npuwattch:`` description dict from a resolved compound.

    ``resolved`` is ``resolve_compound(...)`` output (element → ResolvedElement).
    Each element becomes one physical component; the instance multiplier follows
    the element's ``per`` domain (array / core / chip).
    """
    components, _, _ = _components_for(
        resolved, num_arrays=num_arrays, num_cores=num_cores,
        prefix=prefix, warnings=warnings,
    )
    return {
        "npuwattch": {
            "version": version,
            "technology": {
                "node": tech.node,
                "transistor": tech.transistor,
                "corner": tech.corner,
                "voltage_offset_V": tech.voltage_offset_V,
                "temperature_C": tech.temperature_C,
            },
            "clock": {"frequency_MHz": clock_mhz},
            "components": components,
        }
    }


def to_flattened(description: Mapping[str, Any]) -> Dict[str, Any]:
    """Lower a native ``npuwattch:`` description to the flattened
    ``architecture: {version, local: [...]}`` form that ``build_database`` reads.

    Instance counts move into the ``name[1..count]`` suffix, which is exactly how
    ``DatabaseBuilder`` recovers ``instance_count``.
    """
    nw = description["npuwattch"]
    local: List[Dict[str, Any]] = []
    for comp in nw.get("components", []):
        count = int(comp.get("count", 1))
        name = comp["name"]
        flat_name = f"{name}[1..{count}]" if count >= 1 else name
        local.append({
            "name": flat_name,
            "class": comp.get("class", "unknown"),
            "attributes": comp.get("attributes", {}),
        })
    return {"architecture": {"version": str(nw.get("version", "1.0")), "local": local}}


# ---------------------------------------------------------------------------
# activity (manual §3.3, windowed, + stim_mode column)
# ---------------------------------------------------------------------------

# PyTorchSim core types (ARCHITECTURE_SPEC §6, `CoreType { WS_MESH, STONNE }`).
# Only ws_mesh (the dense weight-stationary systolic array) is modeled; the STONNE
# `SparseCore` (MSNetwork multiplier fabric + reduction/accumulation tree + SDMemory)
# is out of v1.0 scope, and `heterogeneous` is just a per-core mix of the two.
_SUPPORTED_CORE_TYPES = ("ws_mesh",)


def _unsupported_core_types(config: Mapping[str, Any]) -> List[str]:
    """Core types present in a TOGSim config that this harness does not model.

    ``core_type`` is *omitted* for pure ws_mesh runs (the spec's default), so its
    absence means systolic. Any ``stonne_*`` field (``stonne_config_path``,
    ``num_stonne_per_core``, …) also marks a STONNE/heterogeneous config.

    NOTE: written from ARCHITECTURE_SPEC §6 — **not yet validated against a real
    STONNE run** (we have no STONNE sample).
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
    """True when a TOGSim config turns on the optional L2 data cache.

    ``l2d_type: datacache`` (ARCHITECTURE_SPEC §3, tpuv4-style configs) enables
    it; ``none``/absent disables it. A config carrying other ``l2d_*`` keys
    without an explicit ``l2d_type`` is treated as enabled — better one spurious
    warning than a large on-chip SRAM excluded without a trace.
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
    """Clock frequency precedence: explicit flag > TechContext > harness log > default.

    For PyTorchSim the log always carries ``core_freq_mhz``, so the log wins over the
    default; ``default`` (e.g. the CLI's 200 MHz) is the last resort when no source
    provides a clock. Returns ``None`` only if every source is absent/zero.
    """
    for cand in (explicit, tech_clock, log_clock, default):
        if cand:
            return float(cand)
    return None


def _event_for(comp_class: str, stim_mode: str) -> str:
    if comp_class in _MEM_CLASSES:
        return _MEM_MODE_EVENT.get(stim_mode, stim_mode)
    if comp_class in _LINK_CLASSES:
        return "idle" if stim_mode == "idle" else "transfer"
    return "idle" if stim_mode == "idle" else "op"   # logic clusters


def build_activity(
    windows: Sequence[Any],
    bound_per_window: Sequence[Sequence[Any]],
    class_by_element: Mapping[str, str],
    *,
    prefix: str = "systolic",
    exec_cycles: Optional[Sequence[Optional[int]]] = None,
    name_by_element: Optional[Mapping[str, str]] = None,
    word_bits_by_element: Optional[Mapping[str, int]] = None,
    ports_by_element: Optional[Mapping[str, int]] = None,
) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """Build windowed §3.3 rows. Kernels run back-to-back, so window *i* spans
    ``[Σcyc<i, Σcyc≤i)``; per (element, stim_mode) counts are summed within a
    window. Returns ``(rows, total_cycles, warnings)``.

    ``name_by_element`` overrides the default ``prefix.element`` component
    naming (multi-compound emits mix prefixes). Bound actions whose ``unit`` is
    ``bytes``/``vectors`` are converted to memory words of the element's
    capacity-resolved macro via ``word_bits_by_element`` (bytes ÷ word bytes;
    vectors × lanes × operand bits ÷ word bits), rounded up. ``flits`` converts
    per element kind (§3.9): memory elements get flit_bits ÷ word_bits word
    accesses; crossbars get flits ÷ (valid_fraction(mode) × ports) active
    cycles (``ports_by_element``); links (d2dlink) get one crossing per flit.
    """
    rows: List[Dict[str, Any]] = []
    warnings: List[str] = []
    word_bits = word_bits_by_element or {}
    xbar_ports = ports_by_element or {}
    start = 0
    for i, (w, bounds) in enumerate(zip(windows, bound_per_window)):
        ecyc = None
        if exec_cycles is not None:
            ecyc = exec_cycles[i]
        if ecyc is None:
            ecyc = getattr(w, "exec_cycles", None)
        if ecyc is None:
            warnings.append(f"window {i}: no exec cycles; cycle_start/end left at {start}")
            ecyc = 0
        end = start + int(ecyc) - 1 if ecyc else start

        agg: Dict[Tuple[str, str], float] = {}
        for ba in bounds:
            for rae in ba.elements:
                count = ba.cycle_count
                unit = getattr(ba, "unit", "words")
                if unit == "flits":
                    comp_class = class_by_element.get(rae.element, "")
                    if comp_class in _MEM_CLASSES:
                        wb = word_bits.get(rae.element)
                        flit_bits = 8 * int(
                            (getattr(w, "config", None) or {}).get("booksim_flit_size") or 0)
                        if not wb or not flit_bits:
                            warnings.append(
                                f"window {i}: action {ba.action!r} (unit flits) "
                                f"needs a word width and flit size for element "
                                f"{rae.element!r}; counted as words"
                            )
                        else:
                            count = -(-(count * flit_bits) // wb)    # ceil
                    elif comp_class == "crossbar":
                        ports = xbar_ports.get(rae.element)
                        if not ports:
                            warnings.append(
                                f"window {i}: action {ba.action!r} (unit flits) "
                                f"has no port count for crossbar element "
                                f"{rae.element!r}; counted as cycles 1:1"
                            )
                        else:
                            frac = _XBAR_VALID_FRACTION.get(rae.stim_mode, 1.0)
                            count = -(-count // (frac * ports))      # ceil
                    # links (d2dlink & anything else): one crossing per flit.
                elif unit != "words":
                    wb = word_bits.get(rae.element)
                    if not wb:
                        warnings.append(
                            f"window {i}: action {ba.action!r} uses unit "
                            f"{unit!r} but element {rae.element!r} has no "
                            f"capacity-resolved word width; counted as words"
                        )
                    elif unit == "bytes":
                        count = -(-(count * 8.0) // wb)              # ceil
                    else:                                            # vectors
                        elem_bits = w.mac_config.operand_dtype.bits
                        count = -(-(count * w.lanes * elem_bits) // wb)
                agg[(rae.element, rae.stim_mode)] = (
                    agg.get((rae.element, rae.stim_mode), 0.0) + count
                )
        for (element, mode), cyc in agg.items():
            comp_class = class_by_element.get(element, "")
            if name_by_element and element in name_by_element:
                comp_name = name_by_element[element]
            else:
                comp_name = f"{prefix}.{element}" if prefix else element
            rows.append({
                "window": i,
                "cycle_start": start,
                "cycle_end": end,
                "component": comp_name,
                "event": _event_for(comp_class, mode),
                "mode": mode,
                "count": int(cyc) if float(cyc).is_integer() else cyc,
            })
        start = end + 1
    return rows, start, warnings


def _coverage_messages(
    windows: Sequence[Any],
    bound_per_window: Sequence[Sequence[Any]],
    projection: Any,
) -> Tuple[List[str], List[str]]:
    """Coverage check for every nonzero activity stat no projection action consumed.

    Returns ``(warnings, notes)`` — never fatal, per the emit-gate decision:

    - a stat listed in the projection's ``waivers`` is a WAIVED finding →
      one INFO note per stat (run totals), citing the declared justification;
    - anything else stays a per-window WARNING — with waived stats filtered
      out, a warning now really does mean "possibly a forgotten mapping".
    """
    tool = getattr(projection, "tool", "?")
    waivers: Mapping[str, str] = getattr(projection, "waivers", {}) or {}
    warnings: List[str] = []
    waived_totals: Dict[str, float] = {}
    waived_windows: Dict[str, int] = {}
    for i, (w, bounds) in enumerate(zip(windows, bound_per_window)):
        consumed = {ba.stat for ba in bounds}
        stats = getattr(w, "stats", {}) or {}
        for stat, value in stats.items():
            if stat in consumed or stat in _META_STATS or not value:
                continue
            if stat in waivers:
                waived_totals[stat] = waived_totals.get(stat, 0.0) + float(value)
                waived_windows[stat] = waived_windows.get(stat, 0) + 1
                continue
            warnings.append(
                f"window {i} ({getattr(w, 'kernel_hash', '?')}): activity stat "
                f"{stat!r}={value} is interpreted by no action in projection {tool!r} "
                "(intentional coarser fidelity, or an incomplete projection)"
            )
    notes = [
        f"activity stat {stat!r} (total "
        f"{int(total) if float(total).is_integer() else total} across "
        f"{waived_windows[stat]} window(s)) is not charged — waived in "
        f"projection {tool!r}: {waivers[stat]}"
        for stat, total in sorted(waived_totals.items())
    ]
    return warnings, notes


# ---------------------------------------------------------------------------
# capacity-driven memories (bundle `memories:` → SRAM template components)
# ---------------------------------------------------------------------------

def _sram_resolve_capacity():
    """The SRAM estimator's capacity→template resolver, or ``None``.

    ``estimators.sram.sram`` is deliberately stdlib-only, so importing it here
    is cheap and safe — the package's "do not import estimators" rule guards
    against the torch-heavy modules, and this is the sanctioned exception (the
    template table must have exactly one home, and the estimator owns it).
    """
    try:
        from estimators.sram.sram import resolve_capacity
        return resolve_capacity
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# writers
# ---------------------------------------------------------------------------

def _activity_csv_text(rows: Sequence[Mapping[str, Any]], total_cycles: int) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(ACTIVITY_COLUMNS))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in ACTIVITY_COLUMNS})
    # §3.3 meta row: total cycles (component "__meta__", event "total_cycles").
    writer.writerow({
        "window": "", "cycle_start": "", "cycle_end": "",
        "component": "__meta__", "event": "total_cycles", "mode": "",
        "count": total_cycles,
    })
    return buf.getvalue()


def write_arch(
    emitted: EmittedArch,
    out_dir: Path,
    *,
    description_name: str = "description.yaml",
    activity_name: str = "activity.csv",
) -> Tuple[Path, Path]:
    """Write ``description.yaml`` (§3.1) and ``activity.csv`` (§3.3) to ``out_dir``.

    Returns the two written paths.
    """
    import yaml  # local import: PyYAML is a declared dep, keep module import light

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    desc_path = out_dir / description_name
    act_path = out_dir / activity_name

    with desc_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(emitted.description, f, sort_keys=False)
    with act_path.open("w", encoding="utf-8") as f:
        f.write(_activity_csv_text(emitted.activity_rows, emitted.total_cycles))
    return desc_path, act_path


# ---------------------------------------------------------------------------
# pytorchsim one-call entry (mirrors energy.aggregate.analyze_run)
# ---------------------------------------------------------------------------

def _apply_energy_table(description: Mapping[str, Any], table: Any,
                        notes: List[str], warnings: List[str]) -> None:
    """Override the emitted ``hbm`` components' constants with the run's own
    energy table (``--energy-table``, author handoff 2026-08-10).

    The attributes are the canonical per-command constants the
    ``HBMCostProvider`` prices from, so the override flows unchanged through
    ``write_arch`` → the ``-d``/``-l`` replay. The author table format has no
    refresh term — the built-in derived REFab constant then stays, noted (the
    ``refresh_pj_per_refab`` key is our proposed extension).
    """
    hbm_comps = [c for c in description.get("npuwattch", {}).get("components", [])
                 if c.get("class") == "hbm"]
    if not hbm_comps:
        warnings.append(
            f"--energy-table {table.path.name} supplied but the run emitted no "
            f"DRAM component (no dram_channels / DRAM stats in the log) — the "
            f"table is unused"
        )
        return
    for c in hbm_comps:
        attrs = c.setdefault("attributes", {})
        attrs["mem_act_energy_pJ"] = table.act_pj
        attrs["mem_access_energy_per_bit_pJ"] = table.transfer_pj_per_bit
        if table.ref_pj is not None:
            attrs["mem_ref_energy_pJ"] = table.ref_pj
    ref_note = (f"refresh {table.ref_pj:g} pJ/REFab from the table"
                if table.ref_pj is not None else
                "refresh keeps the built-in derived constant (the table has "
                "no refresh term)")
    notes.append(
        f"DRAM constants from the run's energy table {table.name!r} "
        f"({table.path.name}): activation {table.act_pj:g} pJ, transfer "
        f"{table.transfer_pj_per_bit:g} pJ/bit "
        f"({table.transfer_split_str()}); {ref_note}"
    )


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
    """Read a PyTorchSim run (TOGSim logs + gem5/codegen outputs, two separate
    directories) and emit its NPUWattch description + activity.

    ``base_config`` is the run's config.yml, when provided: each log's header
    wins on overlap, the yml fills gaps in damaged headers, and any key where
    the two disagree is warned (evidence of a mixed run directory).

    ``booksim_dir`` is the run's ``booksim2_config/`` (optional): ``anynet`` NoC
    topologies need their ``.net`` file from it; ``fly`` NoCs are self-contained
    in the log. Without it an anynet run's NoC degrades to a warning.

    ``energy_table`` (optional, a ``harness.pytorchsim.EnergyTable``): the
    run's declared DRAM energy-cost table — its constants replace the dram
    compound's built-in ones on the emitted ``hbm`` components (INFO note);
    logs declaring a *different* table than the one charged are warned.

    The physical architecture is single (a reconfigurable systolic array); all
    kernels must agree on ``lanes`` and the element set. If a later kernel's config
    differs (e.g. a run mixing fp and int kernels), the first kernel's config is
    used for the description and the divergence is recorded as a warning — the
    per-kernel activity still reflects each kernel faithfully.

    Definition errors surface here: a malformed compound/projection hard-errors via
    bundle validation + ``resolve_compound``/``bind_window``; activity a projection
    leaves uninterpreted is reported (non-fatal) in ``EmittedArch.warnings`` —
    unless the projection *declares* the exclusion (its ``waivers``/``out_of_scope``
    blocks), which lands in ``EmittedArch.notes`` (INFO) instead.
    """
    from .harness.compounds import (
        Compound,
        CompoundBundleError,
        resolve_compound,
    )
    from .harness.pytorchsim import (
        bind_window,
        build_hierarchy,
        expand_bounds,
        load_definitions,
        read_run,
    )

    if bundle is None:
        bundle = load_definitions()
    compound = bundle.compound(compound_name)
    projection = bundle.projection("pytorchsim")
    pm = bundle.primitive_modes

    all_windows = read_run(togsim_dir, gem5_dir, base_config=base_config,
                           booksim_dir=booksim_dir,
                           expected_dram_table=(energy_table.name
                                                if energy_table else None))
    # Non-MAC kernel windows (softmax/layernorm/elementwise — no linalg.matmul)
    # are KEPT since 2026-07-30: they bind the non-systolic compounds
    # (vpu/fpsfu/spads/dma/dram/noc). The templated vfu/spads elements still
    # need a datapath dtype, borrowed from the run's first MAC kernel (the
    # physical array is uniform within a run); a run with NO MAC kernel at all
    # falls back to an assumed fp32 datapath + WARNING.
    windows = list(all_windows)
    mac_windows = [w for w in windows if w.mac_config is not None]

    warnings: List[str] = []
    # Planned-but-unbuilt external integrations are WARNINGS (a temporary gap,
    # unlike the sanctioned out_of_scope declarations below).
    warnings.extend(
        f"pending third-party integration (not implemented — this energy is "
        f"NOT included): {t}"
        for t in getattr(projection, "third_party_pending", ())
    )
    # INFO tier: the projection's scope boundary (`out_of_scope`) leads, so a
    # reader sees the sanctioned exclusions before any per-stat waiver detail.
    notes: List[str] = list(projection.out_of_scope)
    # Per-window reader warnings (MLIR/meta provenance, low-confidence flags,
    # missing gem5 stats, …) are part of the emitted provenance.
    for w in all_windows:
        warnings.extend(
            x if x.startswith(w.kernel_hash) else f"{w.kernel_hash}: {x}"
            for x in w.warnings
        )
    # Representative MacConfig: the run's first MAC kernel; a run with no MAC
    # kernel gets the fp32 fallback (assumption unbacked by run evidence →
    # WARNING; the borrowed-dtype case is a sanctioned assumption → INFO note).
    lanes0 = windows[0].lanes
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
        from .harness.pytorchsim.mac_config import fallback_fp32_mac_config
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
    for w in mac_windows[1:]:
        rw = resolve_compound(compound, w.mac_config)
        if set(rw) != set(resolved0):
            warnings.append(f"kernel {w.kernel_hash} has a different element set; using {mac_windows[0].kernel_hash}")
        elif any(rw[e].config != resolved0[e].config for e in resolved0):
            warnings.append(
                f"kernel {w.kernel_hash} reconfigures the array "
                f"(config differs from {mac_windows[0].kernel_hash}); description uses the first"
            )

    cfg0 = windows[0].config or {}
    if base_config:
        from .harness.pytorchsim.run_config import config_conflicts
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
    # Integer run-config keys double as expression symbols for harness-owned
    # compounds (e.g. the spads' capacity_kbit).
    extra_symbols = {k: v for k, v in cfg0.items()
                     if isinstance(v, int) and not isinstance(v, bool)}

    # Header from the tool-agnostic builder; components are emitted one per
    # physical instance (core{c}.array{a}.pe, core{c}.vmem, …) — never lumped.
    # The per-instance activity split lives in harness instances.py.
    description = build_description(
        {}, tech, num_arrays=num_arrays, clock_mhz=float(clk), prefix=prefix,
        warnings=warnings, num_cores=num_cores,
    )
    (comps, class_by_element, name_by_element, word_bits_by_element,
     ports_by_element, per_by_element) = _emit_per_instance(
        resolved0, num_cores=num_cores, arrays_per_core=arrays_per_core,
        warnings=warnings)
    description["npuwattch"]["components"].extend(comps)

    # Auxiliary compounds the projection also drives (e.g. the spads): resolved
    # against the first kernel + the run-config symbols, emitted WITHOUT the mac
    # compound's prefix. An element whose config symbols this run lacks (older
    # configs) is skipped with a warning, element by element.
    aux_compounds = []
    aux_resolved_by_compound: Dict[str, Dict[str, Any]] = {}
    for cname in projection.compounds:
        if cname == compound_name or cname not in bundle.compounds:
            continue
        aux = bundle.compound(cname)
        aux_compounds.append(aux)
        resolved_aux: Dict[str, Any] = {}
        aux_resolved_by_compound[cname] = resolved_aux
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
        description["npuwattch"]["components"].extend(aux_comps)
        class_by_element.update(acls)
        name_by_element.update(anames)
        word_bits_by_element.update(wb)
        ports_by_element.update(pb)
        per_by_element.update(aper)

    # The run's own DRAM energy table replaces the built-in constants on the
    # emitted hbm components (the provider reads them as canonical attrs, so
    # write_arch → -d/-l replay carries the override unchanged).
    if energy_table is not None:
        _apply_energy_table(description, energy_table, notes, warnings)

    # Non-MAC windows bind with the representative MacConfig (the systolic
    # actions still bind only where their stats carry activity); the effective
    # windows also feed build_activity, whose bytes/vectors unit conversion
    # reads the operand dtype.
    eff_windows = [w if w.mac_config is not None
                   else dc_replace(w, mac_config=rep_mac) for w in windows]
    bound_per_window = []
    seen_notes: set = set()
    for w in eff_windows:
        skipped: List[str] = []
        bounds = sum((bind_window(w, projection, c, pm, skipped=skipped)
                      for c in aux_compounds),
                     bind_window(w, projection, compound, pm, skipped=skipped))
        bounds, split_notes = expand_bounds(
            w, bounds, per_by_element,
            num_cores=num_cores, arrays_per_core=arrays_per_core)
        bound_per_window.append(bounds)
        for msg in skipped + split_notes:   # identical notes reported once
            if msg not in seen_notes:
                seen_notes.add(msg)
                warnings.append(msg)
    rows, total_cycles, act_warn = build_activity(
        eff_windows, bound_per_window, class_by_element, prefix=prefix,
        exec_cycles=[w.exec_cycles for w in windows],
        name_by_element=name_by_element,
        word_bits_by_element=word_bits_by_element,
        ports_by_element=ports_by_element,
    )
    warnings.extend(act_warn)
    cov_warnings, cov_notes = _coverage_messages(windows, bound_per_window, projection)
    warnings.extend(cov_warnings)
    notes.extend(cov_notes)

    # Harness-owned builder (harness/pytorchsim/hierarchy.py): builders are
    # per-source adapters; the core keeps only the shared tree structure and
    # renderers (report.tree).
    try:
        hierarchy = build_hierarchy(
            description, resolved0, aux_resolved_by_compound,
            num_cores=num_cores, arrays_per_core=arrays_per_core,
        )
    except Exception as e:                      # a view must never kill the emit
        warnings.append(f"hierarchy view unavailable: {e}")
        hierarchy = None

    # Per-window provenance from the PARSED data (kind is derived, never
    # guessed): a window with its own MacConfig is `mac`, `fused` when SFU or
    # vector activity rode along in the same kernel; a window without one is
    # `non_mac` (charged via the borrowed/fallback dtype).
    provenance: List[Dict[str, Any]] = []
    for i, w in enumerate(windows):
        s = w.stats or {}
        sys_c = int(s.get("systolic_active_cycles", 0) or 0)
        vec_c = int(s.get("vector_active_cycles", 0) or 0)
        sfu = int(sum(s.get(k, 0) or 0 for k in _SFU_STAT_KEYS))
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

    return EmittedArch(
        description=description,
        activity_rows=rows,
        total_cycles=total_cycles,
        warnings=warnings,
        notes=notes,
        hierarchy=hierarchy,
        window_labels=[w.kernel_hash for w in windows],
        window_provenance=provenance,
    )
