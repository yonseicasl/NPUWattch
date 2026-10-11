"""SRAM macro estimator. Measured tables and trained MLPs give its costs.

The estimator answers a CACTI-style query: node, depth, width, banks, PVT, and
activity. It gives the energy, leakage, area, and timing of an SRAM macro.
The macro is a composition of the SPICE-measured tiles in
``dataset_gen/sram/datasets/``:

- ``sram_array.csv`` is the tile dataset. Each row is a 6T bitcell tile
  (rows x cols) with its read and write energies, leakage, delays, and GDS
  area.
- ``sram_decoder.csv`` has the pitch-matched registered row decoder of each
  tile. The decoder data includes the wordline RC that the decoder drives.
  The array testbench uses an ideal wordline source. Thus the wordline charge
  energy is counted one time only, in the decoder data.

Model (the dataset has no column mux and no wordline stitching):

- A macro is banks x (n_vert x n_horz) measured tiles.
- Each tile has its own row decoder for each port (x ``n_ports``).
- One access selects one vertical tile group. All horizontal tiles of the
  group fire together.
- The array has no clock. Thus an array without an access has leakage only.
- Only the accessed bank has a clock. The other banks are clock-gated, as a
  compiler macro with its chip enable off, and have leakage only. A cycle
  without an access has leakage only.
- In the accessed bank, a decoder that has a clock but does not fire uses
  ``dec_idle`` energy. The energy of one access includes this energy of the
  other tile groups of the bank. ``tile_clock_gating`` sets it to zero.
- The solver selects the tiling with the fewest tiles in a bank, thus the
  largest measured tiles. The datasets do not model the composition of tiles
  in either direction: the glue between vertical groups (address and enable
  fanout, data-out mux) is not in them, and each horizontal tile has its own
  decoder where a real macro shares one decoder across a wide wordline. If
  the objective alone selected the tiling, it would use these errors: many
  short groups would look cheap and fast. The objective (``optimize``)
  selects between tilings with the same number of tiles.

Dataset energies are integrals across a 10 ns window. Each integral includes
the leakage of its window. The loader subtracts
``leak_power_mW * window_ns`` one time. Thus all subsequent values are
dynamic energy only. The energy aggregation (manual §6) adds the leakage
separately from ``leak_power``.

Delay composition (the two sheets use the same 50%-VDD wordline threshold):

    t_read  = dec_wlen_wl_ns + rd_delay_ns
    t_write = max(dec_wlen_wl_ns, wr_bl_ns) + wr_cell_ns

Vocabulary (it agrees with CACTI 5+/6 and with memory compilers):

- ``tile``: one measured bitcell array with its own row decoder. CACTI name:
  sub-array. A tile has one access at a time.
- ``tile group``: the ``n_horz`` tiles that fire together for one word. A
  bank has ``n_vert`` groups, and one access selects one group. A memory
  compiler calls this an internal "bank" or segment.
- ``macro``: one instance of a template (``sram_64k`` or ``sram_256k``). It
  has a decoder, a column mux, and I/O. A memory compiler gives a macro and
  PnR places it.
- ``bank``: ``mem_banks``. A bank is a unit with its own address and its own
  decoders. Accesses to different banks can occur concurrently. CACTI: "each
  bank can be concurrently accessed and has its own address and data bus".
- ``port``: a physical port of the array of a bank (1RW / 1R1W / 2RW). It is
  never the number of concurrent accesses.

Units are those of the repo: pJ / mW / um2 / ns. ``depth`` is words PER BANK.
Total bits = n_banks * depth * bw, as in the vocabulary of the class mapper.
This module uses only the standard library and the message catalog
(``npuwattch.diagnostics`` and ``npuwattch_estimators.errors``, which also use
only the standard library). Thus ``EstimatorHost`` can execute it with
``runpy`` in all environments.

The ``TilePointSource`` interface gives the cost of one tile. The ``source``
feature selects one of two implementations:

- ``TableTilePointSource``: exact grid lookup and separable PVT k-scaling.
- The trained MLP quartets: ``sram_mlp.py`` and the ``<metric>__v1.*``
  checkpoints in this directory. ``train_sram.py`` trains them and writes
  their metrics to ``eval_report.json``.

``source="auto"`` (the default) uses the MLPs if the checkpoints are present
and torch imports. If not, it uses the table and gives a warning with the
cause.
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

from npuwattch.diagnostics import NPUWattchError, emit, error, warning
from npuwattch_estimators.errors import (
    EstimatorQueryError, SramDatasetError, SramQueryError)

# --------------------------------------------------------------------------
# ESTIMATOR_SPEC. Keep it a pure literal: EstimatorHost reads it with
# ast.literal_eval and does not import this module.
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
_MEAS_WINDOW_NS = 10.0           # length of one operation window of the array TB
_REF_SHAPES = ((16, 8), (64, 16), (256, 32))   # reference shapes with a PVT sweep
_STIM_MODES = ("read", "write", "idle", "random")
_OBJECTIVES = ("energy", "area", "delay")
_PVT_SPREAD_WARN = 1.15          # warn above this spread between reference shapes
_TILE_GLUE_WARN = 4              # warn above this number of tiles in a bank (glue logic)
_UTIL_WARN = 0.5                 # warn below this utilization of physical bits
_DYN_EPS_PJ = 1e-9               # float error tolerance of the leakage subtraction


# --------------------------------------------------------------------------
# Dataset records
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ArrayPoint:
    """One row of sram_array.csv. The *_dyn energies do not include the window leakage."""

    rows: int
    cols: int
    wr_same_dyn_pJ: float
    wr_toggle_dyn_pJ: float      # all `cols` bits flip (the toggle_rate = 1.0 row)
    rd_1to1_dyn_pJ: float
    rd_1to0_dyn_pJ: float
    leak_power_mW: float
    rd_delay_ns: float
    wr_bl_ns: float
    wr_cell_ns: float
    array_area_um2: float
    decoder_area_um2: float
    # Provenance and auxiliary measurements. The model does not use them. The reports show them.
    wr1_init_energy_pJ: float
    wr0_fill_energy_pJ: float
    rd_bl_dev_ns: float
    rd_sense_ns: float
    flow_run_id: str


@dataclass(frozen=True)
class DecoderPoint:
    """One row of sram_decoder.csv. The *_dyn energies do not include the window leakage."""

    rows: int
    cols: int
    act_dyn_pJ: float            # the WL fires, same address
    flip_dyn_pJ: float           # the WL fires, all address bits toggle
    idle_dyn_pJ: float           # en=0, the clock toggles, no WL fires
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
    shapes_by_node: Dict[str, Tuple[Tuple[int, int], ...]]   # nominal shapes in both sheets
    validation_tr05: List[Dict[str, str]]                    # raw rows, for tests only


_DATASET_CACHE: Dict[str, SramDataset] = {}


def _resolve_dataset_dir(features: Optional[Mapping[str, Any]] = None) -> Path:
    """Find the dataset directory.

    Priority: features['dataset_dir'], then $NPUWATTCH_SRAM_DATA, then a
    search in the parent directories of this file.
    """
    explicit = (features or {}).get("dataset_dir") or os.environ.get(_DATASET_ENV)
    if explicit:
        cand = Path(explicit)
        if not (cand / _ARRAY_CSV).is_file() or not (cand / _DECODER_CSV).is_file():
            raise SramQueryError.nw(8201, path=cand)
        return cand
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "dataset_gen" / "sram" / "datasets"
        if (cand / _ARRAY_CSV).is_file() and (cand / _DECODER_CSV).is_file():
            return cand
    raise SramQueryError.nw(8202, env_var=_DATASET_ENV)


def _fnum(row: Mapping[str, str], key: str, ctx: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        raise SramDatasetError.nw(8203, key=key, context=ctx) from None


def _fnum_or(row: Mapping[str, str], key: str, default: float) -> float:
    """Parse a joined column that can be empty, and return ``default`` if it is.

    Example: ``decoder_area_um2`` of the array sheet is empty if the related
    decoder run failed.
    """
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def _dyn(raw_pJ: float, leak_mW: float, window_ns: float, ctx: str) -> float:
    """Return the dynamic energy: the raw window integral minus the leakage of the window."""
    dyn = raw_pJ - leak_mW * window_ns          # mW * ns == pJ
    if dyn < -_DYN_EPS_PJ:
        raise SramDatasetError.nw(8204, energy_pJ=dyn, context=ctx)
    return max(0.0, dyn)


def load_dataset(dataset_dir: Optional[Path] = None) -> SramDataset:
    """Parse and check the two sheets. The result is cached for each directory."""
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
                continue                        # the model uses only hp, TT rows
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
                    raise SramDatasetError.nw(8205, node=node, context=ctx)
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
                # This column is a join from the decoder sheet. It is empty if
                # the related decoder run failed. The model reads the decoder
                # area from the decoder sheet, thus this value is for
                # information only.
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
                    raise SramDatasetError.nw(8206, sheet="nominal array",
                                              key=key, context=ctx)
                nominal_array[key] = pt
            else:
                pkey = (node, r, c, dv, temp)
                if pkey in pvt_array:
                    raise SramDatasetError.nw(8206, sheet="PVT array",
                                              key=pkey, context=ctx)
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
                raise SramDatasetError.nw(8207, clk_ns=clk_ns, context=ctx)
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
                    raise SramDatasetError.nw(8206, sheet="nominal decoder",
                                              key=key, context=ctx)
                nominal_dec[key] = pt
            else:
                pkey = (node, r, c, dv, temp)
                if pkey in pvt_dec:
                    raise SramDatasetError.nw(8206, sheet="PVT decoder",
                                              key=pkey, context=ctx)
                pvt_dec[pkey] = pt

    if not nominal_array or not nominal_dec:
        raise SramDatasetError.nw(8208, path=ddir)

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
    """The normalized query. ``depth_words`` is words PER BANK."""

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
    model_dir: Optional[str] = None      # replaces the default checkpoint directory
    #: The name of the macro template. If it is set, the instance is a bank
    #: *hierarchy*: ``banks`` banks, each with
    #: ``depth_words / template.depth_words`` macros. Each macro is one
    #: instance of the template. ``_bank_hierarchy_costs`` calculates the
    #: costs from the query of one macro.
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
    raise EstimatorQueryError.nw(8002, node=value)


def _pos_int(value: Any, name: str) -> int:
    iv = int(value)
    if iv < 1:
        raise SramQueryError.nw(8209, name=name, value=value)
    return iv


def _fraction(features: Mapping[str, Any], name: str, default: float) -> float:
    v = float(features.get(name, default))
    if not 0.0 <= v <= 1.0:
        raise SramQueryError.nw(8210, name=name, value=v)
    return v


# --------------------------------------------------------------------------
# SRAM macro templates (for components that give only a capacity)
# --------------------------------------------------------------------------
#
# The bitline of a real macro is rarely longer than 256 cells. A larger
# capacity uses a column mux. If a component gives only a capacity (for
# example, "scratchpad = 16 MB" from a simulator), NPUWattch applies these two
# templates and gives a warning. It does not solve an unconstrained geometry.
#
# How the solver uses a template:
# - A template sets the tile shape to 256×32, a measured grid point of each
#   node.
# - Thus the mux groups become vertical tile groups: depth/rows(256) groups,
#   each with a read width of io_bits.
# - On an access, one group has dynamic energy. The other (mux-1) groups add
#   bitcell leakage and idle decoder energy.
# - This gives the exact column-mux leakage with configurations that the SRAM
#   datasets and MLPs support.
#
# Approximation (the estimator gives a warning):
# - A real macro with a column mux fires ONE wordline across all physical
#   columns and precharges all bitlines.
# - The tile model gives each group its own short wordline. Thus the dynamic
#   energy of the shared wordline and bitlines is too low.
# - The model does not include the column mux (pass gates, shared sense
#   amplifiers).

SRAM_TEMPLATES: Dict[str, Dict[str, int]] = {
    # name: wordlines × column mux × IO bits  (capacity = rows · io_bits · mux)
    "sram_64k": {"rows": 256, "col_mux": 4, "io_bits": 64,
                 "depth_words": 1024, "bits": 65536,
                 "tile_rows": 256, "tile_cols": 32},
    "sram_256k": {"rows": 256, "col_mux": 8, "io_bits": 128,
                  "depth_words": 2048, "bits": 262144,
                  "tile_rows": 256, "tile_cols": 32},
}
_TEMPLATE_SMALL, _TEMPLATE_LARGE = "sram_64k", "sram_256k"


def _bank_parts(template: str, n_macros: int) -> List[Dict[str, Any]]:
    """Divide the macros of a template into banks of 16 macros or fewer.

    The full banks of 16 macros are one part and come first. The remaining
    macros are a second part with one bank. An access to that bank charges
    only the macros that the bank has.
    """
    t = SRAM_TEMPLATES[template]
    parts = []
    full_banks, tail = divmod(n_macros, MAX_MACROS_PER_BANK)
    for banks, s_per_bank in ((full_banks, MAX_MACROS_PER_BANK), (1, tail)):
        if banks and s_per_bank:
            parts.append({
                "mem_template": template,
                "data_width": t["io_bits"],
                "mem_depth_per_bank": s_per_bank * t["depth_words"],
                "mem_banks": banks,
            })
    return parts


def resolve_capacity(capacity_bits: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Make a set of template macros that holds a given capacity.

    Macro count:

    - Use as many large (256k) macros as the capacity fills.
    - Use small (64k) macros for the remainder.
    - If the small macros have the capacity of one large macro or more, use
      one more large macro and no small macros.

    ``_bank_parts`` then divides the macros into banks of 16 macros maximum.

    Return ``(parts, warnings)``. Each part is a dict of component attributes
    with their NPUWattch names, for a description (manual §3.1):
    `mem_template`, `data_width`, `mem_depth_per_bank` (macros per bank x
    template depth), and `mem_banks`.
    """
    if capacity_bits <= 0:
        raise SramQueryError.nw(8211, capacity_bits=capacity_bits)
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
    templates = " + ".join(
        f"{c}x {n}" for n, c in
        ((_TEMPLATE_LARGE, n_large), (_TEMPLATE_SMALL, n_small)) if c)
    warnings = [warning(8212, capacity_bits=capacity_bits, templates=templates,
                        max_macros=MAX_MACROS_PER_BANK, utilization=util)]
    if util < 0.5:
        warnings.append(warning(8213, utilization=util, template=_TEMPLATE_SMALL))
    return parts, warnings


#: The maximum number of template macros in one bank of a template hierarchy.
MAX_MACROS_PER_BANK = 16


def _apply_template(features: Mapping[str, Any],
                    warnings: List[str]) -> Mapping[str, Any]:
    """Apply and check ``mem_template`` in a features dict.

    If there is no template, return the features without a change.
    ``mem_depth_per_bank`` gives the number of macros in a bank. It must be
    ``S x template.depth_words`` with 1 <= S <= 16. If it is absent, the bank
    has one macro.
    """
    name = features.get("mem_template")
    if not name:
        return features
    t = SRAM_TEMPLATES.get(str(name))
    if t is None:
        raise SramQueryError.nw(8214, template=name,
                                available=", ".join(sorted(SRAM_TEMPLATES)))
    merged = dict(features)
    for feat, key in (("data_width", "io_bits"),
                      ("tile_rows", "tile_rows"), ("tile_cols", "tile_cols")):
        given = merged.get(feat)
        if given is None:
            merged[feat] = t[key]
        elif int(given) != t[key]:
            raise SramQueryError.nw(8215, template=name, feature=feat,
                                    fixed=t[key], given=given)

    depth = merged.get("mem_depth_per_bank")
    if depth is None:
        merged["mem_depth_per_bank"] = t["depth_words"]          # S = 1
    else:
        depth = int(depth)
        s, rem = divmod(depth, t["depth_words"])
        if rem or not (1 <= s <= MAX_MACROS_PER_BANK):
            raise SramQueryError.nw(
                8216, template=name, depth=depth, macro_depth=t["depth_words"],
                max_macros=MAX_MACROS_PER_BANK,
                macros=f"{s}+{rem}w" if rem else s)

    warnings.append(warning(8217, template=name, col_mux=t["col_mux"],
                            io_bits=t["io_bits"]))
    return merged


def normalize_config(
    features: Mapping[str, Any], ds: SramDataset
) -> Tuple[SramConfig, List[str]]:
    """Check a features dict against the dataset and make the normalized query."""
    warnings: List[str] = []
    features = _apply_template(features, warnings)

    node_raw = features.get("node")
    if node_raw is None:
        raise SramQueryError.nw(8218, name="node", meaning="technology node")
    node = _norm_node(node_raw)
    if node not in ds.shapes_by_node:
        raise SramQueryError.nw(8219, node=node,
                                available=", ".join(sorted(ds.shapes_by_node)))

    corner = str(features.get("corner", "TT"))
    if corner != "TT":
        raise SramQueryError.nw(8220, corner=corner)
    transistor = str(features.get("transistor", "hp"))
    if transistor != "hp":
        raise SramQueryError.nw(8221, transistor=transistor)

    depth_raw = features.get("mem_depth_per_bank")
    if depth_raw is None:
        raise SramQueryError.nw(8218, name="mem_depth_per_bank",
                                meaning="words per bank")
    width_raw = features.get("data_width")
    if width_raw is None:
        raise SramQueryError.nw(8218, name="data_width",
                                meaning="word width in bits")
    depth = _pos_int(depth_raw, "mem_depth_per_bank")
    width = _pos_int(width_raw, "data_width")
    banks_raw = features.get("mem_banks")
    banks = _pos_int(banks_raw if banks_raw is not None else 1, "mem_banks")

    # Physical array ports = dedicated read + dedicated write + shared RW.
    # If a macro gives none of the three, it has one RW port (the usual case).
    r_p = int(features.get("mem_r_ports") or 0)
    w_p = int(features.get("mem_w_ports") or 0)
    rw_p = int(features.get("mem_rw_ports") or 0)
    ports = (r_p + w_p + rw_p) or 1
    if ports > 2:
        warnings.append(warning(8222, ports=ports))
        ports = 2
    if ports == 2:
        warnings.append(warning(8223))

    vdd = features.get("vdd_V")
    if vdd is not None:
        dv = round(float(vdd) - ds.nominal_vdd_by_node[node], 3)
    else:
        dv = round(float(features.get("voltage_offset_V", 0.0)), 3)

    temp = float(features.get("temperature_C", 25.0))

    optimize = str(features.get("optimize", "energy"))
    if optimize not in _OBJECTIVES:
        raise SramQueryError.nw(8224, choices=_OBJECTIVES, optimize=optimize)

    source = str(features.get("source", "auto"))
    if source not in ("auto", "table", "mlp"):
        raise SramQueryError.nw(8225, source=source)
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
# PVT scaling (a separable multiplicative model from the reference shapes)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PvtScale:
    """Multiplicative k-factors relative to (TT, nominal V, 25C), one for each metric class."""

    k_rd_dyn: float = 1.0
    k_wr_dyn: float = 1.0
    k_dec_dyn: float = 1.0
    k_leak_array: float = 1.0
    k_leak_dec: float = 1.0
    k_t_read: float = 1.0
    k_t_write: float = 1.0
    spread: Tuple[Tuple[str, float], ...] = ()   # for each metric: max/min across the reference shapes
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
_LOG_T_METRICS = ("leak_array", "leak_dec")     # exponential functions of temperature


def _anchor_k(ds: SramDataset, node: str, metric: str,
              dv: float, temp: float) -> Tuple[Optional[float], float]:
    """Return (geometric mean of k, max/min spread) at one measured PVT point.

    The calculation uses the reference shapes that have data at this point.
    """
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
    """Do a piecewise-linear interpolation on the grid of measured voltage offsets."""
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
    """Return the measured PVT domain of a node.

    The domain comes from the reference-shape rows of the decoder sheet.
    Return (dvs_by_temp, all_dvs, t_lo, t_hi). The table k-scaling and the
    MLP source use this function. Thus the two clamp to the same domain for
    each node. Example: 20nm has no +0.15 V rows, thus its limit is +0.10 V.
    """
    dvs_by_temp: Dict[float, set] = {}
    for (n, r, c, adv, at) in ds.pvt_dec:
        if n == node and (r, c) in _REF_SHAPES:
            dvs_by_temp.setdefault(at, set()).add(adv)
    if not dvs_by_temp:
        raise SramDatasetError.nw(8226, node=node)
    all_dvs = sorted(set().union(*dvs_by_temp.values()) | {0.0})
    return dvs_by_temp, all_dvs, 25.0, max(dvs_by_temp)


def clamp_pvt(ds: SramDataset, node: str, dv: float,
              temp: float) -> Tuple[float, float, List[str]]:
    """Clamp (dv, temp) to the measured domain. Return (q_dv, q_temp, warnings)."""
    _, all_dvs, t_lo, t_hi = pvt_domain(ds, node)
    warnings: List[str] = []
    q_dv, q_temp = dv, temp
    if q_dv < all_dvs[0] or q_dv > all_dvs[-1]:
        q_dv = min(max(q_dv, all_dvs[0]), all_dvs[-1])
        warnings.append(warning(8227, value=dv, lo=all_dvs[0],
                                hi=all_dvs[-1], clamped=q_dv))
    if q_temp < t_lo or q_temp > t_hi:
        q_temp = min(max(q_temp, t_lo), t_hi)
        warnings.append(warning(8228, value=temp, lo=t_lo, hi=t_hi,
                                clamped=q_temp))
    return q_dv, q_temp, warnings


def pvt_scale(ds: SramDataset, node: str, dv: float, temp: float) -> PvtScale:
    """Return the k-factors at (dv, temp). All factors are 1 at the nominal point."""
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
                anchors[0.0] = 1.0              # the nominal point
            for adv in sorted(dvs_by_temp.get(at, ())):
                k, spread = _anchor_k(ds, node, metric, adv, at)
                if k is not None:
                    anchors[adv] = k
                    worst_spread = max(worst_spread, spread)
            if not anchors:
                raise SramDatasetError.nw(8229, node=node, metric=metric,
                                          temperature_C=at)
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
            warnings.append(warning(8230, metric=metric, spread=worst_spread))

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
# TilePointSource interface. The table and the MLP models implement it.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TileCosts:
    """The costs of one tile at the PVT of the query.

    The dynamic energies do not include leakage. The leakage is a power.
    """

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
    """The table source: exact grid lookup and separable PVT scaling."""

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
# Selection of the tile source (table or trained MLPs)
# --------------------------------------------------------------------------
# sram_mlp.py uses torch. This module loads it BY FILE PATH and only if it is
# necessary. Thus this module uses only the standard library, runpy can
# execute it, and the estimator stays self-contained in this directory.

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
    """Select the source of the tile costs from cfg.source.

    Return (src, source_used, model_meta, warnings).

    - 'auto' uses the trained MLPs if the checkpoint quartets are present and
      torch imports. If not, it uses the table and gives a warning with the
      cause.
    - 'mlp' raises an error if the MLPs are not available.
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
            raise SramQueryError.nw(8231, reason=reason)
        return (TableTilePointSource(ds), "table", None,
                [warning(8232, reason=reason)])
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
    edge_cols: Optional[int]     # columns of a narrower last horizontal tile (None = all tiles equal)
    n_vert: int                  # vertical tile groups (one access selects one group)
    n_horz: int                  # horizontal tiles, the edge tile included
    banks: int
    ports: int
    tiles_per_bank: int
    total_tiles: int
    logical_bits: int
    physical_bits: int
    utilization: float


@dataclass(frozen=True)
class SramUnitCosts:
    """The unit costs of the full instance, with all banks and all ports."""

    e_read_pJ: float             # one access, plus the idle energy of the other decoders of its bank
    e_write_pJ: float
    e_idle_pJ: float             # for each cycle with no access (0: all banks are clock-gated)
    leak_power_mW: float
    area_um2: float
    t_read_ns: float
    t_write_ns: float
    f_max_MHz: float
    # Breakdown: for one access or one bank-cycle, before the multiplication by the banks.
    rd_array_pJ: float
    wr_array_pJ: float
    dec_access_pJ: float
    idle_overhead_pJ: float      # the (N_dec - fired) * dec_idle term of one access
    bank_idle_pJ: float          # for each cycle, one clocked bank with no access
    leak_array_mW: float
    leak_dec_mW: float
    structure: SramStructure
    pvt: PvtScale
    warnings: Tuple[str, ...] = ()
    source: str = "table"                        # the source of the tile costs
    model_meta: Optional[Dict[str, Any]] = None  # summary of the MLP bundle (mlp source only)
    # Idle accounting.
    # ``e_read_pJ`` above is the cost of ONE access. It is the array and
    # decoder energy of the accessed group, plus the idle energy of the other
    # decoder groups of the same bank. The other banks are clock-gated. Thus
    # N parallel accesses to N banks cost N x e_read_pJ, and a cycle without
    # an access costs leakage only (e_idle_pJ == 0).
    #   e_read_pJ == e_access_read_pJ + (n_dec_groups - 1) * dec_idle_group_pJ
    e_access_read_pJ: float = 0.0    # the accessed group only (array + decoder)
    e_access_write_pJ: float = 0.0
    dec_idle_group_pJ: float = 0.0   # one clocked decoder group that does not fire, for one cycle
    n_dec_groups: int = 0            # clocked decoder groups of the accessed bank


def _horz_tiling(cfg: SramConfig, shapes: Sequence[Tuple[int, int]],
                 r: int, c: int) -> Optional[List[Tuple[int, int]]]:
    """Return the horizontal tiles [(cols, used_bits), ...] for the tile shape (r, c)."""
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
            return None                       # no measured tile can be the edge tile
        tiles.append((edge_opts[0], rem))
    return tiles


def _compose(cfg: SramConfig, src: TableTilePointSource, k: PvtScale,
             r: int, horz: List[Tuple[int, int]]) -> SramUnitCosts:
    """Calculate the costs of one candidate structure. The module docstring gives the model."""
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

    # Decoders in one bank = n_vert * n_horz * P. One access fires the n_horz
    # decoders of the selected group of one port. The other decoders of the
    # bank have a clock and are idle. The other banks are clock-gated. With
    # tile clock gating, the idle decoders of the bank also use no energy.
    if cfg.tile_clock_gating:
        idle_overhead = 0.0
        bank_idle = 0.0
    else:
        idle_overhead = (n_vert * P - 1) * dec_idle_horz
        bank_idle = n_vert * P * dec_idle_horz
    e_idle = 0.0                         # no access: all banks are clock-gated

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
        e_access_read_pJ=rd_array + dec_access,
        e_access_write_pJ=wr_array + dec_access,
        dec_idle_group_pJ=(0.0 if cfg.tile_clock_gating else dec_idle_horz),
        n_dec_groups=n_vert * P,
    )


def _rank_key(cfg: SramConfig, c: SramUnitCosts) -> Tuple:
    # The first key is the number of tiles in a bank (see the module
    # docstring). The objective selects between tilings with the same number
    # of tiles.
    e = round(c.e_read_pJ, 9)
    ar = round(c.area_um2, 6)
    t = round(c.t_read_ns, 6)
    s = c.structure
    n = s.tiles_per_bank
    if cfg.optimize == "area":
        return (n, ar, e, t, s.tile_rows, s.tile_cols)
    if cfg.optimize == "delay":
        return (n, t, e, ar, s.tile_rows, s.tile_cols)
    return (n, e, ar, t, s.tile_rows, s.tile_cols)


def _bank_hierarchy_costs(cfg: SramConfig, ds: SramDataset,
                          extra_warnings: Sequence[str] = ()) -> SramUnitCosts:
    """Calculate the costs of a template instance from ONE measured macro.

    A template instance is a hierarchy::

        instance -> cfg.banks banks -> S macros each -> col-mux tile groups
                    (S = depth_words / template.depth_words, <= 16)

    A "macro" is one instance of the template: a memory compiler macro with a
    decoder, a column mux, and I/O. It is the largest block for which the
    datasets give a cost directly. The recursive call below calculates the
    cost of that macro (banks=1, no template). The levels above the macro are
    arithmetic on the result.

    Access model (clock gating at the bank level):

    * The accessed macro has the cost of a full read or write. This cost
      includes its internal column-mux groups, which is the idle_overhead of
      the recursive call.
    * The other S-1 macros of the SAME bank have a clock but no access. Each
      adds one macro idle energy to the energy of the access.
    * All other banks are clock-gated. They have leakage only. The
      ``leak_power`` term charges it as a function of time, never for each
      access.
    """
    t = SRAM_TEMPLATES[cfg.template]
    s_per_bank = cfg.depth_words // t["depth_words"]
    n_macros = cfg.banks * s_per_bank

    macro = _unit_costs_for_cfg(
        replace(cfg, template=None, depth_words=t["depth_words"], banks=1),
        ds, extra_warnings,
    )
    sibling_idle = (s_per_bank - 1) * macro.bank_idle_pJ

    st = macro.structure
    structure = replace(
        st,
        banks=cfg.banks,
        tiles_per_bank=s_per_bank * st.tiles_per_bank,
        total_tiles=n_macros * st.total_tiles,
        logical_bits=n_macros * st.logical_bits,
        physical_bits=n_macros * st.physical_bits,
    )
    return replace(
        macro,
        e_read_pJ=macro.e_read_pJ + sibling_idle,
        e_write_pJ=macro.e_write_pJ + sibling_idle,
        e_idle_pJ=0.0,                       # no access: all banks are clock-gated
        idle_overhead_pJ=macro.idle_overhead_pJ + sibling_idle,
        bank_idle_pJ=s_per_bank * macro.bank_idle_pJ,
        leak_power_mW=n_macros * macro.leak_power_mW,
        leak_array_mW=n_macros * macro.leak_array_mW,
        leak_dec_mW=n_macros * macro.leak_dec_mW,
        area_um2=n_macros * macro.area_um2,
        structure=structure,
        # Idle terms: the S macros of the accessed bank have a clock.
        e_access_read_pJ=macro.e_access_read_pJ,
        e_access_write_pJ=macro.e_access_write_pJ,
        dec_idle_group_pJ=macro.dec_idle_group_pJ,
        n_dec_groups=s_per_bank * macro.n_dec_groups,
        # The timing is that of one macro. The warning from _apply_template
        # tells the user that bank select and routing are not in the model.
    )


def _unit_costs_for_cfg(cfg: SramConfig, ds: SramDataset,
                        extra_warnings: Sequence[str] = ()) -> SramUnitCosts:
    if cfg.template:
        return _bank_hierarchy_costs(cfg, ds, extra_warnings)
    shapes = ds.shapes_by_node[cfg.node]
    # Always calculate k (the separable table scaling). The MLP source does
    # not use its factors, but the report shows k as a diagnostic. k also
    # gives the warnings about the domain clamp and the reference-shape
    # spread for the two sources.
    k = pvt_scale(ds, cfg.node, cfg.voltage_offset_v, cfg.temperature_c)
    src, source_used, model_meta, src_warns = _resolve_source(cfg, ds)

    cands = [(r, c) for (r, c) in shapes
             if (cfg.tile_rows is None or r == cfg.tile_rows)
             and (cfg.tile_cols is None or c == cfg.tile_cols)]
    if not cands:
        avail = ", ".join(f"{r}x{c}" for r, c in shapes)
        raise SramQueryError.nw(8233, tile_rows=cfg.tile_rows,
                                tile_cols=cfg.tile_cols, node=cfg.node,
                                available=avail)

    best: Optional[SramUnitCosts] = None
    best_key: Optional[Tuple] = None
    seen: set = set()
    for (r, c) in cands:
        horz = _horz_tiling(cfg, shapes, r, c)
        if not horz:
            continue
        sig = (r, tuple(horz))
        if sig in seen:                      # wide candidates can give the same tiles
            continue
        seen.add(sig)
        costs = _compose(cfg, src, k, r, horz)
        key = _rank_key(cfg, costs)
        if best_key is None or key < best_key:
            best, best_key = costs, key
    if best is None:
        raise SramQueryError.nw(8234, config=cfg)

    warnings = list(extra_warnings) + list(k.warnings) + list(src_warns)
    s = best.structure
    if s.utilization < _UTIL_WARN:
        warnings.append(warning(8235, utilization=s.utilization,
                                logical_bits=s.logical_bits,
                                physical_bits=s.physical_bits))
    if s.tiles_per_bank > _TILE_GLUE_WARN:
        warnings.append(warning(8236, tiles=s.tiles_per_bank))
    if cfg.clock_mhz and cfg.clock_mhz > best.f_max_MHz:
        warnings.append(warning(8237, clock_mhz=cfg.clock_mhz,
                                f_max_MHz=best.f_max_MHz,
                                t_read_ns=best.t_read_ns,
                                t_write_ns=best.t_write_ns))
    return replace(best, warnings=tuple(warnings), source=source_used,
                   model_meta=model_meta)


def unit_costs(features: Mapping[str, Any]) -> SramUnitCosts:
    """Return the unit costs of the full instance for a features dict."""
    ds = load_dataset(_resolve_dataset_dir(features))
    cfg, warns = normalize_config(features, ds)
    return _unit_costs_for_cfg(cfg, ds, warns)


def energy_for_stim_mode(costs: SramUnitCosts, stim_mode: str) -> float:
    """Return the dynamic energy [pJ] of the full instance for one cycle or event of a stim_mode."""
    if stim_mode == "read":
        return costs.e_read_pJ
    if stim_mode == "write":
        return costs.e_write_pJ
    if stim_mode == "idle":
        return costs.e_idle_pJ
    if stim_mode == "random":
        return 0.5 * (costs.e_read_pJ + costs.e_write_pJ)
    raise SramQueryError.nw(8238, mode=stim_mode, modes=_STIM_MODES)


# --------------------------------------------------------------------------
# EstimatorHost entrypoints. The host contract: return None if there is an error.
# --------------------------------------------------------------------------

def _host_error(exc: Exception) -> None:
    """Print the error of an entrypoint. The host contract: do not raise."""
    if isinstance(exc, NPUWattchError) and exc.code is not None:
        emit(exc)
    else:
        error(8240, error=exc).emit()


def _entry(features: Optional[Mapping[str, Any]]):
    if not isinstance(features, Mapping):
        raise SramQueryError.nw(8239)
    return unit_costs(features)


def get_energy(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Return the dynamic energy [pJ] for features['stim_mode'|'op'] (default: read)."""
    try:
        costs = _entry(features)
        mode = (features.get("stim_mode") or features.get("op") or "read")
        return energy_for_stim_mode(costs, str(mode))
    except Exception as e:  # host contract: do not raise
        _host_error(e)
        return None


def get_area(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Return the total macro area [um2] (all banks, arrays + decoders)."""
    try:
        return _entry(features).area_um2
    except Exception as e:
        _host_error(e)
        return None


def get_timing(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Return the read access time [ns] (decoder wlen->WL + array WL->OUT)."""
    try:
        return _entry(features).t_read_ns
    except Exception as e:
        _host_error(e)
        return None


def get_leakage(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[float]:
    """Return the static leakage power [mW] (all banks, arrays + decoders)."""
    try:
        return _entry(features).leak_power_mW
    except Exception as e:
        _host_error(e)
        return None


def get_unit_costs(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[dict]:
    """Return the full SramUnitCosts as a plain dict."""
    try:
        return asdict(_entry(features))
    except Exception as e:
        _host_error(e)
        return None


def get_report(features: Optional[Mapping[str, Any]] = None, **kwargs: Any) -> Optional[dict]:
    """Return the unit costs, the structure, the provenance, and the warnings.

    The provenance identifies the raw dataset rows that the result uses.
    """
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
        _host_error(e)
        return None


# --------------------------------------------------------------------------
# UnitCostProvider factory (the provider has the structure of the Protocol in npuwattch.energy)
# --------------------------------------------------------------------------

class _SramUnitCostProvider:
    """A provider that answers queries for the primitive 'sram'.

    It sends queries for all other primitives to a fallback provider. It has
    the structure of the ``UnitCostProvider`` protocol: the calibrated flag
    and four methods. From npuwattch, it imports only the message catalog,
    thus runpy can execute this file. It caches the costs for each normalized query (SramConfig is
    frozen and hashable).
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
            raise EstimatorQueryError.nw(8001, provider="sram",
                                         primitive=primitive)
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

    def idle_terms(self, primitive: str,
                   features: Mapping[str, Any]) -> Optional[Tuple[float, float]]:
        """Return ``(e_idle_per_cycle_pJ, idle_displaced_per_access_pJ)``.

        The energy aggregation uses these values for the idle accounting of
        each cycle. Return None if the primitive has no clocked idle term:
        the tiles are clock-gated, or the primitive is not an sram.
        """
        if primitive != "sram":
            fb = getattr(self._fallback, "idle_terms", None)
            return fb(primitive, features) if fb is not None else None
        c = self._costs(features)
        if c.e_idle_pJ <= 0.0 or c.n_dec_groups <= 0:
            return None
        return (c.e_idle_pJ, c.dec_idle_group_pJ)

    def envelope_warnings(self, primitive: str,
                          features: Mapping[str, Any]) -> List[str]:
        """Return the envelope warnings (an optional method of the protocol).

        For primitives other than 'sram', the fallback provider gives them.
        The logic estimator does its range checks in this method.
        """
        if primitive == "sram":
            return []
        fb = getattr(self._fallback, "envelope_warnings", None)
        return list(fb(primitive, features)) if fb is not None else []


def make_unit_cost_provider(defaults: Optional[Mapping[str, Any]] = None,
                            dataset_dir: Optional[str] = None,
                            fallback: Any = None) -> _SramUnitCostProvider:
    """Make a UnitCostProvider for the primitive 'sram'.

    - ``defaults`` are default features (for example, the activity policy).
      The features of each call have priority over them.
    - ``fallback`` is a UnitCostProvider that answers queries for other
      primitives. Without a fallback, such a query raises an error.
    - ``calibrated`` is True if there is no fallback. If there is a fallback,
      ``calibrated`` has the value of the fallback.
    """
    return _SramUnitCostProvider(defaults=defaults, dataset_dir=dataset_dir,
                                 fallback=fallback)
