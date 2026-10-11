# Run manifest: gemma2_9b_prefill

Workload: BRIEF section C1, Gemma-2-9B, one decoder block, prefill pass
(T = 512 tokens). fp32. hidden 3584, 16 q heads, 8 kv heads, head_dim 256,
FFN 14336, GeGLU with `F.gelu(approximate="tanh")`.

| item | value |
| --- | --- |
| image | `ghcr.io/psal-postech/torchsim-tutorial:ispass2026` |
| image digest | `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5` |
| PyTorchSim | git `33ee1c8` in the image, torch 2.8.0, Python 3.11 |
| config (kernels 1-9) | `/workspace/PyTorchSim/configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` (shipped, unchanged; copy in `config.yml` + `core_spad_size_kb: 16384`) |
| config (kernel 10 only) | the same file with `pytorchsim_functional_mode: 0` and absolute ramulator/booksim paths (`_data/probe/c1_booksim_tpuv3_funcoff.yml`). GELU (tanh) crashes Spike with functional mode on; the timing and the energy do not depend on it, only the CPU result check is lost |
| modes | timing 1, functional 1 (kernel 10: 0), autotune on (as shipped), `icnt_type: booksim2` |
| lock timeout | the script sets `PyTorchSimFrontend.extension_codecache.LOCK_TIMEOUT = 14400` at run time (default 600 s). This is a wait time of the compile lock in the frontend; no file of the image is edited and the simulation is unchanged. Without it the FFN kernels fail with a file-lock timeout during autotune |
| script | `run_gemma2_9b.py` (this folder), `prefill main` and `prefill gelu` |
| raw dumps | `../_data/gemma2_9b_prefill_raw2/` (kernels 1-9), `../_data/gemma2_9b_prefill_gelu_raw/` (kernel 10) |
| stdout | `stdout.log` (main), `stdout_gelu.log` (GELU) |
| date | 2026-10-10 15:21 to 23:04 UTC (main, 7 h 43 min; `6_ffn_up_gate` alone 3 h 32 min, `7_ffn_down` 3 h 05 min); GELU 16:56 UTC, 204 s |

One `torch.compile(dynamic=False)` call per kernel, no `TOGSimulator(...)`
context, so every log names exactly one `outputs/<hash>/`. Logs carry a
run-order prefix (`NNN_<kernel>__<orig>.log`). Kernels 1-9 matched the CPU
reference (allclose); kernel 10 ran with functional mode off and has no
check. The GELU log and kernel directory were merged into this root after
the main run. `1_q_proj` and `2_kv_proj` have the same shape (3584 ->
4096) and share a hash. `outputs/<hash>/` holds `meta.txt`,
`m5out/stats.txt`, the kernel `.mlir`, and the tile graph `*_tog.py`.

## Kernels (run order)

| kernel | hash | log | total cycles | wall s |
| --- | --- | --- | --- | --- |
| `1_q_proj` | `hh2rkfm2shc` | `000_1_q_proj__20261010_152145_7502b349.log` | 411821 | 569.2 |
| `2_kv_proj` | `hh2rkfm2shc` | `001_2_kv_proj__20261010_152607_f6b735ae.log` | 415722 | 262.7 |
| `3_attn_qk` | `c5rsqnrhpkg` | `002_3_attn_qk__20261010_153004_f2d72d4e.log` | 100824 | 124.7 |
| `4_attn_av` | `a4wezqhotkh` | `003_4_attn_av__20261010_153218_ea81ace8.log` | 101085 | 133.3 |
| `5_o_proj` | `3r37xjjvm4h` | `004_5_o_proj__20261010_154542_ecbbf446.log` | 316815 | 976.4 |
| `6_ffn_up_gate` | `mmgicjzcmdn` | `005_6_ffn_up_gate__20261010_191739_dcf0442e.log` | 5575632 | 16494.1 |
| `7_ffn_down` | `yw5nznrnirt` | `006_7_ffn_down__20261010_222210_880fb0d4.log` | 2691664 | 9149.3 |
| `8_softmax_p0` | `wrudvhevyxb` | `007_8_softmax_p0__20261010_230019_eb7187ca.log` | 51704 | 316.2 |
| `8_softmax_p1` | `ipbxgx4w6yq` | `008_8_softmax_p1__20261010_230040_36e807f8.log` | 52035 | 316.2 |
| `8_softmax_p2` | `of3ho7cemfo` | `009_8_softmax_p2__20261010_230116_f3850e75.log` | 104817 | 316.2 |
| `9_rmsnorm_p0` | `atgvpmwapjx` | `010_9_rmsnorm_p0__20261010_230337_8ac0baca.log` | 26065 | 154.6 |
| `9_rmsnorm_p1` | `bvkylb47r2w` | `011_9_rmsnorm_p1__20261010_230401_90e25e63.log` | 60682 | 154.6 |
| `10_gelu_mul` | `tbnqdzrcnyv` | `012_10_gelu_mul__20261010_165657_cf1cd59f.log` | 471933 | 204.3 |

Collected on 2026-10-11 with `_data/probe/collect.py` (GELU raw first, then
the main raw, so `config.yml` is the functional-ON config).
