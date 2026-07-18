"""Load + validate the compound / projection contract (JSON **or** YAML).

Three artifacts (docs/COMPOUND_SCHEMA.md), nothing tool-specific leaks into a
compound:

    primitive_modes.{json,yaml}    the per-primitive stim_mode vocabulary (= POWER_MODES)
    compounds/<name>.{json,yaml}   a compound's ELEMENTS (tool-agnostic composition)
    projections/<tool>.{json,yaml} native action -> {element: stim_mode} + count/scale

This module implements the loaders, the static validation the schema §5
requires, and per-kernel *resolution* of a compound + projection against a
concrete ``MacConfig`` (placeholders/symbols -> concrete primitive, config,
counts).

System vs harness-definition files are kept apart:

- This package (``compounds/``) is the **interpretation system**: the loader,
  validation and resolution engine, plus the stim_mode vocabulary **contract**
  (``compounds/data/primitive_modes.json``) — tied to the characterized
  ``POWER_MODES`` and the trained models, not meant to be edited.
- Each **harness** ships its own **definition bundle** (the compounds it models +
  its projection), authored in JSON or YAML and meant to be read/copied/edited:
  e.g. ``harness/pytorchsim/definitions/{compounds,projections}/``. Users point
  ``load_bundle`` / ``load_compounds`` / ``load_projection`` at their own files.
"""

from __future__ import annotations

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
    "load_bundle",
    "validate_projection",
    "resolve_compound",
    "resolve_action",
]

DATA_DIR = Path(__file__).resolve().parent / "data"

# The primitives the systolic PE placeholder {mac_primitive} can resolve to.
MAC_PRIMITIVES = ("intmac", "fpmac", "mxfpmac")

# Symbols permitted in count/scale/config expressions, resolved per kernel.
_ALLOWED_SYMBOLS = ("lanes", "bitwidth")


class CompoundBundleError(ValueError):
    """A compound/projection/vocabulary artifact is malformed or inconsistent."""


# Bundle files may be JSON or YAML (YAML is a superset, so a .json file also
# parses as YAML; we dispatch on extension and fall back for unknown suffixes).
_STRUCTURED_SUFFIXES = (".json", ".yaml", ".yml")


def _read_structured(path: Path, what: str) -> object:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise CompoundBundleError(f"{what} not found: {p}") from e
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
        raise CompoundBundleError(f"{what} is not valid JSON/YAML: {e}") from e
    if obj is None:
        raise CompoundBundleError(f"{what} is empty: {p}")
    return obj


def _strip_comments(d: Mapping) -> Dict:
    """Drop ``_``-prefixed comment keys from a JSON object."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# scalar-expression resolution (lanes*lanes, bitwidth, 1, ...)
# ---------------------------------------------------------------------------

def _is_placeholder(v: object) -> bool:
    return isinstance(v, str) and v.startswith("{") and v.endswith("}")


def _is_scalar_expr(s: str) -> bool:
    """True if every factor is a digit or an allowed symbol (so it is resolvable)."""
    for term in s.split("+"):
        for factor in term.split("*"):
            f = factor.strip()
            if not (f.isdigit() or f in _ALLOWED_SYMBOLS):
                return False
    return True


def _check_scalar_expr(expr: object, where: str) -> None:
    """Syntactic check (no values): int, or +/*-joined symbols/int literals."""
    if isinstance(expr, bool) or not isinstance(expr, (int, str)):
        raise CompoundBundleError(f"{where}: scalar must be int or expr string, got {expr!r}")
    if isinstance(expr, int):
        return
    for term in expr.split("+"):
        for factor in term.split("*"):
            f = factor.strip()
            if f in _ALLOWED_SYMBOLS or f.isdigit():
                continue
            raise CompoundBundleError(
                f"{where}: unresolved token {f!r} in {expr!r} "
                f"(allowed symbols: {', '.join(_ALLOWED_SYMBOLS)})"
            )


def _resolve_scalar_expr(expr: Union[int, str], symbols: Mapping[str, int], where: str) -> int:
    if isinstance(expr, bool):
        raise CompoundBundleError(f"{where}: bool is not a scalar")
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
                raise CompoundBundleError(f"{where}: unresolved symbol {f!r} in {expr!r}")
        total += prod
    return total


# ---------------------------------------------------------------------------
# primitive_modes.json — the stim_mode vocabulary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrimitiveModes:
    """The characterized stim_mode vocabulary: primitive -> allowed modes.

    This is the guard that a projection never asks for a power the dataset can't
    measure — an estimator only predicts modes it was trained on.
    """

    modes: Mapping[str, List[str]]

    def primitives(self) -> List[str]:
        return sorted(self.modes)

    def modes_of(self, primitive: str) -> List[str]:
        if primitive not in self.modes:
            raise CompoundBundleError(f"unknown primitive: {primitive!r}")
        return list(self.modes[primitive])

    def is_valid(self, primitive: str, mode: str) -> bool:
        return mode in self.modes.get(primitive, ())

    def require(self, primitive: str, mode: str) -> None:
        """Raise unless ``(primitive, mode)`` is a characterized pair."""
        if primitive not in self.modes:
            raise CompoundBundleError(
                f"primitive {primitive!r} not in vocabulary "
                f"({', '.join(self.primitives())})"
            )
        if mode not in self.modes[primitive]:
            raise CompoundBundleError(
                f"stim_mode {mode!r} not characterized for {primitive!r}; "
                f"allowed: {', '.join(self.modes[primitive])}"
            )


def _validate_modes_obj(obj: object) -> Dict[str, List[str]]:
    if not isinstance(obj, dict):
        raise CompoundBundleError("primitive_modes: top-level must be an object")
    modes = obj.get("modes", obj)  # allow either {"modes": {...}} or a bare map
    if not isinstance(modes, dict) or not modes:
        raise CompoundBundleError("primitive_modes: 'modes' must be a non-empty object")
    out: Dict[str, List[str]] = {}
    for prim, lst in modes.items():
        if prim.startswith("_"):  # comment keys
            continue
        if not isinstance(lst, list) or not lst:
            raise CompoundBundleError(
                f"primitive_modes[{prim!r}] must be a non-empty list of mode names"
            )
        if not all(isinstance(m, str) and m for m in lst):
            raise CompoundBundleError(
                f"primitive_modes[{prim!r}] must contain non-empty strings"
            )
        if len(set(lst)) != len(lst):
            raise CompoundBundleError(f"primitive_modes[{prim!r}] has duplicate modes")
        if "random" not in lst:
            raise CompoundBundleError(
                f"primitive_modes[{prim!r}] must include 'random' (the universal anchor)"
            )
        out[prim] = list(lst)
    return out


def load_primitive_modes(path: Optional[Path] = None) -> PrimitiveModes:
    """Load the stim_mode vocabulary (JSON/YAML; defaults to the shipped bundle)."""
    p = Path(path) if path is not None else DATA_DIR / "primitive_modes.json"
    return PrimitiveModes(modes=_validate_modes_obj(_read_structured(p, "primitive_modes")))


# ---------------------------------------------------------------------------
# compounds/<name>.json — tool-agnostic composition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompoundElement:
    name: str
    primitive: str                       # concrete or "{mac_primitive}"
    config: object                       # "{mac_config}" | dict | concrete
    count: Union[int, str]               # e.g. "lanes*lanes"

    @property
    def primitive_is_template(self) -> bool:
        return _is_placeholder(self.primitive)


@dataclass(frozen=True)
class Compound:
    name: str
    select_primitive_by: Optional[str]
    elements: Dict[str, CompoundElement]


def _parse_compound(name: str, obj: Mapping) -> Compound:
    els_obj = obj.get("elements")
    if not isinstance(els_obj, dict) or not els_obj:
        raise CompoundBundleError(f"compound {name!r}: 'elements' must be a non-empty object")
    elements: Dict[str, CompoundElement] = {}
    for ename, espec in els_obj.items():
        if not isinstance(espec, dict) or "primitive" not in espec:
            raise CompoundBundleError(
                f"compound {name!r} element {ename!r}: needs at least a 'primitive'"
            )
        if not isinstance(espec["primitive"], str):
            raise CompoundBundleError(
                f"compound {name!r} element {ename!r}: 'primitive' must be a string "
                f"(got {type(espec['primitive']).__name__}); if you wrote a placeholder "
                f"like {{mac_primitive}} in YAML, quote it: \"{{mac_primitive}}\""
            )
        count = espec.get("count", 1)
        _check_scalar_expr(count, f"compound {name!r} element {ename!r} count")
        elements[ename] = CompoundElement(
            name=ename,
            primitive=espec["primitive"],
            config=espec.get("config"),
            count=count,
        )
    return Compound(
        name=name,
        select_primitive_by=obj.get("select_primitive_by"),
        elements=elements,
    )


def load_compounds(path: Path) -> Dict[str, Compound]:
    """Load a compounds JSON file (one file may declare several compounds)."""
    obj = _read_structured(Path(path), "compounds file")
    if not isinstance(obj, dict):
        raise CompoundBundleError("compounds file: top-level must be an object")
    out: Dict[str, Compound] = {}
    for name, spec in _strip_comments(obj).items():
        if not isinstance(spec, dict):
            raise CompoundBundleError(f"compound {name!r}: must be an object")
        out[name] = _parse_compound(name, spec)
    if not out:
        raise CompoundBundleError("compounds file declares no compounds")
    return out


# ---------------------------------------------------------------------------
# projections/<tool>.json — native action -> element stim_mode
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CountFrom:
    stat: str
    scale: Union[int, str]


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


def _parse_action(compound: str, action: str, obj: Mapping) -> ActionMapping:
    cf = obj.get("count_from")
    if not isinstance(cf, dict) or "stat" not in cf:
        raise CompoundBundleError(
            f"projection {compound}.{action}: 'count_from' needs a 'stat'"
        )
    stat = cf["stat"]
    if not isinstance(stat, str) or not stat:
        raise CompoundBundleError(
            f"projection {compound}.{action}: count_from.stat must be a non-empty string"
        )
    scale = cf.get("scale", 1)
    _check_scalar_expr(scale, f"projection {compound}.{action} count_from.scale")
    els = obj.get("elements")
    if not isinstance(els, dict) or not els:
        raise CompoundBundleError(
            f"projection {compound}.{action}: 'elements' must be a non-empty object"
        )
    for k, v in els.items():
        if not isinstance(v, str) or not v:
            raise CompoundBundleError(
                f"projection {compound}.{action}.elements[{k!r}] must be a mode string"
            )
    return ActionMapping(action=action, count_from=CountFrom(stat, scale), elements=dict(els))


def load_projection(path: Path) -> Projection:
    obj = _read_structured(Path(path), "projection file")
    if not isinstance(obj, dict) or "tool" not in obj:
        raise CompoundBundleError("projection file: needs a top-level 'tool'")
    compounds_obj = obj.get("compounds")
    if not isinstance(compounds_obj, dict) or not compounds_obj:
        raise CompoundBundleError("projection file: 'compounds' must be a non-empty object")
    compounds: Dict[str, Dict[str, ActionMapping]] = {}
    for cname, actions in _strip_comments(compounds_obj).items():
        if not isinstance(actions, dict):
            raise CompoundBundleError(f"projection compound {cname!r}: must be an object")
        parsed: Dict[str, ActionMapping] = {}
        for aname, aspec in _strip_comments(actions).items():
            if not isinstance(aspec, dict):
                raise CompoundBundleError(
                    f"projection {cname}.{aname}: must be an object"
                )
            parsed[aname] = _parse_action(cname, aname, aspec)
        compounds[cname] = parsed
    return Projection(tool=obj["tool"], compounds=compounds)


# ---------------------------------------------------------------------------
# static validation (schema §5) — no MacConfig needed
# ---------------------------------------------------------------------------

def validate_projection(
    projection: Projection,
    compounds: Mapping[str, Compound],
    primitive_modes: PrimitiveModes,
) -> None:
    """Enforce schema §5 as far as is possible without a resolved primitive.

    - every referenced compound exists;
    - every projection element exists in the compound;
    - for elements with a *concrete* primitive, ``(primitive, mode)`` is
      characterized now; for the templated MAC PE, the mode must be valid for at
      least one MAC primitive (a typo guard — the exact check runs at resolution).
    """
    for cname, actions in projection.compounds.items():
        if cname not in compounds:
            raise CompoundBundleError(
                f"projection {projection.tool!r} references unknown compound {cname!r}"
            )
        compound = compounds[cname]
        for aname, mapping in actions.items():
            for ename, mode in mapping.elements.items():
                if ename not in compound.elements:
                    raise CompoundBundleError(
                        f"projection {cname}.{aname}: element {ename!r} not in compound "
                        f"({', '.join(compound.elements)})"
                    )
                el = compound.elements[ename]
                if el.primitive_is_template:
                    if not any(primitive_modes.is_valid(p, mode) for p in MAC_PRIMITIVES):
                        raise CompoundBundleError(
                            f"projection {cname}.{aname}: mode {mode!r} for templated "
                            f"element {ename!r} is not valid for any MAC primitive "
                            f"({', '.join(MAC_PRIMITIVES)})"
                        )
                else:
                    primitive_modes.require(el.primitive, mode)


# ---------------------------------------------------------------------------
# per-kernel resolution against a concrete MacConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedElement:
    name: str
    primitive: str
    config: object
    count: int                           # instance count (for area/leak)


@dataclass(frozen=True)
class ResolvedActionElement:
    element: str
    primitive: str
    config: object
    stim_mode: str


@dataclass(frozen=True)
class ActionResolution:
    """A native action resolved for one kernel: which stat drives it, the scale,
    and each element's (primitive, config, stim_mode).

    Per-window energy = stat_value(stat) * scale
                        * sum_element per_cycle_energy(primitive, config, stim_mode).
    Element ``count`` (for area/leak) lives on the resolved compound, NOT here —
    energy uses count_from, area/leak use element.count; the two never multiply.
    """

    action: str
    stat: str
    scale: int
    elements: List[ResolvedActionElement] = field(default_factory=list)


def _symbols_for(mac_config) -> Dict[str, int]:
    return {"lanes": int(mac_config.lanes), "bitwidth": int(mac_config.operand_dtype.bits)}


def _resolve_config(cfg: object, mac_config, symbols: Mapping[str, int], where: str) -> object:
    if cfg == "{mac_config}":
        return dict(mac_config.primitive_config)
    if _is_placeholder(cfg):
        raise CompoundBundleError(f"{where}: unknown placeholder {cfg!r}")
    if isinstance(cfg, dict):
        resolved = {}
        for k, v in cfg.items():
            if isinstance(v, bool):
                resolved[k] = v
            elif isinstance(v, int):
                resolved[k] = v
            elif isinstance(v, str) and not _is_placeholder(v) and _is_scalar_expr(v):
                resolved[k] = _resolve_scalar_expr(v, symbols, f"{where}.{k}")
            else:
                resolved[k] = v  # literal string config (e.g. an mxfpmac format name)
        return resolved
    return cfg


def resolve_compound(compound: Compound, mac_config) -> Dict[str, ResolvedElement]:
    """Resolve placeholders/symbols to a concrete element table for one kernel."""
    symbols = _symbols_for(mac_config)
    out: Dict[str, ResolvedElement] = {}
    for ename, el in compound.elements.items():
        primitive = mac_config.primitive if el.primitive_is_template else el.primitive
        config = _resolve_config(
            el.config, mac_config, symbols, f"compound {compound.name}.{ename}.config"
        )
        count = _resolve_scalar_expr(
            el.count, symbols, f"compound {compound.name}.{ename}.count"
        )
        out[ename] = ResolvedElement(name=ename, primitive=primitive, config=config, count=count)
    return out


def resolve_action(
    projection: Projection,
    compound: Compound,
    action: str,
    mac_config,
    primitive_modes: PrimitiveModes,
) -> ActionResolution:
    """Resolve one native action for a kernel, enforcing the vocabulary at the
    *resolved* primitive.

    Elements omitted from the action's ``elements`` map default to ``idle``
    (schema §5), so accounting stays complete. An omitted or explicit mode the
    resolved primitive can't do (e.g. ``mxfpmac`` + ``hold_b``) raises — honest,
    rather than silently mischarging.
    """
    actions = projection.compounds.get(compound.name)
    if actions is None or action not in actions:
        raise CompoundBundleError(
            f"projection {projection.tool!r} has no action {action!r} for {compound.name!r}"
        )
    mapping = actions[action]
    resolved_elems = resolve_compound(compound, mac_config)
    symbols = _symbols_for(mac_config)
    scale = _resolve_scalar_expr(
        mapping.count_from.scale, symbols,
        f"projection {compound.name}.{action} count_from.scale",
    )

    out_elems: List[ResolvedActionElement] = []
    for ename, re in resolved_elems.items():
        mode = mapping.elements.get(ename, "idle")  # omitted -> idle default
        primitive_modes.require(re.primitive, mode)
        out_elems.append(
            ResolvedActionElement(
                element=ename, primitive=re.primitive, config=re.config, stim_mode=mode
            )
        )
    return ActionResolution(
        action=action, stat=mapping.count_from.stat, scale=scale, elements=out_elems
    )


# ---------------------------------------------------------------------------
# bundle loading (a harness-definition directory)
# ---------------------------------------------------------------------------
#
# A "bundle" is a directory a harness (or a user) authors:
#
#     <root>/compounds/<name>.{json,yaml}       the compounds this harness models
#     <root>/projections/<tool>.{json,yaml}     native action -> stim_mode maps
#     <root>/primitive_modes.{json,yaml}        (optional) override the contract
#
# The stim_mode vocabulary (``primitive_modes``) is the SYSTEM contract shipped
# with the interpreter under ``compounds/data/``; a bundle overrides it only if it
# ships its own file (i.e. it characterized new modes).

def _structured_files(directory: Path) -> List[Path]:
    """All ``*.json``/``*.yaml``/``*.yml`` files in a directory, sorted, deduped
    by stem (a ``.json`` and ``.yaml`` of the same name is an authoring error)."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    files: List[Path] = []
    for suf in _STRUCTURED_SUFFIXES:
        files.extend(directory.glob(f"*{suf}"))
    seen: Dict[str, Path] = {}
    for p in sorted(files):
        if p.stem in seen:
            raise CompoundBundleError(
                f"two bundle files with stem {p.stem!r} in {directory}: "
                f"{seen[p.stem].name} and {p.name}"
            )
        seen[p.stem] = p
    return [seen[k] for k in sorted(seen)]


def load_compounds_dir(directory: Path) -> Dict[str, Compound]:
    """Load every compounds file (JSON/YAML) in a directory."""
    out: Dict[str, Compound] = {}
    for p in _structured_files(directory):
        out.update(load_compounds(p))
    return out


def _resolve_named(directory: Path, name: str) -> Optional[Path]:
    for suf in _STRUCTURED_SUFFIXES:
        cand = Path(directory) / f"{name}{suf}"
        if cand.is_file():
            return cand
    return None


def load_bundle(root: Path) -> "Bundle":
    """Load a harness-definition directory into a validated ``Bundle``.

    Reads ``<root>/compounds/`` + ``<root>/projections/``; ``primitive_modes``
    comes from ``<root>`` if the bundle ships one, else the system contract. The
    returned bundle is checked (``Bundle.validate``) before it is handed back.
    """
    root = Path(root)
    compounds = load_compounds_dir(root / "compounds")
    projections = {
        p.stem: load_projection(p) for p in _structured_files(root / "projections")
    }
    pm_path = _resolve_named(root, "primitive_modes")
    modes = load_primitive_modes(pm_path) if pm_path else load_primitive_modes()
    bundle = Bundle(compounds=compounds, projections=projections, primitive_modes=modes)
    bundle.validate()
    return bundle


@dataclass(frozen=True)
class Bundle:
    """A harness's definitions: its compounds + projections + the mode vocabulary."""

    compounds: Dict[str, Compound]
    projections: Dict[str, Projection]
    primitive_modes: PrimitiveModes

    def validate(self) -> None:
        """Statically validate every projection against the compounds + vocabulary."""
        for proj in self.projections.values():
            validate_projection(proj, self.compounds, self.primitive_modes)

    def compound(self, name: str) -> Compound:
        if name not in self.compounds:
            raise CompoundBundleError(
                f"no compound {name!r} in bundle ({', '.join(sorted(self.compounds))})"
            )
        return self.compounds[name]

    def projection(self, tool: str) -> Projection:
        if tool not in self.projections:
            raise CompoundBundleError(
                f"no projection {tool!r} in bundle ({', '.join(sorted(self.projections))})"
            )
        return self.projections[tool]
