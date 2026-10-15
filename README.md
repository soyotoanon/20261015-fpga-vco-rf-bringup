# FPGA输出信号驱动VCO产生RF信号的跑通

本仓库记录并复现以下硬件链路：

`FPGA → AD9767/ACM9767 DAC → VCO/DDS 模拟控制输入 → RF 输出 → 示波器`

仓库包含已经生成的 FPGA 比特流、Verilog/XDC/Vivado 构建文件、构建验证报告，以及用于同时采集 DAC 电压与 DDS RF 幅度的桌面测试程序。

## 目录

```text
fpga/
  bitstream/      已生成的 .bit，可直接烧写
  rtl/            FPGA 顶层 Verilog
  constraints/    ATK-DF7A35 V2.1 引脚约束
  scripts/        Vivado 2023.2 构建脚本
  tb/             行为仿真 testbench
  reports/        DRC、时序和资源报告
  BUILD_VERIFICATION.txt
  README_烧写说明.txt

scope_tester/
  dds_dac_scope_tester.py
  启动DDS-DAC同帧测试.cmd
  安装依赖.cmd
  README.txt
```

## FPGA 固件行为

- 板卡：ATK-DF7A35 V2.1，XC7A35T-2FGG484
- DAC：ACM9767 V1.3 / AD9767，14 bit 双通道
- 时钟：50 MHz
- 上电先输出中点码 `0x2000`，保持约 2.68 s
- 随后从 `0x0000` 到 `0x3FFF` 遍历全部 16384 个码
- 每码保持约 1.31072 ms，一轮约 21.47 s
- 扫描结束后回到中点并循环

直接烧写文件：

```text
fpga/bitstream/fpga_dac_vco_bringup.bit
```

已使用 Vivado 2023.2 完成综合、布局布线、DRC、时序检查和比特流生成。详细结果见 `fpga/BUILD_VERIFICATION.txt`。

## 示波器测试程序

接线：

- RIGOL CH1：DAC 输出
- RIGOL CH2：DDS/VCO RF 输出
- 示波器通过 USB Device 或 LAN 连接电脑

Windows 下双击：

```text
scope_tester/启动DDS-DAC同帧测试.cmd
```

程序会让示波器生成并冻结一个新帧，然后从同一冻结帧读取：

- CH1 `VAVG`：DAC 控制电压
- CH2 `VPP` 或 `VRMS`：RF 幅度
- CH2 `FREQUENCY`：RF 频率

程序显示散点、目标直线、实测线性拟合、R²和斜率倍率，并可导出 CSV。

## 安全说明

第一次使用时先只把 DAC 接入示波器，确认实际电压范围后再连接 VCO/DDS 输入。DAC 的标称全量程不代表目标 ADC/AIN/AM 输入一定允许相同电压范围。请先确认目标接口的允许电压、直流耦合方式和输入结构。

