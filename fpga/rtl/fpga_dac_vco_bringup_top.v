`timescale 1ns / 1ps
// ============================================================================
//  fpga_dac_vco_bringup_top.v
//  任务名: fpga输出信号驱动vco产生rf信号的跑通
//
//  板卡: DaVinci ATK-DF7A35 V2.1 / XC7A35T-2FGG484, 50 MHz 晶振
//  DAC : ACM9767 V1.3 (AD9767 双通道 14 位), 偏移二进制码
//        0x0000 -> 约 -5 V,  0x2000 -> 约 0 V,  0x3FFF -> 约 +5 V
//
//  用途: DAC 输出覆盖全量程, 验证
//        FPGA -> AD9767 -> DDS 第8路 VCO ADC输入 -> RF 输出振幅 链路
//
//  行为 (全自动, 无需拨码开关, 循环执行):
//    S_MID : 输出中点码 0x2000 (约 0 V), 保持约 2.7 s
//            —— 上电先给安全电平, 方便确认 DDS 基线
//    S_RAMP: 全量程阶梯扫描 0x0000 -> 0x3FFF
//            每个码停留 2^16 个时钟 (约 1.31 ms), 扫完一圈约 21.5 s
//    S_BACK: 回到中点 0x2000 保持约 2.7 s, 然后再次扫描
//
//  用法提示:
//    - 想改成"固定输出某个码": 把下方 FORCE_FIXED 改为 1, FIXED_CODE 填码值
//    - 想让扫描变慢/变快: 改 DWELL_MAX (每码停留时钟数)
//
//  接口时序与 dac_code_test_top.v 完全一致 (厂家 AN9767 例程做法):
//    数据在时钟下降沿更新, CLK/WRT 直接接 50 MHz 时钟
// ============================================================================
module fpga_dac_vco_bringup_top #(
    // 量产比特流使用下面的默认值；参数化只为便于仿真覆盖整段扫描。
    parameter        FORCE_FIXED = 1'b0,
    parameter [13:0] FIXED_CODE  = 14'h2000,
    parameter [27:0] HOLD_MAX    = 28'd134_217_727,
    parameter [16:0] DWELL_MAX   = 17'd65_535
) (
    input  wire        sys_clk,      // R4, 50 MHz
    input  wire        sys_rst_n,    // U2, 低有效 (板上已上拉)

    output wire [13:0] da1_data,     // AD9767 通道1 数据
    output wire        da1_clk,      // CLK1
    output wire        da1_wrt,      // WRT1

    output wire [13:0] da2_data,     // AD9767 通道2 数据
    output wire        da2_clk,      // CLK2
    output wire        da2_wrt       // WRT2
);

    localparam [13:0] CODE_MID = 14'h2000;         // 中点 ≈ 0 V

    // -------------------- 状态机 --------------------
    localparam [1:0] S_MID  = 2'd0;   // 上电中点保持
    localparam [1:0] S_RAMP = 2'd1;   // 全量程扫描
    localparam [1:0] S_BACK = 2'd2;   // 扫完回中点

    reg [1:0]  state;
    reg [27:0] hold_cnt;
    reg [16:0] dwell_cnt;
    reg [13:0] ramp_code;
    reg [13:0] code;          // 当前输出码

    always @(posedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            state     <= S_MID;
            hold_cnt  <= 28'd0;
            dwell_cnt <= 17'd0;
            ramp_code <= 14'h0000;
            code      <= CODE_MID;
        end else begin
            case (state)
                // ---- 上电/每轮开始: 中点保持 ----
                S_MID: begin
                    code <= CODE_MID;
                    if (hold_cnt == HOLD_MAX) begin
                        hold_cnt  <= 28'd0;
                        dwell_cnt <= 17'd0;
                        ramp_code <= 14'h0000;
                        state     <= S_RAMP;
                    end else begin
                        hold_cnt <= hold_cnt + 28'd1;
                    end
                end

                // ---- 全量程阶梯扫描 0x0000 -> 0x3FFF ----
                S_RAMP: begin
                    code <= ramp_code;
                    if (dwell_cnt == DWELL_MAX) begin
                        dwell_cnt <= 17'd0;
                        if (ramp_code == 14'h3FFF) begin
                            state    <= S_BACK;
                            hold_cnt <= 28'd0;
                        end else begin
                            ramp_code <= ramp_code + 14'd1;
                        end
                    end else begin
                        dwell_cnt <= dwell_cnt + 17'd1;
                    end
                end

                // ---- 扫完回中点, 稍后再次扫描 ----
                default: begin  // S_BACK
                    code <= CODE_MID;
                    if (hold_cnt == HOLD_MAX) begin
                        hold_cnt  <= 28'd0;
                        dwell_cnt <= 17'd0;
                        ramp_code <= 14'h0000;
                        state     <= S_RAMP;
                    end else begin
                        hold_cnt <= hold_cnt + 28'd1;
                    end
                end
            endcase

            // 固定码调试模式: 覆盖状态机输出
            if (FORCE_FIXED)
                code <= FIXED_CODE;
        end
    end

    // ---- 数据在时钟下降沿更新, 给 DAC 留半个周期 (10 ns) 建立时间 ----
    reg [13:0] da1_r;
    reg [13:0] da2_r;

    always @(negedge sys_clk or negedge sys_rst_n) begin
        if (!sys_rst_n) begin
            da1_r <= CODE_MID;
            da2_r <= CODE_MID;
        end else begin
            da1_r <= code;
            da2_r <= code;
        end
    end

    assign da1_data = da1_r;
    assign da2_data = da2_r;

    // 双端口(Dual)模式, 数据在 CLK 与 WRT 上升沿写入, 两者同源
    assign da1_clk  = sys_clk;
    assign da1_wrt  = sys_clk;
    assign da2_clk  = sys_clk;
    assign da2_wrt  = sys_clk;

endmodule
