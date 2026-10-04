"""The report views of a run.

The package has two parts:

``tree``
    The instance hierarchy view. The CLI option ``--tree`` prints it as text.
``html``, ``svg``, and ``templates/report.html.j2``
    The HTML and JSON report (manual §8). ``build_context`` makes one dict of
    plain data from a §6 ``RunEnergy``. ``write_report`` renders the dict to
    one self-contained ``report.html`` and writes the same dict to
    ``report.json`` (§3.6). The pure functions of ``svg`` draw the charts as
    inline SVG.

This package contains only the parts that all harnesses use: the tree
structure, the renderers, and the tree builder for the flat description
format of the core. The harnesses own the builders for their formats:
``npuwattch_harness/pytorchsim/hierarchy.py`` reconstructs the hierarchy, and
``npuwattch_harness/timeloop/tree.py`` reads the hierarchy that the Accelergy
YAML declares.
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
