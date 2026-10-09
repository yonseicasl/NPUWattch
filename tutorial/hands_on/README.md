# NPUWattch hands-on notebooks

Five Jupyter notebooks that run the tutorial examples and show you how to read
the results. Open them in order.

| Notebook | What you do | Time |
| --- | --- | --- |
| `00_setup.ipynb` | Check the environment and see how the notebooks work | 2 min |
| `01_pytorchsim_tpu.ipynb` | Run NPUWattch on a PyTorchSim run; read the tree and the messages; change the PE to bf16; look at the native files | 10 min |
| `02_timeloop_eyeriss.ipynb` | Run NPUWattch on a Timeloop mapping of AlexNet; read the windows and the report | 8 min |
| `03_timeloop_gemmini_vs_nvdla.ipynb` | Compare two designs on ResNet-50 and Llama-3-8B; charge a block Timeloop never saw | 8 min |
| `04_your_own_data.ipynb` | Add a block of your own to a run, as a user component and as a compound with its projection; swap in your own DRAM table | 8 min |

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
example, show the tree or the messages, load `report.json` into a table, show
`report.html` inside the notebook.

The background reading is in `../npuwattch_basic/`.
