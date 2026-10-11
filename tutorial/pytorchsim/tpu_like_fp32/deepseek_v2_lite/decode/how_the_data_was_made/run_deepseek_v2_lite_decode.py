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


# ---------------- workload ----------------
# DeepSeek-V2-Lite, one MoE decoder block, DECODE T=1, KV length 512 (BRIEF C2).
# top-6 routing: 6 active experts x 1 token each.
# Routing itself is not simulated; the router GEMM (7_router) is.
r = torch.randn
T, KV, NE, TPE = 1, 512, 6, 1
H, D_QK, D_V = 16, 192, 128
mm = lambda a, b: torch.matmul(a, b)
bmm = lambda a, b: torch.bmm(a, b)
# 1_q_proj: T x 2048 @ 2048 x 3072 (16 heads x 192, no q LoRA in Lite)
run_kernel("1_q_proj", mm, r(T, 2048), r(2048, 3072))
# 2_kv_a_proj: T x 2048 @ 2048 x 576 (kv_lora 512 + rope 64)
run_kernel("2_kv_a_proj", mm, r(T, 2048), r(2048, 576))
# 3_kv_b_proj: T x 512 @ 512 x 4096 (16 x (128 nope + 128 v))
run_kernel("3_kv_b_proj", mm, r(T, 512), r(512, 4096))
# 4_attn_qk: bmm 16 x (T x 192 @ 192 x KV)
run_kernel("4_attn_qk", bmm, r(H, T, D_QK), r(H, D_QK, KV))
# 5_attn_av: bmm 16 x (T x KV @ KV x 128)
run_kernel("5_attn_av", bmm, r(H, T, KV), r(H, KV, D_V))
# 6_o_proj: T x 2048 @ 2048 x 2048
run_kernel("6_o_proj", mm, r(T, 2048), r(2048, 2048))
# 7_router: T x 2048 @ 2048 x 64
run_kernel("7_router", mm, r(T, 2048), r(2048, 64))
# 8_experts_up_gate: bmm NE x (TPE x 2048 @ 2048 x 2816)
run_kernel("8_experts_up_gate", bmm, r(NE, TPE, 2048), r(NE, 2048, 2816))
# 9_experts_down: bmm NE x (TPE x 1408 @ 1408 x 2048)
run_kernel("9_experts_down", bmm, r(NE, TPE, 1408), r(NE, 1408, 2048))
# 10_shared_up_gate: T x 2048 @ 2048 x 5632 (2 shared experts)
run_kernel("10_shared_up_gate", mm, r(T, 2048), r(2048, 5632))
# 11_shared_down: T x 2816 @ 2816 x 2048
run_kernel("11_shared_down", mm, r(T, 2816), r(2816, 2048))
# 12_softmax: 16 x T x KV, dim=-1 (lowers to 3 kernels -> _p0.._p2)
run_kernel("12_softmax", lambda x: torch.softmax(x, dim=-1), r(H, T, KV))
# 13_rmsnorm: x * rsqrt(mean(x^2) + eps) * w on T x 2048 (lowers to 2 kernels -> _p0, _p1)
run_kernel("13_rmsnorm", lambda x, w: x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + 1e-6) * w,
           r(T, 2048), r(2048))
# 14_silu_mul: silu(g) * u on T x 1408
run_kernel("14_silu_mul", lambda g, u: F.silu(g) * u, r(T, 1408), r(T, 1408))
# ------------------------------------------

with open(os.path.join(RAW, "kernels.yaml"), "w") as f:
    for name, h, log, cyc, wall in rows:
        f.write(f"- {{name: {name}, hash: {h}, log: {log}, cycles: {cyc}, wall_s: {wall}}}\n")
print("[done]", flush=True)
