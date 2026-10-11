# Run manifest: llama3_8b_prefill

Workload: BRIEF section B2, Llama-3-8B, one decoder block, prefill pass
(T = 512 tokens, KV length 512). fp32. hidden 4096, 32 q heads, 8 kv heads,
head_dim 128, FFN 14336.

| item | value |
| --- | --- |
| image | `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` |
| image digest | `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5` (id `d7881046072c`) |
| PyTorchSim | git `33ee1c8` in the image, torch 2.8.0, Python 3.11 |
| config | `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (shipped, unchanged; copy in `config.yml` + `core_spad_size_kb: 16384`) |
| modes | timing 1, functional 1, autotune on (as shipped), `icnt_type: booksim2` |
| script | `run_llama3_8b_prefill.py` (this folder) |
| launcher | `_data/probe/run_in_container.sh llama3_8b_prefill_raw <config> run_llama3_8b_prefill.py` |
| raw dump | `../_data/llama3_8b_prefill_raw/` |
| date | 2026-10-10, container 08:57-13:31 UTC, process wall 274 min |

One `torch.compile(dynamic=False)` call per kernel, no `TOGSimulator(...)`
context, so every log names exactly one `outputs/<hash>/`. Logs carry a
run-order prefix (`NNN_<kernel>__<orig>.log`). All outputs matched the CPU
reference (`allclose=True`). All 10 BRIEF kernels ran (13 windows).

## Per-kernel table

| # | kernel | op / shape | hash | log | total exec cycles | wall (s) |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 1_q_proj | matmul 512x4096 @ 4096x4096 | kkakzpc7ouf | 000_1_q_proj__20261010_091120_1518a77d.log | 345779 | 982.8 |
| 1 | 2_kv_proj | matmul 512x4096 @ 4096x2048 | 5yfaq3xx6py | 001_2_kv_proj__20261010_092008_d8076b96.log | 173832 | 451.8 |
| 2 | 3_attn_qk | bmm 32 x (512x128 @ 128x512) | vt7mvihotlc | 002_3_attn_qk__20261010_092314_96f2e896.log | 152117 | 168.6 |
| 3 | 4_attn_av | bmm 32 x (512x512 @ 512x128) | as2djgi5uoy | 003_4_attn_av__20261010_092555_5826847c.log | 151557 | 167.9 |
| 4 | 5_o_proj | matmul 512x4096 @ 4096x4096 | kkakzpc7ouf | 004_5_o_proj__20261010_093445_961bd545.log | 326832 | 611.9 |
| 5 | 6_ffn_up_gate | matmul 512x4096 @ 4096x28672 | ocbjyihxqcr | 005_6_ffn_up_gate__20261010_120750_cf869d2c.log | 3267126 | 10690.5 |
| 6 | 7_ffn_down | matmul 512x14336 @ 14336x4096 | edpnz5zxm52 | 006_7_ffn_down__20261010_130157_494775f0.log | 1716468 | 2236.7 |
| 7 | 8_softmax_p0 | softmax 32x512x512 (amax) | p6ns2wv23j7 | 007_8_softmax_p0__20261010_132108_eb7a1f85.log | 101862 | 697.2 (3 parts) |
| 8 | 8_softmax_p1 | softmax (sub/exp/sum) | ebph2z2udbs | 008_8_softmax_p1__20261010_132145_fa6a509d.log | 102603 | ″ |
| 9 | 8_softmax_p2 | softmax (div/exp/sub) | xnvbb47zx4g | 009_8_softmax_p2__20261010_132251_809420fe.log | 216312 | ″ |
| 10 | 9_rmsnorm_p0 | rmsnorm 512x4096 (mean of x^2) | oe6sjnczkyb | 010_9_rmsnorm_p0__20261010_132614_a36783c9.log | 27692 | 175.5 (2 parts) |
| 11 | 9_rmsnorm_p1 | rmsnorm (rsqrt, mul) | or4ewbsiolc | 011_9_rmsnorm_p1__20261010_132634_6758645d.log | 81227 | ″ |
| 12 | 10_silu_mul | silu(g)*u 512x14336 | h2bv5y2jv6s | 012_10_silu_mul__20261010_133022_b9897a4a.log | 428866 | 253.5 |

`1_q_proj` and `5_o_proj` have the same shape and share the hash
`kkakzpc7ouf`, but their cycle counts differ (345779 vs 326832, -5.5 %).
Both are final TOGSim runs of the same compiled kernel in one process; the
difference is TOGSim run-to-run variation, not a different tiling.

## Deviations

1. **Runtime change in the script:** `PyTorchSimFrontend.extension_codecache.LOCK_TIMEOUT`
   is set to 14400 s (image default 600 s) at the top of the script, before
   any kernel runs. No source file in the image was edited. Reason: the
   decode run lost `6_ffn_up_gate` to a 600 s `.compile.lock` Timeout during
   autotune (see `../llama3_8b_decode/RUN_MANIFEST.md`). With the larger
   value, no kernel failed. The value changes only how long a frontend thread
   waits for a lock; it does not change any simulation setting or the
   autotune candidate timeout (baseline wall + 15 s).
2. This process started while the decode process was still running its
   `7_ffn_down` kernel (one decode + one prefill process at the same time).
3. Wall time: `6_ffn_up_gate` took 2 h 58 min (autotune ~60 min, Spike
   functional simulation ~89 min with 64 GB RSS, final TOGSim ~25 min), on a
   shared host (load average 8-38). Whole process 4 h 34 min.

## NPUWattch

`out/console.txt`, `out/report.{html,json}`; run with
`./run.sh <this root> --node 7nm --report <this root>/out/` and the three
tutorial yamls from `NPUWattch/tutorial/pytorchsim/tpu_like_fp32/`.
Total 6.905e+11 pJ (dyn 6.885e+11 + leak 2.001e+09), 7.545 ms;
dram_chan 8.062e+10 pJ = 11.7 % of total. 0 ERROR, 14 WARNING.
