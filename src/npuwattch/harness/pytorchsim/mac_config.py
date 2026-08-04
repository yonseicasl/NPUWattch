"""Infer a systolic-array MAC's NPUWattch primitive config from PyTorchSim artifacts.

This is workstream B, item #2 of the integration plan. PyTorchSim changes the
hardware configuration at runtime, so the MAC's datatype parameters are *not* in
a static description — they must be read out of each compiled kernel's
**codegen artifacts** (not the activity trace):

    outputs/<hash>/meta.txt      torch dtype + shape of every kernel arg
    outputs/<hash>/*.mlir        func.func @kernel signature + `linalg.matmul`

The activity trace (``m5out/stats.txt``, TOGSim log) is a *separate* input that
drives per-window activity counts for the projection; it says nothing about the
MAC's bit-widths. See ``docs/COMPOUND_SCHEMA.md`` §2.1.

What is derivable per kernel (verified against the five local-run samples):

============ ============================================================
MAC param    source (primary -> cross-check)
============ ============================================================
operand      ``linalg.matmul ins`` element type -> meta.txt inputs
             -> func.func signature (used to catch a failed int lowering)
accumulator  ``linalg.matmul outs`` element type -> meta.txt output buffer
lanes        config (``vpu_num_lanes`` / ``systolicArrayWidth``) — passed in
pipeline     NOT derivable (array is opLat=1); NPUWattch assumption, default 2
============ ============================================================

The only assumed datatype parameter is ``pipeline_stages``; everything else is
read from the kernel. When the ``outputs/`` artifacts are absent (a
description-only run) the accumulator width falls back to a rule.

Known drift handled explicitly: the Dec-2025 PyTorchSim image cannot lower an
int matmul, so an ``int8`` GEMM emits a kernel whose func signature is ``i8``
but whose ``linalg.matmul`` is ``f32`` (a scalar-emulation fallback) and whose
``meta.txt`` is missing. That disagreement is detected, the tensor (int) dtype
wins for primitive selection, and the result is flagged low-confidence /
uncalibrated rather than silently reported as an f32 MAC.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

class MacInferenceError(ValueError):
    """The artifacts are present but a MAC config cannot be inferred from them."""


class NotAMatmulKernel(MacInferenceError):
    """The kernel contains no ``linalg.matmul`` — not a MAC kernel (skip it)."""


@dataclass(frozen=True)
class DType:
    """A scalar numeric type, normalized across MLIR and torch spellings."""

    kind: str                       # "float" | "int"
    bits: int                       # total width in bits
    canonical: str                  # "f32", "bf16", "i8", ...
    exp_bits: Optional[int] = None  # float only
    mantissa_bits: Optional[int] = None
    signed: bool = True             # int only (floats: True/ignored)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.canonical


# Canonical float formats: canonical -> (bits, exp_bits, mantissa_bits).
_FLOAT_FORMATS: Dict[str, Tuple[int, int, int]] = {
    "f64": (64, 11, 52),
    "f32": (32, 8, 23),
    "f16": (16, 5, 10),
    "bf16": (16, 8, 7),
    "f8e4m3": (8, 4, 3),
    "f8e5m2": (8, 5, 2),
}

# Spelling -> canonical, covering MLIR element types and torch dtype names.
_DTYPE_ALIASES: Dict[str, str] = {
    # floats — MLIR
    "f64": "f64", "f32": "f32", "f16": "f16", "bf16": "bf16",
    "f8e4m3fn": "f8e4m3", "f8e4m3": "f8e4m3", "f8e5m2": "f8e5m2",
    # floats — torch
    "torch.float64": "f64", "torch.double": "f64",
    "torch.float32": "f32", "torch.float": "f32",
    "torch.float16": "f16", "torch.half": "f16",
    "torch.bfloat16": "bf16",
    # ints — MLIR (signless) and torch. Width parsed generically below for i<N>.
    "torch.int64": "i64", "torch.long": "i64",
    "torch.int32": "i32", "torch.int": "i32",
    "torch.int16": "i16", "torch.short": "i16",
    "torch.int8": "i8", "torch.uint8": "u8", "torch.bool": "i1",
}


def parse_dtype(token: str) -> DType:
    """Normalize an MLIR element type or torch dtype spelling into a ``DType``."""
    raw = token.strip()
    key = raw.lower()
    canonical = _DTYPE_ALIASES.get(key, key)

    if canonical in _FLOAT_FORMATS:
        bits, exp, mant = _FLOAT_FORMATS[canonical]
        return DType("float", bits, canonical, exp_bits=exp, mantissa_bits=mant)

    # Generic integer: MLIR ``i8``/``i32`` (signless), torch ``iN``/``uN``.
    m = re.fullmatch(r"([iu])(\d+)", canonical)
    if m:
        signed = m.group(1) == "i"
        bits = int(m.group(2))
        return DType("int", bits, canonical, signed=signed)

    raise MacInferenceError(f"unrecognized dtype token: {token!r}")


# ---------------------------------------------------------------------------
# MacConfig — the inference result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MacConfig:
    """Inferred MAC primitive + the exact RTL params it takes.

    ``primitive_config`` holds only the parameters the chosen primitive's RTL
    generator accepts (see ``dataset_gen/logic/rtl_gen/SUMMARY.md``):

    - ``fpmac``  -> ``exp_bits``, ``mantissa_bits``, ``pipeline_stages``
      (accumulation format is internal to the RTL; ``accum_dtype`` is
      informational only).
    - ``intmac`` -> ``a_width``, ``b_width``, ``out_width``, ``acc_width``,
      ``pipeline_stages``.
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
    """The zero-evidence fallback: an fp32 (e8m23) datapath, confidence 'low'.

    Used when a run contains NO MAC kernel at all, so there is no kernel to
    borrow a representative dtype from — the non-MAC windows still need one to
    resolve the templated vfu/spads elements. fp32 is the SFU fallback
    convention (§_SFU_FALLBACK_EXP_MANT) applied to the datapath; callers must
    surface a WARNING (an assumption unbacked by any run evidence).
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
    attr: int                  # 1 = input/param, 2 = computed/output buffer
    dtype: DType
    shape: Tuple[int, ...]


def parse_meta(text: str) -> List[MetaEntry]:
    """Parse a ``meta.txt`` into typed entries. Unparseable lines are skipped."""
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

# element type + dims inside a memref, e.g. "128x256xf32, 1" or "16384xi8".
_MEMREF = re.compile(r"memref<([^>]*)>")
_FUNC_KERNEL = re.compile(r"func\.func\s+@kernel\s*\(([^)]*)\)")
# ins(...) and outs(...) may sit on separate lines -> DOTALL.
_MATMUL = re.compile(
    r"linalg\.matmul\s+ins\((?P<ins>[^)]*)\)\s*outs\((?P<outs>[^)]*)\)",
    re.DOTALL,
)


def _memref_shape_and_elem(inner: str) -> Tuple[Tuple[int, ...], DType]:
    """``"128x256xf32, 1"`` -> ((128, 256), DType(f32))."""
    body = inner.split(",", 1)[0].strip()        # drop memory space / layout
    parts = body.split("x")
    elem = parts[-1].strip()
    dims: Tuple[int, ...] = tuple(
        int(p) for p in parts[:-1] if p.strip().isdigit()
    )
    return dims, parse_dtype(elem)


def _memrefs(fragment: str) -> List[Tuple[Tuple[int, ...], DType]]:
    return [_memref_shape_and_elem(m) for m in _MEMREF.findall(fragment)]


@dataclass(frozen=True)
class MlirMatmul:
    func_operand_types: List[DType]                  # every memref elem in signature
    ins: List[Tuple[Tuple[int, ...], DType]]         # matmul input operands
    outs: Tuple[Tuple[int, ...], DType]              # matmul output/accumulator


def parse_mlir(text: str) -> MlirMatmul:
    """Extract the func signature operand types and the ``linalg.matmul`` operands."""
    mm = _MATMUL.search(text)
    if not mm:
        raise NotAMatmulKernel("no `linalg.matmul` found in MLIR")

    ins = _memrefs(mm.group("ins"))
    outs_list = _memrefs(mm.group("outs"))
    if len(ins) < 2 or not outs_list:
        raise MacInferenceError(
            f"malformed linalg.matmul: {len(ins)} ins / {len(outs_list)} outs"
        )

    func_types: List[DType] = []
    fm = _FUNC_KERNEL.search(text)
    if fm:
        func_types = [dt for _, dt in _memrefs(fm.group(1))]

    return MlirMatmul(func_operand_types=func_types, ins=ins, outs=outs_list[0])


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def _fallback_int_acc_width(operand_bits: int, lanes: int) -> int:
    """acc_width = 2*bitwidth + ceil(log2(lanes)) (COMPOUND_SCHEMA §2.1 fallback)."""
    lanes = max(1, lanes)
    return 2 * operand_bits + math.ceil(math.log2(lanes)) if lanes > 1 else 2 * operand_bits


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
            "exp_bits": operand.exp_bits,
            "mantissa_bits": operand.mantissa_bits,
            "pipeline_stages": pipeline_stages,
        }
    if operand.kind == "int":
        if lowering_ok and accum.kind == "int":
            acc_width = accum.bits
        else:
            acc_width = _fallback_int_acc_width(operand.bits, lanes)
        return "intmac", {
            "a_width": operand.bits,
            "b_width": operand.bits,
            "out_width": acc_width,
            "acc_width": acc_width,
            "pipeline_stages": pipeline_stages,
        }
    raise MacInferenceError(f"no MAC primitive for operand kind {operand.kind!r}")


def infer_mac_config(
    mlir_text: str,
    lanes: int,
    *,
    meta_text: Optional[str] = None,
    pipeline_stages: int = 2,
) -> MacConfig:
    """Infer a ``MacConfig`` from one kernel's MLIR (+ optional meta.txt).

    ``lanes`` is the systolic array width (``vpu_num_lanes`` / ``systolicArrayWidth``),
    an architecture-level parameter that comes from the config, not the kernel.
    """
    if lanes < 1:
        raise MacInferenceError(f"lanes must be >= 1, got {lanes}")

    mlir = parse_mlir(mlir_text)
    meta = parse_meta(meta_text) if meta_text else []
    warnings: List[str] = []
    provenance: Dict[str, str] = {}

    # --- operand dtype ---------------------------------------------------
    ins_types = [dt for _, dt in mlir.ins]
    if len({dt.canonical for dt in ins_types}) > 1:
        warnings.append(
            "mixed-precision matmul operands "
            f"({', '.join(dt.canonical for dt in ins_types)}); using the first"
        )
    matmul_operand = ins_types[0]

    func_int_types = [dt for dt in mlir.func_operand_types if dt.kind == "int"]
    lowering_ok = True
    if matmul_operand.kind == "float" and func_int_types:
        # Dec-2025 image: int matmul was not lowered; it fell back to scalar f32.
        # The kernel's tensor dtype (func signature) is the real intent.
        operand = min(func_int_types, key=lambda d: d.bits)
        lowering_ok = False
        warnings.append(
            f"partial int lowering: linalg.matmul is {matmul_operand.canonical} but "
            f"kernel I/O is {operand.canonical}; selecting intmac by tensor dtype. "
            "int MAC energy is NOT calibrated on this image."
        )
        provenance["operand_dtype"] = "mlir:func.func signature (matmul disagreed)"
    else:
        operand = matmul_operand
        provenance["operand_dtype"] = "mlir:linalg.matmul ins"

    # meta.txt cross-check for the operand dtype (inputs = attr 1).
    meta_inputs = [e for e in meta if e.attr == 1]
    if meta_inputs:
        meta_in_canon = {e.dtype.canonical for e in meta_inputs}
        if lowering_ok and operand.canonical not in meta_in_canon:
            warnings.append(
                f"operand dtype {operand.canonical} (MLIR) not among meta.txt "
                f"input dtypes {sorted(meta_in_canon)}"
            )
        provenance["operand_dtype_crosscheck"] = "meta.txt inputs (attr=1)"

    # --- accumulator dtype ----------------------------------------------
    if lowering_ok:
        accum = mlir.outs[1]
        provenance["accum_dtype"] = "mlir:linalg.matmul outs"
    else:
        # matmul outs is the same bogus f32; derive by rule.
        acc_bits = _fallback_int_acc_width(operand.bits, lanes)
        accum = DType("int", acc_bits, f"i{acc_bits}", signed=True)
        provenance["accum_dtype"] = "fallback rule 2*bits+ceil(log2(lanes))"

    # --- primitive + params ----------------------------------------------
    primitive, cfg = _select_primitive(
        operand, accum, lanes, pipeline_stages, lowering_ok
    )
    provenance["lanes"] = "caller (config vpu_num_lanes / systolicArrayWidth)"
    provenance["pipeline_stages"] = "assumed (opLat=1 array; not derivable)"

    # --- gemm tile shape (for activity calibration / reporting) ----------
    gemm_shape: Optional[Tuple[int, int, int]] = None
    a_shape, _ = mlir.ins[0]
    b_shape, _ = mlir.ins[1]
    if len(a_shape) == 2 and len(b_shape) == 2:
        gemm_shape = (a_shape[0], a_shape[1], b_shape[1])  # (M, K, N)
        if a_shape[1] != b_shape[0]:
            warnings.append(
                f"matmul K mismatch: A={a_shape} B={b_shape}"
            )

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
    """The kernel MLIR is ``c<hash>.mlir`` (not ``*_llvm.mlir`` / ``*_sample*.mlir``)."""
    candidates = [
        p for p in sorted(kernel_dir.glob("*.mlir"))
        if not p.stem.endswith(("_llvm", "_sample", "_sample_llvm"))
    ]
    if not candidates:
        raise MacInferenceError(f"no kernel .mlir in {kernel_dir}")
    # Prefer the one that actually contains a linalg.matmul; >1 such is ambiguous.
    matmul = [
        p for p in candidates
        if "linalg.matmul" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    if len(matmul) > 1:
        raise MacInferenceError(
            f"{kernel_dir}: {len(matmul)} candidate kernel MLIRs contain linalg.matmul "
            f"({', '.join(p.name for p in matmul)}); ambiguous — leave exactly one"
        )
    if matmul:
        return matmul[0]
    return candidates[0]


def infer_mac_config_from_dir(
    kernel_dir: Path,
    lanes: int,
    *,
    pipeline_stages: int = 2,
) -> MacConfig:
    """Infer from an ``outputs/<hash>/`` directory (reads meta.txt + kernel MLIR)."""
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
    )


# ---------------------------------------------------------------------------
# meta.txt-only fallback (author delivery bundles ship no kernel MLIR)
# ---------------------------------------------------------------------------

def infer_mac_config_from_meta(
    meta_text: str,
    lanes: int,
    *,
    pipeline_stages: int = 2,
) -> MacConfig:
    """Infer a ``MacConfig`` from ``meta.txt`` alone — the MLIR-less fallback.

    Author delivery bundles (``gem5_outputs/<hash>/``) carry only meta.txt +
    gem5 stats; without ``linalg.matmul`` this path cannot *prove* the kernel is
    a matmul, so the **caller must gate on TOGSim activity** (systolic cycles /
    GEMM ops > 0) before calling. What meta.txt supports and what is assumed:

    - operand dtype ← the 2-D ``attr=1`` (input) entries' torch dtype; 1-D
      entries (biases) don't vote. Mixed dtypes pick the narrowest, with a
      warning (same rule as the partial-int-lowering MLIR path).
    - accumulator ← **assumed**: fp operands accumulate in f32 (f64 stays f64);
      int uses the ``2·bits + ceil(log2(lanes))`` fallback rule.
    - gemm_shape ← best-effort from two 2-D inputs sharing a K dim (either
      orientation); ``None`` when ambiguous. Informational only.

    ``confidence`` is always ``"low"``.
    """
    if lanes < 1:
        raise MacInferenceError(f"lanes must be >= 1, got {lanes}")

    entries = parse_meta(meta_text)
    if not entries:
        raise MacInferenceError("meta.txt has no parseable entries")

    warnings: List[str] = []
    provenance: Dict[str, str] = {}

    inputs_2d = [e for e in entries if e.attr == 1 and len(e.shape) == 2]
    voters = inputs_2d
    if not voters:
        voters = [e for e in entries if e.attr == 1]
        if voters:
            warnings.append(
                "no 2-D input tensors in meta.txt; operand dtype taken from "
                "non-matrix inputs"
            )
    if not voters:
        raise MacInferenceError("meta.txt has no attr=1 (input) entries")

    by_canonical = {e.dtype.canonical: e.dtype for e in voters}
    if len(by_canonical) > 1:
        operand = min(by_canonical.values(), key=lambda d: (d.bits, d.canonical))
        warnings.append(
            f"mixed input dtypes in meta.txt ({', '.join(sorted(by_canonical))}); "
            f"using the narrowest ({operand.canonical})"
        )
    else:
        operand = next(iter(by_canonical.values()))
    provenance["operand_dtype"] = "meta.txt inputs (attr=1); no kernel MLIR"

    # Accumulator is invisible in meta.txt — assume, and say so.
    if operand.kind == "float":
        acc_canonical = "f64" if operand.bits > 32 else "f32"
        bits, exp, mant = _FLOAT_FORMATS[acc_canonical]
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

    # Best-effort (M, K, N): exactly two 2-D inputs sharing an inner dim.
    gemm_shape: Optional[Tuple[int, int, int]] = None
    if len(inputs_2d) == 2:
        (m0, k0), (b0, b1) = inputs_2d[0].shape, inputs_2d[1].shape
        if k0 == b0:
            gemm_shape = (m0, k0, b1)
        elif k0 == b1:                       # weights stored transposed
            gemm_shape = (m0, k0, b0)

    warnings.append(
        "MAC config inferred from meta.txt only (no kernel MLIR); accumulator "
        "format is assumed — energy for this kernel is lower-confidence"
    )
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
