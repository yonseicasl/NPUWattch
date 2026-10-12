# NPUWattch hands-on notebooks

Six Jupyter notebooks that run the tutorial examples and show you how to read
the results. Open them in order.

| Notebook | The machine | What you do | Time |
| --- | --- | --- | --- |
| `00_setup.ipynb` | | Check the environment and see how the notebooks work | 2 min |
| `01_pytorchsim_tpu.ipynb` | TPU-like NPU: 2 arrays of 128×128 PEs, 16 MB scratchpad, HBM2 | Run NPUWattch on a PyTorchSim run; read the tree and the messages; change the PE to bf16; look at the native files | 10 min |
| `02_pytorchsim_workloads.ipynb` | the same TPU-like NPU, and a 2-core version | Run the other PyTorchSim workloads and explain each result: a training step, one vs. two cores, kernels without a MAC, ResNet-50 at 1.2% array occupancy, and three LLM decoder blocks in prefill and decode | 12 min |
| `03_timeloop_eyeriss.ipynb` | Eyeriss-like: 14×12 PEs, 128 KB global buffer, LPDDR4 | Run NPUWattch on a Timeloop mapping of AlexNet; read the windows and the report | 8 min |
| `04_timeloop_gemmini_vs_nvdla.ipynb` | Gemmini-like: 16×16 PEs, 320 KB of buffers. NVDLA-like: 8×8 MACs, 65 KB of buffers. Both LPDDR4 | Compare two designs on ResNet-50 and Llama-3-8B, and next to the TPU-like run of notebook 2; charge a block Timeloop never saw | 8 min |
| `05_your_own_data.ipynb` | the designs of notebooks 1, 3, and 4 | Add a block of your own to a run, as a user component and as a compound with its projection; swap in your own DRAM table | 8 min |

Every run prints a `Machine:` line next to its results (node, clock, MAC
units and peak rate, on-chip memories, DRAM), and every result table has a
`time` and a `MAC util %` column, so a number is never far from the hardware
it belongs to.

Every notebook has been run once and keeps its output, so you can read along
without running anything. Every example folder also contains the report of a
7 nm run in `out/`.

## Running them

```bash
cd NPUWattch && pip install -e .
pip install jupyter pandas matplotlib
jupyter lab tutorial/hands_on
```

The notebooks run the examples in `../timeloop/` and `../pytorchsim/` in
place. They write a few extra files next to the examples (`native/`,
`out_*/`, `out/console*.txt`) and a `work/` folder here, all ignored by git.

`tutorial_helpers.py` holds the small functions the notebooks call: run an
example, show the tree, the messages or the message summary, explain a
message code, load `report.json` into a table, show `report.html` inside the
notebook.

The background reading is in `../npuwattch_basic/`.
