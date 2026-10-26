# Run manifest — matmul_1024 (bf16)

| Item | Value |
| --- | --- |
| Date | 2026-10-26 |
| Image | `ghcr.io/psal-postech/torchsim-tutorial:ispass2026`, image id `d7881046072c`, digest `sha256:018667ac8958fbcd4fdee4bceeb2918f1b3e1dcc6a2d47cb62b4262bceabaac5` |
| PyTorchSim | v1.1.0 as shipped in the image (`/workspace/PyTorchSim`, commit `33ee1c8`, `git describe`: `v1.0.1-213-g33ee1c8`, 2026-05-07) |
| Container runtime | rootless podman, `--security-opt label=disable` |
| Config | the shipped `configs/systolic_ws_128x128_c1_booksim_tpuv3.yml` with two edits: `pytorchsim_functional_mode: 1` → `0`, and the relative `../configs/` paths written as absolute paths. `../config.yml` is the file as used |
| Workload | `run_matmul_1024_bf16.py` with `DTYPE=bf16 SIZE=1024`: one `torch.compile(dynamic=False)(torch.matmul)` call on two 1024×1024 `torch.bfloat16` tensors |
| Output | kernel hash `5affeun55ak`, log `20261026_033150_db59ff91.log`, 45 195 cycles, 131 072 DRAM reads + 65 536 writes of 32 B |
| Control | the same patched toolchain with `DTYPE=fp32`: kernel hash `fqywo6ndalo` (the hash of the shipped fp32 example) and 52 135 cycles against the shipped example's 52 022 (0.2%) |

## Why the toolchain needed patches

The image compiles a bf16 kernel through MLIR → LLVM IR → `llc` (RISC-V with
the VCIX extension) → gem5 for the sample program, and TOGSim replays the
tile graph. Three things broke on the way to gem5. None of them is in TOGSim
or in the tile graph.

1. **`llc` had no bf16 vector features.** It stopped with "Do not know how to
   split the result of this operator". Fix: `-mattr` gets `+zvfbfmin,+zvfbfwma`.
2. **gem5 cannot decode the scalarized bf16 vector add.** The VCIX lowering
   accumulates the systolic pops with `fadd <N x bfloat>`. LLVM has no bf16
   vector add and scalarizes it through Zfbfmin `fcvt.s.bf16` instructions,
   which gem5 rejects ("Unknown instruction"). Fix: `patch/mlir_translate_bf16.py`
   runs the real `mlir-translate` and then rewrites every bf16 vector `fadd`
   in the LLVM IR into an f32 add on bit-extended operands (bf16 is the upper
   half of f32) with round-to-nearest-even back to bf16. It also turns bf16
   masked loads and stores into i16 ones; the scalarized bf16 masked loads
   had cost 3× in cycles.
3. **gem5 rejects `vnsrl.wi` under LMUL 8.** With the default fixed-length
   vector lowering the narrowing shift follows an `e16, m8` `vsetvli`, and
   gem5 stops with "LMUL=8 is illegal". Fix: `-riscv-v-fixed-length-vector-lmul-max=4`.

`patch/extension_codecache.diff` applies fixes 1 and 3 to the three `llc`
calls of `PyTorchSimFrontend/extension_codecache.py` and routes its two
`mlir-translate` calls through the wrapper. The patched file was bind-mounted
over the image's copy. The image itself was not changed.

## How it was run

```bash
D=<work dir>            # holds run_matmul_1024_bf16.py (as run_mm.py), patch/, cfg/, and the output folders
podman run --rm --security-opt label=disable -v $D:/data \
  -v $D/patch/extension_codecache.py:/workspace/PyTorchSim/PyTorchSimFrontend/extension_codecache.py \
  -e DTYPE=bf16 -e SIZE=1024 \
  -e TOGSIM_CONFIG=/data/cfg/systolic_ws_128x128_c1_booksim_tpuv3_fn0.yml \
  -e TORCHSIM_DUMP_PATH=/data/mm1024_bf16/outputs -e TORCHSIM_LOG_PATH=/data/mm1024_bf16/togsim_results \
  ghcr.io/psal-postech/torchsim-tutorial:ispass2026 \
  bash -lc 'cd /workspace/PyTorchSim && python /data/run_mm.py'
```

The wrapper is called at `/data/patch/mlir_translate_bf16.py` inside the
container, so the work dir must be mounted at `/data`. `TORCHSIM_DUMP_PATH`
must end in `outputs`. The `cfg/` file is the shipped config with the two
edits above (the launch script of the run wrote it with `sed` on first use).

## What was checked

- The run completes in timing mode and TOGSim prints one kernel.
- The fp32 control with the same patched toolchain reproduces the shipped
  fp32 example's kernel hash and its cycle count within 0.2%.
- `meta.txt` shows `torch.bfloat16` operands and output; the DRAM requests
  are half of the fp32 run's (2-byte operands).
- NPUWattch reads the run without changes to the harness.

## What was not checked

- **The numerical result.** The functional mode was off: Spike's systolic
  model in this image computes in float only, so a bf16 functional run is not
  possible. The cycle counts, the traffic, and the instruction counts are
  what the simulator produced for the bf16 kernel.
- **The cost of the vector-add rewrite in cycles.** The rewritten add is a
  few more vector instructions per accumulation step in the sample program
  that gem5 times. It is the only arithmetic that differs from what an
  unpatched toolchain would emit for bf16, had it compiled.
