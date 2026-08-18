# pattmath_local — local replacement for the dead /home/i3dhdd1 PDK mount

Created 2026-07-17. Every node's `techlib_*/sram/lvs.rs` references two files
from `/home/i3dhdd1/autoCellGen/KNU_shared/pattmath` (`#define FINFET_PDK`,
line 26). That mount is no longer reachable; ICV aborts with PXL fatal #913
(and deletes its outputs) when the path is missing. This directory holds
local copies so the extraction flow is self-contained:

- `functions.rs` — generic ICV LVS utility include, referenced at
  `user_functions_file` (lvs.rs line 1147). Provenance:
  `~/ys_knu/sram/minkwan/functions.rs`, byte-identical to the independent
  SAED-28nm PDK copy at
  `/home/KNUEEhdd1/shared/techlib/saed28nm/customPDK32nm/icv/lvs/Include/`.
- `techfiles-customcompiler/i3d_gdsout.map` — layer map referenced at
  `openaccess_options(layer_mapping_file=...)` (lvs.rs line 74). Only
  consulted when ICV reads OpenAccess views; our flow feeds GDS, so this
  file must exist but its content does not affect extraction. Provenance:
  `2026_0617/WORK/01-post-layout_32/i3d_gdsout.map` (the FinFET-aware
  variant, incl. PDIFF/NDIFF/FIN/LTC/PTC/LTC2M0/M0/VIA0 rows).

Equivalence was proven at 20nm: extracting the pre-fix DL_X1 GDS with a
runset redirected to these files reproduces the netlist extracted on
2026-07-16 while the real mount was still alive, byte-identically outside
comment headers (`2026_0617/2026_0716_dffr_dl/fix_20nm_dl/validate_runset/`).

To use: change lvs.rs line 26 in each techlib to
    #define FINFET_PDK "/home/KNUEEhdd1/ys_knu/kmk/NPUWattch/dataset_gen/tech_libs/pattmath_local"
(keep a `.bak_i3dhdd1` copy of each runset first).

Related i3d collateral that already lives locally in `/home/KNUEEhdd1/shared`
(same volume, not the dead mount): 5nm ICV decks
`i3d_5nm_finfet/icv/i3d_finfet5nm_{lvs,drc}_rules.rs`, 5nm tech files, ITF,
nxtgrd, TLU+, NDM under `shared/techlib/i3d_5nm_finfet_tech/`.
