# dc.tcl -- decoder synthesis (env-driven; invoked by run_decoder.sh)
#
# Environment:
#   DEC_TOP         top module name (dec_<R>x<C>)
#   DEC_RTL         decoder RTL file
#   DEC_DB          std-cell .db (absolute path, from tech_libs catalog)
#   DEC_CLK_NS      clock period in ns (SRAM flow op cadence: 10)
#   DEC_WL_LOAD_PF  per-WL-output pin load in pF (array wordline cap)
#   DEC_LOAD_SCALE  pF -> library-cap-unit multiplier (check units.rpt)
#
# Outputs (cwd): <top>_syn.v, <top>.sdc, area.rpt, qor.rpt, timing.rpt,
#                units.rpt, cells.rpt

set top        $env(DEC_TOP)
set rtl        $env(DEC_RTL)
set dbfile     $env(DEC_DB)
set clk_ns     $env(DEC_CLK_NS)
set wl_load_pf $env(DEC_WL_LOAD_PF)
set load_scale $env(DEC_LOAD_SCALE)

set_app_var target_library [list $dbfile]
set_app_var link_library   [concat {*} [list $dbfile]]

read_verilog $rtl
current_design $top
link
uniquify

create_clock -name clk -period $clk_ns [get_ports clk]
set_input_delay  0.5 -clock clk \
    [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay 0.5 -clock clk [all_outputs]

# Wordline load drives the WL driver sizing -- this is what makes the
# decoder netlist column-count dependent.
set_load [expr {$wl_load_pf * $load_scale}] [get_ports wl*]
set_max_fanout 8 [current_design]
# minimize area (the 10 ns cadence is trivially met) -- without this the
# floorplan width is derived from an oversized netlist that place_opt then
# shrinks, and the achieved utilization lands far below the target
set_max_area 0

compile

redirect units.rpt  { report_units }
redirect area.rpt   { report_area }
redirect qor.rpt    { report_qor }
redirect timing.rpt { report_timing }
redirect cells.rpt  { report_cell }

write -format verilog -hierarchy -output ${top}_syn.v
write_sdc ${top}.sdc
exit
