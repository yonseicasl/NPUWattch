#!/usr/bin/env python3
"""Train the four SRAM MLPs (energy / leakage / timing / area) — manual §5.

Standalone-plugin rule: everything lives in src/estimators/sram/.  This script
loads its siblings ``sram.py`` (dataset loader = single source of the
leak-subtraction) and ``sram_mlp.py`` (feature vocabulary, net, quartet IO) by
file path, trains per manual §5.4 (Adam 1e-3 + plateau decay, batch 256 capped
at n/8, early stop on val MAPE patience 30, seed 42, CPU), with the §5.3
histogram-weighted L1 adapted to one axis (the log10 target) — weights are
ACTUALLY applied.  Targets are ABSOLUTE log10 values in the estimator's
internal space (leak-subtracted dynamic pJ / mW / ns / um2).

Outputs (to --out-dir, default = this directory):
  <metric>__v1.{pt,scalers.json,loss.json,meta.json}   x4   (§3.5 quartets)
  eval_report.json                                          (metrics + audits)

Usage:
  python train_sram.py [--models energy,leakage,timing,area] [--epochs 1500]
                       [--dataset-dir DIR] [--out-dir DIR] [--seed 42]
                       [--skip-audits]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import torch

_HERE = Path(__file__).resolve().parent


def _load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(f"_sram_sib_{name}",
                                                  _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


sram = _load_sibling("sram")
smlp = _load_sibling("sram_mlp")

ENERGY_ARRAY_ATTRS = {"rd_1to1": "rd_1to1_dyn_pJ", "rd_1to0": "rd_1to0_dyn_pJ",
                      "wr_same": "wr_same_dyn_pJ", "wr_toggle": "wr_toggle_dyn_pJ"}
ENERGY_DEC_ATTRS = {"dec_act": "act_dyn_pJ", "dec_flip": "flip_dyn_pJ",
                    "dec_idle": "idle_dyn_pJ"}


# ---------------------------------------------------------------------------
# sample assembly
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sample:
    node: str
    rows: int
    cols: int
    dv: float
    temp: float
    op: str
    y_log10: float
    x: Tuple[float, ...]

    @property
    def group(self) -> Tuple:
        return (self.node, self.rows, self.cols, self.dv, self.temp)


def _iter_points(nominal: Dict, pvt: Dict):
    for (node, r, c), pt in nominal.items():
        yield node, r, c, 0.0, 25.0, pt
    for (node, r, c, dv, t), pt in pvt.items():
        yield node, r, c, dv, t, pt


def _mk(model: str, node: str, r: int, c: int, dv: float, t: float,
        op: str, value: float, dropped: List[Dict]) -> Optional[Sample]:
    if not (value and value > 0.0 and math.isfinite(value)):
        dropped.append({"model": model, "node": node, "shape": f"{r}x{c}",
                        "dv": dv, "temp": t, "op": op, "value": value})
        return None
    nm = smlp.node_nm(node)
    return Sample(node, r, c, dv, t, op, math.log10(value),
                  tuple(smlp.feature_vector(model, nm, r, c, dv, t, op)))


def assemble(ds) -> Tuple[Dict[str, List[Sample]], List[Dict]]:
    samples: Dict[str, List[Sample]] = {m: [] for m in smlp.MODEL_NAMES}
    dropped: List[Dict] = []

    for node, r, c, dv, t, pt in _iter_points(ds.nominal_array, ds.pvt_array):
        for op, attr in ENERGY_ARRAY_ATTRS.items():
            s = _mk("energy", node, r, c, dv, t, op, getattr(pt, attr), dropped)
            if s:
                samples["energy"].append(s)
        s = _mk("leakage", node, r, c, dv, t, "array", pt.leak_power_mW, dropped)
        if s:
            samples["leakage"].append(s)

    for node, r, c, dv, t, pt in _iter_points(ds.nominal_dec, ds.pvt_dec):
        for op, attr in ENERGY_DEC_ATTRS.items():
            s = _mk("energy", node, r, c, dv, t, op, getattr(pt, attr), dropped)
            if s:
                samples["energy"].append(s)
        s = _mk("leakage", node, r, c, dv, t, "dec", pt.leak_power_mW, dropped)
        if s:
            samples["leakage"].append(s)

    # timing: composed access times (needs BOTH sheets at the same point;
    # unpaired points are dropped and logged)
    a_map = {(n, r, c, 0.0, 25.0): p for (n, r, c), p in ds.nominal_array.items()}
    a_map.update(ds.pvt_array)
    d_map = {(n, r, c, 0.0, 25.0): p for (n, r, c), p in ds.nominal_dec.items()}
    d_map.update(ds.pvt_dec)
    for key in sorted(a_map.keys() ^ d_map.keys()):
        dropped.append({"model": "timing", "node": key[0],
                        "shape": f"{key[1]}x{key[2]}", "dv": key[3],
                        "temp": key[4], "op": "unpaired", "value": None})
    for key in sorted(a_map.keys() & d_map.keys()):
        node, r, c, dv, t = key
        a, d = a_map[key], d_map[key]
        t_read, t_write = smlp.compose_timing(d.wlen_wl_ns, a.rd_delay_ns,
                                              a.wr_bl_ns, a.wr_cell_ns)
        for op, val in (("t_read", t_read), ("t_write", t_write)):
            s = _mk("timing", node, r, c, dv, t, op, val, dropped)
            if s:
                samples["timing"].append(s)

    # area: PVT-independent -> nominal rows only (dedup by construction)
    for (node, r, c), pt in ds.nominal_array.items():
        s = _mk("area", node, r, c, 0.0, 25.0, "array", pt.array_area_um2, dropped)
        if s:
            samples["area"].append(s)
    for (node, r, c), pt in ds.nominal_dec.items():
        s = _mk("area", node, r, c, 0.0, 25.0, "dec", pt.dec_area_um2, dropped)
        if s:
            samples["area"].append(s)

    return samples, dropped


def split_by_group(items: Sequence[Sample], seed: int,
                   fracs=(0.8, 0.1, 0.1)) -> Tuple[List[Sample], ...]:
    """80/10/10 by design point — all op-rows of one simulation stay together."""
    groups = sorted({s.group for s in items})
    rng = random.Random(seed)
    rng.shuffle(groups)
    n = len(groups)
    n_tr = int(round(fracs[0] * n))
    n_va = int(round(fracs[1] * n))
    buckets = {}
    for i, g in enumerate(groups):
        buckets[g] = 0 if i < n_tr else (1 if i < n_tr + n_va else 2)
    out: Tuple[List[Sample], ...] = ([], [], [])
    for s in items:
        out[buckets[s.group]].append(s)
    return out


# ---------------------------------------------------------------------------
# §5.3 loss (one axis = the log10 target), weights applied
# ---------------------------------------------------------------------------

def fit_loss_weights(y_train: Sequence[float], bins: int = 30,
                     mu: float = 1.0, eps: float = 1e-6) -> Dict[str, Any]:
    y = torch.tensor(list(y_train), dtype=torch.float32)
    hist, edges = torch.histogram(y, bins=bins)
    pmf = hist / hist.sum()
    # Empty bins get weight 0 (no sample ever falls there) — including their
    # 1/eps in the normalization would crush every occupied bin's weight to
    # ~0 and starve the bulk of the data of gradient. Normalize to unit mean
    # over SAMPLES (sum pmf*w == 1), which is the usable reading of §5.3's
    # unit-mean rule for a sparse 1-D axis.
    w = torch.where(hist > 0, 1.0 / (pmf + eps), torch.zeros_like(pmf))
    w = w / float((pmf * w).sum())
    return {"axes": [{"name": "target_log10",
                      "edges": edges.tolist(), "weights": w.tolist()}],
            "mu": mu, "eps": eps,
            "normalization": "unit mean over samples; empty bins weight 0"}


def loss_weight_for(spec: Dict[str, Any], y_log10: float) -> float:
    ax = spec["axes"][0]
    edges = ax["edges"]
    idx = 0
    for i in range(1, len(edges) - 1):
        if y_log10 >= edges[i]:
            idx = i
        else:
            break
    return spec["mu"] * ax["weights"][idx]


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _ranks(v: Sequence[float]) -> List[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    ranks = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            ranks[order[t]] = avg
        i = j + 1
    return ranks


def _pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    return _pearson(_ranks(x), _ranks(y))


def mape(truth: Sequence[float], pred: Sequence[float]) -> float:
    return sum(abs(p - t) / t for t, p in zip(truth, pred)) / len(truth)


# ---------------------------------------------------------------------------
# training
# ---------------------------------------------------------------------------

@dataclass
class TrainResult:
    net: Any
    scalers: Dict[str, Any]
    loss_spec: Dict[str, Any]
    val_mape: float
    epochs_run: int
    n_train: int
    n_val: int


def _standardize_fit(xs: List[Tuple[float, ...]], mask: List[bool]):
    cols = list(zip(*xs))
    mean, std = [], []
    for j, col in enumerate(cols):
        if mask[j]:
            m = sum(col) / len(col)
            v = sum((a - m) ** 2 for a in col) / len(col)
            mean.append(m)
            std.append(max(math.sqrt(v), 1e-9))
        else:
            mean.append(0.0)
            std.append(1.0)
    return mean, std


def _tensorize(samples: Sequence[Sample], scalers: Dict[str, Any],
               loss_spec: Optional[Dict[str, Any]] = None):
    xm = torch.tensor(scalers["x_mean"], dtype=torch.float32)
    xs = torch.tensor(scalers["x_std"], dtype=torch.float32)
    mk = torch.tensor(scalers["x_scale_mask"], dtype=torch.bool)
    x = torch.tensor([s.x for s in samples], dtype=torch.float32)
    x = torch.where(mk, (x - xm) / xs, x)
    y = torch.tensor([(s.y_log10 - scalers["y_mean"]) / scalers["y_std"]
                      for s in samples], dtype=torch.float32)
    w = None
    if loss_spec is not None:
        w = torch.tensor([loss_weight_for(loss_spec, s.y_log10)
                          for s in samples], dtype=torch.float32)
    return x, y, w


def _val_mape(net, x, y, scalers) -> float:
    with torch.no_grad():
        p_log = net(x) * scalers["y_std"] + scalers["y_mean"]
        t_log = y * scalers["y_std"] + scalers["y_mean"]
        p = torch.pow(10.0, p_log)
        t = torch.pow(10.0, t_log)
        return float((torch.abs(p - t) / t).mean())


def train_model(model: str, train_s: List[Sample], val_s: List[Sample],
                arch: List[int], epochs: int, seed: int,
                lr: float = 1e-3, patience: int = 150) -> TrainResult:
    torch.manual_seed(seed)
    mask = smlp.scale_mask(model)
    x_mean, x_std = _standardize_fit([s.x for s in train_s], mask)
    ys = [s.y_log10 for s in train_s]
    y_mean = sum(ys) / len(ys)
    y_std = max(math.sqrt(sum((a - y_mean) ** 2 for a in ys) / len(ys)), 1e-9)
    scalers = {"x_mean": x_mean, "x_std": x_std, "x_scale_mask": mask,
               "y_mean": y_mean, "y_std": y_std, "target_log10": True,
               "features": smlp.base_feature_names(model) + list(smlp.ONE_HOTS[model])}
    loss_spec = fit_loss_weights(ys)

    xt, yt, wt = _tensorize(train_s, scalers, loss_spec)
    xv, yv, _ = _tensorize(val_s, scalers)

    net = smlp.SramMlp(smlp.n_inputs(model), arch)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min",
                                                       factor=0.5, patience=50,
                                                       min_lr=1e-5)
    bs = min(256, max(1, math.ceil(len(train_s) / 8)))
    gen = torch.Generator().manual_seed(seed)

    best = math.inf
    best_state = {k: v.clone() for k, v in net.state_dict().items()}
    since_best = 0
    epoch = 0
    for epoch in range(1, epochs + 1):
        net.train()
        for idx in torch.randperm(len(train_s), generator=gen).split(bs):
            opt.zero_grad()
            pred = net(xt[idx])
            loss = (wt[idx] * torch.abs(pred - yt[idx])).mean()
            loss.backward()
            opt.step()
        net.eval()
        vm = _val_mape(net, xv, yv, scalers)
        sched.step(vm)
        if vm < best - 1e-5:
            best = vm
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
            since_best = 0
        else:
            since_best += 1
            if since_best >= patience:
                break
    net.load_state_dict(best_state)
    net.eval()
    return TrainResult(net=net, scalers=scalers, loss_spec=loss_spec,
                       val_mape=best, epochs_run=epoch,
                       n_train=len(train_s), n_val=len(val_s))


def _predict_linear(net, scalers, samples: Sequence[Sample]) -> List[float]:
    x, _, _ = _tensorize(samples, scalers)
    with torch.no_grad():
        y_log = net(x) * scalers["y_std"] + scalers["y_mean"]
    return [10.0 ** v for v in y_log.tolist()]


def eval_per_op(net, scalers, samples: Sequence[Sample]) -> Dict[str, Any]:
    preds = _predict_linear(net, scalers, samples)
    truths = [10.0 ** s.y_log10 for s in samples]
    per_op: Dict[str, Any] = {}
    ops = sorted({s.op for s in samples})
    for op in ops:
        t = [tr for s, tr in zip(samples, truths) if s.op == op]
        p = [pr for s, pr in zip(samples, preds) if s.op == op]
        per_op[op] = {"mape": mape(t, p), "n": len(t)}
    return {"mape": mape(truths, preds),
            "spearman": spearman(truths, preds),
            "per_op": per_op,
            "_preds": preds, "_truths": truths}


# ---------------------------------------------------------------------------
# audits + table baseline
# ---------------------------------------------------------------------------

AUDITS: List[Tuple[str, Callable[[Sample], bool]]] = [
    ("leave_node_5nm", lambda s: s.node == "5nm"),
    ("leave_node_7nm", lambda s: s.node == "7nm"),
    ("leave_node_10nm", lambda s: s.node == "10nm"),
    ("leave_node_16nm", lambda s: s.node == "16nm"),
    ("leave_node_20nm", lambda s: s.node == "20nm"),
    ("leave_shape_8x64_256x4", lambda s: (s.rows, s.cols) in ((8, 64), (256, 4))),
    ("leave_corner_55C", lambda s: s.temp == 55.0),
    ("leave_corner_pm015V", lambda s: abs(s.dv) == 0.15),
]


def run_audits(model: str, samples: List[Sample], arch: List[int],
               epochs: int, seed: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, held in AUDITS:
        if model == "area" and name.startswith("leave_corner"):
            continue                       # area has no PVT axis
        holdout = [s for s in samples if held(s)]
        rest = [s for s in samples if not held(s)]
        if len(holdout) < 8 or len(rest) < 50:
            out[name] = {"skipped": f"holdout={len(holdout)} rest={len(rest)}"}
            continue
        tr, va, _ = split_by_group(rest, seed, fracs=(0.9, 0.1, 0.0))
        res = train_model(model, tr, va, arch, epochs, seed)
        ev = eval_per_op(res.net, res.scalers, holdout)
        out[name] = {"mape": ev["mape"],
                     "per_op": {k: v["mape"] for k, v in ev["per_op"].items()},
                     "n_holdout": len(holdout)}
    return out


_K_CLASS = {"rd_1to1": "k_rd_dyn", "rd_1to0": "k_rd_dyn",
            "wr_same": "k_wr_dyn", "wr_toggle": "k_wr_dyn",
            "dec_act": "k_dec_dyn", "dec_flip": "k_dec_dyn",
            "dec_idle": "k_dec_dyn",
            "array": "k_leak_array", "dec": "k_leak_dec"}
_NOM_ATTR = {**{op: ("array", attr) for op, attr in ENERGY_ARRAY_ATTRS.items()},
             **{op: ("dec", attr) for op, attr in ENERGY_DEC_ATTRS.items()},
             "array": ("array", "leak_power_mW"), "dec": ("dec", "leak_power_mW")}


def table_baseline(ds, results: Dict[str, TrainResult],
                   test_sets: Dict[str, List[Sample]]) -> Dict[str, Any]:
    """MLP vs separable-k table on held-out PVT rows (energy/leakage per-op,
    timing at the composed level)."""
    out: Dict[str, Any] = {}
    kcache: Dict[Tuple, Any] = {}

    def k_for(node, dv, temp):
        key = (node, dv, temp)
        if key not in kcache:
            kcache[key] = sram.pvt_scale(ds, node, dv, temp)
        return kcache[key]

    for model in ("energy", "leakage"):
        rows: Dict[str, Dict[str, List[float]]] = {}
        skipped = 0
        pvt_samples = [s for s in test_sets[model]
                       if not (s.dv == 0.0 and s.temp == 25.0)]
        preds = _predict_linear(results[model].net, results[model].scalers,
                                pvt_samples)
        for s, p_mlp in zip(pvt_samples, preds):
            sheet, attr = _NOM_ATTR[s.op]
            nom_map = ds.nominal_array if sheet == "array" else ds.nominal_dec
            nom = nom_map.get((s.node, s.rows, s.cols))
            if nom is None:
                skipped += 1
                continue
            k = getattr(k_for(s.node, s.dv, s.temp), _K_CLASS[s.op])
            truth = 10.0 ** s.y_log10
            d = rows.setdefault(s.op, {"t": [], "mlp": [], "tab": []})
            d["t"].append(truth)
            d["mlp"].append(p_mlp)
            d["tab"].append(getattr(nom, attr) * k)
        out[model] = {op: {"mlp_mape": mape(d["t"], d["mlp"]),
                           "table_mape": mape(d["t"], d["tab"]),
                           "n": len(d["t"])}
                      for op, d in sorted(rows.items())}
        out[model]["_skipped_no_nominal"] = skipped

    # timing: composed t_read / t_write per held-out (node, shape, corner)
    groups = {s.group for s in test_sets["timing"]
              if not (s.dv == 0.0 and s.temp == 25.0)}
    comp = {"t_read": {"t": [], "mlp": [], "tab": []},
            "t_write": {"t": [], "mlp": [], "tab": []}}
    res = results["timing"]
    for (node, r, c, dv, t) in sorted(groups):
        a = ds.pvt_array.get((node, r, c, dv, t))
        d = ds.pvt_dec.get((node, r, c, dv, t))
        an = ds.nominal_array.get((node, r, c))
        dn = ds.nominal_dec.get((node, r, c))
        if not (a and d and an and dn):
            continue
        truth = smlp.compose_timing(d.wlen_wl_ns, a.rd_delay_ns,
                                    a.wr_bl_ns, a.wr_cell_ns)
        k = k_for(node, dv, t)
        nom = smlp.compose_timing(dn.wlen_wl_ns, an.rd_delay_ns,
                                  an.wr_bl_ns, an.wr_cell_ns)
        tab = (nom[0] * k.k_t_read, nom[1] * k.k_t_write)
        nm = smlp.node_nm(node)
        tgt_s = [Sample(node, r, c, dv, t, op, 0.0,
                        tuple(smlp.feature_vector("timing", nm, r, c, dv, t, op)))
                 for op in smlp.TIMING_TARGETS]
        pv = dict(zip(smlp.TIMING_TARGETS,
                      _predict_linear(res.net, res.scalers, tgt_s)))
        mlp = (pv["t_read"], pv["t_write"])
        for i, key in enumerate(("t_read", "t_write")):
            comp[key]["t"].append(truth[i])
            comp[key]["mlp"].append(mlp[i])
            comp[key]["tab"].append(tab[i])
    out["timing_composed"] = {
        key: ({"mlp_mape": mape(d["t"], d["mlp"]),
               "table_mape": mape(d["t"], d["tab"]), "n": len(d["t"])}
              if d["t"] else {"n": 0})
        for key, d in comp.items()}
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", default=",".join(smlp.MODEL_NAMES))
    ap.add_argument("--dataset-dir", default=None)
    ap.add_argument("--out-dir", default=str(_HERE))
    ap.add_argument("--epochs", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=300)
    ap.add_argument("--skip-audits", action="store_true")
    args = ap.parse_args(argv)

    # Tiny nets: more threads oversubscribe the matmuls and hurt both speed
    # and run-to-run reproducibility. 4 is plenty.
    torch.set_num_threads(4)
    ddir = Path(args.dataset_dir) if args.dataset_dir else sram._resolve_dataset_dir()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for m in models:
        if m not in smlp.MODEL_NAMES:
            ap.error(f"unknown model '{m}' (choose from {smlp.MODEL_NAMES})")

    ds = sram.load_dataset(ddir)
    ds_hash = smlp.dataset_hash(ddir)
    samples, dropped = assemble(ds)
    print(f"dataset {ddir} sha256={ds_hash[:12]}…  samples: "
          + ", ".join(f"{m}={len(samples[m])}" for m in smlp.MODEL_NAMES)
          + f", dropped={len(dropped)}")

    report: Dict[str, Any] = {
        "dataset": {"dir": str(ddir), "sha256": ds_hash,
                    "dropped_rows": dropped},
        "seed": args.seed, "epochs_max": args.epochs,
        "date": datetime.now().isoformat(timespec="seconds"),
        "torch": torch.__version__,
        "models": {}, "audits": {}, "gates": {},
    }
    results: Dict[str, TrainResult] = {}
    test_sets: Dict[str, List[Sample]] = {}

    for model in models:
        t0 = time.time()
        arch = smlp.DEFAULT_ARCH[model]
        tr, va, te = split_by_group(samples[model], args.seed)
        res = train_model(model, tr, va, arch, args.epochs, args.seed,
                          lr=args.lr, patience=args.patience)
        ev = eval_per_op(res.net, res.scalers, te)
        results[model] = res
        test_sets[model] = te

        # per-op mean loss weight (histogram-skew check)
        op_w: Dict[str, float] = {}
        for op in smlp.ONE_HOTS[model]:
            ws = [loss_weight_for(res.loss_spec, s.y_log10)
                  for s in tr if s.op == op]
            if ws:
                op_w[op] = sum(ws) / len(ws)

        worst = sorted(
            ({"node": s.node, "shape": f"{s.rows}x{s.cols}", "dv": s.dv,
              "temp": s.temp, "op": s.op, "truth": t, "pred": p,
              "rel_err": abs(p - t) / t}
             for s, t, p in zip(te, ev["_truths"], ev["_preds"])),
            key=lambda d: -d["rel_err"])[:10]

        meta = {
            "model": model, "version": smlp.VERSION, "arch": arch,
            "n_in": smlp.n_inputs(model),
            "features": res.scalers["features"],
            "one_hot": list(smlp.ONE_HOTS[model]),
            "target": f"log10_{smlp.TARGET_UNITS[model]}",
            "dataset_sha256": ds_hash, "seed": args.seed,
            "split": {"train": len(tr), "val": len(va), "test": len(te)},
            "epochs_run": res.epochs_run,
            "val_mape": res.val_mape, "test_mape": ev["mape"],
            "test_spearman": ev["spearman"],
            "per_op_test_mape": {k: v["mape"] for k, v in ev["per_op"].items()},
            "date": datetime.now().isoformat(timespec="seconds"),
            "torch": torch.__version__,
        }
        smlp.save_quartet(out_dir, model, res.net, res.scalers,
                          res.loss_spec, meta)

        over5 = [op for op, v in ev["per_op"].items() if v["mape"] > 0.05]
        over10 = [op for op, v in ev["per_op"].items() if v["mape"] > 0.10]
        report["models"][model] = {
            "arch": arch, "split": meta["split"],
            "epochs_run": res.epochs_run, "val_mape": res.val_mape,
            "test_mape": ev["mape"], "test_spearman": ev["spearman"],
            "per_op_test_mape": meta["per_op_test_mape"],
            "per_op_mean_loss_weight": op_w,
            "worst10_test": worst,
            "min_target": min(10.0 ** s.y_log10 for s in samples[model]),
            "train_seconds": round(time.time() - t0, 1),
        }
        report["gates"][model] = {"pass_10pct": not over10,
                                  "ops_over_5pct": over5,
                                  "ops_over_10pct": over10}
        print(f"[{model}] arch={arch} test MAPE={ev['mape']:.3%} "
              f"ρ={ev['spearman']:.3f} epochs={res.epochs_run} "
              f"({time.time() - t0:.0f}s)  over5%={over5 or '-'}")

        if not args.skip_audits:
            report["audits"][model] = run_audits(model, samples[model], arch,
                                                 args.epochs, args.seed)

    if set(models) >= {"energy", "leakage", "timing"}:
        report["baseline_vs_table"] = table_baseline(ds, results, test_sets)

    (out_dir / "eval_report.json").write_text(json.dumps(report, indent=1))
    print(f"wrote {out_dir / 'eval_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
