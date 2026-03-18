# ==============================================================================
# ICC2 Physical Design Script ? MyDesign
# ==============================================================================

set maindesign      "MyDesign"
set REFERENCE_LIB  "./../MyNDMFile"
set Tech_file      "./../MyTechFile"
set libtluplus     "./../MyTLUFile"
set_host_options -max_cores 16

# ==============================================================================
# 1. Create Library, Read Designs and SDC
# ==============================================================================
create_lib $maindesign -ref_libs $REFERENCE_LIB -technology $Tech_file

read_verilog ./MyDesign_syn.v
read_sdc ./MyDesign.sdc

read_parasitic_tech -tlup $libtluplus -layermap ./../MyMapFile

link_block MyDesign

# ==============================================================================
# 2. Metal Layer Routing Direction
# ==============================================================================
set_attribute [get_layers M1] routing_direction horizontal
set_attribute [get_layers M3] routing_direction horizontal
set_attribute [get_layers M5] routing_direction horizontal
set_attribute [get_layers M7] routing_direction horizontal
set_attribute [get_layers M9] routing_direction horizontal
set_attribute [get_layers M11] routing_direction horizontal
set_attribute [get_layers M2] routing_direction vertical
set_attribute [get_layers M4] routing_direction vertical
set_attribute [get_layers M6] routing_direction vertical
set_attribute [get_layers M8] routing_direction vertical
set_attribute [get_layers M10] routing_direction vertical
set_attribute [get_layers M12] routing_direction vertical

# ==============================================================================
# 3. Floorplan Initialization
# ==============================================================================
initialize_floorplan \
    -control_type      core \
    -core_utilization  0.7 \
    -shape             R \
    -orientation       N \
    -side_ratio        {1.0 1.0} \
    -core_offset       {1} \
    -flip_first_row    true \
    -coincident_boundary true

# Report core area
set core   [get_attribute [get_core_area] bbox]
set core_x [lindex [lindex $core 1] 0]
set core_y [lindex [lindex $core 1] 1]
puts "Core area: $core_x x $core_y"

# ==============================================================================
# 4. Power / Ground Nets
# ==============================================================================
create_net -power  VDD
create_net -ground VSS
connect_pg_net -net VDD [get_pins -physical_context *VDD]
connect_pg_net -net VSS [get_pins -physical_context *VSS]

# ==============================================================================
# 5. Power Planning ? Ring
# ==============================================================================
#create_pg_ring_pattern ring_pattern \
#    -horizontal_layer M9 -horizontal_width {5} -horizontal_spacing {2} \
#    -vertical_layer   M8 -vertical_width   {5} -vertical_spacing   {2}

#set_pg_strategy core_ring \
#    -pattern {{name: ring_pattern} {nets: {VDD VSS}} {offset: {3 3}}} \
#    -core

# ==============================================================================
# 6. Power Planning ? Mesh
# ==============================================================================
#create_pg_mesh_pattern mesh_pattern \
#    -layers { \
#        { {horizontal_layer: M5} {width: 1.104} {spacing: interleaving} {pitch: 8.4}   {offset: 1.4}  {trim: true} } \
#        { {vertical_layer:   M6} {width: 3}     {spacing: interleaving} {pitch: 19.456} {offset: 6.08} {trim: true} } \
#    }

#set_pg_strategy ALL_mesh -core \
#    -pattern {{name: mesh_pattern} {nets: VDD VSS}} \
#    -extension {{stop: innermost_ring}}

# ==============================================================================
# 7. Power Planning ? Standard Cell Rails and Via Rules
# ==============================================================================
create_pg_std_cell_conn_pattern rail_pattern -layers M1

set_pg_strategy M1_rails -core \
    -pattern {{name: rail_pattern} {nets: VDD VSS}} \
    -extension {{stop: core_boundary} {direction: L B R T}}

#set_pg_via_master_rule VIA_6x1 -via_array_dimension {6 1}

#set_pg_strategy_via_rule via_rule -via_rule { \
#    {{{strategies: ALL_mesh} {layers: M2}}  \
#     {{strategies: M1_rails} {layers: M1}}  \
#     {via_master: VIA_6x1}}                     \
#    {{intersection: undefined} {via_master: NIL}} \
#}

compile_pg -strategies {core_ring ALL_mesh M1_rails}

# ==============================================================================
# 8. Pin Assignment
# ==============================================================================
set_block_pin_constraints -self
place_pins -self

# ==============================================================================
# 9. Placement
# ==============================================================================
set_parasitic_parameters \
    -library   $maindesign \
    -early_spec $libtluplus \
    -late_spec  $libtluplus

create_placement -effort high -floorplan

legalize_placement

place_opt

# ==============================================================================
# 10. CTS / Post-CTS Optimization
# ==============================================================================
synthesize_clock_trees

#clock_opt

#save_block -as MyDesign:MyDesign/post_cts.design

# ==============================================================================
# 11. Routing / Post-Route Optimization
# ==============================================================================
route_auto -max_detail_route_iterations 7

#route_opt

# ==============================================================================
# 12. Reporting
# ==============================================================================
report_qor

# ==============================================================================
# 13. Outputs
# ==============================================================================
write_verilog ./MyDesign_icc2.v
write_gds -hierarchy all_design_libs -lib_cell_view layout ./MyDesign.gds
write_def ./MyDesign.def
save_block -as MyDesign:MyDesign/route_opt.design

exit
