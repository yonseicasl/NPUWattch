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
    1002: (ERROR, "Estimator {estimator!r} declares no training entrypoint.",
           "The ESTIMATOR_SPEC of this estimator has no train entrypoint. "
           "Thus npuwattch -t cannot train its models. "
           "Use the training script of the estimator. "
           "The next INFO line gives the script, if NPUWattch knows it."),
    1003: (INFO, "Train the models of this estimator with {script}.",
           "The script controls the group split, the adaptive loss and the "
           "checkpoint files. Run the script directly."),
    1004: (INFO, "NPUWattch runs in training mode."),
    1005: (INFO, "Estimator: {estimator}"),
    1006: (INFO, "Model type: {model_type}"),
    1007: (INFO, "Training data: {path}"),
    1008: (INFO, "Epochs: {epochs}, Batch size: {batch_size}, LR: {lr}"),
    1009: (ERROR, "The training failed: {error}",
           "The estimator stopped the training with an error. "
           "The text after the colon comes from the estimator. "
           "Correct the training data or the training options."),
    1010: (INFO, "The training is complete."),
    1011: (INFO, "The description is a native NPUWattch description."),
    1012: (WARNING, "--tree: NPUWattch cannot show the hierarchy view: {error}",
           "NPUWattch did not make the hierarchy view of the description. "
           "The hierarchy view is only a view. "
           "The energy calculation continues, and its results are correct. "
           "Examine the error text to find the cause."),
    1013: (ERROR, "Native mode accepts one activity CSV, but {count} were "
                  "given: {paths}",
           "In native mode, NPUWattch reads one activity CSV with -l. "
           "One activity CSV can have many windows. "
           "Give one activity CSV."),
    1014: (INFO, "Technology: {node} / {transistor} / {corner} / "
                 "{voltage_offset_V:+.3f} V / {temperature_C} C."),
    1015: (ERROR, "NPUWattch cannot read the activity CSV {path}: {error}",
           "The file does not exist, or its format is not correct. "
           "Make sure that the path is correct. "
           "Make sure that the file is a native activity CSV."),
    1016: (INFO, "Activity: {path} ({rows} rows)."),
    1017: (INFO, "Activity: {path} ({rows} rows, total_cycles={total_cycles})."),
    1018: (ERROR, "{error}",
           "NPUWattch found an error in the input, and the run stopped. "
           "The text comes from the part of NPUWattch that found the error. "
           "Correct the input."),
    1019: (CRITICAL, "The energy calculation stopped with an internal error: "
                     "{error}",
           "An unexpected exception occurred in NPUWattch. "
           "Run the command again with -v 2 to show the traceback. "
           "Send the error text and the traceback to the NPUWattch "
           "developers."),
    1020: (WARNING, "The report has no hierarchy view: {error}",
           "NPUWattch did not make the hierarchy view of the description. "
           "The report shows the energy results without this view. "
           "The energy results are correct. "
           "Examine the error text to find the cause."),
    1021: (INFO, "NPUWattch runs in estimator mode."),
    1022: (ERROR, "Estimator mode accepts one description, but {count} were "
                  "given.",
           "In estimator mode, NPUWattch reads one native description with "
           "-d. Give one description."),
    1023: (ERROR, "The description {path} does not exist.",
           "NPUWattch did not find the file that -d gives. "
           "Make sure that the path is correct."),
    1024: (ERROR, "{path} is not a native NPUWattch description.",
           "A native description has the top-level key npuwattch. "
           "This file does not have this key. "
           "Give an Accelergy or Timeloop architecture YAML to the timeloop "
           "harness. The next INFO line gives the command."),
    1025: (INFO, "Use this command for an Accelergy or Timeloop architecture "
                 "YAML: npuwattch --harness timeloop --arch-yaml {path}",
           "The -d option reads only a native NPUWattch description. "
           "The timeloop harness reads an Accelergy or Timeloop description. "
           "You can also give --node and --clock-mhz to the harness."),
    1026: (INFO, "Harness mode: {harness}"),
    1027: (CRITICAL, "The harness stopped with an internal error: {error}",
           "An unexpected exception occurred in the harness. "
           "Run the command again with -v 2 to show the traceback. "
           "Send the error text and the traceback to the developers of the "
           "harness."),
    1028: (WARNING, "--tree: this run has no hierarchy view.",
           "The harness did not make a hierarchy view for this run. "
           "The warnings of the harness below give the cause. "
           "The hierarchy view is only a view, and the energy results are "
           "correct."),
    1029: (INFO, "Per-kernel provenance ({count} kernel(s)):"),
    1030: (INFO, "Wrote native description: {path}"),
    1031: (INFO, "Wrote native activity:    {path}"),
    1032: (INFO, "Wrote report:      {path}"),
    1033: (INFO, "Wrote report data: {path}"),
    1034: (WARNING, "--report: NPUWattch cannot write the report: {error}",
           "NPUWattch did not write the HTML report or the report.json file. "
           "The console results of the run are correct. "
           "Examine the error text to find the cause. "
           "Make sure that you can write to the output directory."),
    1035: (INFO, "Per-{term} energy ({count} {noun}):"),
    1036: (INFO, "GEMM kernels (mac/fused): {gemm_pJ:.4g} pJ ({gemm_windows} "
                 "window(s)), non-GEMM kernels: {non_gemm_pJ:.4g} pJ "
                 "({non_gemm_windows} window(s), {percent:.1f}% of total)."),
    1037: (INFO, "Per-{term} component energy (dynamic, pJ):"),
    1038: (INFO, "{count} component(s) with no dynamic activity are not in "
                 "the table.",
           "These components have no dynamic energy in any window. "
           "The energy summary below gives their leakage energy."),
    1039: (INFO, "Energy summary: {tag}"),
    1040: (INFO, "DRAM device energy ({components}): activation "
                 "{activate_pJ:.4g} pJ ({activate_pct:.1f}%), transfer "
                 "{transfer_pJ:.4g} pJ ({transfer_pct:.1f}%, read {read_pJ:.4g}, "
                 "write {write_pJ:.4g}), refresh {refresh_pJ:.4g} pJ "
                 "({refresh_pct:.1f}%)."),

    # -- 11xx: argument parser (npuwattch_parser) -----------------------------
    1101: (ERROR, "Command line: {message}",
           "The command line is not correct. "
           "The text after the colon comes from the Python argument parser. "
           "Run npuwattch --help to see the options."),
    1102: (ERROR, "--harness and -d/--description cannot be used together.",
           "A harness makes the native description from the simulator "
           "files. Thus a harness run does not read a description. "
           "For a harness run, give --harness and its inputs. "
           "For a native run, give -d without --harness."),
    1103: (ERROR, "{flags} can be used only with --harness.",
           "These flags are inputs or options of a harness. "
           "Give --harness to select the harness. "
           "Run npuwattch --help to see the flags of each harness."),
    1104: (ERROR, "{flag} needs {needed_flag}.",
           "Some harness inputs work only together with a second input. "
           "Give the second input also."),
    1105: (ERROR, "--vectorless-activity applies only to a vectorless run.",
           "A vectorless run has no activity log. "
           "NPUWattch uses the vectorless activity in place of the activity "
           "log. A vectorless run is -d without -l, or a harness that has no "
           "activity input. Remove --vectorless-activity from the command "
           "line."),
    1106: (ERROR, "--vectorless-activity: {flag} gives real activity, so the "
                  "run is not vectorless.",
           "--vectorless-activity applies only to a vectorless run. "
           "A harness run with an activity input is not vectorless. "
           "Remove --vectorless-activity, or remove the activity input."),
    1107: (ERROR, "--vectorless-activity: the {harness!r} harness reads real "
                  "activity from its logs.",
           "--vectorless-activity applies only to a vectorless run. "
           "This harness always reads the activity from the simulator logs. "
           "Thus a run of this harness is not vectorless. "
           "Remove --vectorless-activity."),
    1108: (ERROR, "--vectorless-activity is {value}, but it must be in the "
                  "range (0, 1].",
           "The vectorless activity is the fraction of random switching. "
           "A value of 1 is full random switching. "
           "Give a value that is more than 0 and not more than 1."),
    1109: (ERROR, "Flatten mode (-f/--flatten) needs -i/--input.",
           "The flatten mode reads one Accelergy v0.4 YAML file. "
           "Give the file with -i."),
    1110: (ERROR, "-i is not a harness input (harness inputs: {inputs}).",
           "A harness reads each input from its own named flag. "
           "Give each input with its flag. "
           "Run npuwattch --help to see the flags of each harness."),
    1111: (ERROR, "-i is not a harness input (harness inputs: {inputs}, or "
                  "{usage_hint}).",
           "A harness reads each input from its own named flag. "
           "Give each input with its flag, or use the method in the "
           "message. Run npuwattch --help to see the flags of each harness."),
    1112: (ERROR, "--harness {harness}: required input(s) are missing: "
                  "{missing}",
           "The harness cannot run without these inputs. "
           "Give each input with its flag. "
           "The text after each flag tells what the input is."),
    1113: (ERROR, "{flag} is not an option of the {harness!r} harness.",
           "Each harness has its own options. "
           "Remove the flag, or select a harness that has this option. "
           "Run npuwattch --help to see the options of each harness."),
    1114: (ERROR, "Training mode (-t/--train) needs {flag}.",
           "The training mode needs --train-estimator, --train-type and "
           "--train-csv. Give the missing flag."),
    1115: (ERROR, "Estimator mode needs -d/--description.",
           "The estimator mode reads one native description. "
           "Give the description with -d. "
           "To use a simulator, give --harness and its inputs."),

    # -- 12xx: estimator host (npuwattch_estimator_host) ----------------------
    1201: ("EstimatorRootError", "NPUWattch did not find the estimator root.",
           "NPUWattch looks for ./src/npuwattch_estimators and for the "
           "installed npuwattch_estimators package. It found neither. "
           "Install NPUWattch with its estimators, or run npuwattch from the "
           "repository root."),
    1202: (INFO, "Estimator root: {path}"),
    1203: (WARNING, "The estimator root has no estimator modules.",
           "NPUWattch found the estimator root, but no module in it. "
           "Without estimators, NPUWattch cannot calculate energy or area. "
           "Make sure that the installation is complete."),
    1204: (INFO, "Modules found:"),
    1205: (ERROR, "NPUWattch cannot load the estimator module '{module}': "
                  "{error}",
           "The import of the module stopped with an error. "
           "NPUWattch does not use this estimator. "
           "Examine the error text. "
           "Make sure that the dependencies of the estimator are installed."),
    1206: (ERROR, "The estimator module '{module}' does not exist "
                  "(available: {available}).",
           "No estimator module has this name. "
           "Use one of the available names."),
    1207: (ERROR, "NPUWattch cannot load the namespace of the estimator "
                  "module '{module}'.",
           "The module did not load correctly. "
           "Examine the earlier messages to find the cause."),
    1208: (ERROR, "The estimator module '{module}' has no callable "
                  "'{function}' (available: {available}).",
           "NPUWattch tried to call a function that the module does not "
           "define. Correct the ESTIMATOR_SPEC or the module."),
    1209: (ERROR, "{module}.{function} stopped with an exception: {error}",
           "The estimator function raised an exception. "
           "NPUWattch got no result from this function. "
           "Examine the error text. "
           "Make sure that the attributes of the component are correct."),
    1210: (ERROR, "The estimator module '{module}' has no ESTIMATOR_SPEC.",
           "Each estimator module declares its entrypoints in ESTIMATOR_SPEC. "
           "Without it, NPUWattch cannot call the module. "
           "Add ESTIMATOR_SPEC to the module."),
    1211: (ERROR, "The estimator module '{module}' does not declare the "
                  "entrypoint '{entrypoint}'.",
           "The ESTIMATOR_SPEC of the module has no entry for this "
           "entrypoint. Thus NPUWattch cannot call it. "
           "Add the entrypoint to ESTIMATOR_SPEC, or use a different "
           "estimator."),
    1212: (ERROR, "Estimator '{module}' does not exist, so it gives no "
                  "{metric} value.",
           "NPUWattch did not find an estimator with this name. "
           "The result has no value for this metric. "
           "Use the name of an installed estimator."),
    1213: (ERROR, "Estimator '{module}' does not exist, so NPUWattch cannot "
                  "train it.",
           "NPUWattch did not find an estimator with this name. "
           "Give the name of an installed estimator with --train-estimator."),
    1214: (ERROR, "Estimator '{module}' does not exist.",
           "NPUWattch did not find an estimator with this name. "
           "Use the name of an installed estimator."),

    # -- 13xx: description database (npuwattch_db) ----------------------------
    1301: (INFO, "NPUWattch builds the description database from {source}."),
    1302: (WARNING, "The YAML file is empty.",
           "The description file has no content. "
           "Thus the database has no components. "
           "Make sure that the file is the correct description."),
    1303: (INFO, "The description database has {components} components "
                 "with {instances} instances in total."),
    1304: (INFO, "Registered components:"),

    # -- 18xx: shared wrappers (this module) ----------------------------------
    1801: (INFO, "{message}",
           "This message comes from a plugin that does not use the message "
           "catalog. NPUWattch shows the text of the plugin without change."),
    1802: (WARNING, "{message}",
           "This message comes from a plugin that does not use the message "
           "catalog. NPUWattch shows the text of the plugin without change. "
           "Refer to the documentation of the plugin for its meaning."),
    1803: (ERROR, "{message}",
           "This message comes from a plugin that does not use the message "
           "catalog. NPUWattch shows the text of the plugin without change. "
           "Refer to the documentation of the plugin for its meaning."),
    1804: (WARNING, "{subject}: {message}",
           "This message comes from an estimator or a plugin. "
           "It is about one component or element, which is the subject "
           "before the colon. NPUWattch shows the text of the plugin without "
           "change."),

    # -- 19xx: message system (npuwattch_parser, npuwattch_console) ----------
    1901: (ERROR, "--suppress: {problem}",
           "--suppress takes one or more codes of INFO or WARNING messages. "
           "The code does not exist, or its message is an ERROR or CRITICAL "
           "message. Run npuwattch --list-messages to see the codes."),
    1902: (INFO, "Message summary: {critical} CRITICAL, {error} ERROR, "
                 "{warning} WARNING, {info} INFO."),
    1903: (INFO, "Message summary: {critical} CRITICAL, {error} ERROR, "
                 "{warning} WARNING, {info} INFO, {suppressed} suppressed "
                 "({codes})."),
    1904: (ERROR, "--explain: {problem}",
           "--explain takes one message code, such as NW-6002. "
           "The code is not correct, or it has no catalog entry. "
           "Run npuwattch --list-messages to see the codes."),

    # -- 20xx: attribute names (naming) ---------------------------------------
    2001: ("NamingError", "{component} ({primitive}): attribute '{key}' is a "
                          "legacy alias of '{target}'.",
           "Each concept has one attribute name. "
           "NPUWattch does not accept a legacy alias. "
           "Rename the attribute to the canonical name in the message. "
           "The list npuwattch.naming.CANONICAL gives the canonical names."),
    2002: (WARNING, "{component} ({primitive}): attribute '{key}' is not in "
                    "the canonical vocabulary.",
           "No estimator reads this attribute. "
           "Its value has no effect on the results. "
           "Make sure that the attribute name is spelled correctly. "
           "The list npuwattch.naming.CANONICAL gives the canonical names."),
    2003: ("NamingError", "{component} ({primitive}): required attribute(s) "
                          "{missing} are missing (required: {required}).",
           "The estimator of this primitive cannot calculate a result "
           "without these attributes. "
           "Add the missing attributes to the component."),
    2004: (WARNING, "{component} ({primitive}): '{key}' is not a parameter "
                    "of {primitive}.",
           "The attribute name is canonical, but the estimator of this "
           "primitive does not read it. "
           "NPUWattch ignores the attribute, and its value has no effect on "
           "the results. Remove the attribute, or make sure that the class "
           "is correct."),

    # -- 21xx: user component library (user_components) -----------------------
    2101: ("UserComponentError", "{where}: user_components is not a mapping.",
           "The user_components key holds a mapping from component names to "
           "their entries. Correct the YAML structure. "
           "The tutorial has an example library."),
    2102: ("UserComponentError", "{where}: {what} is {value!r}, but it must "
                                 "be a positive number.",
           "This value must be more than 0. Give a positive number."),
    2103: ("UserComponentError", "{where}: {what} is {value!r}, but it must "
                                 "be a number of 0 or more.",
           "This value cannot be negative. Give a number of 0 or more."),
    2104: ("UserComponentError", "{where}: the component name {name!r} is "
                                 "not valid.",
           "A component name has lowercase letters, digits and underscores. "
           "The first character is a letter. "
           "Rename the component."),
    2105: ("UserComponentError", "{where}: {name}: the entry is not a "
                                 "mapping.",
           "Each user component is a mapping of its keys, such as reference, "
           "area_um2 and actions. Correct the YAML structure of the entry."),
    2106: ("UserComponentError", "{where}: {name}: unknown key(s) {keys}",
           "The entry has keys that NPUWattch does not know. "
           "Make sure that the key names are spelled correctly. "
           "Remove the keys that are not necessary."),
    2107: ("UserComponentError", "{where}: {name}: reference.node is "
                                 "missing.",
           "The key reference.node gives the technology node of the area "
           "and the energy values. "
           "Add reference.node to the entry, such as node: 7nm."),
    2108: ("UserComponentError", "{where}: {name}: design_class "
                                 "{design_class!r} is not one of {classes}.",
           "The design_class key has a fixed set of values. "
           "Use one of the values in the message."),
    2109: ("UserComponentError", "{where}: {name}: actions is not a mapping "
                                 "with one or more actions.",
           "The actions key maps each action name to its energy. "
           "Give one or more actions, each with an energy_pJ value."),
    2110: ("UserComponentError", "{where}: {name}.actions.{action}: the "
                                 "action has no energy_pJ key.",
           "Each action is a mapping with the key energy_pJ. "
           "The value is the energy of one action in pJ. "
           "Give energy_pJ as a number."),
    2111: ("UserComponentError", "{where}: {name}.characterized is not a "
                                 "mapping of nodes to values.",
           "The characterized key maps each technology node to the area and "
           "the action energies at that node. "
           "Correct the YAML structure."),
    2112: ("UserComponentError", "{where}: {name}: the node or its values "
                                 "are not correct.",
           "Each key of characterized is a technology node, such as 7nm. "
           "Its value is a mapping of the area and the action energies. "
           "Correct the node name or its values."),
    2113: ("UserComponentError", "The user component library {path} does "
                                 "not exist.",
           "NPUWattch did not find the file that --user-components gives. "
           "Make sure that the path is correct."),
    2114: ("UserComponentError", "{path} is not valid YAML: {error}",
           "NPUWattch cannot parse the user component library. "
           "The error text gives the line of the problem. "
           "Correct the YAML syntax."),
    2115: ("UserComponentError", "{path} has no top-level user_components "
                                 "key.",
           "A user component library has the top-level key user_components. "
           "Add this key, and put the components below it."),
    2116: (INFO, "User component {name!r} ({source}) is in the library, but "
                 "the run does not use it.",
           "No component of the run has this class. "
           "No action is necessary."),

    # -- 22xx: description and activity emitter (arch_synth) ------------------
    2201: ("EmitterError", "{element}: capacity_kbit and capacity_bit are "
                           "both given.",
           "An SRAM element gives its capacity with one key. "
           "Remove capacity_kbit or capacity_bit."),
    2202: (WARNING, "{element}: the SRAM estimator is not available, so the "
                    "element is not in the description.",
           "NPUWattch cannot import npuwattch_estimators.sram. "
           "This element gives only its capacity, so NPUWattch needs the "
           "SRAM estimator to find its macros. "
           "The energy and the area of this element are not in the results. "
           "Install the SRAM estimator."),
    2203: (WARNING, "{element}: the access energy is charged to the primary "
                    "part, and '{element}.tail' has leakage and area only.",
           "The SRAM solver divided the capacity of this element into a "
           "primary part and a tail part. "
           "The unit cost of the primary part includes the accesses of both "
           "parts. Thus the tail part has only leakage energy and area."),
    2204: (WARNING, "Window {window}: the window has no exec cycles, so its "
                    "cycle_start and cycle_end are {start}.",
           "The simulator log gives no exec cycles for this window. "
           "NPUWattch uses 0 cycles for the window. "
           "The values that use the cycle count of this window, such as "
           "power, are not correct. "
           "Make sure that the simulator log is complete."),
    2205: (WARNING, "Window {window}: action {action!r} on element "
                    "{element!r} counts flits as words.",
           "To change flits to words, NPUWattch needs the word width of the "
           "element and the BookSim flit size. "
           "One of the two values is missing. "
           "Thus NPUWattch counts one flit as one word. "
           "The access count and the energy of this element are approximate."),
    2206: (WARNING, "Window {window}: crossbar element {element!r} has no "
                    "port count, so action {action!r} counts one flit as one "
                    "cycle.",
           "To change flits to crossbar cycles, NPUWattch divides the flit "
           "count by the port count. "
           "This element has no port count. "
           "Thus the crossbar energy is approximate. "
           "Give the port count of the crossbar element in the description."),
    2207: (WARNING, "Window {window}: element {element!r} has no word width, "
                    "so action {action!r} counts {unit!r} as words.",
           "To change bytes or vectors to words, NPUWattch needs the word "
           "width of the element. "
           "The word width comes from the capacity of the element. "
           "Thus the access count and the energy of this element are "
           "approximate. Give the capacity of the element in the "
           "description."),
    2208: (WARNING, "Window {window} ({kernel}): no action of projection "
                    "{tool!r} uses the activity stat {stat!r}={value}.",
           "The projection maps activity stats to the actions of the "
           "elements. No action uses this stat, so its energy is not in the "
           "results. The projection can omit the stat intentionally, or the "
           "projection can be incomplete. "
           "To accept the stat, add it with a reason to the waivers of the "
           "projection."),
    2209: (INFO, "Activity stat {stat!r} (total {total} in {windows} "
                 "window(s)) is not charged, because projection {tool!r} "
                 "waives it: {reason}",
           "The waivers of the projection list the stats that have no "
           "energy in NPUWattch. The reason comes from the projection. "
           "No action is necessary."),

    # -- 30xx: unit-cost providers (energy.unit_cost) -------------------------
    3001: ("NoModelError", "There is no model for class {primitive!r}.",
           "NPUWattch has no estimator for this class. "
           "Give the area and the action energies of the component in the "
           "user component library. "
           "Use --user-components to give the library."),
    3002: ("EnergyTableError", "NPUWattch cannot read the link energy table "
                               "{path}: {error}",
           "The link energy table is a data file of the NPUWattch package. "
           "The file is missing, or its content is not correct. "
           "Make sure that the installation is complete."),
    3003: ("EnergyTableError", "Link energy table {path}: energy_pj_per_bit "
                               "is {value!r}, but it must be a positive "
                               "number.",
           "The value energy_pj_per_bit is the energy of one bit on the link "
           "in pJ. The value must be more than 0. "
           "Correct the value in the table."),
    3004: ("ProviderChainError", "The {provider} provider got primitive "
                                 "{primitive!r} and has no fallback provider.",
           "This provider gives the cost of one primitive. "
           "It sends each other primitive to its fallback provider. "
           "This provider has no fallback provider. "
           "This is an internal error. "
           "Send the error text to the NPUWattch developers."),

    # -- 31xx: energy calculation (energy.aggregate) --------------------------
    3101: (WARNING, "{component}: {events:g} access events are more than its "
                    "{instances} x {cycles} cycles, so its idle energy is 0.",
           "Each instance can serve one access event in each cycle. "
           "The activity has more events than the instances can serve in "
           "the cycles of the run. "
           "NPUWattch sets the idle energy of the component to 0. "
           "Make sure that the activity counts and the cycle count are "
           "correct."),
    3102: (WARNING, "The run has no exec cycles, so the idle energy of "
                    "{components} is charged for each access event.",
           "NPUWattch calculates the clocked idle energy from the exec "
           "cycles of the run. The activity has no exec cycles. "
           "Thus NPUWattch charges the idle energy for each access event. "
           "The idle energy of these components is approximate. "
           "Give the cycles of each window in the activity."),
    3103: ("AggregateError", "The native description has no "
                             "clock.frequency_MHz.",
           "NPUWattch needs the clock frequency to change cycles to time. "
           "The description has no clock.frequency_MHz, and the run has no "
           "default_clock_mhz. "
           "Add clock.frequency_MHz to the description."),
    3104: ("NoModelError", "{component}: there is no model for class "
                           "{primitive!r}.",
           "NPUWattch has no estimator for this class. "
           "Give the area and the action energies of the component in the "
           "user component library. "
           "Use --user-components to give the library."),

    # -- 32xx: continuous node axis (energy.node_scaling) ---------------------
    3201: ("NodeError", "Technology node {value!r} is not a valid length in "
                        "nm.",
           "A technology node is a length in nm, such as 7nm or 12.5nm. "
           "Correct the node."),
    3202: ("NodeError", "Technology node {value!r} is not a positive length.",
           "A technology node must be more than 0 nm. "
           "Correct the node."),
    3203: ("ProviderChainError", "resolve_node got an empty set of "
                                 "characterized nodes.",
           "An estimator gave no characterized nodes. "
           "This is an internal error of the estimator. "
           "Send the error text to the developers of the estimator."),
    3204: (WARNING, "Node {requested_nm:g} nm is outside the supported "
                    "envelope {envelope_lo_nm:g}-{envelope_hi_nm:g} nm "
                    "(characterized {char_lo_nm:g}-{char_hi_nm:g} nm), so "
                    "NPUWattch uses {eval_nm:g} nm.",
           "The supported envelope is the characterized node range plus "
           "and minus 50 percent. "
           "NPUWattch moves the node to the nearest limit of the envelope. "
           "The results are for that node, not for the requested node. "
           "Use a node in the envelope."),
    3205: (WARNING, "Node {requested_nm:g} nm is outside the characterized "
                    "range {char_lo_nm:g}-{char_hi_nm:g} nm, so NPUWattch "
                    "extrapolates from {lo} and {hi}.",
           "NPUWattch extrapolates the results in log scale from the trend "
           "of the two nearest characterized nodes. "
           "The results are a first-order estimate. "
           "Use a characterized node for the best accuracy."),
    3206: (INFO, "Node {requested_nm:g} nm is not a characterized node, so "
                 "NPUWattch interpolates between {lo} and {hi} in log scale."),

    # -- 33xx: vectorless activity (energy.vectorless) ------------------------
    3301: ("VectorlessError", "The vectorless activity is {activity}, but it "
                              "must be in the range (0, 1].",
           "The vectorless activity is the fraction of random switching. "
           "A value of 1 is full random switching. "
           "Give a value that is more than 0 and not more than 1."),
    3302: (INFO, "VECTORLESS estimate: each component is charged at "
                 "{activity:.0%} of random switching.",
           "The run has no activity log. "
           "Thus NPUWattch charges each component at a fixed fraction of "
           "random switching. "
           "Crossbar components use the measured valid25 mode in place of "
           "this fraction. "
           "The dynamic values are energies for each cycle. "
           "The average power is the steady-state value."),
    3303: (INFO, "User component(s) {components} have no random action, so "
                 "this VECTORLESS run charges their area and leakage only.",
           "A vectorless run charges each user component with its random "
           "action. These components have no random action in the user "
           "component library. "
           "Thus their dynamic energy is not in the results. "
           "To include it, add a random action to the library."),
    3304: (INFO, "{count} capacity '.tail' part(s) are charged leakage and "
                 "area only.",
           "The unit cost of the primary part includes the access energy of "
           "its tail part. No action is necessary."),

    # -- 34xx: DRAM energy tables (energy.dram_table) -------------------------
    3401: ("EnergyTableError", "Energy table {path}: {key} is {value!r}, but "
                               "it must be a positive number.",
           "Each energy value of the table must be more than 0. "
           "Correct the value in the table."),
    3402: ("EnergyTableError", "The energy table {path} does not exist.",
           "NPUWattch did not find the file that --energy-table gives. "
           "Make sure that the path is correct."),
    3403: ("EnergyTableError", "Energy table {path} is not valid YAML: "
                               "{error}",
           "NPUWattch cannot parse the energy table. "
           "The error text gives the line of the problem. "
           "Correct the YAML syntax."),
    3404: ("EnergyTableError", "Energy table {path}: the top level is not a "
                               "mapping.",
           "The top level of an energy table is a mapping with the keys name "
           "and offchip_dram. Correct the YAML structure."),
    3405: ("EnergyTableError", "Energy table {path} has no 'name' key.",
           "The name key gives the name of the table, such as HBM2. "
           "NPUWattch compares this name with the [Config/Energy] echo in "
           "the simulator log. "
           "Add the name key to the table."),
    3406: ("EnergyTableError", "Energy table {path} has no 'offchip_dram' "
                               "mapping.",
           "The offchip_dram mapping holds the DRAM energy values. "
           "Add the offchip_dram mapping to the table."),
    3407: ("EnergyTableError", "Energy table {path}: "
                               "offchip_dram.transfer_pj_per_bit is empty or "
                               "is not a mapping.",
           "The mapping transfer_pj_per_bit gives the energy of each per-bit "
           "transfer term in pJ. Give one or more terms."),

    # -- 36xx: provider chain (energy.provider_factory) -----------------------
    3601: (WARNING, "Estimator {estimator!r}: the unit_cost_provider is not "
                    "available: {error}",
           "NPUWattch cannot make the unit-cost provider of this estimator. "
           "The run continues without this estimator. "
           "If a component needs this estimator, the run stops with NW-3104. "
           "Examine the error text to find the cause."),

    # -- 40xx: HTML and JSON report (report.html) -----------------------------
    4001: ("ReportError", "Report: the run has no windows.",
           "The report shows the energy of each window. "
           "This run has no window, so NPUWattch cannot make the report. "
           "Make sure that the activity has one or more windows."),
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
