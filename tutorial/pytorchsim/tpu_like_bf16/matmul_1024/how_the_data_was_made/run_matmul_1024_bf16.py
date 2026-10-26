"""One NxNxN matmul (DTYPE, SIZE) through PyTorchSim: one torch.compile call, one TOGSim log; prints a kernels.yaml row."""
import glob, os, re, time, torch
dt = {"fp32": torch.float32, "bf16": torch.bfloat16}[os.environ["DTYPE"]]
N = int(os.environ.get("SIZE", "1024"))
LOG_DIR = os.environ["TORCHSIM_LOG_PATH"]
dev = torch.device("npu:0")
torch.manual_seed(0)
a = torch.randn(N, N, dtype=dt); b = torch.randn(N, N, dtype=dt)
t0 = time.time()
out = torch.compile(dynamic=False)(torch.matmul)(a.to(dev), b.to(dev))
wall = time.time() - t0
logs = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))
for lg in logs:
    txt = open(lg).read()
    cyc = re.findall(r"Total execution cycles: (\d+)", txt)
    hs = sorted(set(re.findall(r"/outputs/([A-Za-z0-9]+)/", txt)))
    print(f"[kernels.yaml] - {{name: matmul_{N}, hash: {hs[0] if hs else '?'}, log: {os.path.basename(lg)}, cycles: {cyc[-1] if cyc else '?'}}}", flush=True)
print(f"[run] dtype={dt} N={N} wall={wall:.0f}s out.dtype={out.dtype}", flush=True)
