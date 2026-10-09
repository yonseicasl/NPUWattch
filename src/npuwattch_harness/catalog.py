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
    5001: (_H, "HARNESS_SPEC missing 'name'"),
    5002: (_H, "harness {harness!r}: 'inputs' must be a non-empty dict"),
    5003: (_H, "harness {harness!r}: 'ingest' must be callable"),
    5004: (_H, "flag {flag} has two meanings: {first!r} and {second!r} "
               "(harness {harness!r})"),
    5005: (_H, "unknown harness {harness!r}; available: {available}"),
    5006: (_H, "harness {harness!r}: unknown input(s) {unknown}; "
               "declared: {declared}"),
    5007: (_H, "harness {harness!r}: missing required input {input_name!r} "
               "({flag}) — {hint}"),
    5008: (_H, "harness {harness!r}: missing required input {input_name!r} "
               "({flag})"),
    5009: (_H, "harness {harness!r}: input {input_name!r} is not a "
               "{expected}: {path}"),

    # -- 51xx run_inputs ----------------------------------------------------
    5101: (_H, "{file_name} not found in {run_dir} — put the file there or "
               "give it with {flag}"),
    5102: (_H, "the compound components or the projection of the run are not "
               "correct: {error}"),
    5103: (_H, "the user component library is not correct: {error}"),

    # -- 52xx vocabulary ----------------------------------------------------
    5201: (_V, "vocabulary table not found: {path}"),
    5202: (_V, "{path}: not valid YAML: {error}"),
    5203: (_V, "{path}: the table must be a mapping"),
    5204: (_V, "{path}: unknown section(s) {unknown} (expected: {expected})"),
    5205: (_V, "{path}: {where}: {primitive!r} is not a NPUWattch primitive "
               "({known})"),
    5206: (_V, "{path}: primitive {primitive!r} is in two families "
               "({first}, {second})"),
    5207: (_V, "{path}: {section}.{family}: no such family in `families`"),
    5208: (_V, "{path}: attributes.{family}.{name}: {name!r} is not a "
               "NPUWattch attribute name (see npuwattch.naming)"),
    5209: (_V, "{path}: hints.{family}.{name}: {name!r} is a NPUWattch "
               "attribute name; put it in `attributes`"),
    5210: (_V, "{path}: {section}.{family}.{name}: declared twice"),
    5211: (_V, "{path}: float_formats.{name}: give [total bits, exponent "
               "bits, mantissa bits]"),

    # -- 53xx compounds: files and scalar expressions -----------------------
    5301: (_C, "{what} not found: {path}"),
    5302: (_C, "{what} is not valid JSON/YAML: {error}"),
    5303: (_C, "{what} is empty: {path}"),
    5304: (_C, "{where}: scalar must be int or expr string, got {expr!r}"),
    5305: (_C, "{where}: malformed token {token!r} in {expr!r} (use ints, +, "
               "*, and identifier symbols — MAC scalars {mac_symbols} or the "
               "harness's integer run-config keys)"),
    5306: (_C, "{where}: bool is not a scalar"),
    5307: (_C, "{where}: unresolved symbol {symbol!r} in {expr!r}"),
    # -- the stim_mode table --
    5308: (_C, "unknown primitive: {primitive!r}"),
    5309: (_C, "primitive {primitive!r} not in vocabulary ({primitives})"),
    5310: (_C, "stim_mode {mode!r} not characterized for {primitive!r}; "
               "allowed: {allowed}"),
    5311: (_C, "primitive_modes: top-level must be an object"),
    5312: (_C, "primitive_modes: 'modes' must be a non-empty object"),
    5313: (_C, "primitive_modes[{primitive!r}] must be a non-empty list of "
               "mode names"),
    5314: (_C, "primitive_modes[{primitive!r}] must contain non-empty strings"),
    5315: (_C, "primitive_modes[{primitive!r}] has duplicate modes"),
    5316: (_C, "primitive_modes[{primitive!r}] must include 'random' (the "
               "universal anchor)"),
    # -- compounds files --
    5317: (_C, "compound {compound!r}: 'elements' must be a non-empty object"),
    5318: (_C, "compound {compound!r} element {element!r}: needs at least a "
               "'primitive'"),
    5319: (_C, "compound {compound!r} element {element!r}: 'primitive' must be "
               "a string (got {type_name}); if you wrote a placeholder like "
               "{{mac_primitive}} in YAML, quote it: \"{{mac_primitive}}\""),
    5320: (_C, "compound {compound!r} element {element!r}: 'per' must be one "
               "of {choices}, got {per!r}"),
    5321: (_C, "compound {compound!r}: 'default_mode' must be one of "
               "{choices}, got {default_mode!r}"),
    5322: (_C, "compounds file: top-level must be an object"),
    5323: (_C, "compound {compound!r}: must be an object"),
    5324: (_C, "compounds file declares no compounds"),
    # -- projection files --
    5325: (_C, "projection {compound}.{action}: 'count_from' needs a 'stat'"),
    5326: (_C, "projection {compound}.{action}: count_from.stat must be a "
               "non-empty string"),
    5327: (_C, "projection {compound}.{action}: count_from.unit must be one "
               "of {choices}, got {unit!r}"),
    5328: (_C, "projection {compound}.{action}: 'elements' must be a "
               "non-empty object"),
    5329: (_C, "projection {compound}.{action}.elements[{element!r}] must be "
               "a mode string"),
    5330: (_C, "projection file: needs a top-level 'tool'"),
    5331: (_C, "projection file: 'compounds' must be a non-empty object"),
    5332: (_C, "projection compound {compound!r}: must be an object"),
    5333: (_C, "projection {compound}.{action}: must be an object"),
    5334: (_C, "projection file: {legacy!r} was renamed — use {current!r}"),
    5335: (_C, "projection file: 'waivers' must be an object mapping stat "
               "name -> justification string"),
    5336: (_C, "projection waivers[{stat!r}]: the justification must be a "
               "non-empty string (say WHY the stat is deliberately not "
               "charged)"),
    5337: (_C, "projection {compound}.{action} charges stat {stat!r} which is "
               "also listed in 'waivers' — remove one of the two"),
    5338: (_C, "projection file: {key!r} must be a list of non-empty strings"),
    # -- static checks and resolution --
    5339: (_C, "projection {tool!r} references unknown compound {compound!r}"),
    5340: (_C, "projection {compound}.{action}: element {element!r} not in "
               "compound ({elements})"),
    5341: (_C, "projection {compound}.{action}: mode {mode!r} for templated "
               "element {element!r} is not valid for any MAC primitive "
               "({mac_primitives})"),
    5342: (_C, "compound {compound}.{element}: the templates {{mac_primitive}} "
               "and {{mac_config}} need a MAC configuration, which this run "
               "does not have"),
    5343: (_C, "{where}: unknown placeholder {placeholder!r}"),
    5344: (_C, "projection {tool!r} has no action {action!r} for "
               "{compound!r}"),
    # -- bundles --
    5345: (_C, "two bundle files with stem {stem!r} in {directory}: {first} "
               "and {second}"),
    5346: (_C, "no compound {compound!r} in bundle ({available})"),
    5347: (_C, "no projection {tool!r} in bundle ({available})"),
}, retired=(), source=__name__)
