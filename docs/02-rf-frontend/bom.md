# 24 GHz IRM 传感器 BOM (主板 + 接口板)

工程样机阶段元器件清单。每个关键件给出**首选**与**至少一家替代**，
避免单点供应链风险。器件按子系统分组。

## 1. RF 前端 (24 GHz)

| Ref | 描述 | 首选 P/N | 替代 P/N | 备注 |
|---|---|---|---|---|
| U_RF1 | 24 GHz FMCW 收发 MMIC | Infineon **BGT24MTR12** | Silicon Radar TRX_024_054 | VQFN-32, 5×5 mm |
| Y_REF | 50 MHz TCXO ±0.5 ppm | SiTime SiT5356AC-FK-25E0-50.000000 | Crystek CCSO-914X3-50.000 | 相位噪声 −130 dBc/Hz @10kHz |
| U_LDO_RF1 | 低噪 LDO 3.3 V | ADI ADM7172ACPZ-3.3 | TI TPS7A4700 | 10 µV_rms |
| U_LDO_RF2 | 低噪 LDO 1.8 V | ADI ADM7172ACPZ-1.8 | LT LT3045 | |
| 耦合器 | rat-race 微带 | PCB 上实现 | — | RO4350B |
| 探针接口 | 50 Ω 玻璃-金属密封 SMA | Pasternack PE91175 | Huber+Suhner 23_SMA-50-2-19 | 4.5 mm |

## 2. 中频 / ADC 链

| Ref | 描述 | 首选 | 替代 | 备注 |
|---|---|---|---|---|
| U_IFOP1/2 | 低噪运放 (差分缓冲) | TI OPA1612 | ADI LT1819 | 1.1 nV/√Hz |
| U_PGA | 可编程增益放大 | TI LMP8358 | ADI AD8338 | 1×/10×/100× |
| U_ADC | 4 通道 14-bit 100 MSps | TI ADS5263 | ADI AD9253 | LVDS 输出 |
| U_ADC_CLK | ADC 时钟 buffer | TI LMK00301 | — | 由 STM32 同步 |

## 3. 基带 MCU

| Ref | 描述 | 首选 | 替代 | 备注 |
|---|---|---|---|---|
| U_MCU | Cortex-M7 480MHz | STM32H743ZIT6 | NXP MIMXRT1062DVL6A | 2MB Flash / 1MB SRAM |
| Y_MCU | 25 MHz HSE | Abracon ABM3 | — | |
| U_EEPROM | 256 kbit I²C | ST M24M02-DRMN6TP | Microchip 24LC256 | 标定参数 |
| U_FLASH | 64 Mbit QSPI | ISSI IS25LP064A | Winbond W25Q64 | 固件备份 / 日志 |

## 4. 接口板

| Ref | 描述 | 首选 | 替代 | 备注 |
|---|---|---|---|---|
| U_DAC | 16-bit 模拟输出 | TI DAC8830 | ADI AD5683 | 0.5–4.5 V |
| U_OPA_OUT | 输出缓冲 | TI OPA2188 | ADI AD8676 | 零漂 |
| U_IOLINK | IO-Link Class B 收发 | ST L6360 | Maxim MAX22513 | 内置 DC-DC |
| U_RS485 | 隔离 RS-485 | ADI ISO1500 | TI ISO35T | 5 kV iso |
| U_ISO_DIG | 数字隔离器 4ch | ADI ADuM141D | TI ISO7841 | SPI/UART 共用 |

## 5. 电源

| Ref | 描述 | 首选 | 替代 | 备注 |
|---|---|---|---|---|
| Q_REVPOL | 反接保护 PMOS | NXP PMV45EP | Infineon BSP320P | 0.7 W |
| D_TVS_IN | 输入 TVS 33 V | Littelfuse SMBJ33CA | Bourns SMBJ33CA | |
| L_FERRITE | 共模 EMI | TDK MPZ2012S221A | Murata BLM21 | 输入 π |
| U_BUCK1 | 5 V/1 A Buck | TI TPS54360 | ADI LT8640 | 36 V_in |
| U_BUCK2 | 3.6 V/0.5 A | TI TPS54160 | LT3990 | 给 LDO |
| U_BUCK3 | 2.5 V/0.3 A | TI TPS54160 | — | ADC AVDD |
| U_LDO_D | 3.3 V_D | TI LP5907 | Microchip MIC5365 | |

## 6. 连接器与机械

| Ref | 描述 | 首选 | 备注 |
|---|---|---|---|
| J_OUT | 外部接口 (主) | DEUTSCH DT04-5P-EE01 | 防水级 |
| J_OUT_M12 | 外部接口 (可选) | TE 1838249-3 | IP69K |
| 螺纹 | M22×1.5 / M27×2 / G3/4 三规格机壳 | 自制金属壳 | 316L 不锈钢 |
| 密封 | O-Ring + 背靠环 | Parker 2-014 NBR70 + PTFE | 350 bar 静密封 |
| 承压窗 | Φ4 mm 蓝宝石 + Kovar 焊环 | 自制 | 见 04-pressure-window |

## 7. PCB

| 板 | 工艺 | 估价 (100 件) |
|---|---|---|
| RF 主板 (50×30, 6 层, RO4350B 顶层) | 阻抗控制 ±5 % | 30 元/件 |
| 接口板 (35×30, 4 层, FR4) | — | 6 元/件 |

## 8. 关键采购风险

| 件 | 风险 | 缓解 |
|---|---|---|
| BGT24MTR12 | 单一供应商 (Infineon), 周期 12–16 周 | TRX_024 footprint 兼容预留 |
| AWR1243 (77G) | TI 周期 20–26 周 | NXP TEF810x 备选 |
| 蓝宝石承压窗 | 国内可加工厂家少 | 与 PEEK 备选并行设计 |
| 高精度 TCXO | 国外品牌为主 | 国产长城 / 唯捷 备选 |
| ADC ADS5263 | 在生命周期中 | NXP/ADI 备选预留 |

## 9. 单机 BOM 成本预估 (千件量)

| 子系统 | 成本 (USD) |
|---|---|
| RF MMIC + 时钟 + 耦合器 | 22 |
| MCU + ADC + 存储 | 18 |
| 接口 (IO-Link + RS485 + DAC) | 12 |
| 电源 + 保护 | 6 |
| 连接器 + PCB | 9 |
| 机械 (壳 + 窗 + 密封) | 28 |
| **小计 (BOM)** | **95** |
| 制造 + 测试 + 标定 | 25 |
| **出厂成本** | **~120 USD** |

77 GHz 衍生版 BOM 预估 +30 USD（主要为 AWR1243 与高频 PCB）。
