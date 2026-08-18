# Packaging helper only. Do not import estimator modules from the main program
# (they may pull in torch). Sanctioned exception: estimators.sram.sram is
# deliberately stdlib-only, and the emitter imports its SRAM template table
# (resolve_capacity) — the single source of truth the estimator owns.
