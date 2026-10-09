"""The message catalog of the built-in estimators (NW-8000 to NW-8999).

See ``npuwattch.diagnostics`` for the rules. The exception classes are in
``npuwattch_estimators.errors``. Blocks:

- 8000-8099 common: the messages that two or more estimators use
  (``errors.py`` and the shared texts of the providers and trainers).
- 8100-8199 logic:
  8100-8149 ``logic/logic.py``, 8150-8179 ``logic/logic_mlp.py``,
  8180-8199 ``logic/train_logic.py``.
- 8200-8299 sram:
  8200-8249 ``sram/sram.py``, 8250-8279 ``sram/sram_mlp.py``,
  8280-8299 ``sram/train_sram.py``.
- 8300-8399 custom: ``custom/custom.py`` and ``custom/scaler.py``.

Add a new entry at the end of its block. Do not renumber an entry and do not
use a number again: add a removed number to ``retired``.
"""

from npuwattch.diagnostics import ERROR, INFO, WARNING, register

register("NW", {
    # -- 80xx common ------------------------------------------------------
    8001: ("EstimatorQueryError",
           "{provider} provider got primitive {primitive!r} and has no fallback"),
    8002: ("EstimatorQueryError",
           "cannot parse technology node from {node!r}"),
    8003: (INFO, "wrote {path}"),

    # -- 81xx logic: logic.py ---------------------------------------------
    8101: ("LogicModelError",
           "logic MLP layer unavailable ({error}) — torch and the v2 "
           "checkpoints are required"),
    8102: ("LogicQueryError",
           "logic/{component}: required attribute {key!r} is missing or "
           "non-numeric (got {value!r})"),
    8103: ("LogicQueryError",
           "logic/{component}: net_oversubscription must be in (0, 1] "
           "(got {value!r})"),
    8104: ("EstimatorInternalError",
           "logic: unmapped component {component!r}"),
    8105: ("LogicCheckpointError",
           "logic/{component}.{metric}: checkpoint feature order {got} != "
           "code {expected} — version drift, retrain or pin logic_mlp.VERSION"),
    8106: ("LogicQueryError",
           "logic/{component}: node {node!r} is outside the characterized set "
           "{nodes} (nm) — no extrapolation across the node one-hot"),
    8107: ("LogicQueryError",
           "logic/{component}: stim_mode {mode!r} was never characterized "
           "(known: {modes})"),
    8110: (WARNING,
           "pipeline_stages={requested} is outside the characterized "
           "{lo}-{hi} for {primitive} (depth = registered latency incl. "
           "input/output registers) — evaluated at pipeline_stages={used}"),
    8111: (WARNING,
           "{param}={value:g} is outside the characterized {lo:g}-{hi:g} for "
           "{primitive} — extrapolated"),
    8112: (WARNING,
           "clock {clock_ns:g} ns ({clock_mhz:.0f} MHz) is faster than the "
           "fastest characterized implementation of this {primitive} "
           "configuration at {node_nm} nm ({fastest_ns:g} ns, "
           "{fastest_mhz:.0f} MHz) — extrapolated along the clock axis; a "
           "deeper pipeline or slower clock is characterized"),
    8113: (WARNING,
           "clock {clock_ns:g} ns ({clock_mhz:.0f} MHz) is {side} than any "
           "characterized {primitive} at {node_nm} nm ({lo_ns:g}-{hi_ns:g} ns) "
           "— extrapolated along the clock axis"),

    # -- 81xx logic: logic_mlp.py -----------------------------------------
    8150: ("LogicQueryError",
           "{component}.{column}: unknown category {value!r} (known: {known})"),

    # -- 81xx logic: train_logic.py ---------------------------------------
    8180: (ERROR, "unknown component '{component}' (choose from {known})"),
    8181: (ERROR, "unknown metric '{metric}' (choose from {known})"),
    8182: (INFO, "[{component}] rows={rows}  samples: {samples}, "
                 "dropped={dropped}"),

    # -- 82xx sram: sram.py -----------------------------------------------
    8201: ("SramQueryError",
           "dataset dir {path} lacks sram_array.csv/sram_decoder.csv"),
    8202: ("SramQueryError",
           "cannot locate sram_array.csv/sram_decoder.csv; set "
           "${env_var} or pass features['dataset_dir']"),
    8203: ("SramDatasetError", "bad/missing '{key}' in {context}"),
    8204: ("SramDatasetError",
           "negative dynamic energy ({energy_pJ:.3e} pJ) after leakage "
           "subtraction in {context} — dataset inconsistent"),
    8205: ("SramDatasetError",
           "inconsistent nominal vdd for {node} at {context}"),
    8206: ("SramDatasetError", "duplicate {sheet} row {key} at {context}"),
    8207: ("SramDatasetError",
           "decoder TB cadence changed (clk_ns={clk_ns}) at {context}; "
           "leakage-subtraction window must be revisited"),
    8208: ("SramDatasetError", "no nominal rows loaded from {path}"),
    8209: ("SramQueryError", "{name} must be >= 1 (got {value!r})"),
    8210: ("SramQueryError", "{name} must be in [0, 1] (got {value})"),
    8211: ("SramQueryError",
           "capacity must be positive, got {capacity_bits} bits"),
    8212: (WARNING,
           "capacity-only SRAM spec ({capacity_bits} bits): auto-applied macro "
           "template(s) {templates} grouped into banks of <= {max_macros} "
           "macros; utilization {utilization:.1%}"),
    8213: (WARNING,
           "template utilization {utilization:.1%} < 50% — capacity is far "
           "below one {template} macro; energy/area reflect the full macro"),
    8214: ("SramQueryError",
           "unknown mem_template '{template}'; available: {available}"),
    8215: ("SramQueryError",
           "mem_template '{template}' fixes {feature}={fixed} but got {given} "
           "— drop the explicit value or drop the template"),
    8216: ("SramQueryError",
           "mem_template '{template}': mem_depth_per_bank={depth} must be "
           "S x {macro_depth} words with 1 <= S <= {max_macros} macros per "
           "bank (got S={macros})"),
    8217: (WARNING,
           "mem_template '{template}' (256 WL x {col_mux}:1 col-mux x "
           "{io_bits}b): mux approximated by 256x32 tile groups — unselected "
           "groups' bitcell leakage + idle decoders are charged; shared-WL/BL "
           "dynamic, the mux itself, and inter-bank select/routing are not "
           "modeled"),
    8218: ("SramQueryError", "missing required feature '{name}' ({meaning})"),
    8219: ("SramQueryError",
           "node '{node}' not in the SRAM dataset (available: {available})"),
    8220: ("SramQueryError",
           "corner '{corner}' not characterized (dataset is TT-only)"),
    8221: ("SramQueryError",
           "transistor '{transistor}' not characterized (hp only)"),
    8222: (WARNING,
           "mem_r_ports+mem_w_ports+mem_rw_ports={ports} not characterized; "
           "clamped to dual-port (2)"),
    8223: (WARNING,
           "dual-port: per-access energy taken equal to single-port "
           "(measured), decoder count/area/leakage/idle doubled; array area "
           "assumed port-independent"),
    8224: ("SramQueryError",
           "optimize must be one of {choices} (got '{optimize}')"),
    8225: ("SramQueryError", "source must be auto|table|mlp (got '{source}')"),
    8226: ("SramDatasetError", "no PVT reference data for node '{node}'"),
    8227: (WARNING,
           "voltage_offset_V={value:+.3f} outside measured range "
           "[{lo:+.2f}, {hi:+.2f}]; clamped to {clamped:+.2f}"),
    8228: (WARNING,
           "temperature_C={value:g} outside measured range [{lo:g}, {hi:g}]; "
           "clamped to {clamped:g}"),
    8229: ("SramDatasetError",
           "no usable PVT reference rows for node '{node}' metric '{metric}' "
           "at {temperature_C:g}C"),
    8230: (WARNING,
           "PVT scaling for '{metric}' disagrees across reference shapes "
           "(max/min = {spread:.2f}); shape-dependent PVT behaviour is "
           "averaged"),
    8231: ("SramQueryError", "source='mlp' requested but {reason}"),
    8232: (WARNING, "source=auto fell back to table: {reason}"),
    8233: ("SramQueryError",
           "no measured tile shape matches tile_rows={tile_rows} "
           "tile_cols={tile_cols} at {node} (available: {available})"),
    8234: ("SramQueryError", "no feasible tiling for {config}"),
    8235: (WARNING,
           "physical-bit utilization {utilization:.2f} ({logical_bits}/"
           "{physical_bits} bits); the padding still burns read energy and "
           "leakage"),
    8236: (WARNING,
           "{tiles} tiles/bank: inter-tile glue (address/enable fanout, dout "
           "muxing, bank select) is not in the datasets — energy/delay are "
           "underestimated at high tile counts"),
    8237: (WARNING,
           "clock_mhz={clock_mhz:g} exceeds f_max={f_max_MHz:.1f} MHz "
           "(t_read={t_read_ns:.3f} ns, t_write={t_write_ns:.3f} ns)"),
    8238: ("SramQueryError",
           "unknown sram stim_mode '{mode}' (use {modes})"),
    8239: ("SramQueryError", "features dict required"),
    8240: (ERROR, "sram: {error}"),

    # -- 82xx sram: sram_mlp.py -------------------------------------------
    8250: ("SramCheckpointError",
           "checkpoint quartets in {path} were trained on different dataset "
           "versions"),
    8251: (WARNING,
           "sram MLP checkpoints were trained on a different dataset version "
           "(trained {trained_sha}…, live {live_sha}…) — consider retraining "
           "(train_sram.py)"),

    # -- 82xx sram: train_sram.py -----------------------------------------
    8280: (ERROR, "unknown model '{model}' (choose from {known})"),
    8281: (INFO, "dataset {path} sha256={sha}…  samples: {samples}, "
                 "dropped={dropped}"),

    # -- 83xx custom --------------------------------------------------------
    8301: ("CustomQueryError",
           "user component {component!r} has no action {action!r}; its "
           "actions are {actions}"),
    8302: (WARNING,
           "user component {component!r}: the values are for {reference} and "
           "the run is at {node}; the custom component scaler is not "
           "implemented, so the values are used WITHOUT scaling"),
}, retired=(), source=__name__)
