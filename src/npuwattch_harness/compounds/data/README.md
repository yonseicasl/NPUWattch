# Compound interpreter — system data

This directory holds **system files** for the compound interpreter (the
load/validate/resolve engine in `../loader.py`). These are NPUWattch internals,
not harness definitions users author.

```
primitive_modes.json    the stim_mode vocabulary CONTRACT — do not edit by hand
```

`primitive_modes.json` mirrors the characterized
`dataset_gen/logic/autosweep/sweep_spec.POWER_MODES`. A `(primitive, stim_mode)`
pair absent here is one the trained models cannot predict, so the loader rejects
any projection that uses it. It is kept as JSON because it is a machine-tied
contract (to be auto-generated from `POWER_MODES`), not a hand-authored sample.

The **harness definitions** users read/copy/edit — the compound component lists
and the per-tool projections — live with each harness instead, e.g.
`../../pytorchsim/definitions/`. See `docs/COMPOUND_SCHEMA.md`.
