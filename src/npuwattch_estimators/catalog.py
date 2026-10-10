"""The message catalog of the built-in estimators (NW-8000 to NW-8999).

See ``npuwattch.diagnostics`` for the rules. The exception classes are in
``npuwattch_estimators.errors``. The ``blocks`` argument of ``register``
below gives the block of each module. In a block, the numbers are in the
source order of the module.

Add a new entry at the end of its block. Do not renumber an entry and do not
use a number again: add a removed number to ``retired``.
"""

from npuwattch.diagnostics import ERROR, INFO, WARNING, register

_E = "npuwattch_estimators."

register("NW", blocks={
    (8000, 8099): _E[:-1],                  # common: any estimator module
    (8100, 8149): _E + "logic.logic",
    (8150, 8179): _E + "logic.logic_mlp",
    (8180, 8199): _E + "logic.train_logic",
    (8200, 8249): _E + "sram.sram",
    (8250, 8279): _E + "sram.sram_mlp",
    (8280, 8299): _E + "sram.train_sram",
    (8300, 8399): _E + "custom",
}, entries={
    # -- 80xx common ------------------------------------------------------
    8001: ("EstimatorQueryError",
           "The {provider} provider does not serve primitive {primitive!r} "
           "and has no fallback provider.",
           "A provider gives each primitive that it does not serve to its "
           "fallback provider. This provider has no fallback provider. Give "
           "a fallback provider when you make this provider."),
    8002: ("EstimatorQueryError",
           "NPUWattch cannot read a technology node from {node!r}.",
           "The node value must contain the node size in nm. Give the node as "
           "a number or as a string such as 7nm."),
    8003: (INFO, "Wrote {path}"),

    # -- 81xx logic: logic.py ---------------------------------------------
    8101: ("LogicModelError",
           "The logic MLP models are not available: {error}",
           "The logic estimator needs PyTorch and the v2 model checkpoints. "
           "NPUWattch could not load one of them. Install torch in the Python "
           "environment. Make sure that the v2 checkpoints are in the model "
           "directory of the logic estimator."),
    8102: ("LogicQueryError",
           "logic/{component}: the required attribute {key!r} is missing or "
           "is not a number (got {value!r}).",
           "The logic model of this primitive needs a numeric value for this "
           "attribute. Give the attribute as a number in the description."),
    8103: ("LogicQueryError",
           "logic/{component}: net_oversubscription {value!r} is not in the "
           "range (0, 1].",
           "The net_oversubscription attribute is a fraction. Give a value "
           "that is larger than 0 and not larger than 1."),
    8104: ("EstimatorInternalError",
           "Logic: there is no attribute mapping for primitive {component!r}.",
           "The logic estimator serves this primitive, but its code has no "
           "attribute mapping for it. This is an error in NPUWattch. Report "
           "the error to the NPUWattch developers."),
    8105: ("LogicCheckpointError",
           "logic/{component}.{metric}: the checkpoint feature order {got} is "
           "different from the code order {expected}.",
           "The checkpoint and the code come from different versions of the "
           "logic MLP. NPUWattch cannot use this checkpoint. Train the model "
           "again with train_logic.py. Or use the checkpoints that agree with "
           "logic_mlp.VERSION."),
    8106: ("LogicQueryError",
           "logic/{component}: node {node!r} is not one of the characterized "
           "nodes {nodes} (nm).",
           "The logic model has a separate input for each characterized node. "
           "Thus the model cannot extrapolate to a different node. Use one of "
           "the characterized nodes."),
    8107: ("LogicQueryError",
           "logic/{component}: stim_mode {mode!r} is not characterized "
           "(characterized modes: {modes}).",
           "The logic model of this primitive has data only for the "
           "characterized stimulus modes. Use one of these modes."),
    8110: (WARNING,
           "pipeline_stages={requested} is outside the characterized range "
           "{lo}-{hi} of {primitive}, so NPUWattch uses "
           "pipeline_stages={used}.",
           "The pipeline depth is the registered latency, with the input and "
           "the output registers. The model of this primitive has data only "
           "for depths in this range. NPUWattch uses the nearest "
           "characterized depth. The energy, area, and timing of this "
           "component are for that depth."),
    8111: (WARNING,
           "{param}={value:g} is outside the characterized range {lo:g}-{hi:g} "
           "of {primitive}.",
           "The model of this primitive has training data only in this range. "
           "NPUWattch extrapolates the value. The result of this component is "
           "less accurate."),
    8112: (WARNING,
           "Clock {clock_ns:g} ns ({clock_mhz:.0f} MHz) is faster than the "
           "fastest {primitive} implementation at {node_nm} nm "
           "({fastest_ns:g} ns, {fastest_mhz:.0f} MHz).",
           "The dataset has no implementation of this primitive configuration "
           "at this clock. NPUWattch extrapolates the model along the clock "
           "axis. The result of this component is less accurate. To stay in "
           "the characterized range, use a deeper pipeline or a slower clock."),
    8113: (WARNING,
           "Clock {clock_ns:g} ns ({clock_mhz:.0f} MHz) is {side} than any "
           "characterized {primitive} at {node_nm} nm ({lo_ns:g}-{hi_ns:g} ns).",
           "The clock is outside the clock range of the dataset for this "
           "primitive and node. NPUWattch extrapolates the model along the "
           "clock axis. The result of this component is less accurate."),

    # -- 81xx logic: logic_mlp.py -----------------------------------------
    8150: ("LogicQueryError",
           "{component}.{column}: the value {value!r} is not a known category "
           "(known categories: {known}).",
           "The logic model uses this attribute as a category. It has data "
           "only for the known categories. Use one of the known categories."),

    # -- 81xx logic: train_logic.py ---------------------------------------
    8180: (ERROR, "Unknown component '{component}' (known components: {known}).",
           "The train_logic.py script trains models only for these logic "
           "primitives. Give one of the known names."),
    8181: (ERROR, "Unknown metric '{metric}' (known metrics: {known}).",
           "The train_logic.py script trains models only for these metrics. "
           "Give one of the known metrics."),
    8182: (INFO, "[{component}] rows={rows}  samples: {samples}, "
                 "dropped={dropped}"),

    # -- 82xx sram: sram.py -----------------------------------------------
    8201: ("SramQueryError",
           "The SRAM dataset directory {path} does not contain sram_array.csv "
           "and sram_decoder.csv.",
           "The SRAM estimator needs these two dataset files. Give a directory "
           "that contains the two files."),
    8202: ("SramQueryError",
           "NPUWattch cannot find sram_array.csv and sram_decoder.csv, and "
           "${env_var} is not set.",
           "NPUWattch did not find the SRAM dataset in dataset_gen/sram/datasets. "
           "Set the environment variable to the dataset directory. Or give the "
           "directory in features['dataset_dir']."),
    8203: ("SramDatasetError",
           "{context}: the value of '{key}' is missing or is not a number.",
           "The SRAM dataset is not correct, and NPUWattch cannot use it. "
           "Correct this row of the dataset file."),
    8204: ("SramDatasetError",
           "{context}: the dynamic energy is negative ({energy_pJ:.3e} pJ) "
           "after NPUWattch subtracts the leakage energy.",
           "NPUWattch calculates the dynamic energy as the window energy minus "
           "the leakage energy of the window. A negative result shows that the "
           "dataset is not consistent. Examine the energy and the leakage "
           "values of this row."),
    8205: ("SramDatasetError",
           "{context}: the nominal vdd of {node} is different from the other "
           "rows.",
           "The nominal rows of one node must have the same vdd. Correct the "
           "vdd value of this row."),
    8206: ("SramDatasetError",
           "{context}: the {sheet} row {key} occurs more than one time.",
           "Each configuration must have one row in each sheet of the SRAM "
           "dataset. Remove the duplicate row."),
    8207: ("SramDatasetError",
           "{context}: the decoder testbench uses clk_ns={clk_ns}, which is "
           "different from the measurement window.",
           "NPUWattch subtracts the leakage energy over a fixed measurement "
           "window. This window agrees with the clock period of the decoder "
           "testbench. A different clock period makes the subtraction "
           "incorrect. Change the measurement window in sram.py to agree with "
           "the testbench."),
    8208: ("SramDatasetError",
           "NPUWattch did not find nominal rows in the SRAM dataset {path}.",
           "The SRAM estimator needs the nominal rows of the dataset. Give a "
           "complete SRAM dataset."),
    8209: ("SramQueryError", "{name}={value!r} is less than 1.",
           "This SRAM feature is a count. Give an integer of 1 or more."),
    8210: ("SramQueryError", "{name}={value} is not in the range [0, 1].",
           "This SRAM feature is a fraction. Give a value from 0 to 1."),
    8211: ("SramQueryError",
           "The SRAM capacity {capacity_bits} bits is not a positive number.",
           "Give an SRAM capacity that is larger than 0 bits."),
    8212: (WARNING,
           "The SRAM of {capacity_bits} bits uses the macro templates "
           "{templates} in banks of at most {max_macros} macros "
           "(utilization {utilization:.1%}).",
           "The description gives only the capacity of this SRAM. NPUWattch "
           "selected the macro templates for this capacity. Give the SRAM "
           "shape in the description to use a different structure."),
    8213: (WARNING,
           "The template utilization {utilization:.1%} is less than 50% of "
           "one {template} macro.",
           "The capacity is much smaller than the smallest template macro. The "
           "energy and the area are for the full macro. Thus they are larger "
           "than for an SRAM of this capacity."),
    8214: ("SramQueryError",
           "mem_template '{template}' is not known (known templates: "
           "{available}).",
           "Use one of the known SRAM macro templates."),
    8215: ("SramQueryError",
           "mem_template '{template}' sets {feature}={fixed}, but the "
           "description gives {given}.",
           "The template sets this feature. Remove the feature from the "
           "description. Or remove the template."),
    8216: ("SramQueryError",
           "mem_template '{template}': mem_depth_per_bank={depth} is not "
           "S x {macro_depth} words with 1 <= S <= {max_macros} (S={macros}).",
           "A bank of a template SRAM has S template macros. Thus the bank "
           "depth must be an integer multiple of the macro depth. Give a "
           "mem_depth_per_bank in this range."),
    8217: (WARNING,
           "mem_template '{template}' (256 WL x {col_mux}:1 col-mux x "
           "{io_bits}b): NPUWattch models the column mux with 256x32 tile "
           "groups.",
           "The leakage of the unselected bitcell groups and of the idle "
           "decoders is in the result. The dynamic energy of the shared word "
           "lines and bit lines is not in the result. The energy of the mux "
           "and of the inter-bank select and routing is not in the result."),
    8218: ("SramQueryError",
           "The required SRAM feature '{name}' ({meaning}) is missing.",
           "The SRAM estimator cannot answer a query without this feature. "
           "Give the feature."),
    8219: ("SramQueryError",
           "Node '{node}' is not in the SRAM dataset (available nodes: "
           "{available}).",
           "The SRAM estimator has data only for these nodes. Use one of "
           "them."),
    8220: ("SramQueryError", "Corner '{corner}' is not characterized.",
           "The SRAM dataset has data only for the TT corner. Use corner TT."),
    8221: ("SramQueryError",
           "Transistor '{transistor}' is not characterized.",
           "The SRAM dataset has data only for the hp transistor. Use "
           "transistor hp."),
    8222: (WARNING,
           "mem_r_ports+mem_w_ports+mem_rw_ports={ports} is not "
           "characterized, so NPUWattch uses two ports.",
           "The SRAM dataset has single-port and dual-port data. NPUWattch "
           "calculates an SRAM with more ports as a dual-port SRAM. The energy "
           "and the area of the additional ports are not in the result."),
    8223: (WARNING,
           "The dual-port SRAM uses the single-port access energy.",
           "The access energy of one port is the measured single-port value. "
           "NPUWattch doubles the decoder count, area, leakage, and idle "
           "energy. The array area is the single-port array area."),
    8224: ("SramQueryError",
           "Optimize '{optimize}' is not known (known values: {choices}).",
           "Use one of the known optimization objectives."),
    8225: ("SramQueryError",
           "Source '{source}' is not auto, table, or mlp.",
           "Give source auto, table, or mlp."),
    8226: ("SramDatasetError",
           "The SRAM dataset has no PVT reference data for node '{node}'.",
           "NPUWattch needs PVT reference rows to scale the SRAM to a voltage "
           "offset or a temperature. Use the nominal voltage and 25 C for this "
           "node. Or add PVT reference rows to the dataset."),
    8227: (WARNING,
           "voltage_offset_V={value:+.3f} is outside the measured range "
           "[{lo:+.2f}, {hi:+.2f}], so NPUWattch uses {clamped:+.2f}.",
           "The SRAM dataset has PVT data only in this voltage range. "
           "NPUWattch uses the nearest limit of the range. The result is for "
           "that voltage offset."),
    8228: (WARNING,
           "temperature_C={value:g} is outside the measured range [{lo:g}, "
           "{hi:g}], so NPUWattch uses {clamped:g}.",
           "The SRAM dataset has PVT data only in this temperature range. "
           "NPUWattch uses the nearest limit of the range. The result is for "
           "that temperature."),
    8229: ("SramDatasetError",
           "The SRAM dataset has no usable PVT reference rows for node "
           "'{node}', metric '{metric}', at {temperature_C:g} C.",
           "NPUWattch cannot scale this metric to the requested voltage and "
           "temperature. Add PVT reference rows for this node to the dataset."),
    8230: (WARNING,
           "The PVT scaling of '{metric}' is different for the reference "
           "shapes (max/min = {spread:.2f}).",
           "NPUWattch uses the average PVT scaling of the reference shapes. "
           "The PVT scaling of this metric is less accurate for a given "
           "shape."),
    8231: ("SramQueryError", "source='mlp' is not available: {reason}",
           "The SRAM MLP models cannot be loaded. Install torch and the SRAM "
           "checkpoints. Or give source auto or table."),
    8232: (WARNING, "The SRAM estimator uses the table source: {reason}",
           "With source=auto, NPUWattch uses the MLP models when they are "
           "available. They are not available, thus NPUWattch uses the "
           "measured table."),
    8233: ("SramQueryError",
           "No measured tile shape agrees with tile_rows={tile_rows} "
           "tile_cols={tile_cols} at {node} (available: {available}).",
           "The SRAM estimator does not interpolate tile shapes. Give a tile "
           "shape that is in the list. Or remove tile_rows and tile_cols."),
    8234: ("SramQueryError", "There is no possible tiling for {config}.",
           "No measured tile shape can make an SRAM of this configuration. "
           "Change the depth, the width, or the tile shape."),
    8235: (WARNING,
           "The physical-bit utilization is {utilization:.2f} "
           "({logical_bits}/{physical_bits} bits).",
           "The tiles have more bits than the SRAM capacity. The unused bits "
           "also use read energy and leakage. The result includes this "
           "energy."),
    8236: (WARNING,
           "The SRAM bank has {tiles} tiles, and the inter-tile logic is not "
           "in the result.",
           "The SRAM datasets do not include the inter-tile logic: address and "
           "enable fanout, data-out muxes, and bank select. The energy and the "
           "delay of this logic are not in the result. The missing part "
           "increases with the number of tiles."),
    8237: (WARNING,
           "clock_mhz={clock_mhz:g} is more than f_max={f_max_MHz:.1f} MHz "
           "(t_read={t_read_ns:.3f} ns, t_write={t_write_ns:.3f} ns).",
           "The read time or the write time of this SRAM is longer than the "
           "clock period. Use a slower clock or a different SRAM shape."),
    8238: ("SramQueryError",
           "SRAM stim_mode '{mode}' is not known (known modes: {modes}).",
           "Use one of the known SRAM stimulus modes."),
    8239: ("SramQueryError", "The SRAM query has no features dict.",
           "The SRAM entrypoints need a features dict. Give the features as a "
           "dict."),
    8240: (ERROR, "SRAM estimator: {error}",
           "The SRAM estimator stopped with an unexpected error. The host "
           "receives no result for this query. Report the error to the "
           "NPUWattch developers."),

    # -- 82xx sram: sram_mlp.py -------------------------------------------
    8250: ("SramCheckpointError",
           "The checkpoint quartets in {path} come from different dataset "
           "versions.",
           "All SRAM checkpoints must come from the same dataset. Train the "
           "SRAM models again with train_sram.py."),
    8251: (WARNING,
           "The SRAM MLP checkpoints come from a different dataset version "
           "(trained {trained_sha}…, live {live_sha}…).",
           "The dataset changed after the training of the checkpoints. The "
           "MLP results can be different from the current dataset. Train the "
           "SRAM models again with train_sram.py."),

    # -- 82xx sram: train_sram.py -----------------------------------------
    8280: (ERROR, "Unknown model '{model}' (known models: {known}).",
           "The train_sram.py script trains only these models. Give one of "
           "the known names."),
    8281: (INFO, "Dataset {path} sha256={sha}…  samples: {samples}, "
                 "dropped={dropped}"),

    # -- 83xx custom --------------------------------------------------------
    8301: ("CustomQueryError",
           "User component {component!r} has no action {action!r} (its "
           "actions: {actions}).",
           "The user component library gives the energy of each action of "
           "this component. It does not give this action. Add the action to "
           "the user component library."),
    8302: (WARNING,
           "User component {component!r}: the values are for {reference}, "
           "but the run is at {node}.",
           "NPUWattch does not scale the values of a user component to a "
           "different node. The result of this component uses the values "
           "without a change. Give values for the node of the run in the user "
           "component library."),
}, retired=(), source=__name__)
