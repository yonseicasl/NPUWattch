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

# Standard compile ? balances runtime and QoR for most designs.
# compile_ultra (commented below) provides higher effort at longer runtime;
# enable it for timing-critical blocks once basic flow is verified.
compile
#compile_ultra -no_autoungroup -no_boundary_optimization

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

quit