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




def safe_kernel(name, fn, *cpu_inputs, check=True):
    """Run one kernel; on failure record the error and continue."""
    try:
        return run_kernel(name, fn, *cpu_inputs, check=check)
    except Exception as e:   # noqa: BLE001
        import traceback; traceback.print_exc()
        print(f"[kernel] {name} FAILED: {type(e).__name__}: {e}", flush=True)
        rows.append((name, "FAILED", "-", "-", "-"))
        torch._dynamo.reset()


# ---------------- workload: Llama-3-8B one decoder block, decode ----------------
# hidden 4096, 32 q heads, 8 kv heads, head_dim 128, FFN 14336, KV length 512, fp32.
r = torch.randn
T = 1        # tokens in this pass (prefill 512, decode 1)
KV = 512      # key/value length
H, NH, HD, FF = 4096, 32, 128, 14336
print(f"[workload] llama3_8b decode T={T} KV={KV}", flush=True)
# 1_q_proj: GEMM T x 4096 x 4096
safe_kernel("1_q_proj", lambda a, b: torch.matmul(a, b), r(T, H), r(H, H))
# 2_kv_proj: GEMM T x 4096 x 2048 (K and V of 8 kv heads)
safe_kernel("2_kv_proj", lambda a, b: torch.matmul(a, b), r(T, H), r(H, 2048))
# 3_attn_qk: bmm 32 x (T x 128 @ 128 x 512)
safe_kernel("3_attn_qk", lambda q, k: torch.bmm(q, k), r(NH, T, HD), r(NH, HD, KV))
# 4_attn_av: bmm 32 x (T x 512 @ 512 x 128)
safe_kernel("4_attn_av", lambda p, v: torch.bmm(p, v), r(NH, T, KV), r(NH, KV, HD))
# 5_o_proj: GEMM T x 4096 x 4096
safe_kernel("5_o_proj", lambda a, b: torch.matmul(a, b), r(T, H), r(H, H))
# 6_ffn_up_gate: GEMM T x 4096 x 28672 (gate and up fused)
safe_kernel("6_ffn_up_gate", lambda a, b: torch.matmul(a, b), r(T, H), r(H, 2 * FF))
# 7_ffn_down: GEMM T x 14336 x 4096
safe_kernel("7_ffn_down", lambda a, b: torch.matmul(a, b), r(T, FF), r(FF, H))
# 8_softmax: softmax 32 x T x 512 over dim=-1 (lowers to 3 kernels)
safe_kernel("8_softmax", lambda x: torch.softmax(x, dim=-1), r(NH, T, KV))
# 9_rmsnorm: x * rsqrt(mean(x^2) + eps) * w on T x 4096 (lowers to 2 kernels)
safe_kernel("9_rmsnorm", lambda x, w: x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + 1e-5) * w,
           r(T, H), r(H))
# 10_silu_mul: silu(g) * u on T x 14336
safe_kernel("10_silu_mul", lambda g, u: F.silu(g) * u, r(T, FF), r(T, FF))
# ------------------------------------------------------

with open(os.path.join(RAW, "kernels.yaml"), "w") as f:
    for name, h, log, cyc, wall in rows:
        f.write(f"- {{name: {name}, hash: {h}, log: {log}, cycles: {cyc}, wall_s: {wall}}}\n")
print("[done]", flush=True)
