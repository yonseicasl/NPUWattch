"""The message catalog of the harness registry, the run inputs, the
vocabulary and the compounds (NW-5000 to NW-5999).

See ``npuwattch.diagnostics`` for the rules. Blocks:

- 50xx: ``registry`` (and the package ``__init__``).
- 51xx: ``run_inputs``.
- 52xx: ``vocabulary``.
- 53xx-54xx: ``compounds`` (``compounds/loader.py``).

Add a new entry at the end of its block. Do not renumber an entry and do not
use a number again: add a removed number to ``retired``.
"""

from npuwattch.diagnostics import register

_H = "HarnessError"
_V = "VocabularyError"
_C = "CompoundBundleError"

register("NW", {
    # -- 50xx registry ------------------------------------------------------
    5001: (_H, "Harness package {package!r}: the HARNESS_SPEC has no 'name'.",
           "NPUWattch selects a harness by the 'name' in its HARNESS_SPEC. "
           "Add a 'name' string to the HARNESS_SPEC of the package."),
    5002: (_H, "Harness {harness!r}: 'inputs' in the HARNESS_SPEC is empty or "
               "is not a dict.",
           "The 'inputs' dict declares the input files and directories of the "
           "harness. Each key is an input name. Each value is a dict with the "
           "flag, the kind and the hint of the input. Declare one or more "
           "inputs."),
    5003: (_H, "Harness {harness!r}: 'ingest' in the HARNESS_SPEC is not "
               "callable.",
           "NPUWattch calls the 'ingest' function to convert the simulator "
           "output into activity. Set 'ingest' to a function."),
    5004: (_H, "Harness {harness!r}: flag {flag} has two meanings, {first!r} "
               "and {second!r}.",
           "Two harnesses can use the same CLI flag only for the same input or "
           "option name. This harness uses the flag for a different name. "
           "Give the input or the option of this harness a different flag."),
    5005: (_H, "Harness {harness!r} is not available (available harnesses: "
               "{available}).",
           "NPUWattch did not find a harness package with this name. A harness "
           "package that does not import is not available. Give one of the "
           "available names with --harness."),
    5006: (_H, "Harness {harness!r}: the inputs {unknown} are not declared "
               "(declared: {declared}).",
           "The harness accepts the inputs that its HARNESS_SPEC declares. "
           "Remove the unknown inputs. Or use the name of a declared input."),
    5007: (_H, "Harness {harness!r}: the required input {input_name!r} "
               "({flag}) is missing: {hint}",
           "The harness cannot run without this input. Give the input with "
           "its flag."),
    5008: (_H, "Harness {harness!r}: the required input {input_name!r} "
               "({flag}) is missing.",
           "The harness cannot run without this input. Give the input with "
           "its flag."),
    5009: (_H, "Harness {harness!r}: the input {input_name!r} is not a "
               "{expected}: {path}",
           "The path does not exist, or it is not of the kind that the "
           "harness reads. Make sure that the path is correct. Give a path "
           "of the kind that the message shows."),

    # -- 51xx run_inputs ----------------------------------------------------
    5101: (_H, "{file_name} is not in {run_dir}, and {flag} is not given.",
           "The harness needs this definition file. Without the flag, "
           "NPUWattch looks for the file in the directory of the run inputs. "
           "Put the file in that directory. Or give the file with the flag "
           "in the message."),
    5102: (_H, "The compound components or the projection of the run are not "
               "correct: {error}",
           "NPUWattch checked the compound components file and the projection "
           "file of the run. The text after the colon gives the problem and "
           "its own NW code. Use npuwattch --explain with that code. Correct "
           "the file."),
    5103: (_H, "The user component library is not correct: {error}",
           "NPUWattch checked the user component library of the run. The text "
           "after the colon gives the problem and its own NW code. Use "
           "npuwattch --explain with that code. Correct the library file."),

    # -- 52xx vocabulary ----------------------------------------------------
    5201: (_V, "The vocabulary table {path} does not exist.",
           "Each harness reads its vocabulary table from definitions/"
           "vocabulary.yaml in its package. Make sure that the file exists. "
           "If the file of an installed harness is missing, install "
           "NPUWattch again."),
    5202: (_V, "{path}: the vocabulary table is not valid YAML: {error}",
           "NPUWattch could not parse the vocabulary table. The YAML error "
           "gives the line and the column of the problem. Correct the YAML "
           "syntax at that position."),
    5203: (_V, "{path}: the vocabulary table is not a mapping.",
           "The top level of the table maps section names to sections. "
           "Write the sections, such as classes and attributes, as keys at "
           "the top level."),
    5204: (_V, "{path}: the sections {unknown} are unknown (permitted: "
               "{expected}).",
           "The vocabulary table accepts the sections in the message. "
           "Correct the spelling of the section name. Or remove the section."),
    5205: (_V, "{path}: {where}: {primitive!r} is not an NPUWattch primitive "
               "(primitives: {known}).",
           "The vocabulary table maps simulator names to NPUWattch primitives. "
           "Use a primitive name from the list in the message."),
    5206: (_V, "{path}: primitive {primitive!r} is in two families, {first} "
               "and {second}.",
           "The family of a primitive selects its attribute table. A "
           "primitive can be in one family only. Remove the primitive from "
           "one of the two families."),
    5207: (_V, "{path}: {section}.{family}: the family is not in 'families'.",
           "Each family in the attributes and hints sections must also be in "
           "the families section. Add the family to 'families'. Or correct "
           "the spelling of the family name."),
    5208: (_V, "{path}: attributes.{family}.{name}: {name!r} is not an "
               "NPUWattch attribute name.",
           "The keys in the attributes section are NPUWattch attribute names. "
           "Use an attribute name from npuwattch.naming. "
           "Put a simulator value that has no NPUWattch name in the hints "
           "section."),
    5209: (_V, "{path}: hints.{family}.{name}: {name!r} is an NPUWattch "
               "attribute name.",
           "The hints section is for simulator values that have no NPUWattch "
           "name. Move this entry to the attributes section."),
    5210: (_V, "{path}: {section}.{family}.{name}: the name is declared two "
               "times.",
           "A name can occur one time in a family, in the attributes section "
           "or in the hints section. Remove one of the two declarations."),
    5211: (_V, "{path}: float_formats.{name}: the value is not a list of "
               "three integers.",
           "A float format gives the total bits, the exponent bits and the "
           "mantissa bits. Write the value as a list of three integers, such "
           "as [16, 8, 7]."),

    # -- 53xx compounds: files and scalar expressions -----------------------
    5301: (_C, "The {what} {path} does not exist.",
           "NPUWattch did not find the file at this path. Make sure that the "
           "path is correct. Give the compound components with "
           "--compound-components. Give the projection with --projection."),
    5302: (_C, "The {what} {path} is not valid JSON or YAML: {error}",
           "NPUWattch reads a .json file as JSON and a .yaml or .yml file as "
           "YAML. The parser error gives the position of the problem. "
           "Correct the syntax at that position."),
    5303: (_C, "The {what} {path} is empty.",
           "The file contains no data. Write the content of the file. "
           "Examples are in the tutorial."),
    5304: (_C, "{where}: the scalar {expr!r} is not an integer or an "
               "expression string.",
           "A scalar is an integer or a string expression, such as "
           "'lanes*lanes' or '2*bitwidth+1'. Write the value in one of these "
           "two forms."),
    5305: (_C, "{where}: the token {token!r} in {expr!r} is not valid.",
           "An expression contains integers, symbols, + and *. A symbol is a "
           "MAC scalar (lanes or bitwidth) or an integer run-config key of "
           "the harness. Remove other characters, such as -, / and "
           "parentheses."),
    5306: (_C, "{where}: a bool is not a scalar.",
           "YAML reads true, false, yes and no as bool values. A scalar is an "
           "integer or a string expression. Write an integer or an "
           "expression."),
    5307: (_C, "{where}: the symbol {symbol!r} in {expr!r} has no value.",
           "This run gives no value for this symbol. The symbols are lanes "
           "and bitwidth from the MAC configuration, and the integer "
           "run-config keys of the harness. Correct the spelling of the "
           "symbol. Or use a symbol that this run gives."),
    # -- the stim_mode table --
    5308: (_C, "Primitive {primitive!r} is not in the stim_mode table.",
           "The stim_mode table, primitive_modes, gives the characterized "
           "modes of each primitive. This primitive has no characterized "
           "modes. Use a primitive that is in the table."),
    5309: (_C, "Primitive {primitive!r} is not in the stim_mode table "
               "(primitives: {primitives}).",
           "The stim_mode table, primitive_modes, gives the characterized "
           "modes of each primitive. This primitive has no characterized "
           "modes. Use a primitive from the list in the message."),
    5310: (_C, "stim_mode {mode!r} is not characterized for {primitive!r} "
               "(permitted: {allowed}).",
           "An estimator can predict only the stim_modes of its training "
           "data. Use one of the permitted modes for this primitive."),
    5311: (_C, "primitive_modes: the top level is not an object.",
           "The top level of the stim_mode table is an object. It maps each "
           "primitive to its list of modes, directly or under a 'modes' key. "
           "Correct the structure of the file."),
    5312: (_C, "primitive_modes: 'modes' is empty or is not an object.",
           "The 'modes' object maps each primitive to its list of stim_mode "
           "names. Give one or more primitives."),
    5313: (_C, "primitive_modes[{primitive!r}]: the value is empty or is not "
               "a list.",
           "The value of each primitive is the list of its stim_mode names. "
           "Give one or more mode names in a list."),
    5314: (_C, "primitive_modes[{primitive!r}]: a mode name is empty or is "
               "not a string.",
           "Each mode name is a non-empty string. Correct or remove the "
           "incorrect entry."),
    5315: (_C, "primitive_modes[{primitive!r}]: a mode name occurs two times.",
           "Each mode name can occur one time in the list of a primitive. "
           "Remove the duplicate name."),
    5316: (_C, "primitive_modes[{primitive!r}]: the list does not include "
               "'random'.",
           "Each primitive is characterized in the 'random' mode. NPUWattch "
           "uses this mode as the default mode and for the VECTORLESS "
           "estimate. Add 'random' to the list."),
    # -- compounds files --
    5317: (_C, "Compound {compound!r}: 'elements' is empty or is not an "
               "object.",
           "A compound component is a set of elements. The 'elements' object "
           "maps each element name to its primitive, config and count. Give "
           "one or more elements."),
    5318: (_C, "Compound {compound!r} element {element!r}: the element has no "
               "'primitive' key.",
           "Each element is an object, and its 'primitive' key gives the "
           "NPUWattch primitive. Add a 'primitive' key to the element."),
    5319: (_C, "Compound {compound!r} element {element!r}: 'primitive' is a "
               "{type_name}, not a string.",
           "The value of 'primitive' is a primitive name or the placeholder "
           "{mac_primitive}. YAML reads an unquoted {mac_primitive} as a "
           "mapping. Put the placeholder in quotes: \"{mac_primitive}\"."),
    5320: (_C, "Compound {compound!r} element {element!r}: 'per' {per!r} is "
               "not one of {choices}.",
           "The 'per' key tells NPUWattch how to multiply the count of the "
           "element. 'array' and 'core' multiply the count by the number of "
           "arrays or cores of the run. 'chip' gives no multiplier. Use one "
           "of these three values."),
    5321: (_C, "Compound {compound!r}: 'default_mode' {default_mode!r} is not "
               "one of {choices}.",
           "The default_mode sets the charge of the elements that an action "
           "does not name. 'idle' charges one idle for each such element. "
           "'gated' does not charge them, and the leakage term includes "
           "them. Use 'idle' or 'gated'."),
    5322: (_C, "Compounds file: the top level is not an object.",
           "The top level of a compounds file maps each compound name to its "
           "definition. Write each compound as a key at the top level. "
           "Examples are in the tutorial."),
    5323: (_C, "Compound {compound!r}: the definition is not an object.",
           "A compound definition is an object with an 'elements' key and "
           "optional keys, such as 'default_mode'. Write the compound as an "
           "object."),
    5324: (_C, "The compounds file declares no compounds.",
           "The file has no keys, or it has only comment keys. A key that "
           "starts with _ is a comment. Add one or more compounds."),
    # -- projection files --
    5325: (_C, "Projection {compound}.{action}: the action has no "
               "count_from.stat.",
           "Each action has a count_from object. Its 'stat' key names the "
           "simulator stat that counts the action. Add count_from with a "
           "'stat' key to the action."),
    5326: (_C, "Projection {compound}.{action}: count_from.stat is empty or "
               "is not a string.",
           "count_from.stat is the name of a simulator stat. Write the stat "
           "name as a string."),
    5327: (_C, "Projection {compound}.{action}: count_from.unit {unit!r} is "
               "not one of {choices}.",
           "The unit tells NPUWattch what one count of the stat is. Use one "
           "of the units in the message. The default unit is words."),
    5328: (_C, "Projection {compound}.{action}: 'elements' is empty or is not "
               "an object.",
           "The 'elements' object of an action maps each element of the "
           "compound to its stim_mode. Give one or more elements."),
    5329: (_C, "Projection {compound}.{action}.elements[{element!r}]: the "
               "value is not a mode string.",
           "The value of each element is a stim_mode name from the stim_mode "
           "table. Write the mode name as a string."),
    5330: (_C, "The projection file has no top-level 'tool' key.",
           "The top level of a projection file is an object. Its 'tool' key "
           "names the harness of the projection, such as pytorchsim or "
           "timeloop. Add a 'tool' key at the top level."),
    5331: (_C, "Projection file: 'compounds' is empty or is not an object.",
           "The 'compounds' object maps each compound name to its simulator "
           "actions. Give one or more compounds."),
    5332: (_C, "Projection compound {compound!r}: the value is not an object.",
           "The value of each compound is an object that maps each simulator "
           "action to its mapping. Write the actions of the compound as an "
           "object."),
    5333: (_C, "Projection {compound}.{action}: the action is not an object.",
           "Each action is an object with the keys count_from and elements. "
           "Write the action as an object."),
    5334: (_C, "Projection file: the key {legacy!r} has the new name "
               "{current!r}.",
           "NPUWattch does not accept the old key name. Rename the key in the "
           "projection file."),
    5335: (_C, "Projection file: 'waivers' is not an object.",
           "The 'waivers' object maps a stat name to a justification string. "
           "NPUWattch reads a waived stat but does not charge it. The run "
           "shows the stat as a note, not as a coverage warning. Write "
           "'waivers' as an object."),
    5336: (_C, "Projection waivers[{stat!r}]: the justification is empty or "
               "is not a string.",
           "The justification tells why the projection does not charge the "
           "stat. Write the justification as a non-empty string."),
    5337: (_C, "Projection {compound}.{action} charges stat {stat!r}, which is "
               "also in 'waivers'.",
           "A waived stat is not charged. Thus a stat cannot be charged and "
           "also waived. Remove the stat from 'waivers'. Or remove the action "
           "that charges it."),
    5338: (_C, "Projection file: {key!r} is not a list of non-empty strings.",
           "The keys out_of_scope and third_party_pending are lists of text. "
           "Each entry is a non-empty string. Write the key as a list of "
           "strings."),
    # -- static checks and resolution --
    5339: (_C, "Projection {tool!r}: the compound {compound!r} does not "
               "exist.",
           "The projection refers to a compound that is not in the compound "
           "components. Correct the compound name in the projection. Or add "
           "the compound to the compound components."),
    5340: (_C, "Projection {compound}.{action}: element {element!r} is not in "
               "the compound (elements: {elements}).",
           "The projection names an element that the compound does not "
           "declare. Correct the element name. Or add the element to the "
           "compound."),
    5341: (_C, "Projection {compound}.{action}: mode {mode!r} of the templated "
               "element {element!r} is not valid for a MAC primitive "
               "({mac_primitives}).",
           "The MAC configuration of the run selects the primitive of a "
           "templated element. No MAC primitive has this mode in the "
           "stim_mode table. Correct the mode name."),
    5342: (_C, "Compound {compound}.{element} uses a MAC template, and the run "
               "has no MAC configuration.",
           "The placeholders {mac_primitive} and {mac_config} take their "
           "values from the MAC configuration of the run. A Timeloop run has "
           "no MAC configuration. Replace the placeholders with a primitive "
           "name and a config."),
    5343: (_C, "{where}: the placeholder {placeholder!r} is unknown.",
           "The config of an element accepts one placeholder, "
           "{mac_config}. Replace the placeholder with {mac_config} or with a "
           "config object."),
    5344: (_C, "Projection {tool!r} has no action {action!r} for compound "
               "{compound!r}.",
           "The projection has no mapping for this simulator action of the "
           "compound. Add the action under the compound in the projection "
           "file."),
    # -- bundles --
    5345: (_C, "{directory}: two files have the stem {stem!r}: {first} and "
               "{second}.",
           "A directory of compound files cannot have two files with the same "
           "stem, such as a .json file and a .yaml file. NPUWattch cannot "
           "select one of them. Delete or rename one of the two files."),
    5346: (_C, "The bundle has no compound {compound!r} (compounds: "
               "{available}).",
           "The harness needs this compound in the compound components of the "
           "run. Add the compound. Or correct the compound name in the "
           "compound components file."),
    5347: (_C, "The bundle has no projection for the tool {tool!r} "
               "(projections: {available}).",
           "The harness reads the projection whose 'tool' key is the harness "
           "name. Set 'tool' in the projection file to the name in the "
           "message."),
}, retired=(), source=__name__)
