"""The message catalog of the PyTorchSim harness (NW-6000 to NW-6999).

See ``npuwattch.diagnostics`` for the rules. The ``blocks`` argument of
``register`` below gives the block of each module. In a block, the numbers
are in the source order of the module.

Add a new entry at the end of its block. Do not renumber an entry and do not
use a number again: add a removed number to ``retired``.

Many window messages start with ``{kernel}:``. This is the hash of the
kernel (the window) that the message is about.
"""

from npuwattch.diagnostics import INFO, WARNING, register

_P = "npuwattch_harness.pytorchsim."

register("NW", blocks={
    (6000, 6099): _P + "ingest",
    (6100, 6199): _P + "mac_config",
    (6200, 6299): _P + "activity",
    (6300, 6399): _P + "togsim_log",
    (6400, 6499): _P + "booksim",
    (6500, 6599): _P + "dram",
    (6600, 6699): _P + "instances",
    (6700, 6799): _P + "run_config",
}, entries={
    # -- 60xx ingest ---------------------------------------------------------
    6001: (INFO,
           "{count} non-MAC kernel(s) use the {dtype} datapath of MAC kernel "
           "{kernel}.",
           "A non-MAC kernel has no systolic activity. NPUWattch charges it "
           "only on the compounds other than the systolic array. The vfu and "
           "spads elements take their datapath dtype from the first MAC "
           "kernel. The physical array is the same for all kernels of a run. "
           "No action is necessary."),
    6002: (WARNING,
           "The run has no MAC kernel, so non-MAC kernels use an fp32 datapath.",
           "NPUWattch takes the datapath dtype of the vfu and spads elements "
           "from a MAC kernel. This run has no MAC kernel. Thus NPUWattch uses "
           "fp32 (e8m23) for these elements. The energy of the non-MAC kernels "
           "is correct only if the real datapath is fp32."),
    6003: ("RunConfigError",
           "The kernels have different lanes ({lanes} and {other_lanes}).",
           "The physical array is the same for all kernels of a run. Thus all "
           "kernels must have the same vpu_num_lanes. Make sure that all "
           "TOGSim logs come from one run."),
    6004: (WARNING,
           "Kernel {kernel}: the element set is different from kernel "
           "{first_kernel}.",
           "The MAC configuration of this kernel gives a different set of "
           "elements in the MAC compound. This occurs in a run with fp and int "
           "kernels. The description uses the elements of the first MAC kernel. "
           "The area and the leakage power come from this description. The "
           "activity of each kernel is correct."),
    6005: (WARNING,
           "Kernel {kernel}: the array configuration is different from kernel "
           "{first_kernel}.",
           "The MAC configuration of this kernel gives the same elements with "
           "a different configuration. The description uses the configuration "
           "of the first MAC kernel. The area and the leakage power come from "
           "this description. The activity of each kernel is correct."),
    6006: (WARNING, "{compound}.{element}: the element is not emitted: {error}",
           "NPUWattch could not resolve this element with the configuration of "
           "the run. Usually, the configuration does not have a symbol that "
           "the element uses. The energy and the area of this element are not "
           "in the results. Add the symbol to the run configuration, or correct "
           "the compound component definition."),
    6007: (WARNING,
           "{integration}: the third-party integration is pending, and its "
           "energy is not included.",
           "The projection of this harness declares this item as a pending "
           "third-party integration. NPUWattch does not model it. Its energy "
           "is not in the results."),
    6008: (INFO, "Out of scope: {item}",
           "The projection of this harness declares this item outside the "
           "energy scope. The results do not include it. No action is "
           "necessary."),
    6009: (WARNING,
           "core_type {core_type!r} is not supported, and its energy is not "
           "included.",
           "This harness models the ws_mesh (systolic) core. It does not model "
           "STONNE or heterogeneous cores. The activity and the energy of "
           "these cores are not in the results."),
    6010: (WARNING,
           "l2d_type={l2d_type!r} enables an L2 data cache, and its energy is "
           "not included.",
           "The energy scope of this harness is the vector unit, the VMEM, the "
           "systolic array, and the on-chip NoC. NPUWattch does not model the "
           "L2 data cache. This cache is a large on-chip SRAM. Its energy and "
           "area are not in the results."),
    6011: ("RunConfigError", "There is no clock frequency for the run.",
           "NPUWattch did not find a clock frequency in the arguments, the "
           "technology context, or core_freq_mhz of the log. Give the clock "
           "frequency with --clock-mhz. In the Python API, give clock_mhz or "
           "default_clock_mhz."),
    6012: (WARNING,
           "num_arrays={num_arrays} is not divisible by num_cores={num_cores}, "
           "so the run is treated as one core.",
           "NPUWattch divides the arrays equally between the cores. This "
           "division is not possible here. Thus the description has one core "
           "that contains all the arrays. The per-core components and the "
           "per-core split do not agree with the real chip. Check num_arrays "
           "and num_cores in the run configuration."),
    6013: (WARNING, "The hierarchy view is not available: {error}",
           "NPUWattch could not make the hierarchy view of the description. "
           "The report does not show the hierarchy. The energy and the area "
           "results do not change."),

    # -- 61xx mac_config -----------------------------------------------------
    6101: ("MacInferenceError", "The dtype token {token!r} is not recognized.",
           "NPUWattch reads the operand dtype from the kernel MLIR or from "
           "meta.txt. It does not know this token. Thus the kernel has no MAC "
           "configuration."),
    6102: ("NotAMatmulKernel", "The MLIR has no linalg.matmul.",
           "A kernel without linalg.matmul is not a matmul kernel. NPUWattch "
           "treats it as a non-MAC kernel."),
    6103: ("MacInferenceError",
           "The linalg.matmul is malformed: {ins} inputs and {outs} outputs.",
           "A linalg.matmul has two or more inputs and one or more outputs. "
           "NPUWattch cannot read the operand dtypes from this operation. Thus "
           "the kernel has no MAC configuration."),
    6104: ("MacInferenceError",
           "There is no MAC primitive for the operand kind {kind!r}.",
           "NPUWattch has MAC primitives for float and int operands. It cannot "
           "select a primitive for this kind. Thus the kernel has no MAC "
           "configuration."),
    6105: ("MacInferenceError", "lanes={lanes} is not valid.",
           "The number of lanes comes from vpu_num_lanes in the run "
           "configuration. The value must be 1 or more. Correct vpu_num_lanes "
           "in the configuration."),
    6106: (WARNING,
           "{kernel}: the matmul operands have mixed dtypes ({dtypes}), and "
           "NPUWattch uses the first.",
           "The MAC primitive has one operand dtype. NPUWattch uses the dtype "
           "of the first operand. The MAC energy of this kernel is "
           "approximate."),
    6107: (WARNING,
           "{kernel}: linalg.matmul is {matmul_dtype}, but the kernel I/O is "
           "{tensor_dtype}, so NPUWattch uses intmac.",
           "The build did not lower the int matmul to an int operation. "
           "NPUWattch selects the intmac primitive from the tensor dtype of "
           "the kernel. The simulated activity comes from the float code of "
           "the build. Thus the MAC energy of this kernel is approximate."),
    6108: (WARNING,
           "{kernel}: the MLIR operand dtype {dtype} is not in the meta.txt "
           "input dtypes {meta_dtypes}.",
           "NPUWattch compares the operand dtype of the MLIR with the input "
           "dtypes of meta.txt. The two files do not agree. NPUWattch uses the "
           "MLIR dtype. Make sure that the MLIR and meta.txt come from the "
           "same kernel."),
    6109: (WARNING,
           "{kernel}: the K dimensions of the matmul do not agree: "
           "A={a_shape}, B={b_shape}.",
           "The second dimension of A must be equal to the first dimension of "
           "B. The GEMM shape of this kernel in the results can be incorrect. "
           "Check the kernel MLIR."),
    6110: ("MacInferenceError", "There is no kernel .mlir file in {path}.",
           "NPUWattch reads the MAC configuration from the kernel MLIR. It "
           "ignores the _llvm and _sample files. Give the gem5/codegen "
           "directory that contains the kernel MLIR."),
    6111: ("MacInferenceError",
           "{path}: {count} kernel MLIR files contain linalg.matmul: {files}",
           "NPUWattch reads the MAC configuration from one kernel MLIR. It "
           "cannot select one of these files. Keep one kernel MLIR in the "
           "directory and remove the others."),
    6112: ("MacInferenceError", "meta.txt has no entry that NPUWattch can read.",
           "NPUWattch reads the input dtypes from meta.txt when the kernel has "
           "no MLIR. This file has no valid entry. Thus the kernel has no MAC "
           "configuration."),
    6113: (WARNING,
           "{kernel}: meta.txt has no 2-D input tensor, so the operand dtype "
           "comes from other inputs.",
           "NPUWattch usually reads the operand dtype from the 2-D input "
           "tensors of meta.txt. This kernel has no 2-D input tensor. Thus "
           "NPUWattch uses the dtype of the other inputs. The MAC energy of "
           "this kernel is approximate."),
    6114: ("MacInferenceError", "meta.txt has no input entry (attr=1).",
           "NPUWattch reads the operand dtype from the input entries of "
           "meta.txt. This file has no input entry. Thus the kernel has no MAC "
           "configuration."),
    6115: (WARNING,
           "{kernel}: meta.txt has mixed input dtypes ({dtypes}), and "
           "NPUWattch uses the narrowest ({dtype}).",
           "The MAC primitive has one operand dtype. NPUWattch uses the "
           "narrowest input dtype. The MAC energy of this kernel is "
           "approximate."),
    6116: (WARNING,
           "{kernel}: the MAC configuration comes from meta.txt, because there "
           "is no kernel MLIR.",
           "meta.txt does not give the accumulator format. NPUWattch assumes "
           "f32 or f64 for float operands and a width rule for int operands. "
           "The MAC energy of this kernel is less accurate. Keep the kernel "
           ".mlir file in the gem5/codegen directory for a better estimate."),

    # -- 62xx activity -------------------------------------------------------
    6201: (WARNING,
           "{kernel}: the kernel has no linalg.matmul, so it has no MAC "
           "configuration.",
           "NPUWattch treats the kernel as a non-MAC kernel. This is correct "
           "for softmax, layernorm, and elementwise kernels. No action is "
           "necessary if the kernel has no matmul."),
    6202: (WARNING, "{kernel}: the MAC configuration is not available: {error}",
           "NPUWattch could not get the MAC configuration from the kernel MLIR. "
           "The message gives the cause. NPUWattch charges the kernel with the "
           "MAC configuration of the first MAC kernel. The energy of this "
           "kernel is correct only if the two kernels use the same datapath."),
    6203: (WARNING,
           "{kernel}: the kernel has no MLIR and no systolic or GEMM activity, "
           "so it is a non-MAC kernel.",
           "Without a kernel MLIR, NPUWattch identifies a MAC kernel from the "
           "systolic or GEMM activity in the log. This kernel has no such "
           "activity. NPUWattch treats it as a non-MAC kernel."),
    6204: (WARNING,
           "{kernel}: the MAC configuration from meta.txt is not available: "
           "{error}",
           "The kernel has no MLIR, and NPUWattch could not get the MAC "
           "configuration from meta.txt. The message gives the cause. "
           "NPUWattch charges the kernel with the MAC configuration of the "
           "first MAC kernel. The energy of this kernel is correct only if "
           "the two kernels use the same datapath."),
    6205: (WARNING,
           "{kernel}: there is no kernel MLIR and no meta.txt, so the MAC "
           "configuration is not available.",
           "NPUWattch reads the MAC configuration from the kernel MLIR or from "
           "meta.txt. NPUWattch charges the kernel with the MAC configuration "
           "of the first MAC kernel. The energy of this kernel is correct only "
           "if the two kernels use the same datapath."),
    6206: (WARNING,
           "{kernel}: there is no m5out/stats.txt, so the gem5 instruction "
           "counts are not available.",
           "NPUWattch reads the matmul and SFU instruction counts of the kernel "
           "from the gem5 stats. The actions that use these counts are not "
           "charged for this kernel. Give the gem5/codegen directory that "
           "contains m5out/stats.txt."),
    6207: (WARNING,
           "{kernel}: the kernel has SFU operations and an int operand dtype, "
           "so NPUWattch charges the SFU at fp32.",
           "The SFU model takes its format from the float operand dtype of the "
           "kernel. For an int dtype, NPUWattch uses fp32 (e8m23). The SFU "
           "energy is correct only if the SFU operates at fp32."),
    6208: (WARNING,
           "{kernel}: the kernel has SFU operations and an unknown operand "
           "dtype, so NPUWattch charges the SFU at fp32.",
           "The SFU model takes its format from the float operand dtype of the "
           "kernel. This kernel has no MAC configuration, thus the dtype is "
           "unknown. NPUWattch uses fp32 (e8m23). The SFU energy is correct "
           "only if the SFU operates at fp32."),
    6209: ("MacInferenceError",
           "The TOGSim log directory {path} does not exist.",
           "Give the togsim_results/ directory of the run with --togsim-dir."),
    6210: ("MacInferenceError",
           "The gem5/codegen output directory {path} does not exist.",
           "Give the per-kernel output directory of the run with --gem5-dir. "
           "For a raw run, this is outputs/. For an author bundle, this is "
           "gem5_outputs/."),
    6211: ("MacInferenceError", "There is no *.log file in {path}.",
           "NPUWattch reads one TOGSim log for each kernel from the final "
           "togsim_results/ directory of the run. Give this directory with "
           "--togsim-dir. The logs in outputs/<hash>/togsim_result/ are "
           "autotune candidates, not results."),
    6212: (WARNING,
           "{kernel}: {directory}/{kernel}/ does not exist, so the MAC "
           "configuration is not available.",
           "NPUWattch reads the MAC configuration of a kernel from its "
           "directory in the gem5/codegen output. NPUWattch charges the kernel "
           "with the MAC configuration of the first MAC kernel. Make sure that "
           "--gem5-dir and --togsim-dir come from the same run."),
    6213: ("MacInferenceError",
           "There is no TOGSim log in {path} that NPUWattch can read: {skipped}",
           "NPUWattch could not parse a log in this directory. The message "
           "gives the error for each log. Use the logs of a current PyTorchSim "
           "build."),
    6214: (WARNING,
           "NPUWattch skipped {count} log(s) that it cannot read: {skipped}",
           "The message gives the error for each skipped log. The kernels of "
           "these logs are not in the results. Correct or remove these logs."),
    6215: ("MacInferenceError",
           "Window {kernel}: there is no MAC configuration, so NPUWattch "
           "cannot bind the projection.",
           "Each window must have a MAC configuration before NPUWattch binds "
           "the projection. The ingest step gives a MAC configuration to each "
           "window. If you call bind_window directly, give a window that has "
           "a MAC configuration."),
    6216: (WARNING, "{compound}.{action}: the action is not charged: {error}",
           "NPUWattch could not resolve this action with the configuration of "
           "the run. Usually, the configuration does not have a symbol that "
           "the action uses. The energy of this action is not in the results. "
           "Add the symbol to the run configuration, or correct the "
           "projection."),

    # -- 63xx togsim_log -----------------------------------------------------
    6301: ("TogsimLogError", "The log has no 'PyTorchSim config:' header.",
           "NPUWattch reads the run configuration from this header. Older logs "
           "with a 'TOGSim Config:' JSON header are not supported. Run the "
           "simulation again with a current PyTorchSim build."),
    6302: ("TogsimLogError", "The 'PyTorchSim config:' block of the log is empty.",
           "NPUWattch reads the run configuration from this block. The block "
           "has no key. Make sure that the log is complete."),
    6303: ("TogsimLogError",
           "The models_list log contains {count} kernel directories: {hashes}",
           "NPUWattch cannot divide the combined activity of this log between "
           "the kernels. Thus NPUWattch skips the log. Run the simulator one "
           "time for each kernel."),
    6304: ("TogsimLogError", "The log has no kernel hash.",
           "NPUWattch reads the kernel hash from the --trace_so argument, "
           "outputs/<hash>/trace.so, on the command line. A models_list build "
           "gives an outputs/<hash>/ path in the log body. This log has "
           "neither. Use the complete log of the run."),
    6305: ("TogsimLogError", "The configuration has no integer vpu_num_lanes.",
           "NPUWattch needs vpu_num_lanes for the MAC configuration. The log "
           "header and config.yml do not give it. Give the config.yml of the "
           "run with --config-yml."),
    6306: (WARNING,
           "{kernel}: config {key}={value} is different from the [Config/DRAM] "
           "echo ({echoed}).",
           "The log echoes the DRAM configuration in the [Config/DRAM] block. "
           "NPUWattch keeps the value of the configuration. Make sure that the "
           "log and the configuration come from the same run."),

    # -- 64xx booksim --------------------------------------------------------
    6401: ("NetFileError",
           ".net line {line}: the line {text!r} does not start with "
           "'router <id>'.",
           "Each line of an anynet .net file starts with 'router' and an "
           "integer id. Correct the .net file."),
    6402: ("NetFileError",
           ".net line {line}: the router id {token!r} is not an integer.",
           "Correct the router id in the .net file."),
    6403: ("NetFileError",
           ".net line {line}: the token {token!r} is not 'node' or 'router'.",
           "After the router id, each entry of a .net line is a node or a "
           "router link. Correct the .net file."),
    6404: ("NetFileError",
           "The anynet network file {name} is not in {directory}, and the "
           "directory has no .net file.",
           "An anynet topology needs its .net network file from the BookSim "
           "config directory. Give the booksim2_config/ directory of the run "
           "with --booksim-dir."),
    6405: ("NetFileError",
           "The anynet network file {name!r} is not in {directory}, and the "
           "directory has {count} .net files.",
           "If the named file is missing, NPUWattch uses the .net file of the "
           "directory. With more than one file, NPUWattch cannot select one. "
           "Put the named file in the directory, or keep one .net file in it."),
    6406: (WARNING,
           "The log has no DRAM request totals, so the NoC dynamic energy is "
           "not charged.",
           "NPUWattch calculates the NoC flits from the DRAM requests. The NoC "
           "area and leakage power are in the results. The dynamic energy of "
           "the NoC is not in the results. Use the complete log of the run."),
    6407: (WARNING,
           "BookSim reports an average packet length of {length:g} flits, so "
           "NPUWattch scales the flit totals by {length:g}.",
           "The NoC model assumes one flit for each packet. BookSim reports a "
           "different average packet length. NPUWattch multiplies the flit "
           "totals by this average. No action is necessary."),
    6408: (WARNING,
           "The NoC is not emitted: the log has no BookSim [config] echo.",
           "NPUWattch reads the NoC topology from the BookSim config echo in "
           "the log. Older PyTorchSim builds do not write this echo. The NoC "
           "energy and area are not in the results. Use a current PyTorchSim "
           "build."),
    6409: (WARNING,
           "The NoC is not emitted: icnt_type {icnt_type!r} is not modeled.",
           "This harness models the booksim2 interconnect. The NoC energy and "
           "area are not in the results."),
    6410: (WARNING,
           "The NoC is not emitted: the BookSim config has no integer flit_size.",
           "NPUWattch needs flit_size for the NoC width. The NoC energy and "
           "area are not in the results. Make sure that the log has the "
           "complete BookSim config."),
    6411: (WARNING,
           "The NoC is not emitted: the fly topology with n={n!r} is not "
           "supported ({supported}).",
           "This harness models the fly topology with n = 1 and the anynet "
           "topology. The NoC energy and area are not in the results."),
    6412: (WARNING,
           "The NoC is not emitted: the fly topology has no integer k.",
           "NPUWattch needs k for the number of switch ports. The NoC energy "
           "and area are not in the results."),
    6413: (WARNING,
           "The NoC is not emitted: the anynet topology needs the BookSim "
           "config directory.",
           "An anynet topology reads its .net network file from the BookSim "
           "config directory. Give the booksim2_config/ directory of the run "
           "with --booksim-dir. Without it, the NoC energy and area are not in "
           "the results."),
    6414: (WARNING, "The NoC is not emitted: {error}",
           "NPUWattch could not read the .net network file of the anynet "
           "topology. The message gives the cause. The NoC energy and area are "
           "not in the results."),
    6415: (WARNING,
           "The NoC is not emitted: {file} has no router with attached nodes.",
           "NPUWattch models a router with attached nodes as a switch. This "
           ".net file has no such router. The NoC energy and area are not in "
           "the results. Correct the .net file."),
    6416: (WARNING,
           "{file}: router {router} has no nodes and {links} links, so "
           "NPUWattch treats it as a switch.",
           "A router without nodes is usually a pass-through channel with two "
           "links. This router has a different number of links. NPUWattch "
           "models it as a switch. Check the .net file."),
    6417: (WARNING,
           "{file}: the router radix varies ({radices}), so NPUWattch uses the "
           "largest radix for all switches.",
           "The NoC model uses one switch radix. NPUWattch uses the largest "
           "radix of the file. The NoC energy and area of the smaller switches "
           "are higher than the real values."),
    6418: (WARNING,
           "The NUMA request total {numa_total} is different from the [DRAM] "
           "request total {dram_total}.",
           "NPUWattch uses the NUMA local/remote ratio to divide the NoC "
           "traffic between the dies. The two totals do not agree, but "
           "NPUWattch uses this ratio. The die-to-die part of the NoC energy is "
           "approximate."),
    6419: (WARNING,
           "The NoC traffic split assumes uniform traffic: {fraction:.2f} of "
           "the flits cross a die-to-die channel.",
           "The log has no NUMA local/remote counters. NPUWattch assumes "
           "uniform traffic between the dies. Each crossing flit is charged "
           "one die-to-die channel crossing and a second switch traversal. The "
           "die-to-die part of the NoC energy is approximate."),
    6420: (WARNING,
           "The NoC is not emitted: the BookSim topology {topology!r} is not "
           "supported ({supported}).",
           "This harness models the fly topology with n = 1 and the anynet "
           "topology. The NoC energy and area are not in the results."),

    # -- 65xx dram -----------------------------------------------------------
    6501: (WARNING,
           "--energy-table {file} is not used, because the run has no DRAM "
           "component.",
           "The log has no dram_channels and no DRAM stats. Thus NPUWattch "
           "emits no DRAM component. The DRAM energy table has no effect."),
    6502: ("HarnessError",
           "The default DRAM energy table is not available: {error}",
           "NPUWattch needs a DRAM energy table for the DRAM component. It "
           "could not load the default table, hbm2.yml. Give the energy table "
           "of the run with --energy-table."),
    6503: (INFO,
           "DRAM constants from {name!r} ({file}): activation {act_pj:g} pJ, "
           "transfer {transfer_pj_per_bit:g} pJ/bit ({transfer_split}), "
           "refresh {ref_pj:g} pJ/REFab.",
           "NPUWattch charges the DRAM with the constants of the energy table "
           "that --energy-table gives. No action is necessary."),
    6504: (INFO,
           "DRAM constants from {name!r} ({file}): activation {act_pj:g} pJ, "
           "transfer {transfer_pj_per_bit:g} pJ/bit ({transfer_split}), "
           "refresh from hbm2.yml.",
           "NPUWattch charges the DRAM with the constants of the energy table "
           "that --energy-table gives. This table has no refresh term. Thus "
           "the refresh energy comes from the default table, hbm2.yml."),
    6505: (WARNING,
           "{kernel}: the configuration has no dram_req_size_byte, so "
           "NPUWattch uses {size} B for each DRAM request.",
           "NPUWattch calculates the DRAM byte traffic from the request count "
           "and the request size. The default size is the HBM2 request size. "
           "The VMEM and DMA energy is correct only if the run uses this size. "
           "Give the config.yml of the run with --config-yml."),
    6506: (WARNING,
           "{kernel}: the per-core DMA responses ({dma_total}) are different "
           "from the [DRAM] request total ({dram_total}).",
           "NPUWattch uses the [DRAM] total as the DRAM traffic. It divides "
           "the traffic between the cores with the DMA shares. The per-core "
           "split is approximate."),
    6507: (WARNING,
           "{kernel}: the DRAM statistics block reports {reads} reads and "
           "{writes} writes, but the [DRAM] totals are {log_reads} and "
           "{log_writes}.",
           "The DRAM device energy uses the counts of the statistics block. "
           "The VMEM and NoC traffic uses the [DRAM] interval totals. The two "
           "sources in the log do not agree."),
    6508: (WARNING,
           "{kernel}: the log has no DRAM statistics block, so the "
           "row-activation and refresh energy are not charged.",
           "NPUWattch reads the activation and refresh commands from the "
           "'=== DRAM statistics ===' block. Without it, NPUWattch charges the "
           "read and write energy from the [DRAM] request totals. The DRAM "
           "energy does not include the activation and refresh energy."),
    6509: (WARNING,
           "{kernel}: the run declares the DRAM energy table {declared!r} "
           "({path}), but NPUWattch charges {charged!r} from --energy-table.",
           "The [Config/Energy] block of the log names the energy table of the "
           "run. The table of --energy-table has a different name. The DRAM "
           "energy uses the constants of that table. Give the energy table of "
           "the run with --energy-table."),
    6510: (WARNING,
           "{kernel}: the run declares the DRAM energy table {declared!r} "
           "({path}), but NPUWattch charges the default {charged} table.",
           "The [Config/Energy] block of the log names the energy table of the "
           "run. NPUWattch did not get this table and uses the default table. "
           "The DRAM energy is for the default memory technology. Give the "
           "energy table of the run with --energy-table."),

    # -- 66xx instances ------------------------------------------------------
    6601: (WARNING,
           "{stat}: NPUWattch divides the SFU operations between the cores by "
           "their vector active cycles.",
           "The log gives the SFU operations of the kernel as one total. "
           "NPUWattch divides the total between the cores in proportion to "
           "their vector active cycles. The per-core energy is approximate. "
           "The total energy does not change."),
    6602: (WARNING,
           "{stat}: NPUWattch divides the DRAM→VMEM fill between the cores by "
           "their MOVIN instructions.",
           "The log gives the DRAM→VMEM fill of the kernel as one total. "
           "NPUWattch divides the total between the cores in proportion to "
           "their MOVIN instructions. The per-core energy is approximate. The "
           "total energy does not change."),
    6603: (WARNING,
           "{stat}: NPUWattch divides the VMEM→DRAM drain between the cores by "
           "their MOVOUT instructions.",
           "The log gives the VMEM→DRAM drain of the kernel as one total. "
           "NPUWattch divides the total between the cores in proportion to "
           "their MOVOUT instructions. The per-core energy is approximate. The "
           "total energy does not change."),
    6604: (WARNING,
           "{stat}: NPUWattch divides the stat between the cores by their "
           "systolic active cycles.",
           "The log gives this stat of the kernel as one total. NPUWattch "
           "divides the total between the cores in proportion to their "
           "systolic active cycles. The per-core energy is approximate. The "
           "total energy does not change."),
    6605: (WARNING,
           "There are no per-core {counter} counters, so NPUWattch uses the "
           "systolic active-cycle share.",
           "The per-core counters of this stat are zero or missing. NPUWattch "
           "divides the stat between the cores by their systolic active "
           "cycles. The per-core energy is approximate. The total energy does "
           "not change."),
    6606: (WARNING,
           "{counter}: all values are zero in this window, so NPUWattch "
           "divides the stat equally.",
           "NPUWattch cannot divide the stat by a counter that is zero. It "
           "gives an equal share to each instance. The per-instance energy is "
           "approximate. The total energy does not change."),
    6607: (WARNING,
           "{stat}: NPUWattch divides the kernel total between the arrays by "
           "their active cycles.",
           "The log gives this stat as one total for the kernel. NPUWattch "
           "divides it between the arrays in proportion to the active cycles "
           "of each array. The per-array energy is approximate. The total "
           "energy does not change."),

    # -- 67xx run_config -----------------------------------------------------
    6701: ("RunConfigError",
           "{path}: the content is a {type}, not a YAML mapping.",
           "A config.yml contains a mapping of keys and values. Give the "
           "config.yml of the run with --config-yml."),
    6702: (WARNING,
           "config.yml and the log header have different values for {key}: "
           "{file_value!r} and {log_value!r}.",
           "NPUWattch uses the value of the log header. The two files can come "
           "from different runs. Make sure that config.yml is the file of this "
           "run."),
}, retired=(), source=__name__)
