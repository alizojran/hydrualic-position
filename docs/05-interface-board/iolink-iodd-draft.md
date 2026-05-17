# IO-Link IODD 草案

IO-Link 设备描述 (IODD) 文件最终用 XML 格式，本文档是参数表与
ISDU 索引的草案，方便后续生成 `IRM24-V1-yyyymmdd-IODD1.1.xml`。

## 1. 基本设备信息

| 字段 | 值 |
|---|---|
| Vendor ID | 待申请 |
| Vendor Name | Your Company Name |
| Vendor URL | https://... |
| Device ID | 0x010001 (待分配) |
| Product ID | IRM-24G-V1 |
| Product Name | IRM Hydraulic Position Sensor |
| Product Family | IRM Series |
| Product Text | "Contactless radar-based linear position for hydraulic cylinders" |
| Master Cycle Time | 1.0 ms (min) |
| Min Cycle Time | 1.0 ms |
| IO-Link Revision | 1.1.3 |
| SIO Mode | Yes (back-compat 模拟 PNP) |
| Power | 24 V Class B, max 200 mA |

## 2. Process Data In (设备→主站)

总长 96 bit = 12 byte (PD Length)：

| 偏移 (byte) | 长度 | 类型 | 名称 | 单位 |
|---|---|---|---|---|
| 0–3 | 4 | int32 | Position | µm |
| 4–7 | 4 | int32 | Velocity | µm/s |
| 8 | 1 | uint8 | SNR | 1/2 dB |
| 9 | 1 | uint8 | OilTempC | (offset −40, step 1) |
| 10 | 1 | uint8 | Quality (0–100 %) | % |
| 11 | 1 | uint8 | Status flags | bit-field |

### 2.1 Status flags (byte 11)

| Bit | 含义 |
|---|---|
| 0 | Measurement Valid |
| 1 | Multi-peak warning |
| 2 | Calibrated |
| 3 | Over-temperature |
| 4 | Out-of-range |
| 5 | RF fault |
| 6 | Self-test passed |
| 7 | Reserved |

## 3. Process Data Out (主站→设备)

PD Out 长 16 bit = 2 byte：

| 偏移 | 类型 | 名称 |
|---|---|---|
| 0 | uint8 | Command (0=NOP, 1=Reset, 2=Zero, 3=Auto-cal εr) |
| 1 | uint8 | Reserved |

## 4. ISDU 参数 (索引 / 子索引)

### 4.1 标准参数 (IO-Link 规定)

| Index | Sub | Access | Type | 描述 |
|---|---|---|---|---|
| 0x0002 (2) | 0 | RW | uint8 | System Command (0x80=Restore Factory, 0x82=Reset) |
| 0x0003 (3) | 0 | RW | uint8 | Data Storage Index |
| 0x0010 (16) | 0 | RO | string | Vendor Name |
| 0x0012 (18) | 0 | RO | string | Product Name |
| 0x0014 (20) | 0 | RO | string | Vendor URL |
| 0x0015 (21) | 0 | RO | string | Hardware Revision |
| 0x0016 (22) | 0 | RO | string | Firmware Revision |
| 0x0018 (24) | 0 | RW | string | Application Specific Tag |
| 0x0021 (33) | 0 | RW | string | Function Tag |
| 0x0022 (34) | 0 | RW | string | Location Tag |
| 0x0024 (36) | 0 | RO | uint16 | Device Status |
| 0x0025 (37) | 0 | RO | string | Detailed Device Status |

### 4.2 设备特定参数 (自定义索引 ≥ 64)

| Index | Sub | Access | Type | 默认 | 描述 |
|---|---|---|---|---|---|
| 64 | 0 | RW | int32 | 0 | Position zero offset (µm) |
| 65 | 0 | RW | float | 1.000 | Position gain |
| 66 | 0 | RW | int32 | 0 | Range Low (µm) |
| 67 | 0 | RW | int32 | 2000000 | Range High (µm) |
| 68 | 0 | RW | uint8 | 4 | Kalman strength (0–10) |
| 69 | 0 | RW | uint16 | 1000 | Sample rate Hz |
| 70 | 0 | RW | uint8 | 0 | Fail-safe mode |
| 71 | 0 | RW | uint8 | 0 | Polarity invert |
| 80 | 0 | RW | float | 2.20 | Oil εr at 25 °C |
| 81 | 0 | RW | float | -1.5e-3 | dεr/dT |
| 82 | 0 | RO | float | — | Current εr (live) |
| 83 | 0 | RO | float | — | Current oil temp |
| 84 | 0 | RO | float | — | Current SNR (dB) |
| 90 | 0 | RO | string | — | Serial Number |
| 91 | 0 | RO | uint32 | — | Hour counter |
| 92 | 0 | RO | uint32 | — | Total measurements |
| 100 | 0 | WO | uint8 | — | Trigger: 1=Cal Zero, 2=Cal εr, 3=Save |
| 101 | 0 | RO | uint16[16] | — | Last 16 SNR history |
| 102 | 0 | RO | uint16[16] | — | Last 16 fault codes |

## 5. Events (告警/警告)

IO-Link 设备可主动触发事件 (Event)：

| Code | Type | Severity | 描述 |
|---|---|---|---|
| 0x4000 | Error | Error | RF MMIC fault |
| 0x4001 | Error | Error | PLL unlock |
| 0x4002 | Error | Error | No echo (signal lost) |
| 0x4003 | Error | Error | EEPROM error |
| 0x6000 | Warning | Warning | Multi-peak (multipath) |
| 0x6001 | Warning | Warning | Oil εr drift detected |
| 0x6002 | Warning | Warning | Temperature out of range |
| 0x6003 | Warning | Warning | Calibration aging |
| 0x8C40 | Notification | Notification | Power-up |
| 0x8C41 | Notification | Notification | Configuration changed |

## 6. SIO (Standard I/O) 模式

当 IO-Link 主站不连接时，CQ 引脚自动降级为 SIO：
- 输出 PNP 24 V 高电平 = 位置 0–50 % 行程内
- 切换阈值可通过 ISDU 配置
- 默认作为简单"接近开关"功能

## 7. Data Storage (DS)

IO-Link 1.1 的 Data Storage 机制允许设备热插拔后参数自动恢复：
- 主站缓存 ISDU 64–82 的内容
- 设备替换时，主站把缓存写回新设备 → 现场更换无需重新标定
- 标定数据 (ISDU 84–92) 不参与 DS (设备特定)

## 8. IODD 文件结构 (XML 略)

最终 XML 包含：
- `<DeviceIdentity>` 设备 ID / 厂商 / 修订
- `<DeviceFunction>` 处理数据 + 参数
- `<ProcessDataCollection>` PD In / PD Out 定义
- `<VariableCollection>` ISDU 参数
- `<EventCollection>` Events
- `<UserInterface>` 主站工具 UI (中/英文标签)
- `<DocumentLocation>` 用户手册链接

文件命名遵循 IODD V1.1.3 规范：
`YourCompany-IRM24G-yyyymmdd-IODD1.1.xml`

## 9. 与 ILC 控制器的对接 (推荐路径)

```
   Beckhoff CX (IO-Link Master EL6224)
            │
            ├── IRM #1 (Cyl A)
            ├── IRM #2 (Cyl B)
            ├── IRM #3 (Cyl C)
            └── IRM #N (Cyl N)
                │
                ▼ Process Data 1 kHz 同步
   IEC 61131-3 PLC Runtime
            │
            ▼
   FB_CrossCoupledILC (本仓库 src/)
            │
            ▼
   阀控制 (EtherCAT 输出)
```

IO-Link Master 提供毫秒级同步（PD 周期），且支持热插拔与 Data
Storage，对工业自动化场景比 Modbus 优。**多缸场景 IO-Link 是首
选**。

## 10. 互通性验证矩阵

| Master | 验证状态 (P1 计划) |
|---|---|
| Siemens SIMATIC SIRIUS IO-Link Master | 计划 |
| Beckhoff EL6224 | 计划 |
| IFM AL1100 / AL1300 | 计划 |
| Pepperl+Fuchs ICE3-8IOL-G65L-V1D | 计划 |
| Balluff BNI IOL | 计划 |
| TMG TE/IO-Link Tester | 必做 (CE 认证) |
