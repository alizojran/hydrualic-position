#!/usr/bin/env python3
"""
生成 KiCad 8 自定义符号库 irm-symbols.kicad_sym

只覆盖 KiCad 标准库中不存在的器件 (RF MMIC、IO-Link 收发、机械窗等)。
通用器件 (op-amp, LDO, MCU 常见型号、被动) 直接引用 KiCad 内置库。

运行：
    python3 hardware/scripts/generate_symbols.py
输出：
    hardware/libraries/irm-symbols.kicad_sym
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from textwrap import dedent

OUT = os.path.join(os.path.dirname(__file__), "..", "libraries",
                   "irm-symbols.kicad_sym")

PIN_TYPES = {
    "input", "output", "bidirectional", "tri_state", "passive",
    "free", "unspecified", "power_in", "power_out",
    "open_collector", "open_emitter", "no_connect",
}


@dataclass
class Pin:
    number: str
    name: str
    ptype: str = "passive"
    side: str = "L"   # L/R/T/B (left, right, top, bottom)
    y: float = 0.0    # 由布局函数填写
    x: float = 0.0


@dataclass
class Sym:
    name: str
    description: str
    footprint: str
    datasheet: str = ""
    pins: list[Pin] = field(default_factory=list)
    width: float = 25.4         # mm
    pad_top: float = 2.54
    pad_bot: float = 2.54


# -------------------------- 器件定义 --------------------------

BGT24MTR12 = Sym(
    name="BGT24MTR12",
    description="Infineon 24 GHz FMCW Radar Transceiver, VQFN-32",
    footprint="Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.7x3.7mm",
    datasheet="https://www.infineon.com/dgdl/Infineon-BGT24MTR12-DS-v01_01-EN.pdf",
    pins=[
        Pin("1",  "GND",      "power_in",  "L"),
        Pin("2",  "VCC_DIG",  "power_in",  "L"),
        Pin("3",  "SDO",      "output",    "L"),
        Pin("4",  "SDI",      "input",     "L"),
        Pin("5",  "SCK",      "input",     "L"),
        Pin("6",  "~{CS}",    "input",     "L"),
        Pin("7",  "~{INT}",   "output",    "L"),
        Pin("8",  "GND",      "power_in",  "L"),
        Pin("9",  "VCC_PLL",  "power_in",  "L"),
        Pin("10", "REF_IN",   "input",     "L"),
        Pin("11", "REF_OUT",  "output",    "L"),
        Pin("12", "GND",      "power_in",  "L"),
        Pin("13", "VCC_VCO",  "power_in",  "L"),
        Pin("14", "VTUNE",    "passive",   "L"),
        Pin("15", "GND",      "power_in",  "L"),
        Pin("16", "VCC_PA",   "power_in",  "L"),
        Pin("17", "TX_OUT",   "output",    "R"),
        Pin("18", "GND",      "power_in",  "R"),
        Pin("19", "VCC_LNA",  "power_in",  "R"),
        Pin("20", "RX_IN",    "input",     "R"),
        Pin("21", "GND",      "power_in",  "R"),
        Pin("22", "VCC_MIX",  "power_in",  "R"),
        Pin("23", "IFI_P",    "output",    "R"),
        Pin("24", "IFI_N",    "output",    "R"),
        Pin("25", "IFQ_P",    "output",    "R"),
        Pin("26", "IFQ_N",    "output",    "R"),
        Pin("27", "GND",      "power_in",  "R"),
        Pin("28", "VCC_IF",   "power_in",  "R"),
        Pin("29", "NC1",      "no_connect","R"),
        Pin("30", "NC2",      "no_connect","R"),
        Pin("31", "ENABLE",   "input",     "R"),
        Pin("32", "GND",      "power_in",  "R"),
        Pin("33", "EP_GND",   "power_in",  "B"),  # 中央热焊盘
    ],
    width=30.48,
)

ADS5263 = Sym(
    name="ADS5263",
    description="TI 4-ch 16-bit ADC, 100 MSps LVDS, HTQFP-64",
    footprint="Package_QFP:TQFP-64_10x10mm_P0.5mm",
    datasheet="https://www.ti.com/lit/ds/symlink/ads5263.pdf",
    pins=[  # 简化版，按功能分组
        Pin("1",  "AVDD_3V",  "power_in",  "L"),
        Pin("2",  "AGND",     "power_in",  "L"),
        Pin("3",  "INA_P",    "input",     "L"),
        Pin("4",  "INA_N",    "input",     "L"),
        Pin("5",  "INB_P",    "input",     "L"),
        Pin("6",  "INB_N",    "input",     "L"),
        Pin("7",  "INC_P",    "input",     "L"),
        Pin("8",  "INC_N",    "input",     "L"),
        Pin("9",  "IND_P",    "input",     "L"),
        Pin("10", "IND_N",    "input",     "L"),
        Pin("11", "VREF",     "passive",   "L"),
        Pin("12", "AGND",     "power_in",  "L"),
        Pin("13", "CLK_P",    "input",     "L"),
        Pin("14", "CLK_N",    "input",     "L"),
        Pin("15", "SCLK",     "input",     "R"),
        Pin("16", "SDATA",    "bidirectional","R"),
        Pin("17", "SEN",      "input",     "R"),
        Pin("18", "RESET",    "input",     "R"),
        Pin("19", "PDN",      "input",     "R"),
        Pin("20", "DA_P",     "output",    "R"),
        Pin("21", "DA_N",     "output",    "R"),
        Pin("22", "DB_P",     "output",    "R"),
        Pin("23", "DB_N",     "output",    "R"),
        Pin("24", "DC_P",     "output",    "R"),
        Pin("25", "DC_N",     "output",    "R"),
        Pin("26", "DD_P",     "output",    "R"),
        Pin("27", "DD_N",     "output",    "R"),
        Pin("28", "DCLK_P",   "output",    "R"),
        Pin("29", "DCLK_N",   "output",    "R"),
        Pin("30", "DVDD_1V8", "power_in",  "R"),
        Pin("31", "DGND",     "power_in",  "R"),
        Pin("32", "EP_GND",   "power_in",  "B"),
    ],
    width=30.48,
)

L6360 = Sym(
    name="L6360",
    description="ST IO-Link Class B Master/Device Transceiver, VQFN-24",
    footprint="Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
    datasheet="https://www.st.com/resource/en/datasheet/l6360.pdf",
    pins=[
        Pin("1",  "VCC",     "power_in",  "L"),
        Pin("2",  "VCC",     "power_in",  "L"),
        Pin("3",  "GND",     "power_in",  "L"),
        Pin("4",  "GND",     "power_in",  "L"),
        Pin("5",  "VL",      "passive",   "L"),
        Pin("6",  "PG",      "output",    "L"),
        Pin("7",  "EN",      "input",     "L"),
        Pin("8",  "DI",      "input",     "L"),
        Pin("9",  "DO",      "output",    "L"),
        Pin("10", "WU",      "input",     "L"),
        Pin("11", "L+",      "passive",   "R"),
        Pin("12", "CQ",      "bidirectional","R"),
        Pin("13", "L-",      "power_in",  "R"),
        Pin("14", "CL",      "passive",   "R"),
        Pin("15", "SEN_C",   "passive",   "R"),
        Pin("16", "VSW",     "passive",   "R"),
        Pin("17", "BOOT",    "passive",   "R"),
        Pin("18", "VBAT",    "power_in",  "R"),
        Pin("19", "OL1",     "output",    "R"),
        Pin("20", "OL2",     "output",    "R"),
        Pin("21", "FAULT",   "output",    "R"),
        Pin("22", "GND",     "power_in",  "R"),
        Pin("23", "AGND",    "power_in",  "R"),
        Pin("24", "REF",     "passive",   "R"),
        Pin("25", "EP_GND",  "power_in",  "B"),
    ],
)

ISO1500 = Sym(
    name="ISO1500",
    description="ADI 5kV Isolated RS-485 Transceiver, SOIC-16",
    footprint="Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
    datasheet="https://www.analog.com/media/en/technical-documentation/data-sheets/iso1500.pdf",
    pins=[
        Pin("1",  "VCC1",   "power_in",     "L"),
        Pin("2",  "GND1",   "power_in",     "L"),
        Pin("3",  "RXD",    "output",       "L"),
        Pin("4",  "~{RE}",  "input",        "L"),
        Pin("5",  "DE",     "input",        "L"),
        Pin("6",  "TXD",    "input",        "L"),
        Pin("7",  "GND1",   "power_in",     "L"),
        Pin("8",  "VCC1",   "power_in",     "L"),
        Pin("9",  "VCC2",   "power_in",     "R"),
        Pin("10", "GND2",   "power_in",     "R"),
        Pin("11", "Y",      "output",       "R"),
        Pin("12", "Z",      "output",       "R"),
        Pin("13", "B",      "input",        "R"),
        Pin("14", "A",      "input",        "R"),
        Pin("15", "GND2",   "power_in",     "R"),
        Pin("16", "VCC2",   "power_in",     "R"),
    ],
)

ADUM141D = Sym(
    name="ADuM141D",
    description="ADI Quad-channel digital isolator (3/1 forward/reverse), SOIC-16",
    footprint="Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
    datasheet="https://www.analog.com/media/en/technical-documentation/data-sheets/adum140d-141d-142d.pdf",
    pins=[
        Pin("1",  "VDD1",   "power_in",  "L"),
        Pin("2",  "GND1",   "power_in",  "L"),
        Pin("3",  "VIA",    "input",     "L"),
        Pin("4",  "VIB",    "input",     "L"),
        Pin("5",  "VIC",    "input",     "L"),
        Pin("6",  "VOD",    "output",    "L"),
        Pin("7",  "GND1",   "power_in",  "L"),
        Pin("8",  "VDD1",   "power_in",  "L"),
        Pin("9",  "VDD2",   "power_in",  "R"),
        Pin("10", "GND2",   "power_in",  "R"),
        Pin("11", "VID",    "input",     "R"),
        Pin("12", "VOC",    "output",    "R"),
        Pin("13", "VOB",    "output",    "R"),
        Pin("14", "VOA",    "output",    "R"),
        Pin("15", "GND2",   "power_in",  "R"),
        Pin("16", "VDD2",   "power_in",  "R"),
    ],
)

DAC8830 = Sym(
    name="DAC8830",
    description="TI 16-bit Serial DAC, MSOP-8",
    footprint="Package_SO:MSOP-8_3x3mm_P0.65mm",
    datasheet="https://www.ti.com/lit/ds/symlink/dac8830.pdf",
    pins=[
        Pin("1", "~{SYNC}",  "input",     "L"),
        Pin("2", "SCLK",     "input",     "L"),
        Pin("3", "DIN",      "input",     "L"),
        Pin("4", "GND",      "power_in",  "L"),
        Pin("5", "VOUT",     "output",    "R"),
        Pin("6", "VREF",     "passive",   "R"),
        Pin("7", "VDD",      "power_in",  "R"),
        Pin("8", "AGND",     "power_in",  "R"),
    ],
    width=20.32,
)

TPS54360 = Sym(
    name="TPS54360",
    description="TI 60V Synchronous Buck, 3.5A, HSOP-8",
    footprint="Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm",
    datasheet="https://www.ti.com/lit/ds/symlink/tps54360.pdf",
    pins=[
        Pin("1", "BOOT",  "passive",   "L"),
        Pin("2", "VIN",   "power_in",  "L"),
        Pin("3", "EN",    "input",     "L"),
        Pin("4", "RT/CLK","passive",   "L"),
        Pin("5", "FB",    "input",     "R"),
        Pin("6", "COMP",  "passive",   "R"),
        Pin("7", "GND",   "power_in",  "R"),
        Pin("8", "SW",    "output",    "R"),
        Pin("9", "EP_GND","power_in",  "B"),
    ],
    width=20.32,
)

ADM7172 = Sym(
    name="ADM7172",
    description="ADI 6.5V 2A Ultralow-noise LDO, SOIC-8 EP",
    footprint="Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3.1mm",
    datasheet="https://www.analog.com/media/en/technical-documentation/data-sheets/adm7171_7172.pdf",
    pins=[
        Pin("1", "VIN",     "power_in",  "L"),
        Pin("2", "EN",      "input",     "L"),
        Pin("3", "SS",      "passive",   "L"),
        Pin("4", "GND",     "power_in",  "L"),
        Pin("5", "ADJ",     "passive",   "R"),
        Pin("6", "VOUT_SNS","input",     "R"),
        Pin("7", "VOUT",    "power_out", "R"),
        Pin("8", "PGND",    "power_in",  "R"),
        Pin("9", "EP_GND",  "power_in",  "B"),
    ],
    width=20.32,
)

SiT5356 = Sym(
    name="SiT5356_TCXO",
    description="SiTime SiT5356 50 MHz TCXO ±0.5 ppm, 5x3.2mm SMD",
    footprint="Oscillator:Oscillator_SMD_SiTime_5032_4Pin_5.0x3.2mm",
    datasheet="https://www.sitime.com/datasheet/SiT5356",
    pins=[
        Pin("1", "OE",      "input",     "L"),
        Pin("2", "GND",     "power_in",  "L"),
        Pin("3", "CLK_OUT", "output",    "R"),
        Pin("4", "VDD",     "power_in",  "R"),
    ],
    width=12.7,
)

# 机械占位件 — 接到 PCB 上的物理接口
PRESSURE_WINDOW = Sym(
    name="PRESSURE_WINDOW",
    description="Sapphire pressure window + Kovar braze + coaxial probe assembly (mechanical)",
    footprint="irm-footprints:PRESSURE_WINDOW_Probe",
    pins=[
        Pin("1", "RF_IN",   "passive",   "L"),  # 50 Ω 同轴探针端
        Pin("2", "SHIELD",  "passive",   "L"),  # 探针外屏蔽 / 缸体接地
        Pin("3", "PROBE_TIP","passive",  "R"),  # 探针顶端 (机械接触油)
        Pin("4", "WINDOW",  "passive",   "R"),  # 蓝宝石窗 (机械)
    ],
    width=25.4,
)

COAX_LAUNCHER = Sym(
    name="COAX_LAUNCHER",
    description="50 Ω SMA Edge-Launch (Pasternack PE91175) glass-metal sealed",
    footprint="irm-footprints:SMA_EdgeLaunch_PE91175",
    pins=[
        Pin("1", "RF",       "passive",   "R"),
        Pin("2", "SHIELD",   "passive",   "L"),
    ],
    width=12.7,
)

RATRACE_COUPLER = Sym(
    name="RATRACE_COUPLER",
    description="180-deg rat-race hybrid coupler on Rogers RO4350B (PCB structure)",
    footprint="irm-footprints:RatRace_Coupler_24GHz",
    pins=[
        Pin("1", "P1_TX",    "passive",   "L"),  # Σ
        Pin("2", "P2_ANT",   "passive",   "R"),  # 共用天线端
        Pin("3", "P3_RX",    "passive",   "L"),  # Δ
        Pin("4", "P4_TERM",  "passive",   "R"),  # 隔离/终端 50Ω
    ],
    width=25.4,
)


SYMBOLS = [
    BGT24MTR12, ADS5263, L6360, ISO1500, ADUM141D,
    DAC8830, TPS54360, ADM7172, SiT5356,
    PRESSURE_WINDOW, COAX_LAUNCHER, RATRACE_COUPLER,
]


# -------------------------- 布局算法 --------------------------

def layout_pins(sym: Sym) -> tuple[float, float]:
    """把 pin 按 side 排列到 width × height 的矩形上。返回 (width, height)"""
    left = [p for p in sym.pins if p.side == "L"]
    right = [p for p in sym.pins if p.side == "R"]
    bot = [p for p in sym.pins if p.side == "B"]
    top = [p for p in sym.pins if p.side == "T"]

    max_side = max(len(left), len(right))
    height = (max_side + 1) * 2.54 + sym.pad_top + sym.pad_bot
    # 高度对齐 2.54 网格
    height = max(height, 12.7)
    height = math_ceil(height, 2.54)

    w_half = sym.width / 2
    h_half = height / 2

    def spread(pins: list[Pin], side: str) -> None:
        if not pins:
            return
        n = len(pins)
        spacing = 2.54
        if side in ("L", "R"):
            total = (n - 1) * spacing
            y_start = total / 2
            for i, p in enumerate(pins):
                p.y = y_start - i * spacing
                # 对齐 2.54 网格
                p.y = round(p.y / 2.54) * 2.54
                p.x = -w_half - 2.54 if side == "L" else w_half + 2.54
        else:  # T / B
            total = (n - 1) * spacing
            x_start = -total / 2
            for i, p in enumerate(pins):
                p.x = x_start + i * spacing
                p.x = round(p.x / 2.54) * 2.54
                p.y = -h_half - 2.54 if side == "B" else h_half + 2.54

    spread(left, "L")
    spread(right, "R")
    spread(bot, "B")
    spread(top, "T")
    return sym.width, height


def math_ceil(x: float, step: float) -> float:
    import math
    return math.ceil(x / step) * step


# -------------------------- S-Expression 输出 --------------------------

def pin_sexpr(p: Pin, sym_w: float, sym_h: float) -> str:
    rot = {"L": 0, "R": 180, "T": 270, "B": 90}[p.side]
    return dedent(f"""\
      (pin {p.ptype} line
        (at {p.x:.2f} {p.y:.2f} {rot})
        (length 2.54)
        (name "{p.name}" (effects (font (size 1.27 1.27))))
        (number "{p.number}" (effects (font (size 1.27 1.27))))
      )""")


def symbol_sexpr(sym: Sym) -> str:
    w, h = layout_pins(sym)
    w_half, h_half = w / 2, h / 2

    pins_sexpr = "\n".join(pin_sexpr(p, w, h) for p in sym.pins)
    ref_y = h_half + 1.27
    val_y = -h_half - 1.27

    return dedent(f"""\
    (symbol "{sym.name}"
      (pin_names (offset 1.016) hide)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "U"
        (at 0 {ref_y:.2f} 0)
        (effects (font (size 1.27 1.27))))
      (property "Value" "{sym.name}"
        (at 0 {val_y:.2f} 0)
        (effects (font (size 1.27 1.27))))
      (property "Footprint" "{sym.footprint}"
        (at 0 0 0)
        (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "{sym.datasheet}"
        (at 0 0 0)
        (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "{sym.description}"
        (at 0 0 0)
        (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "{sym.name}_0_1"
        (rectangle
          (start {-w_half:.2f} {h_half:.2f})
          (end {w_half:.2f} {-h_half:.2f})
          (stroke (width 0.254) (type solid))
          (fill (type background)))
{pins_sexpr}
      )
    )""")


def build_library() -> str:
    parts = [symbol_sexpr(s) for s in SYMBOLS]
    inner = "\n".join(parts)
    return dedent(f"""\
    (kicad_symbol_lib
      (version 20231120)
      (generator "irm_gen")
      (generator_version "8.0")
    {inner}
    )
    """)


# -------------------------- main --------------------------

def main() -> None:
    lib = build_library()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(lib)
    print(f"Wrote {len(SYMBOLS)} symbols → {OUT}")
    print("Symbols:")
    for s in SYMBOLS:
        print(f"  - {s.name:<22} ({len(s.pins)} pins)  {s.description}")


if __name__ == "__main__":
    main()
