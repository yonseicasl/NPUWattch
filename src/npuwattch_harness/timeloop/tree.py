"""Hierarchy tree of an Accelergy/Timeloop architecture (the ``--tree`` view).

Each harness makes its own tree. For this harness, the Accelergy v0.4 file
declares the hierarchy. This module changes the hierarchy tree of the
flattener into ``report.tree.ArchTreeNode`` data.

The node kinds are Component, Container, structural, and Nothing. The instance
count of a component is the accumulated mesh x the length of the component
list.

:mod:`.ingest` attaches the tree to ``EmittedArch.hierarchy``. The PyTorchSim
harness does the same (``npuwattch_harness/pytorchsim/hierarchy.py``). The shared
``npuwattch.report.tree`` module prints the tree. Thus the ``--tree`` option
of the CLI is independent of the harness.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["tree_from_accelergy"]

#: The warnings of the storage rule that tell that the word width or the
#: depth is an assumed value (``vocabulary._storage_rule``).
_ASSUMED_SIZE = frozenset({"NW-7302", "NW-7304"})


def _storage_capacity(node) -> "str | None":
    """Return the capacity text of a storage component, for example ``32 KB``.

    The function uses the same translation as the ingest: the depth of each
    bank is the Accelergy depth / n_banks. Thus the tree shows the capacity
    that the estimator models.
    """
    from npuwattch.report.tree import capacity_suffix
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
    except Exception:                       # a tree error must not stop the run
        return None
    if any(getattr(w, "code", None) in _ASSUMED_SIZE for w in warnings):
        return None                         # assumed width or depth: show no capacity
    return capacity_suffix(attrs)


def tree_from_accelergy(input_yaml: Path):
    """Read an Accelergy v0.4 architecture file. Return its declared
    hierarchy as a ``report.tree.ArchTreeNode``."""
    from npuwattch.report.tree import ArchTreeNode
    from .accelergy_flattener import AccelergyV04Flattener

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
        else:                                   # Parallel, Hierarchical, or Pipelined
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
