# PyTorchSim examples

One PyTorchSim run (a 1024×1024×1024 float32 `torch.matmul` on a TPUv3-like
NPU), modeled with two different hardware models. Each example is a folder with
a `./run` script.

```
pytorchsim/
├── tpu_like_fp32/       fp32 PEs: the PE follows the kernel dtype (the basic example)
└── tpu_like_bf16/       bf16 PEs: the PE is fixed in compound_components.yaml
```

```bash
cd tpu_like_fp32 && ./run
cd tpu_like_bf16 && ./run
```

The two folders have the same simulator files. Only `compound_components.yaml`
is different. The simulator run is float32, so the bf16 datapath of a real TPU
is set in the hardware model.
<!-- Internal note: PyTorchSim cannot simulate bf16 or fp16 kernels, so the
bf16 datapath comes from the hardware model, not from the run. -->

| | `tpu_like_fp32` | `tpu_like_bf16` |
| --- | --- | --- |
| Systolic PE | `fpmac` e8m23 (from the kernel MLIR) | `fpmac` e8m7 (fixed) |
| Weight register | 32 bits | 16 bits |
| Vector unit | fp32 | fp32 |
| Energy at 7nm | 6.13 mJ | 2.29 mJ |
| pJ/FLOP (DRAM included) | 2.86 | 1.07 |

Start with `tpu_like_fp32/README.md`. It explains each file and each console
message in detail. `tpu_like_bf16/README.md` explains how the PE is set to bf16
and which numbers carry over from the float32 run.
