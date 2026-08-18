"""Timeloop/Accelergy ingest — an architecture YAML → a native NPUWattch run.

This is the home of what used to be the console's "legacy Accelergy path"
(``-d arch.yaml`` → flatten → per-component estimator calls). That path predated
the §6 energy core: it asked one estimator plugin per component for a number and
printed it, with no activity model, no window accounting, and no report. It also
carried its own class→plugin routing table, which is why ``src/estimators/`` kept
prototype-era ``adder``/``crossbar``/``regfile``/``custom`` directories alive.

Here the same input becomes a **native §3.1 description** and goes through the
identical core every other input goes through — the same provider chain (v2 logic
MLPs + the SRAM estimator), the same §6 aggregation, the same ``--report``. The
Accelergy-specific knowledge that remains is exactly what a harness owns: reading
that toolchain's file format (:mod:`npuwattch.yaml_flattener_accelergy_v4`) and
translating its vocabulary into ours (:mod:`.vocabulary`).

**Activity.** With ``--stats`` (a ``timeloop-{model,mapper}.stats.txt`` file or
a directory of per-layer stats files), the run is **vectored**: :mod:`.stats`
turns Timeloop's per-level access counts into native §3.3 rows (reads → read,
fills+updates → write, Computes → op in the ``hold_b`` mode the projection
declares). Without it, the run is the labeled **VECTORLESS** estimate: every
component charged at 25 % of random switching, exactly as ``-d native.yaml``
without ``-l`` is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ...arch_synth import EmittedArch
from ...naming import NamingError, validate_attributes
from .vocabulary import (
    UNMAPPED_PRIMITIVE,
    attributes_for,
    primitive_for,
    reclassify_regfile_as_sram,
)

__all__ = ["ingest", "description_from_accelergy"]

#: Top-level attribute names carrying the design clock, in MHz and in seconds.
_CLOCK_MHZ_KEYS = ("clockrate", "clock_rate", "frequency_mhz", "clock_mhz")
_CLOCK_SECONDS_KEYS = ("global_cycle_seconds", "cycle_seconds")


def ingest(inputs: Mapping[str, Path], tech: Any, **opts: Any) -> EmittedArch:
    """Harness entrypoint: ``{"arch": <architecture.yaml>, "stats"?: <path>,
    "stats_map"?: <yaml>}`` → ``EmittedArch``."""
    arch_path = Path(inputs["arch"])
    description, warnings, notes = description_from_accelergy(
        arch_path, tech, default_clock_mhz=opts.get("default_clock_mhz"),
        verbose=int(opts.get("verbose", 0)))

    stats_path = inputs.get("stats")
    if stats_path is not None:
        from .stats import activity_from_stats

        if opts.get("vectorless_activity") is not None:
            warnings.append(
                "--vectorless-activity ignored: the Timeloop stats provide "
                "real activity")
        rows, total_cycles, window_labels, s_warnings, s_notes = (
            activity_from_stats(
                Path(stats_path), description,
                mode=str(opts.get("stats_mode") or "windows"),
                map_path=inputs.get("stats_map")))
        warnings.extend(s_warnings)
        notes.extend(s_notes)
        vectorless: Optional[float] = None
    else:
        from ...energy.vectorless import (
            DEFAULT_VECTORLESS_ACTIVITY,
            vectorless_activity_rows,
        )

        vectorless = float(opts.get("vectorless_activity")
                           or DEFAULT_VECTORLESS_ACTIVITY)
        rows, vectorless_notes = vectorless_activity_rows(
            description, activity=vectorless)
        notes.extend(vectorless_notes)
        total_cycles = 1
        window_labels = ["vectorless"]

    hierarchy = None
    try:
        from .tree import tree_from_accelergy
        hierarchy = tree_from_accelergy(arch_path)
    except Exception as e:                      # view only — never fatal
        warnings.append(f"hierarchy view unavailable: {e}")

    return EmittedArch(
        description=description,
        activity_rows=rows,
        total_cycles=total_cycles,
        warnings=warnings,
        notes=notes,
        hierarchy=hierarchy,
        tree_source="declared in the Accelergy description",
        window_labels=window_labels,
        vectorless_activity=vectorless,
    )


def description_from_accelergy(
    arch_path: Path,
    tech: Any,
    *,
    default_clock_mhz: Optional[float] = None,
    verbose: int = 0,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Accelergy v0.4 architecture YAML → ``({"npuwattch": ...}, warnings, notes)``.

    The flattener already resolves the hierarchy, spatial fanout and attribute
    inheritance, so each flattened entry is one physical component with a full
    dotted name and an instance count. This function's job is the vocabulary
    boundary: class → primitive, attributes → canonical names.
    """
    from ...npuwattch_db import build_database_from_dict
    from ...yaml_flattener_accelergy_v4 import AccelergyV04Flattener

    flattener = AccelergyV04Flattener()
    content = flattener.parse_yaml(str(arch_path))
    flattened = flattener.flatten_hierarchy(content)
    db = build_database_from_dict(flattened, verbose=verbose,
                                  source_name=str(arch_path))

    warnings: List[str] = []
    notes: List[str] = []
    components: List[Dict[str, Any]] = []
    unmapped: List[str] = []
    declared_nodes: set = set()

    for entry in db.components:
        if not entry.enabled:
            continue
        name = entry.base_name or entry.name
        declared = _declared_node(entry.attributes)
        if declared:
            declared_nodes.add(declared)
        primitive = primitive_for(entry.comp_class, entry.subclass,
                                  entry.attributes)
        if primitive is None:
            unmapped.append(f"{name} (class {entry.comp_class!r})")
            primitive = UNMAPPED_PRIMITIVE

        attrs = attributes_for(primitive, entry.attributes, component=name,
                               warnings=warnings, notes=notes)

        if primitive == "regfile" and reclassify_regfile_as_sram(attrs):
            primitive = "sram"
            notes.append(
                f"{name}: declared a regfile but holds more than "
                f"32 Kib — modeled with the SRAM estimator")

        primitive, attrs = _validated(primitive, attrs, component=name,
                                      warnings=warnings)
        components.append({
            "name": name,
            "class": primitive,
            "count": int(entry.instance_count),
            "attributes": attrs,
        })

    if unmapped:
        warnings.append(
            f"{len(unmapped)} component(s) have no NPUWattch primitive and are "
            f"priced with the placeholder: {', '.join(sorted(unmapped))}")
    if not components:
        raise ValueError(
            f"{arch_path}: no enabled components found — is this an Accelergy "
            f"v0.4 architecture description?")

    # A native description carries ONE technology block; Accelergy declares the
    # node per component. Disagreement is worth saying out loud — the run is
    # being evaluated at the CLI's node, not the one written in the file.
    foreign = sorted(n for n in declared_nodes if n != str(tech.node).lower())
    if foreign:
        warnings.append(
            f"the description declares technology {', '.join(foreign)} but the "
            f"run is evaluated at {tech.node} (--node); NPUWattch models the "
            f"node it is told to")

    clock_mhz, clock_note = _clock_mhz(flattener, tech, default_clock_mhz)
    if clock_note:
        notes.append(clock_note)

    description = {
        "npuwattch": {
            "version": "1.0",
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
    return description, warnings, notes


def _declared_node(attributes: Mapping[str, Any]) -> Optional[str]:
    """The component's own ``technology:`` attribute, normalized to '45nm'."""
    for key, value in (attributes or {}).items():
        if str(key).strip().lower() != "technology":
            continue
        text = str(value).strip().lower().replace(" ", "")
        return text if text.endswith("nm") else f"{text}nm"
    return None


def _validated(primitive: str, attrs: Dict[str, Any], *, component: str,
               warnings: List[str]) -> Tuple[str, Dict[str, Any]]:
    """Run §3.1 naming validation; a component that fails becomes user_defined.

    A single malformed component must not take down a 200-component
    description — it becomes placeholder-priced and says why.
    """
    try:
        warnings.extend(validate_attributes(primitive, attrs,
                                            component=component))
    except NamingError as e:
        warnings.append(
            f"{component}: {e} — priced with the placeholder instead")
        return UNMAPPED_PRIMITIVE, attrs
    return primitive, attrs


def _clock_mhz(flattener: Any, tech: Any,
               default_clock_mhz: Optional[float]) -> Tuple[float, Optional[str]]:
    """Clock precedence: ``--clock-mhz`` > the description > the CLI default.

    Accelergy spells the clock two ways at the top level — ``clockrate`` in MHz
    and Timeloop's ``global_cycle_seconds``.
    """
    declared = getattr(flattener, "top_level_attributes", None) or {}
    lowered = {str(k).strip().replace("-", "_").lower(): v
               for k, v in declared.items()}

    from_desc: Optional[float] = None
    for key in _CLOCK_MHZ_KEYS:
        if lowered.get(key) is not None:
            try:
                from_desc = float(lowered[key])
            except (TypeError, ValueError):
                from_desc = None
            break
    if from_desc is None:
        for key in _CLOCK_SECONDS_KEYS:
            value = lowered.get(key)
            if value:
                try:
                    from_desc = 1.0e-6 / float(value)   # s/cycle → MHz
                except (TypeError, ValueError, ZeroDivisionError):
                    from_desc = None
                break

    explicit = getattr(tech, "clock_mhz", None)
    if explicit:
        note = None
        if from_desc and abs(from_desc - float(explicit)) > 1e-6:
            note = (f"clock: --clock-mhz {explicit:g} MHz overrides the "
                    f"description's {from_desc:g} MHz")
        return float(explicit), note
    if from_desc:
        return from_desc, f"clock: {from_desc:g} MHz, from the description"
    fallback = float(default_clock_mhz or 200.0)
    return fallback, (f"clock: the description declares none — assuming "
                      f"{fallback:g} MHz")
