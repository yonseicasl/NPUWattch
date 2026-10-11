# Run manifest: gemma2_9b_decode

Workload: BRIEF section C1, Gemma-2-9B, one decoder block, decode pass
(T = 1 token, KV length 512). fp32. hidden 3584, 16 q heads, 8 kv heads,
head_dim 256, FFN 14336, GeGLU with `F.gelu(approximate="tanh")`.

| item | value |
| --- | --- |
| image | `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` |
| image digest | `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5` (id `d7881046072c`) |
| PyTorchSim | git `33ee1c8` in the image, torch 2.8.0, Python 3.11 |
| config (kernels 1-9) | `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (shipped, unchanged; copy in `config.yml` + `core_spad_size_kb: 16384`) |
| config (kernel 10 only) | `_data/probe/c1_booksim_tpuv3_funcoff.yml` = the same file with `pytorchsim_functional_mode: 0` and absolute ramulator/booksim paths (no other difference) |
| modes | timing 1, functional 1 (kernel 10: 0), autotune on (as shipped), `icnt_type: booksim2` |
| script | `run_gemma2_9b.py` (this folder), `decode main` and `decode gelu` |
| launchers | `_data/probe/run_in_container.sh gemma2_9b_decode_raw2 <c1 config> "run_gemma2_9b.py decode main"`; `run_in_container.sh gemma2_9b_decode_gelu_raw /data/probe/c1_booksim_tpuv3_funcoff.yml "run_gemma2_9b.py decode gelu"` |
| raw dumps | `../_data/gemma2_9b_decode_raw2/` (kernels 1-9), `../_data/gemma2_9b_decode_gelu_raw/` (kernel 10) |
| stdout | `stdout.log` (main), `stdout_gelu.log` (GELU) |
| date | main: 2026-10-10 15:14-16:54 UTC (2026-10-11 00:14-01:54 KST), process wall 99 min 8 s; GELU: 2026-10-10 07:55 UTC, 11 s |

One `torch.compile(dynamic=False)` call per kernel, no `TOGSimulator(...)`
context, so every log names exactly one `outputs/<hash>/`. Logs carry a
run-order prefix (`NNN_<kernel>__<orig>.log`). Every log was checked: line 1
is the TOGSim command line, one `PyTorchSim config:` block follows, the tail
has `Total execution cycles:`. Kernels 1-9 matched the CPU reference
(`allclose=True`). All 10 BRIEF kernels ran (13 windows).

## Per-kernel table

| # | kernel | op / shape | hash | log | total exec cycles | wall (s) |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 1_q_proj | matmul 1x3584 @ 3584x4096 | xejxc5sa4br | 000_1_q_proj__20261010_152001_ef5c1384.log | 179060 | 419.3 |
| 1 | 2_kv_proj | matmul 1x3584 @ 3584x4096 | xejxc5sa4br | 001_2_kv_proj__20261010_152201_71ecc79c.log | 179087 | 119.0 |
| 2 | 3_attn_qk | bmm 16 x (1x256 @ 256x512) | ymiusov62vy | 002_3_attn_qk__20261010_152352_57fe9ef7.log | 27509 | 21.1 |
| 3 | 4_attn_av | bmm 16 x (1x512 @ 512x256) | nh7xrv6o2eu | 003_4_attn_av__20261010_152413_b24ee77f.log | 27477 | 20.8 |
| 4 | 5_o_proj | matmul 1x4096 @ 4096x3584 | p3oqizvg4p6 | 004_5_o_proj__20261010_152931_88857547.log | 178464 | 394.0 |
| 5 | 6_ffn_up_gate | matmul 1x3584 @ 3584x28672 | moq55hp2a3g | 005_6_ffn_up_gate__20261010_161023_e8d652b4.log | 1242039 | 3098.0 |
| 6 | 7_ffn_down | matmul 1x14336 @ 14336x3584 | vm2r6eucy5h | 006_7_ffn_down__20261010_164405_1c0ca856.log | 1049115 | 1809.2 |
| 7 | 8_softmax_p0 | softmax 16x1x512 (amax) | xef3d6mdsn3 | 007_8_softmax_p0__20261010_165300_6a8026e3.log | 904 | 20.4 |
| 8 | 8_softmax_p1 | softmax (sub/exp/sum) | iwflep7gzuf | 008_8_softmax_p1__20261010_165300_7767e347.log | 1304 | 20.4 |
| 9 | 8_softmax_p2 | softmax (div/exp/sub) | 6mtuccoae3f | 009_8_softmax_p2__20261010_165301_f34cacfa.log | 425 | 20.4 |
| 10 | 9_rmsnorm_p0 | rmsnorm 1x3584 (pow_1_mean) | e344xkrl27w | 010_9_rmsnorm_p0__20261010_165338_5131e057.log | 2072 | 38.6 |
| 11 | 9_rmsnorm_p1 | rmsnorm (add_pow_1_mean_rsqrt_mul_mul_1) | f7b6nmjktym | 011_9_rmsnorm_p1__20261010_165339_2fcf75df.log | 412 | 38.6 |
| 12 | 10_gelu_mul | gelu_tanh(g)*u 1x14336 (functional OFF) | r5uw3zsobp5 | 012_10_gelu_mul__20261010_075502_172abbdb.log | 1223 | 4.5 |

`1_q_proj` and `2_kv_proj` have the same shape (3584 -> 4096) and share the
hash `xejxc5sa4br`; their cycle counts differ by TOGSim run-to-run variation
only. Collection: `collect.py` was run on the GELU raw dir first and on the
main raw dir last, so `config.yml` is the functional-ON c1 config that ran
kernels 1-9.

## Deviations

1. **Runtime change in the script:** `PyTorchSimFrontend.extension_codecache.LOCK_TIMEOUT`
   is set to 14400 s (image default 600 s) at the top of the script, before
   any kernel runs (as in `run_llama3_8b_prefill.py`). No file in the image
   was edited. Reason: the first decode attempt (`_data/gemma2_9b_decode_raw`,
   kept, not used) lost `6_ffn_up_gate` to
   `InductorError: Timeout: The file lock '.../outputs/udajqw22lh6/.compile.lock' could not be acquired`
   during autotune. With the larger value no kernel failed. The value
   changes only how long a frontend thread waits for a lock; it does not
   change any simulation setting or the autotune candidate timeout.
2. **GELU functional-off exception:** `10_gelu_mul` ran with
   `pytorchsim_functional_mode: 0` (`c1_booksim_tpuv3_funcoff.yml`), because
   Spike does not execute the custom vtanh instruction ("An illegal
   instruction was executed!", PROBE_REPORT section 4). The output is not
   computed, so there is no CPU check (`allclose=None`). Timing, gem5 stats
   and the tile graph are produced as usual. So this root mixes two configs
   that differ only in the functional-mode flag (and absolute paths); the
   timing model is identical.
3. The decode GELU log is reused from `_data/gemma2_9b_decode_gelu_raw`
   (2026-10-10 07:55 UTC, exit 0, an earlier run by the previous agent).
   That run used the same script without the LOCK_TIMEOUT lines; the
   kernel is small and not affected by that setting.
4. Host load: this process ran at the same time as the gemma2 prefill main
   process and the llama3_8b_decode `6_ffn_up_gate` rerun container
   (15:14-16:11 UTC); wall times are
   for a shared host.

## NPUWattch

`out/console.txt`, `out/report.{html,json}`; run with
`./run.sh <this root> --node 7nm --report <this root>/out/` and the three
tutorial yamls from `NPUWattch/tutorial/pytorchsim/tpu_like_fp32/`.
Total 3.961e+10 pJ (dyn 3.879e+10 + leak 8.151e+08), 3.074 ms;
dram_chan 3.499e+10 pJ = 88.3 % of total. GEMM windows 3.953e+10 pJ,
non-GEMM 7.821e+07 pJ (0.2 %). 0 CRITICAL, 0 ERROR, 16 WARNING
(NW-6201 x6, NW-6208 x3, NW-6607 x3, NW-8212 x3, NW-8111 x1), 40 INFO.
