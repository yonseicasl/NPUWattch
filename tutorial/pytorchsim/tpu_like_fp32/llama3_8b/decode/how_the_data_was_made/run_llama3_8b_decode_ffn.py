"""Rerun of one kernel of the Llama-3-8B decode root: 6_ffn_up_gate only.

The first decode run (run_llama3_8b_decode.py, 2026-10-10) lost this kernel to
the 600 s frontend compile-lock timeout. This script uses the same run_kernel
logic and the same tensor shapes, and raises LOCK_TIMEOUT at run time (as in
run_llama3_8b_prefill.py). The image and the simulation are not changed.

The log gets the run-order prefix 004a, so that it sorts after
004_5_o_proj and before 005_7_ffn_down in the merged root.

Run INSIDE the container (see probe/run_in_container.sh). Environment:
  TOGSIM_CONFIG, TORCHSIM_DUMP_PATH (<raw>/outputs), TORCHSIM_LOG_PATH.
"""
import glob, os, re, time
import torch
# Runtime-only change (no source edit): the frontend file-lock wait LOCK_TIMEOUT
# is 600 s in the image. Large-GEMM autotune candidates run longer than that.
import PyTorchSimFrontend.extension_codecache as _ecc
_ecc.LOCK_TIMEOUT = 14400
print(f"[setup] extension_codecache.LOCK_TIMEOUT = {_ecc.LOCK_TIMEOUT}", flush=True)

LOG_DIR = os.environ["TORCHSIM_LOG_PATH"]
RAW = os.path.dirname(LOG_DIR)
dev = torch.device("npu:0")
torch.manual_seed(0)
HASH = re.compile(r"tog_path: \S*/outputs/([A-Za-z0-9]+)/")
rows = []          # kernels.yaml rows
PREFIX = "004a"    # run-order prefix in the merged decode root


def run_kernel(name, fn, *cpu_inputs, check=True):
    """Compile fn alone, run it on npu:0, rename its log(s) <PREFIX>_<name>[_pK]__*.log."""
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
        pre = PREFIX if len(new) == 1 else f"{PREFIX}{k}"
        dst = os.path.join(LOG_DIR, f"{pre}_{part}__{os.path.basename(lg)}")
        os.rename(lg, dst)
        tr = lg[:-4] + ".trace"
        if os.path.exists(tr):
            os.rename(tr, dst[:-4] + ".trace")
        h = hs[0] if len(hs) == 1 else ",".join(hs)
        rows.append((part, h, os.path.basename(dst), cyc[-1] if cyc else "?", f"{wall:.1f}"))
        print(f"[kernel] {part} hash={h} log={os.path.basename(dst)} cycles={cyc[-1] if cyc else '?'} wall={wall:.1f}s allclose={ok}", flush=True)
    if not new:
        print(f"[kernel] {name} produced NO log (wall={wall:.1f}s)", flush=True)
    torch._dynamo.reset()
    return out


# ---------------- Llama-3-8B decode, kernel 6 only ----------------
r = torch.randn
T = 1
H, FF = 4096, 14336
print(f"[workload] llama3_8b decode T={T}: 6_ffn_up_gate only", flush=True)
# 6_ffn_up_gate: GEMM T x 4096 x 28672 (gate and up fused)
run_kernel("6_ffn_up_gate", lambda a, b: torch.matmul(a, b), r(T, H), r(H, 2 * FF))

with open(os.path.join(RAW, "kernels.yaml"), "w") as f:
    for name, h, log, cyc, wall in rows:
        f.write(f"- {{name: {name}, hash: {h}, log: {log}, cycles: {cyc}, wall_s: {wall}}}\n")
print("[done]", flush=True)
