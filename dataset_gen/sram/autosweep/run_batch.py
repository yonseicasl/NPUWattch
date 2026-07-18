#!/usr/bin/env python3
"""
run_batch.py — SRAM characterization sweep driver (array + decoder flows).

Python replacement for run_batch.sh (2026-07-15), mirroring the logic
autosweep driver's operating model:

  ./run_batch.py [jobs.csv] [-nodes 20,16] [-jobs-per-node N]
                 [--dry-run] [--no-dec] [--no-collect] [--no-prune]
                 [--stop-on-fail]

Job list format is unchanged (see gen_jobs.py / README.md):
  node,rows,cols,wd,toggle_rate,vdd_V,temp_C,pex

Operating model
  - ALL nodes in the (filtered) job list run in parallel — one worker per
    node; within a node, -jobs-per-node N sims run concurrently
    (default 1).  Total concurrent HSPICE = nodes x N, bounded by license
    seats; the decoder stage additionally takes dc_shell/icc2_shell seats
    while building missing collateral.
  - -nodes 20,16 filters the job list to those nodes and fails fast if a
    requested node has no SRAM library in the tech_libs catalog — use it
    to bring up a newly added node without touching finished ones.
  - Resume: an array job whose configuration key already has a row in
    datasets/sram_array.csv is skipped; a decoder point already in
    sram_decoder.csv is skipped.  Crash-interrupted runs left no sheet
    row, so they re-run whole.  Duplicate keys inside one job list run
    once.
  - Storage bounding: right after each sim its run dir is pruned to
    {meta/area/wl_load json, measures.csv, sim.log, .mt0, the testbench}
    plus a gzipped tr0 (nothing downstream re-reads the raw tr0 — both
    collect scripts work from measures.csv).  After the LAST batch job of
    a decoder config, its DC/ICC2/GDS/PEX stage dirs are pruned to
    reports + json sidecars; a later re-run of that config rebuilds them
    from scratch.  Array 01_gds/02_pex collateral is deliberately KEPT:
    it is a few MB per config, every PVT point of the config reuses it,
    and the decoder flow reads the array SPEF for its wordline load.
  - Failures land in sweep_failures.tsv and do not stop the batch
    (unless --stop-on-fail); per-job logs go to logs/.

After the batch, collect_array.py --skip-bad and collect_decoder.py
rebuild both dataset sheets idempotently (latest run per config wins).
"""
import argparse
import csv
import glob
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BATCH_DIR = os.path.dirname(os.path.abspath(__file__))
SRAM = os.path.normpath(os.path.join(BATCH_DIR, ".."))
SPICE = os.path.join(SRAM, "spice")
ARR = os.path.join(SRAM, "array")
DEC = os.path.join(SRAM, "decoder")
DATASETS = os.path.join(SRAM, "datasets")
LOG_DIR = os.path.join(BATCH_DIR, "logs")
FAILURES = os.path.join(BATCH_DIR, "sweep_failures.tsv")
STAMP = time.strftime("%Y%m%d_%H%M%S")

# Files kept in a pruned 03_sim / 05_sim run dir (everything else is
# deleted; the tr0 is gzipped in place).  collect_array/collect_decoder
# only ever read meta.json + area.json (+ wl_load.json) + measures.csv,
# so pruned run dirs stay valid sources for idempotent sheet rebuilds.
SIM_KEEP = {"meta.json", "area.json", "wl_load.json", "measures.csv",
            "sim.log"}

# Decoder stage-dir prune policy: keep(name) per stage, drop the rest.
# 03_gds/04_pex removal breaks run_decoder.sh --reuse-gds on purpose — a
# future batch on the same config re-runs DC/ICC2/PEX (accepted cost for
# the ~20-400 MB/config these dirs otherwise hold).
DEC_STAGE_KEEP = {
    "01_syn": lambda n: n.endswith(".rpt"),
    "02_pnr": lambda n: n.endswith(".json") or n == "icc2_reports",
    "03_gds": lambda n: n.endswith(".json"),
    "04_pex": lambda n: n.endswith((".RESULTS", ".LAYOUT_ERRORS")),
}

_PRINT_LOCK = threading.Lock()
_FAIL_LOCK = threading.Lock()
_LOCKS_LOCK = threading.Lock()
_CELL_LOCKS = {}


def say(msg):
    with _PRINT_LOCK:
        print(msg, flush=True)


def die(msg):
    sys.exit("run_batch: error: %s" % msg)


def cell_lock(key):
    with _LOCKS_LOCK:
        if key not in _CELL_LOCKS:
            _CELL_LOCKS[key] = threading.Lock()
        return _CELL_LOCKS[key]


def read_env_file(path):
    env = {}
    with open(path) as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def norm_node(spec):
    spec = str(spec).strip().lower()
    if spec.endswith("nm"):
        spec = spec[:-2]
    if not spec.isdigit():
        die("bad node spec: %r" % spec)
    return str(int(spec))


class NodeInfo(object):
    """Catalog + node.env facts for one node; construction fails fast when
    the node has no SRAM library (a typo'd -nodes would otherwise burn a
    whole batch on per-job errors)."""

    def __init__(self, key):
        self.key = key                      # "20"
        self.dirname = "%02dnm" % int(key)  # "20nm" (TECH_20nm)
        proc = subprocess.run(
            ["python3", os.path.join(SPICE, "scripts", "tech_paths.py"),
             "--node", key],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        paths = {}
        for line in proc.stdout.decode("utf-8", "replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                paths[k.strip()] = v.strip()
        if proc.returncode != 0 or not paths.get("TECH_SRAM"):
            die("node %s has no SRAM library (no sramdir in "
                "tech_libs/catalog.json)" % key)
        self.tech_sram = paths["TECH_SRAM"]
        env_path = os.path.join(self.tech_sram, "node.env")
        if not os.path.isfile(env_path):
            die("missing %s" % env_path)
        env = read_env_file(env_path)
        self.name = env.get("NODE_NAME", self.dirname)   # sheet node column
        self.vdd_nom = float(env["VDD"])
        self.temp = float(env.get("TEMP", 25))
        self.flavor = env.get("FLAVOR", "hp")
        self.corner = env.get("CORNER", "TT")
        self.tech_dir = os.path.join(SRAM, "TECH_" + self.dirname)


class WdResolver(object):
    """default/unit write-driver strengths via the gdstk python (the maps
    live in gen_col.py/gen_array.py, which import gdstk)."""

    def __init__(self, py):
        self.py = py
        self.cache = {}

    def _query(self, expr, node):
        code = ("import sys; sys.path.insert(0, %r);"
                "from gen_col import NODE_SPECS, norm_node;"
                "from gen_array import default_wd;"
                "print(%s)" % (os.path.join(ARR, "scripts"), expr))
        proc = subprocess.run([self.py, "-c", code],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            die("cannot resolve wd for node %s (set PYTHON_GDSTK in "
                "site.env to a gdstk python):\n%s"
                % (node, proc.stdout.decode("utf-8", "replace").strip()))
        return int(proc.stdout.decode().strip().splitlines()[-1])

    def default(self, node, rows):
        key = ("default", node, rows)
        if key not in self.cache:
            self.cache[key] = self._query(
                "default_wd(NODE_SPECS[norm_node(%r)], %d)" % (node, rows),
                node)
        return self.cache[key]

    def unit(self, node):
        key = ("unit", node)
        if key not in self.cache:
            self.cache[key] = self._query(
                "NODE_SPECS[norm_node(%r)].wd_unit" % node, node)
        return self.cache[key]


# ── job list -> work items ───────────────────────────────────────────────────

def read_jobs(path):
    jobs = []
    with open(path) as fp:
        for lineno, line in enumerate(fp, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            f = [t.strip() for t in line.split(",")]
            if f[0] == "node":
                continue
            if len(f) < 3 or not f[1] or not f[2]:
                say("SKIP malformed jobs.csv line %d: %s" % (lineno, line))
                continue
            f += [""] * (8 - len(f))
            jobs.append({"node": f[0], "rows": int(f[1]), "cols": int(f[2]),
                         "wd": f[3], "toggle_rate": f[4], "vdd": f[5],
                         "temp": f[6], "pex": f[7]})
    return jobs


def resolve_job(raw, info, wds):
    rows, cols = raw["rows"], raw["cols"]
    wd = int(raw["wd"]) if raw["wd"] else wds.default(info.key, rows)
    rate_req = float(raw["toggle_rate"]) if raw["toggle_rate"] else 1.0
    if not 0.0 <= rate_req <= 1.0:
        die("toggle_rate %g out of [0,1]" % rate_req)
    n_t = int(round(rate_req * cols))
    rate = round(float(n_t) / cols, 6)     # TB's effective rate = sheet key
    vdd = float(raw["vdd"]) if raw["vdd"] else info.vdd_nom
    temp = float(raw["temp"]) if raw["temp"] else info.temp
    pex = int(raw["pex"]) if raw["pex"] else 1
    voff = round(vdd - info.vdd_nom, 6)
    job = {
        "info": info, "rows": rows, "cols": cols, "wd": wd,
        "rate_req": rate_req, "rate": rate, "vdd": vdd, "temp": temp,
        "pex": pex,
        "cell": "array_X%d_%dx%d" % (wd, rows, cols),
        "dec_cell": "dec_%dx%d" % (rows, cols),
        "vdd_arg": raw["vdd"], "temp_arg": raw["temp"],
    }
    job["key"] = (info.name, info.flavor, info.corner, voff,
                  round(temp, 6), rows, cols, wd, rate, pex)
    job["dec_key"] = (info.name, rows, cols, voff, round(temp, 6), pex)
    job["tag"] = "%s_%s_tr%g_v%s_t%s" % (
        info.dirname, job["cell"], rate_req,
        raw["vdd"] or "nom", raw["temp"] or "nom")
    job["dec_tag"] = "%s_%s_v%s_t%s" % (
        info.dirname, job["dec_cell"],
        raw["vdd"] or "nom", raw["temp"] or "nom")
    return job


def load_array_keys():
    keys = set()
    path = os.path.join(DATASETS, "sram_array.csv")
    if not os.path.isfile(path):
        return keys
    with open(path, newline="") as fp:
        for r in csv.DictReader(fp):
            keys.add((r["node"], r["transistor"], r["corner"],
                      round(float(r["voltage_offset_V"]), 6),
                      round(float(r["temperature_C"]), 6),
                      int(r["rows"]), int(r["cols"]), int(r["wd"]),
                      round(float(r["toggle_rate"]), 6), int(r["pex"])))
    return keys


def load_dec_keys():
    keys = set()
    path = os.path.join(DATASETS, "sram_decoder.csv")
    if not os.path.isfile(path):
        return keys
    with open(path, newline="") as fp:
        for r in csv.DictReader(fp):
            keys.add((r["node"], int(r["rows"]), int(r["cols"]),
                      round(float(r["voltage_offset_V"]), 6),
                      round(float(r["temperature_C"]), 6), int(r["pex"])))
    return keys


# ── storage pruning ──────────────────────────────────────────────────────────

def gzip_file(path):
    with open(path, "rb") as fi, gzip.open(path + ".gz", "wb", 6) as fo:
        shutil.copyfileobj(fi, fo, 1 << 20)
    os.unlink(path)


def prune_sim_dir(run_dir):
    """Keep measures + metadata + testbench, gzip the tr0, drop the rest
    (netlist copy, .lis/.ic0/.st0/.pa0, spef/models symlinks)."""
    for name in sorted(os.listdir(run_dir)):
        path = os.path.join(run_dir, name)
        if (name in SIM_KEEP or name.endswith((".mt0", ".tr0.gz"))
                or (name.startswith("tb_") and name.endswith(".sp"))):
            continue
        if name.endswith(".tr0"):
            gzip_file(path)
        elif os.path.islink(path) or os.path.isfile(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def prune_dec_stages(work_dir):
    """Reduce a decoder config's DC/ICC2/GDS/PEX stage dirs to reports +
    sidecars once every batch job on the config is done."""
    for stage, keep in DEC_STAGE_KEEP.items():
        stage_dir = os.path.join(work_dir, stage)
        if not os.path.isdir(stage_dir):
            continue
        for name in sorted(os.listdir(stage_dir)):
            if keep(name):
                continue
            path = os.path.join(stage_dir, name)
            if os.path.islink(path) or os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)


# ── running one work item ────────────────────────────────────────────────────

def record_failure(tag, step, message):
    with _FAIL_LOCK:
        new = not os.path.isfile(FAILURES)
        with open(FAILURES, "a") as fp:
            if new:
                fp.write("tag\tstep\terror\n")
            fp.write("%s\t%s\t%s\n" % (
                tag, step,
                message[:300].replace("\t", " ").replace("\n", " ")))


class StepError(RuntimeError):
    def __init__(self, step, message):
        super(StepError, self).__init__(message)
        self.step = step


def run_step(step, cmd, log_path, cwd=None, env=None):
    with open(log_path, "a") as log:
        log.write("\n===== %s [%s]: %s\n"
                  % (step, time.strftime("%H:%M:%S"), " ".join(cmd)))
        log.flush()
        proc = subprocess.run(cmd, cwd=cwd, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        tail = ""
        try:
            with open(log_path, errors="replace") as fp:
                tail = "".join(fp.readlines()[-5:]).strip()
        except OSError:
            pass
        raise StepError(step, "exit %d; log tail: %s"
                        % (proc.returncode, tail))


def parse_run_dir(log_path):
    run_dir = None
    with open(log_path, errors="replace") as fp:
        for line in fp:
            if line.startswith("Results: "):
                run_dir = line[len("Results: "):].strip()
    return run_dir


def build_array_collateral(job, wds, log_path, env):
    """gen_wd/gen_col/gen_array/gds2spice for whatever is missing.  Every
    artifact takes its own lock and is re-checked inside it: arrays of
    one node share wd ladders and columns (8x4/8x8/8x16 all need
    column_X4_8), so a per-array lock alone lets concurrent jobs race
    the shared builds (gen_col then dies on "exists (use --force)")."""
    info, cell = job["info"], job["cell"]
    tech = info.tech_dir
    col = "column_X%d_%d" % (job["wd"], job["rows"])
    col_gds = os.path.join(tech, col, "01_gds", col + ".gds")
    py = wds.py
    if not os.path.isfile(col_gds):
        unit = wds.unit(info.key)
        wd = "wd_X%d" % job["wd"]
        wd_gds = os.path.join(tech, wd, "01_gds", wd + ".gds")
        if job["wd"] != unit and not os.path.isfile(wd_gds):
            with cell_lock((info.key, wd)):
                if not os.path.isfile(wd_gds):
                    run_step("gen_wd",
                             [py, os.path.join(ARR, "scripts",
                                               "gen_wd.py"),
                              "--node", info.key, "X%d" % job["wd"]],
                             log_path, env=env)
        with cell_lock((info.key, col)):
            if not os.path.isfile(col_gds):
                run_step("gen_col",
                         [py, os.path.join(ARR, "scripts", "gen_col.py"),
                          "--node", info.key, "--rows", str(job["rows"]),
                          "--wd", str(job["wd"])],
                         log_path, env=env)
    with cell_lock((info.key, cell)):
        gds = os.path.join(tech, cell, "01_gds", cell + ".gds")
        sidecar = os.path.join(tech, cell, "01_gds", cell + ".json")
        if not (os.path.isfile(gds) and os.path.isfile(sidecar)):
            run_step("gen_array",
                     [py, os.path.join(ARR, "scripts", "gen_array.py"),
                      "--node", info.key, "--rows", str(job["rows"]),
                      "--wd", str(job["wd"]), "--cols", str(job["cols"]),
                      "--force"],
                     log_path, env=env)
        pex_sp = os.path.join(tech, cell, "02_pex", cell + ".sp")
        pex_spef = os.path.join(tech, cell, "02_pex", cell + ".spef")
        need = not os.path.isfile(pex_sp) or (
            job["pex"] == 1 and not os.path.isfile(pex_spef))
        if need:
            run_step("extract",
                     [os.path.join(SPICE, "gds2spice.sh"),
                      "--node", info.key, cell],
                     log_path, cwd=SPICE, env=env)


def run_array_item(job, wds, opts, env):
    log_path = os.path.join(LOG_DIR, "%s_%s.log" % (job["tag"], STAMP))
    build_array_collateral(job, wds, log_path, env)
    cmd = [os.path.join(ARR, "run_array.sh"),
           "--node", job["info"].key, job["cell"],
           "--toggle", "%g" % job["rate_req"]]
    if job["pex"] == 1:
        cmd.append("--pex")
    if job["vdd_arg"]:
        cmd += ["--vdd", job["vdd_arg"]]
    if job["temp_arg"]:
        cmd += ["--temp", job["temp_arg"]]
    run_step("simulate", cmd, log_path, cwd=ARR, env=env)
    run_dir = parse_run_dir(log_path)
    if not run_dir or not os.path.isfile(os.path.join(run_dir,
                                                      "measures.csv")):
        raise StepError("simulate", "no measures.csv in run dir %r "
                        "(see %s)" % (run_dir, log_path))
    if opts.prune:
        prune_sim_dir(run_dir)
    return log_path


def run_dec_item(job, wds, opts, env):
    log_path = os.path.join(LOG_DIR, "%s_%s.log" % (job["dec_tag"], STAMP))
    info = job["info"]
    # wl_load.py needs an array PEX spef (wordline RC) and the array's
    # 01_gds sidecar (die height, rows must match) on disk; nothing else
    # guarantees they exist when this runs — the array item races us
    # under -jobs-per-node > 1, and a sheet-resumed array may have no
    # collateral at all.  Building this job's own array satisfies both
    # (matching rows AND cols); the artifact locks make it a no-op when
    # the array item got there first.
    build_array_collateral(job, wds, log_path, env)
    cmd = [os.path.join(DEC, "run_decoder.sh"),
           "--node", info.key, "--rows", str(job["rows"]),
           "--cols", str(job["cols"]), "--reuse-gds"]
    if job["pex"] == 0:
        cmd.append("--no-pex")
    if job["vdd_arg"]:
        cmd += ["--vdd", job["vdd_arg"]]
    if job["temp_arg"]:
        cmd += ["--temp", job["temp_arg"]]
    # the whole script (DC/ICC2 collateral build + sim) holds the cell
    # lock: two PVT points of one decoder must not both decide the GDS is
    # missing and run DC/ICC2 into the same stage dirs
    with cell_lock((info.key, job["dec_cell"])):
        run_step("decoder", cmd, log_path, cwd=DEC, env=env)
    run_dir = parse_run_dir(log_path)
    if not run_dir or not os.path.isfile(os.path.join(run_dir,
                                                      "measures.csv")):
        raise StepError("decoder", "no measures.csv in run dir %r "
                        "(see %s)" % (run_dir, log_path))
    if opts.prune:
        prune_sim_dir(run_dir)
    return log_path


# ── per-node worker ──────────────────────────────────────────────────────────

def _fmt_dur(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return "%dh%02dm" % (seconds // 3600, seconds % 3600 // 60)
    return "%dm%02ds" % (seconds // 60, seconds % 60)


def run_item(item, wds, opts, env, state):
    kind, job = item
    tag = job["tag"] if kind == "array" else job["dec_tag"]
    if state["stop"].is_set():
        return kind, tag, "aborted", 0.0
    start = time.monotonic()
    try:
        if kind == "array":
            run_array_item(job, wds, opts, env)
        else:
            run_dec_item(job, wds, opts, env)
        outcome = "done"
    except StepError as exc:
        record_failure(tag, exc.step, str(exc))
        outcome = "failed:%s" % exc.step
        if opts.stop_on_fail:
            state["stop"].set()
    except Exception as exc:  # noqa: BLE001 — a sweep must survive bad jobs
        record_failure(tag, "internal", "%s: %s" % (type(exc).__name__, exc))
        outcome = "failed:internal"
        if opts.stop_on_fail:
            state["stop"].set()

    # decoder stage-dir prune once the config's last batch item finished
    # cleanly (any failure keeps the collateral around for debugging)
    if kind == "dec" and opts.prune:
        ckey = (job["info"].key, job["dec_cell"])
        with state["dec_lock"]:
            state["dec_pending"][ckey] -= 1
            if outcome != "done":
                state["dec_failed"].add(ckey)
            ready = (state["dec_pending"][ckey] == 0
                     and ckey not in state["dec_failed"])
        if ready:
            prune_dec_stages(os.path.join(job["info"].tech_dir,
                                          job["dec_cell"]))
    return kind, tag, outcome, time.monotonic() - start


def run_node(node_key, items, wds, opts, env, state):
    counts = {"done": 0, "failed": 0, "aborted": 0}
    total = len(items)

    def finish(index, result):
        kind, tag, outcome, duration = result
        counts["failed" if outcome.startswith("failed")
               else outcome if outcome in counts else "done"] += 1
        say("[%snm] %d/%d %s %s (%s, %s)"
            % (node_key, index, total, outcome, tag, kind,
               _fmt_dur(duration)))

    if opts.jobs_per_node <= 1:
        for index, item in enumerate(items, start=1):
            finish(index, run_item(item, wds, opts, env, state))
        return counts
    with ThreadPoolExecutor(max_workers=opts.jobs_per_node) as pool:
        futures = [pool.submit(run_item, item, wds, opts, env, state)
                   for item in items]
        for index, future in enumerate(as_completed(futures), start=1):
            finish(index, future.result())
    return counts


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run the SRAM characterization sweep (array + decoder "
        "flows) from a job list; all nodes in parallel.")
    parser.add_argument("jobs", nargs="?",
                        default=os.path.join(BATCH_DIR, "jobs.csv"),
                        help="job list CSV (default: autosweep/jobs.csv)")
    parser.add_argument("-nodes", dest="nodes", default=None,
                        help="comma-separated node filter, e.g. -nodes 3 or "
                        "-nodes 20,16; fails fast if a node has no SRAM "
                        "library (default: every node in the job list)")
    parser.add_argument("-jobs-per-node", dest="jobs_per_node", type=int,
                        default=1,
                        help="concurrent sims per node (default 1; total "
                        "concurrent HSPICE = nodes x this)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the per-node plan and exit")
    parser.add_argument("--no-dec", dest="dec", action="store_false",
                        help="array flow only, skip decoder points")
    parser.add_argument("--no-collect", dest="collect", action="store_false",
                        help="skip the dataset sheet rebuild at the end")
    parser.add_argument("--no-prune", dest="prune", action="store_false",
                        help="keep every run artifact on disk (no tr0 gzip, "
                        "no report-only reduction)")
    parser.add_argument("--stop-on-fail", action="store_true",
                        help="abort the batch on the first failure")
    opts = parser.parse_args()
    if opts.jobs_per_node < 1:
        parser.error("-jobs-per-node must be >= 1")
    if not os.path.isfile(opts.jobs):
        die("no job list: %s" % opts.jobs)

    env = dict(os.environ)
    site = os.path.join(BATCH_DIR, "site.env")
    if os.path.isfile(site):
        env.update(read_env_file(site))
    py_gdstk = env.get("PYTHON_GDSTK", "python3")
    env["PYTHON_GDSTK"] = py_gdstk
    wds = WdResolver(py_gdstk)

    raw_jobs = read_jobs(opts.jobs)
    wanted = None
    if opts.nodes:
        wanted = {norm_node(part) for part in opts.nodes.split(",")
                  if part.strip()}
        if not wanted:
            parser.error("-nodes needs a comma-separated node list, "
                         "e.g. -nodes 20,16")
        for node in sorted(wanted):
            NodeInfo(node)  # fail fast on catalog gaps before planning
        kept = [j for j in raw_jobs if norm_node(j["node"]) in wanted]
        say("node filter %s kept %d/%d job list rows"
            % (sorted(wanted), len(kept), len(raw_jobs)))
        raw_jobs = kept

    infos = {}
    jobs = []
    for raw in raw_jobs:
        key = norm_node(raw["node"])
        if key not in infos:
            infos[key] = NodeInfo(key)
        jobs.append(resolve_job(raw, infos[key], wds))

    array_done = load_array_keys()
    dec_done = load_dec_keys()

    # per-node work lists: array jobs (deduped on sheet key) + decoder
    # points (deduped; needed even when the array row already exists)
    per_node = {}
    dec_pending = {}
    seen_arrays, seen_decs = set(), set()
    n_skip_arr = n_skip_dec = 0
    for job in jobs:
        node = job["info"].key
        items = per_node.setdefault(node, [])
        if job["key"] in seen_arrays or job["key"] in array_done:
            n_skip_arr += job["key"] not in seen_arrays
            seen_arrays.add(job["key"])
        else:
            seen_arrays.add(job["key"])
            items.append(("array", job))
        if not opts.dec:
            continue
        if job["dec_key"] in seen_decs or job["dec_key"] in dec_done:
            n_skip_dec += job["dec_key"] not in seen_decs
            seen_decs.add(job["dec_key"])
        else:
            seen_decs.add(job["dec_key"])
            items.append(("dec", job))
            ckey = (node, job["dec_cell"])
            dec_pending[ckey] = dec_pending.get(ckey, 0) + 1
    per_node = {n: items for n, items in per_node.items() if items}

    n_arr = sum(1 for items in per_node.values()
                for kind, _ in items if kind == "array")
    n_dec = sum(1 for items in per_node.values()
                for kind, _ in items if kind == "dec")
    say("plan: %d array sim(s) + %d decoder point(s) across nodes %s; "
        "%d array / %d decoder key(s) already in the sheets -> skipped"
        % (n_arr, n_dec, sorted(per_node) or "[]", n_skip_arr, n_skip_dec))
    if opts.dry_run:
        for node in sorted(per_node):
            for kind, job in per_node[node]:
                say("  [%snm] %s %s" % (
                    node, kind,
                    job["tag"] if kind == "array" else job["dec_tag"]))
        return 0
    if not per_node:
        say("nothing to run")
        return 0

    os.makedirs(LOG_DIR, exist_ok=True)
    state = {"stop": threading.Event(), "dec_lock": threading.Lock(),
             "dec_pending": dec_pending, "dec_failed": set()}
    totals = {"done": 0, "failed": 0, "aborted": 0}
    with ThreadPoolExecutor(max_workers=len(per_node)) as pool:
        futures = [pool.submit(run_node, node, items, wds, opts, env, state)
                   for node, items in per_node.items()]
        for future in as_completed(futures):
            for key, value in future.result().items():
                totals[key] += value
    say("batch: %d done, %d failed, %d aborted (failures -> %s)"
        % (totals["done"], totals["failed"], totals["aborted"], FAILURES))

    if opts.collect and totals["done"]:
        subprocess.run(["python3",
                        os.path.join(ARR, "scripts", "collect_array.py"),
                        "--skip-bad"], env=env)
        subprocess.run(["python3",
                        os.path.join(DEC, "scripts", "collect_decoder.py")],
                       env=env)
        subprocess.run(["python3", os.path.join(BATCH_DIR, "qa_sheets.py")],
                       env=env)
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
