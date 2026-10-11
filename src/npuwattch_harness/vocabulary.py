"""Vocabulary table engine. This module is used by all harnesses.

Each simulator uses its own names. NPUWattch uses one name for each concept
(see ``npuwattch.naming``). A harness gives a vocabulary table,
``<harness>/definitions/vocabulary.yaml``, that connects the two sets of names.
This module loads the table, checks it, and applies it.

The table has these sections. All sections are optional.

``classes``
    Simulator class name -> NPUWattch primitive.
``float_format``
    How the simulator declares a floating-point datatype.
``families``
    Family name -> primitives that use the same attribute table.
``attributes``
    Family -> NPUWattch attribute -> simulator spellings. The first spelling
    that the component declares is used.
``hints``
    Family -> hint name -> simulator spellings. A hint is a simulator value
    that has no NPUWattch name. The derivation rules of the harness use hints
    to calculate NPUWattch attributes.
``ignore``
    Simulator attributes that are not hardware. No note is written for them.
``description``
    Concept -> spellings of top-level (not per-component) attributes.
``dtypes``
    Simulator datatype spelling -> datatype name.
``float_formats``
    Datatype name -> [total bits, exponent bits, mantissa bits].
``stats``
    Group name -> simulator counter names.

The engine only translates names. A rule that calculates a value (for example,
depth = capacity / width) is not a name translation. Such rules stay in the
Python code of the harness.
"""

from __future__ import annotations

from npuwattch.diagnostics import NPUWattchError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

import yaml

from npuwattch.naming import CANONICAL, LEGACY_ALIASES, PRIMITIVE_PARAMS

__all__ = [
    "AttributeReader",
    "Vocabulary",
    "VocabularyError",
    "load_vocabulary",
    "positive_int",
]

_SECTIONS = ("tool", "classes", "float_format", "families", "attributes",
             "hints", "ignore", "description", "dtypes", "float_formats",
             "stats")


class VocabularyError(NPUWattchError, ValueError):
    """A vocabulary table is incorrect."""


def positive_int(value: Any) -> Optional[int]:
    """Return ``value`` as an integer larger than zero, or ``None``."""
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _normalize(key: Any) -> str:
    """Change a simulator name to the form that the table uses.

    A NPUWattch name stays as it is, because some NPUWattch names contain
    uppercase unit letters (``net_energy_per_bit_pJ``).
    """
    text = str(key).strip()
    if text in CANONICAL:
        return text
    return text.replace("-", "_").lower()


@dataclass(frozen=True)
class Vocabulary:
    """One loaded vocabulary table."""

    tool: str
    classes: Mapping[str, str] = field(default_factory=dict)
    float_keys: Tuple[str, ...] = ()
    float_words: Tuple[str, ...] = ()
    float_siblings: Mapping[str, str] = field(default_factory=dict)
    family_of: Mapping[str, str] = field(default_factory=dict)
    #: family -> name -> spellings. Attribute names and hint names are merged.
    spellings: Mapping[str, Mapping[str, Tuple[str, ...]]] = field(
        default_factory=dict)
    ignore: FrozenSet[str] = frozenset()
    description: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    dtypes: Mapping[str, str] = field(default_factory=dict)
    #: datatype name -> (total bits, exponent bits, mantissa bits)
    float_formats: Mapping[str, Tuple[int, int, int]] = field(
        default_factory=dict)
    stats: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)

    def primitive_for(
        self,
        comp_class: Optional[str],
        subclass: Optional[str] = None,
        attributes: Optional[Mapping[str, Any]] = None,
    ) -> Optional[str]:
        """Return the primitive for a simulator class, or ``None``.

        ``comp_class`` has priority over ``subclass``. If the primitive is an
        integer unit and the attributes declare a floating-point datatype, the
        result is the floating-point sibling.
        """
        primitive: Optional[str] = None
        for candidate in (comp_class, subclass):
            if candidate:
                primitive = self.classes.get(str(candidate).strip().lower())
                if primitive is not None:
                    break
        if primitive in self.float_siblings:
            for key in self.float_keys:
                value = (attributes or {}).get(key)
                if isinstance(value, str) and any(
                        word in value.lower() for word in self.float_words):
                    return self.float_siblings[primitive]
        return primitive

    def family(self, primitive: str) -> Optional[str]:
        """Return the family of a primitive, or ``None``."""
        return self.family_of.get(primitive)

    def read(self, primitive: str, raw: Optional[Mapping[str, Any]]
             ) -> "AttributeReader":
        """Start to read the attributes of one component."""
        family = self.family_of.get(primitive)
        return AttributeReader(self.spellings.get(family, {}), self.ignore, raw)


class AttributeReader:
    """Reads the simulator attributes of one component by NPUWattch name.

    The reader records each simulator attribute that a caller takes. At the
    end, :meth:`ignored` gives the attributes that no caller took.
    """

    def __init__(self, spellings: Mapping[str, Tuple[str, ...]],
                 ignore: FrozenSet[str],
                 raw: Optional[Mapping[str, Any]]) -> None:
        self._spellings = spellings
        self._ignore = ignore
        self.values: Dict[str, Any] = {
            _normalize(k): v for k, v in (raw or {}).items()}
        self.consumed: set = set()

    def take_with_key(self, name: str) -> Tuple[Optional[str], Optional[Any]]:
        """Take the first declared spelling of ``name``.

        Return the spelling and its value, or ``(None, None)``.
        """
        for key in self._spellings.get(name, (name,)):
            if self.values.get(key) is not None:
                self.consumed.add(key)
                return key, self.values[key]
        return None, None

    def take(self, name: str) -> Optional[Any]:
        """Take the value of ``name``, or ``None``."""
        return self.take_with_key(name)[1]

    def take_int(self, name: str) -> Optional[int]:
        """Take the value of ``name`` as an integer larger than zero."""
        return positive_int(self.take(name))

    def take_all_ints(self, name: str) -> List[int]:
        """Take all declared spellings of ``name`` and return their values."""
        out: List[int] = []
        for key in self._spellings.get(name, (name,)):
            if key in self.values:
                self.consumed.add(key)
                value = positive_int(self.values[key])
                if value:
                    out.append(value)
        return out

    def peek_int(self, name: str) -> Optional[int]:
        """Read ``name`` as a positive integer but do not take it."""
        for key in self._spellings.get(name, (name,)):
            if self.values.get(key) is not None:
                return positive_int(self.values[key])
        return None

    def take_named(self) -> Dict[str, Any]:
        """Take each attribute that has a NPUWattch name or a known alias.

        Use this for a primitive that has no attribute table.
        """
        out: Dict[str, Any] = {}
        for key, value in self.values.items():
            name = key if key in CANONICAL else LEGACY_ALIASES.get(key)
            if name:
                out[name] = value
                self.consumed.add(key)
        return out

    def ignored(self) -> List[str]:
        """Return the attributes that no caller took, in sorted order."""
        return sorted(k for k in self.values
                      if k not in self.consumed and k not in self._ignore)


def load_vocabulary(path: Path) -> Vocabulary:
    """Load and check one vocabulary table.

    Raise :class:`VocabularyError` if a target is not a NPUWattch name.
    """
    path = Path(path)
    try:
        table = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise VocabularyError.nw(5201, path=path) from e
    except yaml.YAMLError as e:
        raise VocabularyError.nw(5202, path=path, error=e) from e
    if not isinstance(table, Mapping):
        raise VocabularyError.nw(5203, path=path)
    unknown = sorted(set(table) - set(_SECTIONS))
    if unknown:
        raise VocabularyError.nw(5204, path=path, unknown=", ".join(unknown),
                                 expected=", ".join(_SECTIONS))

    known_primitives = set(PRIMITIVE_PARAMS)

    def check_primitive(primitive: Any, where: str) -> str:
        if primitive not in known_primitives:
            raise VocabularyError.nw(
                5205, path=path, where=where, primitive=primitive,
                known=", ".join(sorted(known_primitives)))
        return primitive

    classes = {
        str(source).lower(): check_primitive(primitive, f"classes.{source}")
        for source, primitive in (table.get("classes") or {}).items()}

    float_format = table.get("float_format") or {}
    float_siblings = {
        check_primitive(a, "float_format.siblings"):
            check_primitive(b, "float_format.siblings")
        for a, b in (float_format.get("siblings") or {}).items()}

    family_of: Dict[str, str] = {}
    for family, primitives in (table.get("families") or {}).items():
        for primitive in primitives or ():
            check_primitive(primitive, f"families.{family}")
            if primitive in family_of:
                raise VocabularyError.nw(
                    5206, path=path, primitive=primitive,
                    first=family_of[primitive], second=family)
            family_of[primitive] = family

    spellings: Dict[str, Dict[str, Tuple[str, ...]]] = {}
    for section in ("attributes", "hints"):
        for family, names in (table.get(section) or {}).items():
            if family not in set(family_of.values()):
                raise VocabularyError.nw(5207, path=path, section=section,
                                         family=family)
            merged = spellings.setdefault(family, {})
            for name, keys in (names or {}).items():
                if section == "attributes" and name not in CANONICAL:
                    raise VocabularyError.nw(5208, path=path, family=family,
                                             name=name)
                if section == "hints" and name in CANONICAL:
                    raise VocabularyError.nw(5209, path=path, family=family,
                                             name=name)
                if name in merged:
                    raise VocabularyError.nw(5210, path=path, section=section,
                                             family=family, name=name)
                merged[name] = tuple(str(k) for k in keys or ())

    float_formats: Dict[str, Tuple[int, int, int]] = {}
    for name, fields in (table.get("float_formats") or {}).items():
        if not (isinstance(fields, list) and len(fields) == 3
                and all(isinstance(x, int) for x in fields)):
            raise VocabularyError.nw(5211, path=path, name=name)
        float_formats[str(name)] = (fields[0], fields[1], fields[2])

    return Vocabulary(
        tool=str(table.get("tool") or path.parent.parent.name),
        classes=classes,
        float_keys=tuple(float_format.get("keys") or ()),
        float_words=tuple(float_format.get("words") or ()),
        float_siblings=float_siblings,
        family_of=family_of,
        spellings=spellings,
        ignore=frozenset(str(k) for k in table.get("ignore") or ()),
        description={str(k): tuple(v or ())
                     for k, v in (table.get("description") or {}).items()},
        dtypes={str(k).lower(): str(v)
                for k, v in (table.get("dtypes") or {}).items()},
        float_formats=float_formats,
        stats={str(k): tuple(str(n) for n in v or ())
               for k, v in (table.get("stats") or {}).items()},
    )
