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
    7101: (INFO, "compound component {name!r} ({file}): parsed, but not used"),
    7102: (WARNING, "--vectorless-activity ignored: the Timeloop stats provide "
                    "real activity"),
    7103: (WARNING, "hierarchy view unavailable: {error}"),
    7104: ("CompoundBundleError",
           "element {element!r}: {key} = {value!r} has no value; the Accelergy "
           "component does not declare that attribute as an integer"),
    7105: ("HarnessError",
           "{component}: compound component {compound!r}: {error} (the symbols "
           "of this component are: {symbols})"),
    7106: ("HarnessError",
           "the projection of a Timeloop run must declare `tool: timeloop` "
           "(found: {found})"),
    7107: ("HarnessError",
           "projection: compound {compound!r} has action(s) {actions}; the "
           "Timeloop events are {events}"),
    7108: ("HarnessError", "{component}: projection {compound}.{action}: {error}"),
    7109: (INFO, "{component}: attribute user_component {entry!r} — the user "
                 "component library entry gives its cost (the class "
                 "{comp_class!r} is for Timeloop only)"),
    7110: (INFO, "{component}: class {comp_class!r} is the compound component "
                 "{compound!r} ({elements})"),
    7111: (INFO, "{component}: class {comp_class!r} uses the user component "
                 "library entry {entry!r}"),
    7112: (INFO, "{component}: declared a regfile but holds more than 32 Kib — "
                 "modeled with the SRAM estimator"),
    7113: (WARNING, "{component}: {error} — NOT modeled: its energy and area are "
                    "NOT included in these results"),
    7114: (WARNING, "{count} component(s) have no NPUWattch primitive and are "
                    "NOT modeled (their energy and area are NOT included in "
                    "these results): {components} — to include one, define its "
                    "class as a compound component (--compound-components) or "
                    "add it to the user component library (--user-components)"),
    7115: ("HarnessError",
           "{path}: no enabled components found — is this an Accelergy v0.4 "
           "architecture description?"),
    7116: (INFO, "the description declares technology {declared} but the run "
                 "is evaluated at {node} (--node); NPUWattch models the node it "
                 "is told to"),
    7117: (WARNING, "the description declares technology {declared} but the run "
                    "is evaluated at {node} (--node default); NPUWattch models "
                    "the node it is told to"),
    7118: (INFO, "clock: --clock-mhz {clock_mhz:g} MHz overrides the "
                 "description's {declared_mhz:g} MHz"),
    7119: (INFO, "clock: {clock_mhz:g} MHz, from the description"),
    7120: (INFO, "clock: the description declares none — assuming "
                 "{clock_mhz:g} MHz"),

    # -- 72xx stats -----------------------------------------------------------
    7201: ("TimeloopStatsError",
           "{path}: no '=== <level> ===' blocks found — is this a "
           "timeloop-model/mapper .stats.txt?"),
    7202: ("TimeloopStatsError", "{path}: no positive cycle count found"),
    7203: ("TimeloopStatsError",
           "{path}: no '{pattern}' files found — pass a timeloop-model/mapper "
           "stats file or a directory of per-layer stats files"),
    7204: ("TimeloopStatsError",
           "stats map: level '{level}'{where} must name components (a name, "
           "{{name: N}} for N events per access, or "
           "{{name: {{count: N, action: A}}}})"),
    7205: ("TimeloopStatsError",
           "stats map: level '{level}'{where} must list component names"),
    7206: ("TimeloopStatsError",
           "stats map: level '{level}' has unknown event '{event}' (use "
           "{events})"),
    7207: ("TimeloopStatsError", "stats map: level '{level}' binds nothing"),
    7208: ("TimeloopStatsError",
           "stats map: level '{level}' must be a component name, a list of "
           "names, or {{read|write|op: names}}"),
    7209: ("TimeloopStatsError",
           "{path}: expected a mapping with 'levels:'/'ignore:'"),
    7210: ("TimeloopStatsError",
           "{path}: 'levels' must be a mapping and 'ignore' a list"),
    7211: ("TimeloopStatsError",
           "{path}: unknown key(s) {keys} — the stats map takes 'levels:' and "
           "'ignore:'"),
    7212: ("TimeloopStatsError",
           "stats mode must be 'windows' or 'aggregate', got {mode!r}"),
    7213: ("TimeloopStatsError",
           "stats map names component(s) not in the description: {missing} — "
           "description components are {components}"),
    7214: (WARNING, "stats level '{level}' is ambiguous in the description "
                    "({candidates}) — pick one via --stats-map 'levels:'"),
    7215: (WARNING, "stats level '{level}' declares {stats_instances} "
                    "instance(s) but the description has {declared} for "
                    "'{component}' — are the stats from this architecture?"),
    7216: ("TimeloopStatsError",
           "stats map: level '{level}' names the action '{action}' for the "
           "compound component '{component}' — a compound takes its actions "
           "from projection.yaml"),
    7217: ("TimeloopStatsError",
           "stats map: level '{level}' charges '{component}' with the action "
           "'{action}', but its actions are {actions}"),
    7218: (INFO, "Timeloop stats: {files} file(s), {cycles} cycles, "
                 "{charged}/{total} description component(s) charged ({mode} "
                 "mode); compute charged in the weight-stationary mode "
                 "(Computes -> hold_b)"),
    7219: (WARNING, "stats level(s) with no matching description component: "
                    "{levels} — their activity is NOT charged; rename via "
                    "--stats-map 'levels:' or drop deliberately via 'ignore:'"),
    7220: (INFO, "stats level(s) dropped by the map's 'ignore:': {levels} — "
                 "their energy is deliberately NOT in this run"),
    7221: (WARNING, "{count} description component(s) get no Timeloop activity "
                    "(charged leakage/area only — Timeloop does not model "
                    "them): {components}"),
    7222: (INFO, "stats level '{level}' fans out per --stats-map: {bindings} "
                 "(the same access count charges each listed component)"),
    7223: (INFO, "{component}: charged in the '{mode}' stim mode — the wanted "
                 "mode is not characterized for this primitive"),

    # -- 73xx vocabulary ------------------------------------------------------
    7301: (INFO, "{component} ({primitive}): ignored Accelergy attribute(s) "
                 "{attributes} — no NPUWattch attribute corresponds"),
    7302: (WARNING, "{component} ({primitive}): no word width declared — "
                    "assuming 32 bits"),
    7303: (INFO, "{component} ({primitive}): depth {depth} derived from the "
                 "declared capacity / {width} b word"),
    7304: (WARNING, "{component} ({primitive}): neither depth nor capacity "
                    "declared — assuming 64 entries"),
    7305: (WARNING, "{component} ({primitive}): total depth {depth} is not a "
                    "multiple of {banks} banks — rounded up to {per_bank} words "
                    "per bank"),
    7306: (INFO, "{component} ({primitive}): depth {depth} is the Accelergy "
                 "total over {banks} banks → mem_depth_per_bank {per_bank} "
                 "({capacity} total)"),
    7307: (INFO, "{component} ({primitive}): no port count declared — assuming "
                 "a single shared read-or-write port"),
    7308: (INFO, "{component} ({primitive}): bandwidth {bandwidth} → up to "
                 "{accesses} bank accesses per cycle; each is charged as one "
                 "access event"),
    7309: (WARNING, "{component} ({primitive}): bandwidth {bandwidth} needs "
                    "{accesses} accesses/cycle, more than {banks} bank(s) × "
                    "{ports} port(s) = {slots} — the declared structure cannot "
                    "serve Timeloop's mapping; it would need {needed_banks} "
                    "banks (or more ports)"),
    7310: (WARNING, "{component} (hbm): no word width declared — charging a "
                    "32 B burst (256 bits) per access"),
    7311: (WARNING, "{component} ({primitive}): no operand width declared — "
                    "assuming 8 bits"),
    7312: (INFO, "{component} (intmac): accumulator width {width} b inferred as "
                 "{multiplier}x the operand width — Accelergy declares none "
                 "(int8 x int8 -> int32 convention)"),
    7313: (WARNING, "{component} ({primitive}): {width} b is not an IEEE width "
                    "— assuming single precision (8, 23); declare exponent_bits "
                    "/ mantissa_bits to model the real format"),
    7314: (WARNING, "{component} ({primitive}): no width or exponent/mantissa "
                    "split declared — assuming fp32"),
    7315: (INFO, "{component} ({primitive}): exponent/mantissa {split} inferred "
                 "from the declared {width} b width (IEEE 754); bf16 and fp16 "
                 "share a width — declare the split to distinguish them"),
    7316: (INFO, "{component} (fpsfu): sfu_segments not declared — assuming a "
                 "16-segment PWL table"),
    7317: (WARNING, "{component} ({primitive}): no flit/data width declared — "
                    "assuming 64 bits"),
    7318: (WARNING, "{component} ({primitive}): no port count declared — "
                    "assuming a 2-port element"),
    7319: (WARNING, "{component} (d2dlink): no width declared — assuming 64 "
                    "bits"),

    # -- 74xx dram --------------------------------------------------------------
    7401: (INFO, "{component}: {pj_per_bit:g} pJ/bit from --energy-table "
                 "{table!r} ({file}: {split})"),
    7402: ("HarnessError",
           "{component}: DRAM type {dram_type!r} has no energy table in "
           "{table_dir}/ — declare an Accelergy type (LPDDR4, LPDDR, DDR3, "
           "GDDR5, HBM2, HMC) or pass --energy-table"),
    7403: (INFO, "{component} (DRAM type {dram_type}): {pj_per_bit:g} pJ/bit "
                 "from the shipped table {file} (override with --energy-table)"),
    7404: ("HarnessError",
           "{component}: no DRAM type declared and the fallback table "
           "{table_dir}/{file} is not available — declare an Accelergy type or "
           "pass --energy-table"),
    7405: (WARNING, "{component}: no DRAM type declared — priced with the "
                    "{fallback} table ({file}, {pj_per_bit:g} pJ/bit); declare "
                    "an Accelergy type (LPDDR4, LPDDR, DDR3, GDDR5, HBM2, HMC) "
                    "or pass --energy-table"),
    7406: (WARNING, "--energy-table {file} supplied but the description has no "
                    "DRAM component — the table is unused"),

    # -- 75xx accelergy_flattener ---------------------------------------------
    7501: (WARNING, "No tree to display"),
    7502: (INFO, "Architecture Hierarchy Tree:"),
    7503: (INFO, "Flattening {path} for estimator mode..."),
    7504: (INFO, "Flattened YAML written to: {path}"),
}, retired=(), source=__name__)
