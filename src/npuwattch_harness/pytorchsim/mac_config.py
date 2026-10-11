"""Infer the MAC configuration of a systolic array from PyTorchSim artifacts.

PyTorchSim can change the hardware configuration at runtime. Thus a static
description does not give the datatype parameters of the MAC. This module reads
them from the **codegen artifacts** of each compiled kernel:

    outputs/<hash>/meta.txt      torch dtype + shape of every kernel arg
    outputs/<hash>/*.mlir        func.func @kernel signature + `linalg.matmul`

The activity trace (``m5out/stats.txt`` and the TOGSim log) is a *different*
input. It supplies the activity counts of each window for the projection. It
does not give the bit widths of the MAC. See ``docs/COMPOUND_SCHEMA.md`` §2.1.

The parameters that the module gets for each kernel:

============ ============================================================
MAC param    source (primary -> cross-check)
============ ============================================================
operand      ``linalg.matmul ins`` element type -> meta.txt inputs
             -> func.func signature (to find a failed int lowering)
accumulator  ``linalg.matmul outs`` element type -> meta.txt output buffer
lanes        run configuration (``vpu_num_lanes`` / ``systolicArrayWidth``)
pipeline     not in the artifacts (the array has opLat=1); assumed, default 2
============ ============================================================

``pipeline_stages`` is the only assumed datatype parameter. The module reads
all other parameters from the kernel. If the ``outputs/`` artifacts are absent,
the accumulator width comes from a fallback rule.

Limitation: some PyTorchSim builds cannot lower an integer matmul. An ``int8``
GEMM then gives a kernel with an ``i8`` func signature, an ``f32``
``linalg.matmul`` (a scalar emulation), and no ``meta.txt``. The module finds
this disagreement and selects the primitive from the tensor (int) dtype. It
sets the confidence to low and gives a warning that the energy is not
calibrated.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from npuwattch.diagnostics import NPUWattchError, warning

from .definitions import VOCABULARY

__all__ = [
    "DType",
    "MacConfig",
    "MacInferenceError",
    "NotAMatmulKernel",
    "infer_mac_config",
    "infer_mac_config_from_dir",
    "parse_meta",
    "parse_mlir",
]


# ---------------------------------------------------------------------------
# Datatypes
# ---------------------------------------------------------------------------

class MacInferenceError(NPUWattchError, ValueError):
    """The artifacts are present, but they do not give a MAC configuration."""


class NotAMatmulKernel(MacInferenceError):
    """The kernel has no ``linalg.matmul``. It is not a MAC kernel, thus skip it."""


@dataclass(frozen=True)
class DType:
    """A scalar numeric type. MLIR and torch spellings map to one canonical name."""

    kind: str                       # "float" | "int"
    bits: int                       # total width in bits
    canonical: str                  # "f32", "bf16", "i8", ...
    exp_bits: Optional[int] = None  # float only
    mantissa_bits: Optional[int] = None
    signed: bool = True             # int only (ignored for floats)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.canonical


def parse_dtype(token: str) -> DType:
    """Convert an MLIR element type or a torch dtype spelling into a ``DType``.

    The vocabulary table supplies the dtype spellings and the float formats.
    """
    raw = token.strip()
    key = raw.lower()
    canonical = VOCABULARY.dtypes.get(key, key)

    if canonical in VOCABULARY.float_formats:
        bits, exp, mant = VOCABULARY.float_formats[canonical]
        return DType("float", bits, canonical, exp_bits=exp, mantissa_bits=mant)

    # Integer: MLIR ``i8``/``i32`` (no sign), or torch ``iN``/``uN``.
    m = re.fullmatch(r"([iu])(\d+)", canonical)
    if m:
        signed = m.group(1) == "i"
        bits = int(m.group(2))
        return DType("int", bits, canonical, signed=signed)

    raise MacInferenceError.nw(6101, token=token)


# ---------------------------------------------------------------------------
# MacConfig: the result of the inference
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MacConfig:
    """The MAC primitive of one kernel and its attributes.

    ``primitive_config`` uses NPUWattch attribute names (``npuwattch.naming``):

    - ``fpmac``: ``number_format``, ``data_width``, ``exponent_bits``,
      ``mantissa_bits``, ``pipeline_stages``. The accumulation format is
      internal to the RTL, thus ``accum_dtype`` is only information.
    - ``intmac``: ``number_format``, ``data_width_a``, ``data_width_b``,
      ``data_width_out``, ``data_width_acc``, ``pipeline_stages``.
    """

    primitive: str                         # "fpmac" | "intmac"
    primitive_config: Dict[str, int]
    operand_dtype: DType
    accum_dtype: DType
    lanes: int
    pipeline_stages: int
    confidence: str                        # "high" | "low"
    gemm_shape: Optional[Tuple[int, int, int]] = None   # (M, K, N) tile
    warnings: Tuple[str, ...] = ()
    provenance: Dict[str, str] = field(default_factory=dict)


def fallback_fp32_mac_config(lanes: int, *, pipeline_stages: int = 2) -> "MacConfig":
    """Return the fallback without evidence: an fp32 (e8m23) datapath, confidence 'low'.

    Use it if a run has NO MAC kernel. Then no kernel can supply a dtype, but
    the non-MAC windows need one to resolve the templated vfu and spads
    elements. The fp32 format is also the fallback of the SFU
    (§_SFU_FALLBACK_EXP_MANT). The caller must give a WARNING, because no run
    evidence supports this assumption.
    """
    operand = parse_dtype("f32")
    primitive, cfg = _select_primitive(operand, operand, lanes, pipeline_stages,
                                       lowering_ok=True)
    return MacConfig(
        primitive=primitive,
        primitive_config=cfg,
        operand_dtype=operand,
        accum_dtype=operand,
        lanes=lanes,
        pipeline_stages=pipeline_stages,
        confidence="low",
        provenance={"source": "fallback_fp32 (no MAC kernel in the run)"},
    )


# ---------------------------------------------------------------------------
# meta.txt parsing
# ---------------------------------------------------------------------------

# arg0_1=(1, torch.float32, torch.Size([1024, 1024]))
_META_LINE = re.compile(
    r"^(?P<name>\w+)=\(\s*(?P<attr>\d+)\s*,\s*"
    r"(?P<dtype>torch\.\w+)\s*,\s*"
    r"torch\.Size\(\[(?P<shape>[\d,\s]*)\]\)\s*\)\s*$"
)


@dataclass(frozen=True)
class MetaEntry:
    name: str
    attr: int                  # 1 = input or parameter, 2 = computed or output buffer
    dtype: DType
    shape: Tuple[int, ...]


def parse_meta(text: str) -> List[MetaEntry]:
    """Parse a ``meta.txt`` into typed entries. Skip the lines that do not parse."""
    entries: List[MetaEntry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _META_LINE.match(line)
        if not m:
            continue
        shape_str = m.group("shape").strip()
        shape = tuple(
            int(x) for x in shape_str.split(",") if x.strip()
        ) if shape_str else ()
        entries.append(
            MetaEntry(
                name=m.group("name"),
                attr=int(m.group("attr")),
                dtype=parse_dtype(m.group("dtype")),
                shape=shape,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# MLIR parsing
# ---------------------------------------------------------------------------

# The dimensions and the element type in a memref, for example
# "128x256xf32, 1" or "16384xi8".
_MEMREF = re.compile(r"memref<([^>]*)>")
_FUNC_KERNEL = re.compile(r"func\.func\s+@kernel\s*\(([^)]*)\)")
# ins(...) and outs(...) can be on different lines, thus DOTALL is necessary.
_MATMUL = re.compile(
    r"linalg\.matmul\s+ins\((?P<ins>[^)]*)\)\s*outs\((?P<outs>[^)]*)\)",
    re.DOTALL,
)


def _memrefs(fragment: str) -> List[Tuple[Tuple[int, ...], DType]]:
    """Return the shape and element type of each ``memref<...>`` in the text."""
    out: List[Tuple[Tuple[int, ...], DType]] = []
    for inner in _MEMREF.findall(fragment):
        body = inner.split(",", 1)[0].strip()        # remove the memory space and layout
        parts = body.split("x")
        dims = tuple(int(p) for p in parts[:-1] if p.strip().isdigit())
        out.append((dims, parse_dtype(parts[-1].strip())))
    return out


@dataclass(frozen=True)
class MlirMatmul:
    func_operand_types: List[DType]                  # each memref element type in the signature
    ins: List[Tuple[Tuple[int, ...], DType]]         # matmul input operands
    outs: Tuple[Tuple[int, ...], DType]              # matmul output (accumulator)


def parse_mlir(text: str) -> MlirMatmul:
    """Get the operand types of the func signature and the ``linalg.matmul`` operands."""
    mm = _MATMUL.search(text)
    if not mm:
        raise NotAMatmulKernel.nw(6102)

    ins = _memrefs(mm.group("ins"))
    outs_list = _memrefs(mm.group("outs"))
    if len(ins) < 2 or not outs_list:
        raise MacInferenceError.nw(6103, ins=len(ins), outs=len(outs_list))

    func_types: List[DType] = []
    fm = _FUNC_KERNEL.search(text)
    if fm:
        func_types = [dt for _, dt in _memrefs(fm.group(1))]

    return MlirMatmul(func_operand_types=func_types, ins=ins, outs=outs_list[0])


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def _fallback_int_acc_width(operand_bits: int, lanes: int) -> int:
    """Fallback: data_width_acc = 2*bitwidth + ceil(log2(lanes)) (COMPOUND_SCHEMA §2.1)."""
    lanes = max(1, lanes)
    return 2 * operand_bits + math.ceil(math.log2(lanes)) if lanes > 1 else 2 * operand_bits


#: Minimum ``pipeline_stages`` of the fpmac that the RTL generator makes.
#: ``pipeline_stages`` is the total latency. The fpmac contains an fpmul and an
#: fpadd, and each needs two stages, thus the minimum is 4 (mul 2 + add 2).
#: The intmac range is 2 to 5, thus only the fpmac has this clamp.
_FPMAC_MIN_STAGES = 4


def _select_primitive(
    operand: DType,
    accum: DType,
    lanes: int,
    pipeline_stages: int,
    lowering_ok: bool,
) -> Tuple[str, Dict[str, int]]:
    if operand.kind == "float":
        assert operand.exp_bits is not None and operand.mantissa_bits is not None
        return "fpmac", {
            "number_format": "fp",
            "data_width": 1 + operand.exp_bits + operand.mantissa_bits,
            "exponent_bits": operand.exp_bits,
            "mantissa_bits": operand.mantissa_bits,
            "pipeline_stages": max(pipeline_stages, _FPMAC_MIN_STAGES),
        }
    if operand.kind == "int":
        if lowering_ok and accum.kind == "int":
            acc_width = accum.bits
        else:
            acc_width = _fallback_int_acc_width(operand.bits, lanes)
        return "intmac", {
            "number_format": "int",
            "data_width_a": operand.bits,
            "data_width_b": operand.bits,
            "data_width_out": acc_width,
            "data_width_acc": acc_width,
            "pipeline_stages": pipeline_stages,
        }
    raise MacInferenceError.nw(6104, kind=operand.kind)


def infer_mac_config(
    mlir_text: str,
    lanes: int,
    *,
    meta_text: Optional[str] = None,
    pipeline_stages: int = 2,
    kernel: str = "kernel",
) -> MacConfig:
    """Infer a ``MacConfig`` from the MLIR of one kernel and, optionally, its meta.txt.

    ``lanes`` is the width of the systolic array (``vpu_num_lanes`` /
    ``systolicArrayWidth``). It is an architecture parameter from the run
    configuration, not from the kernel. ``kernel`` is the name (the hash) of
    the kernel in the warnings.
    """
    if lanes < 1:
        raise MacInferenceError.nw(6105, lanes=lanes)

    mlir = parse_mlir(mlir_text)
    meta = parse_meta(meta_text) if meta_text else []
    warnings: List[str] = []
    provenance: Dict[str, str] = {}

    # --- operand dtype ---------------------------------------------------
    ins_types = [dt for _, dt in mlir.ins]
    if len({dt.canonical for dt in ins_types}) > 1:
        warnings.append(warning(
            6106, kernel=kernel,
            dtypes=", ".join(dt.canonical for dt in ins_types)))
    matmul_operand = ins_types[0]

    func_int_types = [dt for dt in mlir.func_operand_types if dt.kind == "int"]
    lowering_ok = True
    if matmul_operand.kind == "float" and func_int_types:
        # The build did not lower the int matmul and used scalar f32 instead.
        # The tensor dtype of the kernel (func signature) is the correct operand type.
        operand = min(func_int_types, key=lambda d: d.bits)
        lowering_ok = False
        warnings.append(warning(
            6107, kernel=kernel, matmul_dtype=matmul_operand.canonical,
            tensor_dtype=operand.canonical))
        provenance["operand_dtype"] = "mlir:func.func signature (matmul disagreed)"
    else:
        operand = matmul_operand
        provenance["operand_dtype"] = "mlir:linalg.matmul ins"

    # Compare the operand dtype with the meta.txt inputs (attr 1).
    meta_inputs = [e for e in meta if e.attr == 1]
    if meta_inputs:
        meta_in_canon = {e.dtype.canonical for e in meta_inputs}
        if lowering_ok and operand.canonical not in meta_in_canon:
            warnings.append(warning(
                6108, kernel=kernel, dtype=operand.canonical,
                meta_dtypes=sorted(meta_in_canon)))
        provenance["operand_dtype_crosscheck"] = "meta.txt inputs (attr=1)"

    # --- accumulator dtype ----------------------------------------------
    if lowering_ok:
        accum = mlir.outs[1]
        provenance["accum_dtype"] = "mlir:linalg.matmul outs"
    else:
        # The matmul outs type is also the incorrect f32. Use the fallback rule.
        acc_bits = _fallback_int_acc_width(operand.bits, lanes)
        accum = DType("int", acc_bits, f"i{acc_bits}", signed=True)
        provenance["accum_dtype"] = "fallback rule 2*bits+ceil(log2(lanes))"

    # --- primitive + params ----------------------------------------------
    primitive, cfg = _select_primitive(
        operand, accum, lanes, pipeline_stages, lowering_ok
    )
    provenance["lanes"] = "caller (config vpu_num_lanes / systolicArrayWidth)"
    provenance["pipeline_stages"] = "assumed (opLat=1 array; not derivable)"

    # --- gemm tile shape (for activity calibration and the report) -------
    gemm_shape: Optional[Tuple[int, int, int]] = None
    a_shape, _ = mlir.ins[0]
    b_shape, _ = mlir.ins[1]
    if len(a_shape) == 2 and len(b_shape) == 2:
        gemm_shape = (a_shape[0], a_shape[1], b_shape[1])  # (M, K, N)
        if a_shape[1] != b_shape[0]:
            warnings.append(warning(6109, kernel=kernel, a_shape=a_shape,
                                    b_shape=b_shape))

    return MacConfig(
        primitive=primitive,
        primitive_config=cfg,
        operand_dtype=operand,
        accum_dtype=accum,
        lanes=lanes,
        pipeline_stages=pipeline_stages,
        confidence="high" if lowering_ok else "low",
        gemm_shape=gemm_shape,
        warnings=tuple(warnings),
        provenance=provenance,
    )


def _find_kernel_mlir(kernel_dir: Path) -> Path:
    """Return the kernel MLIR ``c<hash>.mlir``, not ``*_llvm.mlir`` or ``*_sample*.mlir``."""
    candidates = [
        p for p in sorted(kernel_dir.glob("*.mlir"))
        if not p.stem.endswith(("_llvm", "_sample", "_sample_llvm"))
    ]
    if not candidates:
        raise MacInferenceError.nw(6110, path=kernel_dir)
    # Use the file that has a linalg.matmul. More than one such file is an error.
    matmul = [
        p for p in candidates
        if "linalg.matmul" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    if len(matmul) > 1:
        raise MacInferenceError.nw(
            6111, path=kernel_dir, count=len(matmul),
            files=", ".join(p.name for p in matmul))
    if matmul:
        return matmul[0]
    return candidates[0]


def infer_mac_config_from_dir(
    kernel_dir: Path,
    lanes: int,
    *,
    pipeline_stages: int = 2,
    kernel: Optional[str] = None,
) -> MacConfig:
    """Infer from an ``outputs/<hash>/`` directory. Read meta.txt and the kernel MLIR.

    The default of ``kernel`` (the name in the warnings) is the directory
    name, which is the kernel hash.
    """
    kernel_dir = Path(kernel_dir)
    mlir_path = _find_kernel_mlir(kernel_dir)
    meta_path = kernel_dir / "meta.txt"
    meta_text = (
        meta_path.read_text(encoding="utf-8") if meta_path.is_file() else None
    )
    return infer_mac_config(
        mlir_path.read_text(encoding="utf-8"),
        lanes,
        meta_text=meta_text,
        pipeline_stages=pipeline_stages,
        kernel=kernel if kernel is not None else kernel_dir.name,
    )


# ---------------------------------------------------------------------------
# Fallback with meta.txt only (some run bundles have no kernel MLIR)
# ---------------------------------------------------------------------------

def infer_mac_config_from_meta(
    meta_text: str,
    lanes: int,
    *,
    pipeline_stages: int = 2,
    kernel: str = "kernel",
) -> MacConfig:
    """Infer a ``MacConfig`` from ``meta.txt`` only. This is the fallback without MLIR.

    Some run bundles (``gem5_outputs/<hash>/``) have only meta.txt and the gem5
    stats. Without ``linalg.matmul``, this function cannot *prove* that the
    kernel is a matmul. Thus the **caller must first make sure that the TOGSim
    activity is not zero** (systolic cycles or GEMM ops > 0).

    What meta.txt supplies and what the function assumes:

    - operand dtype: the torch dtype of the 2-D ``attr=1`` (input) entries.
      The function ignores 1-D entries (biases). If the dtypes are different,
      it uses the narrowest and gives a warning. The MLIR path uses the same
      rule for a partial int lowering.
    - accumulator: **assumed**. Floating-point operands accumulate in f32, and
      f64 stays f64. Integer operands use the ``2·bits + ceil(log2(lanes))``
      fallback rule.
    - gemm_shape: an estimate from two 2-D inputs that share a K dimension, in
      one of the two orientations. It is ``None`` if the shape is ambiguous.
      It is only information.

    ``confidence`` is always ``"low"``. ``kernel`` is the name (the hash) of
    the kernel in the warnings.
    """
    if lanes < 1:
        raise MacInferenceError.nw(6105, lanes=lanes)

    entries = parse_meta(meta_text)
    if not entries:
        raise MacInferenceError.nw(6112)

    warnings: List[str] = []
    provenance: Dict[str, str] = {}

    inputs_2d = [e for e in entries if e.attr == 1 and len(e.shape) == 2]
    voters = inputs_2d
    if not voters:
        voters = [e for e in entries if e.attr == 1]
        if voters:
            warnings.append(warning(6113, kernel=kernel))
    if not voters:
        raise MacInferenceError.nw(6114)

    by_canonical = {e.dtype.canonical: e.dtype for e in voters}
    if len(by_canonical) > 1:
        operand = min(by_canonical.values(), key=lambda d: (d.bits, d.canonical))
        warnings.append(warning(
            6115, kernel=kernel, dtypes=", ".join(sorted(by_canonical)),
            dtype=operand.canonical))
    else:
        operand = next(iter(by_canonical.values()))
    provenance["operand_dtype"] = "meta.txt inputs (attr=1); no kernel MLIR"

    # meta.txt does not give the accumulator. Assume it and record the assumption.
    if operand.kind == "float":
        acc_canonical = "f64" if operand.bits > 32 else "f32"
        bits, exp, mant = VOCABULARY.float_formats[acc_canonical]
        accum = DType("float", bits, acc_canonical, exp_bits=exp, mantissa_bits=mant)
        provenance["accum_dtype"] = f"assumed {acc_canonical} (meta.txt-only)"
    else:
        acc_bits = _fallback_int_acc_width(operand.bits, lanes)
        accum = DType("int", acc_bits, f"i{acc_bits}", signed=True)
        provenance["accum_dtype"] = "fallback rule 2*bits+ceil(log2(lanes))"

    primitive, cfg = _select_primitive(
        operand, accum, lanes, pipeline_stages, lowering_ok=False
    )
    provenance["lanes"] = "caller (config vpu_num_lanes / systolicArrayWidth)"
    provenance["pipeline_stages"] = "assumed (opLat=1 array; not derivable)"

    # Estimate (M, K, N) from exactly two 2-D inputs that share an inner dimension.
    gemm_shape: Optional[Tuple[int, int, int]] = None
    if len(inputs_2d) == 2:
        (m0, k0), (b0, b1) = inputs_2d[0].shape, inputs_2d[1].shape
        if k0 == b0:
            gemm_shape = (m0, k0, b1)
        elif k0 == b1:                       # the weights are transposed
            gemm_shape = (m0, k0, b0)

    warnings.append(warning(6116, kernel=kernel))
    return MacConfig(
        primitive=primitive,
        primitive_config=cfg,
        operand_dtype=operand,
        accum_dtype=accum,
        lanes=lanes,
        pipeline_stages=pipeline_stages,
        confidence="low",
        gemm_shape=gemm_shape,
        warnings=tuple(warnings),
        provenance=provenance,
    )
