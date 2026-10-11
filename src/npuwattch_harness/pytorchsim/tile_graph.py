"""The raw tile graph of a PyTorchSim kernel (``outputs/<hash>/*_tog.py``).

PyTorchSim compiles a kernel to a loop nest of tile operations. The MLIR
pass ``test-tile-operation-graph`` writes this loop nest as a Python dict
literal, ``<key>_tog.py``, in the kernel directory. The frontend expands it
into ``tile_graph.onnx``, which TOGSim replays.

The file has these node types:

* ``root``: the top node.
* ``loopNode``: a loop with ``loop_start``, ``loop_end``, ``loop_step``.
* ``ComputeNode``: one tile operation. ``compute_type`` is 0 for a vector
  operation, 1 for a GEMM tile, and 2 for a weight preload.
* ``DMANode``: a data transfer. This module does not use it.

The number of executions of a compute node is the product of the trip
counts of the loops above it. TOGSim counts each execution as one ``COMP``
instruction: ``compute_type > 0`` in the GEMM count, ``compute_type == 0``
in the vector count.

The gem5 sample program (``*_sample``) executes each compute node one time,
in the order of this file, and dumps the gem5 statistics after each one.
The frontend takes the ``numCycles`` of each dump as the cycle count of that
node (``Simulator/simulator.py``, ``CycleSimulator.compile_and_simulate``:
one entry for each dump, without the last dump, popped onto the compute
nodes in file order). ``activity.py`` uses the same order to scale the
instruction counts of each dump by the executions of its node.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

__all__ = ["ComputeNode", "TileGraph", "find_tile_graph", "read_tile_graph"]

VECTOR, GEMM, PRELOAD = 0, 1, 2


@dataclass(frozen=True)
class ComputeNode:
    node_id: int
    compute_type: int          # 0 vector, 1 GEMM, 2 weight preload
    executions: int            # dynamic execution count in the kernel


@dataclass(frozen=True)
class TileGraph:
    path: Path
    nodes: List[ComputeNode]   # in file (depth-first) order

    @property
    def gemm_executions(self) -> int:
        """The COMP GEMM count of TOGSim: preloads and GEMM tiles."""
        return sum(n.executions for n in self.nodes if n.compute_type > 0)

    @property
    def vector_executions(self) -> int:
        return sum(n.executions for n in self.nodes if n.compute_type == 0)


def find_tile_graph(kernel_dir: Path) -> Optional[Path]:
    """Return the ``*_tog.py`` file of a kernel directory, or None."""
    files = sorted(Path(kernel_dir).glob("*_tog.py"))
    return files[0] if files else None


def _trip_count(node: Dict) -> int:
    start = int(node.get("loop_start", 0))
    end = int(node.get("loop_end", 0))
    step = int(node.get("loop_step", 1)) or 1
    return max(1, math.ceil((end - start) / step))


def read_tile_graph(path: Path) -> TileGraph:
    """Read a ``*_tog.py`` file and return its compute nodes in order.

    The file is ``graph = {<int>: {...}, ...}``. The function evaluates the
    literal only (``ast.literal_eval``); it does not execute the file.
    """
    text = Path(path).read_text(encoding="utf-8")
    body = text.split("=", 1)[1] if "=" in text.split("\n", 1)[0] else text
    graph = ast.literal_eval(body.strip())
    nodes: List[ComputeNode] = []

    def walk(node_id: int, mult: int) -> None:
        node = graph[node_id]
        kind = node.get("node_name")
        if kind == "loopNode":
            mult *= _trip_count(node)
        elif kind == "ComputeNode":
            nodes.append(ComputeNode(node_id=int(node_id),
                                     compute_type=int(node.get("compute_type", 0)),
                                     executions=mult))
        for child in node.get("children", []):
            walk(child, mult)

    roots = [k for k, v in graph.items() if not v.get("parents")]
    for r in sorted(roots):
        walk(r, 1)
    return TileGraph(path=Path(path), nodes=nodes)
