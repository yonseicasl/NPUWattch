"""Emitter of the description and the activity rows. All harnesses use it.

This module is part of the NPUWattch core. It is not a harness. A harness
gives two things:

* the log readers, which parse the files of one simulator;
* the definitions: a vocabulary table, compounds, and projections.

The emitter applies the definitions to one run. The input is the resolved
compounds and the bound actions of a harness. The output is the two inputs
that the core reads:

* The description (manual §3.1, root key ``npuwattch:``).
  :func:`build_description` makes the description. :func:`to_flattened`
  changes it to the form ``architecture: {local: [...]}`` that
  ``npuwattch_db.build_database`` reads.
* The activity rows (manual §3.3). :func:`build_activity` makes one row for
  each combination of window, element, and stim_mode. The columns
  ``component,event,count`` are the columns of §3.3. The optional column
  ``mode`` gives the stim_mode, because the dynamic energy of §6 depends on
  the stim_mode. For example, the energies of ``hold_b`` and ``random`` are
  very different, and the event does not show the stim_mode.

:class:`EmittedArch` contains the result of one run. :func:`write_arch` writes
the result to two files.

Errors and warnings:

* A definition error stops the run. The checks are in ``resolve_compound``,
  ``bind_window``, and ``validate_attributes``. Examples:

  - an unknown compound or element
  - a stim_mode that has no characterization
  - a ``{...}`` template that has no value
  - a mode that the primitive does not support
* A nonzero activity stat that no projection action uses does not stop the
  run. The emitter cannot know if the author of the projection ignored the
  stat intentionally. Thus each such stat gives a warning in
  ``EmittedArch.warnings``.

The emitter does not depend on the models. It emits structure (classes,
counts, attributes, event counts) and no energy values.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from npuwattch.diagnostics import NPUWattchError, about, info, warning
from npuwattch.naming import validate_attributes

__all__ = [
    "EmitterError",
    "EmittedArch",
    "build_description",
    "build_activity",
    "to_flattened",
    "write_arch",
    "ACTIVITY_COLUMNS",
]

# The class of the emitted component for each primitive. The core resolves the
# class to an estimator (``register_file`` -> regfile, ``intmac`` -> intmac).
# A primitive that is not in this table uses its own name as the class.
PRIMITIVE_TO_CLASS: Dict[str, str] = {
    "intmac": "intmac",
    "fpmac": "fpmac",
    "mxfpmac": "mxfpmac",
    "regfile": "register_file",
    "arithmetic": "adder",
    "crossbar": "crossbar",
}

# stim_mode -> event of §3.3, for each component family.
_MEM_CLASSES = ("register_file", "regfile", "sram", "fifo", "hbm")
_LINK_CLASSES = ("crossbar", "noc", "wire", "d2dlink")
_MEM_MODE_EVENT = {"read": "read", "write": "write", "idle": "idle", "random": "write"}

# Unit "flits" on a crossbar element. At a stim_mode with partial activity,
# N flits use N / (valid_fraction x ports) cycles of the full crossbar.
# Thus the dynamic energy stays proportional to the flit count (§3.9).
# A stim_mode that is not in this table has a fraction of 1.0.
_XBAR_VALID_FRACTION = {"valid25": 0.25}

# Window stats that are inputs for timing and leakage. A projection does not
# charge them as activity, thus the coverage check ignores them.
_META_STATS = frozenset({"total_exec_cycles", "numCycles"})

# Window and kernel: a window is one time interval [cycle_start, cycle_end] of
# the activity rows (§3.3). The term applies to all harnesses.
# A window is not always a kernel. A gem5 periodic dump, a Timeloop layer, and
# the vectorless interval are windows also.
# For PyTorchSim, one compiled kernel is one window. Thus the console and the
# report show "kernel" for PyTorchSim runs.
# The column name below and the code identifiers stay "window".
ACTIVITY_COLUMNS: Tuple[str, ...] = (
    "window", "cycle_start", "cycle_end", "component", "event", "mode", "count",
)


class EmitterError(NPUWattchError, ValueError):
    """A resolved element cannot be emitted as a component (a definition error)."""


# ---------------------------------------------------------------------------
# result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EmittedArch:
    """The description and the activity rows of one run, with their provenance."""

    description: Dict[str, Any]                 # {"npuwattch": {...}}, manual §3.1
    activity_rows: List[Dict[str, Any]]         # rows of manual §3.3, with the mode column
    activity_columns: Tuple[str, ...] = ACTIVITY_COLUMNS
    total_cycles: int = 0
    warnings: List[str] = field(default_factory=list)
    #: Notes: the exclusions that the projection declares in its `waivers` and
    #: `out_of_scope` blocks. They are intentional and documented.
    #: The notes stay apart from `warnings`. Thus a warning always tells the
    #: user that the result can be incorrect.
    notes: List[str] = field(default_factory=list)
    #: The instance hierarchy (report.tree.ArchTreeNode): cores x arrays x PEs,
    #: the scratchpads of each core, the NoC. The flat description gives this
    #: structure only as counts. Only the display uses the hierarchy (CLI
    #: --tree, the report). The §3.1 description stays flat.
    hierarchy: Optional[Any] = None
    #: The source of ``hierarchy``, for the caption of --tree. An example is
    #: "declared in the Accelergy description". If the value is ``None``, the
    #: console shows its default caption.
    tree_source: Optional[str] = None
    #: The kernel hash of each window, in window order. The energy display for
    #: each window uses it, because the §3.3 CSV contains only indices.
    window_labels: List[str] = field(default_factory=list)
    #: One provenance record for each window, in window order. The values come
    #: from the parsed data:
    #: {"window", "kernel", "kind": mac|fused|non_mac, "dtype", "dtype_source":
    #: own|borrowed:<hash>|fallback_fp32, "systolic_active_cycles",
    #: "vector_active_cycles", "sfu_ops", "dram_requests", "exec_cycles"}.
    #: The console prints the records at -v>=2. report.json always contains
    #: them.
    window_provenance: List[Dict[str, Any]] = field(default_factory=list)
    #: The fraction of random switching that the harness assumed. The harness
    #: sets it if the simulator gave no counters and the activity is synthetic.
    #: The CLI and the report then label the run VECTORLESS.
    #: ``None``: the activity came from the counters of the simulator.
    vectorless_activity: Optional[float] = None


def _components_for(
    resolved: Mapping[str, Any],
    *,
    num_arrays: int,
    num_cores: int,
    prefix: str,
    warnings: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, int]]:
    """Change the resolved elements into components of §3.1.

    There are two types of element:

    * A usual primitive becomes one component. Its count is the element count
      x the multiplier of the ``per`` domain (array, core, or chip). A count
      of 0 tells that the structure is not in this run. An example is
      ``icnt_d2d`` on a single-chip fly network. The function ignores such an
      element and gives no warning.
    * An ``sram`` element whose config gives ``capacity_kbit`` or
      ``capacity_bit`` becomes one or two components. The macro templates of
      the SRAM estimator (``resolve_capacity``, the bank hierarchy of §3.8)
      give the parts. The primary component gets the activity. The optional
      ``.tail`` part has only leakage and area.

    Return ``(components, word_bits_by_element, ports_by_element)``:

    * ``word_bits_by_element``: the word width of the primary part of each
      capacity element. The conversion of the units bytes, vectors, and flits
      uses it.
    * ``ports_by_element``: the port count of each crossbar element. The
      conversion of flits to cycles uses it.
    """
    # The SRAM estimator owns the table of macro templates. The module
    # `npuwattch_estimators.sram.sram` uses only the standard library, thus this import
    # is permitted here.
    try:
        from npuwattch_estimators.sram.sram import resolve_capacity
    except ImportError:
        resolve_capacity = None
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
                raise EmitterError.nw(2201, element=name)
            capacity_bits = (int(cfg["capacity_bit"]) if "capacity_bit" in cfg
                             else int(cfg["capacity_kbit"]) * 1024)
            if resolve_capacity is None:
                if warnings is not None:
                    warnings.append(warning(2202, element=name))
                continue
            parts, part_warns = resolve_capacity(capacity_bits)
            if warnings is not None:
                warnings.extend(about(name, w) for w in part_warns)
                if len(parts) > 1:
                    warnings.append(warning(2203, element=name))
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
    """Change the resolved elements into one §3.1 component for each instance.

    This function does not make one component whose ``count`` includes all
    cores and arrays. It emits each instance separately, which is the smallest
    unit that the simulator reports:

    * A ``per: array`` element becomes ``core{c}.array{a}.{element}``, one
      for each core and array.
    * A ``per: core`` element becomes ``core{c}.{element}``, one for each
      core.
    * A ``per: chip`` element keeps its name.

    Each component has the count of the element in one instance. The function
    records the messages of the first instance only, because all instances
    have the same structure.

    Return ``(components, class_by_element, name_by_element,
    word_bits_by_element, ports_by_element, per_by_element)``. The key of the
    first five is the element name with its instance prefix. The expanded
    bound actions use that name. The key of ``per_by_element`` is the element
    name without a prefix. The bound actions before expansion use that name.
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
    # The element config must already use NPUWattch attribute names. A config
    # with a different name is a definition error, thus the check raises.
    attrs = {k: v for k, v in (config if isinstance(config, Mapping)
                               else {}).items() if v is not None}
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
# description (manual §3.1, root key npuwattch:)
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
    """Make the description (root key ``npuwattch:``) from a resolved compound.

    ``resolved`` is the output of ``resolve_compound(...)``: element name ->
    ResolvedElement. Each element becomes one component. The ``per`` domain of
    the element (array, core, or chip) gives the instance multiplier.
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
    """Change a description to the form that ``build_database`` reads.

    The form is ``architecture: {version, local: [...]}``. The instance count
    of a component moves into the suffix ``name[1..count]``. ``DatabaseBuilder``
    reads ``instance_count`` from that suffix.
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
# activity rows (manual §3.3, with the stim_mode column)
# ---------------------------------------------------------------------------

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
    """Make the activity rows of §3.3, one group of rows for each window.

    The windows run one after the other. Thus window *i* starts at the sum of
    the cycles of the windows before it. In one window, the function adds the
    counts of each pair of element and stim_mode. Return ``(rows,
    total_cycles, warnings)``.

    ``name_by_element`` replaces the default component name
    ``prefix.element``. This is necessary if the run has compounds with
    different prefixes.

    The ``unit`` of a bound action sets the conversion of its count. The
    function rounds each result up.

    * ``bytes``: count x 8 / word bits. The result is memory words.
    * ``vectors``: count x lanes x operand bits / word bits. The result is
      memory words.
    * ``flits`` on a memory element: count x flit bits / word bits. The
      result is word accesses.
    * ``flits`` on a crossbar: count / (valid fraction of the stim_mode x
      ports). The result is active cycles (§3.9).
    * ``flits`` on a link (d2dlink): one crossing for each flit.

    ``word_bits_by_element`` gives the word bits of the macro of an element.
    ``ports_by_element`` gives the ports of a crossbar.
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
            warnings.append(warning(2204, window=i, start=start))
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
                            warnings.append(warning(
                                2205, window=i, action=ba.action,
                                element=rae.element))
                        else:
                            count = -(-(count * flit_bits) // wb)    # ceil
                    elif comp_class == "crossbar":
                        ports = xbar_ports.get(rae.element)
                        if not ports:
                            warnings.append(warning(
                                2206, window=i, action=ba.action,
                                element=rae.element))
                        else:
                            frac = _XBAR_VALID_FRACTION.get(rae.stim_mode, 1.0)
                            count = -(-count // (frac * ports))      # ceil
                    # A link (d2dlink or any other class): one crossing for each flit.
                elif unit != "words":
                    wb = word_bits.get(rae.element)
                    if not wb:
                        warnings.append(warning(
                            2207, window=i, action=ba.action, unit=unit,
                            element=rae.element))
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
            if comp_class in _MEM_CLASSES:
                event = _MEM_MODE_EVENT.get(mode, mode)
            elif mode == "idle":
                event = "idle"
            else:
                event = "transfer" if comp_class in _LINK_CLASSES else "op"
            rows.append({
                "window": i,
                "cycle_start": start,
                "cycle_end": end,
                "component": comp_name,
                "event": event,
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
    """Find each nonzero activity stat that no projection action used.

    Return ``(warnings, notes)``. The check does not stop the run.

    - A stat that is in the ``waivers`` of the projection gives one note. The
      note shows the total of the run and the declared reason.
    - Each other stat gives one warning for each window. Such a warning tells
      the user that the projection possibly has no action for the stat.
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
            warnings.append(warning(
                2208, window=i, kernel=getattr(w, "kernel_hash", "?"),
                stat=stat, value=value, tool=tool))
    notes = [
        info(2209, stat=stat,
             total=int(total) if float(total).is_integer() else total,
             windows=waived_windows[stat], tool=tool, reason=waivers[stat])
        for stat, total in sorted(waived_totals.items())
    ]
    return warnings, notes


# ---------------------------------------------------------------------------
# writers
# ---------------------------------------------------------------------------

def write_arch(
    emitted: EmittedArch,
    out_dir: Path,
    *,
    description_name: str = "description.yaml",
    activity_name: str = "activity.csv",
) -> Tuple[Path, Path]:
    """Write ``description.yaml`` (§3.1) and ``activity.csv`` (§3.3) to ``out_dir``.

    Return the paths of the two files.
    """
    import yaml  # A local import keeps the import of this module fast.

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    desc_path = out_dir / description_name
    act_path = out_dir / activity_name

    with desc_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(emitted.description, f, sort_keys=False)
    with act_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ACTIVITY_COLUMNS))
        writer.writeheader()
        for row in emitted.activity_rows:
            writer.writerow({k: row.get(k, "") for k in ACTIVITY_COLUMNS})
        # The last row gives the total cycles (manual §3.3).
        writer.writerow({
            "window": "", "cycle_start": "", "cycle_end": "",
            "component": "__meta__", "event": "total_cycles", "mode": "",
            "count": emitted.total_cycles,
        })
    return desc_path, act_path
