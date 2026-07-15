# ==============================================================================
# PrimeTime Power Script ? MyDesign
# ==============================================================================

sh date
if {[sizeof_collection [get_designs -quiet *]] > 0} {
    remove_design -all
}

set top_design      "MyDesign"
set target_library  "./../MyDBFile"
set link_library    "* $target_library"
set netlist_file    "./MyDesign_icc2.v"
set sdc_file        "./MyDesign.sdc"
set spef_file       "./MyDesign.spef"
set activity_mode   "unvectored"
set activity_file   ""
set clock_period_ns 5
set_host_options -max_cores 8

read_verilog $netlist_file
current_design $top_design
link

read_sdc $sdc_file
# No -pin_cap_included: StarRC writes the SPEF with *DESIGN_FLOW "PIN_CAP NONE",
# so the pin capacitances are NOT in the file and PT must add them from the
# library. Claiming otherwise leaves every net short of its receiver caps, which
# under-reports both path delay and switching power.
read_parasitics -keep_capacitive_coupling -increment $spef_file

# The netlist is post-CTS: without this PT times an ideal clock (zero insertion
# delay, zero skew) and reports optimistic slack that disagrees with ICC2.
set_propagated_clock [all_clocks]

update_timing -full

set power_enable_analysis TRUE
set power_analysis_mode averaged

#START_OF_PT_APPENDED_SCRIPT
if {$activity_mode eq "vectored"} {
    if {$activity_file eq ""} {
        error "activity_mode is vectored but activity_file is empty"
    }
    set activity_ext [string tolower [file extension $activity_file]]
    if {$activity_ext eq ".saif"} {
        # The TB's SAIF window covers only its random power phase; the file's
        # instance tree is <top>_tb/dut (VCS $toggle_report on "<tb>.dut").
        read_saif -strip_path "${top_design}_tb/dut" $activity_file
    } elseif {$activity_ext eq ".vcd"} {
        read_vcd -strip_path "${top_design}_tb/dut" $activity_file
    } else {
        error "unsupported activity file extension: $activity_file"
    }
} else {
    set inPorts [all_inputs]
    set clockPorts [get_ports -quiet {__CLOCK_PORTS__}]
    set inPortsNoClock [remove_from_collection $inPorts $clockPorts]
    set_switching_activity -static_probability 0.5 -toggle_rate 0.4 $inPortsNoClock -period $clock_period_ns
    set_switching_activity -static_probability 0.5 -toggle_rate 0.2 -type registers -hierarchy -period $clock_period_ns
}
#END_OF_PT_APPENDED_SCRIPT

update_power
check_power
write_sdf -version 2.1 ./${top_design}_pt.sdf

# ==============================================================================
# Reporting
# ==============================================================================
# Redirected to stable file names for the data-collection stage. NOTE: 05_pwr.sh
# copies the whole tool log to power.rpt, so these must not be named power.rpt.

# Power group summary: total internal/switching/leakage/total, split by
# clock_network / register / combinational / sequential. Plain report_power ?
# passing -hierarchy suppresses this table and prints only the instance tree.
redirect -file ./power_summary.rpt {report_power -nosplit}

# Per-instance power tree (same numbers, broken down by hierarchy).
redirect -file ./power_hier.rpt {report_power -verbose -nosplit -hierarchy}

# Signoff timing on the propagated clock. report_global_timing gives WNS/TNS per
# path group directly; the hand-rolled ReportTNS above passes a path-group
# collection where get_timing_paths wants a name, so it finds no paths and prints
# its sentinel (WNS 100000, TNS 0) for every group.
redirect -file ./timing.rpt {report_timing -nets -nosplit}
redirect -file ./global_timing.rpt {report_global_timing}
redirect -file ./constraint.rpt {report_constraint -all_violators -nosplit}

# Coverage check: how many nets actually got parasitics from the SPEF. A low
# number here means the netlist/SPEF names diverged and the run is not post-layout.
redirect -file ./annotated_parasitics.rpt {report_annotated_parasitics}

# Coverage check for vectored runs: how much of the design's activity was
# annotated from the SAIF/VCD vs. filled in by propagation defaults.
redirect -file ./switching_activity.rpt {report_switching_activity}

exit
