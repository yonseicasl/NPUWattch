"""Timeloop/Accelergy ingest: an Accelergy architecture file -> a NPUWattch run.

This module is the entry point of the harness. It changes an Accelergy v0.4
architecture file into a description (manual §3.1). The description then goes
through the same energy core (manual §6) as all other inputs:

* the same model providers (the logic MLPs and the SRAM estimator),
* the same energy aggregation,
* the same ``--report``.

Two modules contain the knowledge that is specific to Accelergy.
:mod:`.accelergy_flattener` reads the file format. :mod:`.vocabulary`
translates the Accelergy names into NPUWattch names.

Activity
--------
``--stats`` takes one ``timeloop-{model,mapper}.stats.txt`` file, or a
directory that has one stats file for each layer. With ``--stats``,
:mod:`.stats` changes the access counts of each level into activity rows
(manual §3.3):

* reads -> ``read``
* fills + updates -> ``write``
* Computes -> ``op``, in the ``hold_b`` stim_mode (weight-stationary)

Without ``--stats``, the run is a vectorless run and has the label VECTORLESS.
Each component gets 25 % of the random switching activity. A run with
``-d native.yaml`` and no ``-l`` does the same.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from npuwattch.arch_synth import EmittedArch
from ..compounds import Compound, CompoundBundleError, resolve_action, resolve_compound
from ..registry import HarnessError
from ..run_inputs import (
    attach_user_components,
    find_definition,
    load_run_bundle,
    load_user_library,
)
from ..vocabulary import positive_int
from .dram import select_table, warn_if_unused
from npuwattch.naming import CANONICAL, NamingError, validate_attributes
from .vocabulary import (
    VOCABULARY,
    attributes_for,
    primitive_for,
    reclassify_regfile_as_sram,
)

__all__ = ["DEFINITIONS_DIR", "ingest", "description_from_accelergy"]

#: Projection action name -> the activity event of the Timeloop stats.
_ACTION_EVENT = {"read": "read", "write": "write", "compute": "op"}

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"

def ingest(inputs: Mapping[str, Path], tech: Any, **opts: Any) -> EmittedArch:
    """Entry point of the harness. Return an ``EmittedArch``.

    ``inputs`` is ``{"arch": <architecture.yaml>, "stats"?: <path>,
    "stats_map"?: <yaml>, "energy_table"?: <yml>, "compound_components"?,
    "projection"?, "user_components"?}``.

    The last three are the definition files of the design. The default of
    each is the file with the fixed name in the directory of the architecture
    file (``npuwattch_harness.run_inputs``).
    """
    arch_path = Path(inputs["arch"])
    run_dir = arch_path.resolve().parent
    energy_table = select_table(inputs.get("energy_table"))
    compounds_path = find_definition(inputs, "compound_components", run_dir)
    bundle = load_run_bundle(compounds_path,
                             find_definition(inputs, "projection", run_dir))
    library_path = find_definition(inputs, "user_components", run_dir)
    library = load_user_library(library_path)

    compound_instances: Dict[str, Tuple[str, Dict[str, int]]] = {}
    description, warnings, notes = description_from_accelergy(
        arch_path, tech, default_clock_mhz=opts.get("default_clock_mhz"),
        verbose=int(opts.get("verbose", 0)),
        node_explicit=bool(opts.get("node_explicit", False)),
        energy_table=energy_table, user_components=library,
        compounds=bundle.compounds, compound_instances=compound_instances)
    warn_if_unused(description, energy_table, warnings)
    attach_user_components(description, library, library_path, notes)
    used_compounds = {cls for cls, _ in compound_instances.values()}
    notes.extend(
        f"compound component {name!r} ({compounds_path.name}): parsed, but "
        f"not used"
        for name in bundle.compounds if name not in used_compounds)
    compound_bindings = _compound_bindings(bundle, compound_instances)

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
                map_path=inputs.get("stats_map"),
                compound_bindings=compound_bindings))
        warnings.extend(s_warnings)
        notes.extend(s_notes)
        vectorless: Optional[float] = None
    else:
        from npuwattch.energy.vectorless import (
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
    except Exception as e:                      # The view is optional. Continue.
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


def _expand_compound(compound: Compound, name: str, entry: Any,
                     components: List[Dict[str, Any]],
                     warnings: List[str]) -> Dict[str, int]:
    """Add one description component for each element of a compound.

    ``entry`` is the Accelergy component. Its integer attributes are the
    symbols of the config expressions of the compound. Return the symbols.

    A compound that cannot be resolved is a definition error, thus the
    function raises :class:`HarnessError`.
    """
    symbols: Dict[str, int] = {}
    for key, value in (entry.attributes or {}).items():
        number = positive_int(value)
        if number is not None and not isinstance(value, bool):
            symbols[str(key).strip().replace("-", "_").lower()] = number
    try:
        resolved = resolve_compound(compound, None, symbols)
        for element, rel in resolved.items():
            attrs = {k: v for k, v in (rel.config or {}).items()
                     if v is not None}
            component = f"{name}.{element}"
            # A name that is not a symbol stays a string. For a numeric
            # attribute that is an expression that has no value.
            for key, value in attrs.items():
                if (isinstance(value, str) and key in CANONICAL
                        and CANONICAL[key].kind in ("int", "float")):
                    raise CompoundBundleError(
                        f"element {element!r}: {key} = {value!r} has no "
                        f"value; the Accelergy component does not declare "
                        f"that attribute as an integer")
            warnings.extend(validate_attributes(rel.primitive, attrs,
                                                component=component))
            components.append({
                "name": component,
                "class": rel.primitive,
                "count": int(entry.instance_count) * int(rel.count),
                "attributes": attrs,
            })
    except (CompoundBundleError, NamingError) as e:
        raise HarnessError(
            f"{name}: compound component {compound.name!r}: {e} (the "
            f"symbols of this component are: "
            f"{', '.join(sorted(symbols)) or 'none'})") from e
    return symbols


def _compound_bindings(
    bundle: Any, compound_instances: Mapping[str, Tuple[str, Dict[str, int]]],
) -> Dict[str, Dict[str, List[Tuple[str, str, int]]]]:
    """Return the activity bindings of the compound components of a design.

    The result is ``component -> event -> [(element component, stim_mode,
    scale)]``. The stats reader uses it to send the events of a compound
    component to its elements. The projection of the run gives the elements
    and the stim_mode of each event (``read``, ``write``, ``compute``).
    """
    projection = bundle.projections.get("timeloop")
    if projection is None:
        raise HarnessError(
            f"the projection of a Timeloop run must declare `tool: timeloop` "
            f"(found: {', '.join(sorted(bundle.projections)) or 'none'})")
    for cname, actions in projection.compounds.items():
        unknown = sorted(set(actions) - set(_ACTION_EVENT))
        if unknown:
            raise HarnessError(
                f"projection: compound {cname!r} has action(s) "
                f"{', '.join(unknown)}; the Timeloop events are "
                f"{', '.join(_ACTION_EVENT)}")
    bindings: Dict[str, Dict[str, List[Tuple[str, str, int]]]] = {}
    for name, (cname, symbols) in compound_instances.items():
        per_event: Dict[str, List[Tuple[str, str, int]]] = {}
        for action in projection.compounds.get(cname, {}):
            try:
                resolved = resolve_action(
                    projection, bundle.compounds[cname], action, None,
                    bundle.primitive_modes, extra_symbols=symbols)
            except CompoundBundleError as e:
                raise HarnessError(f"{name}: projection {cname}.{action}: {e}") from e
            per_event[_ACTION_EVENT[action]] = [
                (f"{name}.{el.element}", el.stim_mode, resolved.scale)
                for el in resolved.elements]
        bindings[name] = per_event
    return bindings


def description_from_accelergy(
    arch_path: Path,
    tech: Any,
    *,
    default_clock_mhz: Optional[float] = None,
    verbose: int = 0,
    node_explicit: bool = False,
    energy_table: Optional[Any] = None,
    user_components: Optional[Mapping[str, Any]] = None,
    compounds: Optional[Mapping[str, Compound]] = None,
    compound_instances: Optional[Dict[str, Tuple[str, Dict[str, int]]]] = None,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Accelergy v0.4 architecture file -> ``({"npuwattch": ...}, warnings, notes)``.

    The flattener resolves the hierarchy, the spatial fanout, and the attribute
    inheritance. Thus each flattened entry is one physical component. It has a
    full dotted name and an instance count.

    This function translates the names: class -> primitive, and Accelergy
    attributes -> NPUWattch names.

    ``energy_table`` is the ``EnergyTable`` of ``--energy-table``, or ``None``.
    It gives the energy constants of each DRAM component.

    The function finds the model of an Accelergy class in this order:

    1. ``compounds``: a compound component with the name of the class. The
       component becomes one description component for each element,
       ``<name>.<element>``. If ``compound_instances`` is given, the function
       records ``name -> (compound name, expression symbols)`` in it.
    2. The vocabulary table: one class -> one primitive.
    3. ``user_components``: the user component library entry with the name of
       the class.

    A component whose class is in none of these is not in the description,
    and the run gives a warning.
    """
    from npuwattch.npuwattch_db import build_database_from_dict
    from .accelergy_flattener import AccelergyV04Flattener

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
        # Record the `technology` attribute of the component as a node name
        # (for example, "45nm").
        for key, value in (entry.attributes or {}).items():
            if str(key).strip().lower() == "technology":
                text = str(value).strip().lower().replace(" ", "")
                declared_nodes.add(text if text.endswith("nm") else f"{text}nm")
                break
        class_name = str(entry.comp_class or "").strip().lower()
        if class_name in (compounds or {}):
            symbols = _expand_compound(
                compounds[class_name], name, entry, components, warnings)
            if compound_instances is not None:
                compound_instances[name] = (class_name, symbols)
            notes.append(
                f"{name}: class {entry.comp_class!r} is the compound "
                f"component {class_name!r} "
                f"({', '.join(compounds[class_name].elements)})")
            continue
        primitive = primitive_for(entry.comp_class, entry.subclass,
                                  entry.attributes)
        if primitive is None:
            user_class = class_name
            if user_class in (user_components or {}):
                # A user component has no attributes. Its cost is in the
                # user component library.
                components.append({
                    "name": name, "class": user_class,
                    "count": int(entry.instance_count), "attributes": {}})
                notes.append(
                    f"{name}: class {entry.comp_class!r} uses the user "
                    f"component library entry {user_class!r}")
            else:
                unmapped.append(f"{name} (class {entry.comp_class!r})")
            continue

        attrs = attributes_for(primitive, entry.attributes, component=name,
                               warnings=warnings, notes=notes,
                               energy_table=energy_table)

        if primitive == "regfile" and reclassify_regfile_as_sram(attrs):
            primitive = "sram"
            notes.append(
                f"{name}: declared a regfile but holds more than "
                f"32 Kib — modeled with the SRAM estimator")

        # Check the names. One incorrect component must not stop a large
        # description. It is not in the description and the run gives a
        # warning.
        try:
            warnings.extend(validate_attributes(primitive, attrs,
                                                component=name))
        except NamingError as e:
            warnings.append(
                f"{name}: {e} — NOT modeled: its energy and area are NOT "
                f"included in these results")
            continue
        components.append({
            "name": name,
            "class": primitive,
            "count": int(entry.instance_count),
            "attributes": attrs,
        })

    if unmapped:
        warnings.append(
            f"{len(unmapped)} component(s) have no NPUWattch primitive and are "
            f"NOT modeled (their energy and area are NOT included in these "
            f"results): {', '.join(sorted(unmapped))} — to include one, "
            f"define its class as a compound component "
            f"(--compound-components) or add it to the user component "
            f"library (--user-components)")
    if not components:
        raise ValueError(
            f"{arch_path}: no enabled components found — is this an Accelergy "
            f"v0.4 architecture description?")

    # A description has one technology block. Accelergy declares the node for
    # each component. The run uses the node of the CLI, not the node in the
    # file. If the two nodes are different, tell the user:
    # - With an explicit --node, the user selected the node. This is usual,
    #   because `technology:` in a Timeloop file is only for the Accelergy
    #   tables. The message is a note.
    # - With the default node (7nm), the message is a warning.
    foreign = sorted(n for n in declared_nodes if n != str(tech.node).lower())
    if foreign:
        msg = (f"the description declares technology {', '.join(foreign)} but "
               f"the run is evaluated at {tech.node} (--node"
               f"{'' if node_explicit else ' default'}); NPUWattch models the "
               f"node it is told to")
        (notes if node_explicit else warnings).append(msg)

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


def _clock_mhz(flattener: Any, tech: Any,
               default_clock_mhz: Optional[float]) -> Tuple[float, Optional[str]]:
    """Return the clock frequency in MHz and an optional note.

    Priority: ``--clock-mhz`` > the Accelergy file > the CLI default.

    An Accelergy file can declare the clock at the top level in two forms: a
    frequency in MHz (``clockrate``) or the Timeloop cycle time in seconds
    (``global_cycle_seconds``). ``VOCABULARY.description`` lists the accepted
    spellings.
    """
    declared = getattr(flattener, "top_level_attributes", None) or {}
    lowered = {str(k).strip().replace("-", "_").lower(): v
               for k, v in declared.items()}

    from_desc: Optional[float] = None
    for key in VOCABULARY.description["clock_mhz"]:
        if lowered.get(key) is not None:
            try:
                from_desc = float(lowered[key])
            except (TypeError, ValueError):
                from_desc = None
            break
    if from_desc is None:
        for key in VOCABULARY.description["cycle_seconds"]:
            value = lowered.get(key)
            if value:
                try:
                    from_desc = 1.0e-6 / float(value)   # s/cycle -> MHz
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
