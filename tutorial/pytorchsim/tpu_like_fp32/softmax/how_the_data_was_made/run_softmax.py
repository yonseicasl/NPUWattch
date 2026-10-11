"""Template: run one workload, one TOGSim log per compiled kernel.

Run INSIDE the container (see run_in_container.sh). Environment (set by the
launcher, never inside this script):
  TOGSIM_CONFIG       absolute path of the run config (.yml)
  TORCHSIM_DUMP_PATH  <raw>/outputs          (dir name MUST be 'outputs')
  TORCHSIM_LOG_PATH   <raw>/togsim_results
Do NOT wrap calls in `with TOGSimulator(...)`: that streams all kernels into
one TOGSim process (one log for many kernels, and the log goes to stdout).
"""
import glob, os, re, time
import torch
import torch.nn.functional as F

LOG_DIR = os.environ["TORCHSIM_LOG_PATH"]
RAW = os.path.dirname(LOG_DIR)
dev = torch.device("npu:0")
torch.manual_seed(0)
HASH = re.compile(r"tog_path: \S*/outputs/([A-Za-z0-9]+)/")
rows = []          # kernels.yaml rows
seq = [0]


def run_kernel(name, fn, *cpu_inputs, check=True):
    """Compile fn alone, run it on npu:0, rename its log(s) NNN_<name>[_pK]__*.log."""
    before = set(glob.glob(os.path.join(LOG_DIR, "*.log")))
    t0 = time.time()
    npu_inputs = [t.to(dev) for t in cpu_inputs]
    out = torch.compile(dynamic=False)(fn)(*npu_inputs)
    wall = time.time() - t0
    ok = torch.allclose(out.cpu(), fn(*cpu_inputs), rtol=1e-2, atol=1e-2) if check else None
    new = sorted(set(glob.glob(os.path.join(LOG_DIR, "*.log"))) - before,
                 key=lambda p: open(p).readline()[:25])     # by first-line stamp
    for k, lg in enumerate(new):
        txt = open(lg).read()
        hs = sorted(set(HASH.findall(txt)))
        cyc = re.findall(r"Total execution cycles: (\d+)", txt)
        part = name if len(new) == 1 else f"{name}_p{k}"
        dst = os.path.join(LOG_DIR, f"{seq[0]:03d}_{part}__{os.path.basename(lg)}")
        os.rename(lg, dst)
        tr = lg[:-4] + ".trace"
        if os.path.exists(tr):
            os.rename(tr, dst[:-4] + ".trace")
        seq[0] += 1
        h = hs[0] if len(hs) == 1 else ",".join(hs)
        rows.append((part, h, os.path.basename(dst), cyc[-1] if cyc else "?", f"{wall:.1f}"))
        print(f"[kernel] {part} hash={h} log={os.path.basename(dst)} cycles={cyc[-1] if cyc else '?'} wall={wall:.1f}s allclose={ok}", flush=True)
    if not new:
        print(f"[kernel] {name} produced NO log (wall={wall:.1f}s)", flush=True)
    torch._dynamo.reset()
    return out


# ---------------- workload: softmax ----------------
r = torch.randn
# 01_softmax: softmax over the last dim of 1024x1024 (lowers to 3 kernels)
run_kernel("01_softmax", lambda x: torch.softmax(x, dim=-1), r(1024, 1024))
# 02_exp2: elementwise exp2 on 1024x1024 (lowers to CustomVexp)
run_kernel("02_exp2", lambda x: torch.exp2(x), r(1024, 1024))
# ------------------------------------------------------

with open(os.path.join(RAW, "kernels.yaml"), "w") as f:
    for name, h, log, cyc, wall in rows:
        f.write(f"- {{name: {name}, hash: {h}, log: {log}, cycles: {cyc}, wall_s: {wall}}}\n")
print("[done]", flush=True)
