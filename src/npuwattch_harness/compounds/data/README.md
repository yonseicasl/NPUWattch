# Compound interpreter — system data

This directory holds **system files** for the compound interpreter (the engine
in `../loader.py` that loads, validates, and resolves compounds). These files
are NPUWattch internals. Users don't write them.

```
primitive_modes.json    the stim_mode vocabulary CONTRACT — do not edit by hand
```

`primitive_modes.json` mirrors the characterized
`dataset_gen/logic/autosweep/sweep_spec.POWER_MODES`. It lists every
`(primitive, stim_mode)` pair that the trained models cover, and the loader
rejects any projection that uses a pair not in this list. The file is JSON
because it's a machine-checked contract, not a hand-written sample. We plan to
generate it automatically from `POWER_MODES`.

The **harness definitions** that users read, copy, and edit (the compound
component lists and the per-tool projections) live with each harness instead,
for example in `../../pytorchsim/definitions/`. See `docs/COMPOUND_SCHEMA.md`.
