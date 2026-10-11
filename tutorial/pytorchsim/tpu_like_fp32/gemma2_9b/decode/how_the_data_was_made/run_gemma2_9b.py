"""Gemma-2-9B one decoder block (BRIEF C1), fp32. Usage:
  python run_gemma2_9b.py <prefill|decode> <main|gelu>
main = kernels 1-9 (functional ON c1 config); gelu = kernel 10 only
(run with the functional-OFF config, check=False, own raw dir).
One TOGSim log per compiled kernel.

Run INSIDE the container (see run_in_container.sh). Environment (set by the
launcher, never inside this script):
  TOGSIM_CONFIG       absolute path of the run config (.yml)
  TORCHSIM_DUMP_PATH  <raw>/outputs          (dir name MUST be 'outputs')
  TORCHSIM_LOG_PATH   <raw>/togsim_results
Do NOT wrap calls in `with TOGSimulator(...)`: that streams all kernels into
one TOGSim process (one log for many kernels, and the log goes to stdout).
"""
import glob, os, re, sys, time
import torch
import torch.nn.functional as F
# Runtime-only change (no source edit): the frontend file-lock wait LOCK_TIMEOUT
# is 600 s in the image. Large-GEMM autotune candidates run longer than that,
# and a second candidate with the same hash then fails with a lock Timeout.
import PyTorchSimFrontend.extension_codecache as _ecc
_ecc.LOCK_TIMEOUT = 14400
print(f"[setup] extension_codecache.LOCK_TIMEOUT = {_ecc.LOCK_TIMEOUT}", flush=True)

LOG_DIR = os.environ["TORCHSIM_LOG_PATH"]
RAW = os.path.dirname(LOG_DIR)
dev = torch.device("npu:0")
torch.manual_seed(0)
HASH = re.compile(r"tog_path: \S*/outputs/([A-Za-z0-9]+)/")
rows = []          # kernels.yaml rows
seq = [0]


def _run_kernel(name, fn, *cpu_inputs, check=True):
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


def run_kernel(name, fn, *cpu_inputs, check=True):
    """Run one kernel; on failure print the error, record it, and continue."""
    import traceback
    try:
        return _run_kernel(name, fn, *cpu_inputs, check=check)
    except Exception as e:
        traceback.print_exc()
        print(f"[kernel] {name} FAILED: {type(e).__name__}: {e}", flush=True)
        rows.append((name, "FAILED", "-", "-", "-"))
        torch._dynamo.reset()


# ---------------- workload: Gemma-2-9B block ----------------
PHASE, PART = sys.argv[1], sys.argv[2]
H, NQ, NKV, HD, FFN, KV = 3584, 16, 8, 256, 14336, 512
T = 512 if PHASE == "prefill" else 1
r = torch.randn
print(f"[cfg] phase={PHASE} part={PART} T={T} KV={KV} TOGSIM_CONFIG={os.environ.get('TOGSIM_CONFIG')}", flush=True)
if PART == "main":
    # 1_q_proj: T x 3584 @ 3584 x 4096 (16 heads x 256)
    run_kernel("1_q_proj", lambda a, b: torch.matmul(a, b), r(T, H), r(H, NQ * HD))
    # 2_kv_proj: T x 3584 @ 3584 x 4096 (K and V, 8 kv heads x 256 each)
    run_kernel("2_kv_proj", lambda a, b: torch.matmul(a, b), r(T, H), r(H, 2 * NKV * HD))
    # 3_attn_qk: 16 x (T x 256 @ 256 x 512)
    run_kernel("3_attn_qk", lambda q, kt: torch.bmm(q, kt), r(NQ, T, HD), r(NQ, HD, KV))
    # 4_attn_av: 16 x (T x 512 @ 512 x 256)
    run_kernel("4_attn_av", lambda p, v: torch.bmm(p, v), r(NQ, T, KV), r(NQ, KV, HD))
    # 5_o_proj: T x 4096 @ 4096 x 3584
    run_kernel("5_o_proj", lambda a, b: torch.matmul(a, b), r(T, NQ * HD), r(NQ * HD, H))
    # 6_ffn_up_gate: T x 3584 @ 3584 x 28672 (gate + up)
    run_kernel("6_ffn_up_gate", lambda a, b: torch.matmul(a, b), r(T, H), r(H, 2 * FFN))
    # 7_ffn_down: T x 14336 @ 14336 x 3584
    run_kernel("7_ffn_down", lambda a, b: torch.matmul(a, b), r(T, FFN), r(FFN, H))
    # 8_softmax: 16 x T x 512, dim=-1 (lowers to 3 kernels)
    run_kernel("8_softmax", lambda x: torch.softmax(x, dim=-1), r(NQ, T, KV))
    # 9_rmsnorm: x * rsqrt(mean(x^2) + eps) * w, T x 3584 (lowers to 2 kernels)
    run_kernel("9_rmsnorm",
               lambda x, w: x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + 1e-6) * w,
               r(T, H), r(H))
else:
    # 10_gelu_mul: gelu_tanh(g) * u, T x 14336. Spike cannot execute vtanh, so
    # this runs with pytorchsim_functional_mode: 0 (no CPU result check).
    seq[0] = 12   # run-order prefix after kernel 9 (main part writes logs 000-011)
    run_kernel("10_gelu_mul", lambda g, u: F.gelu(g, approximate="tanh") * u,
               r(T, FFN), r(T, FFN), check=False)
# ------------------------------------------------------

with open(os.path.join(RAW, "kernels.yaml"), "w") as f:
    for name, h, log, cyc, wall in rows:
        f.write(f"- {{name: {name}, hash: {h}, log: {log}, cycles: {cyc}, wall_s: {wall}}}\n")
print("[done]", flush=True)
