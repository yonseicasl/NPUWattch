"""The message catalog of the ``npuwattch`` package (NW-1000 to NW-4999).

See ``npuwattch.diagnostics`` for the rules. Blocks (one sub-block for each
module; the numbers in a sub-block are in source order):

- 10xx  CLI (``npuwattch_console``)
- 11xx  argument parser (``npuwattch_parser``)
- 12xx  estimator host (``npuwattch_estimator_host``)
- 13xx  description database (``npuwattch_db``)
- 18xx  shared wrappers (this module): a message from a source that does not
  use the catalog yet (a plain ``str`` from a third-party plugin), and a
  message about one component or element
- 19xx  message system (``--suppress``, the message summary)
- 20xx  attribute names (``naming``)
- 21xx  user component library (``user_components``)
- 22xx  description and activity emitter (``arch_synth``)
- 30xx  unit-cost providers (``energy.unit_cost``)
- 31xx  energy calculation (``energy.aggregate``)
- 32xx  continuous node axis (``energy.node_scaling``)
- 33xx  vectorless activity (``energy.vectorless``)
- 34xx  DRAM energy tables (``energy.dram_table``)
- 36xx  provider chain (``energy.provider_factory``)
- 40xx  HTML and JSON report (``report.html``)

Add a new entry at the end of its block. Do not renumber an entry and do not
use a number again: add a removed number to ``retired``.
"""

from typing import Any

from npuwattch.diagnostics import (
    CRITICAL,
    ERROR,
    INFO,
    WARNING,
    Diagnostic,
    NPUWattchError,
    error,
    info,
    register,
    warning,
)

register("NW", {
    # -- 10xx: CLI (npuwattch_console) ----------------------------------------
    1001: (INFO, "Instance hierarchy ({source}):"),
    1002: (ERROR, "Estimator {estimator!r} declares no training entrypoint."),
    1003: (INFO, "Its models are trained by {script} — run that directly (it "
                 "owns the group split, the adaptive loss and the checkpoint "
                 "quartet; manual §5)."),
    1004: (INFO, "Starting training mode"),
    1005: (INFO, "Estimator: {estimator}"),
    1006: (INFO, "Model type: {model_type}"),
    1007: (INFO, "Training data: {path}"),
    1008: (INFO, "Epochs: {epochs}, Batch size: {batch_size}, LR: {lr}"),
    1009: (ERROR, "Training failed: {error}"),
    1010: (INFO, "Training completed successfully!"),
    1011: (INFO, "Native NPUWattch description detected (§3.1)"),
    1012: (WARNING, "--tree: hierarchy view unavailable: {error}"),
    1013: (ERROR, "Native mode expects exactly one activity CSV, got "
                  "{count}: {paths}"),
    1014: (INFO, "Technology: {node} / {transistor} / {corner} / "
                 "{voltage_offset_V:+.3f} V / {temperature_C} C"),
    1015: (ERROR, "Failed to read activity CSV {path}: {error}"),
    1016: (INFO, "Activity: {path} ({rows} rows)"),
    1017: (INFO, "Activity: {path} ({rows} rows, total_cycles={total_cycles})"),
    1018: (ERROR, "{error}"),
    1019: (CRITICAL, "Energy aggregation failed (internal error): {error}"),
    1020: (WARNING, "hierarchy view unavailable: {error}"),
    1021: (INFO, "Starting estimator mode"),
    1022: (ERROR, "Estimator mode expects one description, got {count}"),
    1023: (ERROR, "Description not found: {path}"),
    1024: (ERROR, "Not a native NPUWattch description (no 'npuwattch:' "
                  "root): {path}"),
    1025: (INFO, "Accelergy/Timeloop architecture YAMLs go through the "
                 "timeloop harness explicitly: npuwattch --harness timeloop "
                 "--arch-yaml {path} [--node ... --clock-mhz ...]"),
    1026: (INFO, "Harness mode: {harness}"),
    1027: (CRITICAL, "Harness ingest failed (internal error): {error}"),
    1028: (WARNING, "--tree: no hierarchy view for this run (the emitter's "
                    "warnings below say why); energy accounting is unaffected"),
    1029: (INFO, "Per-kernel provenance ({count} kernel(s)):"),
    1030: (INFO, "Wrote native description: {path}"),
    1031: (INFO, "Wrote native activity:    {path}"),
    1032: (INFO, "Wrote report:      {path}"),
    1033: (INFO, "Wrote report data: {path}"),
    1034: (WARNING, "--report: report generation failed: {error}"),
    1035: (INFO, "Per-{term} energy ({count} {noun})"),
    1036: (INFO, "GEMM kernels (mac/fused): {gemm_pJ:.4g} pJ ({gemm_windows} "
                 "window(s)); non-GEMM kernels: {non_gemm_pJ:.4g} pJ "
                 "({non_gemm_windows} window(s), {percent:.1f}% of total)"),
    1037: (INFO, "Per-{term} component energy (dynamic, pJ)"),
    1038: (INFO, "{count} component(s) with no dynamic activity omitted — "
                 "leakage in the summary below"),
    1039: (INFO, "Energy summary — {tag}"),
    1040: (INFO, "DRAM device energy ({components}): activation "
                 "{activate_pJ:.4g} pJ ({activate_pct:.1f}%) + transfer "
                 "{transfer_pJ:.4g} pJ ({transfer_pct:.1f}%; read {read_pJ:.4g} "
                 "+ write {write_pJ:.4g}) + refresh {refresh_pJ:.4g} pJ "
                 "({refresh_pct:.1f}%)"),

    # -- 11xx: argument parser (npuwattch_parser) -----------------------------
    1101: (ERROR, "command line: {message}"),
    1102: (ERROR, "--harness and -d/--description are mutually exclusive"),
    1103: (ERROR, "{flags} require(s) --harness"),
    1104: (ERROR, "{flag} requires {needed_flag}"),
    1105: (ERROR, "--vectorless-activity applies only to vectorless runs: -d "
                  "WITHOUT -l, or a harness with no activity reader (it "
                  "replaces the missing activity log)"),
    1106: (ERROR, "--vectorless-activity: {flag} provides real activity; the "
                  "flag applies only to vectorless runs (-d without -l, or a "
                  "harness run without {flag})"),
    1107: (ERROR, "--vectorless-activity: the {harness!r} harness reads real "
                  "activity from its logs; the flag applies only to vectorless "
                  "runs (-d without -l, or a harness that has no activity "
                  "input)"),
    1108: (ERROR, "--vectorless-activity must be in (0, 1], got {value}"),
    1109: (ERROR, "Flattener mode (-f/--flatten) requires -i/--input"),
    1110: (ERROR, "-i is not a harness input; pass the named inputs of the "
                  "harness: {inputs}"),
    1111: (ERROR, "-i is not a harness input; pass the named inputs of the "
                  "harness: {inputs} (or {usage_hint})"),
    1112: (ERROR, "Harness mode (--harness {harness}) requires {missing}"),
    1113: (ERROR, "{flag} is not an option of the {harness!r} harness"),
    1114: (ERROR, "Training mode (-t/--train) requires {flag}"),
    1115: (ERROR, "Estimator mode requires -d/--description"),

    # -- 12xx: estimator host (npuwattch_estimator_host) ----------------------
    1201: ("EstimatorRootError", "Could not locate estimator root. Tried "
                                 "./src/npuwattch_estimators and installed "
                                 "'npuwattch_estimators' package."),
    1202: (INFO, "Estimator root: {path}"),
    1203: (WARNING, "No estimator modules found."),
    1204: (INFO, "Modules found:"),
    1205: (ERROR, "Failed to load module '{module}': {error}"),
    1206: (ERROR, "Estimator module '{module}' not found. Available: "
                  "{available}"),
    1207: (ERROR, "Failed to load namespace for module '{module}'"),
    1208: (ERROR, "Function '{function}' not found/callable in '{module}'. "
                  "Available: {available}"),
    1209: (ERROR, "Exception in {module}.{function}: {error}"),
    1210: (ERROR, "No ESTIMATOR_SPEC found for module '{module}'"),
    1211: (ERROR, "Entrypoint '{entrypoint}' not declared for '{module}'"),
    1212: (ERROR, "Estimator '{module}' does not exist. Returning None for "
                  "{metric}."),
    1213: (ERROR, "Estimator '{module}' does not exist. Cannot train."),
    1214: (ERROR, "Estimator '{module}' does not exist."),

    # -- 13xx: description database (npuwattch_db) ----------------------------
    1301: (INFO, "Starting database construction from: {source}"),
    1302: (WARNING, "Empty YAML file"),
    1303: (INFO, "Database construction complete. Loaded {components} "
                 "components with {instances} total instances."),
    1304: (INFO, "Registered Components List:"),

    # -- 18xx: shared wrappers (this module) ----------------------------------
    1801: (INFO, "{message}"),
    1802: (WARNING, "{message}"),
    1803: (ERROR, "{message}"),
    1804: (WARNING, "{subject}: {message}"),

    # -- 19xx: message system (npuwattch_parser, npuwattch_console) ----------
    1901: (ERROR, "--suppress: {problem}"),
    1902: (INFO, "Message summary: {critical} CRITICAL, {error} ERROR, "
                 "{warning} WARNING, {info} INFO"),
    1903: (INFO, "Message summary: {critical} CRITICAL, {error} ERROR, "
                 "{warning} WARNING, {info} INFO; {suppressed} suppressed "
                 "({codes})"),

    # -- 20xx: attribute names (naming) ---------------------------------------
    2001: ("NamingError", "{component} ({primitive}): attribute '{key}' is a "
                          "legacy alias; rename it to '{target}'. Estimators "
                          "accept exactly one name per concept — see "
                          "npuwattch.naming.CANONICAL."),
    2002: (WARNING, "{component} ({primitive}): unknown attribute '{key}' — not "
                    "in the canonical vocabulary; no estimator will read it"),
    2003: ("NamingError", "{component} ({primitive}): missing required "
                          "attribute(s) {missing}. Required: {required}"),
    2004: (WARNING, "{component} ({primitive}): '{key}' is canonical but not a "
                    "{primitive} parameter — it will be ignored"),

    # -- 21xx: user component library (user_components) -----------------------
    2101: ("UserComponentError", "{where}: user_components must be a mapping"),
    2102: ("UserComponentError", "{where}: {what} must be a positive number, "
                                 "got {value!r}"),
    2103: ("UserComponentError", "{where}: {what} must be a number >= 0, "
                                 "got {value!r}"),
    2104: ("UserComponentError", "{where}: component name {name!r} must be "
                                 "lowercase letters, digits, and underscores, "
                                 "and start with a letter"),
    2105: ("UserComponentError", "{where}: {name}: must be a mapping"),
    2106: ("UserComponentError", "{where}: {name}: unknown key(s) {keys}"),
    2107: ("UserComponentError", "{where}: {name}: reference.node is necessary "
                                 "(the technology node of the area and energy "
                                 "values)"),
    2108: ("UserComponentError", "{where}: {name}: design_class must be one of "
                                 "{classes}, got {design_class!r}"),
    2109: ("UserComponentError", "{where}: {name}: actions must be a mapping "
                                 "with one action or more"),
    2110: ("UserComponentError", "{where}: {name}.actions.{action}: give "
                                 "{{energy_pJ: <number>}}"),
    2111: ("UserComponentError", "{where}: {name}.characterized must map a "
                                 "node to its values"),
    2112: ("UserComponentError", "{where}: {name}: give a node such as 7nm "
                                 "and a mapping"),
    2113: ("UserComponentError", "user component library not found: {path}"),
    2114: ("UserComponentError", "{path}: not valid YAML: {error}"),
    2115: ("UserComponentError", "{path}: the file must have a top-level "
                                 "`user_components` key"),
    2116: (INFO, "user component {name!r} ({source}): parsed, but not used"),

    # -- 22xx: description and activity emitter (arch_synth) ------------------
    2201: ("EmitterError", "{element}: give capacity_kbit OR capacity_bit, "
                           "not both"),
    2202: (WARNING, "{element}: SRAM estimator unavailable "
                    "(npuwattch_estimators.sram not importable); "
                    "capacity-specified element not emitted"),
    2203: (WARNING, "{element}: traffic charged to the primary part; "
                    "'{element}.tail' carries leakage/area only"),
    2204: (WARNING, "window {window}: no exec cycles; cycle_start/end left at "
                    "{start}"),
    2205: (WARNING, "window {window}: action {action!r} (unit flits) needs a "
                    "word width and flit size for element {element!r}; "
                    "counted as words"),
    2206: (WARNING, "window {window}: action {action!r} (unit flits) has no "
                    "port count for crossbar element {element!r}; counted as "
                    "cycles 1:1"),
    2207: (WARNING, "window {window}: action {action!r} uses unit {unit!r} but "
                    "element {element!r} has no capacity-resolved word width; "
                    "counted as words"),
    2208: (WARNING, "window {window} ({kernel}): activity stat {stat!r}={value} "
                    "is interpreted by no action in projection {tool!r} "
                    "(intentional coarser fidelity, or an incomplete "
                    "projection)"),
    2209: (INFO, "activity stat {stat!r} (total {total} across {windows} "
                 "window(s)) is not charged — waived in projection {tool!r}: "
                 "{reason}"),

    # -- 30xx: unit-cost providers (energy.unit_cost) -------------------------
    3001: ("NoModelError", "no model for class {primitive!r} — NPUWattch has "
                           "no estimator for it; give its area and action "
                           "energies in the user component library "
                           "(--user-components)"),
    3002: ("EnergyTableError", "link energy table {path}: {error}"),
    3003: ("EnergyTableError", "link energy table {path}: energy_pj_per_bit "
                               "must be a positive number, got {value!r}"),
    3004: ("ProviderChainError", "{provider} provider got primitive "
                                 "{primitive!r} and has no fallback"),

    # -- 31xx: energy calculation (energy.aggregate) --------------------------
    3101: (WARNING, "{component}: {events:g} access events exceed the "
                    "{instances} x {cycles} cycles the component can serve — "
                    "idle energy floored at 0"),
    3102: (WARNING, "no exec cycles: clocked-idle energy of {components} "
                    "charged per access event"),
    3103: ("AggregateError", "native description has no clock.frequency_MHz "
                             "(and no default_clock_mhz)"),
    3104: ("NoModelError", "{component}: no model for class {primitive!r} — "
                           "NPUWattch has no estimator for it; give its area "
                           "and action energies in the user component library "
                           "(--user-components)"),

    # -- 32xx: continuous node axis (energy.node_scaling) ---------------------
    3201: ("NodeError", "cannot parse technology node {value!r} — expected a "
                        "length in nm such as '7nm' or '12.5nm'"),
    3202: ("NodeError", "technology node must be a positive length, got "
                        "{value!r}"),
    3203: ("ProviderChainError", "resolve_node needs a non-empty characterized "
                                 "node set"),
    3204: (WARNING, "node {requested_nm:g} nm is outside the supported envelope "
                    "{envelope_lo_nm:g}-{envelope_hi_nm:g} nm (characterized "
                    "{char_lo_nm:g}-{char_hi_nm:g} nm ±50%) — evaluated at "
                    "{eval_nm:g} nm instead; the results model {eval_nm:g} nm, "
                    "not {requested_nm:g} nm"),
    3205: (WARNING, "node {requested_nm:g} nm is outside the characterized "
                    "range {char_lo_nm:g}-{char_hi_nm:g} nm — log-extrapolated "
                    "from the {lo}/{hi} trend; treat the results as "
                    "first-order"),
    3206: (INFO, "node {requested_nm:g} nm is not a characterized node — "
                 "log-interpolated between {lo} and {hi}"),

    # -- 33xx: vectorless activity (energy.vectorless) ------------------------
    3301: ("VectorlessError", "vectorless activity must be in (0, 1], got "
                              "{activity}"),
    3302: (INFO, "VECTORLESS estimate: no activity log — every component "
                 "charged at {activity:.0%} of random switching "
                 "(crossbar-family uses the measured valid25 mode); dynamic "
                 "values are per-cycle energies and avg power is the "
                 "steady-state figure"),
    3303: (INFO, "user component(s) {components}: no `random` action in the "
                 "library — charged area and leakage only in this VECTORLESS "
                 "run"),
    3304: (INFO, "{count} capacity '.tail' part(s) charged leakage/area only "
                 "(their access energy is already in the primary part's unit "
                 "cost)"),

    # -- 34xx: DRAM energy tables (energy.dram_table) -------------------------
    3401: ("EnergyTableError", "energy table {path}: {key} must be a positive "
                               "number, got {value!r}"),
    3402: ("EnergyTableError", "energy table not found: {path}"),
    3403: ("EnergyTableError", "energy table {path}: not valid YAML — {error}"),
    3404: ("EnergyTableError", "energy table {path}: top level must be a "
                               "mapping"),
    3405: ("EnergyTableError", "energy table {path}: missing 'name' (the table "
                               "name the log's [Config/Energy] echo declares, "
                               "e.g. HBM2)"),
    3406: ("EnergyTableError", "energy table {path}: missing 'offchip_dram' "
                               "mapping"),
    3407: ("EnergyTableError", "energy table {path}: "
                               "offchip_dram.transfer_pj_per_bit must be a "
                               "non-empty mapping of per-bit terms"),

    # -- 36xx: provider chain (energy.provider_factory) -----------------------
    3601: (WARNING, "estimator {estimator!r}: unit_cost_provider unavailable "
                    "({error})"),

    # -- 40xx: HTML and JSON report (report.html) -----------------------------
    4001: ("ReportError", "report: RunEnergy has no windows to report"),
}, retired=(), source=__name__)


# ---------------------------------------------------------------------------
# Shared wrappers
# ---------------------------------------------------------------------------

def as_diagnostic(message: Any, level: str = WARNING) -> Diagnostic:
    """Return ``message`` as a catalog message.

    A :class:`Diagnostic` does not change. An exception with a catalog entry
    becomes the message of its entry. A plain ``str`` (from a third-party
    plugin that does not use the catalog yet) gets the generic entry of
    ``level`` (NW-1801 INFO, NW-1802 WARNING, NW-1803 ERROR). Thus each
    printed line has a code.
    """
    if isinstance(message, Diagnostic):
        return message
    if isinstance(message, NPUWattchError) and message.number is not None:
        return message.as_diagnostic()
    text = str(message)
    if level == INFO:
        return info(1801, message=text)
    if level == ERROR:
        return error(1803, message=text)
    return warning(1802, message=text)


def about(subject: str, message: Any) -> Diagnostic:
    """Return ``message`` with the prefix ``"<subject>: "``.

    The message is about one component or element (for example, an envelope
    warning of an estimator). A :class:`Diagnostic` keeps its code and its
    level; only its text gets the prefix. A plain ``str`` gets the generic
    entry NW-1804 (WARNING).
    """
    if isinstance(message, Diagnostic):
        return Diagnostic(message.space, message.number, message.level,
                          f"{subject}: {message.text}",
                          {**message.fields, "subject": subject})
    return warning(1804, subject=subject, message=str(message))


__all__ = ["about", "as_diagnostic"]
