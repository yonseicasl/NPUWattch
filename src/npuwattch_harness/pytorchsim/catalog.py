"""The message catalog of the PyTorchSim harness (NW-6000 to NW-6999).

See ``npuwattch.diagnostics`` for the rules. Each module has one block of
100 numbers. In a block, the numbers are in the source order of the module:

========= ==============================================================
block     module
========= ==============================================================
60xx      ``ingest`` (representative MAC, run checks, entry point)
61xx      ``mac_config`` (MAC configuration from the codegen files)
62xx      ``activity`` (``read_run``, ``bind_window``)
63xx      ``togsim_log`` (TOGSim log parser)
64xx      ``booksim`` (NoC topology and flit traffic)
65xx      ``dram`` (DRAM energy table, DRAM stats)
66xx      ``instances`` (division of the activity between instances)
67xx      ``run_config`` (``config.yml`` reader)
68xx-69xx  not used (``gem5_stats``, ``hierarchy``, ``definitions`` and
          ``__init__`` give no messages)
========= ==============================================================

Add a new entry at the end of its block. Do not renumber an entry and do not
use a number again: add a removed number to ``retired``.

Many window messages start with ``{kernel}:``. This is the hash of the
kernel (the window) that the message is about.
"""

from npuwattch.diagnostics import INFO, WARNING, register

register("NW", {
    # -- 60xx ingest ---------------------------------------------------------
    6001: (INFO,
           "{count} non-MAC kernel window(s) charged on the non-systolic "
           "compounds only (no systolic activity); the vfu/spads datapath dtype "
           "({dtype}) is borrowed from MAC kernel {kernel} — the physical array "
           "is uniform within a run"),
    6002: (WARNING,
           "run has no MAC kernel: non-MAC windows are charged at an ASSUMED "
           "fp32 (e8m23) datapath for the templated vfu/spads elements — no "
           "kernel in this run evidences the real dtype"),
    6003: ("RunConfigError",
           "inconsistent lanes across kernels ({lanes} vs {other_lanes}); the "
           "physical array must be uniform within a run"),
    6004: (WARNING,
           "kernel {kernel} has a different element set; using {first_kernel}"),
    6005: (WARNING,
           "kernel {kernel} reconfigures the array (config differs from "
           "{first_kernel}); description uses the first"),
    6006: (WARNING, "{compound}.{element}: not emitted — {error}"),
    6007: (WARNING,
           "pending third-party integration (not implemented — this energy is "
           "NOT included): {integration}"),
    6008: (INFO, "out of scope: {item}"),
    6009: (WARNING,
           "unsupported core_type {core_type!r}: this harness models only the "
           "'ws_mesh' (systolic) core. STONNE/heterogeneous cores "
           "(ARCHITECTURE_SPEC §6) are out of v1.0 scope — their activity and "
           "energy are NOT included in these results"),
    6010: (WARNING,
           "config enables an L2 data cache (l2d_type={l2d_type!r}): not "
           "modeled — outside the sanctioned energy scope (vector unit + VMEM + "
           "systolic array + on-chip NoC), and it is a large on-chip SRAM, so "
           "its energy is NOT included in these results"),
    6011: ("RunConfigError",
           "no clock frequency; pass clock_mhz/default_clock_mhz, set "
           "TechContext.clock_mhz, or ensure the log has core_freq_mhz"),
    6012: (WARNING,
           "num_arrays={num_arrays} is not divisible by num_cores={num_cores}; "
           "the per-instance split treats the run as a single core"),
    6013: (WARNING, "hierarchy view unavailable: {error}"),

    # -- 61xx mac_config -----------------------------------------------------
    6101: ("MacInferenceError", "unrecognized dtype token: {token!r}"),
    6102: ("NotAMatmulKernel", "no `linalg.matmul` found in MLIR"),
    6103: ("MacInferenceError",
           "malformed linalg.matmul: {ins} ins / {outs} outs"),
    6104: ("MacInferenceError", "no MAC primitive for operand kind {kind!r}"),
    6105: ("MacInferenceError", "lanes must be >= 1, got {lanes}"),
    6106: (WARNING,
           "{kernel}: mixed-precision matmul operands ({dtypes}); using the first"),
    6107: (WARNING,
           "{kernel}: partial int lowering: linalg.matmul is {matmul_dtype} but "
           "kernel I/O is {tensor_dtype}; selecting intmac by tensor dtype. "
           "int MAC energy is NOT calibrated on this image."),
    6108: (WARNING,
           "{kernel}: operand dtype {dtype} (MLIR) not among meta.txt input "
           "dtypes {meta_dtypes}"),
    6109: (WARNING, "{kernel}: matmul K mismatch: A={a_shape} B={b_shape}"),
    6110: ("MacInferenceError", "no kernel .mlir in {path}"),
    6111: ("MacInferenceError",
           "{path}: {count} candidate kernel MLIRs contain linalg.matmul "
           "({files}); ambiguous — leave exactly one"),
    6112: ("MacInferenceError", "meta.txt has no parseable entries"),
    6113: (WARNING,
           "{kernel}: no 2-D input tensors in meta.txt; operand dtype taken "
           "from non-matrix inputs"),
    6114: ("MacInferenceError", "meta.txt has no attr=1 (input) entries"),
    6115: (WARNING,
           "{kernel}: mixed input dtypes in meta.txt ({dtypes}); using the "
           "narrowest ({dtype})"),
    6116: (WARNING,
           "{kernel}: MAC config inferred from meta.txt only (no kernel MLIR); "
           "accumulator format is assumed — energy for this kernel is "
           "lower-confidence"),

    # -- 62xx activity -------------------------------------------------------
    6201: (WARNING, "{kernel}: kernel has no linalg.matmul; no MAC config"),
    6202: (WARNING, "{kernel}: MAC config inference failed: {error}"),
    6203: (WARNING,
           "{kernel}: no kernel MLIR and no systolic/GEMM activity in the log; "
           "treated as a non-MAC kernel"),
    6204: (WARNING, "{kernel}: meta.txt-only MAC config inference failed: {error}"),
    6205: (WARNING, "{kernel}: no kernel MLIR and no meta.txt; MAC config unavailable"),
    6206: (WARNING,
           "{kernel}: no m5out/stats.txt; gem5 instruction counts unavailable"),
    6207: (WARNING,
           "{kernel}: SFU ops present but the kernel's operand dtype is integer; "
           "charging the SFU at fp32 (e8m23) tables"),
    6208: (WARNING,
           "{kernel}: SFU ops present but the kernel's operand dtype is unknown; "
           "charging the SFU at fp32 (e8m23) tables"),
    6209: ("MacInferenceError", "TOGSim log directory not found: {path}"),
    6210: ("MacInferenceError", "gem5/codegen output directory not found: {path}"),
    6211: ("MacInferenceError",
           "no *.log in {path} — pass the run's final togsim_results/ directory "
           "(autotune logs under outputs/<hash>/togsim_result/ are candidates, "
           "not results)"),
    6212: (WARNING,
           "{kernel}: {directory}/{kernel}/ not found; MAC config unavailable"),
    6213: ("MacInferenceError", "no parseable TOGSim log in {path} — {skipped}"),
    6214: (WARNING, "{count} unparseable log(s) skipped: {skipped}"),
    6215: ("MacInferenceError",
           "window {kernel} has no MAC config; cannot bind projection"),
    6216: (WARNING, "{compound}.{action}: not charged — {error}"),

    # -- 63xx togsim_log -----------------------------------------------------
    6301: ("TogsimLogError",
           "no 'PyTorchSim config:' header found (older 'TOGSim Config: "
           "{{JSON}}' logs are no longer supported — re-run with a current "
           "PyTorchSim build)"),
    6302: ("TogsimLogError", "'PyTorchSim config:' block is empty"),
    6303: ("TogsimLogError",
           "models_list log mentions {count} kernel dirs ({hashes}) — its "
           "combined activity cannot be split per kernel; re-run with one "
           "kernel per simulator invocation"),
    6304: ("TogsimLogError",
           "no kernel hash: expected '--trace_so .../outputs/<hash>/trace.so' "
           "on the command line, or (models_list builds) an outputs/<hash>/ "
           "path in the log body"),
    6305: ("TogsimLogError", "config has no integer 'vpu_num_lanes'"),
    6306: (WARNING,
           "{kernel}: config {key}={value} disagrees with the [Config/DRAM] "
           "echo ({echoed}); keeping the config value"),

    # -- 64xx booksim --------------------------------------------------------
    6401: ("NetFileError",
           ".net line {line}: expected 'router <id> ...', got {text!r}"),
    6402: ("NetFileError", ".net line {line}: non-integer router id {token!r}"),
    6403: ("NetFileError",
           ".net line {line}: unexpected token {token!r} (want 'node'/'router')"),
    6404: ("NetFileError",
           "anynet network file {name} not found in {directory} (no *.net present)"),
    6405: ("NetFileError",
           "anynet network file {name!r} not found in {directory} and the "
           "directory holds {count} *.net files — cannot pick one"),
    6406: (WARNING,
           "log has no DRAM request totals; NoC structure is emitted but its "
           "dynamic energy cannot be charged"),
    6407: (WARNING,
           "BookSim reports packet length average {length:g} (the model assumes "
           "1 flit/packet): flit totals scaled by {length:g}"),
    6408: (WARNING,
           "NoC not emitted: log has no embedded BookSim [config] echo (older build?)"),
    6409: (WARNING,
           "NoC not emitted: icnt_type {icnt_type!r} is not modeled (booksim2 only)"),
    6410: (WARNING, "NoC not emitted: BookSim config has no integer flit_size"),
    6411: (WARNING,
           "NoC not emitted: unsupported topology 'fly' with n={n!r} "
           "(supported: {supported})"),
    6412: (WARNING, "NoC not emitted: fly topology without an integer 'k'"),
    6413: (WARNING,
           "NoC not emitted: anynet topology needs the BookSim config directory "
           "(--booksim-dir, e.g. the run's booksim2_config/) for its .net "
           "network file"),
    6414: (WARNING, "NoC not emitted: {error}"),
    6415: (WARNING, "NoC not emitted: {file} has no router with attached nodes"),
    6416: (WARNING,
           "{file}: router {router} has no nodes and {links} links — treated as "
           "a switch (expected 2-link pass-through channels only)"),
    6417: (WARNING,
           "{file}: router radix varies ({radices}); using the largest for all "
           "switches"),
    6418: (WARNING,
           "NUMA request total {numa_total} != [DRAM] request total "
           "{dram_total}; the d2d split still uses the NUMA local/remote ratio"),
    6419: (WARNING,
           "NoC traffic split is a uniform-traffic assumption: {fraction:.2f} of "
           "flits are charged one die-to-die channel crossing and a second "
           "switch traversal (the log has no NUMA local/remote counters)"),
    6420: (WARNING,
           "NoC not emitted: unsupported BookSim topology {topology!r} "
           "(supported: {supported})"),

    # -- 65xx dram -----------------------------------------------------------
    6501: (WARNING,
           "--energy-table {file} supplied but the run emitted no DRAM "
           "component (no dram_channels / DRAM stats in the log) — the table "
           "is unused"),
    6502: ("HarnessError",
           "the default DRAM energy table is not available ({error}) — pass "
           "--energy-table"),
    6503: (INFO,
           "DRAM constants from the run's energy table {name!r} ({file}): "
           "activation {act_pj:g} pJ, transfer {transfer_pj_per_bit:g} pJ/bit "
           "({transfer_split}); refresh {ref_pj:g} pJ/REFab from the table"),
    6504: (INFO,
           "DRAM constants from the run's energy table {name!r} ({file}): "
           "activation {act_pj:g} pJ, transfer {transfer_pj_per_bit:g} pJ/bit "
           "({transfer_split}); refresh comes from the default table hbm2.yml "
           "(the table has no refresh term)"),
    6505: (WARNING,
           "{kernel}: config has no dram_req_size_byte; assuming {size} B per "
           "DRAM request for byte traffic"),
    6506: (WARNING,
           "{kernel}: per-core DMA responses total {dma_total} != [DRAM] "
           "request total {dram_total}; using the [DRAM] total (per-core split "
           "still uses the DMA shares)"),
    6507: (WARNING,
           "{kernel}: DRAM statistics block reports {reads} reads / {writes} "
           "writes but the [DRAM] interval totals sum to {log_reads} / "
           "{log_writes}; device energy uses the statistics block (VMEM/NoC "
           "traffic keeps the totals)"),
    6508: (WARNING,
           "{kernel}: log has no '=== DRAM statistics ===' block; DRAM "
           "read/write energy is charged from the [DRAM] request totals, but "
           "row-activation and refresh energy are NOT charged"),
    6509: (WARNING,
           "{kernel}: run declares DRAM energy table {declared!r} ({path}), but "
           "--energy-table supplied {charged!r} — its constants are charged; "
           "pass the run's own table file instead"),
    6510: (WARNING,
           "{kernel}: run declares DRAM energy table {declared!r} ({path}), but "
           "NPUWattch charges the default {charged} table — pass the run's "
           "table via --energy-table"),

    # -- 66xx instances ------------------------------------------------------
    6601: (WARNING,
           "{stat}: SFU ops attributed per core by vector active-cycle share"),
    6602: (WARNING,
           "{stat}: DRAM→VMEM fill attributed per core by MOVIN instruction share"),
    6603: (WARNING,
           "{stat}: VMEM→DRAM drain attributed per core by MOVOUT instruction "
           "share"),
    6604: (WARNING, "{stat}: attributed per core by systolic active-cycle share"),
    6605: (WARNING,
           "no per-core {counter} counters; falling back to the systolic "
           "active-cycle share"),
    6606: (WARNING, "{counter}: all zero in this window; split uniformly"),
    6607: (WARNING,
           "{stat}: kernel-total events attributed per array in proportion to "
           "each array's active cycles"),

    # -- 67xx run_config -----------------------------------------------------
    6701: ("RunConfigError", "{path}: expected a YAML mapping, got {type}"),
    6702: (WARNING,
           "config.yml disagrees with the log header: {key} = {file_value!r} "
           "vs {log_value!r}"),
}, retired=(), source=__name__)
