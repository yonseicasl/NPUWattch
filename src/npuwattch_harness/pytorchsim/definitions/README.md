# PyTorchSim harness definitions

The harness has one definition file of its own:

```
vocabulary.yaml     PyTorchSim names -> NPUWattch names (datatype spellings,
                    gem5 instruction classes). Format: manual §3.2.1.
```

The definition files of a **design** are part of the run's input, not part of
the harness. NPUWattch reads them from the run directory (the directory that
contains `togsim_results/`), or from the files you pass on the command line:

| File (fixed name)          | Option                  | Content |
|----------------------------|-------------------------|---------|
| `compound_components.yaml` | `--compound-components` | Hardware structures made of NPUWattch primitives |
| `projection.yaml`          | `--projection`          | PyTorchSim actions -> stim_mode of each compound element |
| `user_components.yaml`     | `--user-components`     | Area and per-action energy of custom blocks |

These files have no built-in defaults, so a run without them stops with an
error. `tutorial/pytorchsim/tpu_like_fp32/` has a complete, working set that
you can copy and edit. The loader is `npuwattch_harness.run_inputs`. The file
formats are in manual §3.7 (compounds and projection) and §3.1.2 (user
components).
