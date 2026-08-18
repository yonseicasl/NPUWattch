# ==============================================================================
# Design Compiler Script ? MyDesign
# ==============================================================================
set topModule  MyDesign
set printModule ./MyDesign
set verilogDir  ./../../../rtl/MyDesign
set target_library ./../MyDBFile
set link_library   "* $target_library"
set_host_options -max_cores 8

# ==============================================================================
# 1. Create Library, Read Designs
# ==============================================================================

# Define the working library path where DC stores intermediate design data
define_design_lib WORK -path ./

# Read all Verilog and SystemVerilog RTL source files from the design directory.
# -autoread recursively picks up all matching files; -top anchors elaboration.
read_file -autoread -format verilog   $verilogDir -top $topModule
read_file -autoread -format sverilog  $verilogDir -top $topModule

# ==============================================================================
# 2. Elaborate and Link
# ==============================================================================

# Elaborate builds the design hierarchy and resolves parameters/generics.
elaborate $topModule

# Set the current working design context for all subsequent commands.
current_design $topModule

# Link resolves all cell references against the target and link libraries.
# Unresolved references will produce ERRORs here ? check link_library if so.
link

# ==============================================================================
# 3. Appended Script Hook
# ==============================================================================

# This section is reserved for externally injected constraints or commands
#START_OF_DC_APPENDED_SCRIPT

#END_OF_DC_APPENDED_SCRIPT

# ==============================================================================
# 4. Compile
# ==============================================================================

# uniquify ensures every instance of a reused module gets a unique copy,
# preventing naming conflicts during hierarchical write-out.
uniquify

# compile_ultra: DesignWare arithmetic architectures + boundary optimization.
# A/B on intmac 32x32 @20nm (2026-07-14): plain compile saturates at a ~6.0 ns
# critical path (ripple-like, 61-65 logic levels); compile_ultra meets 2.5 ns
# (26-30 levels) at 20-24% less area, ~2-5x compile runtime. The dataset must
# not mix netlists from both modes - this flow is compile_ultra everywhere.
compile_ultra

# ==============================================================================
# 5. Write Outputs
# ==============================================================================

# Rename nets and cells to be Verilog-legal before writing (removes special chars).
change_names -rules verilog -hierarchy

# Write the mapped, hierarchical gate-level netlist for hand-off to ICC2.
write -f verilog -hier -o ${printModule}_syn.v

# Write the synthesized SDC ? timing constraints for use in place-and-route.
write_sdc ${printModule}.sdc

# ==============================================================================
# 6. Reporting
# ==============================================================================

# QoR summary ? worst negative slack, total negative slack, and cell count.
report_qor

# Hierarchical power breakdown ? useful for identifying power-hungry blocks.
report_power -hierarchy

# Hierarchical area breakdown ? check against floorplan utilization targets.
report_area -hierarchy

# Worst-path timing report ? verify setup slack meets target before hand-off.
report_timing

# Per-path-class worst paths for the frequency probe (autoprobe.py).
# report_qor lumps every setup path into one 'clk' group, but the sweep clock
# formula needs the input-launched cones separately: set_input_delay tracks
# T/2, so an in2reg cone's budget only grows at half a period and its length
# must be doubled when deriving an achievable clock.
# Every from/to collection is size-guarded: report_timing on an empty
# collection prints an Error line, and 01_syn.sh greps the log for those --
# combinational blocks (no registers) would fail synthesis outright
# (2026-07-23: all 355 NoC probe rows died this way).  autoprobe treats an
# empty bracket as "class absent".  `catch` additionally keeps any report
# surprise from aborting the script.
set nwProbeClk  [get_ports -quiet {i_clk}]
if {[sizeof_collection $nwProbeClk] > 0} {
    set nwProbeIns [remove_from_collection [all_inputs] $nwProbeClk]
} else {
    set nwProbeIns [all_inputs]
}
set nwProbeOuts [all_outputs]
set nwProbeRegD [all_registers -data_pins]
set nwProbeRegC [all_registers -clock_pins]
puts "NW_PATHCLASS in2reg BEGIN"
if {[sizeof_collection $nwProbeIns] > 0 && [sizeof_collection $nwProbeRegD] > 0} {
    catch { report_timing -from $nwProbeIns -to $nwProbeRegD }
}
puts "NW_PATHCLASS in2reg END"
puts "NW_PATHCLASS reg2reg BEGIN"
if {[sizeof_collection $nwProbeRegC] > 0 && [sizeof_collection $nwProbeRegD] > 0} {
    catch { report_timing -from $nwProbeRegC -to $nwProbeRegD }
}
puts "NW_PATHCLASS reg2reg END"
puts "NW_PATHCLASS reg2out BEGIN"
if {[sizeof_collection $nwProbeRegC] > 0 && [sizeof_collection $nwProbeOuts] > 0} {
    catch { report_timing -from $nwProbeRegC -to $nwProbeOuts }
}
puts "NW_PATHCLASS reg2out END"
puts "NW_PATHCLASS in2out BEGIN"
if {[sizeof_collection $nwProbeIns] > 0 && [sizeof_collection $nwProbeOuts] > 0} {
    catch { report_timing -from $nwProbeIns -to $nwProbeOuts }
}
puts "NW_PATHCLASS in2out END"

quit