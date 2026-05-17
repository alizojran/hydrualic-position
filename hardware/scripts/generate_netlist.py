#!/usr/bin/env python3
"""
生成 KiCad 兼容的网络表 + 人可读 wire-list + CSV BOM。

把 docs/02-rf-frontend/24ghz-schematic.md 与
docs/05-interface-board/interface-schematic.md 中描述的电路结构
落地成确切的元件 + 连接，供 KiCad 原理图绘制 / PCB 导入参考。

输出文件 (在 hardware/build/):
    rf-mainboard.net           KiCad legacy netlist
    rf-mainboard-wires.txt     人可读 wire-list
    interface-board.net
    interface-board-wires.txt
    bom-rf-mainboard.csv
    bom-interface-board.csv

运行：python3 hardware/scripts/generate_netlist.py
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

HW = os.path.join(os.path.dirname(__file__), "..")
BUILD = os.path.join(HW, "build")


@dataclass
class Comp:
    ref: str           # 位号 U1, R3, C12 ...
    value: str         # 值 / 型号
    footprint: str
    lib_part: str      # KiCad 符号 lib:name
    desc: str = ""

    def __post_init__(self) -> None:
        # KiCad 引脚连接 {pin_number: net_name}
        self.connections: dict[str, str] = {}


def c(ref: str, value: str, fp: str, lib: str, desc: str = "") -> Comp:
    return Comp(ref=ref, value=value, footprint=fp, lib_part=lib, desc=desc)


# 通用封装 / 符号简写
RES_0402 = "Resistor_SMD:R_0402_1005Metric"
CAP_0402 = "Capacitor_SMD:C_0402_1005Metric"
CAP_0603 = "Capacitor_SMD:C_0603_1608Metric"
IND_0603 = "Inductor_SMD:L_0603_1608Metric"

R = "Device:R"
C_ = "Device:C"
L_ = "Device:L"


# ============================================================
#                       RF 主板 网络表
# ============================================================

def rf_mainboard() -> list[Comp]:
    comps: list[Comp] = []

    # ---------- MMIC + RF 前端 ----------
    U_MMIC = c("U1", "BGT24MTR12",
               "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.7x3.7mm",
               "irm-symbols:BGT24MTR12",
               "24 GHz FMCW Transceiver")
    U_MMIC.connections.update({
        # 电源
        "2":  "+3V3_RF", "9":  "+3V3_RF", "13": "+3V3_RF",
        "16": "+3V3_RF", "19": "+3V3_RF", "22": "+1V8_RF",
        "28": "+1V8_RF",
        "1":  "GND", "8":  "GND", "12": "GND", "15": "GND",
        "18": "GND", "21": "GND", "27": "GND", "32": "GND",
        "33": "GND",
        # SPI 到 MCU
        "3":  "MMIC_SDO",  "4":  "MMIC_SDI",
        "5":  "MMIC_SCK",  "6":  "MMIC_nCS",
        "7":  "MMIC_INT",
        # 参考时钟
        "10": "REF_50M", "11": "REF_OUT",
        # 调谐控制 (PLL 内部，可不外接)
        "14": "VTUNE_TP",
        # RF 端口
        "17": "RF_TX",
        "20": "RF_RX",
        # IF 差分输出 (到 PGA / ADC)
        "23": "IFI_P", "24": "IFI_N",
        "25": "IFQ_P", "26": "IFQ_N",
        # 控制
        "31": "MMIC_EN",
        # NC
        "29": "", "30": "",
    })
    comps.append(U_MMIC)

    # MMIC 去耦
    for i, (pin, net) in enumerate([
        ("2", "+3V3_RF"), ("9", "+3V3_RF"), ("13", "+3V3_RF"),
        ("16", "+3V3_RF"), ("19", "+3V3_RF"),
        ("22", "+1V8_RF"), ("28", "+1V8_RF"),
    ]):
        cap = c(f"C{100+i}", "100nF", CAP_0402, "Device:C", "MMIC decap")
        cap.connections = {"1": net, "2": "GND"}
        comps.append(cap)
    for i, net in enumerate(["+3V3_RF", "+1V8_RF"]):
        cap = c(f"C{120+i}", "10uF", CAP_0603, "Device:C", "MMIC bulk")
        cap.connections = {"1": net, "2": "GND"}
        comps.append(cap)

    # 参考 TCXO
    Y1 = c("Y1", "SiT5356 50MHz",
           "Oscillator:Oscillator_SMD_SiTime_5032_4Pin_5.0x3.2mm",
           "irm-symbols:SiT5356_TCXO",
           "50 MHz TCXO ±0.5 ppm")
    Y1.connections = {"1": "+3V3_RF", "2": "GND", "3": "REF_50M", "4": "+3V3_RF"}
    comps.append(Y1)
    cap_y = c("C130", "10nF", CAP_0402, "Device:C", "TCXO decap")
    cap_y.connections = {"1": "+3V3_RF", "2": "GND"}
    comps.append(cap_y)

    # Rat-race 耦合器
    BL1 = c("BL1", "RatRace_24GHz",
            "irm-footprints:RatRace_Coupler_24GHz",
            "irm-symbols:RATRACE_COUPLER",
            "180° rat-race hybrid")
    BL1.connections = {
        "1": "RF_TX",       # Σ
        "2": "RF_ANT",      # 共用天线端口
        "3": "RF_RX",       # Δ
        "4": "RF_TERM50",   # 隔离端 → 50Ω 终端
    }
    comps.append(BL1)

    # 50 Ω 终端 (rat-race iso port)
    R_TERM = c("R1", "50",
               "Resistor_SMD:R_0402_1005Metric_HF",
               "Device:R", "RF 50Ω termination")
    R_TERM.connections = {"1": "RF_TERM50", "2": "GND"}
    comps.append(R_TERM)

    # 探针/承压窗组件
    PW = c("MK1", "PRESSURE_WINDOW",
           "irm-footprints:PRESSURE_WINDOW_Probe",
           "irm-symbols:PRESSURE_WINDOW",
           "Sapphire pressure window + probe")
    PW.connections = {"1": "RF_ANT", "2": "GND", "3": "", "4": ""}
    comps.append(PW)

    # 可选: 在生产板上 SMA edge-launch (用于工程样机测试)
    J_SMA = c("J1", "SMA_EdgeLaunch",
              "irm-footprints:SMA_EdgeLaunch_PE91175",
              "irm-symbols:COAX_LAUNCHER",
              "Optional SMA for board test (DNI in production)")
    J_SMA.connections = {"1": "RF_ANT_TP", "2": "GND"}
    comps.append(J_SMA)

    # ---------- IF 链 ----------
    # IF I 通道差分缓冲 OPA1612
    U_IFOP1 = c("U2", "OPA1612",
                "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                "Amplifier_Operational:OPA1612xD",
                "Dual low-noise op-amp (IF_I diff buffer)")
    U_IFOP1.connections = {
        "1": "IFI_BUF_P_OUT",     # OUT_A
        "2": "IFI_P_FB",           # -IN_A
        "3": "IFI_P",              # +IN_A
        "4": "GND",                # V-
        "5": "IFI_N",              # +IN_B
        "6": "IFI_N_FB",           # -IN_B
        "7": "IFI_BUF_N_OUT",     # OUT_B
        "8": "+5V_ANALOG",         # V+
    }
    comps.append(U_IFOP1)
    # IF Q 通道
    U_IFOP2 = c("U3", "OPA1612",
                "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                "Amplifier_Operational:OPA1612xD",
                "Dual low-noise op-amp (IF_Q diff buffer)")
    U_IFOP2.connections = {
        "1": "IFQ_BUF_P_OUT", "2": "IFQ_P_FB", "3": "IFQ_P",
        "4": "GND", "5": "IFQ_N", "6": "IFQ_N_FB",
        "7": "IFQ_BUF_N_OUT", "8": "+5V_ANALOG",
    }
    comps.append(U_IFOP2)

    # IF 反馈电阻 (简化, 增益 = 10)
    for i, (label, p_in, p_fb, p_out) in enumerate([
        ("IFI_P", "IFI_P", "IFI_P_FB", "IFI_BUF_P_OUT"),
        ("IFI_N", "IFI_N", "IFI_N_FB", "IFI_BUF_N_OUT"),
        ("IFQ_P", "IFQ_P", "IFQ_P_FB", "IFQ_BUF_P_OUT"),
        ("IFQ_N", "IFQ_N", "IFQ_N_FB", "IFQ_BUF_N_OUT"),
    ]):
        r_fb = c(f"R{10+i*2}", "10k", RES_0402, "Device:R", f"IF feedback {label}")
        r_fb.connections = {"1": p_out, "2": p_fb}
        comps.append(r_fb)
        r_gnd = c(f"R{11+i*2}", "1k", RES_0402, "Device:R", f"IF gain set {label}")
        r_gnd.connections = {"1": p_fb, "2": "GND"}
        comps.append(r_gnd)

    # ---------- ADC ----------
    U_ADC = c("U4", "ADS5263",
              "Package_QFP:TQFP-64_10x10mm_P0.5mm",
              "irm-symbols:ADS5263",
              "Quad 16-bit ADC, 100 MSps")
    U_ADC.connections = {
        "1": "+3V3_ADC",
        "2": "GND", "12": "GND", "31": "GND",
        # 模拟输入 (前两路用于 IF I, 后两路 IF Q)
        "3": "IFI_BUF_P_OUT", "4": "IFI_BUF_N_OUT",   # ch A = IF_I
        "5": "IFI_BUF_P_OUT", "6": "IFI_BUF_N_OUT",   # ch B = IF_I (备份)
        "7": "IFQ_BUF_P_OUT", "8": "IFQ_BUF_N_OUT",   # ch C = IF_Q
        "9": "IFQ_BUF_P_OUT", "10":"IFQ_BUF_N_OUT",
        "11": "ADC_VREF",
        "13": "ADC_CLK_P", "14": "ADC_CLK_N",
        "15": "ADC_SCLK", "16": "ADC_SDATA",
        "17": "ADC_SEN", "18": "ADC_nRESET", "19": "ADC_PDN",
        # LVDS 数据 (到 MCU)
        "20": "ADC_DA_P", "21": "ADC_DA_N",
        "22": "ADC_DB_P", "23": "ADC_DB_N",
        "24": "ADC_DC_P", "25": "ADC_DC_N",
        "26": "ADC_DD_P", "27": "ADC_DD_N",
        "28": "ADC_DCLK_P", "29": "ADC_DCLK_N",
        "30": "+1V8_ADC",
        "32": "GND",
    }
    comps.append(U_ADC)
    # ADC 去耦
    for i, (pin, net) in enumerate([("1", "+3V3_ADC"), ("30", "+1V8_ADC")]):
        cap = c(f"C{140+i}", "100nF", CAP_0402, "Device:C", "ADC decap")
        cap.connections = {"1": net, "2": "GND"}
        comps.append(cap)
        cap = c(f"C{142+i}", "10uF", CAP_0603, "Device:C", "ADC bulk")
        cap.connections = {"1": net, "2": "GND"}
        comps.append(cap)
    # ADC VREF cap
    r_vref = c("C150", "10uF", CAP_0603, "Device:C", "ADC VREF")
    r_vref.connections = {"1": "ADC_VREF", "2": "GND"}
    comps.append(r_vref)

    # ---------- MCU STM32H743ZIT6 (LQFP144) ----------
    # 简化引脚映射 — 实际全引脚在 KiCad 内置库符号上完整
    U_MCU = c("U5", "STM32H743ZIT6",
              "Package_QFP:LQFP-144_20x20mm_P0.5mm",
              "MCU_ST_STM32H7:STM32H743ZITx",
              "Cortex-M7 @ 480 MHz, 2MB Flash / 1MB SRAM")
    U_MCU.connections = {
        # 仅关键引脚 (完整由 KiCad 内置符号决定)
        # SPI1 → MMIC
        "85": "MMIC_SCK", "84": "MMIC_SDO", "86": "MMIC_SDI",
        "83": "MMIC_nCS", "82": "MMIC_INT", "81": "MMIC_EN",
        # SPI2 → ADC config
        "78": "ADC_SCLK", "77": "ADC_SDATA", "79": "ADC_SEN",
        "76": "ADC_nRESET", "75": "ADC_PDN",
        # SAI / LVDS (并不直接对接, 实际用 FMC 或专用 LVDS PHY)
        # 简化: 用 GPIO 模拟读 (低带宽场景) 或外加 LVDS 接收器
        "100": "ADC_DCLK_P", "101": "ADC_DA_P",
        "102": "ADC_DB_P", "103": "ADC_DC_P", "104": "ADC_DD_P",
        # I2C → EEPROM
        "92": "I2C1_SCL", "93": "I2C1_SDA",
        # QSPI → 外置 Flash
        "60": "QSPI_CLK", "61": "QSPI_IO0", "62": "QSPI_IO1",
        "63": "QSPI_IO2", "64": "QSPI_IO3", "59": "QSPI_nCS",
        # UART4 (到接口板 IO-Link / Modbus)
        "48": "IF_UART_TX", "49": "IF_UART_RX",
        # SPI4 (到接口板 DAC + 隔离)
        "44": "IF_SPI_SCK", "45": "IF_SPI_MOSI", "46": "IF_SPI_MISO",
        "47": "IF_SPI_nCS",
        # 同步 I/O
        "50": "SYNC_IN", "51": "SYNC_OUT",
        # 调试 SWD
        "72": "SWDIO", "76": "SWCLK", "121": "NRST",
        # 时钟 25 MHz
        "23": "MCU_HSE_IN", "24": "MCU_HSE_OUT",
        # 电源 (典型 LQFP144 几组 VDD/VSS)
        "11": "+3V3_D", "19": "+3V3_D", "28": "+3V3_D", "50": "+3V3_D",
        "75": "+3V3_D", "100": "+3V3_D", "111": "+3V3_D", "143": "+3V3_D",
        "6": "+1V8_MCU",  # VCAP
        "10": "GND", "20": "GND", "27": "GND", "49": "GND",
        "74": "GND", "99": "GND", "112": "GND", "144": "GND",
        # 这里只列了部分,实际由 KiCad 符号自动映射
    }
    comps.append(U_MCU)

    # MCU 去耦 (10+ 路)
    for i in range(10):
        cap = c(f"C{160+i}", "100nF", CAP_0402, "Device:C", "MCU decap")
        cap.connections = {"1": "+3V3_D", "2": "GND"}
        comps.append(cap)
    for i in range(2):
        cap = c(f"C{170+i}", "10uF", CAP_0603, "Device:C", "MCU bulk")
        cap.connections = {"1": "+3V3_D", "2": "GND"}
        comps.append(cap)

    # MCU 25 MHz crystal
    Y2 = c("Y2", "25MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
           "Device:Crystal", "MCU HSE")
    Y2.connections = {"1": "MCU_HSE_IN", "2": "GND",
                      "3": "MCU_HSE_OUT", "4": "GND"}
    comps.append(Y2)
    for i, (p, val) in enumerate([("MCU_HSE_IN", "18pF"),
                                   ("MCU_HSE_OUT", "18pF")]):
        cap = c(f"C{180+i}", val, CAP_0402, "Device:C", "Crystal load")
        cap.connections = {"1": p, "2": "GND"}
        comps.append(cap)

    # EEPROM
    U_EE = c("U6", "M24M02",
             "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
             "Memory_EEPROM:M24M02-DRMN6TP",
             "256 kbit I2C EEPROM (calibration)")
    U_EE.connections = {
        "1": "GND", "2": "GND", "3": "GND",   # A0-A2 = 0
        "4": "GND",
        "5": "I2C1_SDA", "6": "I2C1_SCL",
        "7": "GND",  # WC
        "8": "+3V3_D",
    }
    comps.append(U_EE)

    # QSPI Flash (固件备份)
    U_FL = c("U7", "IS25LP064A",
             "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
             "Memory_Flash:IS25LP064A",
             "64Mbit QSPI Flash")
    U_FL.connections = {
        "1": "QSPI_nCS", "2": "QSPI_IO1", "3": "QSPI_IO2",
        "4": "GND", "5": "QSPI_IO0", "6": "QSPI_CLK",
        "7": "QSPI_IO3", "8": "+3V3_D",
    }
    comps.append(U_FL)

    # ---------- 电源 ----------
    # Buck1: 9-32V → 5V
    U_BUCK1 = c("U10", "TPS54360",
                "Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm",
                "irm-symbols:TPS54360",
                "Buck #1: VIN → 5V/1A")
    U_BUCK1.connections = {
        "1": "BUCK1_BOOT", "2": "VIN_FILT", "3": "BUCK1_EN",
        "4": "BUCK1_RT", "5": "BUCK1_FB", "6": "BUCK1_COMP",
        "7": "GND", "8": "BUCK1_SW", "9": "GND",
    }
    comps.append(U_BUCK1)
    # Buck1 外围 (示意)
    lb1 = c("L1", "33uH", "Inductor_SMD:L_Bourns-SRP1265A", "Device:L",
            "Buck1 inductor")
    lb1.connections = {"1": "BUCK1_SW", "2": "+5V"}
    comps.append(lb1)

    # Buck2: 9-32V → 3.6V (给 RF LDO)
    U_BUCK2 = c("U11", "TPS54160",
                "Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm",
                "irm-symbols:TPS54360",
                "Buck #2: VIN → 3.6V/0.5A (RF rail pre-LDO)")
    U_BUCK2.connections = {
        "2": "VIN_FILT", "7": "GND", "9": "GND",
        "8": "BUCK2_SW",
        # 其余引脚省略
    }
    comps.append(U_BUCK2)

    # LDO 3V3_RF (低噪)
    U_LDO_RF1 = c("U12", "ADM7172_3.3",
                  "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3.1mm",
                  "irm-symbols:ADM7172",
                  "LDO: 3.6V → 3.3V_RF (10 µV_rms)")
    U_LDO_RF1.connections = {
        "1": "+3V6", "2": "+3V6", "3": "LDO1_SS",
        "4": "GND", "5": "LDO1_ADJ", "6": "+3V3_RF",
        "7": "+3V3_RF", "8": "GND", "9": "GND",
    }
    comps.append(U_LDO_RF1)

    # LDO 1V8_RF
    U_LDO_RF2 = c("U13", "ADM7172_1.8",
                  "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3.1mm",
                  "irm-symbols:ADM7172",
                  "LDO: 3.6V → 1.8V_RF")
    U_LDO_RF2.connections = {
        "1": "+3V6", "2": "+3V6", "3": "LDO2_SS",
        "4": "GND", "5": "LDO2_ADJ", "6": "+1V8_RF",
        "7": "+1V8_RF", "8": "GND", "9": "GND",
    }
    comps.append(U_LDO_RF2)

    # LDO 3V3_D (数字)
    U_LDO_D = c("U14", "LP5907_3.3",
                "Package_TO_SOT_SMD:SOT-23-5",
                "Regulator_Linear:LP5907MFX-3.3",
                "LDO: 5V → 3.3V_D")
    U_LDO_D.connections = {
        "1": "+5V", "2": "GND", "3": "LDO_D_EN",
        "4": "", "5": "+3V3_D",
    }
    comps.append(U_LDO_D)

    # 反接保护 + TVS
    Q_REV = c("Q1", "PMV45EP",
              "Package_TO_SOT_SMD:SOT-23",
              "Transistor_FET:PMV45EP",
              "Reverse polarity protection P-MOSFET")
    Q_REV.connections = {"1": "VIN", "2": "VIN_PROT", "3": "GND"}
    comps.append(Q_REV)
    D_TVS = c("D1", "SMBJ33CA", "Diode_SMD:D_SMB",
              "Diode:SMBJ33CA", "Input TVS")
    D_TVS.connections = {"1": "VIN_PROT", "2": "GND"}
    comps.append(D_TVS)
    L_EMI = c("L_EMI", "BLM21_4A", "Inductor_SMD:L_0805_2012Metric",
              "Device:L", "Input EMI filter")
    L_EMI.connections = {"1": "VIN_PROT", "2": "VIN_FILT"}
    comps.append(L_EMI)

    # 板对板连接器 (到接口板)
    J_B2B = c("J10", "ERF8-15-D",
              "Connector:Samtec_ERF8-015-05.0-S-DV-FR_2x15_P0.80mm_Horizontal",
              "Connector:Conn_02x15_Counter_Clockwise",
              "Board-to-board to interface board")
    j_pins = {
        "1": "VIN_PROT", "2": "GND",
        "3": "+5V", "4": "GND",
        "5": "+3V3_D", "6": "GND",
        "7": "IF_UART_TX", "8": "IF_UART_RX",
        "9": "IF_SPI_SCK", "10": "IF_SPI_MOSI",
        "11": "IF_SPI_MISO", "12": "IF_SPI_nCS",
        "13": "SYNC_IN", "14": "SYNC_OUT",
        "15": "I2C1_SCL", "16": "I2C1_SDA",
        "17": "INT_TEMP_ADC", "18": "GND",
        "19": "FAULT_OUT", "20": "GND",
        # 21-30: 备用 / 隔离信号
    }
    for k in range(21, 31):
        j_pins[str(k)] = ""
    J_B2B.connections = j_pins
    comps.append(J_B2B)

    return comps


# ============================================================
#                     接口板 网络表
# ============================================================

def interface_board() -> list[Comp]:
    comps: list[Comp] = []

    # 板对板连接器 (来自主板)
    J_B2B = c("J20", "ERF8-15-D",
              "Connector:Samtec_ERF8-015-05.0-S-DV-FR_2x15_P0.80mm_Horizontal",
              "Connector:Conn_02x15_Counter_Clockwise",
              "From main board")
    J_B2B.connections = {
        "1": "VIN_PROT", "2": "GND",
        "3": "+5V", "4": "GND",
        "5": "+3V3_D", "6": "GND",
        "7": "MCU_UART_TX", "8": "MCU_UART_RX",
        "9": "MCU_SPI_SCK", "10": "MCU_SPI_MOSI",
        "11": "MCU_SPI_MISO", "12": "MCU_SPI_nCS",
        "13": "SYNC_IN", "14": "SYNC_OUT",
    }
    for k in range(15, 31):
        J_B2B.connections[str(k)] = ""
    comps.append(J_B2B)

    # 数字隔离器 (SPI/UART 跨过隔离屏障)
    U_ISO = c("U30", "ADuM141D",
              "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
              "irm-symbols:ADuM141D",
              "4-channel digital isolator")
    U_ISO.connections = {
        "1": "+3V3_D", "2": "GND",          # 非隔离侧
        "3": "MCU_SPI_SCK",    # VIA (input)
        "4": "MCU_SPI_MOSI",   # VIB
        "5": "MCU_SPI_nCS",    # VIC
        "6": "ISO_SPI_MISO",   # VOD (reverse)
        "7": "GND", "8": "+3V3_D",
        "9": "+3V3_ISO", "10": "GND_ISO",  # 隔离侧
        "11": "ISO_SPI_MISO_FROM_DAC",     # VID
        "12": "ISO_SPI_nCS",   # VOC
        "13": "ISO_SPI_MOSI",  # VOB
        "14": "ISO_SPI_SCK",   # VOA
        "15": "GND_ISO", "16": "+3V3_ISO",
    }
    comps.append(U_ISO)

    # 隔离 DC-DC (SN6505 + 变压器)
    U_DCDC = c("U31", "SN6505B",
               "Package_TO_SOT_SMD:SOT-23-6",
               "Power_Management:SN6505B",
               "Isolated DC-DC primary driver")
    U_DCDC.connections = {
        "1": "+5V", "2": "DCDC_D1", "3": "DCDC_D2",
        "4": "GND", "5": "DCDC_CLK", "6": "DCDC_EN",
    }
    comps.append(U_DCDC)
    TX1 = c("T1", "Würth_750315371",
            "Transformer_SMD:Transformer_Wuerth_750315371",
            "Transformer:Transformer_1P_1S",
            "Isolation transformer 5kV, 1:1")
    TX1.connections = {
        "1": "DCDC_D1", "2": "DCDC_D2",
        "3": "+5V", "4": "GND",
        "5": "DCDC_OUT_P", "6": "DCDC_OUT_N",
        "7": "GND_ISO", "8": "GND_ISO",
    }
    comps.append(TX1)

    # 整流肖特基
    D_R1 = c("D10", "BAT54S", "Package_TO_SOT_SMD:SOT-23",
             "Diode:BAT54S", "Rectifier")
    D_R1.connections = {"1": "DCDC_OUT_P", "2": "+5V_ISO_PRE", "3": "DCDC_OUT_N"}
    comps.append(D_R1)

    # LDO 3V3_ISO
    U_LDO_ISO = c("U32", "TPS7A03_3.3",
                  "Package_TO_SOT_SMD:SOT-23-5",
                  "Regulator_Linear:TPS7A0333",
                  "Isolated 3.3V LDO")
    U_LDO_ISO.connections = {
        "1": "+5V_ISO_PRE", "2": "GND_ISO", "3": "TPS_EN",
        "4": "", "5": "+3V3_ISO",
    }
    comps.append(U_LDO_ISO)

    # DAC 模拟输出
    U_DAC = c("U33", "DAC8830",
              "Package_SO:MSOP-8_3x3mm_P0.65mm",
              "irm-symbols:DAC8830",
              "16-bit DAC")
    U_DAC.connections = {
        "1": "ISO_SPI_nCS", "2": "ISO_SPI_SCK", "3": "ISO_SPI_MOSI",
        "4": "GND_ISO", "5": "DAC_OUT", "6": "DAC_VREF",
        "7": "+3V3_ISO", "8": "GND_ISO",
    }
    comps.append(U_DAC)
    # VREF 4.096V
    U_VREF = c("U34", "REF3040",
               "Package_TO_SOT_SMD:SOT-23",
               "Reference_Voltage:REF3040",
               "4.096V precision reference")
    U_VREF.connections = {"1": "+5V_ISO_PRE", "2": "GND_ISO", "3": "DAC_VREF"}
    comps.append(U_VREF)

    # 输出运放 (0.5–4.5V 缩放)
    U_OPA = c("U35", "OPA2188",
              "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
              "Amplifier_Operational:OPA2188xD",
              "Zero-drift dual op-amp (analog output)")
    U_OPA.connections = {
        "1": "AOUT_BUF",        # OUT_A
        "2": "AOUT_FB",         # -IN_A
        "3": "DAC_OUT",         # +IN_A
        "4": "GND_ISO",         # V-
        "5": "AOUT_REF",        # +IN_B
        "6": "AOUT_FB_B",       # -IN_B
        "7": "AOUT_REF_BUF",    # OUT_B
        "8": "+5V_ISO_PRE",     # V+
    }
    comps.append(U_OPA)

    # 输出限流 + ESD
    R_OUT = c("R30", "62", RES_0402, "Device:R",
              "Output current limit")
    R_OUT.connections = {"1": "AOUT_BUF", "2": "AOUT"}
    comps.append(R_OUT)
    D_OUT = c("D11", "PESD2CAN",
              "Package_TO_SOT_SMD:SOT-23",
              "Diode:PESD2CAN", "Output ESD")
    D_OUT.connections = {"1": "AOUT", "2": "GND_ISO", "3": "GND_ISO"}
    comps.append(D_OUT)

    # IO-Link 收发 L6360
    U_IOLINK = c("U36", "L6360",
                 "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
                 "irm-symbols:L6360",
                 "IO-Link Class B Master/Device transceiver")
    U_IOLINK.connections = {
        "1": "VBAT_24V_ISO", "2": "VBAT_24V_ISO",
        "3": "GND_ISO", "4": "GND_ISO",
        "5": "L6360_VL", "6": "L6360_PG",
        "7": "L6360_EN", "8": "L6360_DI_TXD",
        "9": "L6360_DO_RXD", "10": "L6360_WU",
        "11": "L_PLUS_24V",  # 外部 24V (来自主站)
        "12": "CQ_LINE",     # 数据线
        "13": "L_MINUS",     # 0V
        "14": "L6360_CL",
        "15": "L6360_SEN", "16": "L6360_VSW",
        "17": "L6360_BOOT", "18": "L_PLUS_24V",  # VBAT2
        "19": "L6360_OL1", "20": "L6360_OL2",
        "21": "L6360_FAULT",
        "22": "GND_ISO", "23": "GND_ISO",
        "24": "L6360_REF", "25": "GND_ISO",
    }
    comps.append(U_IOLINK)
    # L6360 boost inductor + caps (简化)
    lb_l6360 = c("L20", "33uH", "Inductor_SMD:L_4x4_H1.8",
                 "Device:L", "L6360 boost L")
    lb_l6360.connections = {"1": "L6360_VSW", "2": "L6360_BOOT"}
    comps.append(lb_l6360)

    # RS-485 (Modbus RTU)
    U_RS485 = c("U37", "ISO1500",
                "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
                "irm-symbols:ISO1500",
                "Isolated RS-485 transceiver, 5kV")
    U_RS485.connections = {
        "1": "+3V3_D", "2": "GND",        # 非隔离侧 (来自 MCU)
        "3": "MCU_UART_RX",                # RXD (output to MCU)
        "4": "RS485_nRE", "5": "RS485_DE",
        "6": "MCU_UART_TX",                # TXD (input from MCU)
        "7": "GND", "8": "+3V3_D",
        "9": "+3V3_ISO", "10": "GND_ISO",  # 隔离侧
        "11": "RS485_Y", "12": "RS485_Z",
        "13": "RS485_B", "14": "RS485_A",
        "15": "GND_ISO", "16": "+3V3_ISO",
    }
    comps.append(U_RS485)
    # RS-485 终端 / 失效安全偏置
    R_TERM_RS = c("R31", "120", RES_0402, "Device:R", "RS-485 termination")
    R_TERM_RS.connections = {"1": "RS485_A", "2": "RS485_B"}
    comps.append(R_TERM_RS)
    R_BIAS_HI = c("R32", "680", RES_0402, "Device:R", "RS-485 fail-safe bias hi")
    R_BIAS_HI.connections = {"1": "+3V3_ISO", "2": "RS485_A"}
    comps.append(R_BIAS_HI)
    R_BIAS_LO = c("R33", "680", RES_0402, "Device:R", "RS-485 fail-safe bias lo")
    R_BIAS_LO.connections = {"1": "RS485_B", "2": "GND_ISO"}
    comps.append(R_BIAS_LO)

    # 外部接口 — M12 5-pin (默认)
    J_OUT = c("J21", "M12-5P",
              "Connector:Conn_M12_A_5p_Solder",
              "Connector:Conn_01x05_Pin",
              "M12 A-code 5-pin (configurable)")
    J_OUT.connections = {
        "1": "L_PLUS_24V",   # V+
        "2": "CQ_OR_RS485A", # CQ (IOL) 或 A (RS485)
        "3": "L_MINUS",      # 0V
        "4": "AOUT_OR_RS485B", # Analog OUT 或 B (RS485)
        "5": "SYNC_EXT",
    }
    comps.append(J_OUT)

    # 接口模式选择 — DIP 开关
    SW_MODE = c("SW1", "DIP-2",
                "Button_Switch_SMD:SW_DIP_SPSTx02_Slide_Copal_CHS-02B_W7.62mm_P1.27mm",
                "Switch:SW_DIP_x02",
                "Interface mode selector")
    SW_MODE.connections = {"1": "MODE_BIT0", "2": "+3V3_ISO",
                            "3": "MODE_BIT1", "4": "+3V3_ISO"}
    comps.append(SW_MODE)

    # 接口路由 — 由 MCU 通过模拟开关 / GPIO 切换 (简化为软件层面)
    # 实物可加 TS3A4751 模拟开关。这里留出 net 名给后期。

    return comps


# ============================================================
#                    输出格式
# ============================================================

def write_kicad_netlist(board_name: str, comps: list[Comp],
                        out_path: str) -> None:
    """KiCad 旧版 netlist (.net) 格式"""
    nets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cp in comps:
        for pin, net in cp.connections.items():
            if net:  # 跳过 NC
                nets[net].append((cp.ref, pin))

    lines = [f"(export (version D)",
             f"  (design",
             f'    (source "{board_name}.kicad_sch")',
             f'    (date "2026-05-17")',
             f'    (tool "irm_gen 0.1"))',
             f"  (components"]
    for cp in comps:
        lines.append(f'    (comp (ref "{cp.ref}")')
        lines.append(f'      (value "{cp.value}")')
        lines.append(f'      (footprint "{cp.footprint}")')
        if cp.desc:
            lines.append(f'      (description "{cp.desc}")')
        lines.append(f'      (libsource (lib "{cp.lib_part.split(":")[0]}") '
                     f'(part "{cp.lib_part.split(":")[1]}")))')
    lines.append("  )")
    lines.append("  (nets")
    for i, (net_name, conns) in enumerate(sorted(nets.items()), start=1):
        lines.append(f'    (net (code "{i}") (name "{net_name}")')
        for ref, pin in conns:
            lines.append(f'      (node (ref "{ref}") (pin "{pin}")))')
    lines.append("  )")
    lines.append(")")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  wrote {out_path}")


def write_wire_list(board_name: str, comps: list[Comp],
                    out_path: str) -> None:
    """人可读 wire-list"""
    nets: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cp in comps:
        for pin, net in cp.connections.items():
            if net:
                nets[net].append((cp.ref, pin, cp.value))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {board_name} — Wire List\n\n")
        f.write(f"共 {len(comps)} 个元件, {len(nets)} 个网络。\n\n")

        f.write("## 元件 (按位号)\n\n")
        f.write("| Ref | Value | Footprint | Lib | Desc |\n")
        f.write("|-----|-------|-----------|-----|------|\n")
        for cp in sorted(comps, key=lambda x: (x.ref[0], int(''.join(c for c in x.ref[1:] if c.isdigit()) or '0'))):
            f.write(f"| {cp.ref} | {cp.value} | `{cp.footprint}` | `{cp.lib_part}` | {cp.desc} |\n")

        f.write("\n## 网络连接 (按 net 名)\n\n")
        for net_name in sorted(nets.keys()):
            conns = nets[net_name]
            f.write(f"### `{net_name}`  ({len(conns)} 节点)\n\n")
            for ref, pin, val in sorted(conns):
                f.write(f"- {ref}.{pin}  ({val})\n")
            f.write("\n")
    print(f"  wrote {out_path}")


def write_bom_csv(board_name: str, comps: list[Comp],
                  out_path: str) -> None:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for cp in comps:
        grouped[(cp.value, cp.footprint)].append(cp.ref)

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Qty", "Value", "Footprint", "References", "Description"])
        for (val, fp), refs in sorted(grouped.items()):
            example = next(c for c in comps if c.value == val
                           and c.footprint == fp)
            w.writerow([len(refs), val, fp,
                        " ".join(sorted(refs)), example.desc])
    print(f"  wrote {out_path}")


# ============================================================

def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    print("Generating RF mainboard…")
    rf = rf_mainboard()
    write_kicad_netlist("rf-mainboard", rf,
                        os.path.join(BUILD, "rf-mainboard.net"))
    write_wire_list("rf-mainboard", rf,
                    os.path.join(BUILD, "rf-mainboard-wires.md"))
    write_bom_csv("rf-mainboard", rf,
                  os.path.join(BUILD, "bom-rf-mainboard.csv"))

    print("\nGenerating interface board…")
    iface = interface_board()
    write_kicad_netlist("interface-board", iface,
                        os.path.join(BUILD, "interface-board.net"))
    write_wire_list("interface-board", iface,
                    os.path.join(BUILD, "interface-board-wires.md"))
    write_bom_csv("interface-board", iface,
                  os.path.join(BUILD, "bom-interface-board.csv"))

    print(f"\nTotal: RF {len(rf)} comps, Interface {len(iface)} comps")


if __name__ == "__main__":
    main()
