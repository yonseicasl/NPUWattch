# PyTorchSim harness definitions

This is the **default bundle** NPUWattch loads for PyTorchSim, and the **worked
sample** to copy when authoring your own harness definitions. It is edited by
hand (unlike the system contract in `../../compounds/data/`), so it is authored
in YAML with inline `#` comments.

```
compounds/systolic_mac.yaml     the compound(s) this harness models (tool-agnostic)
projections/pytorchsim.yaml     PyTorchSim native action -> {element: stim_mode}
```

- **compounds/** — hardware composition as NPUWattch primitives. Tool-agnostic:
  nothing PyTorchSim-specific appears here. Placeholders `{mac_primitive}` /
  `{mac_config}` and the symbols `lanes` / `bitwidth` are resolved per kernel by
  the MAC config inferencer.
- **projections/** — how PyTorchSim's native actions drive the compound's
  elements, and which stat gives each action's cycle count (`count_from`).

Load the shipped bundle:

```python
from npuwattch.harness.pytorchsim import load_definitions
b = load_definitions()                 # Bundle(compounds, projections, primitive_modes)
sm   = b.compound("systolic_mac")
proj = b.projection("pytorchsim")
```

## Author your own (JSON or YAML)

Copy this directory, edit the files (or add new compounds/projections), and load
it — YAML is recommended for hand-authoring, JSON also works:

```python
from npuwattch.harness.compounds import load_bundle
b = load_bundle("my_harness_defs")     # <root>/compounds/, <root>/projections/,
                                       # optional <root>/primitive_modes.*
```

`primitive_modes` stays the system contract unless your bundle ships its own
(only if you characterized new modes). Quote any `{...}` in YAML — an unquoted
`{...}` is a flow mapping.
