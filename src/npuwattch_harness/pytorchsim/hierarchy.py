"""PyTorchSim's instance-hierarchy tree builder (the ``--tree`` view).

**Builders are harness-owned**: a tree builder is a per-source adapter — its
job depends entirely on what hierarchy information the source format
carries, so it lives with that format's owner. PyTorchSim's outputs declare
no hierarchy at all (flat stats + config scalars), so this builder
*reconstructs* the structure the emitter interpreted the run as.

Per the "never lump" per-instance split, the emitter names one component
per physical instance, and the tree **enumerates** those instances so every
leaf matches one row of the energy summary by name:

    chip → core0 → array0 → pe / w_reg
                 → array1 → …
                 → vmem (+ tail) / vpu_spad          (per-core elements)
         → core1 → …
         → noc → icnt_xbar / icnt_buf / icnt_d2d     (per-chip compounds)

What is shared (``npuwattch.report.tree``, core) is only the tool-neutral part:
the ``ArchTreeNode`` structure and the two renderers (``render_text`` for the
CLI, ``to_dict`` for the R1 HTML report). ``tree_from_native`` stays core
(native §3.1 is the core's own format) and the Accelergy builder lives with the
Timeloop harness (``harness/timeloop/tree.py``), whose input format declares
its hierarchy.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["build_hierarchy"]


def build_hierarchy(
    description: Mapping[str, Any],
    resolved0: Mapping[str, Any],
    aux_resolved: Mapping[str, Mapping[str, Any]],
    *,
    num_cores: int,
    arrays_per_core: int,
):
    """The enumerated instance structure behind the per-instance description.
    ``resolved0`` is the MAC compound's resolved elements; ``aux_resolved``
    maps each aux compound name to its resolved elements. Returns a
    ``report.tree.ArchTreeNode`` for ``EmittedArch.hierarchy``.
    """
    from ...report.tree import ArchTreeNode, component_label

    comps = {c["name"]: c for c in description["npuwattch"]["components"]}

    def leaf(element: str, rel: Any, comp_name: str) -> ArchTreeNode:
        comp = comps.get(comp_name, {})
        node = ArchTreeNode(
            element, count=int(rel.count),
            label=component_label(comp.get("class", rel.primitive),
                                  comp.get("attributes") or {}),
        )
        tail = comps.get(f"{comp_name}.tail")
        if tail is not None:                     # capacity remainder macro-set
            node.add(ArchTreeNode(
                "tail",
                label=component_label(tail.get("class", "sram"),
                                      tail.get("attributes") or {})))
        return node

    def domain(rel: Any) -> str:
        return rel.per if rel.per in ("array", "core", "chip") else "chip"

    root = ArchTreeNode("chip")
    per_core_maps = [(None, resolved0)] + list(aux_resolved.items())
    for c in range(max(1, num_cores)):
        core = root.add(ArchTreeNode(f"core{c}"))
        for a in range(max(1, arrays_per_core)):
            array = core.add(ArchTreeNode(f"array{a}"))
            for ename, rel in resolved0.items():
                if domain(rel) == "array" and int(rel.count) > 0:
                    array.add(leaf(ename, rel, f"core{c}.array{a}.{ename}"))
            for _, relmap in aux_resolved.items():
                for ename, rel in relmap.items():
                    if domain(rel) == "array" and int(rel.count) > 0:
                        array.add(leaf(ename, rel, f"core{c}.array{a}.{ename}"))
        for _, relmap in per_core_maps:
            for ename, rel in relmap.items():
                if domain(rel) == "core" and int(rel.count) > 0:
                    core.add(leaf(ename, rel, f"core{c}.{ename}"))

    # per-chip elements: the MAC compound's directly under the root, each aux
    # compound's grouped under a node named after the compound (e.g. "noc").
    for ename, rel in resolved0.items():
        if domain(rel) == "chip" and int(rel.count) > 0:
            root.add(leaf(ename, rel, ename))
    for cname, relmap in aux_resolved.items():
        group = None
        for ename, rel in relmap.items():
            if domain(rel) == "chip" and int(rel.count) > 0:
                if group is None:
                    group = root.add(ArchTreeNode(cname))
                group.add(leaf(ename, rel, ename))
    return root
