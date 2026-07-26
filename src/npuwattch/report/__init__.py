"""Report-side views of a run (workstream C / R1).

Two layers: ``tree`` (the instance-hierarchy view — the CLI renders it as
ASCII via ``--tree``) and the HTML/JSON report itself (``html`` + ``svg`` +
``templates/report.html.j2``, manual §8): ``build_context`` produces one
plain-data dict from a §6 ``RunEnergy``, ``write_report`` renders it to a
single self-contained ``report.html`` and mirrors the same dict into
``report.json`` (§3.6). Charts are pure-function inline SVG (``svg``).

This package holds only the tool-neutral parts (structure, renderers, and the
builder for the core's own flat native format). Per-source builders are
harness-owned: ``harness/pytorchsim/hierarchy.py`` (reconstruction) and
``harness/timeloop/tree.py`` (Accelergy declared hierarchy).
"""

from .html import build_context, render_html, write_report
from .tree import (
    ArchTreeNode,
    component_label,
    render_text,
    to_dict,
    tree_from_native,
)

__all__ = [
    "ArchTreeNode",
    "build_context",
    "component_label",
    "render_html",
    "render_text",
    "to_dict",
    "tree_from_native",
    "write_report",
]
