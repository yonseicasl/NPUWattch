"""Load and check compounds and projections (JSON or YAML).

The schema is in docs/COMPOUND_SCHEMA.md. There are three file types:

    primitive_modes.{json,yaml}    the stim_mode names of each primitive (= POWER_MODES)
    compounds/<name>.{json,yaml}   the elements of a compound
    projections/<tool>.{json,yaml} simulator action -> {element: stim_mode}, count, scale

A compound does not use simulator action names. Only a projection uses them.

This module does three tasks:

- It loads the files.
- It does the static checks of schema §5.
- It resolves a compound and a projection for one kernel with a ``MacConfig``.
  Resolution replaces the placeholders and the symbols with a primitive, a
  config, and counts.

The engine and the definition files are separate:

- This package (``compounds/``) is the engine: the loader, the checks, and
  the resolution. It also has the stim_mode table,
  ``compounds/data/primitive_modes.json``. This table agrees with the
  characterized ``POWER_MODES`` and the trained models. Do not edit it.
- The definition files of a design are inputs of a run: its compound
  components and its projection, in JSON or YAML. You can read, copy, and
  edit these files. Examples are in ``tutorial/pytorchsim/<design>/`` and
  ``tutorial/timeloop/<design>/``. ``npuwattch_harness.run_inputs`` finds and loads
  the files of a run.
"""

from __future__ import annotations

from npuwattch.diagnostics import NPUWattchError
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union

import yaml

__all__ = [
    "DATA_DIR",
    "MAC_PRIMITIVES",
    "CompoundBundleError",
    "PrimitiveModes",
    "CompoundElement",
    "Compound",
    "CountFrom",
    "ActionMapping",
    "Projection",
    "ResolvedElement",
    "ResolvedActionElement",
    "ActionResolution",
    "Bundle",
    "load_primitive_modes",
    "load_compounds",
    "load_compounds_dir",
    "load_projection",
    "validate_projection",
    "resolve_compound",
    "resolve_action",
]

DATA_DIR = Path(__file__).resolve().parent / "data"

# The primitives that the placeholder {mac_primitive} of the systolic PE can resolve to.
MAC_PRIMITIVES = ("intmac", "fpmac", "mxfpmac")

# Symbols in count, scale, and config expressions resolve for each kernel.
# The sources are the MAC scalars (lanes, bitwidth) and the integer run-config
# keys of the harness. A bundle belongs to one harness, thus its compounds can
# use the config keys of that harness.
# Thus the check at load time is only a syntax check: each token must have the
# form of an identifier. An unknown symbol causes an error at resolution.
_MAC_SYMBOLS = ("lanes", "bitwidth")
_SYMBOL_RE = __import__("re").compile(r"[A-Za-z_]\w*$")


class CompoundBundleError(NPUWattchError, ValueError):
    """A compound, projection, or stim_mode file is malformed or inconsistent."""


# Bundle files can be JSON or YAML. The file extension selects the parser.
# For an unknown extension, the loader tries JSON first and then YAML.
_STRUCTURED_SUFFIXES = (".json", ".yaml", ".yml")


def _read_structured(path: Path, what: str) -> object:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise CompoundBundleError.nw(5301, what=what, path=p) from e
    suffix = p.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            obj = yaml.safe_load(text)
        elif suffix == ".json":
            obj = json.loads(text)
        else:  # unknown extension: try JSON, then YAML
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                obj = yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise CompoundBundleError.nw(5302, what=what, error=e) from e
    if obj is None:
        raise CompoundBundleError.nw(5303, what=what, path=p)
    return obj


def _strip_comments(d: Mapping) -> Dict:
    """Remove the comment keys (keys that start with ``_``) from a mapping."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# scalar-expression resolution (lanes*lanes, bitwidth, 1, ...)
# ---------------------------------------------------------------------------

def _is_placeholder(v: object) -> bool:
    return isinstance(v, str) and v.startswith("{") and v.endswith("}")


def _check_scalar_expr(expr: object, where: str) -> None:
    """Check the syntax only: an int, or symbols and int literals joined by + and *."""
    if isinstance(expr, bool) or not isinstance(expr, (int, str)):
        raise CompoundBundleError.nw(5304, where=where, expr=expr)
    if isinstance(expr, int):
        return
    for term in expr.split("+"):
        for factor in term.split("*"):
            f = factor.strip()
            if f.isdigit() or _SYMBOL_RE.match(f):
                continue
            raise CompoundBundleError.nw(
                5305, where=where, token=f, expr=expr,
                mac_symbols=", ".join(_MAC_SYMBOLS))


def _resolve_scalar_expr(expr: Union[int, str], symbols: Mapping[str, int], where: str) -> int:
    if isinstance(expr, bool):
        raise CompoundBundleError.nw(5306, where=where)
    if isinstance(expr, int):
        return expr
    total = 0
    for term in expr.split("+"):
        prod = 1
        for factor in term.split("*"):
            f = factor.strip()
            if f in symbols:
                prod *= symbols[f]
            elif f.isdigit():
                prod *= int(f)
            else:
                raise CompoundBundleError.nw(5307, where=where, symbol=f, expr=expr)
        total += prod
    return total


# ---------------------------------------------------------------------------
# primitive_modes.json: the stim_mode table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrimitiveModes:
    """The characterized stim_mode names: primitive -> permitted modes.

    This table makes sure that a projection uses only modes that the dataset
    has. An estimator can predict only the modes of its training data.
    """

    modes: Mapping[str, List[str]]

    def primitives(self) -> List[str]:
        return sorted(self.modes)

    def modes_of(self, primitive: str) -> List[str]:
        if primitive not in self.modes:
            raise CompoundBundleError.nw(5308, primitive=primitive)
        return list(self.modes[primitive])

    def is_valid(self, primitive: str, mode: str) -> bool:
        return mode in self.modes.get(primitive, ())

    def require(self, primitive: str, mode: str) -> None:
        """Raise an error if ``(primitive, mode)`` is not a characterized pair."""
        if primitive not in self.modes:
            raise CompoundBundleError.nw(
                5309, primitive=primitive,
                primitives=", ".join(self.primitives()))
        if mode not in self.modes[primitive]:
            raise CompoundBundleError.nw(
                5310, mode=mode, primitive=primitive,
                allowed=", ".join(self.modes[primitive]))


def load_primitive_modes(path: Optional[Path] = None) -> PrimitiveModes:
    """Load the stim_mode table (JSON or YAML). The default is the table of this package."""
    p = Path(path) if path is not None else DATA_DIR / "primitive_modes.json"
    obj = _read_structured(p, "primitive_modes")
    if not isinstance(obj, dict):
        raise CompoundBundleError.nw(5311)
    modes = obj.get("modes", obj)  # accept {"modes": {...}} or a bare map
    if not isinstance(modes, dict) or not modes:
        raise CompoundBundleError.nw(5312)
    out: Dict[str, List[str]] = {}
    for prim, lst in modes.items():
        if prim.startswith("_"):  # comment keys
            continue
        if not isinstance(lst, list) or not lst:
            raise CompoundBundleError.nw(5313, primitive=prim)
        if not all(isinstance(m, str) and m for m in lst):
            raise CompoundBundleError.nw(5314, primitive=prim)
        if len(set(lst)) != len(lst):
            raise CompoundBundleError.nw(5315, primitive=prim)
        if "random" not in lst:
            raise CompoundBundleError.nw(5316, primitive=prim)
        out[prim] = list(lst)
    return PrimitiveModes(modes=out)


# ---------------------------------------------------------------------------
# compounds/<name>.json: the elements of a compound
# ---------------------------------------------------------------------------

#: Values of CompoundElement.per. The emitter multiplies the count of an
#: element by the number of arrays or cores of the run. "chip" has no multiplier.
ELEMENT_PER = ("array", "core", "chip")

#: Values of Compound.default_mode. It sets the charge for the elements that
#: an action does not name.
#: "idle": each such element is charged one idle (cycle-domain compounds).
#: "gated": such elements are not charged. This is for bank-gated or
#: clock-gated memories. The leakage term includes them.
DEFAULT_MODES = ("idle", "gated")


@dataclass(frozen=True)
class CompoundElement:
    name: str
    primitive: str                       # a primitive name or "{mac_primitive}"
    config: object                       # "{mac_config}", a dict, or a literal
    count: Union[int, str]               # e.g. "lanes*lanes"
    per: str = "array"                   # multiplier of the instance count

    @property
    def primitive_is_template(self) -> bool:
        return _is_placeholder(self.primitive)


@dataclass(frozen=True)
class Compound:
    name: str
    select_primitive_by: Optional[str]
    elements: Dict[str, CompoundElement]
    default_mode: str = "idle"           # charge for elements not named: idle | gated


def _parse_compound(name: str, obj: Mapping) -> Compound:
    els_obj = obj.get("elements")
    if not isinstance(els_obj, dict) or not els_obj:
        raise CompoundBundleError.nw(5317, compound=name)
    elements: Dict[str, CompoundElement] = {}
    for ename, espec in els_obj.items():
        if not isinstance(espec, dict) or "primitive" not in espec:
            raise CompoundBundleError.nw(5318, compound=name, element=ename)
        if not isinstance(espec["primitive"], str):
            raise CompoundBundleError.nw(
                5319, compound=name, element=ename,
                type_name=type(espec["primitive"]).__name__)
        count = espec.get("count", 1)
        _check_scalar_expr(count, f"compound {name!r} element {ename!r} count")
        per = espec.get("per", "array")
        if per not in ELEMENT_PER:
            raise CompoundBundleError.nw(5320, compound=name, element=ename,
                                         choices=ELEMENT_PER, per=per)
        elements[ename] = CompoundElement(
            name=ename,
            primitive=espec["primitive"],
            config=espec.get("config"),
            count=count,
            per=per,
        )
    default_mode = obj.get("default_mode", "idle")
    if default_mode not in DEFAULT_MODES:
        raise CompoundBundleError.nw(5321, compound=name, choices=DEFAULT_MODES,
                                     default_mode=default_mode)
    return Compound(
        name=name,
        select_primitive_by=obj.get("select_primitive_by"),
        elements=elements,
        default_mode=default_mode,
    )


def load_compounds(path: Path) -> Dict[str, Compound]:
    """Load one compounds file (JSON or YAML).

    One file can declare more than one compound.
    """
    obj = _read_structured(Path(path), "compounds file")
    if not isinstance(obj, dict):
        raise CompoundBundleError.nw(5322)
    out: Dict[str, Compound] = {}
    for name, spec in _strip_comments(obj).items():
        if not isinstance(spec, dict):
            raise CompoundBundleError.nw(5323, compound=name)
        out[name] = _parse_compound(name, spec)
    if not out:
        raise CompoundBundleError.nw(5324)
    return out


# ---------------------------------------------------------------------------
# projections/<tool>.json: simulator action -> stim_mode of each element
# ---------------------------------------------------------------------------

#: How a count_from stat becomes charge events for the target elements:
#:
#: - "words": the raw count x scale.
#: - "bytes": the count / the word bytes of the element.
#: - "vectors": the count x lanes x operand bits / the word bits of the element.
#: - "flits": a NoC flit count. The conversion depends on the element type:
#:   buffer word accesses, crossbar cycles normalized by the valid fraction,
#:   or link crossings.
#:
#: "bytes" and "vectors" apply only to capacity-resolved memory elements.
#: "flits" applies to those elements and also to crossbar and d2dlink elements.
#: The emitter knows the word widths, the port counts, and the flit size (§3.9).
COUNT_UNITS = ("words", "bytes", "vectors", "flits")


@dataclass(frozen=True)
class CountFrom:
    stat: str
    scale: Union[int, str]
    unit: str = "words"


@dataclass(frozen=True)
class ActionMapping:
    action: str
    count_from: CountFrom
    elements: Dict[str, str]             # element name -> stim_mode


@dataclass(frozen=True)
class Projection:
    tool: str
    # compound name -> action name -> ActionMapping
    compounds: Dict[str, Dict[str, ActionMapping]]
    #: stat name -> one-line reason. These are waivers of the coverage warning,
    #: with the same meaning as in a lint or CDC waiver file. The reader
    #: collects the stat, but the projection does not charge it. The coverage
    #: check of the emitter shows these stats as notes (INFO), not as warnings.
    #: A coverage warning then means that a stat has no mapping and is
    #: possibly forgotten.
    waivers: Dict[str, str] = field(default_factory=dict)
    #: Declarations of hardware that is outside the model scope. The harness
    #: readers do not collect its activity, thus there is no stat to waive.
    #: Each run shows these declarations one time as notes (INFO).
    out_of_scope: List[str] = field(default_factory=list)
    #: Planned integrations of third-party tools (calls to an external power
    #: model) that are not implemented. These are temporary gaps, and
    #: ``out_of_scope`` entries are permanent. Thus each entry gives a warning
    #: in each run. Delete the entry when the integration is complete.
    third_party_pending: List[str] = field(default_factory=list)


def _parse_action(compound: str, action: str, obj: Mapping) -> ActionMapping:
    cf = obj.get("count_from")
    if not isinstance(cf, dict) or "stat" not in cf:
        raise CompoundBundleError.nw(5325, compound=compound, action=action)
    stat = cf["stat"]
    if not isinstance(stat, str) or not stat:
        raise CompoundBundleError.nw(5326, compound=compound, action=action)
    scale = cf.get("scale", 1)
    _check_scalar_expr(scale, f"projection {compound}.{action} count_from.scale")
    unit = cf.get("unit", "words")
    if unit not in COUNT_UNITS:
        raise CompoundBundleError.nw(5327, compound=compound, action=action,
                                     choices=COUNT_UNITS, unit=unit)
    els = obj.get("elements")
    if not isinstance(els, dict) or not els:
        raise CompoundBundleError.nw(5328, compound=compound, action=action)
    for k, v in els.items():
        if not isinstance(v, str) or not v:
            raise CompoundBundleError.nw(5329, compound=compound, action=action,
                                         element=k)
    return ActionMapping(action=action, count_from=CountFrom(stat, scale, unit),
                         elements=dict(els))


def load_projection(path: Path) -> Projection:
    obj = _read_structured(Path(path), "projection file")
    if not isinstance(obj, dict) or "tool" not in obj:
        raise CompoundBundleError.nw(5330)
    compounds_obj = obj.get("compounds")
    if not isinstance(compounds_obj, dict) or not compounds_obj:
        raise CompoundBundleError.nw(5331)
    compounds: Dict[str, Dict[str, ActionMapping]] = {}
    for cname, actions in _strip_comments(compounds_obj).items():
        if not isinstance(actions, dict):
            raise CompoundBundleError.nw(5332, compound=cname)
        parsed: Dict[str, ActionMapping] = {}
        for aname, aspec in _strip_comments(actions).items():
            if not isinstance(aspec, dict):
                raise CompoundBundleError.nw(5333, compound=cname, action=aname)
            parsed[aname] = _parse_action(cname, aname, aspec)
        compounds[cname] = parsed

    # An old key name causes an error with a hint. The loader does not accept
    # it as an alias. The NPUWattch attribute names use the same policy.
    for legacy, current in (("ignores", "waivers"), ("notes", "out_of_scope")):
        if legacy in obj:
            raise CompoundBundleError.nw(5334, legacy=legacy, current=current)

    waivers_obj = obj.get("waivers") or {}
    if not isinstance(waivers_obj, dict):
        raise CompoundBundleError.nw(5335)
    waivers: Dict[str, str] = {}
    for stat, justification in _strip_comments(waivers_obj).items():
        if not isinstance(justification, str) or not justification.strip():
            raise CompoundBundleError.nw(5336, stat=stat)
        waivers[stat] = " ".join(justification.split())
    # A stat that is charged and also waived is an error in the definition file.
    for cname, actions in compounds.items():
        for aname, mapping in actions.items():
            if mapping.count_from.stat in waivers:
                raise CompoundBundleError.nw(
                    5337, compound=cname, action=aname,
                    stat=mapping.count_from.stat)

    def _string_list(key: str) -> List[str]:
        raw = obj.get(key) or []
        if not isinstance(raw, list) or any(
                not isinstance(n, str) or not n.strip() for n in raw):
            raise CompoundBundleError.nw(5338, key=key)
        return [" ".join(n.split()) for n in raw]

    return Projection(tool=obj["tool"], compounds=compounds,
                      waivers=waivers,
                      out_of_scope=_string_list("out_of_scope"),
                      third_party_pending=_string_list("third_party_pending"))


# ---------------------------------------------------------------------------
# static checks (schema §5): a MacConfig is not necessary
# ---------------------------------------------------------------------------

def validate_projection(
    projection: Projection,
    compounds: Mapping[str, Compound],
    primitive_modes: PrimitiveModes,
) -> None:
    """Do the checks of schema §5 that are possible before resolution.

    - Each compound that the projection refers to must exist.
    - Each element in the projection must exist in the compound.
    - For an element with a fixed primitive, ``(primitive, mode)`` must be
      characterized.
    - For the templated MAC PE, the mode must be valid for at least one MAC
      primitive. This check finds typing errors. The exact check occurs at
      resolution.
    """
    for cname, actions in projection.compounds.items():
        if cname not in compounds:
            raise CompoundBundleError.nw(5339, tool=projection.tool,
                                         compound=cname)
        compound = compounds[cname]
        for aname, mapping in actions.items():
            for ename, mode in mapping.elements.items():
                if ename not in compound.elements:
                    raise CompoundBundleError.nw(
                        5340, compound=cname, action=aname, element=ename,
                        elements=", ".join(compound.elements))
                el = compound.elements[ename]
                if el.primitive_is_template:
                    if not any(primitive_modes.is_valid(p, mode) for p in MAC_PRIMITIVES):
                        raise CompoundBundleError.nw(
                            5341, compound=cname, action=aname, mode=mode,
                            element=ename,
                            mac_primitives=", ".join(MAC_PRIMITIVES))
                else:
                    primitive_modes.require(el.primitive, mode)


# ---------------------------------------------------------------------------
# resolution for one kernel with a MacConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedElement:
    name: str
    primitive: str
    config: object
    count: int                           # number of instances (for area and leakage)
    per: str = "array"                   # multiplier of the instance count


@dataclass(frozen=True)
class ResolvedActionElement:
    element: str
    primitive: str
    config: object
    stim_mode: str


@dataclass(frozen=True)
class ActionResolution:
    """One simulator action, resolved for one kernel.

    It gives the stat that supplies the event count, the scale, and the
    (primitive, config, stim_mode) of each element.

    Energy of one window = stat_value(stat) * scale
                           * sum_element per_cycle_energy(primitive, config, stim_mode).

    The element ``count`` (for area and leakage) is in the resolved compound,
    not in this object. Energy uses count_from. Area and leakage use
    element.count. Do not multiply the two.
    """

    action: str
    stat: str
    scale: int
    unit: str = "words"
    elements: List[ResolvedActionElement] = field(default_factory=list)


def _symbols_for(mac_config,
                 extra_symbols: Optional[Mapping[str, int]] = None) -> Dict[str, int]:
    """Return the expression symbols.

    The symbols are the MAC scalars and the symbols that the harness supplies
    (integer run-config keys). A bundle belongs to one harness, thus its
    compounds can use the config keys of that harness. If two symbols have
    the same name, the MAC symbol has priority.

    ``mac_config`` can be ``None`` for a design that has no MAC configuration
    (a Timeloop run). Then there are no MAC symbols.
    """
    symbols = {k: int(v) for k, v in (extra_symbols or {}).items()
               if isinstance(v, int) and not isinstance(v, bool)}
    if mac_config is not None:
        symbols.update(
            {"lanes": int(mac_config.lanes),
             "bitwidth": int(mac_config.operand_dtype.bits)}
        )
    return symbols


def _resolve_element(
    compound_name: str, el: CompoundElement, mac_config,
    symbols: Mapping[str, int],
) -> ResolvedElement:
    where = f"compound {compound_name}.{el.name}.config"
    cfg = el.config
    if mac_config is None and (el.primitive_is_template
                               or cfg == "{mac_config}"):
        raise CompoundBundleError.nw(5342, compound=compound_name,
                                     element=el.name)
    primitive = mac_config.primitive if el.primitive_is_template else el.primitive
    if cfg == "{mac_config}":
        config: object = dict(mac_config.primitive_config)
    elif _is_placeholder(cfg):
        raise CompoundBundleError.nw(5343, where=where, placeholder=cfg)
    elif isinstance(cfg, dict):
        config = {}
        for k, v in cfg.items():
            if isinstance(v, bool):
                config[k] = v
            elif isinstance(v, int):
                config[k] = v
            elif (isinstance(v, str) and not _is_placeholder(v)
                  and all(f.strip().isdigit() or _SYMBOL_RE.match(f.strip())
                          for term in v.split("+") for f in term.split("*"))):
                # An identifier that is not a known symbol is a literal string
                # value (for example, an mxfpmac format name "fp8_e4m3").
                # An expression with operators must resolve fully. If not, it
                # causes an error.
                bare = v.strip()
                if ("+" not in v and "*" not in v
                        and not bare.isdigit() and bare not in symbols):
                    config[k] = v
                else:
                    config[k] = _resolve_scalar_expr(v, symbols, f"{where}.{k}")
            else:
                config[k] = v  # a string that is not an expression, a list, or None
    else:
        config = cfg
    count = _resolve_scalar_expr(
        el.count, symbols, f"compound {compound_name}.{el.name}.count"
    )
    return ResolvedElement(name=el.name, primitive=primitive, config=config,
                           count=count, per=el.per)


def resolve_compound(
    compound: Compound, mac_config,
    extra_symbols: Optional[Mapping[str, int]] = None,
) -> Dict[str, ResolvedElement]:
    """Resolve the placeholders and the symbols of a compound for one kernel.

    Return the table of resolved elements.
    """
    symbols = _symbols_for(mac_config, extra_symbols)
    return {
        ename: _resolve_element(compound.name, el, mac_config, symbols)
        for ename, el in compound.elements.items()
    }


def resolve_action(
    projection: Projection,
    compound: Compound,
    action: str,
    mac_config,
    primitive_modes: PrimitiveModes,
    extra_symbols: Optional[Mapping[str, int]] = None,
) -> ActionResolution:
    """Resolve one simulator action for one kernel.

    The function checks each stim_mode against the resolved primitive.

    If the ``elements`` map of the action does not name an element, the
    ``default_mode`` of the compound applies:

    - ``idle``: the element is charged one idle. This gives complete
      accounting for cycle-domain compounds (schema §5).
    - ``gated``: the element is not charged. This is for clock-gated
      memories. Their leakage is charged for the time, not for each event.

    If the resolved primitive does not have the mode (for example ``mxfpmac``
    with ``hold_b``), the function raises an error. It does not charge an
    incorrect mode.
    """
    actions = projection.compounds.get(compound.name)
    if actions is None or action not in actions:
        raise CompoundBundleError.nw(5344, tool=projection.tool, action=action,
                                     compound=compound.name)
    mapping = actions[action]
    symbols = _symbols_for(mac_config, extra_symbols)
    scale = _resolve_scalar_expr(
        mapping.count_from.scale, symbols,
        f"projection {compound.name}.{action} count_from.scale",
    )

    out_elems: List[ResolvedActionElement] = []
    for ename, el in compound.elements.items():
        mode = mapping.elements.get(ename)
        if mode is None:
            if compound.default_mode == "gated":
                continue        # gated: not charged and not resolved
            mode = "idle"
        re = _resolve_element(compound.name, el, mac_config, symbols)
        primitive_modes.require(re.primitive, mode)
        out_elems.append(
            ResolvedActionElement(
                element=ename, primitive=re.primitive, config=re.config, stim_mode=mode
            )
        )
    return ActionResolution(
        action=action, stat=mapping.count_from.stat, scale=scale,
        unit=mapping.count_from.unit, elements=out_elems,
    )


# ---------------------------------------------------------------------------
# bundle loading (the definitions directory of a harness)
# ---------------------------------------------------------------------------
#
# A bundle is a directory that a harness or a user writes:
#
#     <root>/compounds/<name>.{json,yaml}       the compounds of this harness
#     <root>/projections/<tool>.{json,yaml}     simulator action -> stim_mode maps
#     <root>/primitive_modes.{json,yaml}        (optional) replaces the stim_mode table
#
# The default stim_mode table (``primitive_modes``) is in ``compounds/data/``
# of this package. A bundle replaces it only if the bundle has its own file.
# That is necessary only if the bundle author characterized new modes.

def _structured_files(directory: Path) -> List[Path]:
    """Return the ``*.json``, ``*.yaml``, and ``*.yml`` files of a directory, sorted.

    Two files with the same stem (for example a ``.json`` and a ``.yaml``)
    cause an error.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    files: List[Path] = []
    for suf in _STRUCTURED_SUFFIXES:
        files.extend(directory.glob(f"*{suf}"))
    seen: Dict[str, Path] = {}
    for p in sorted(files):
        if p.stem in seen:
            raise CompoundBundleError.nw(5345, stem=p.stem, directory=directory,
                                         first=seen[p.stem].name,
                                         second=p.name)
        seen[p.stem] = p
    return [seen[k] for k in sorted(seen)]


def load_compounds_dir(directory: Path) -> Dict[str, Compound]:
    """Load all compounds files (JSON or YAML) in a directory."""
    out: Dict[str, Compound] = {}
    for p in _structured_files(directory):
        out.update(load_compounds(p))
    return out


@dataclass(frozen=True)
class Bundle:
    """The definitions of one harness: its compounds, its projections, and the stim_mode table."""

    compounds: Dict[str, Compound]
    projections: Dict[str, Projection]
    primitive_modes: PrimitiveModes

    def validate(self) -> None:
        """Check each projection against the compounds and the stim_mode table."""
        for proj in self.projections.values():
            validate_projection(proj, self.compounds, self.primitive_modes)

    def compound(self, name: str) -> Compound:
        if name not in self.compounds:
            raise CompoundBundleError.nw(
                5346, compound=name,
                available=", ".join(sorted(self.compounds)))
        return self.compounds[name]

    def projection(self, tool: str) -> Projection:
        if tool not in self.projections:
            raise CompoundBundleError.nw(
                5347, tool=tool,
                available=", ".join(sorted(self.projections)))
        return self.projections[tool]
