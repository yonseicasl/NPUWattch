"""The message catalog of the Timeloop harness (NW-7000 to NW-7999).

See ``npuwattch.diagnostics`` for the rules. Each module has one block of
100 numbers. The numbers in a block are in the source order of the module:

==========  ===========================================================
Block       Module
==========  ===========================================================
70xx        ``__init__``, ``tree`` (reserved, no messages)
71xx        ``ingest``: description and activity of the run
72xx        ``stats``: Timeloop stats reader and ``--stats-map``
73xx        ``vocabulary``: derivation rules of the attributes
74xx        ``dram``: DRAM energy tables
75xx        ``accelergy_flattener``: ``-f/--flatten`` mode
==========  ===========================================================

Add a new entry at the end of its block. Do not renumber an entry and do
not use a number again: add a removed number to ``retired``.
"""

from npuwattch.diagnostics import INFO, WARNING, register

register("NW", {
    # -- 71xx ingest --------------------------------------------------------
    7101: (INFO, "Compound component {name!r} ({file}) is parsed, but no "
                 "component uses it.",
           "The compound component file defines this compound component. No "
           "component of the description has this class. No action is "
           "necessary."),
    7102: (WARNING, "--vectorless-activity is ignored, because the run has "
                    "Timeloop stats.",
           "The Timeloop stats give the real activity of the run. NPUWattch "
           "uses the stats and ignores the vectorless activity. To use the "
           "vectorless activity, do not give --stats."),
    7103: (WARNING, "The hierarchy view is not available: {error}",
           "NPUWattch cannot make the hierarchy tree of the description. The "
           "energy and the area results do not change. Read the error to "
           "find the problem in the description."),
    7104: ("CompoundBundleError",
           "Element {element!r}: {key} = {value!r} has no integer value.",
           "The value of this element attribute is a name, but the attribute "
           "must be an integer. The Accelergy component does not declare that "
           "name as an integer attribute. Declare the attribute as an integer "
           "in the Accelergy component."),
    7105: ("HarnessError",
           "{component}: compound component {compound!r} is not valid: {error} "
           "(symbols: {symbols}).",
           "NPUWattch cannot resolve the compound component of this component. "
           "The symbols are the attributes that the component gives to the "
           "compound component. Correct the compound component file or the "
           "attributes of the component."),
    7106: ("HarnessError",
           "The projection file has no projection for tool: timeloop (found: "
           "{found}).",
           "A Timeloop run needs a projection for the timeloop tool. The "
           "projection gives the Timeloop events of each compound component. "
           "Add a projection with tool: timeloop to the projection file."),
    7107: ("HarnessError",
           "Projection: compound component {compound!r} has action(s) "
           "{actions} that are not Timeloop events ({events}).",
           "In a Timeloop projection, each action name must be a Timeloop "
           "event. NPUWattch cannot charge an action with a different name. "
           "Rename the action to one of the Timeloop events."),
    7108: ("HarnessError",
           "{component}: the projection {compound}.{action} is not valid: "
           "{error}",
           "NPUWattch cannot resolve this action of the compound component. "
           "Correct the projection file or the compound component file."),
    7109: (INFO, "{component}: the user component library entry {entry!r} "
                 "gives the cost, not the class {comp_class!r}.",
           "The user_component attribute of the component names the library "
           "entry. NPUWattch uses the entry for the area and the energy. "
           "Timeloop uses the class of the component."),
    7110: (INFO, "{component}: class {comp_class!r} is the compound component "
                 "{compound!r} ({elements})."),
    7111: (INFO, "{component}: class {comp_class!r} uses the user component "
                 "library entry {entry!r}"),
    7112: (INFO, "{component}: the regfile holds more than 32 Kib, so "
                 "NPUWattch models it as an SRAM.",
           "The regfile primitive covers sizes up to 32 Kib. For a larger "
           "regfile, NPUWattch uses the SRAM estimator. No action is "
           "necessary."),
    7113: (WARNING, "{component} is not modeled: {error}",
           "An attribute of this component has an error. NPUWattch removes "
           "the component from the run and continues. Its energy and area are "
           "not in the results. Correct the attribute in the description."),
    7114: (WARNING, "{count} component(s) have no NPUWattch primitive and are "
                    "not modeled: {components}",
           "NPUWattch did not find a primitive for the class of these "
           "components. Their energy and area are not in the results. To "
           "include a component, define its class as a compound component "
           "with --compound-components. Or add it to the user component "
           "library with --user-components."),
    7115: ("HarnessError",
           "{path}: NPUWattch found no enabled components.",
           "NPUWattch reads Accelergy v0.4 architecture descriptions. The file "
           "has no enabled component in this format. Make sure that the file "
           "is an Accelergy v0.4 architecture description."),
    7116: (INFO, "The description declares technology {declared}, but the run "
                 "uses {node} from --node.",
           "NPUWattch models the node that --node gives. The technology in "
           "the description has no effect."),
    7117: (WARNING, "The description declares technology {declared}, but the "
                    "run uses the default node {node}.",
           "NPUWattch models the node that --node gives. The run has no "
           "--node, so NPUWattch uses the default node. The technology in the "
           "description has no effect. To model the declared technology, give "
           "it with --node."),
    7118: (INFO, "Clock: {clock_mhz:g} MHz from --clock-mhz replaces "
                 "{declared_mhz:g} MHz from the description."),
    7119: (INFO, "Clock: {clock_mhz:g} MHz, from the description."),
    7120: (INFO, "Clock: the description declares no clock, so NPUWattch uses "
                 "{clock_mhz:g} MHz.",
           "The power and the time values depend on the clock. To use a "
           "different clock, give --clock-mhz."),

    # -- 72xx stats -----------------------------------------------------------
    7201: ("TimeloopStatsError",
           "{path}: NPUWattch found no '=== <level> ===' blocks.",
           "A stats file from timeloop-model or timeloop-mapper has one "
           "'=== <level> ===' block for each level. This file has no such "
           "block. Give a .stats.txt file from timeloop-model or "
           "timeloop-mapper."),
    7202: ("TimeloopStatsError", "{path}: NPUWattch found no positive cycle "
                                 "count.",
           "The stats file must give a cycle count above zero. NPUWattch needs "
           "the cycles for the windows and the power. Give a complete stats "
           "file from timeloop-model or timeloop-mapper."),
    7203: ("TimeloopStatsError",
           "{path}: NPUWattch found no '{pattern}' files.",
           "The directory has no stats file with this name pattern. Give a "
           "stats file from timeloop-model or timeloop-mapper. Or give a "
           "directory of stats files, one file for each layer."),
    7204: ("TimeloopStatsError",
           "Stats map: level '{level}'{where} has an entry that is not a "
           "component name.",
           "Each entry of a level must be a name, {name: N}, or {name: {count: "
           "N, action: A}}. N is the number of events for each access. A is "
           "the action that NPUWattch charges. Correct the stats map file."),
    7205: ("TimeloopStatsError",
           "Stats map: level '{level}'{where} has no component names.",
           "Each level of the stats map must name one or more description "
           "components. Add the component names to the level in the stats map "
           "file."),
    7206: ("TimeloopStatsError",
           "Stats map: level '{level}' has the unknown event '{event}' (known "
           "events: {events}).",
           "The stats map can bind only the Timeloop events in the list. "
           "Correct the event name in the stats map file."),
    7207: ("TimeloopStatsError", "Stats map: level '{level}' binds no "
                                 "component.",
           "This level has no component for any event. Add a component name "
           "to the level. Or put the level in the 'ignore:' list."),
    7208: ("TimeloopStatsError",
           "Stats map: level '{level}' has a value of the wrong type.",
           "The value of a level must be a component name or a list of names. "
           "It can also be a mapping {read|write|op: names}. Correct the stats "
           "map file."),
    7209: ("TimeloopStatsError",
           "{path}: the stats map is not a mapping.",
           "The stats map file must be a YAML mapping. Its keys are 'levels:' "
           "and 'ignore:'."),
    7210: ("TimeloopStatsError",
           "{path}: 'levels' is not a mapping or 'ignore' is not a list.",
           "In a stats map, the value of 'levels' is a mapping from a Timeloop "
           "level to components. The value of 'ignore' is a list of Timeloop "
           "levels. Correct the stats map file."),
    7211: ("TimeloopStatsError",
           "{path}: the stats map has unknown key(s) {keys}.",
           "The stats map takes the keys 'levels:' and 'ignore:'. Remove or "
           "rename the other keys."),
    7212: ("TimeloopStatsError",
           "The stats mode {mode!r} is not 'windows' or 'aggregate'.",
           "The windows mode makes one window for each stats file. The "
           "aggregate mode makes one window for the full run. Give one of the "
           "two modes with --stats-mode."),
    7213: ("TimeloopStatsError",
           "The stats map names component(s) that are not in the description: "
           "{missing} (description components: {components}).",
           "Each component name in the stats map must be a component of the "
           "description. Correct the name in the stats map file."),
    7214: (WARNING, "Stats level '{level}' matches more than one description "
                    "component ({candidates}).",
           "NPUWattch cannot select one component for this Timeloop level. "
           "The activity of the level is not charged. Bind the level to one "
           "component in the 'levels:' of --stats-map."),
    7215: (WARNING, "Stats level '{level}' has {stats_instances} instance(s), "
                    "but the description component '{component}' has "
                    "{declared}.",
           "The instance counts of the Timeloop level and of the description "
           "component are different. The stats can be from a different "
           "architecture. Make sure that the stats and the description are "
           "from the same architecture."),
    7216: ("TimeloopStatsError",
           "Stats map: level '{level}' names the action '{action}' for the "
           "compound component '{component}'.",
           "A compound component takes its actions from projection.yaml. The "
           "stats map cannot name an action for it. Remove the action from "
           "this entry of the stats map."),
    7217: ("TimeloopStatsError",
           "Stats map: level '{level}' charges '{component}' with the unknown "
           "action '{action}' (actions: {actions}).",
           "The action in the stats map must be an action of the primitive of "
           "the component. Use one of the actions in the message."),
    7218: (INFO, "Timeloop stats: {files} file(s), {cycles} cycles, "
                 "{charged}/{total} description components charged ({mode} "
                 "mode).",
           "NPUWattch charges the compute components in the weight-stationary "
           "mode. The Timeloop Computes count becomes the hold_b action."),
    7219: (WARNING, "Stats level(s) with no matching description component: "
                    "{levels}",
           "NPUWattch did not find a description component with the name of "
           "these Timeloop levels. The activity of these levels is not in the "
           "results. To charge a level, rename it in the 'levels:' of "
           "--stats-map. To remove a level on purpose, add it to 'ignore:'."),
    7220: (INFO, "Stats level(s) {levels} are in the 'ignore:' list of the "
                 "map, so their energy is not in the run.",
           "The stats map tells NPUWattch to ignore these levels. No action is "
           "necessary if you want this result."),
    7221: (WARNING, "{count} description component(s) get no Timeloop "
                    "activity: {components}",
           "Timeloop does not model these components. NPUWattch charges only "
           "their leakage energy and their area. Their dynamic energy is not "
           "in the results. To charge a component, bind a Timeloop level to "
           "it in the 'levels:' of --stats-map."),
    7222: (INFO, "Stats level '{level}' charges more than one component: "
                 "{bindings}",
           "The stats map binds this level to these components. NPUWattch "
           "charges the access count of the level to each component."),
    7223: (INFO, "{component}: charged in the '{mode}' stim mode.",
           "The primitive of this component has no data for the stim mode of "
           "this Timeloop event. NPUWattch uses the nearest stim mode that the "
           "primitive has. No action is necessary."),

    # -- 73xx vocabulary ------------------------------------------------------
    7301: (INFO, "{component} ({primitive}): NPUWattch ignores the Accelergy "
                 "attribute(s) {attributes}.",
           "These attributes have no NPUWattch attribute with the same "
           "meaning. They do not change the result. No action is necessary."),
    7302: (WARNING, "{component} ({primitive}): no word width is declared, so "
                    "NPUWattch uses 32 bits.",
           "The description gives no word width for this storage component. "
           "NPUWattch uses a 32-bit word. The energy and the area are correct "
           "only for a 32-bit word. Declare the width of the component in the "
           "description."),
    7303: (INFO, "{component} ({primitive}): depth {depth} is the declared "
                 "capacity divided by the {width} b word."),
    7304: (WARNING, "{component} ({primitive}): no depth or capacity is "
                    "declared, so NPUWattch uses 64 entries.",
           "The description gives no depth and no capacity for this storage "
           "component. NPUWattch uses a depth of 64 entries. The energy and "
           "the area are correct only for this depth. Declare the depth or "
           "the capacity of the component in the description."),
    7305: (WARNING, "{component} ({primitive}): total depth {depth} is not a "
                    "multiple of {banks} banks, so each bank has {per_bank} "
                    "words.",
           "NPUWattch divides the total depth by the number of banks and "
           "rounds up. The modeled capacity is larger than the declared "
           "capacity. Declare a depth that is a multiple of the number of "
           "banks."),
    7306: (INFO, "{component} ({primitive}): depth {depth} is the total of "
                 "{banks} banks, so mem_depth_per_bank is {per_bank} "
                 "({capacity} total).",
           "In Accelergy, the depth is the total for all banks. NPUWattch "
           "divides it by the number of banks."),
    7307: (INFO, "{component} ({primitive}): no port count is declared, so "
                 "NPUWattch uses one shared read-write port."),
    7308: (INFO, "{component} ({primitive}): bandwidth {bandwidth} gives up to "
                 "{accesses} bank accesses per cycle.",
           "NPUWattch charges each bank access as one access event."),
    7309: (WARNING, "{component} ({primitive}): bandwidth {bandwidth} needs "
                    "{accesses} accesses/cycle, but {banks} bank(s) × {ports} "
                    "port(s) give {slots} (needs {needed_banks} banks).",
           "The Timeloop mapping needs more accesses in one cycle than the "
           "declared banks and ports can give. The declared structure cannot "
           "serve this mapping. Declare more banks or more ports. Or change "
           "the bandwidth in the description."),
    7310: (WARNING, "{component} (hbm): no word width is declared, so "
                    "NPUWattch charges a 32 B burst per access.",
           "NPUWattch uses a 256-bit (32 B) burst for each DRAM access. The "
           "DRAM energy is correct only for this burst size. Declare the "
           "width of the DRAM component in the description."),
    7311: (WARNING, "{component} ({primitive}): no operand width is declared, "
                    "so NPUWattch uses 8 bits.",
           "NPUWattch uses an 8-bit integer operand. The energy and the area "
           "are correct only for 8-bit operands. Declare the operand width of "
           "the component in the description."),
    7312: (INFO, "{component} (intmac): the accumulator width is {width} b, "
                 "{multiplier}x the operand width.",
           "The description declares no accumulator width. NPUWattch uses the "
           "int8 x int8 -> int32 convention. To use a different width, declare "
           "the accumulator width in the description."),
    7313: (WARNING, "{component} ({primitive}): {width} b is not an IEEE "
                    "width, so NPUWattch uses fp32 (8, 23).",
           "NPUWattch finds the exponent and mantissa split only for standard "
           "widths. For this width, it uses single precision. The energy and "
           "the area are correct only for fp32. Declare exponent_bits and "
           "mantissa_bits to model the real format."),
    7314: (WARNING, "{component} ({primitive}): no width or exponent/mantissa "
                    "split is declared, so NPUWattch uses fp32.",
           "The description gives no format for this floating-point "
           "component. NPUWattch uses fp32 (e8m23). The energy and the area "
           "are correct only for fp32. Declare exponent_bits and "
           "mantissa_bits in the description."),
    7315: (INFO, "{component} ({primitive}): exponent/mantissa {split} comes "
                 "from the declared {width} b width.",
           "NPUWattch uses the standard split for the width (IEEE 754, or OCP "
           "E4M3 for 8 bits). The formats bf16 and fp16 have the same width. "
           "To model bf16, declare exponent_bits and mantissa_bits."),
    7316: (INFO, "{component} (fpsfu): sfu_segments is not declared, so "
                 "NPUWattch uses a 16-segment PWL table."),
    7317: (WARNING, "{component} ({primitive}): no flit or data width is "
                    "declared, so NPUWattch uses 64 bits.",
           "NPUWattch uses a 64-bit flit for this component. The energy and "
           "the area are correct only for this width. Declare the flit width "
           "of the component in the description."),
    7318: (WARNING, "{component} ({primitive}): no port count is declared, so "
                    "NPUWattch uses 2 ports.",
           "NPUWattch models this component with 2 ports. The energy and the "
           "area are correct only for 2 ports. Declare the port count of the "
           "component in the description."),
    7319: (WARNING, "{component} (d2dlink): no width is declared, so NPUWattch "
                    "uses 64 bits.",
           "NPUWattch models this die-to-die link with a 64-bit width. The "
           "energy and the area are correct only for this width. Declare the "
           "width of the link in the description."),

    # -- 74xx dram --------------------------------------------------------------
    7401: (INFO, "{component}: {pj_per_bit:g} pJ/bit from --energy-table "
                 "{table!r} ({file}: {split})."),
    7402: ("HarnessError",
           "{component}: DRAM type {dram_type!r} has no energy table in "
           "{table_dir}/.",
           "NPUWattch has energy tables for the Accelergy DRAM types LPDDR4, "
           "LPDDR, DDR3, GDDR5, HBM2 and HMC. Declare one of these types. Or "
           "give an energy table with --energy-table."),
    7403: (INFO, "{component} (DRAM type {dram_type}): {pj_per_bit:g} pJ/bit "
                 "from the shipped table {file}.",
           "To use a different table, give --energy-table."),
    7404: ("HarnessError",
           "{component}: no DRAM type is declared, and the fallback table "
           "{table_dir}/{file} is not available.",
           "Without a DRAM type, NPUWattch uses the fallback table. This table "
           "is not in the installation. Declare an Accelergy DRAM type. Or "
           "give an energy table with --energy-table."),
    7405: (WARNING, "{component}: no DRAM type is declared, so NPUWattch uses "
                    "the {fallback} table ({file}, {pj_per_bit:g} pJ/bit).",
           "The DRAM energy is correct only if the DRAM is of this type. "
           "Declare an Accelergy DRAM type (LPDDR4, LPDDR, DDR3, GDDR5, HBM2 "
           "or HMC). Or give an energy table with --energy-table."),
    7406: (WARNING, "--energy-table {file} is not used, because the "
                    "description has no DRAM component.",
           "NPUWattch applies an energy table only to a DRAM component. Remove "
           "--energy-table, or add the DRAM component to the description."),

    # -- 75xx accelergy_flattener ---------------------------------------------
    7501: (WARNING, "The flattener has no hierarchy tree to show.",
           "The flattener did not make a hierarchy tree from the input file. "
           "Make sure that the file is an Accelergy v0.4 architecture "
           "description."),
    7502: (INFO, "Architecture Hierarchy Tree:"),
    7503: (INFO, "NPUWattch flattens {path} for the estimator mode."),
    7504: (INFO, "The flattened YAML is in {path}."),
}, retired=(), source=__name__)
