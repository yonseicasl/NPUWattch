"""Builder of the instance tree of a PyTorchSim run (the ``--tree`` view).

Each harness has its own tree builder, because the hierarchy data is
different in each source format. The outputs of PyTorchSim do not declare a
hierarchy. They contain only stats and configuration values. Thus this
builder makes the tree from the structure that the emitter used for the run.

The emitter names one component for each physical instance. The tree lists
the same instances. Thus the name of each leaf is the name of one row of the
energy summary:

    chip → core0 → array0 → pe / w_reg
                 → array1 → …
                 → vmem (+ tail) / vpu_spad          (elements of each core)
         → core1 → …
         → noc → icnt_xbar / icnt_buf / icnt_d2d     (compounds of the chip)

``npuwattch.report.tree`` contains the parts that all harnesses use:

* ``ArchTreeNode``: the tree structure.
* ``render_text``: the text view for the CLI.
* ``to_dict``: the data for the HTML report.
* ``tree_from_native``: the builder for the native description (§3.1).

The builder for an Accelergy description is in the Timeloop harness
(``npuwattch_harness/timeloop/tree.py``). That input format declares its hierarchy.
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
    """Build the tree of the physical instances of the description.

    ``resolved0`` contains the resolved elements of the MAC compound.
    ``aux_resolved`` contains the resolved elements of each other compound,
    with the compound name as the key.

    Return a ``report.tree.ArchTreeNode`` for ``EmittedArch.hierarchy``.
    """
    from npuwattch.report.tree import ArchTreeNode, component_label

    comps = {c["name"]: c for c in description["npuwattch"]["components"]}

    def leaf(element: str, rel: Any, comp_name: str) -> ArchTreeNode:
        comp = comps.get(comp_name, {})
        node = ArchTreeNode(
            element, count=int(rel.count),
            label=component_label(comp.get("class", rel.primitive),
                                  comp.get("attributes") or {}),
        )
        tail = comps.get(f"{comp_name}.tail")
        if tail is not None:          # the macros for the remaining capacity
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

    # Elements of the chip. The elements of the MAC compound go directly below
    # the root. The elements of each other compound go below a node that has
    # the name of the compound (for example, "noc").
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
