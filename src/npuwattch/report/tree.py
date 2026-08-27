"""Instance-hierarchy view — the tool-neutral tree structure + renderers.

Ownership: **tree builders are per-source adapters and belong to the source
format's owner** — this module keeps only what every source shares:

* ``ArchTreeNode`` — the one structure all builders converge on;
* ``render_text`` (CLI ``--tree``, ASCII box-drawing) and ``to_dict``
  (JSON-able, the R1 HTML report's collapsible tree) — the renderers;
* ``tree_from_native`` — the builder for the core's *own* format: a flat §3.1
  ``npuwattch:`` description, dot-grouped (``systolic.pe`` under ``systolic``,
  ``vmem.tail`` under ``vmem``) with counts and salient attributes.

Harness-owned builders (adapters over their formats' hierarchy information):

* PyTorchSim — no hierarchy is declared anywhere in its outputs, so
  ``harness/pytorchsim/hierarchy.py`` *reconstructs* the factorization at emit
  time and attaches it to ``EmittedArch.hierarchy``;
* Accelergy/Timeloop — the hierarchy is *declared* in the YAML;
  ``harness/timeloop/tree.py`` walks the flattener's parse.

The tree is a **presentation of the model**, not simulator output — its purpose
is letting a user check how their run was interpreted. The flat §3.1 format
itself stays hierarchy-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

__all__ = ["ArchTreeNode", "render_text", "to_dict", "tree_from_native",
           "component_label"]


@dataclass
class ArchTreeNode:
    """One level of the instance hierarchy.

    ``count`` is the multiplicity *at this level* (children multiply under it);
    ``label`` is a short human summary (class, geometry, template, …).
    """

    name: str
    count: int = 1
    label: str = ""
    children: List["ArchTreeNode"] = field(default_factory=list)

    def add(self, child: "ArchTreeNode") -> "ArchTreeNode":
        self.children.append(child)
        return child


def to_dict(node: ArchTreeNode) -> Dict[str, Any]:
    """JSON-able form (the HTML report's input)."""
    d: Dict[str, Any] = {"name": node.name}
    if node.count != 1:
        d["count"] = node.count
    if node.label:
        d["label"] = node.label
    if node.children:
        d["children"] = [to_dict(c) for c in node.children]
    return d


def render_text(node: ArchTreeNode, *, title: Optional[str] = None) -> str:
    """ASCII box-drawing rendering (the ``--tree`` CLI output)."""
    lines: List[str] = []
    if title:
        lines.append(title)

    def fmt(n: ArchTreeNode) -> str:
        s = n.name
        if n.count != 1:
            s += f" [×{n.count}]"
        if n.label:
            s += f"  ({n.label})"
        return s

    def walk(n: ArchTreeNode, prefix: str, is_last: bool, is_root: bool) -> None:
        if is_root:
            lines.append(fmt(n))
            child_prefix = ""
        else:
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}{fmt(n)}")
            child_prefix = prefix + ("    " if is_last else "│   ")
        for i, c in enumerate(n.children):
            walk(c, child_prefix, i == len(n.children) - 1, False)

    walk(node, "", True, True)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# builder: flat native description (§3.1) → dot-grouped tree
# ---------------------------------------------------------------------------

#: Attributes worth showing per class family, in display order.
_SALIENT = {
    "sram": ("mem_template", "mem_banks", "mem_depth_per_bank", "data_width"),
    "regfile": ("data_width", "mem_depth_per_bank"),
    "register_file": ("data_width", "mem_depth_per_bank"),
    "crossbar": ("net_inputs", "net_outputs", "data_width"),
    "d2dlink": ("data_width", "net_energy_per_bit_pJ"),
    "fpmac": ("exponent_bits", "mantissa_bits", "pipeline_stages"),
    "intmac": ("data_width_a", "data_width_b", "data_width_acc"),
    "mxfpmac": ("mx_input_format", "mx_block_elems"),
}


def component_label(comp_class: str, attrs: Mapping[str, Any]) -> str:
    """`class: X, k=v, …` with only that class's salient attributes."""
    parts = [f"class: {comp_class}"]
    for key in _SALIENT.get(str(comp_class), ()):
        v = attrs.get(key)
        if v is not None:
            parts.append(f"{key}={v}")
    return ", ".join(parts)


def tree_from_native(description: Mapping[str, Any]) -> ArchTreeNode:
    """A flat ``npuwattch:`` description → chip → (dot-grouped) components.

    The native format carries no hierarchy (deliberately), so this shows counts
    and nests along dotted names (``core0.array1.pe`` → ``core0`` → ``array1``
    → ``pe``); a ``<base>.tail`` capacity part nests under its ``<base>``
    component.
    """
    root = ArchTreeNode("chip")
    groups: Dict[str, ArchTreeNode] = {}
    by_name: Dict[str, ArchTreeNode] = {}
    for comp in (description.get("npuwattch") or {}).get("components", []):
        name = str(comp.get("name", "?"))
        attrs = comp.get("attributes") or {}
        parts = name.split(".")
        node = ArchTreeNode(
            parts[-1],
            count=int(comp.get("count", 1)),
            label=component_label(comp.get("class", "?"), attrs),
        )
        base, _, leaf = name.rpartition(".")
        if leaf == "tail" and base in by_name:
            by_name[base].add(node)          # capacity tail under its primary
        else:
            parent = root
            for i in range(len(parts) - 1):  # create group nodes along the path
                key = ".".join(parts[:i + 1])
                group = groups.get(key)
                if group is None:
                    group = groups[key] = parent.add(ArchTreeNode(parts[i]))
                parent = group
            parent.add(node)
        by_name[name] = node
    return root


# Harness-owned builders (see module docstring):
#   PyTorchSim reconstruction — harness/pytorchsim/hierarchy.py
#   Accelergy declared walk   — harness/timeloop/tree.py
