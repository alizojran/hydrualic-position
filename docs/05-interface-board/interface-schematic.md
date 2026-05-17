# 接口子板原理图

接口板把基带板的位置/状态数据通过三种工业接口送出：**0.5–4.5 V
模拟、IO-Link Class B、RS-485 (Modbus RTU)**，且全部数字隔离。
板上同时承担**外部电源接入、保护、隔离 DC-DC、连接器**。

## 1. 系统层次

```
   外部 9–32 V ──┬── 反接/TVS/EMI 滤波 ──┐
                 │                          │
                 │     ┌───────────────────┘
                 │     ▼
                 │  非隔离侧电源 (基带板用)
                 │
                 ├── 隔离 DC-DC (Vp = 9–32V → Vi = 5V) ──┐
                 │                                          │
                 ▼                                          ▼
   ┌──────────── 隔离屏障 (基本绝缘 1500V_rms) ────────────┐
   │                                                          │
   │  数字隔离 ADuM141D ─── SPI/UART ─── MCU                 │
   │                                                          │
   │  IO-Link Class B ── L6360 (内置隔离 DC-DC)              │
   │  RS-485 ────────── ISO1500 (内置隔离 5kV)               │
   │  模拟输出 ─────── DAC8830 + OPA2188                     │
   │                                                          │
   └──────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                        M12 / DT04 连接器
```

## 2. 输入保护与电源 (非隔离侧)

```
   J1.PIN1 V+ ──┬─ F1 (1A SMD)──┬── D1 SMBJ33CA ──┬── L1 BLM21 ── 5 V Buck
                │                │                  │              (基带板)
                │                ▼                  ▼
                │              GND               C1 100nF
                │
                └──→ Q1 PMOS (PMV45EP) ────── 反接保护
                       │
                      GND
```

参数：
- F1：1 A 自恢复 PTC 保险丝
- D1：SMBJ33CA 双向 TVS，33 V 钳位，5 kW 峰值
- Q1：PMV45EP P-MOSFET，−30 V, 4 A，Rds_on 35 mΩ
- L1：BLM21 共模扼流，4 A @ 100 MHz
- 串接 33 µH 电感 + 220 µF 钽电解，符合 ISO 7637-2 pulse 抑制

## 3. 隔离 DC-DC

输入侧 Vp 由 5 V Buck 输出（来自基带板电源），隔离变压器把能量送
到隔离侧 Vi = 5 V / 200 mA。

| 项目 | 选型 |
|---|---|
| 拓扑 | Royer 自激或 Push-Pull |
| 控制器 | TI SN6505B |
| 变压器 | Würth 750315371 (1:1, 5 kV 隔离) |
| 整流 | BAT54S 肖特基 |
| LDO | TPS7A03 → 3.3 V_iso |
| 隔离电压 | 5 kV_rms 1 min |
| 隔离侧空载电流 | < 20 mA |
| 效率 | ~78 % @ 满载 |

## 4. 模拟输出 0.5–4.5 V

```
   MCU SPI ──► U_DAC (DAC8830, 16-bit) ──► OPA2188 缓冲 ──┐
                                                            │
                                                  ┌────────┘
                                                  │
                                            R_short_prot
                                            (62 Ω, 0.5 W)
                                                  │
                                                  ▼
                                          J_OUT.PIN4 (AOUT)
                                                  │
                                            (PESD 双向 TVS)
                                                  │
                                                 GND
```

- DAC8830：16-bit SPI, ±0.5 LSB INL，输出 0–5 V
- OPA2188：零漂运放，2.5 nV/°C，1 µV 失调
- 整体准确度 ±0.05 % FS over −40~+85 °C
- 短路保护 62 Ω 限流（短到地：72 mA，OPA 输出耐受）
- 故障安全：MCU 写入 < 0.4 V 或 > 4.6 V 表示传感器错误（NAMUR 区）

## 5. IO-Link Class B

```
   MCU UART ──ISO ── L6360 ──┬── DI (data)
                              ├── CQ
                              └── L+/L- (24 V power, Class B aux)
```

- **L6360**：ST IO-Link Class B 收发器，集成隔离 DC-DC，支持
  COM1 (4.8 k), COM2 (38.4 k), COM3 (230.4 k)
- 输入 24 V 来自 J_OUT 的 L+ (符合 IO-Link 规范)
- L6360 内置反接保护 + 输出短路保护
- IO-Link 主站可通过 IODD 文件配置 60 个参数（位置零点、滤波、量
  程、油品参数等），见 [iolink-iodd-draft.md](iolink-iodd-draft.md)

## 6. RS-485 (Modbus RTU)

```
   MCU UART ──ISO── ISO1500 ──┬── A
                                ├── B
                                └── GND_iso
```

- **ISO1500**：ADI 5 kV 隔离 RS-485 收发器，半双工
- 终端电阻 120 Ω 板上常驻 + 跳线可选 (链路末端启用)
- 偏置电阻 680 Ω 上拉/下拉 (失效安全)
- 串行帧 8N1，9600 / 19200 / 115200 bps 可选
- Modbus RTU 协议，从机模式 (slave)，地址 1–247，DIP 配置或 IO-Link 写入
- 寄存器映射见 [modbus-register-map.md](modbus-register-map.md)

## 7. 接口选择逻辑

```
   ┌─────────────────────────────────────────────────────────┐
   │ 启动时 MCU 读 EEPROM 配置:                                │
   │  ─ interface_mode = 0  → 模拟 0.5–4.5 V                   │
   │  ─ interface_mode = 1  → IO-Link Class B                  │
   │  ─ interface_mode = 2  → Modbus RTU                       │
   │  ─ interface_mode = 3  → 模拟 + Modbus (并行输出)         │
   │                                                            │
   │ 也可通过 DIP 开关 (S1[1:0]) 在线选择：                    │
   │  ─ DIP 优先级 > EEPROM (出厂调试用)                       │
   └─────────────────────────────────────────────────────────┘
```

未激活的接口对应 IC **掉电**（通过 LDO EN 引脚），节省功耗。

## 8. 连接器引脚定义

### 8.1 M12 A-code 5-pin (默认)

| Pin | 颜色 | 信号 | 说明 |
|---|---|---|---|
| 1 | 棕 | V+ (9–32 V) | 主电源 |
| 2 | 白 | RS-485 A / IO-Link CQ | 接口模式决定 |
| 3 | 蓝 | GND | |
| 4 | 黑 | RS-485 B / Analog Out | 接口模式决定 |
| 5 | 灰 | SYNC I/O | 多缸同步 |

### 8.2 DEUTSCH DT04-5P (越野/工程机械)

同上引脚，DT04 防护等级 IP69K，振动级别更高。

## 9. EMC 抑制

- 输入端 π 型 (CMC + 22 nF X 电容 + 共模线圈 1 mH)
- 输出端串接 33 nF Y 电容 (信号-地)
- 全板覆盖金属屏蔽罩，单点接地至外壳
- 板厚 1.6 mm FR4，4 层 (Sig/GND/PWR/Sig)

## 10. 测试点 (FCT)

| TP | 信号 | 测试 |
|---|---|---|
| TP_VIN | 输入电压 | 9 / 24 / 32 V 三档验证 |
| TP_VISO | 隔离侧 3.3 V_iso | 3.25 – 3.35 V |
| TP_AOUT | 模拟输出 | DAC = 0x0000 / 0x8000 / 0xFFFF 三点对比 |
| TP_IOLINK | IO-Link CQ | 主站握手 + 数据交换 |
| TP_RS485A | RS-485 A | Modbus poll 验证 |
| TP_DIP | DIP 状态 | 出厂检测 |

## 11. 物理尺寸

- 板尺寸：35 × 30 × 1.6 mm
- 板对板连接器：Samtec ERF8-15-01-S-D-RA (15+15 pin)
- 接口连接器位于板的窄边
- 安装：板对板叠在基带板下方，整体高度 < 10 mm
