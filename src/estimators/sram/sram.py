"""SRAM macro estimator — calibrated: measured-table + trained-MLP backed.

Answers CACTI-style queries (node, depth, width, banks, PVT, activity) with
energy / leakage / area / timing for an SRAM macro composed from the
SPICE-measured tiles in ``dataset_gen/sram/datasets/``:

- ``sram_array.csv``   — 6T array tiles (rows x cols), read/write energies,
  leakage, delays, GDS areas.
- ``sram_decoder.csv`` — the pitch-matched registered row decoder for each
  tile, including the wordline RC it drives (the array TB uses an ideal WL
  source, so WL charging energy is booked exactly once, here).

Model, by construction of the dataset (no column mux, no WL stitching):
a macro = banks x (n_vert x n_horz) grid of measured tiles, each tile with its
own row decoder (x ``n_ports``).  One vertical group is selected per access;
all horizontal tiles fire together.  The array has no clock, so a non-accessed
array is leakage-only; a non-firing but clocked decoder burns ``dec_idle`` per
cycle (charged by default, zeroed by ``tile_clock_gating``).

Dataset energies are 10 ns-window integrals that INCLUDE their own window's
leakage; the loader subtracts ``leak_power_mW * window_ns`` once so every
number downstream is pure dynamic — the S6 aggregator books leakage
separately via ``leak_power``.

Delay composition (same 50%-VDD wordline threshold on both sheets):

    t_read  = dec_wlen_wl_ns + rd_delay_ns
    t_write = max(dec_wlen_wl_ns, wr_bl_ns) + wr_cell_ns

Units follow the repo convention: pJ / mW / um2 / ns.  ``depth`` is words
PER BANK (total bits = n_banks * depth * bw, matching the class-mapper
vocabulary).  This module is stdlib-only and self-contained so
``EstimatorHost`` can execute it via ``runpy`` in any environment.

The per-tile cost lookup sits behind the ``TilePointSource`` seam with two
implementations selected by the ``source`` feature: ``TableTilePointSource``
(exact grid lookup + separable PVT k-scaling) and the trained MLP quartets
(``sram_mlp.py`` + ``<metric>__v1.*`` checkpoints in this directory, trained
by ``train_sram.py``; metrics in ``eval_report.json``).  ``source="auto"``
(default) uses the MLPs when the checkpoints are present and torch imports,
else the table — always with a warning naming the fallback reason.
"""

from __future__ import annotations

import csv
import importlib.util
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# ESTIMATOR_SPEC — must stay a pure literal (EstimatorHost ast.literal_eval's
# it without importing this module).
# --------------------------------------------------------------------------

ESTIMATOR_SPEC = {
    "primitive": "sram",
    # Characterized nodes (must mirror the sram_array/sram_decoder datasets) —
    # the anchor set energy.node_scaling interpolates the CLI node axis over.
    "nodes": ["5nm", "7nm", "10nm", "16nm", "20nm"],
    "version": "1.0",
    "description": (
        "Calibrated SRAM macro estimator: tiled single-array banks with "
        "per-tile row decoders, backed by the PrimeSim-measured "
        "sram_array/sram_decoder datasets. depth = words per bank."
    ),
    "entrypoints": {
        "energy": "get_energy",
        "area": "get_area",
        "timing": "get_timing",
        "leakage": "get_leakage",
        "report": "get_report",
        "unit_costs": "get_unit_costs",
        "unit_cost_provider": "make_unit_cost_provider",
    },
    "parameters": {
        # Names are canonical (npuwattch.naming) — one spelling per concept, no
        # aliases; a harness translates its simulator's vocabulary at ingest.
        "required": [
            {"name": "node", "type": "str"},
            {"name": "mem_depth_per_bank", "type": "int"},
            {"name": "data_width", "type": "int"},
        ],
        "optional": [
            {"name": "mem_banks", "type": "int", "default": 1},
            {"name": "mem_r_ports", "type": "int", "default": 0},
            {"name": "mem_w_ports", "type": "int", "default": 0},
            {"name": "mem_rw_ports", "type": "int", "default": 1},
            # Macro template (capacity-only specs): fixes data_width/depth and
            # pins the 256x32 tile grid that models its column mux. Values:
            # sram_64k (256WL x 4:1 x 64b) | sram_256k (256WL x 8:1 x 128b).
            {"name": "mem_template", "type": "str", "default": None},
            {"name": "voltage_offset_V", "type": "float", "default": 0.0},
            {"name": "vdd_V", "type": "float", "default": None},
            {"name": "temperature_C", "type": "float", "default": 25.0},
            {"name": "corner", "type": "str", "default": "TT"},
            {"name": "toggle_rate", "type": "float", "default": 0.5},
            {"name": "read_zero_fraction", "type": "float", "default": 0.5},
            {"name": "addr_toggle_rate", "type": "float", "default": 0.5},
            {"name": "optimize", "type": "str", "default": "energy"},
            {"name": "tile_rows", "type": "int", "default": None},
            {"name": "tile_cols", "type": "int", "default": None},
            {"name": "tile_clock_gating", "type": "bool", "default": False},
            {"name": "allow_ragged_edge", "type": "bool", "default": True},
            {"name": "dataset_dir", "type": "str", "default": None},
            {"name": "stim_mode", "type": "str", "default": None},
            {"name": "source", "type": "str", "default": "auto"},
            {"name": "model_dir", "type": "str", "default": None},
        ],
    },
    # Trained MLP quartets (state_dict .pt + scalers/loss/meta sidecars) next
    # to this module; loaded via sram_mlp.py when source resolves to "mlp".
    "models": {
        "energy": "energy__v1.pt",
        "leakage": "leakage__v1.pt",
        "timing": "timing__v1.pt",
        "area": "area__v1.pt",
    },
}

_ARRAY_CSV = "sram_array.csv"
_DECODER_CSV = "sram_decoder.csv"
_DATASET_ENV = "NPUWATTCH_SRAM_DATA"
_MEAS_WINDOW_NS = 10.0           # array TB op-window length (fixed by the flow)
_REF_SHAPES = ((16, 8), (64, 16), (256, 32))   # PVT-swept reference shapes
_STIM_MODES = ("read", "write", "idle", "random")
_OBJECTIVES = ("energy", "area", "delay")
_PVT_SPREAD_WARN = 1.15          # ref-shape disagreement worth flagging
_TILE_GLUE_WARN = 4              # tiles/bank above which glue is non-negligible
_UTIL_WARN = 0.5                 # physical-bit utilization worth flagging
_DYN_EPS_PJ = 1e-9               # tolerated float dust in leak subtraction


# --------------------------------------------------------------------------
# Dataset records
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ArrayPoint:
    """One sram_array.csv row; *_dyn energies have window leakage subtracted."""

    rows: int
    cols: int
    wr_same_dyn_pJ: float
    wr_toggle_dyn_pJ: float      # all `cols` bits flip (toggle_rate = 1.0 row)
    rd_1to1_dyn_pJ: float
    rd_1to0_dyn_pJ: float
    leak_power_mW: float
    rd_delay_ns: float
    wr_bl_ns: float
    wr_cell_ns: float
    array_area_um2: float
    decoder_area_um2: float
    # provenance / aux measures (not used by the model, surfaced in reports)
    wr1_init_energy_pJ: float
    wr0_fill_energy_pJ: float
    rd_bl_dev_ns: float
    rd_sense_ns: float
    flow_run_id: str


@dataclass(frozen=True)
class DecoderPoint:
    """One sram_decoder.csv row; *_dyn energies have window leakage subtracted."""

    rows: int
    cols: int
    act_dyn_pJ: float            # WL fires, same address
    flip_dyn_pJ: float           # WL fires, all address bits toggle
    idle_dyn_pJ: float           # en=0, clk toggles, no WL
    leak_power_mW: float
    wlen_wl_ns: float
    dec_area_um2: float
    flow_run_id: str


@dataclass
class SramDataset:
    dataset_dir: Path
    nominal_array: Dict[Tuple[str, int, int], ArrayPoint]
    nominal_dec: Dict[Tuple[str, int, int], DecoderPoint]
    pvt_array: Dict[Tuple[str, int, int, float, float], ArrayPoint]
    pvt_dec: Dict[Tuple[str, int, int, float, float], DecoderPoint]
    nominal_vdd_by_node: Dict[str, float]
    shapes_by_node: Dict[str, Tuple[Tuple[int, int], ...]]   # nominal array∩dec
    validation_tr05: List[Dict[str, str]]                    # raw rows, tests only


_DATASET_CACHE: Dict[str, SramDataset] = {}


def _resolve_dataset_dir(features: Optional[Mapping[str, Any]] = None) -> Path:
    """features['dataset_dir'] > $NPUWATTCH_SRAM_DATA > walk up from __file__."""
    explicit = (features or {}).get("dataset_dir") or os.environ.get(_DATASET_ENV)
    if explicit:
        cand = Path(explicit)
        if not (cand / _ARRAY_CSV).is_file() or not (cand / _DECODER_CSV).is_file():
            raise ValueError(f"dataset dir {cand} lacks {_ARRAY_CSV}/{_DECODER_CSV}")
        return cand
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "dataset_gen" / "sram" / "datasets"
        if (cand / _ARRAY_CSV).is_file() and (cand / _DECODER_CSV).is_file():
            return cand
    raise ValueError(
        f"cannot locate {_ARRAY_CSV}/{_DECODER_CSV}; set ${_DATASET_ENV} or pass "
        "features['dataset_dir']"
    )


def _fnum(row: Mapping[str, str], key: str, ctx: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"bad/missing '{key}' in {ctx}") from None


def _fnum_or(row: Mapping[str, str], key: str, default: float) -> float:
    """Lenient parse for convenience-join columns that may be empty (e.g. the
    array sheet's decoder_area_um2 when the decoder partner run failed)."""
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def _dyn(raw_pJ: float, leak_mW: float, window_ns: float, ctx: str) -> float:
    """Pure dynamic energy: raw window integral minus its own leakage share."""
    dyn = raw_pJ - leak_mW * window_ns          # mW * ns == pJ
    if dyn < -_DYN_EPS_PJ:
        raise ValueError(
            f"negative dynamic energy ({dyn:.3e} pJ) after leakage subtraction "
            f"in {ctx} — dataset inconsistent"
        )
    return max(0.0, dyn)


def load_dataset(dataset_dir: Optional[Path] = None) -> SramDataset:
    """Parse + validate both sheets once; cached per resolved directory."""
    ddir = Path(dataset_dir) if dataset_dir else _resolve_dataset_dir()
    cache_key = str(ddir.resolve())
    hit = _DATASET_CACHE.get(cache_key)
    if hit is not None:
        return hit

    nominal_array: Dict[Tuple[str, int, int], ArrayPoint] = {}
    pvt_array: Dict[Tuple[str, int, int, float, float], ArrayPoint] = {}
    nominal_dec: Dict[Tuple[str, int, int], DecoderPoint] = {}
    pvt_dec: Dict[Tuple[str, int, int, float, float], DecoderPoint] = {}
    vdd_map: Dict[str, float] = {}
    tr05: List[Dict[str, str]] = []

    with open(ddir / _ARRAY_CSV, newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            ctx = f"{_ARRAY_CSV}:{i}"
            if row.get("transistor") != "hp" or row.get("corner") != "TT":
                continue                        # future FF/SS/lp data: ignored here
            if int(float(row.get("pex", "1"))) != 1:
                continue
            node = row["node"]
            r, c = int(row["rows"]), int(row["cols"])
            dv = round(_fnum(row, "voltage_offset_V", ctx), 3)
            temp = _fnum(row, "temperature_C", ctx)
            tr = _fnum(row, "toggle_rate", ctx)
            if dv == 0.0:
                vdd = _fnum(row, "vdd_V", ctx)
                if node in vdd_map and abs(vdd_map[node] - vdd) > 1e-9:
                    raise ValueError(f"inconsistent nominal vdd for {node} at {ctx}")
                vdd_map[node] = vdd
            if tr != 1.0:
                tr05.append(dict(row))
                continue
            leak = _fnum(row, "leak_power_mW", ctx)
            pt = ArrayPoint(
                rows=r, cols=c,
                wr_same_dyn_pJ=_dyn(_fnum(row, "wr_same_energy_pJ", ctx), leak, _MEAS_WINDOW_NS, ctx),
                wr_toggle_dyn_pJ=_dyn(_fnum(row, "wr_toggle_energy_pJ", ctx), leak, _MEAS_WINDOW_NS, ctx),
                rd_1to1_dyn_pJ=_dyn(_fnum(row, "rd_1to1_energy_pJ", ctx), leak, _MEAS_WINDOW_NS, ctx),
                rd_1to0_dyn_pJ=_dyn(_fnum(row, "rd_1to0_energy_pJ", ctx), leak, _MEAS_WINDOW_NS, ctx),
                leak_power_mW=leak,
                rd_delay_ns=_fnum(row, "rd_delay_ns", ctx),
                wr_bl_ns=_fnum(row, "wr_bl_ns", ctx),
                wr_cell_ns=_fnum(row, "wr_cell_ns", ctx),
                array_area_um2=_fnum(row, "total_area_um2", ctx),
                # convenience join from the decoder sheet; empty when the
                # decoder partner failed — the model reads decoder area from
                # the decoder sheet itself, so this is informational only.
                decoder_area_um2=_fnum_or(row, "decoder_area_um2", 0.0),
                wr1_init_energy_pJ=_fnum(row, "wr1_init_energy_pJ", ctx),
                wr0_fill_energy_pJ=_fnum(row, "wr0_fill_energy_pJ", ctx),
                rd_bl_dev_ns=_fnum(row, "rd_bl_dev_ns", ctx),
                rd_sense_ns=_fnum(row, "rd_sense_ns", ctx),
                flow_run_id=row.get("flow_run_id", ""),
            )
            if dv == 0.0 and temp == 25.0:
                key = (node, r, c)
                if key in nominal_array:
                    raise ValueError(f"duplicate nominal array row {key} at {ctx}")
                nominal_array[key] = pt
            else:
                pkey = (node, r, c, dv, temp)
                if pkey in pvt_array:
                    raise ValueError(f"duplicate PVT array row {pkey} at {ctx}")
                pvt_array[pkey] = pt

    with open(ddir / _DECODER_CSV, newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            ctx = f"{_DECODER_CSV}:{i}"
            if row.get("transistor") != "hp" or row.get("corner") != "TT":
                continue
            if int(float(row.get("pex", "1"))) != 1:
                continue
            node = row["node"]
            r, c = int(row["rows"]), int(row["cols"])
            dv = round(_fnum(row, "voltage_offset_V", ctx), 3)
            temp = _fnum(row, "temperature_C", ctx)
            clk_ns = _fnum(row, "clk_ns", ctx)
            if clk_ns != _MEAS_WINDOW_NS:
                raise ValueError(
                    f"decoder TB cadence changed (clk_ns={clk_ns}) at {ctx}; "
                    "leakage-subtraction window must be revisited"
                )
            leak = _fnum(row, "dec_leak_power_mW", ctx)
            pt = DecoderPoint(
                rows=r, cols=c,
                act_dyn_pJ=_dyn(_fnum(row, "dec_act_energy_pJ", ctx), leak, clk_ns, ctx),
                flip_dyn_pJ=_dyn(_fnum(row, "dec_flip_energy_pJ", ctx), leak, clk_ns, ctx),
                idle_dyn_pJ=_dyn(_fnum(row, "dec_idle_energy_pJ", ctx), leak, clk_ns, ctx),
                leak_power_mW=leak,
                wlen_wl_ns=_fnum(row, "dec_wlen_wl_ns", ctx),
                dec_area_um2=_fnum(row, "dec_area_um2", ctx),
                flow_run_id=row.get("flow_run_id", ""),
            )
            if dv == 0.0 and temp == 25.0:
                key = (node, r, c)
                if key in nominal_dec:
                    raise ValueError(f"duplicate nominal decoder row {key} at {ctx}")
                nominal_dec[key] = pt
            else:
                pkey = (node, r, c, dv, temp)
                if pkey in pvt_dec:
                    raise ValueError(f"duplicate PVT decoder row {pkey} at {ctx}")
                pvt_dec[pkey] = pt

    if not nominal_array or not nominal_dec:
        raise ValueError(f"no nominal rows loaded from {ddir}")

    shapes: Dict[str, Tuple[Tuple[int, int], ...]] = {}
    for node in sorted({k[0] for k in nominal_array}):
        both = sorted(
            (r, c) for (n, r, c) in nominal_array
            if n == node and (n, r, c) in nominal_dec
        )
        if both:
            shapes[node] = tuple(both)

    ds = SramDataset(
        dataset_dir=ddir,
        nominal_array=nominal_array,
        nominal_dec=nominal_dec,
        pvt_array=pvt_array,
        pvt_dec=pvt_dec,
        nominal_vdd_by_node=vdd_map,
        shapes_by_node=shapes,
        validation_tr05=tr05,
    )
    _DATASET_CACHE[cache_key] = ds
    return ds


# --------------------------------------------------------------------------
# Config normalization
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SramConfig:
    """Normalized query. ``depth_words`` is words PER BANK."""

    node: str
    width_bits: int
    depth_words: int
    banks: int = 1
    ports: int = 1
    voltage_offset_v: float = 0.0
    temperature_c: float = 25.0
    toggle_rate: float = 0.5
    read_zero_fraction: float = 0.5
    addr_toggle_rate: float = 0.5
    optimize: str = "energy"
    tile_rows: Optional[int] = None
    tile_cols: Optional[int] = None
    tile_clock_gating: bool = False
    allow_ragged_edge: bool = True
    clock_mhz: Optional[float] = None
    source: str = "auto"                 # auto | table | mlp
    model_dir: Optional[str] = None      # checkpoint dir override
    #: Macro template name. When set, the instance is a bank *hierarchy*:
    #: ``banks`` banks of ``depth_words / template.depth_words`` subarrays each
    #: (each subarray = one template macro), composed by
    #: ``_bank_hierarchy_costs`` from a single-subarray query.
    template: Optional[str] = None


def _first_of(features: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for k in keys:
        if k in features and features[k] is not None:
            return features[k]
    return None


def _norm_node(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{int(value)}nm"
    if isinstance(value, str):
        m = re.search(r"(\d+)", value)
        if m:
            return f"{int(m.group(1))}nm"
    raise ValueError(f"cannot parse technology node from {value!r}")


def _pos_int(value: Any, name: str) -> int:
    iv = int(value)
    if iv < 1:
        raise ValueError(f"{name} must be >= 1 (got {value!r})")
    return iv


def _fraction(features: Mapping[str, Any], name: str, default: float) -> float:
    v = float(features.get(name, default))
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"{name} must be in [0, 1] (got {v})")
    return v


# --------------------------------------------------------------------------
# SRAM macro templates (capacity-only specs)
# --------------------------------------------------------------------------
#
# Real macros rarely run the bitline past 256 cells; taller capacities use a
# column mux instead. When a component gives only a capacity (e.g. a
# simulator's "scratchpad = 16 MB"), NPUWattch auto-applies these two templates
# (with a warning) rather than solving a free geometry.
#
# Solver mapping: a template pins the tile shape to 256×32 (a measured grid
# point on every node), so the mux groups appear as vertical tile groups —
# depth/rows(256) groups of io_bits-wide reads. On an access one group is
# dynamic and the other (mux-1) groups contribute bitcell leakage + idle
# decoder energy, which reproduces the col-mux leakage exactly with configs
# the existing SRAM datasets/MLPs support. Approximation (warned): a real
# muxed macro fires ONE wordline across all physical columns and precharges
# every bitline; the tile model gives each group its own short wordline, so
# shared-WL/BL dynamic energy is underestimated. The column mux itself
# (pass gates, SA sharing) is not modeled.

SRAM_TEMPLATES: Dict[str, Dict[str, int]] = {
    # name: wordlines × col-mux × IO bits  (capacity = rows · io_bits · mux)
    "sram_64k": {"rows": 256, "col_mux": 4, "io_bits": 64,
                 "depth_words": 1024, "bits": 65536,
                 "tile_rows": 256, "tile_cols": 32},
    "sram_256k": {"rows": 256, "col_mux": 8, "io_bits": 128,
                  "depth_words": 2048, "bits": 262144,
                  "tile_rows": 256, "tile_cols": 32},
}
_TEMPLATE_SMALL, _TEMPLATE_LARGE = "sram_64k", "sram_256k"


def _bank_parts(template: str, n_subarrays: int) -> List[Dict[str, Any]]:
    """Group a template's subarrays into banks of <= 16, largest banks first.

    Full 16-subarray banks form one part; a ragged tail becomes its own
    single-bank part (its access charges only the tail's real siblings).
    """
    t = SRAM_TEMPLATES[template]
    parts = []
    full_banks, tail = divmod(n_subarrays, MAX_SUBARRAYS_PER_BANK)
    for banks, s_per_bank in ((full_banks, MAX_SUBARRAYS_PER_BANK), (1, tail)):
        if banks and s_per_bank:
            parts.append({
                "mem_template": template,
                "data_width": t["io_bits"],
                "mem_depth_per_bank": s_per_bank * t["depth_words"],
                "mem_banks": banks,
            })
    return parts


def resolve_capacity(capacity_bits: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Cover an arbitrary capacity with the two macro templates.

    Subarray count: fill with large (256k) macros; cover the remainder with
    small (64k) ones unless that would take a whole large macro's worth (then
    round up to one more large). Subarrays are then grouped into banks of at
    most 16 (``_bank_parts``). Returns ``(parts, warnings)`` where each part is
    a dict of **canonical component attributes** (`mem_template`, `data_width`,
    `mem_depth_per_bank` = subarrays-per-bank x template depth, `mem_banks`)
    ready for a §3.1 description.
    """
    if capacity_bits <= 0:
        raise ValueError(f"capacity must be positive, got {capacity_bits} bits")
    small, large = SRAM_TEMPLATES[_TEMPLATE_SMALL], SRAM_TEMPLATES[_TEMPLATE_LARGE]

    n_large = capacity_bits // large["bits"]
    rem = capacity_bits - n_large * large["bits"]
    n_small = 0
    if rem > 0:
        n_small = -(-rem // small["bits"])                    # ceil
        if n_small * small["bits"] >= large["bits"]:
            n_large += 1
            n_small = 0

    parts: List[Dict[str, Any]] = []
    parts += _bank_parts(_TEMPLATE_LARGE, n_large)
    parts += _bank_parts(_TEMPLATE_SMALL, n_small)

    total = n_large * large["bits"] + n_small * small["bits"]
    util = capacity_bits / total
    warnings = [
        f"capacity-only SRAM spec ({capacity_bits} bits): auto-applied macro "
        f"template(s) "
        + " + ".join(f"{c}x {n}" for n, c in
                     ((_TEMPLATE_LARGE, n_large), (_TEMPLATE_SMALL, n_small)) if c)
        + f" grouped into banks of <= {MAX_SUBARRAYS_PER_BANK} subarrays; "
        + f"utilization {util:.1%}"
    ]
    if util < 0.5:
        warnings.append(
            f"template utilization {util:.1%} < 50% — capacity is far below one "
            f"{_TEMPLATE_SMALL} macro; energy/area reflect the full macro"
        )
    return parts, warnings


#: Max subarrays (template macros) per bank in a template hierarchy.
MAX_SUBARRAYS_PER_BANK = 16


def _apply_template(features: Mapping[str, Any],
                    warnings: List[str]) -> Mapping[str, Any]:
    """Expand/validate ``mem_template`` in a features dict (no-op without one).

    ``mem_depth_per_bank`` encodes the bank's subarray count: it must be
    ``S x template.depth_words`` with 1 <= S <= 16 (omitted -> one subarray).
    """
    name = features.get("mem_template")
    if not name:
        return features
    t = SRAM_TEMPLATES.get(str(name))
    if t is None:
        raise ValueError(
            f"unknown mem_template '{name}'; available: "
            f"{', '.join(sorted(SRAM_TEMPLATES))}"
        )
    merged = dict(features)
    for feat, key in (("data_width", "io_bits"),
                      ("tile_rows", "tile_rows"), ("tile_cols", "tile_cols")):
        given = merged.get(feat)
        if given is None:
            merged[feat] = t[key]
        elif int(given) != t[key]:
            raise ValueError(
                f"mem_template '{name}' fixes {feat}={t[key]} but got {given} — "
                f"drop the explicit value or drop the template"
            )

    depth = merged.get("mem_depth_per_bank")
    if depth is None:
        merged["mem_depth_per_bank"] = t["depth_words"]          # S = 1
    else:
        depth = int(depth)
        s, rem = divmod(depth, t["depth_words"])
        if rem or not (1 <= s <= MAX_SUBARRAYS_PER_BANK):
            raise ValueError(
                f"mem_template '{name}': mem_depth_per_bank={depth} must be "
                f"S x {t['depth_words']} words with 1 <= S <= "
                f"{MAX_SUBARRAYS_PER_BANK} subarrays per bank (got S={s}"
                f"{f'+{rem}w' if rem else ''})"
            )

    warnings.append(
        f"mem_template '{name}' (256 WL x {t['col_mux']}:1 col-mux x "
        f"{t['io_bits']}b): mux approximated by 256x32 tile groups — unselected "
        f"groups' bitcell leakage + idle decoders are charged; shared-WL/BL "
        f"dynamic, the mux itself, and inter-bank select/routing are not modeled"
    )
    return merged


def normalize_config(
    features: Mapping[str, Any], ds: SramDataset
) -> Tuple[SramConfig, List[str]]:
    """Validate/canonicalize a features dict against the loaded dataset."""
    warnings: List[str] = []
    features = _apply_template(features, warnings)

    node_raw = features.get("node")
    if node_raw is None:
        raise ValueError("missing required feature 'node'")
    node = _norm_node(node_raw)
    if node not in ds.shapes_by_node:
        raise ValueError(
            f"node '{node}' not in the SRAM dataset "
            f"(available: {', '.join(sorted(ds.shapes_by_node))})"
        )

    corner = str(features.get("corner", "TT"))
    if corner != "TT":
        raise ValueError(f"corner '{corner}' not characterized (dataset is TT-only)")
    transistor = str(features.get("transistor", "hp"))
    if transistor != "hp":
        raise ValueError(f"transistor '{transistor}' not characterized (hp only)")

    depth_raw = features.get("mem_depth_per_bank")
    if depth_raw is None:
        raise ValueError(
            "missing required feature 'mem_depth_per_bank' (words per bank)")
    width_raw = features.get("data_width")
    if width_raw is None:
        raise ValueError("missing required feature 'data_width' (word width in bits)")
    depth = _pos_int(depth_raw, "mem_depth_per_bank")
    width = _pos_int(width_raw, "data_width")
    banks_raw = features.get("mem_banks")
    banks = _pos_int(banks_raw if banks_raw is not None else 1, "mem_banks")

    # Physical array ports = dedicated read + dedicated write + shared RW.
    # A bare macro with none of the three declared is the common 1RW case.
    r_p = int(features.get("mem_r_ports") or 0)
    w_p = int(features.get("mem_w_ports") or 0)
    rw_p = int(features.get("mem_rw_ports") or 0)
    ports = (r_p + w_p + rw_p) or 1
    if ports > 2:
        warnings.append(
            f"mem_r_ports+mem_w_ports+mem_rw_ports={ports} not characterized; "
            f"clamped to dual-port (2)"
        )
        ports = 2
    if ports == 2:
        warnings.append(
            "dual-port: per-access energy taken equal to single-port (measured), "
            "decoder count/area/leakage/idle doubled; array area assumed "
            "port-independent"
        )

    vdd = features.get("vdd_V")
    if vdd is not None:
        dv = round(float(vdd) - ds.nominal_vdd_by_node[node], 3)
    else:
        dv = round(float(features.get("voltage_offset_V", 0.0)), 3)

    temp = float(features.get("temperature_C", 25.0))

    optimize = str(features.get("optimize", "energy"))
    if optimize not in _OBJECTIVES:
        raise ValueError(f"optimize must be one of {_OBJECTIVES} (got '{optimize}')")

    source = str(features.get("source", "auto"))
    if source not in ("auto", "table", "mlp"):
        raise ValueError(f"source must be auto|table|mlp (got '{source}')")
    model_dir = features.get("model_dir")

    tile_rows = features.get("tile_rows")
    tile_cols = features.get("tile_cols")
    tile_rows = int(tile_rows) if tile_rows is not None else None
    tile_cols = int(tile_cols) if tile_cols is not None else None

    clock = features.get("clock_mhz")
    cfg = SramConfig(
        node=node,
        width_bits=width,
        depth_words=depth,
        banks=banks,
        ports=ports,
        voltage_offset_v=dv,
        temperature_c=temp,
        toggle_rate=_fraction(features, "toggle_rate", 0.5),
        read_zero_fraction=_fraction(features, "read_zero_fraction", 0.5),
        addr_toggle_rate=_fraction(features, "addr_toggle_rate", 0.5),
        optimize=optimize,
        tile_rows=tile_rows,
        tile_cols=tile_cols,
        tile_clock_gating=bool(features.get("tile_clock_gating", False)),
        allow_ragged_edge=bool(features.get("allow_ragged_edge", True)),
        clock_mhz=float(clock) if clock else None,
        source=source,
        model_dir=str(model_dir) if model_dir else None,
        template=(str(features["mem_template"])
                  if features.get("mem_template") else None),
    )
    return cfg, warnings


# --------------------------------------------------------------------------
# PVT scaling (separable multiplicative model from the reference shapes)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PvtScale:
    """Multiplicative k-factors vs (TT, nominal V, 25C), per metric class."""

    k_rd_dyn: float = 1.0
    k_wr_dyn: float = 1.0
    k_dec_dyn: float = 1.0
    k_leak_array: float = 1.0
    k_leak_dec: float = 1.0
    k_t_read: float = 1.0
    k_t_write: float = 1.0
    spread: Tuple[Tuple[str, float], ...] = ()   # per metric: max/min across refs
    warnings: Tuple[str, ...] = ()


# metric -> (needs_array, needs_dec, evaluator(ArrayPoint|None, DecoderPoint|None))
_PVT_METRICS: Dict[str, Any] = {
    "rd_dyn": (True, False,
               lambda a, d: 0.5 * (a.rd_1to1_dyn_pJ + a.rd_1to0_dyn_pJ)),
    "wr_dyn": (True, False,
               lambda a, d: 0.5 * (a.wr_same_dyn_pJ + a.wr_toggle_dyn_pJ)),
    "dec_dyn": (False, True,
                lambda a, d: (d.act_dyn_pJ + d.flip_dyn_pJ + d.idle_dyn_pJ) / 3.0),
    "leak_array": (True, False, lambda a, d: a.leak_power_mW),
    "leak_dec": (False, True, lambda a, d: d.leak_power_mW),
    "t_read": (True, True, lambda a, d: d.wlen_wl_ns + a.rd_delay_ns),
    "t_write": (True, True,
                lambda a, d: max(d.wlen_wl_ns, a.wr_bl_ns) + a.wr_cell_ns),
}
_LOG_T_METRICS = ("leak_array", "leak_dec")     # exponential in temperature


def _anchor_k(ds: SramDataset, node: str, metric: str,
              dv: float, temp: float) -> Tuple[Optional[float], float]:
    """(geomean k, max/min spread) across available refs at one measured anchor."""
    needs_a, needs_d, fn = _PVT_METRICS[metric]
    ratios: List[float] = []
    for (r, c) in _REF_SHAPES:
        a_nom = ds.nominal_array.get((node, r, c))
        d_nom = ds.nominal_dec.get((node, r, c))
        a_pvt = ds.pvt_array.get((node, r, c, dv, temp))
        d_pvt = ds.pvt_dec.get((node, r, c, dv, temp))
        if needs_a and (a_nom is None or a_pvt is None):
            continue
        if needs_d and (d_nom is None or d_pvt is None):
            continue
        nom = fn(a_nom, d_nom)
        pvt = fn(a_pvt, d_pvt)
        if nom <= 0.0 or pvt <= 0.0:
            continue
        ratios.append(pvt / nom)
    if not ratios:
        return None, 1.0
    k = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    return k, max(ratios) / min(ratios)


def _interp_dv(anchors: Dict[float, float], dv: float) -> float:
    """Piecewise-linear interpolation over the measured offset grid."""
    if dv in anchors:
        return anchors[dv]
    xs = sorted(anchors)
    lo = max((x for x in xs if x < dv), default=xs[0])
    hi = min((x for x in xs if x > dv), default=xs[-1])
    if lo == hi:
        return anchors[lo]
    t = (dv - lo) / (hi - lo)
    return anchors[lo] + t * (anchors[hi] - anchors[lo])


def pvt_domain(ds: SramDataset, node: str):
    """Measured PVT domain for a node (from the decoder sheet's ref-shape rows).

    Returns (dvs_by_temp, all_dvs, t_lo, t_hi). Shared by the table k-scaling
    and the MLP source so both clamp to the identical per-node domain (e.g.
    20nm's rejected +0.15 V rows are simply absent -> bound is +0.10 there).
    """
    dvs_by_temp: Dict[float, set] = {}
    for (n, r, c, adv, at) in ds.pvt_dec:
        if n == node and (r, c) in _REF_SHAPES:
            dvs_by_temp.setdefault(at, set()).add(adv)
    if not dvs_by_temp:
        raise ValueError(f"no PVT reference data for node '{node}'")
    all_dvs = sorted(set().union(*dvs_by_temp.values()) | {0.0})
    return dvs_by_temp, all_dvs, 25.0, max(dvs_by_temp)


def clamp_pvt(ds: SramDataset, node: str, dv: float,
              temp: float) -> Tuple[float, float, List[str]]:
    """Clamp (dv, temp) into the measured domain; returns (q_dv, q_temp, warns)."""
    _, all_dvs, t_lo, t_hi = pvt_domain(ds, node)
    warnings: List[str] = []
    q_dv, q_temp = dv, temp
    if q_dv < all_dvs[0] or q_dv > all_dvs[-1]:
        q_dv = min(max(q_dv, all_dvs[0]), all_dvs[-1])
        warnings.append(
            f"voltage_offset_V={dv:+.3f} outside measured range "
            f"[{all_dvs[0]:+.2f}, {all_dvs[-1]:+.2f}]; clamped to {q_dv:+.2f}"
        )
    if q_temp < t_lo or q_temp > t_hi:
        q_temp = min(max(q_temp, t_lo), t_hi)
        warnings.append(
            f"temperature_C={temp:g} outside measured range [{t_lo:g}, {t_hi:g}]; "
            f"clamped to {q_temp:g}"
        )
    return q_dv, q_temp, warnings


def pvt_scale(ds: SramDataset, node: str, dv: float, temp: float) -> PvtScale:
    """k-factors at (dv, temp); identity at the nominal point."""
    if dv == 0.0 and temp == 25.0:
        return PvtScale()

    dvs_by_temp, _, t_lo, t_hi = pvt_domain(ds, node)
    q_dv, q_temp, warnings = clamp_pvt(ds, node, dv, temp)

    ks: Dict[str, float] = {}
    spreads: List[Tuple[str, float]] = []
    for metric in _PVT_METRICS:
        per_temp: Dict[float, float] = {}
        worst_spread = 1.0
        for at in (t_lo, t_hi):
            anchors: Dict[float, float] = {}
            if at == 25.0:
                anchors[0.0] = 1.0              # the nominal point itself
            for adv in sorted(dvs_by_temp.get(at, ())):
                k, spread = _anchor_k(ds, node, metric, adv, at)
                if k is not None:
                    anchors[adv] = k
                    worst_spread = max(worst_spread, spread)
            if not anchors:
                raise ValueError(
                    f"no usable PVT reference rows for node '{node}' "
                    f"metric '{metric}' at {at:g}C"
                )
            per_temp[at] = _interp_dv(anchors, q_dv)
        k_lo, k_hi = per_temp[t_lo], per_temp[t_hi]
        frac = 0.0 if t_hi == t_lo else (q_temp - t_lo) / (t_hi - t_lo)
        if metric in _LOG_T_METRICS and k_lo > 0 and k_hi > 0:
            k = math.exp(math.log(k_lo) + frac * (math.log(k_hi) - math.log(k_lo)))
        else:
            k = k_lo + frac * (k_hi - k_lo)
        ks[metric] = k
        spreads.append((metric, worst_spread))
        if worst_spread > _PVT_SPREAD_WARN:
            warnings.append(
                f"PVT scaling for '{metric}' disagrees across reference shapes "
                f"(max/min = {worst_spread:.2f}); shape-dependent PVT behaviour "
                "is averaged"
            )

    return PvtScale(
        k_rd_dyn=ks["rd_dyn"],
        k_wr_dyn=ks["wr_dyn"],
        k_dec_dyn=ks["dec_dyn"],
        k_leak_array=ks["leak_array"],
        k_leak_dec=ks["leak_dec"],
        k_t_read=ks["t_read"],
        k_t_write=ks["t_write"],
        spread=tuple(spreads),
        warnings=tuple(warnings),
    )


# --------------------------------------------------------------------------
# TilePointSource seam — the MLP models drop in behind this call.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TileCosts:
    """Per-tile costs at the queried PVT (dynamics pure, leakage as power)."""

    rows: int
    cols: int
    rd_1to1_dyn_pJ: float
    rd_1to0_dyn_pJ: float
    wr_same_dyn_pJ: float
    wr_toggle_dyn_pJ: float
    dec_act_dyn_pJ: float
    dec_flip_dyn_pJ: float
    dec_idle_dyn_pJ: float
    leak_array_mW: float
    leak_dec_mW: float
    t_read_ns: float
    t_write_ns: float
    array_area_um2: float
    dec_area_um2: float


class TableTilePointSource:
    """Exact grid lookup + separable PVT scaling (this task's source)."""

    def __init__(self, ds: SramDataset):
        self._ds = ds

    def tile_costs(self, node: str, rows: int, cols: int, k: PvtScale) -> TileCosts:
        a = self._ds.nominal_array[(node, rows, cols)]
        d = self._ds.nominal_dec[(node, rows, cols)]
        return TileCosts(
            rows=rows, cols=cols,
            rd_1to1_dyn_pJ=k.k_rd_dyn * a.rd_1to1_dyn_pJ,
            rd_1to0_dyn_pJ=k.k_rd_dyn * a.rd_1to0_dyn_pJ,
            wr_same_dyn_pJ=k.k_wr_dyn * a.wr_same_dyn_pJ,
            wr_toggle_dyn_pJ=k.k_wr_dyn * a.wr_toggle_dyn_pJ,
            dec_act_dyn_pJ=k.k_dec_dyn * d.act_dyn_pJ,
            dec_flip_dyn_pJ=k.k_dec_dyn * d.flip_dyn_pJ,
            dec_idle_dyn_pJ=k.k_dec_dyn * d.idle_dyn_pJ,
            leak_array_mW=k.k_leak_array * a.leak_power_mW,
            leak_dec_mW=k.k_leak_dec * d.leak_power_mW,
            t_read_ns=k.k_t_read * (d.wlen_wl_ns + a.rd_delay_ns),
            t_write_ns=k.k_t_write * (max(d.wlen_wl_ns, a.wr_bl_ns) + a.wr_cell_ns),
            array_area_um2=a.array_area_um2,
            dec_area_um2=d.dec_area_um2,
        )


# --------------------------------------------------------------------------
# Tile-source resolution (table vs trained MLPs)
# --------------------------------------------------------------------------
# sram_mlp.py (torch side) is loaded lazily BY FILE PATH so this module stays
# stdlib-only and runpy-safe; the plugin remains standalone in this directory.

_MLP_MOD_CACHE: Dict[str, Any] = {}


def _load_mlp_module() -> Tuple[Any, Optional[str]]:
    if "mod" not in _MLP_MOD_CACHE:
        path = Path(__file__).resolve().parent / "sram_mlp.py"
        try:
            spec = importlib.util.spec_from_file_location("_npuwattch_sram_mlp", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            _MLP_MOD_CACHE.update(mod=mod, err=None)
        except Exception as e:
            sys.modules.pop("_npuwattch_sram_mlp", None)
            _MLP_MOD_CACHE.update(mod=None, err=f"{type(e).__name__}: {e}")
    return _MLP_MOD_CACHE["mod"], _MLP_MOD_CACHE["err"]


def _resolve_source(cfg: "SramConfig", ds: SramDataset):
    """Pick the tile-cost source per cfg.source.

    Returns (src, source_used, model_meta, warnings). 'auto' prefers the
    trained MLPs when the checkpoint quartets are present and torch imports;
    otherwise falls back to the table with a warning naming the reason.
    Explicit 'mlp' raises instead of falling back.
    """
    if cfg.source == "table":
        return TableTilePointSource(ds), "table", None, []
    model_dir = Path(cfg.model_dir) if cfg.model_dir else Path(__file__).resolve().parent
    mod, err = _load_mlp_module()
    reason = None
    if mod is None:
        reason = f"sram_mlp unavailable ({err})"
    elif not mod.available(model_dir):
        reason = f"model checkpoint quartets incomplete in {model_dir}"
    if reason:
        if cfg.source == "mlp":
            raise ValueError(f"source='mlp' requested but {reason}")
        return (TableTilePointSource(ds), "table", None,
                [f"source=auto fell back to table: {reason}"])
    q_dv, q_temp, _ = clamp_pvt(ds, cfg.node, cfg.voltage_offset_v,
                                cfg.temperature_c)
    bundle, bwarns = mod.load_bundle(model_dir, ds.dataset_dir)
    src = mod.MlpTilePointSource(bundle, q_dv, q_temp, TileCosts)
    return src, "mlp", bundle.summary(), list(bwarns)


# --------------------------------------------------------------------------
# Structure solver + cost composition
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SramStructure:
    tile_rows: int
    tile_cols: int
    edge_cols: Optional[int]     # ragged last horizontal tile (None = uniform)
    n_vert: int                  # vertical tile groups (one selected per access)
    n_horz: int                  # horizontal tiles incl. the edge tile
    banks: int
    ports: int
    tiles_per_bank: int
    total_tiles: int
    logical_bits: int
    physical_bits: int
    utilization: float


@dataclass(frozen=True)
class SramUnitCosts:
    """Whole-instance unit costs (all banks, all ports composed in)."""

    e_read_pJ: float             # one access + every other enabled decoder idling
    e_write_pJ: float
    e_idle_pJ: float             # per cycle, enabled but not accessed
    leak_power_mW: float
    area_um2: float
    t_read_ns: float
    t_write_ns: float
    f_max_MHz: float
    # breakdown (per single access / per bank-cycle, before bank multiplication)
    rd_array_pJ: float
    wr_array_pJ: float
    dec_access_pJ: float
    idle_overhead_pJ: float      # the (N_dec - fired) * dec_idle term per access
    bank_idle_pJ: float          # per cycle, one bank
    leak_array_mW: float
    leak_dec_mW: float
    structure: SramStructure
    pvt: PvtScale
    warnings: Tuple[str, ...] = ()
    source: str = "table"                        # tile-cost source used
    model_meta: Optional[Dict[str, Any]] = None  # MLP bundle summary (mlp only)


def _horz_tiling(cfg: SramConfig, shapes: Sequence[Tuple[int, int]],
                 r: int, c: int) -> Optional[List[Tuple[int, int]]]:
    """[(cols, used_bits), ...] horizontal tiles for primary shape (r, c)."""
    width = cfg.width_bits
    ragged = cfg.allow_ragged_edge and cfg.tile_cols is None
    if not ragged:
        n = math.ceil(width / c)
        tiles = [(c, c)] * (n - 1) + [(c, width - (n - 1) * c)]
        return tiles
    n_full = width // c
    rem = width - n_full * c
    tiles = [(c, c)] * n_full
    if rem:
        edge_opts = sorted(c2 for (r2, c2) in shapes if r2 == r and c2 >= rem)
        if not edge_opts:
            return None                       # no measured edge tile fits
        tiles.append((edge_opts[0], rem))
    return tiles


def _compose(cfg: SramConfig, src: TableTilePointSource, k: PvtScale,
             r: int, horz: List[Tuple[int, int]]) -> SramUnitCosts:
    """Cost a candidate structure (see module docstring for the model)."""
    n_vert = math.ceil(cfg.depth_words / r)
    p0 = cfg.read_zero_fraction
    a = cfg.addr_toggle_rate
    P = cfg.ports

    rd_array = wr_array = dec_access = dec_idle_horz = 0.0
    leak_arr = leak_dec = area = 0.0
    t_read = t_write = 0.0
    for cols, used in horz:
        t = src.tile_costs(cfg.node, r, cols, k)
        rd_array += (1.0 - p0) * t.rd_1to1_dyn_pJ + p0 * t.rd_1to0_dyn_pJ
        f_tile = cfg.toggle_rate * used / cols
        wr_array += t.wr_same_dyn_pJ + f_tile * (t.wr_toggle_dyn_pJ - t.wr_same_dyn_pJ)
        dec_access += t.dec_act_dyn_pJ + a * (t.dec_flip_dyn_pJ - t.dec_act_dyn_pJ)
        dec_idle_horz += t.dec_idle_dyn_pJ
        leak_arr += t.leak_array_mW
        leak_dec += P * t.leak_dec_mW
        area += t.array_area_um2 + P * t.dec_area_um2
        t_read = max(t_read, t.t_read_ns)
        t_write = max(t_write, t.t_write_ns)

    # decoders in the instance = banks * n_vert * n_horz * P; one access fires
    # the n_horz decoders of one port's selected group, the rest idle (unless
    # per-tile clock gating is assumed).
    if cfg.tile_clock_gating:
        idle_overhead = 0.0
        bank_idle = 0.0
        e_idle = 0.0
    else:
        idle_overhead = (cfg.banks * n_vert * P - 1) * dec_idle_horz
        bank_idle = n_vert * P * dec_idle_horz
        e_idle = cfg.banks * bank_idle

    e_read = rd_array + dec_access + idle_overhead
    e_write = wr_array + dec_access + idle_overhead
    leak_power = cfg.banks * n_vert * (leak_arr + leak_dec)
    area_total = cfg.banks * n_vert * area

    n_horz = len(horz)
    edge_cols = horz[-1][0] if (n_horz and horz[-1][0] != horz[0][0]) else None
    physical_bits = cfg.banks * n_vert * r * sum(cols for cols, _ in horz)
    logical_bits = cfg.banks * cfg.depth_words * cfg.width_bits
    structure = SramStructure(
        tile_rows=r,
        tile_cols=horz[0][0],
        edge_cols=edge_cols,
        n_vert=n_vert,
        n_horz=n_horz,
        banks=cfg.banks,
        ports=P,
        tiles_per_bank=n_vert * n_horz,
        total_tiles=cfg.banks * n_vert * n_horz,
        logical_bits=logical_bits,
        physical_bits=physical_bits,
        utilization=logical_bits / physical_bits,
    )
    return SramUnitCosts(
        e_read_pJ=e_read,
        e_write_pJ=e_write,
        e_idle_pJ=e_idle,
        leak_power_mW=leak_power,
        area_um2=area_total,
        t_read_ns=t_read,
        t_write_ns=t_write,
        f_max_MHz=1000.0 / max(t_read, t_write),
        rd_array_pJ=rd_array,
        wr_array_pJ=wr_array,
        dec_access_pJ=dec_access,
        idle_overhead_pJ=idle_overhead,
        bank_idle_pJ=bank_idle,
        leak_array_mW=cfg.banks * n_vert * leak_arr,
        leak_dec_mW=cfg.banks * n_vert * leak_dec,
        structure=structure,
        pvt=k,
    )


def _rank_key(cfg: SramConfig, c: SramUnitCosts) -> Tuple:
    e = round(c.e_read_pJ, 9)
    ar = round(c.area_um2, 6)
    t = round(c.t_read_ns, 6)
    s = c.structure
    if cfg.optimize == "area":
        return (ar, e, t, s.tile_rows, s.tile_cols)
    if cfg.optimize == "delay":
        return (t, e, ar, s.tile_rows, s.tile_cols)
    return (e, ar, t, s.tile_rows, s.tile_cols)


def _bank_hierarchy_costs(cfg: SramConfig, ds: SramDataset,
                          extra_warnings: Sequence[str] = ()) -> SramUnitCosts:
    """Compose a template instance from ONE measured subarray.

    A template instance is a hierarchy::

        instance -> cfg.banks banks -> S subarrays each -> col-mux tile groups
                    (S = depth_words / template.depth_words, <= 16)

    where "subarray" = one template macro — the largest thing the datasets can
    cost directly. The recursive call below prices that subarray (banks=1,
    template cleared); everything above it is arithmetic on the result.

    Access semantics (user-defined 2026-07-21, bank-level clock gating):

    * the accessed subarray pays a full read/write (its internal col-mux group
      composition included — that is the recursive call's own idle_overhead);
    * its S-1 siblings in the SAME bank are clocked but not accessed — one
      subarray-idle each, folded into the per-access energy;
    * every other bank is clock-gated: leakage only, charged by the
      ``leak_power`` term over time, never per access.
    """
    t = SRAM_TEMPLATES[cfg.template]
    s_per_bank = cfg.depth_words // t["depth_words"]
    n_subarrays = cfg.banks * s_per_bank

    subarray = _unit_costs_for_cfg(
        replace(cfg, template=None, depth_words=t["depth_words"], banks=1),
        ds, extra_warnings,
    )
    sibling_idle = (s_per_bank - 1) * subarray.e_idle_pJ

    st = subarray.structure
    structure = replace(
        st,
        banks=cfg.banks,
        tiles_per_bank=s_per_bank * st.tiles_per_bank,
        total_tiles=n_subarrays * st.total_tiles,
        logical_bits=n_subarrays * st.logical_bits,
        physical_bits=n_subarrays * st.physical_bits,
    )
    return replace(
        subarray,
        e_read_pJ=subarray.e_read_pJ + sibling_idle,
        e_write_pJ=subarray.e_write_pJ + sibling_idle,
        e_idle_pJ=s_per_bank * subarray.e_idle_pJ,   # one bank held active
        idle_overhead_pJ=subarray.idle_overhead_pJ + sibling_idle,
        bank_idle_pJ=s_per_bank * subarray.e_idle_pJ,
        leak_power_mW=n_subarrays * subarray.leak_power_mW,
        leak_array_mW=n_subarrays * subarray.leak_array_mW,
        leak_dec_mW=n_subarrays * subarray.leak_dec_mW,
        area_um2=n_subarrays * subarray.area_um2,
        structure=structure,
        # timing stays the single-subarray path; bank select/routing is part of
        # the approximation warning emitted by _apply_template.
    )


def _unit_costs_for_cfg(cfg: SramConfig, ds: SramDataset,
                        extra_warnings: Sequence[str] = ()) -> SramUnitCosts:
    if cfg.template:
        return _bank_hierarchy_costs(cfg, ds, extra_warnings)
    shapes = ds.shapes_by_node[cfg.node]
    # k (separable table scaling) is ALWAYS computed: the MLP source ignores
    # its factors but the report keeps it as a diagnostic, and it carries the
    # domain-clamp / ref-spread warnings for both sources.
    k = pvt_scale(ds, cfg.node, cfg.voltage_offset_v, cfg.temperature_c)
    src, source_used, model_meta, src_warns = _resolve_source(cfg, ds)

    cands = [(r, c) for (r, c) in shapes
             if (cfg.tile_rows is None or r == cfg.tile_rows)
             and (cfg.tile_cols is None or c == cfg.tile_cols)]
    if not cands:
        avail = ", ".join(f"{r}x{c}" for r, c in shapes)
        raise ValueError(
            f"no measured tile shape matches tile_rows={cfg.tile_rows} "
            f"tile_cols={cfg.tile_cols} at {cfg.node} (available: {avail})"
        )

    best: Optional[SramUnitCosts] = None
    best_key: Optional[Tuple] = None
    seen: set = set()
    for (r, c) in cands:
        horz = _horz_tiling(cfg, shapes, r, c)
        if not horz:
            continue
        sig = (r, tuple(horz))
        if sig in seen:                      # wide-c candidates can collapse
            continue
        seen.add(sig)
        costs = _compose(cfg, src, k, r, horz)
        key = _rank_key(cfg, costs)
        if best_key is None or key < best_key:
            best, best_key = costs, key
    if best is None:
        raise ValueError(f"no feasible tiling for {cfg}")

    warnings = list(extra_warnings) + list(k.warnings) + list(src_warns)
    s = best.structure
    if s.utilization < _UTIL_WARN:
        warnings.append(
            f"physical-bit utilization {s.utilization:.2f} "
            f"({s.logical_bits}/{s.physical_bits} bits); the padding still "
            "burns read energy and leakage"
        )
    if s.tiles_per_bank > _TILE_GLUE_WARN:
        warnings.append(
            f"{s.tiles_per_bank} tiles/bank: inter-tile glue (address/enable "
            "fanout, dout muxing, bank select) is not in the datasets — "
            "energy/delay are underestimated at high tile counts"
        )
    if cfg.clock_mhz and cfg.clock_mhz > best.f_max_MHz:
        warnings.append(
            f"clock_mhz={cfg.clock_mhz:g} exceeds f_max={best.f_max_MHz:.1f} MHz "
            f"(t_read={best.t_read_ns:.3f} ns, t_write={best.t_write_ns:.3f} ns)"
        )
    return replace(best, warnings=tuple(warnings), source=source_used,
                   model_meta=model_meta)


def unit_costs(features: Mapping[str, Any]) -> SramUnitCosts:
    """Public one-call query: features dict -> whole-instance unit costs."""
    ds = load_dataset(_resolve_dataset_dir(features))
    cfg, warns = normalize_config(features, ds)
    return _unit_costs_for_cfg(cfg, ds, warns)


def energy_for_stim_mode(costs: SramUnitCosts, stim_mode: str) -> float:
    """Map a stim_mode to whole-instance dynamic energy per cycle/event [pJ]."""
    if stim_mode == "read":
        return costs.e_read_pJ
    if stim_mode == "write":
        return costs.e_write_pJ
    if stim_mode == "idle":
        return costs.e_idle_pJ
    if stim_mode == "random":
        return 0.5 * (costs.e_read_pJ + costs.e_write_pJ)
    raise ValueError(f"unknown sram stim_mode '{stim_mode}' (use {_STIM_MODES})")


# --------------------------------------------------------------------------
# EstimatorHost entrypoints (return None on error, per host contract)
# --------------------------------------------------------------------------

def _entry(features: Optional[Mapping[str, Any]]):
    if not isinstance(features, Mapping):
        raise ValueError("features dict required")
    return unit_costs(features)


def get_energy(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Dynamic energy [pJ] for features['stim_mode'|'op'] (default: read)."""
    try:
        costs = _entry(features)
        mode = (features.get("stim_mode") or features.get("op") or "read")
        return energy_for_stim_mode(costs, str(mode))
    except Exception as e:  # host contract: never raise
        print(f"[ERROR] sram: {e}")
        return None


def get_area(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Total macro area [um2] (all banks, arrays + decoders)."""
    try:
        return _entry(features).area_um2
    except Exception as e:
        print(f"[ERROR] sram: {e}")
        return None


def get_timing(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Read access time [ns] (decoder wlen->WL + array WL->OUT)."""
    try:
        return _entry(features).t_read_ns
    except Exception as e:
        print(f"[ERROR] sram: {e}")
        return None


def get_leakage(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Static leakage power [mW] (all banks, arrays + decoders)."""
    try:
        return _entry(features).leak_power_mW
    except Exception as e:
        print(f"[ERROR] sram: {e}")
        return None


def get_unit_costs(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[dict]:
    """Whole SramUnitCosts as a plain dict."""
    try:
        return asdict(_entry(features))
    except Exception as e:
        print(f"[ERROR] sram: {e}")
        return None


def get_report(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[dict]:
    """Unit costs + structure + provenance (raw dataset rows used) + warnings."""
    try:
        ds = load_dataset(_resolve_dataset_dir(features))
        cfg, warns = normalize_config(features, ds)
        costs = _unit_costs_for_cfg(cfg, ds, warns)
        s = costs.structure
        shapes_used = sorted({(s.tile_rows, c) for c in
                              ({s.tile_cols} | ({s.edge_cols} if s.edge_cols else set()))})
        provenance = []
        for (r, c) in shapes_used:
            a = ds.nominal_array[(cfg.node, r, c)]
            d = ds.nominal_dec[(cfg.node, r, c)]
            provenance.append({
                "shape": f"{r}x{c}",
                "array_flow_run_id": a.flow_run_id,
                "decoder_flow_run_id": d.flow_run_id,
                "aux": {
                    "wr1_init_energy_pJ": a.wr1_init_energy_pJ,
                    "wr0_fill_energy_pJ": a.wr0_fill_energy_pJ,
                    "rd_bl_dev_ns": a.rd_bl_dev_ns,
                    "rd_sense_ns": a.rd_sense_ns,
                },
            })
        return {
            "config": asdict(cfg),
            "unit_costs": asdict(costs),
            "structure": asdict(s),
            "pvt_scale": asdict(costs.pvt),
            "provenance": provenance,
            "warnings": list(costs.warnings),
            "calibrated": True,
            "source": costs.source,
            "model_meta": costs.model_meta,
            "dataset_dir": str(ds.dataset_dir),
        }
    except Exception as e:
        print(f"[ERROR] sram: {e}")
        return None


# --------------------------------------------------------------------------
# UnitCostProvider factory (structural match for npuwattch.energy's Protocol)
# --------------------------------------------------------------------------

class _SramUnitCostProvider:
    """Routes primitive == 'sram' to this estimator; the rest to a fallback.

    Implements the ``UnitCostProvider`` protocol structurally (calibrated flag
    + four methods) without importing npuwattch, so this file stays runpy-safe.
    Costs are memoized per normalized config (SramConfig is frozen/hashable).
    """

    def __init__(self, defaults: Optional[Mapping[str, Any]] = None,
                 dataset_dir: Optional[str] = None, fallback: Any = None):
        self._defaults = dict(defaults or {})
        if dataset_dir:
            self._defaults.setdefault("dataset_dir", dataset_dir)
        self._fallback = fallback
        self._cache: Dict[SramConfig, SramUnitCosts] = {}
        self.calibrated = (True if fallback is None
                           else bool(getattr(fallback, "calibrated", False)))

    def _costs(self, features: Mapping[str, Any]) -> SramUnitCosts:
        merged = {**self._defaults, **dict(features)}
        ds = load_dataset(_resolve_dataset_dir(merged))
        cfg, warns = normalize_config(merged, ds)
        hit = self._cache.get(cfg)
        if hit is None:
            hit = _unit_costs_for_cfg(cfg, ds, warns)
            self._cache[cfg] = hit
        return hit

    def _delegate(self, method: str, primitive: str,
                  features: Mapping[str, Any]) -> float:
        if self._fallback is None:
            raise ValueError(
                f"sram provider got primitive '{primitive}' and has no fallback"
            )
        return getattr(self._fallback, method)(primitive, features)

    def energy_per_cycle(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "sram":
            return self._delegate("energy_per_cycle", primitive, features)
        mode = str(features.get("stim_mode", "random"))
        return energy_for_stim_mode(self._costs(features), mode)

    def leak_power(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "sram":
            return self._delegate("leak_power", primitive, features)
        return self._costs(features).leak_power_mW

    def area(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "sram":
            return self._delegate("area", primitive, features)
        return self._costs(features).area_um2

    def crit_path(self, primitive: str, features: Mapping[str, Any]) -> float:
        if primitive != "sram":
            return self._delegate("crit_path", primitive, features)
        c = self._costs(features)
        return max(c.t_read_ns, c.t_write_ns)


def make_unit_cost_provider(defaults: Optional[Mapping[str, Any]] = None,
                            dataset_dir: Optional[str] = None,
                            fallback: Any = None) -> _SramUnitCostProvider:
    """Build a UnitCostProvider for 'sram' primitives.

    ``defaults`` are merged UNDER each call's features (activity policy etc.);
    ``fallback`` (any UnitCostProvider) handles non-sram primitives — without
    one, non-sram queries raise. ``calibrated`` is True in strict (no-fallback)
    mode, else inherited from the fallback (conservative).
    """
    return _SramUnitCostProvider(defaults=defaults, dataset_dir=dataset_dir,
                                 fallback=fallback)
