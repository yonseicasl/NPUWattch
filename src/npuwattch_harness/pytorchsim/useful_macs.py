"""The number of useful MAC operations of a PyTorchSim kernel.

TOGSim reports the active cycles of each systolic array, not how many PEs
hold a real weight in those cycles. A batch-1 convolution with few input
channels, or a matrix-vector product, keeps the array active with most PEs
empty. The useful MAC count comes from the operator and the tensor shapes
instead:

* the operator name is in the ``Enqueued kernel`` line of the TOGSim log
  (``operation: mm``, ``bmm``, ``convolution``, ...);
* the tensor shapes are in ``meta.txt`` (``attr`` 1 = input, 2 = output).

Supported operators:

| operator            | inputs                        | MACs                       |
|---------------------|-------------------------------|----------------------------|
| mm, matmul, addmm   | A[M,K], B[K,N]                | M·K·N                      |
| bmm, baddbmm        | A[B,M,K], B[B,K,N]            | B·M·K·N                    |
| convolution, conv2d | X[N,C,H,W], W[M,C/g,R,S]; out | N·M·P·Q·(C/g)·R·S          |

An Inductor name can carry a suffix (``mm_1``, ``mm_2`` in a backward
pass); the suffix is removed. For any other operator the function returns
None, and the harness falls back to charging every active PE cycle as a
MAC.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Optional, Sequence, Tuple

from .mac_config import MetaEntry

__all__ = ["base_operation", "useful_macs"]

_SUFFIX = re.compile(r"_\d+$")
_MM = {"mm", "matmul", "addmm", "linear", "mv"}
_BMM = {"bmm", "baddbmm"}
_CONV = {"convolution", "conv2d", "conv1d", "conv3d", "_convolution"}


def base_operation(operation: Optional[str]) -> Optional[str]:
    """``mm_2`` -> ``mm``. None stays None."""
    if not operation:
        return None
    return _SUFFIX.sub("", operation.strip())


def _inputs_outputs(entries: Iterable[MetaEntry]) -> Tuple[Sequence[Tuple[int, ...]], Sequence[Tuple[int, ...]]]:
    ins = [e.shape for e in entries if e.attr == 1]
    outs = [e.shape for e in entries if e.attr == 2]
    return ins, outs


def useful_macs(operation: Optional[str], entries: Iterable[MetaEntry]) -> Optional[int]:
    """Return the MAC count of the kernel, or None if the operator is unknown
    or the shapes do not fit the operator."""
    op = base_operation(operation)
    if op is None:
        return None
    entries = list(entries)
    ins, outs = _inputs_outputs(entries)
    if op in _MM:
        mats = [s for s in ins if len(s) == 2]
        for a in mats:
            for b in mats:
                if a is not b and a[1] == b[0]:
                    return a[0] * a[1] * b[1]
        return None
    if op in _BMM:
        mats = [s for s in ins if len(s) == 3]
        for a in mats:
            for b in mats:
                if a is not b and a[0] == b[0] and a[2] == b[1]:
                    return a[0] * a[1] * a[2] * b[2]
        return None
    if op in _CONV:
        # The output gives N, M, and the spatial size. The weight gives the
        # reduction C/g·R·S. Padding and stride do not change the MAC count.
        out = next((s for s in outs if len(s) >= 3), None)
        if out is None:
            return None
        spatial_out = math.prod(out[2:])
        candidates = [s for s in ins if len(s) == len(out) and s[0] == out[1]]
        if not candidates:
            return None
        w = candidates[0]
        reduction = math.prod(w[1:])
        return int(out[0] * out[1] * spatial_out * reduction)
    return None
