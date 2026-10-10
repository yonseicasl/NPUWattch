"""The NPUWattch message catalog.

Each message that NPUWattch gives to the user has a code and is an entry in
a catalog. A call site does not write the message text. It gives the code
and the values of the template fields. Thus one code always has one meaning,
and you can find all the messages of the tool in the catalog modules.

A message line has this format (the format of the commercial EDA tools)::

    WARNING (NW-6101): kernel conv_3 has no MAC configuration

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

A catalog module also declares its *blocks*: the range of numbers that each
module of the package uses. The blocks are data, thus the lint can check
that a call site uses a number of its own block.

The test ``tests/test_diagnostics.py`` checks each call site statically: the
code must exist, the kind must agree, the keyword fields must be the
template fields, and the number must be in the block of the module.

A subclass of :class:`NPUWattchError` registers its name and its level when
its class statement runs. Thus no list of exception modules is necessary.
"""

from __future__ import annotations

import importlib
import pkgutil
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
    explain: str = ""    # what the message means and what to do (--explain)

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

#: (space, lo, hi) -> the modules that use the numbers lo..hi. A name that is
#: a package covers each module in the package.
BLOCKS: Dict[Tuple[str, int, int], Tuple[str, ...]] = {}

_builtin_loaded = False


def template_fields(template: str) -> FrozenSet[str]:
    """Return the names of the fields in a ``str.format`` template."""
    names = set()
    for _, name, _, _ in string.Formatter().parse(template):
        if name:
            names.add(name.split(".", 1)[0].split("[", 1)[0])
    return frozenset(names)


def register(space: str, entries: Mapping[int, Tuple[str, str]], *,
             retired: Iterable[int] = (), source: str = "",
             blocks: Optional[Mapping[Tuple[int, int], object]] = None) -> None:
    """Add the entries of one catalog module.

    ``entries`` maps a number to ``(kind, template)`` or to
    ``(kind, template, explain)``. The kind is a level
    (``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``) or the name of an
    exception class. ``retired`` gives the numbers that this module used
    before. These numbers cannot be registered again.

    ``blocks`` maps ``(lo, hi)`` to the module, or the modules, that use the
    numbers ``lo..hi``. A name that is a package covers each module in the
    package. When ``blocks`` is given, each entry must be in one block, and
    the lint checks that each call site is in a module of its block.
    """
    if not space.isidentifier() or not space.isupper():
        raise ValueError(f"message space {space!r} must be an upper-case identifier")
    for number in retired:
        RETIRED[(space, int(number))] = source
    for (lo, hi), modules in (blocks or {}).items():
        _register_block(space, int(lo), int(hi), modules)
    for number, item in entries.items():
        if not isinstance(item, tuple) or len(item) not in (2, 3):
            raise ValueError(f"{space}-{number}: give (kind, template) or "
                             f"(kind, template, explain)")
        kind, template = item[0], item[1]
        explain = " ".join(item[2].split()) if len(item) == 3 else ""
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
        if blocks and block_of(number, space) is None:
            raise ValueError(f"{space}-{number} is in no block of {source or space}")
        CATALOG[key] = Entry(space, number, kind, template, source, explain)


def _register_block(space: str, lo: int, hi: int, modules: object) -> None:
    names = (modules,) if isinstance(modules, str) else tuple(modules)  # type: ignore[arg-type]
    if lo > hi or not names:
        raise ValueError(f"{space}-{lo}..{hi}: a block has lo <= hi and one or "
                         f"more modules")
    if space == NW and not any(a <= lo and hi <= b for a, b in NW_BLOCKS.values()):
        raise ValueError(f"NW-{lo}..{hi}: the block is not inside one NW area")
    for (other_space, lo2, hi2), other in BLOCKS.items():
        if other_space == space and lo <= hi2 and lo2 <= hi:
            raise ValueError(f"{space}-{lo}..{hi} overlaps the block "
                             f"{lo2}..{hi2} of {', '.join(other)}")
    BLOCKS[(space, lo, hi)] = names


def block_of(number: int, space: str = NW) -> Optional[Tuple[int, int, Tuple[str, ...]]]:
    """Return ``(lo, hi, modules)`` of the block that holds the number, or
    ``None`` if the catalog declares no block for it."""
    for (s, lo, hi), modules in BLOCKS.items():
        if s == space and lo <= number <= hi:
            return lo, hi, modules
    return None


def in_block(module: str, number: int, space: str = NW) -> bool:
    """True if ``module`` may use the number: the catalog declares no block
    for it, or ``module`` is one of the block's modules or is in one of its
    packages."""
    found = block_of(number, space)
    if found is None:
        return True
    return any(module == m or module.startswith(m + ".") for m in found[2])


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
        return f"{self.level} {self}"

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

#: Class name -> level, of each subclass of NPUWattchError that Python has
#: loaded. :func:`exception_levels` loads the built-in packages first.
EXCEPTION_LEVELS: Dict[str, str] = {}


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

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        EXCEPTION_LEVELS[cls.__name__] = cls.level

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
        return f"{self.level} {self}"

    def as_diagnostic(self) -> Diagnostic:
        """Return the exception as a message with the same code and level."""
        return Diagnostic(self.space, self.number or 0, self.level,
                          self.text or str(self), self.fields)


def as_diagnostic(message: object, level: str = WARNING) -> Diagnostic:
    """Return ``message`` as a catalog message.

    A :class:`Diagnostic` does not change. An exception with a catalog entry
    becomes the message of its entry. A plain ``str`` (from a third-party
    plugin that does not use the catalog yet) gets the generic entry of
    ``level`` (NW-1801 INFO, NW-1802 WARNING, NW-1803 ERROR). Thus each
    printed line has a code.
    """
    if isinstance(message, Diagnostic):
        return message
    if isinstance(message, NPUWattchError) and message.number is not None:
        return message.as_diagnostic()
    text = str(message)
    if level == INFO:
        return info(1801, message=text)
    if level == ERROR:
        return error(1803, message=text)
    return warning(1802, message=text)


def about(subject: str, message: object) -> Diagnostic:
    """Return ``message`` with the prefix ``"<subject>: "``.

    The message is about one component or element (for example, an envelope
    warning of an estimator). A :class:`Diagnostic` keeps its code and its
    level; only its text gets the prefix. A plain ``str`` gets the generic
    entry NW-1804 (WARNING).
    """
    if isinstance(message, Diagnostic):
        return Diagnostic(message.space, message.number, message.level,
                          f"{subject}: {message.text}",
                          {**message.fields, "subject": subject})
    return warning(1804, subject=subject, message=str(message))


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


def suppressible(code: str) -> str:
    """Return the normalized code of a message that ``--suppress`` can hide.

    Only INFO and WARNING entries can be suppressed. An ERROR or a CRITICAL
    message always stops the run, thus it is always printed. Raises
    ``ValueError`` if the code is not correct, has no entry, or is not an
    INFO or WARNING entry. The argument parser checks each code with this
    function one time, then :func:`suppress` stores the codes.
    """
    space, number = parse_code(code)
    entry = lookup(number, space)
    if entry.kind not in (INFO, WARNING):
        raise ValueError(f"{entry.code} is a {entry.kind} entry; only INFO "
                         f"and WARNING messages can be suppressed")
    return entry.code


def suppress(codes: Iterable[str]) -> None:
    """Hide the messages with these codes (normalized by :func:`suppressible`)."""
    _suppressed.update(codes)


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
            why = ""
            if code is not None:
                try:
                    why = lookup(m.number, m.space).explain
                except ValueError:
                    pass
            out[key] = {"code": code, "level": getattr(m, "level", level),
                        "message": text, "count": 1, "explain": why}
    return list(out.values())


# ---------------------------------------------------------------------------
# The catalog as a list (--list-messages, MESSAGES.md)
# ---------------------------------------------------------------------------

def exception_levels() -> Dict[str, str]:
    """Return the level of each exception class, by class name.

    A subclass of :class:`NPUWattchError` registers itself when Python runs
    its class statement. This function imports each module of the built-in
    packages first, thus each built-in class is registered. A plugin
    registers its classes when it is imported.
    """
    for top in sorted({name.split(".", 1)[0] for name in BUILTIN_CATALOGS}):
        package = importlib.import_module(top)
        for module in pkgutil.walk_packages(package.__path__, top + "."):
            importlib.import_module(module.name)
    return dict(EXCEPTION_LEVELS)


def listing(prefix: str = "") -> List[Tuple[Entry, str]]:
    """Return ``(entry, level)`` for each entry whose code starts with
    ``prefix`` (case is ignored). The level of an exception entry is the
    level of its class."""
    levels = exception_levels()
    return [(e, levels.get(e.kind, ERROR) if e.is_exception else e.kind)
            for e in entries() if e.code.upper().startswith(prefix.upper())]


def explain(code: str) -> str:
    """Return the ``--explain`` text of a code: the level, the message
    template, the exception class, the explanation and the source module.

    Raises ``ValueError`` if the code is not correct or has no entry."""
    space, number = parse_code(code)
    e = lookup(number, space)
    level = exception_levels().get(e.kind, ERROR) if e.is_exception else e.kind
    out = [f"{e.code}  {level}", "", f"  Message:   {e.template}"]
    if e.is_exception:
        out.append(f"  Exception: {e.kind}")
    out.append(f"  Source:    {e.source}")
    out.append("")
    out.append("  " + (e.explain or "No explanation is available for this message."))
    return "\n".join(out)


def catalog_markdown() -> str:
    """Return the catalog as the Markdown page ``MESSAGES.md``."""
    out = [
        "# NPUWattch messages",
        "",
        "<!-- Generated from the catalog modules. Do not edit. Update with:",
        "     python -m npuwattch.diagnostics --markdown > MESSAGES.md -->",
        "",
        "Each message that NPUWattch gives has a code. A console line has the",
        "format `LEVEL (CODE): text`. `npuwattch --list-messages [PREFIX]`",
        "shows the same list. `npuwattch --explain CODE` shows one entry.",
        "`--suppress CODE[,CODE...]` hides INFO and WARNING messages. In a",
        "message, `{name}` is a value of the run.",
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
    rows = listing(f"{NW}-")
    for title, (lo, hi) in NW_BLOCKS.items():
        block = [(e, level) for e, level in rows if lo <= e.number <= hi]
        if not block:
            continue
        out += ["", f"## NW-{lo}..{hi}: {title}", "",
                "| Code | Level | Message | Explanation |", "|---|---|---|---|"]
        for e, level in block:
            text = e.template.replace("|", "\\|").replace("\n", " ")
            if e.is_exception:
                level = f"{level} ({e.kind})"
            why = e.explain.replace("|", "\\|")
            out.append(f"| {e.code} | {level} | {text} | {why} |")
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
