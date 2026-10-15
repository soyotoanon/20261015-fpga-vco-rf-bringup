`timescale 1ns / 1ps

module tb_fpga_dac_vco_bringup;
    reg sys_clk = 1'b0;
    reg sys_rst_n = 1'b0;

    wire [13:0] da1_data;
    wire        da1_clk;
    wire        da1_wrt;
    wire [13:0] da2_data;
    wire        da2_clk;
    wire        da2_wrt;

    integer expected_code;
    integer checks;
    reg     scanning;

    always #10 sys_clk = ~sys_clk; // 50 MHz

    fpga_dac_vco_bringup_top #(
        .HOLD_MAX (28'd2),
        .DWELL_MAX(17'd0)
    ) dut (
        .sys_clk  (sys_clk),
        .sys_rst_n(sys_rst_n),
        .da1_data (da1_data),
        .da1_clk  (da1_clk),
        .da1_wrt  (da1_wrt),
        .da2_data (da2_data),
        .da2_clk  (da2_clk),
        .da2_wrt  (da2_wrt)
    );

    task fail;
        input [8*120-1:0] message;
        begin
            $display("SIM_FAIL: %0s at %0t ns", message, $time);
            $finish;
        end
    endtask

    initial begin
        expected_code = 0;
        checks = 0;
        scanning = 1'b0;

        #75;
        sys_rst_n = 1'b1;

        // 一次完整 14-bit 扫描只需约 328 us（仿真把每码停留缩为 1 拍）。
        #500000;
        fail("timeout before completing full-range scan");
    end

    // 数据在下降沿寄存，延后 1 ns 避开非阻塞赋值的 delta-cycle。
    always @(negedge sys_clk) begin
        if (sys_rst_n) begin
            #1;

            if ((da1_clk !== 1'b0) || (da1_wrt !== 1'b0) ||
                (da2_clk !== 1'b0) || (da2_wrt !== 1'b0))
                fail("forwarded DAC clock/write signals do not follow sys_clk");

            if ((da1_data !== da2_data))
                fail("DAC channel 1 and channel 2 data differ");

            if (!scanning) begin
                if (da1_data == 14'h0000) begin
                    scanning = 1'b1;
                    expected_code = 0;
                end
            end

            if (scanning) begin
                if (da1_data !== expected_code[13:0])
                    fail("full-range scan is not monotonic or skipped a code");

                checks = checks + 1;
                if (expected_code == 14'h3fff) begin
                    // 下一拍必须安全回到中点码。
                    @(negedge sys_clk);
                    #1;
                    if ((da1_data !== 14'h2000) || (da2_data !== 14'h2000))
                        fail("scan did not return to midpoint after full scale");
                    if (checks != 16384)
                        fail("scan did not cover exactly all 16384 DAC codes");
                    $display("SIM_PASS: covered 0x0000..0x3fff, checks=%0d", checks);
                    $finish;
                end
                expected_code = expected_code + 1;
            end
        end
    end

endmodule
