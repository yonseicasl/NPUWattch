"""The instance hierarchy view: the tree structure and its renderers.

A tree builder is an adapter for one source format, and **the owner of the
source format owns the builder**. This module contains only the parts that
all sources use:

* ``ArchTreeNode``: the one structure that all builders make.
* ``render_text``: the renderer for the CLI option ``--tree``. It draws the
  tree as text with box-drawing characters.
* ``to_dict``: the renderer for JSON. The HTML report uses it for the
  collapsible tree.
* ``tree_from_native``: the builder for the format of the core, a flat §3.1
  ``npuwattch:`` description. It groups the components by the dots in their
  names (``systolic.pe`` under ``systolic``, ``vmem.tail`` under ``vmem``).
  It shows the counts and the important attributes.

The harnesses own the builders for their formats:

* PyTorchSim: the outputs of the simulator declare no hierarchy. Thus
  ``npuwattch_harness/pytorchsim/hierarchy.py`` *reconstructs* the hierarchy
  and attaches it to ``EmittedArch.hierarchy``.
* Accelergy/Timeloop: the YAML *declares* the hierarchy.
  ``npuwattch_harness/timeloop/tree.py`` makes the tree from the parsed YAML.

The tree **shows the model**. It is not simulator output. With the tree, you
can check how NPUWattch interpreted the run. The flat §3.1 format has no
hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

__all__ = ["ArchTreeNode", "render_text", "to_dict", "tree_from_native",
           "capacity_suffix",
           "component_label"]


@dataclass
class ArchTreeNode:
    """One level of the instance hierarchy.

    ``count`` is the number of instances *at this level*. The count of a
    child multiplies with the count of its parent. ``label`` is a short
    summary, for example the class, the geometry, or the template.
    """

    name: str
    count: int = 1
    label: str = ""
    children: List["ArchTreeNode"] = field(default_factory=list)

    def add(self, child: "ArchTreeNode") -> "ArchTreeNode":
        self.children.append(child)
        return child


def to_dict(node: ArchTreeNode) -> Dict[str, Any]:
    """Return the tree as a dict for JSON. The HTML report uses this dict."""
    d: Dict[str, Any] = {"name": node.name}
    if node.count != 1:
        d["count"] = node.count
    if node.label:
        d["label"] = node.label
    if node.children:
        d["children"] = [to_dict(c) for c in node.children]
    return d


def render_text(node: ArchTreeNode, *, title: Optional[str] = None) -> str:
    """Return the tree as text with box-drawing characters. The CLI option
    ``--tree`` prints this text."""
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
# Builder: flat description (§3.1) → tree grouped by dotted names
# ---------------------------------------------------------------------------

#: Class -> the attributes that the label shows, in display order.
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


def capacity_suffix(attrs: Mapping[str, Any]) -> Optional[str]:
    """Return the total capacity of a storage component, for example
    ``32 KB``.

    The capacity is banks x words per bank x bits per word. The estimator
    uses this total. Thus an incorrect depth in the description is easy to
    see in the tree.
    """
    try:
        depth = int(attrs.get("mem_depth_per_bank") or 0)
        width = int(attrs.get("data_width") or 0)
        banks = int(attrs.get("mem_banks") or 1)
    except (TypeError, ValueError):
        return None
    bits = depth * width * banks
    if bits <= 0:
        return None
    if bits % (8 * 1024 * 1024) == 0:
        return f"{bits // (8 * 1024 * 1024)} MB"
    if bits % (8 * 1024) == 0:
        return f"{bits // (8 * 1024)} KB"
    if bits % 8 == 0:
        return f"{bits // 8} B"
    return f"{bits} bit"


def component_label(comp_class: str, attrs: Mapping[str, Any]) -> str:
    """Return the label `class: X, k=v, …` of a component.

    The label shows only the attributes that ``_SALIENT`` lists for the
    class. The label of a storage class also shows the total capacity.
    """
    parts = [f"class: {comp_class}"]
    for key in _SALIENT.get(str(comp_class), ()):
        v = attrs.get(key)
        if v is not None:
            parts.append(f"{key}={v}")
    label = ", ".join(parts)
    if str(comp_class) in ("sram", "regfile", "register_file"):
        cap = capacity_suffix(attrs)
        if cap:
            label += f" = {cap}"
    return label


def tree_from_native(description: Mapping[str, Any]) -> ArchTreeNode:
    """Make a tree from a flat ``npuwattch:`` description.

    The description has no hierarchy. This is a decision of the format. Thus
    the tree shows the counts and uses the dotted names for the levels:
    ``core0.array1.pe`` → ``core0`` → ``array1`` → ``pe``. A ``<base>.tail``
    component, which holds the remaining capacity, goes below its ``<base>``
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
            by_name[base].add(node)          # the tail goes below its base
        else:
            parent = root
            for i in range(len(parts) - 1):  # make the group nodes of the path
                key = ".".join(parts[:i + 1])
                group = groups.get(key)
                if group is None:
                    group = groups[key] = parent.add(ArchTreeNode(parts[i]))
                parent = group
            parent.add(node)
        by_name[name] = node
    return root


# The builders that the harnesses own (see the module docstring):
#   PyTorchSim: npuwattch_harness/pytorchsim/hierarchy.py
#   Accelergy/Timeloop: npuwattch_harness/timeloop/tree.py
