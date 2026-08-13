"""Console table rendering.

Every CLI table goes through this module so that **column widths are measured
from the data**, never hardcoded. The previous hand-rolled ``f"{name:<26}"``
layout silently broke alignment whenever a value was wider than its column —
which is the normal case for hierarchical component names such as
``system_top_level.eyeriss.PE_column.PE.weights_spad`` (50 chars in a 26-char
column).

Two rules the renderer keeps:

* **Never truncate.** If a table's natural width exceeds the target console
  width, the console is widened to fit instead of eliding cells. Component
  names and energy figures are what the reader came for; a wrapped log line is
  a smaller problem than a name cut to ``system_top_level.eyeriss.PE_col…``.
* **Log-safe by default.** ``rich`` falls back to an 80-column, colourless
  console when stdout is not a terminal, which would make redirected runs
  (``npuwattch ... > run.log``) *narrower* than the old fixed layout. Here a
  non-tty gets :data:`DEFAULT_LOG_WIDTH` instead, and colour is left to rich's
  own tty detection (off when redirected).

Names are shortened by :func:`strip_common_prefix`: the hierarchy prefix shared
by every row is removed and reported once in the caption, so the column carries
only the part that differs.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Iterable, List, Optional, Sequence, Tuple

from rich.console import Console
from rich.table import Table

__all__ = [
    "DEFAULT_LOG_WIDTH",
    "MIN_PREFIX_SAVING",
    "add_columns",
    "column_capacity",
    "make_table",
    "note",
    "print_table",
    "rule",
    "strip_common_prefix",
    "target_width",
]

#: Console width assumed when stdout is not a terminal (redirected to a file).
#: Matches the width of the ``=``/``-`` section rules the CLI has always used.
DEFAULT_LOG_WIDTH = 100

#: Only strip a shared name prefix when it buys at least this many columns —
#: below that the caption costs more attention than the saving is worth.
MIN_PREFIX_SAVING = 4


# ---------------------------------------------------------------------------
# console
# ---------------------------------------------------------------------------

def target_width() -> int:
    """Preferred console width: the terminal's when attached to one, else
    :data:`DEFAULT_LOG_WIDTH`. ``COLUMNS`` overrides both (rich honours it too,
    and CI/pytest set it)."""
    env = os.environ.get("COLUMNS")
    if env and env.isdigit() and int(env) > 0:
        return int(env)
    try:
        if sys.stdout.isatty():
            return max(60, os.get_terminal_size(sys.stdout.fileno()).columns)
    except (OSError, ValueError, AttributeError):
        pass
    return DEFAULT_LOG_WIDTH


def _console(width: int) -> Console:
    """A console writing to the *current* ``sys.stdout``.

    ``file`` is deliberately not passed: rich resolves ``sys.stdout`` at write
    time when it is ``None``, so a module-level console would keep writing to
    the real stdout under ``capsys``. ``highlight=False`` stops rich from
    recolouring numbers inside cells we have already formatted.
    """
    return Console(width=width, highlight=False, soft_wrap=False)


def _natural_width(table: Table) -> int:
    """Width the table wants if nothing constrains it."""
    probe = Console(width=10_000, file=io.StringIO(), highlight=False)
    return probe.measure(table).maximum


def print_table(table: Table) -> None:
    """Render *table*, widening the console rather than truncating any cell."""
    width = max(target_width(), _natural_width(table))
    _console(width).print(table)


def rule(char: str = "=") -> str:
    """A full-width separator line, for the section banners around tables."""
    return char * target_width()


# ---------------------------------------------------------------------------
# layout helpers
# ---------------------------------------------------------------------------

def _rendered_width(col_widths: Sequence[int]) -> int:
    """Total width of a bordered table whose columns hold *col_widths* chars.

    Each column costs its content plus one space of padding either side; the
    box then adds one vertical rule per column plus the closing one. Matches
    the geometry of :func:`make_table` — keep the two in step.
    """
    return sum(w + 2 for w in col_widths) + len(col_widths) + 1


def column_capacity(first_width: int, other_width: int,
                    available: Optional[int] = None) -> int:
    """How many ``other_width`` columns fit next to a fixed first column.

    Used to chunk the component x window matrix into groups that fit the
    console. Always at least 1: a single window column is printed even if it
    overflows, because dropping it would lose data.
    """
    limit = target_width() if available is None else available
    n = 1
    while _rendered_width([first_width] + [other_width] * (n + 1)) <= limit:
        n += 1
    return n


def strip_common_prefix(names: Sequence[str]) -> Tuple[List[str], str]:
    """Drop the dot-separated hierarchy prefix shared by every name.

    Returns ``(short_names, prefix)``; *prefix* is ``""`` when nothing was
    stripped, and the caller is expected to report a non-empty one in the
    table caption so the short names stay unambiguous.

    Only whole segments are removed, and never the last one — a component must
    keep a name. ``["a.b.x", "a.b.y"]`` becomes ``(["x", "y"], "a.b")``, while
    ``["core0.pe", "dram"]`` shares nothing and is returned unchanged.
    """
    if len(names) < 2:
        return list(names), ""
    split = [n.split(".") for n in names]
    shared: List[str] = []
    for i in range(min(len(p) for p in split) - 1):   # never the leaf segment
        seg = split[0][i]
        if all(p[i] == seg for p in split):
            shared.append(seg)
        else:
            break
    prefix = ".".join(shared)
    if len(prefix) < MIN_PREFIX_SAVING:
        return list(names), ""
    cut = len(prefix) + 1
    return [n[cut:] for n in names], prefix


# ---------------------------------------------------------------------------
# table construction
# ---------------------------------------------------------------------------

def make_table() -> Table:
    """An empty table in the house style.

    Notes that would otherwise become a rich ``caption`` are printed by the
    caller as ordinary ``[INFO]``-style lines instead: rich pads a caption out
    to the full table width, leaving trailing whitespace in redirected logs,
    and a note above the table is read before the rows it qualifies.
    """
    return Table()


def add_columns(table: Table, headers: Iterable[Tuple[str, str]]) -> None:
    """Add ``(header, justify)`` columns, none of which may wrap."""
    for header, justify in headers:
        table.add_column(header, justify=justify, no_wrap=True, overflow="fold")


def note(text: str) -> str:
    """Indent a qualifying note to sit under its ``[INFO]`` heading."""
    return f"       {text}"
