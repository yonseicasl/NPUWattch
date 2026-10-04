"""Console table rendering.

Each CLI table uses this module. The module **measures the column widths
from the data**. A fixed column width is not sufficient, because a
hierarchical component name can be long. For example,
``system_top_level.eyeriss.PE_column.PE.weights_spad`` has 50 characters.

The renderer obeys two rules:

* **No truncation.** If a table is wider than the target console width, the
  renderer makes the console wider. It does not cut a cell, because the
  reader needs the full component names and energy values. A wrapped log
  line is a smaller problem than a name cut to
  ``system_top_level.eyeriss.PE_col…``.
* **Safe output to a log file.** If stdout is not a terminal, ``rich`` uses
  a console of 80 columns, which is too narrow for a redirected run
  (``npuwattch ... > run.log``). This module uses :data:`DEFAULT_LOG_WIDTH`
  instead. ``rich`` controls the colour and sets it off for redirected output.

:func:`strip_common_prefix` makes the names shorter. It removes the hierarchy
prefix that all rows share. The caller prints the prefix one time above the
table. Thus the column contains only the part that is different.
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

#: The console width if stdout is not a terminal (output redirected to a file).
#: It is equal to the width of the ``=``/``-`` section rules of the CLI.
DEFAULT_LOG_WIDTH = 100

#: Remove a shared name prefix only if it saves this number of columns or
#: more. For a smaller saving, the added note is not worth the space.
MIN_PREFIX_SAVING = 4


# ---------------------------------------------------------------------------
# console
# ---------------------------------------------------------------------------

def target_width() -> int:
    """Return the preferred console width.

    If stdout is a terminal, the width is the terminal width. If not, it is
    :data:`DEFAULT_LOG_WIDTH`. ``COLUMNS`` has priority over the two. ``rich``
    also obeys ``COLUMNS``, and CI and pytest set it."""
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
    """Return a console that writes to the *current* ``sys.stdout``.

    ``file`` is not given, on purpose. If ``file`` is ``None``, rich finds
    ``sys.stdout`` at write time. A module-level console keeps the initial
    stdout, which is incorrect under ``capsys``. ``highlight=False`` prevents
    a colour change of the numbers in cells that are already formatted.
    """
    return Console(width=width, highlight=False, soft_wrap=False)


def _natural_width(table: Table) -> int:
    """Return the width of the table without a width limit."""
    probe = Console(width=10_000, file=io.StringIO(), highlight=False)
    return probe.measure(table).maximum


def print_table(table: Table) -> None:
    """Print *table*. Make the console wider if necessary. Do not cut a cell."""
    width = max(target_width(), _natural_width(table))
    _console(width).print(table)


def rule(char: str = "=") -> str:
    """Return a full-width separator line for the section banners."""
    return char * target_width()


# ---------------------------------------------------------------------------
# layout helpers
# ---------------------------------------------------------------------------

def _rendered_width(col_widths: Sequence[int]) -> int:
    """Return the total width of a bordered table with *col_widths* columns.

    Each column uses its content plus one space of padding on each side. The
    box adds one vertical rule for each column, and one more to close the
    table. This agrees with the geometry of :func:`make_table`. Keep the two
    the same.
    """
    return sum(w + 2 for w in col_widths) + len(col_widths) + 1


def column_capacity(first_width: int, other_width: int,
                    available: Optional[int] = None) -> int:
    """Return the number of ``other_width`` columns that fit after a fixed
    first column.

    The component x window matrix uses this to divide its columns into groups
    that fit the console. The result is 1 or more. One window column is
    printed even if it is too wide, because the table must show all the data.
    """
    limit = target_width() if available is None else available
    n = 1
    while _rendered_width([first_width] + [other_width] * (n + 1)) <= limit:
        n += 1
    return n


def strip_common_prefix(names: Sequence[str]) -> Tuple[List[str], str]:
    """Remove the dot-separated hierarchy prefix that all names share.

    Returns ``(short_names, prefix)``. *prefix* is ``""`` if nothing was
    removed. The caller must print a non-empty prefix near the table, thus
    the short names stay clear.

    Only complete segments are removed. The last segment always stays,
    because a component must keep a name. ``["a.b.x", "a.b.y"]`` becomes
    ``(["x", "y"], "a.b")``. ``["core0.pe", "dram"]`` shares no prefix and
    does not change.
    """
    if len(names) < 2:
        return list(names), ""
    split = [n.split(".") for n in names]
    shared: List[str] = []
    for i in range(min(len(p) for p in split) - 1):   # not the last segment
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
    """Return an empty table in the standard style.

    A table has no rich ``caption``. The caller prints a note as an
    ``[INFO]``-style line above the table. Rich pads a caption to the full
    table width, which puts trailing spaces in redirected logs. Also, the
    reader sees a note above the table before the rows that it applies to.
    """
    return Table()


def add_columns(table: Table, headers: Iterable[Tuple[str, str]]) -> None:
    """Add ``(header, justify)`` columns. The columns do not wrap."""
    for header, justify in headers:
        table.add_column(header, justify=justify, no_wrap=True, overflow="fold")


def note(text: str) -> str:
    """Indent a note, to put it below its ``[INFO]`` heading."""
    return f"       {text}"
