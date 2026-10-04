# PyTorchSim harness definitions

The harness keeps one definition file of its own:

```
vocabulary.yaml     PyTorchSim names -> NPUWattch names (datatype spellings,
                    gem5 instruction classes). Format: manual §3.2.1.
```

The definitions of a **design** are inputs of a run, not part of the harness.
NPUWattch reads them from the run directory (the directory that contains
`togsim_results/`), or from the files you give on the command line:

| File (fixed name)          | Option                  | Content |
|----------------------------|-------------------------|---------|
| `compound_components.yaml` | `--compound-components` | hardware structures made of NPUWattch primitives |
| `projection.yaml`          | `--projection`          | PyTorchSim actions -> stim_mode of each compound element |
| `user_components.yaml`     | `--user-components`     | area and action energies of blocks NPUWattch has no model for |

There is no default inside NPUWattch: a run without these files stops with an
error. `tutorial/pytorchsim/` holds a complete, working set to copy and edit.
The loader is `npuwattch_harness.run_inputs`; the formats are in manual §3.7
(compounds and projection) and §3.1.2 (user components).
