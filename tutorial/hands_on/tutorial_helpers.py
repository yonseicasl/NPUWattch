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
    for line in lines[start:]:
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
            "area": c["area_str"],
        })
    df = pd.DataFrame(rows).sort_values("share %", ascending=False).reset_index(drop=True)
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
        "avg power": t["avg_power_str"],
        "pJ / MAC": round(e["pJ_per_mac"], 2) if e.get("pJ_per_mac") else None,
        "total_pJ": t["energy_pJ"],
    }


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
