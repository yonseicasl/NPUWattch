"""Small helpers for the hands-on notebooks.

The notebooks call these functions so that each cell stays short. Every
function either runs NPUWattch and keeps its console output, or shows one
part of that output or of the report it wrote.
"""

import json
import pathlib
import re
import shutil
import subprocess

TUTORIAL_ROOT = pathlib.Path(__file__).resolve().parent.parent


def example(path):
    """Return the absolute path of an example folder under tutorial/."""
    return TUTORIAL_ROOT / path


def npuwattch_binary():
    """Return the path of the npuwattch command, or stop with a clear message."""
    found = shutil.which("npuwattch")
    if found is None:
        raise SystemExit(
            "npuwattch is not on your PATH. Install it first:\n"
            "    cd NPUWattch && pip install -e .\n"
            "and then restart this notebook kernel."
        )
    return found


def run(example_dir, *extra_args, log_name="console.txt"):
    """Run an example's ./run script with extra flags and return the console text.

    The full console text is also saved to out/<log_name> in the example folder.
    """
    example_dir = pathlib.Path(example_dir)
    npuwattch_binary()
    result = subprocess.run(
        ["bash", "./run", *extra_args],
        cwd=example_dir, capture_output=True, text=True,
    )
    text = result.stdout + result.stderr
    out_dir = example_dir / "out"
    out_dir.mkdir(exist_ok=True)
    (out_dir / log_name).write_text(text)
    if result.returncode != 0:
        print(text)
        raise RuntimeError(f"./run failed in {example_dir} (exit {result.returncode})")
    return text


def run_npuwattch(args, cwd):
    """Run the npuwattch command with a list of arguments and return the console text."""
    binary = npuwattch_binary()
    result = subprocess.run([binary, *args], cwd=cwd, capture_output=True, text=True)
    text = result.stdout + result.stderr
    if result.returncode != 0:
        print(text)
        raise RuntimeError(f"npuwattch failed (exit {result.returncode})")
    return text


def show_tree(text):
    """Print the instance tree that --tree printed."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if "Instance hierarchy" in l), None)
    if start is None:
        print("(no tree in this output; add --tree)")
        return
    print(lines[start])
    body = lines[start + 1:]
    if body and body[0].startswith("----"):      # the separator under the header
        body = body[1:]
    for line in body:
        if line.startswith("----"):
            break
        print(line)


MESSAGE_LINE = re.compile(r"^(INFO|WARNING|ERROR|CRITICAL) \((NW-\d{4})\): ")


def messages(text):
    """Return the messages of a run as a list of (level, code, line) tuples.

    A message line has the format "LEVEL (NW-nnnn): text".
    """
    found = []
    for line in text.splitlines():
        match = MESSAGE_LINE.match(line)
        if match:
            found.append((match.group(1), match.group(2), line))
    return found


def show_messages(text, kinds=("WARNING",), codes=None):
    """Print the message lines of a run.

    Use kinds to select levels, for example ("WARNING", "INFO").
    Use codes to select message codes, for example ["NW-7222"].
    If you give codes, the function ignores kinds.
    """
    found = False
    for level, code, line in messages(text):
        if (code in codes) if codes else (level in kinds):
            print(line)
            found = True
    if not found:
        print(f"(no {' / '.join(codes or kinds)} lines)")


def show_summary(text):
    """Print the message summary at the end of a run."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if "Message summary:" in l), None)
    if start is None:
        print("(no message summary found)")
        return
    print(lines[start])
    for line in lines[start + 1:]:
        if not line.startswith("    NW-"):
            break
        print(line)


def explain(code):
    """Print the explanation of one message code (npuwattch --explain)."""
    result = subprocess.run([npuwattch_binary(), "--explain", code],
                            capture_output=True, text=True)
    lines = (result.stdout + result.stderr).splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(code)), 0)
    print("\n".join(lines[start:]).rstrip())


def show_totals(text):
    """Print the run totals (the 'total energy = ...' line and the lines after it)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("total energy")), None)
    if start is None:
        print("(no totals line found)")
        return
    for line in lines[start:start + 3]:
        if line.strip():
            print(line)


def total_energy_pJ(text):
    """Return the total energy in pJ from the console text."""
    match = re.search(r"total energy = ([0-9.e+-]+) pJ", text)
    return float(match.group(1)) if match else None


def report(example_dir, name="out/report.json"):
    """Load the report.json that a run wrote."""
    return json.loads((pathlib.Path(example_dir) / name).read_text())


def components_df(rep, top=None):
    """Return the component table of a report as a pandas DataFrame."""
    import pandas as pd

    rows = []
    for c in rep["components"]:
        rows.append({
            "component": c["name"],
            "class": c["cls"],
            "model": c["model"],
            "instances": c["count"],
            "energy": c["energy_str"],
            "share %": round(c["energy_pct"], 1),
            "area µm²/inst": c["area_str"],
            "_pJ": c["energy_pJ"],
        })
    df = (pd.DataFrame(rows).sort_values("_pJ", ascending=False)
          .drop(columns="_pJ").reset_index(drop=True))
    return df.head(top) if top else df


def windows_df(rep):
    """Return the per-window table of a report as a pandas DataFrame."""
    import pandas as pd

    rows = []
    for w in rep["windows"]:
        rows.append({
            "window": w["label"],
            "cycles": w["cycles"],
            "dynamic": w["dyn_str"],
            "leakage": w["leak_str"],
            "total": w["total_str"],
            "total_pJ": w["total_pJ"],
        })
    return pd.DataFrame(rows)


def summary_row(rep, label):
    """Return one row of headline numbers from a report, for side-by-side tables."""
    t = rep["totals"]
    e = rep.get("efficiency") or {}
    split = rep.get("npu_dram_split") or {}
    return {
        "design / workload": label,
        "total energy": t["energy_str"],
        "DRAM share %": round(split.get("dram_pct", 0.0), 1),
        "area mm²": round(t["area_mm2"], 3),
        "time": t["exec_time_str"],
        "avg power": t["avg_power_str"],
        "MAC util %": mac_utilization(rep),
        "pJ / MAC": round(e["pJ_per_mac"], 2) if e.get("pJ_per_mac") else None,
        "total_pJ": t["energy_pJ"],
    }


def tree_leaves(rep):
    """Return the leaf nodes of the report's instance tree as (path, node) pairs.

    The path is the dotted name of the node, for example "chip.core0.array0.pe".
    """
    found = []

    def walk(node, path):
        name = f"{path}.{node['name']}" if path else node["name"]
        children = node.get("children") or []
        if not children:
            found.append((name, node))
        for child in children:
            walk(child, name)

    walk(rep["tree"], "")
    return found


def tree_count(rep, leaf_name):
    """Return how many instances of one leaf name the tree has, summed over all paths.

    For example tree_count(rep, "pe") is the number of PEs in all systolic
    arrays, and tree_count(rep, "dram_chan") is the number of DRAM channels.
    """
    return sum(node.get("count", 1) for path, node in tree_leaves(rep)
               if path.rsplit(".", 1)[-1] == leaf_name)


def tree_label(rep, leaf_name):
    """Return the label of the first leaf with this name, for example its class and sizes."""
    for path, node in tree_leaves(rep):
        if path.rsplit(".", 1)[-1] == leaf_name:
            return node.get("label", "")
    return ""


def mac_units(rep):
    """Return the number of MAC units of the design.

    These are the PEs of the systolic arrays in a PyTorchSim run ("pe") and
    the MAC components in a Timeloop run ("mac"). The vector unit is not
    counted.
    """
    return tree_count(rep, "pe") + tree_count(rep, "mac")


def mac_utilization(rep):
    """Return the MAC utilization of a run in percent, or None if the run has no MACs.

    MAC utilization = useful MACs / (cycles x MAC units). It says how much of
    the run time the MAC units did useful work.
    """
    e = rep.get("efficiency") or {}
    units = mac_units(rep)
    cycles = rep["totals"]["cycles"]
    if not e.get("mac_ops") or not units or not cycles:
        return None
    return round(100.0 * e["mac_ops"] / (cycles * units), 1)


def _pe_type(label):
    """Return a short data-type name for a PE label, for example "fp32" or "int"."""
    m = re.search(r"exponent_bits=(\d+), mantissa_bits=(\d+)", label)
    if m:
        return {("8", "23"): "fp32", ("8", "7"): "bf16", ("5", "10"): "fp16"}.get(m.groups(), "fp")
    if "intmac" in label:
        return "int"
    return ""


def _size(label):
    """Return the size at the end of a tree label, for example "128 KB", or ""."""
    m = re.search(r"= ([\d.]+ [KMG]?B)\s*$", label)
    return m.group(1) if m else ""


def _peak(rep, units):
    """Return the peak rate of the MAC units as a string, 2 operations per MAC."""
    f_hz = rep["clock"]["frequency_MHz"] * 1e6
    tops = units * 2 * f_hz / 1e12
    unit = "TOPS" if _pe_type(tree_label(rep, "pe") or tree_label(rep, "mac")) == "int" else "TFLOP/s"
    return f"{tops:.3g} {unit}"


def machine_card(rep, name=None):
    """Print one line that says what machine the report is about.

    The line has the node and the clock, the MAC units and their peak rate,
    the on-chip memories, and the DRAM. All of it comes from report.json, so
    the line always matches the numbers next to it. Give a name when you
    print the cards of two designs one after the other.
    """
    node = re.sub(r"(\d)nm$", r"\1 nm", rep["tech"]["node"])
    f = rep["clock"]["frequency_MHz"]
    units = mac_units(rep)
    parts = [f"{node}, {f:g} MHz"]

    if tree_count(rep, "pe"):                                  # a PyTorchSim run
        cores = sum(1 for c in rep["tree"]["children"] for cc in [c] if cc["name"].startswith("core"))
        arrays = sum(1 for path, _ in tree_leaves(rep) if path.endswith(".pe"))
        per_array = tree_count(rep, "pe") // arrays
        side = int(round(per_array ** 0.5))
        shape = f"{side}×{side}" if side * side == per_array else f"{per_array}"
        pe = _pe_type(tree_label(rep, "pe"))
        parts.append(f"{cores} core{'s' if cores > 1 else ''}, {arrays} arrays of {shape} {pe} PEs "
                     f"= {units:,} MAC units (peak {_peak(rep, units)})")
        lanes = tree_count(rep, "vpu_spad")
        if lanes:
            parts.append(f"{lanes} lanes × {_size(tree_label(rep, 'vpu_spad'))} scratchpad")
        xbar = tree_label(rep, "icnt_xbar")
        m = re.search(r"net_inputs=(\d+), net_outputs=(\d+)", xbar)
        if m:
            parts.append(f"NoC {m.group(1)}×{m.group(2)} crossbar")
        chans = tree_count(rep, "dram_chan")
        pj_bit = (rep.get("dram_breakdown") or {}).get("constants", {}).get("access_pJ_per_bit")
        if chans:
            parts.append(f"DRAM {chans} channels" + (f" at {pj_bit:g} pJ/bit" if pj_bit else ""))
    else:                                                      # a Timeloop run
        mesh = re.findall(r"mesh[XY]=(\d+)", " ".join(_container_labels(rep)))
        grid = "×".join(mesh) + " = " if mesh else ""
        parts.append(f"{grid}{units:,} MAC units (peak {_peak(rep, units)})")
        buffers = [f"{path.rsplit('.', 1)[-1]} {_size(node.get('label', ''))}"
                   for path, node in tree_leaves(rep)
                   if "smartbuffer_SRAM" in node.get("label", "") and _size(node.get("label", ""))]
        if buffers:
            parts.append("Buffers: " + ", ".join(buffers))
        dram_type = ""
        for note in (rep.get("provenance") or {}).get("notes", []):
            m = re.search(r"DRAM type (\w+)", note)
            if m:
                dram_type = m.group(1)
                break
        pj_bit = (rep.get("dram_breakdown") or {}).get("constants", {}).get("access_pJ_per_bit")
        parts.append("DRAM " + (dram_type + " " if dram_type else "") + (f"at {pj_bit:g} pJ/bit" if pj_bit else ""))

    head = f"Machine ({name}): " if name else "Machine: "
    print(head + ". ".join(parts) + ".")


def _container_labels(rep):
    """Return the labels of the container nodes of the tree (they carry meshX / meshY)."""
    found = []

    def walk(node):
        if node.get("children"):
            found.append(node.get("label", ""))
            for child in node["children"]:
                walk(child)

    walk(rep["tree"])
    return found


def show_utilization(rep):
    """Print the cycles, the time, and the MAC utilization of a run in one line each."""
    t = rep["totals"]
    e = rep.get("efficiency") or {}
    f = rep["clock"]["frequency_MHz"]
    print(f"cycles: {t['cycles']:,} at {f:g} MHz = {t['exec_time_str']}")
    units = mac_units(rep)
    util = mac_utilization(rep)
    if util is not None:
        print(f"useful MACs: {e['mac_ops'] / 1e9:.2f} G on {units:,} MAC units in {t['cycles']:,} cycles "
              f"= {util}% MAC utilization")
    else:
        print("useful MACs: none (the run has no GEMM kernel)")


def show_report(example_dir, height=650):
    """Show the HTML report of an example inside the notebook.

    The report is one self-contained HTML file. This function puts the
    content of the file into the frame (srcdoc), and does not give a path.
    Thus the report shows in VS Code and in Jupyter, and the saved notebook
    keeps it.
    """
    import html
    from IPython.display import HTML

    path = pathlib.Path(example_dir) / "out" / "report.html"
    doc = html.escape(path.read_text(encoding="utf-8"), quote=True)
    return HTML(f'<div><iframe srcdoc="{doc}" width="100%" height="{height}" '
                f'style="border:0"></iframe></div>')


def show_file(path, max_lines=None):
    """Print a text file, optionally only its first lines."""
    lines = pathlib.Path(path).read_text().splitlines()
    if max_lines:
        lines = lines[:max_lines]
    print("\n".join(lines))
