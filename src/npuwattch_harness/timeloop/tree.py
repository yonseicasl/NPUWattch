"""Accelergy/Timeloop instance-hierarchy tree builder (the ``--tree`` view).

**Builders are harness-owned**: this format's hierarchy is *declared* in the
Accelergy v0.4 YAML itself, and the Accelergy
description path is slated to move under ``--harness timeloop`` — so its tree
builder lives here already. It is the flattener's ``print_tree`` walk
re-expressed as data: same node kinds (Component / Container / structural /
Nothing), same instance arithmetic (accumulated mesh × component-list length),
rendered by the shared ``npuwattch.report.tree`` renderers.

When the Timeloop harness lands, its ingest attaches this tree to
``EmittedArch.hierarchy`` exactly like the PyTorchSim harness does
(``harness/pytorchsim/hierarchy.py``) — the CLI's ``--tree`` never knows which
harness produced the tree.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["tree_from_accelergy"]


def _storage_capacity(node) -> "str | None":
    """``32 KB`` for a storage component, from the same translation the
    ingest applies (Accelergy depth ÷ n_banks per bank) — so the declared
    tree shows the capacity the estimator will be sized to."""
    from ...report.tree import capacity_suffix
    from .vocabulary import attributes_for, primitive_for

    try:
        primitive = primitive_for(node.comp_class, node.subclass,
                                  node.attributes or {})
        if primitive not in ("sram", "regfile", "fifo"):
            return None
        warnings: list = []
        attrs = attributes_for(primitive, node.attributes or {},
                               component=node.name, warnings=warnings,
                               notes=[])
    except Exception:                       # the tree must never break the run
        return None
    if any("assuming" in w for w in warnings):
        return None                         # width/depth guessed: no capacity claim
    return capacity_suffix(attrs)


def tree_from_accelergy(input_yaml: Path):
    """Parse an Accelergy v0.4 description and convert its declared hierarchy
    into a ``report.tree.ArchTreeNode``."""
    from ...report.tree import ArchTreeNode
    from ...yaml_flattener_accelergy_v4 import AccelergyV04Flattener

    flattener = AccelergyV04Flattener()
    content = flattener.parse_yaml(str(input_yaml))
    flattener.tree_root = flattener.build_hierarchy_tree(content)

    def convert(node) -> ArchTreeNode:
        kind = node.node_type
        if kind == "Component":
            base, _suffix, list_len = flattener.interpret_component_list(node.name)
            mesh_x, mesh_y = node.calculate_accumulated_mesh()
            count = mesh_x * mesh_y * (list_len or 1)
            label = f"class: {node.comp_class}"
            if node.subclass:
                label += f"/{node.subclass}"
            cap = _storage_capacity(node)
            if cap:
                label += f" = {cap}"
            out = ArchTreeNode(base, count=count, label=label)
        elif kind == "Container":
            spatial = []
            for k in ("meshX", "meshY"):
                v = (node.spatial or {}).get(k)
                if v and v > 1:
                    spatial.append(f"{k}={v}")
            out = ArchTreeNode(node.name,
                               label=", ".join(["container"] + spatial))
        elif kind == "Nothing":
            out = ArchTreeNode(node.name, count=node.get_own_fanout(),
                               label="nothing")
        else:                                   # Parallel / Hierarchical / Pipelined
            out = ArchTreeNode(node.name)
        if not getattr(node, "enabled", True):
            out.label = (out.label + ", " if out.label else "") + "DISABLED"
        for child in node.children:
            out.add(convert(child))
        return out

    root = ArchTreeNode("architecture")
    for child in (flattener.tree_root.children
                  if flattener.tree_root is not None else []):
        root.add(convert(child))
    return root
