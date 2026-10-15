# ============================================================================
# fpga_dac_vco_bringup.xdc
# 任务: fpga输出信号驱动vco产生rf信号的跑通
# 板卡: DaVinci ATK-DF7A35 V2.1 / XC7A35T-2FGG484
# 引脚定义与 passthrough_5mhz / dac_code_test 完全一致 (飞线方案, WIRING.md)
# ============================================================================

set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

set_property -dict {PACKAGE_PIN R4 IOSTANDARD LVCMOS33} [get_ports sys_clk]
set_property -dict {PACKAGE_PIN U2 IOSTANDARD LVCMOS33} [get_ports sys_rst_n]
create_clock -period 20.000 -name sys_clk [get_ports sys_clk]

# AD9767 port 1 -> J2-19..34
set_property -dict {PACKAGE_PIN K16 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[0]}]
set_property -dict {PACKAGE_PIN L16 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[1]}]
set_property -dict {PACKAGE_PIN L20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[2]}]
set_property -dict {PACKAGE_PIN L19 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[3]}]
set_property -dict {PACKAGE_PIN T20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[4]}]
set_property -dict {PACKAGE_PIN U20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[5]}]
set_property -dict {PACKAGE_PIN N19 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[6]}]
set_property -dict {PACKAGE_PIN N18 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[7]}]
set_property -dict {PACKAGE_PIN M20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[8]}]
set_property -dict {PACKAGE_PIN N20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[9]}]
set_property -dict {PACKAGE_PIN J21 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[10]}]
set_property -dict {PACKAGE_PIN J20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[11]}]
set_property -dict {PACKAGE_PIN G20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[12]}]
set_property -dict {PACKAGE_PIN H20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da1_data[13]}]
set_property -dict {PACKAGE_PIN L18 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports da1_clk]
set_property -dict {PACKAGE_PIN M18 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports da1_wrt]

# AD9767 port 2 -> J2-35..50
set_property -dict {PACKAGE_PIN F21 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[0]}]
set_property -dict {PACKAGE_PIN F18 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[1]}]
set_property -dict {PACKAGE_PIN E17 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[2]}]
set_property -dict {PACKAGE_PIN D17 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[3]}]
set_property -dict {PACKAGE_PIN N22 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[4]}]
set_property -dict {PACKAGE_PIN M22 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[5]}]
set_property -dict {PACKAGE_PIN M21 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[6]}]
set_property -dict {PACKAGE_PIN L21 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[7]}]
set_property -dict {PACKAGE_PIN K22 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[8]}]
set_property -dict {PACKAGE_PIN K21 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[9]}]
set_property -dict {PACKAGE_PIN J22 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[10]}]
set_property -dict {PACKAGE_PIN H22 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[11]}]
set_property -dict {PACKAGE_PIN G22 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[12]}]
set_property -dict {PACKAGE_PIN G21 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports {da2_data[13]}]
set_property -dict {PACKAGE_PIN E19 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports da2_clk]
set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports da2_wrt]
