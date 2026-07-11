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

proc ReportTNS {} {
    suppress_message CMD-041

    set design_tns 0
    set design_wns 100000
    set design_tps 0
    foreach_in_collection group [get_path_groups *] {
        set group_tns 0
        set group_wns 100000
        set group_tps 0
        foreach_in_collection path [get_timing_paths -nworst 1 -max_paths 1000000 -group $group] {
            set slack [get_attribute $path slack]
            if {$slack < $group_wns} {
                set group_wns $slack
                if {$slack < $design_wns} {
                    set design_wns $slack
                }
            }
            if {$slack < 0.0} {
                set group_tns [expr $group_tns + $slack]
            } else {
                set group_tps [expr $group_tps + $slack]
            }
        }
        set design_tns [expr $design_tns + $group_tns]
        set design_tps [expr $design_tps + $group_tps]
        set group_name [get_attribute $group full_name]
        echo [format "Group %s Worst Negative Slack : %g" $group_name $group_wns]
        echo [format "Group %s Total Negative Slack : %g" $group_name $group_tns]
        echo [format "Group %s Total Positive Slack : %g" $group_name $group_tps]
        echo ""
    }
    echo "------------------------------------------"
    echo [format "Design Worst Negative Slack : %g" $design_wns]
    echo [format "Design Total Negative Slack : %g" $design_tns]
    echo [format "Design Total Positive Slack : %g" $design_tps]

    unsuppress_message CMD-041
}

read_verilog $netlist_file
current_design $top_design
link

read_sdc $sdc_file
read_parasitics -pin_cap_included -keep_capacitive_coupling -increment $spef_file

report_timing -nets -nosplit
ReportTNS

set power_enable_analysis TRUE
set power_analysis_mode averaged

#START_OF_PT_APPENDED_SCRIPT
if {$activity_mode eq "vectored"} {
    if {$activity_file eq ""} {
        error "activity_mode is vectored but activity_file is empty"
    }
    set activity_ext [string tolower [file extension $activity_file]]
    if {$activity_ext eq ".saif"} {
        read_saif -input $activity_file -instance_name $top_design
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
report_power -verbose -nosplit -hierarchy

exit
