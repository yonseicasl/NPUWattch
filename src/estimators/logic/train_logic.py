#!/usr/bin/env python3
"""Train the logic-primitive MLPs (component × metric) — manual §5.

Deliberately the same recipe and code shape as ``sram/train_sram.py`` (user
decision 2026-07-28): Adam 1e-3 + plateau decay, batch 256 capped at n/8,
early stop on val MAPE, seed 42, CPU, absolute log10 targets, quartet
checkpoints.  Differences:

- one model per (component, metric): 7 components × {energy, leakage,
  timing, area};
- the §5.3 adaptive loss uses its ORIGINAL two axes (SCR, SAR) — the SRAM
  trainer's target-axis form was the SPICE adaptation.  Same empty-bin rule:
  empty bins weight 0, normalized to unit mean over the training samples;
- power metrics carry a ``stim_mode`` one-hot including ``none`` (the
  unvectored row; 2026-07-28 decision).  ``--ab-none`` (default on) retrains
  each energy model WITHOUT the none rows and evaluates both on the same
  non-none test rows — the evidence for dropping ``none`` later, if it ever
  clearly hurts;
- timing/area rows are per DESIGN (deduped across modes; the sweep implements
  each design once).

Outputs (to --out-dir, default = this directory):
  <component>_<metric>__<VERSION>.{pt,scalers.json,loss.json,meta.json}
  eval_report.json

``VERSION`` is ``logic_mlp.VERSION`` (currently ``v2``) — the same constant the
inference side loads by, so a bump swaps the whole served set at once. Bump it
whenever the *characterized object* changes (a library fix, re-pipelined RTL, a
new feature axis), not for a routine retrain on the same data.

Usage:
  python train_logic.py [--components fpmac,intmac,...] [--metrics energy,...]
                        [--epochs 6000] [--patience 300] [--seed 42]
                        [--dataset-dir DIR] [--out-dir DIR]
                        [--audits] [--skip-ab]
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch

_HERE = Path(__file__).resolve().parent


def _load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(f"_logic_sib_{name}",
                                                  _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


lmlp = _load_sibling("logic_mlp")


def _resolve_dataset_dir() -> Path:
    return _HERE.parents[2] / "dataset_gen" / "logic" / "datasets"


# ---------------------------------------------------------------------------
# sample assembly
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sample:
    component: str
    node: str
    clock_ns: float
    params: str                      # arch_params string (design identity)
    mode: str                        # stim_mode; "" for timing/area
    scr: float
    sar: float
    y_log10: float
    x: Tuple[float, ...]

    @property
    def group(self) -> Tuple:
        return (self.params, self.node, self.clock_ns)


def _mk(component: str, metric: str, row: Dict[str, str],
        dropped: List[Dict]) -> Optional[Sample]:
    try:
        value = float(row[lmlp.TARGET_COLUMNS[metric]])
    except (KeyError, ValueError):
        value = float("nan")
    node = row["node"]
    clock_ns = float(row["clock_period_ns"])
    mode = row.get("stim_mode", "") if metric in lmlp.MODE_METRICS else ""
    if not (value > 0.0 and math.isfinite(value)):
        dropped.append({"component": component, "metric": metric,
                        "params": row.get("arch_params"), "node": node,
                        "clock_ns": clock_ns, "mode": mode, "value": value})
        return None
    # empty numeric param = 1 (pre-07-21 mxfpmac rows lack pipeline_stages:
    # that template is combinational = 1 stage)
    params = {c: float(row[c]) if row.get(c, "") not in ("", None) else 1.0
              for c in lmlp.PARAM_COLUMNS[component]}
    params.update({c: float(row.get(c, 0) or 0)
                   for c in lmlp.FLAG_COLUMNS.get(component, ())})
    params.update({col: row[col]
                   for col, _ in lmlp.CATEGORICAL_COLUMNS.get(component, ())})
    x = lmlp.feature_vector(component, metric, lmlp.node_nm(node), clock_ns,
                            params, mode or None)
    return Sample(component=component, node=node, clock_ns=clock_ns,
                  params=row["arch_params"], mode=mode,
                  scr=float(row["syn_scr"]), sar=float(row["syn_sar"]),
                  y_log10=math.log10(value), x=tuple(x))


def assemble(component: str, rows: List[Dict[str, str]]
             ) -> Tuple[Dict[str, List[Sample]], List[Dict]]:
    samples: Dict[str, List[Sample]] = {m: [] for m in lmlp.METRICS}
    dropped: List[Dict] = []
    for metric in lmlp.MODE_METRICS:                    # one row per mode
        for row in rows:
            if row.get("stim_mode") not in lmlp.STIM_MODES[component]:
                dropped.append({"component": component, "metric": metric,
                                "params": row.get("arch_params"),
                                "mode": row.get("stim_mode"),
                                "value": "unknown stim_mode"})
                continue
            s = _mk(component, metric, row, dropped)
            if s:
                samples[metric].append(s)
    seen: set = set()
    for row in rows:                                    # one row per design
        key = (row["arch_params"], row["node"], row["clock_period_ns"])
        if key in seen:
            continue
        seen.add(key)
        for metric in ("timing", "area"):
            s = _mk(component, metric, row, dropped)
            if s:
                samples[metric].append(s)
    return samples, dropped


def leak_quarantine_keys(rows: List[Dict[str, str]], dex: float
                         ) -> Tuple[set, Dict[str, Any]]:
    """Row keys whose leakage is contaminated (see --leakage-outlier-dex).

    Per node, the clean anchor is the 10th percentile of log10(leak/cell) —
    robust even where contamination is the majority (16nm: ~70% of rows),
    because the clean floor is device physics and node-flat (~-6.3).
    """
    per_node: Dict[str, List[float]] = {}
    vals: List[Tuple[Tuple, str, float]] = []
    for r in rows:
        try:
            leak = float(r["leak_power_mW"])
            cells = float(r["pnr_total_cells"])
        except (KeyError, ValueError):
            continue
        if leak <= 0 or cells <= 0:
            continue
        lpc = math.log10(leak / cells)
        key = (r["arch_params"], r["node"], float(r["clock_period_ns"]),
               r.get("stim_mode", ""))
        per_node.setdefault(r["node"], []).append(lpc)
        vals.append((key, r["node"], lpc))
    anchor = {n: sorted(v)[int(0.10 * len(v))] for n, v in per_node.items()}
    bad = {key for key, node, lpc in vals if lpc > anchor[node] + dex}
    stats = {
        "dex": dex,
        "anchor_log10_mW_per_cell": {n: round(a, 3) for n, a in anchor.items()},
        "quarantined_per_node": {
            n: sum(1 for k, nn, lpc in vals if nn == n and k in bad)
            for n in sorted(per_node)},
    }
    return bad, stats


def split_by_group(items: Sequence[Sample], seed: int,
                   fracs=(0.8, 0.1, 0.1)) -> Tuple[List[Sample], ...]:
    """80/10/10 by design — all mode-rows of one implementation stay together."""
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
# §5.3 loss — the original two axes (SCR, SAR), empty-bin rule from SRAM
# ---------------------------------------------------------------------------

def fit_loss_weights(train_s: Sequence[Sample], bins: int = 20,
                     mu: float = 1.0, eps: float = 1e-6) -> Dict[str, Any]:
    axes = []
    per_axis_w = []
    for name, vals in (("scr", [s.scr for s in train_s]),
                       ("sar", [s.sar for s in train_s])):
        v = torch.tensor(vals, dtype=torch.float32)
        edges = torch.linspace(0.0, 1.0, bins + 1)
        idx = torch.bucketize(v, edges[1:-1])
        pmf = torch.bincount(idx, minlength=bins).float() / len(vals)
        # Empty bins get weight 0 (nothing ever falls there) — including their
        # 1/eps in a normalization would crush the occupied bins (the SRAM
        # empty-bin lesson, applied per axis).
        w = torch.where(pmf > 0, 1.0 / (pmf + eps), torch.zeros_like(pmf))
        axes.append({"name": name, "edges": edges.tolist(), "weights": w.tolist()})
        per_axis_w.append((idx, w))
    # w_i = mu * sqrt(wc*wa), normalized to unit mean over TRAIN SAMPLES.
    raw = torch.sqrt(per_axis_w[0][1][per_axis_w[0][0]]
                     * per_axis_w[1][1][per_axis_w[1][0]])
    norm = float(raw.mean())
    return {"axes": axes, "mu": mu, "eps": eps, "sample_norm": norm,
            "max_min_ratio": float(raw.max() / raw[raw > 0].min()),
            "normalization": "sqrt(w_scr*w_sar)/sample_norm; unit mean over "
                             "samples; empty bins weight 0"}


def loss_weight_for(spec: Dict[str, Any], scr: float, sar: float) -> float:
    def axis_w(ax, v):
        edges = ax["edges"]
        idx = 0
        for i in range(1, len(edges) - 1):
            if v >= edges[i]:
                idx = i
            else:
                break
        return ax["weights"][idx]
    w = math.sqrt(axis_w(spec["axes"][0], scr) * axis_w(spec["axes"][1], sar))
    return spec["mu"] * w / spec["sample_norm"]


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
# training (same recipe as train_sram.train_model)
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
        w = torch.tensor([loss_weight_for(loss_spec, s.scr, s.sar)
                          for s in samples], dtype=torch.float32)
    return x, y, w


def _val_mape(net, x, y, scalers) -> float:
    with torch.no_grad():
        p_log = net(x) * scalers["y_std"] + scalers["y_mean"]
        t_log = y * scalers["y_std"] + scalers["y_mean"]
        p = torch.pow(10.0, p_log)
        t = torch.pow(10.0, t_log)
        return float((torch.abs(p - t) / t).mean())


def train_model(component: str, metric: str, train_s: List[Sample],
                val_s: List[Sample], arch: List[int], epochs: int, seed: int,
                lr: float = 1e-3, patience: int = 300) -> TrainResult:
    torch.manual_seed(seed)
    mask = lmlp.scale_mask(component, metric)
    x_mean, x_std = _standardize_fit([s.x for s in train_s], mask)
    ys = [s.y_log10 for s in train_s]
    y_mean = sum(ys) / len(ys)
    y_std = max(math.sqrt(sum((a - y_mean) ** 2 for a in ys) / len(ys)), 1e-9)
    scalers = {"x_mean": x_mean, "x_std": x_std, "x_scale_mask": mask,
               "y_mean": y_mean, "y_std": y_std, "target_log10": True,
               "features": lmlp.feature_names(component, metric)}
    loss_spec = fit_loss_weights(train_s)

    xt, yt, wt = _tensorize(train_s, scalers, loss_spec)
    xv, yv, _ = _tensorize(val_s, scalers)

    net = lmlp.LogicMlp(lmlp.n_inputs(component, metric), arch)
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


def eval_per_mode(net, scalers, samples: Sequence[Sample]) -> Dict[str, Any]:
    preds = _predict_linear(net, scalers, samples)
    truths = [10.0 ** s.y_log10 for s in samples]
    per_mode: Dict[str, Any] = {}
    for mode in sorted({s.mode for s in samples}):
        t = [tr for s, tr in zip(samples, truths) if s.mode == mode]
        p = [pr for s, pr in zip(samples, preds) if s.mode == mode]
        per_mode[mode or "-"] = {"mape": mape(t, p), "n": len(t)}
    per_node: Dict[str, float] = {}
    for node in sorted({s.node for s in samples}):
        t = [tr for s, tr in zip(samples, truths) if s.node == node]
        p = [pr for s, pr in zip(samples, preds) if s.node == node]
        per_node[node] = mape(t, p)
    return {"mape": mape(truths, preds),
            "spearman": spearman(truths, preds),
            "per_mode": per_mode, "per_node": per_node,
            "_preds": preds, "_truths": truths}


# ---------------------------------------------------------------------------
# audits (leave-node-out) + the none A/B
# ---------------------------------------------------------------------------

def run_audits(component: str, metric: str, samples: List[Sample],
               arch: List[int], epochs: int, seed: int,
               patience: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for node in (f"{n}nm" for n in lmlp.NODE_LIST):
        holdout = [s for s in samples if s.node == node]
        rest = [s for s in samples if s.node != node]
        if len(holdout) < 8 or len(rest) < 50:
            out[f"leave_node_{node}"] = {
                "skipped": f"holdout={len(holdout)} rest={len(rest)}"}
            continue
        tr, va, _ = split_by_group(rest, seed, fracs=(0.9, 0.1, 0.0))
        res = train_model(component, metric, tr, va, arch, epochs, seed,
                          patience=patience)
        ev = eval_per_mode(res.net, res.scalers, holdout)
        out[f"leave_node_{node}"] = {
            "mape": ev["mape"],
            "per_mode": {k: v["mape"] for k, v in ev["per_mode"].items()},
            "n_holdout": len(holdout)}
    return out


def ab_none(component: str, samples: List[Sample], arch: List[int],
            epochs: int, seed: int, patience: int,
            with_none: TrainResult, test_s: List[Sample]) -> Dict[str, Any]:
    """Retrain the energy model WITHOUT the 'none' rows; compare both on the
    same non-none test rows — the evidence basis for dropping 'none' later."""
    if "none" not in lmlp.STIM_MODES[component]:
        return {"skipped": "'none' already excluded from this component's "
                           "vocabulary (dropped per an earlier A/B)"}
    test_ex = [s for s in test_s if s.mode != "none"]
    if not test_ex:
        return {"skipped": "no non-none test rows"}
    sans = [s for s in samples if s.mode != "none"]
    tr, va, _ = split_by_group(sans, seed, fracs=(0.9, 0.1, 0.0))
    # Keep the comparison honest: exclude any training design that appears in
    # the shared test rows.
    test_groups = {s.group for s in test_ex}
    tr = [s for s in tr if s.group not in test_groups]
    va = [s for s in va if s.group not in test_groups] or tr[-max(1, len(tr)//10):]
    res = train_model(component, "energy", tr, va, arch, epochs, seed,
                      patience=patience)
    ev_with = eval_per_mode(with_none.net, with_none.scalers, test_ex)
    ev_sans = eval_per_mode(res.net, res.scalers, test_ex)
    return {
        "test_rows_ex_none": len(test_ex),
        "with_none_mape": ev_with["mape"],
        "without_none_mape": ev_sans["mape"],
        "with_none_per_mode": {k: v["mape"] for k, v in ev_with["per_mode"].items()},
        "without_none_per_mode": {k: v["mape"] for k, v in ev_sans["per_mode"].items()},
        "verdict_hint": ("none HURTS (>1%p)" if
                         ev_with["mape"] - ev_sans["mape"] > 0.01 else "keep none"),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--components", default=",".join(lmlp.COMPONENTS))
    ap.add_argument("--metrics", default=",".join(lmlp.METRICS))
    ap.add_argument("--dataset-dir", default=None)
    ap.add_argument("--out-dir", default=str(_HERE))
    ap.add_argument("--epochs", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=300)
    ap.add_argument("--audits", action="store_true",
                    help="run leave-node-out audits (5 extra trainings per model)")
    ap.add_argument("--skip-ab", action="store_true",
                    help="skip the energy none-A/B retrain")
    ap.add_argument("--leakage-exclude-nodes", default="",
                    help="comma-separated nodes whose rows are EXCLUDED from the "
                         "leakage models only (coarser fallback for the same "
                         "contamination --leakage-outlier-dex quarantines per row)")
    ap.add_argument("--leakage-outlier-dex", type=float, default=1.5,
                    help="quarantine leakage rows whose log10(leak/cell) exceeds "
                         "the node's clean anchor (10th pct) by this many decades "
                         "(0 disables). 2026-07-28: a subset of std cells carries "
                         "corrupted leakage characterization (~1000x, physically "
                         "inverted vs clock pressure; 16/20nm clock-tree cells, "
                         "7nm combinational cells) — the clean population sits "
                         "~0.5 dex wide at ~-6.3 log10(mW/cell) on every node, "
                         "contamination at +2..+3.7 dex, so 1.5 dex splits them "
                         "cleanly. See eval_report 'leakage_quarantine'.")
    args = ap.parse_args(argv)

    torch.set_num_threads(4)          # tiny nets: more threads hurt (see SRAM)
    ddir = Path(args.dataset_dir) if args.dataset_dir else _resolve_dataset_dir()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    components = [c.strip() for c in args.components.split(",") if c.strip()]
    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
    for c in components:
        if c not in lmlp.COMPONENTS:
            ap.error(f"unknown component '{c}' (choose from {lmlp.COMPONENTS})")
    for m in metrics:
        if m not in lmlp.METRICS:
            ap.error(f"unknown metric '{m}' (choose from {lmlp.METRICS})")

    ds_hash = lmlp.dataset_hash(ddir, components)
    report: Dict[str, Any] = {
        "dataset": {"dir": str(ddir), "sha256": ds_hash,
                    "components": components},
        "seed": args.seed, "epochs_max": args.epochs,
        "date": datetime.now().isoformat(timespec="seconds"),
        "torch": torch.__version__,
        "models": {}, "audits": {}, "gates": {}, "ab_none": {},
        "dropped_rows": [],
    }

    leak_excl = {n.strip() for n in args.leakage_exclude_nodes.split(",")
                 if n.strip()}
    if leak_excl:
        report["leakage_exclusions"] = {
            "nodes": sorted(leak_excl),
            "reason": "clock-tree cell leakage characterization corrupted at "
                      "these nodes (clock-network leakage up to ~2000x, "
                      "physically inverted vs clock constraint); leakage "
                      "models cover the remaining nodes only",
        }

    report["leakage_quarantine"] = {}
    for component in components:
        rows = list(csv.DictReader(open(lmlp.dataset_csv(ddir, component))))
        samples, dropped = assemble(component, rows)
        if leak_excl:
            samples["leakage"] = [s for s in samples["leakage"]
                                  if s.node not in leak_excl]
        if args.leakage_outlier_dex > 0:
            bad, qstats = leak_quarantine_keys(rows, args.leakage_outlier_dex)
            samples["leakage"] = [
                s for s in samples["leakage"]
                if (s.params, s.node, s.clock_ns, s.mode) not in bad]
            report["leakage_quarantine"][component] = qstats
        report["dropped_rows"].extend(dropped)
        print(f"[{component}] rows={len(rows)}  samples: "
              + ", ".join(f"{m}={len(samples[m])}" for m in lmlp.METRICS)
              + f", dropped={len(dropped)}")

        for metric in metrics:
            t0 = time.time()
            arch = lmlp.DEFAULT_ARCH[metric]
            tr, va, te = split_by_group(samples[metric], args.seed)
            res = train_model(component, metric, tr, va, arch, args.epochs,
                              args.seed, lr=args.lr, patience=args.patience)
            ev = eval_per_mode(res.net, res.scalers, te)

            worst = sorted(
                ({"node": s.node, "clock_ns": s.clock_ns, "params": s.params,
                  "mode": s.mode, "truth": t, "pred": p,
                  "rel_err": abs(p - t) / t}
                 for s, t, p in zip(te, ev["_truths"], ev["_preds"])),
                key=lambda d: -d["rel_err"])[:10]

            meta = {
                "component": component, "model": metric,
                "version": lmlp.VERSION, "arch": arch,
                "n_in": lmlp.n_inputs(component, metric),
                "features": res.scalers["features"],
                "stim_modes": list(lmlp.modes_for(component, metric)),
                "target": f"log10_{lmlp.TARGET_UNITS[metric]}",
                "target_column": lmlp.TARGET_COLUMNS[metric],
                "dataset_sha256": ds_hash, "seed": args.seed,
                "split": {"train": len(tr), "val": len(va), "test": len(te)},
                "epochs_run": res.epochs_run,
                "val_mape": res.val_mape, "test_mape": ev["mape"],
                "test_spearman": ev["spearman"],
                "per_mode_test_mape": {k: v["mape"]
                                       for k, v in ev["per_mode"].items()},
                "per_node_test_mape": ev["per_node"],
                "excluded_nodes": (sorted(leak_excl)
                                   if metric == "leakage" and leak_excl else []),
                "pvt": "TT/25C/nominal only (the dataset has no PVT axes)",
                "loss_max_min_ratio": res.loss_spec["max_min_ratio"],
                "date": datetime.now().isoformat(timespec="seconds"),
                "torch": torch.__version__,
            }
            lmlp.save_quartet(out_dir, component, metric, res.net,
                              res.scalers, res.loss_spec, meta)

            key = f"{component}.{metric}"
            over5 = [m for m, v in ev["per_mode"].items() if v["mape"] > 0.05]
            over10 = [m for m, v in ev["per_mode"].items() if v["mape"] > 0.10]
            report["models"][key] = {
                "arch": arch, "split": meta["split"],
                "epochs_run": res.epochs_run, "val_mape": res.val_mape,
                "test_mape": ev["mape"], "test_spearman": ev["spearman"],
                "per_mode_test_mape": meta["per_mode_test_mape"],
                "per_node_test_mape": ev["per_node"],
                "worst10_test": worst,
                "train_seconds": round(time.time() - t0, 1),
            }
            report["gates"][key] = {"pass_10pct": not over10,
                                    "modes_over_5pct": over5,
                                    "modes_over_10pct": over10}
            print(f"  [{key}] arch={arch} test MAPE={ev['mape']:.3%} "
                  f"ρ={ev['spearman']:.3f} epochs={res.epochs_run} "
                  f"({time.time() - t0:.0f}s)  over5%={over5 or '-'}")

            if metric == "energy" and not args.skip_ab:
                report["ab_none"][component] = ab_none(
                    component, samples["energy"], arch, args.epochs,
                    args.seed, args.patience, res, te)
                print(f"  [{component}] none-A/B: "
                      f"{report['ab_none'][component]}")

            if args.audits:
                report["audits"][key] = run_audits(
                    component, metric, samples[metric], arch, args.epochs,
                    args.seed, args.patience)

        # free per-component eval tensors before the next component
        (out_dir / "eval_report.json").write_text(json.dumps(report, indent=1))

    (out_dir / "eval_report.json").write_text(json.dumps(report, indent=1))
    print(f"wrote {out_dir / 'eval_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
