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


def harvest(names, before, wall):
    """Rename the new logs in run order to NNN_<names[k]>__*.log."""
    new = sorted(set(glob.glob(os.path.join(LOG_DIR, "*.log"))) - before,
                 key=lambda p: open(p).readline()[:25])
    if len(new) != len(names):
        print(f"[warn] expected {len(names)} logs, got {len(new)}", flush=True)
        names = [f"k{k}" for k in range(len(new))]
    for part, lg in zip(names, new):
        txt = open(lg).read()
        hs = sorted(set(HASH.findall(txt)))
        cyc = re.findall(r"Total execution cycles: (\d+)", txt)
        dst = os.path.join(LOG_DIR, f"{seq[0]:03d}_{part}__{os.path.basename(lg)}")
        os.rename(lg, dst)
        tr = lg[:-4] + ".trace"
        if os.path.exists(tr):
            os.rename(tr, dst[:-4] + ".trace")
        seq[0] += 1
        h = hs[0] if len(hs) == 1 else ",".join(hs)
        rows.append((part, h, os.path.basename(dst), cyc[-1] if cyc else "?", f"{wall:.1f}"))
        print(f"[kernel] {part} hash={h} log={os.path.basename(dst)} cycles={cyc[-1] if cyc else '?'} wall={wall:.1f}s", flush=True)


# ---------------- workload: matmul_train ----------------
# fwd: c = a @ b (1024^3); backward via autograd of c.sum():
#   grad_a = g @ b^T, grad_b = a^T @ g (g = ones(1024,1024)).
# Autograd emits the backward GEMMs as mm_1 / mm_2; which is which is
# decided after the run from outputs/<hash>/meta.txt. Logs are first named
# fwd / bwd_mm_1 / bwd_mm_2 here (run order).
a_c, b_c = torch.randn(1024, 1024), torch.randn(1024, 1024)
a = a_c.clone().to(dev).requires_grad_()
b = b_c.clone().to(dev).requires_grad_()
before = set(glob.glob(os.path.join(LOG_DIR, "*.log")))
t0 = time.time()
opt = torch.compile(dynamic=False)(lambda x, y: x @ y)
c = opt(a, b)
t1 = time.time()
harvest(["fwd"], before, t1 - t0)
before = set(glob.glob(os.path.join(LOG_DIR, "*.log")))
c.sum().backward()
harvest(["bwd_mm_1", "bwd_mm_2"], before, time.time() - t1)
ac, bc = a_c.clone().requires_grad_(), b_c.clone().requires_grad_()
(ac @ bc).sum().backward()
print("[check] fwd allclose =", torch.allclose(c.detach().cpu(), (a_c @ b_c), rtol=1e-2, atol=1e-2),
      " grad_a allclose =", torch.allclose(a.grad.cpu(), ac.grad, rtol=1e-2, atol=1e-2),
      " grad_b allclose =", torch.allclose(b.grad.cpu(), bc.grad, rtol=1e-2, atol=1e-2), flush=True)
# ------------------------------------------------------

with open(os.path.join(RAW, "kernels.yaml"), "w") as f:
    for name, h, log, cyc, wall in rows:
        f.write(f"- {{name: {name}, hash: {h}, log: {log}, cycles: {cyc}, wall_s: {wall}}}\n")
print("[done]", flush=True)
