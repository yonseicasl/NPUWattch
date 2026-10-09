"""The NPUWattch message catalog.

Each message that NPUWattch gives to the user has a code and is an entry in
a catalog. A call site does not write the message text. It gives the code
and the values of the template fields. Thus one code always has one meaning,
and you can find all the messages of the tool in the catalog modules.

A message line has this format (the format of the commercial EDA tools)::

    WARNING: (NW-6101): kernel conv_3 has no MAC configuration

The level states who must do something:

- INFO: progress or a fact about the run. No action is necessary.
- WARNING: the run continues, but a result can be incorrect or approximate.
  Read the message.
- ERROR: the input is not correct or is out of scope. The run stops.
- CRITICAL: NPUWattch or its models are not correct. The run stops.

Codes
-----
A code is ``<SPACE>-<number>``. All built-in messages use the space ``NW``.
A third-party estimator or harness registers its own space (for example
``ACME``) and uses its own numbers. In one space, a number has one entry.

The built-in numbers have four digits. The first digit is the area and the
second digit is the module (see ``NW_BLOCKS``). A number is permanent: do not
renumber an entry and do not use a number again. When an entry is removed,
add its number to the ``retired`` set of the catalog module.

Messages and exceptions
-----------------------
An entry is a *message* entry (its kind is a level) or an *exception* entry
(its kind is the name of an exception class)::

    warnings.append(warning(6101, kernel=name))      # message entry
    raise MacInferenceError.nw(6110, kernel=name)    # exception entry

A message entry makes a :class:`Diagnostic`. This is a ``str`` with the
value ``"(NW-6101): <text>"`` and the attributes ``code``, ``level``,
``text`` and ``fields``. Because it is a ``str``, the existing lists of
warnings and notes accept it without change. Call :meth:`Diagnostic.emit`
to print it.

An exception entry can be raised only through its class (``Cls.nw``). The
class gives the level. ``str(exc)`` is ``"(NW-5101): <text>"``.

Catalog modules
---------------
Each package has one catalog module that calls :func:`register`. The
catalog modules of NPUWattch are in ``BUILTIN_CATALOGS``. They load the first
time that a code is looked up. A plugin calls :func:`register` when it is
imported.

The test ``tests/test_diagnostics.py`` checks each call site statically: the
code must exist, the kind must agree, and the keyword fields must be the
template fields.
"""

from __future__ import annotations

import importlib
import string
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, Iterator, List, Mapping, Optional, Tuple

INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"
CRITICAL = "CRITICAL"

#: The levels, from the least to the most severe.
LEVELS: Tuple[str, ...] = (INFO, WARNING, ERROR, CRITICAL)

#: The space of the built-in messages.
NW = "NW"

#: The number blocks of the NW space. The first digit is the area. The
#: second digit is the module in the area.
NW_BLOCKS: Dict[str, Tuple[int, int]] = {
    "CLI, parser and estimator host": (1000, 1899),
    "message system": (1900, 1999),
    "description, naming, user components, arch synthesis": (2000, 2999),
    "energy": (3000, 3999),
    "report": (4000, 4999),
    "harness registry, run inputs, vocabulary, compounds": (5000, 5999),
    "PyTorchSim harness": (6000, 6999),
    "Timeloop harness": (7000, 7999),
    "estimators": (8000, 8999),
    "reserved (gem5 harness)": (9000, 9999),
}

#: The catalog modules of NPUWattch. They load the first time that a code is
#: looked up.
BUILTIN_CATALOGS: Tuple[str, ...] = (
    "npuwattch.catalog",
    "npuwattch_harness.catalog",
    "npuwattch_harness.pytorchsim.catalog",
    "npuwattch_harness.timeloop.catalog",
    "npuwattch_estimators.catalog",
)


@dataclass(frozen=True)
class Entry:
    """One catalog entry."""

    space: str
    number: int
    kind: str            # a level (message entry) or an exception class name
    template: str
    source: str = ""     # the catalog module that registered the entry

    @property
    def code(self) -> str:
        return f"{self.space}-{self.number}"

    @property
    def is_exception(self) -> bool:
        return self.kind not in LEVELS

    @property
    def fields(self) -> FrozenSet[str]:
        return template_fields(self.template)


#: (space, number) -> entry.
CATALOG: Dict[Tuple[str, int], Entry] = {}

#: (space, number) of the retired entries. A retired number is not used again.
RETIRED: Dict[Tuple[str, int], str] = {}

_builtin_loaded = False


def template_fields(template: str) -> FrozenSet[str]:
    """Return the names of the fields in a ``str.format`` template."""
    names = set()
    for _, name, _, _ in string.Formatter().parse(template):
        if name:
            names.add(name.split(".", 1)[0].split("[", 1)[0])
    return frozenset(names)


def register(space: str, entries: Mapping[int, Tuple[str, str]], *,
             retired: Iterable[int] = (), source: str = "") -> None:
    """Add the entries of one catalog module.

    ``entries`` maps a number to ``(kind, template)``. The kind is a level
    (``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``) or the name of an
    exception class. ``retired`` gives the numbers that this module used
    before. These numbers cannot be registered again.
    """
    if not space.isidentifier() or not space.isupper():
        raise ValueError(f"message space {space!r} must be an upper-case identifier")
    for number in retired:
        RETIRED[(space, int(number))] = source
    for number, (kind, template) in entries.items():
        key = (space, number)
        if not isinstance(number, int) or number <= 0:
            raise ValueError(f"{space}: message number {number!r} must be a positive int")
        if space == NW and not 1000 <= number <= 9999:
            raise ValueError(f"NW-{number}: built-in numbers have four digits")
        if key in CATALOG:
            raise ValueError(f"{space}-{number} is already registered by "
                             f"{CATALOG[key].source or 'another module'}")
        if key in RETIRED:
            raise ValueError(f"{space}-{number} is retired; use a new number")
        if kind not in LEVELS and not (kind.isidentifier() and kind[:1].isupper()):
            raise ValueError(f"{space}-{number}: kind {kind!r} is not a level "
                             f"or an exception class name")
        CATALOG[key] = Entry(space, number, kind, template, source)


def load_builtin_catalogs() -> None:
    """Import the catalog modules in ``BUILTIN_CATALOGS`` (one time only)."""
    global _builtin_loaded
    if _builtin_loaded:
        return
    _builtin_loaded = True
    for name in BUILTIN_CATALOGS:
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as e:
            # A package can have no catalog module yet. An import error in a
            # catalog module itself is not ignored.
            if e.name != name:
                raise


def lookup(number: int, space: str = NW) -> Entry:
    """Return the entry of ``<space>-<number>``."""
    key = (space, number)
    if key not in CATALOG:
        load_builtin_catalogs()
    try:
        return CATALOG[key]
    except KeyError:
        raise ValueError(f"{space}-{number} is not a catalog entry") from None


def parse_code(code: str) -> Tuple[str, int]:
    """Change ``"NW-6101"`` to ``("NW", 6101)``."""
    space, sep, number = code.strip().rpartition("-")
    if not sep or not space or not number.isdigit():
        raise ValueError(f"{code!r} is not a message code (example: NW-6101)")
    return space.upper(), int(number)


def entries() -> Iterator[Entry]:
    """Return all the entries, sorted by space and number."""
    load_builtin_catalogs()
    for key in sorted(CATALOG):
        yield CATALOG[key]


def _render(entry: Entry, fields: Mapping[str, object]) -> str:
    try:
        return entry.template.format(**fields)
    except (KeyError, IndexError, ValueError, AttributeError) as e:
        # A message must not hide the problem that it reports. Thus a bad
        # template gives the raw template and the values, not a new error.
        values = ", ".join(f"{k}={v!r}" for k, v in fields.items())
        return f"{entry.template} [{values}] (template error: {e!r})"


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class Diagnostic(str):
    """One message: a ``str`` with the value ``"(<code>): <text>"``.

    Use the attributes for the parts: ``code``, ``space``, ``number``,
    ``level``, ``text`` and ``fields``. ``line`` is the printed line.
    """

    space: str
    number: int
    level: str
    text: str
    fields: Dict[str, object]

    def __new__(cls, space: str, number: int, level: str, text: str,
                fields: Optional[Mapping[str, object]] = None) -> "Diagnostic":
        self = super().__new__(cls, f"({space}-{number}): {text}")
        self.space = space
        self.number = number
        self.level = level
        self.text = text
        self.fields = dict(fields or {})
        return self

    def __reduce__(self):
        return (Diagnostic, (self.space, self.number, self.level, self.text,
                             self.fields))

    @property
    def code(self) -> str:
        return f"{self.space}-{self.number}"

    @property
    def line(self) -> str:
        return f"{self.level}: {self}"

    def as_dict(self) -> Dict[str, object]:
        """Return the JSON form of the message."""
        return {"code": self.code, "level": self.level, "message": self.text}

    def emit(self) -> None:
        """Print the message, if it is not suppressed."""
        emit(self)


class Space:
    """The message constructors of one space.

    The module functions :func:`info`, :func:`warning`, :func:`error` and
    :func:`critical` are the constructors of the ``NW`` space. A plugin
    makes its own: ``ACME = Space("ACME")``, then ``ACME.warning(1, ...)``.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def make(self, level: str, number: int, fields: Mapping[str, object]) -> Diagnostic:
        entry = lookup(number, self.name)
        if entry.kind != level:
            raise ValueError(f"{entry.code} is a {entry.kind} entry, not {level}")
        return Diagnostic(entry.space, number, level, _render(entry, fields), fields)

    def info(self, number: int, /, **fields: object) -> Diagnostic:
        return self.make(INFO, number, fields)

    def warning(self, number: int, /, **fields: object) -> Diagnostic:
        return self.make(WARNING, number, fields)

    def error(self, number: int, /, **fields: object) -> Diagnostic:
        return self.make(ERROR, number, fields)

    def critical(self, number: int, /, **fields: object) -> Diagnostic:
        return self.make(CRITICAL, number, fields)


_NW = Space(NW)


def info(number: int, /, **fields: object) -> Diagnostic:
    """Make the INFO message ``NW-<number>``."""
    return _NW.make(INFO, number, fields)


def warning(number: int, /, **fields: object) -> Diagnostic:
    """Make the WARNING message ``NW-<number>``."""
    return _NW.make(WARNING, number, fields)


def error(number: int, /, **fields: object) -> Diagnostic:
    """Make the ERROR message ``NW-<number>``."""
    return _NW.make(ERROR, number, fields)


def critical(number: int, /, **fields: object) -> Diagnostic:
    """Make the CRITICAL message ``NW-<number>``."""
    return _NW.make(CRITICAL, number, fields)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class NPUWattchError(Exception):
    """The base of each exception that has a catalog entry.

    A subclass keeps its usual built-in base, for example
    ``class HarnessError(NPUWattchError, ValueError)``, thus the existing
    ``except ValueError`` clauses do not change. Make an instance with
    :meth:`nw`. ``level`` is the level of the line that the CLI prints.
    A plugin sets ``space`` to its own space.
    """

    level: str = ERROR
    space: str = NW
    number: Optional[int] = None
    text: str = ""
    fields: Dict[str, object] = {}

    @classmethod
    def nw(cls, number: int, /, **fields: object) -> "NPUWattchError":
        """Make the exception of the catalog entry ``<space>-<number>``."""
        entry = lookup(number, cls.space)
        if entry.kind != cls.__name__:
            raise ValueError(f"{entry.code} is a {entry.kind} entry, "
                             f"not {cls.__name__}")
        text = _render(entry, fields)
        exc = cls(f"({entry.code}): {text}")
        exc.number = number
        exc.text = text
        exc.fields = dict(fields)
        return exc

    @property
    def code(self) -> Optional[str]:
        return None if self.number is None else f"{self.space}-{self.number}"

    @property
    def line(self) -> str:
        return f"{self.level}: {self}"

    def as_diagnostic(self) -> Diagnostic:
        """Return the exception as a message with the same code and level."""
        return Diagnostic(self.space, self.number or 0, self.level,
                          self.text or str(self), self.fields)


# ---------------------------------------------------------------------------
# Output: suppression and the message summary
# ---------------------------------------------------------------------------

#: The codes that ``--suppress`` hides.
_suppressed: set = set()
#: (level, code) -> number of printed messages.
_printed: Counter = Counter()
#: code -> number of suppressed messages.
_hidden: Counter = Counter()


def reset() -> None:
    """Clear the suppression list and the counters (one CLI run, or a test)."""
    _suppressed.clear()
    _printed.clear()
    _hidden.clear()


def _suppressible(code: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(code, None)`` for a code that can be suppressed, else
    ``(None, problem)``."""
    try:
        space, number = parse_code(code)
        entry = lookup(number, space)
    except ValueError as e:
        return None, str(e)
    if entry.kind not in (INFO, WARNING):
        return None, (f"{entry.code} is a {entry.kind} entry; only INFO "
                      f"and WARNING messages can be suppressed")
    return entry.code, None


def suppress_problems(codes: Iterable[str]) -> List[str]:
    """Return the problems of a ``--suppress`` list. Nothing changes."""
    return [p for p in (_suppressible(c)[1] for c in codes) if p]


def suppress(codes: Iterable[str]) -> List[str]:
    """Hide the messages with these codes. Return the problems.

    Only INFO and WARNING entries can be suppressed. An ERROR or a CRITICAL
    message always stops the run, thus it is always printed.
    """
    problems = []
    for code in codes:
        ok, problem = _suppressible(code)
        if ok:
            _suppressed.add(ok)
        else:
            problems.append(problem)
    return problems


def is_suppressed(code: Optional[str]) -> bool:
    return code in _suppressed


def emit(message, *, file=None) -> None:
    """Print a message line (a :class:`Diagnostic` or an ``NPUWattchError``).

    A suppressed message is not printed, but it is counted.
    """
    code = getattr(message, "code", None)
    level = getattr(message, "level", None)
    if code in _suppressed:
        _hidden[code] += 1
        return
    _printed[(level, code)] += 1
    print(message.line, file=file if file is not None else sys.stdout)


def group(messages: Iterable[object], level: str = WARNING) -> List[Dict[str, object]]:
    """Group equal messages for a report: one record for each different
    (code, text), in the order of the first occurrence, with a count.

    A suppressed message is not in the result. A plain ``str`` (not a
    catalog message) has the code ``None`` and the level ``level``.
    """
    out: Dict[Tuple[Optional[str], str], Dict[str, object]] = {}
    for m in messages:
        code = getattr(m, "code", None)
        if code in _suppressed:
            continue
        text = getattr(m, "text", None) or str(m)
        key = (code, text)
        if key in out:
            out[key]["count"] += 1
        else:
            out[key] = {"code": code, "level": getattr(m, "level", level),
                        "message": text, "count": 1}
    return list(out.values())


# ---------------------------------------------------------------------------
# The catalog as a list (--list-messages, docs/MESSAGES.md)
# ---------------------------------------------------------------------------

#: The modules that define the exception classes of the NW entries. The
#: listing imports them to find the level of each class. A test makes sure
#: that each exception entry has its class here.
EXCEPTION_MODULES: Tuple[str, ...] = (
    "npuwattch.arch_synth",
    "npuwattch.energy.aggregate",
    "npuwattch.energy.dram_table",
    "npuwattch.energy.node_scaling",
    "npuwattch.energy.unit_cost",
    "npuwattch.energy.vectorless",
    "npuwattch.naming",
    "npuwattch.npuwattch_estimator_host",
    "npuwattch.report.html",
    "npuwattch.user_components",
    "npuwattch_estimators.errors",
    "npuwattch_harness.compounds.loader",
    "npuwattch_harness.pytorchsim.booksim",
    "npuwattch_harness.pytorchsim.mac_config",
    "npuwattch_harness.pytorchsim.run_config",
    "npuwattch_harness.pytorchsim.togsim_log",
    "npuwattch_harness.registry",
    "npuwattch_harness.timeloop.stats",
    "npuwattch_harness.vocabulary",
)


def exception_levels() -> Dict[str, str]:
    """Return the level of each loaded exception class, by class name."""
    for name in EXCEPTION_MODULES:
        importlib.import_module(name)
    levels: Dict[str, str] = {}
    todo = [NPUWattchError]
    while todo:
        cls = todo.pop()
        for sub in cls.__subclasses__():
            levels[sub.__name__] = sub.level
            todo.append(sub)
    return levels


def listing(prefix: str = "") -> List[Tuple[str, str, str, str]]:
    """Return ``(code, level, class, template)`` for each entry whose code
    starts with ``prefix`` (case is ignored). ``class`` is empty for a
    message entry."""
    levels = exception_levels()
    rows = []
    for e in entries():
        if not e.code.upper().startswith(prefix.upper()):
            continue
        if e.is_exception:
            rows.append((e.code, levels.get(e.kind, ERROR), e.kind, e.template))
        else:
            rows.append((e.code, e.kind, "", e.template))
    return rows


def catalog_markdown() -> str:
    """Return the catalog as the Markdown page ``docs/MESSAGES.md``."""
    out = [
        "# NPUWattch messages",
        "",
        "<!-- Generated from the catalog modules. Do not edit. Update with:",
        "     python -m npuwattch.diagnostics --markdown > docs/MESSAGES.md -->",
        "",
        "Each message that NPUWattch gives has a code. A console line has the",
        "format `LEVEL: (CODE): text`. `npuwattch --list-messages [PREFIX]`",
        "shows the same list. `--suppress CODE[,CODE...]` hides INFO and",
        "WARNING messages. In a template, `{name}` is a value of the run.",
        "",
        "| Level | Meaning |",
        "|---|---|",
        "| INFO | Progress or a fact about the run. No action is necessary. |",
        "| WARNING | The run continues, but a result can be incorrect or "
        "approximate. Read the message. |",
        "| ERROR | The input is not correct or is out of scope. The run stops. |",
        "| CRITICAL | NPUWattch or its models are not correct. The run stops. "
        "Please report it. |",
    ]
    rows = listing()
    for title, (lo, hi) in NW_BLOCKS.items():
        block = [r for r in rows
                 if r[0].startswith("NW-") and lo <= int(r[0][3:]) <= hi]
        if not block:
            continue
        out += ["", f"## NW-{lo}..{hi}: {title}", "",
                "| Code | Level | Exception | Message |", "|---|---|---|---|"]
        for code, level, kind, template in block:
            text = template.replace("|", "\\|").replace("\n", " ")
            out.append(f"| {code} | {level} | {kind} | {text} |")
    return "\n".join(out) + "\n"


def summary() -> Dict[str, object]:
    """Return the counts of the printed and the suppressed messages."""
    by_level: Counter = Counter()
    by_code: Dict[str, Dict[str, object]] = {}
    for (level, code), n in _printed.items():
        by_level[level] += n
        if level in (WARNING, ERROR, CRITICAL) and code:
            by_code[code] = {"level": level, "count": n}
    return {
        "by_level": {lvl: by_level.get(lvl, 0) for lvl in LEVELS},
        "by_code": dict(sorted(by_code.items())),
        "suppressed": dict(sorted(_hidden.items())),
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["--markdown"]:
        # Under ``-m`` this file is ``__main__``, a second module object. The
        # catalog modules register in ``npuwattch.diagnostics``, thus use it.
        _registry = importlib.import_module("npuwattch.diagnostics")
        sys.stdout.write(_registry.catalog_markdown())
    else:
        sys.stderr.write("usage: python -m npuwattch.diagnostics --markdown\n")
        sys.exit(2)
