# icc2.tcl -- decoder PnR (env-driven; invoked by run_decoder.sh)
#
# Floorplan policy (pitch-matched row decoder): the die HEIGHT is fixed to
# the SRAM array height (rounded UP to a whole std-cell row), the WIDTH is
# derived by run_decoder.sh from the synthesized cell area at the target
# utilization (rounded UP to the placement-site width here).  wl[*] pins go
# on the east edge spread over the array row positions; addr/clk/en/wlen on
# the west edge.
#
# Environment:
#   DEC_TOP        top module (dec_<R>x<C>)
#   DEC_NETLIST    <top>_syn.v          DEC_SDC   <top>.sdc
#   DEC_NDM        std-cell NDM (absolute)
#   DEC_TECHFILE   layout tech file (.mw.tf, absolute)
#   DEC_TLUP       TLUPlus (absolute)   DEC_LAYERMAP  tf<->itf map (absolute)
#   DEC_H_UM       requested die height (array height)
#   DEC_UTIL       target utilization (width = cell_area / (util*H),
#                  computed here from the linked block's own cell areas)
#   DEC_ROWS       wordline count (pin spacing)
#
# Outputs (cwd): <top>.gds, <top>.icc2.v, <top>.def, rails.json, dims.json,
#                icc2_reports/

set top      $env(DEC_TOP)
set netlist  $env(DEC_NETLIST)
set sdcfile  $env(DEC_SDC)
set ndm      $env(DEC_NDM)
set techfile $env(DEC_TECHFILE)
set tlup     $env(DEC_TLUP)
set lmap     $env(DEC_LAYERMAP)
set Hreq     $env(DEC_H_UM)
set util     $env(DEC_UTIL)
set nrows    $env(DEC_ROWS)

set_host_options -max_cores 4

file delete -force ${top}_lib
create_lib ${top}_lib -ref_libs [list $ndm] -technology $techfile
read_verilog -top $top $netlist
link_block
read_sdc $sdcfile
read_parasitic_tech -tlup $tlup -layermap $lmap

# metal layer names differ per node tech file (M0... vs metal0...)
proc mlayer {n} {
    foreach cand [list "M$n" "metal$n"] {
        if {[sizeof_collection [get_layers -quiet $cand]]} { return $cand }
    }
    return ""
}
# metal directions (same convention as the legacy flow)
for {set i 0} {$i <= 9} {incr i} {
    set l [mlayer $i]
    if {$l eq ""} { continue }
    set_attribute [get_layers $l] routing_direction \
        [expr {$i % 2 ? "vertical" : "horizontal"}]
}
# keep top-level routing off M1: the frames under-model cell-internal M1
# (no blockages), so M1 routes can short cell internals (seen at 5nm --
# OAI21 B1 route crossed internal M1 and shorted D/QN).  Pins are still
# reached by via drops from M2.
set_ignored_layers -min_routing_layer [mlayer 2]
# ...and (only where needed) force via landings fully inside the pin shape:
# with an off-pin via the M1 pad can clip an adjacent internal wire (seen at
# 5nm -- the via at the DFF D pin also touched the cell's clock-inverter
# output 8 nm below, shorting D to ckb).  Enabled per node via
# DEC_PIN_VIA_STRICT because the same option at 20nm produced merged decode
# nets in extraction; the larger-pin nodes never needed it.
if {[info exists env(DEC_PIN_VIA_STRICT)] && $env(DEC_PIN_VIA_STRICT) == "1"} {
    set_app_options -name route.common.connect_within_pins_by_layer_name \
        -value [list [list [mlayer 1] via_wire_standard_cell_pins]]
    puts "DECFP strict in-pin via connections enabled"
}

# -- floorplan: fixed height (array-pitch-matched), derived width ---------
# Two passes: the linked netlist's cell areas shrink substantially once
# place_opt resizes for the (easy) 10 ns timing, so a width derived from
# the pre-place areas overshoots badly.  Pass 1 coarse-places in a loose
# box just to get the post-sizing cell area; pass 2 re-floorplans at the
# target utilization and runs the real flow.
proc sum_cell_area {} {
    set a 0.0
    foreach_in_collection c [get_cells -hierarchical \
                                 -filter "is_hierarchical == false"] {
        catch { set a [expr {$a + [get_attribute $c area]}] }
    }
    return $a
}
set site  [index_collection [get_site_defs] 0]
set siteH [get_attribute $site height]
set siteW [get_attribute $site width]
set H [expr {ceil($Hreq / $siteH) * $siteH}]

# widest placed cell (valid after pass-1 placement; from the physical bbox)
proc max_cell_width {} {
    set w 0.0
    foreach_in_collection c [get_cells -hierarchical \
                                 -filter "is_hierarchical == false"] {
        catch {
            set bb [get_attribute $c bbox]
            set cw [expr {[lindex $bb 1 0] - [lindex $bb 0 0]}]
            if {$cw > $w} { set w $cw }
        }
    }
    return $w
}

set area0 [sum_cell_area]
# pass-1 box: loose utilization with a generous floor (>= 30 sites) so even
# a few wide multi-height cells (DFFs) always fit
set W1 [expr {ceil(max($area0 / (0.35 * $H), 30 * $siteW) / $siteW) * $siteW}]
initialize_floorplan -control_type die -boundary \
    [list [list 0 0] [list 0 $H] [list $W1 $H] [list $W1 0]]
set_parasitic_parameters -early_spec $tlup -late_spec $tlup
set_app_options -name place.coarse.continue_on_missing_scandef -value true
create_placement -effort high -floorplan -timing_driven
legalize_placement
place_opt
set cell_area [sum_cell_area]
set wmin [expr {[max_cell_width] + 2 * $siteW}]

set Wreq [expr {max($cell_area / ($util * $H), $wmin)}]
set W [expr {ceil($Wreq / $siteW) * $siteW}]
puts "DECFP pre-place area ${area0} -> post-sizing ${cell_area} um2, site ${siteW}x${siteH} -> die ${W}x${H}"

initialize_floorplan -control_type die -boundary \
    [list [list 0 0] [list 0 $H] [list $W $H] [list $W 0]]

# -- pin constraints: wl east at row pitch, controls west -----------------
set pitch [expr {double($H) / $nrows}]
for {set i 0} {$i < $nrows} {incr i} {
    set y [expr {($i + 0.5) * $pitch}]
    set_individual_pin_constraints -ports [get_ports "wl\[$i\]"] \
        -location [list $W $y]
}
set ins [remove_from_collection [all_inputs] [get_ports wl*]]
set nin [sizeof_collection $ins]
set k 0
foreach_in_collection p $ins {
    set y [expr {($k + 0.5) * double($H) / $nin}]
    set_individual_pin_constraints -ports $p -location [list 0 $y]
    incr k
}

# -- PG: M0 std-cell rails (legacy pattern) --------------------------------
if {![sizeof_collection [get_nets -quiet VDD]]} { create_net -power  VDD }
if {![sizeof_collection [get_nets -quiet VSS]]} { create_net -ground VSS }
connect_pg_net -net VDD [get_pins -physical_context *VDD]
connect_pg_net -net VSS [get_pins -physical_context *VSS]
create_pg_std_cell_conn_pattern rail_pattern -layers [mlayer 0]
set_pg_strategy M0_rails -core \
    -pattern {{name: rail_pattern}{nets: VDD VSS}} \
    -extension {{stop: core_boundary}{direction: L B R T}}
compile_pg -strategies {M0_rails}

# -- place / CTS / route ---------------------------------------------------
create_placement -effort high -floorplan -timing_driven
legalize_placement
place_pins -self
place_opt
synthesize_clock_trees
clock_opt
route_auto
route_opt

file mkdir icc2_reports
redirect icc2_reports/timing.rpt      { report_timing }
redirect icc2_reports/utilization.rpt { report_utilization }
redirect icc2_reports/design.rpt      { report_design -library }

write_verilog ${top}.icc2.v
write_gds -hierarchy all_design_libs -lib_cell_view layout ${top}.gds
write_def ${top}.def

# -- rails.json: exact VDD/VSS M0 rail tracks for the GDT labeler ----------
proc shape_net_name {sh} {
    foreach attr {net.full_name net.name net_name} {
        if {![catch {get_attribute -quiet $sh $attr} v] && $v ne ""} {
            return $v
        }
    }
    return ""
}
set ys(VDD) {}
set ys(VSS) {}
foreach_in_collection sh [get_shapes -quiet -filter "layer_name == [mlayer 0]"] {
    set n [shape_net_name $sh]
    if {$n ne "VDD" && $n ne "VSS"} { continue }
    set bb [get_attribute $sh bbox]
    set y0 [lindex $bb 0 1]
    set y1 [lindex $bb 1 1]
    set x0 [lindex $bb 0 0]
    set x1 [lindex $bb 1 0]
    # full-width horizontal rails only (skip cell-internal / follow shapes)
    if {[expr {$x1 - $x0}] < [expr {0.5 * $::W}]} { continue }
    lappend ys($n) [format %.4f [expr {($y0 + $y1) / 2.0}]]
}
set f [open rails.json w]
puts $f "{"
puts $f " \"die_w_um\": $W, \"die_h_um\": $H,"
puts $f " \"vdd_ys\": \[[join [lsort -real -unique $ys(VDD)] ,]\],"
puts $f " \"vss_ys\": \[[join [lsort -real -unique $ys(VSS)] ,]\]"
puts $f "}"
close $f

# -- dims.json: area sidecar source ----------------------------------------
set cell_area 0.0
foreach_in_collection c [get_cells -hierarchical -filter "is_hierarchical == false"] {
    catch { set cell_area [expr {$cell_area + [get_attribute $c area]}] }
}
set f [open dims.json w]
puts $f [format {{
 "die_w_um": %.4f, "die_h_um": %.4f,
 "die_area_um2": %.4f, "cell_area_um2": %.4f,
 "site_w_um": %.4f, "site_h_um": %.4f
}} $W $H [expr {$W * $H}] $cell_area $siteW $siteH]
close $f

save_block
exit
