# Modbus RTU 寄存器映射

IRM 传感器作为 Modbus RTU **从机 (Slave)**，默认地址 0x01，
波特率 19200 8N1。本表是 V1 寄存器规范，用于上位机 (PLC/HMI)
读取位置/状态、配置参数、读取诊断。

## 1. 通讯参数 (默认)

| 项 | 值 |
|---|---|
| 物理层 | RS-485 半双工 |
| 协议 | Modbus RTU |
| Slave 地址 | 1 (1–247 可配) |
| 波特率 | 19200 (9600 / 38400 / 57600 / 115200 可选) |
| 数据位 | 8 |
| 奇偶 | None (E / O 可选) |
| 停止位 | 1 |
| 帧间隔 | ≥ 3.5 字符 |
| CRC | Modbus CRC-16 (poly 0xA001) |

## 2. 支持的功能码

| FC | 名称 | 用途 |
|---|---|---|
| 0x03 | Read Holding Registers | 读位置、状态、参数 |
| 0x04 | Read Input Registers | 读只读诊断 |
| 0x06 | Write Single Register | 写单参数 |
| 0x10 | Write Multiple Registers | 批量写参数 |
| 0x2B | Read Device Identification | 设备信息 |

## 3. Holding Registers (FC 0x03 / 0x06 / 0x10)

> 所有寄存器 16-bit。32-bit 数据占 2 个连续寄存器，**Big-Endian**
> (高字在低地址)。浮点为 IEEE 754 single。

### 3.1 测量数据 (只读，地址 0x0000–0x001F)

| 地址 | 寄存器数 | 类型 | 单位 | 描述 |
|---|---|---|---|---|
| 0x0000 | 2 | int32 | µm | 当前活塞位置 |
| 0x0002 | 2 | int32 | µm | 速度 |
| 0x0004 | 2 | float | mm | 位置 (浮点冗余表示) |
| 0x0006 | 2 | float | mm/s | 速度 (浮点) |
| 0x0008 | 1 | uint16 | — | 测量计数器 (递增) |
| 0x0009 | 1 | uint16 | 1/10 dB | 主峰回波 SNR |
| 0x000A | 1 | int16 | 0.1 °C | 油温 |
| 0x000B | 1 | int16 | 0.1 °C | 传感器内部温度 |
| 0x000C | 2 | float | — | 当前 ε_r 估计 |
| 0x000E | 1 | uint16 | — | 主峰幅度 (0–65535) |
| 0x000F | 1 | uint16 | — | TM02 副峰幅度 |
| 0x0010 | 4 | uint32×2 | µs | 时间戳 (low/high, monotonic) |
| 0x0014 | 1 | uint16 | bit-field | 状态字 (见 §3.5) |
| 0x0015 | 1 | uint16 | bit-field | 错误字 (见 §3.6) |
| 0x0016 | 1 | uint16 | — | 当前激活接口 (0=AN 1=IOL 2=Mod) |
| 0x0017 | 1 | uint16 | — | 固件版本 (高字节主，低字节次) |

### 3.2 配置参数 (读/写，地址 0x0100–0x01FF)

> 写入后需要用 FC 0x06 写 0x01FE = 0xCAFE 触发 EEPROM 保存

| 地址 | 寄存器数 | 类型 | 默认 | 描述 |
|---|---|---|---|---|
| 0x0100 | 1 | uint16 | 0 | 接口选择 0=AN 1=IOL 2=Mod 3=AN+Mod |
| 0x0101 | 1 | uint16 | 1 | Modbus Slave 地址 (1–247) |
| 0x0102 | 1 | uint16 | 4 | 波特率索引 0=9600 1=19200 2=38400 3=57600 4=115200 |
| 0x0103 | 1 | uint16 | 0 | 奇偶 0=N 1=E 2=O |
| 0x0104 | 1 | uint16 | 1000 | 测量更新率 Hz (500/1000/2000) |
| 0x0105 | 2 | int32 | 0 | 零位偏移 (µm) — 装机后用户写入 |
| 0x0107 | 2 | float | 1.0 | 增益 (用户线性校正) |
| 0x0109 | 2 | int32 | 0 | 行程下限 (µm) |
| 0x010B | 2 | int32 | 2000000 | 行程上限 (µm) |
| 0x010D | 1 | uint16 | 4 | Kalman 滤波强度 (0=off, 1–10) |
| 0x010E | 2 | float | 2.20 | 油 ε_r (25°C) — 标定值 |
| 0x0110 | 2 | float | -0.0015 | dε_r/dT (1/°C) |
| 0x0112 | 1 | uint16 | 0 | 故障安全模式 0=保持 1=NAMUR 2=零 |
| 0x0113 | 1 | uint16 | 0 | 极性反转 (0=正向 1=反向) |
| 0x0114 | 2 | uint32 | 0 | 用户标签 (字串 ASCII 4字节) |
| 0x0116 | 8 | string | "" | 安装位置标签 (16 字符) |
| 0x01FE | 1 | uint16 | — | **0xCAFE = 保存到 EEPROM** |
| 0x01FF | 1 | uint16 | — | **0xDEAD = 恢复出厂** |

### 3.3 标定数据 (读/特权写，0x0200–0x02FF)

写需要先写口令 0x02FE = 0x55AA (出厂口令)。

| 地址 | 类型 | 描述 |
|---|---|---|
| 0x0200..0x021F | float×16 | 全程标定查找表 (16 点行程 vs 实际距离) |
| 0x0220..0x023F | float×16 | 同上查找表的位置坐标 |
| 0x0240..0x024F | float×8 | 温度系数表 |
| 0x02F0..0x02FD | string | 出厂序列号 (28 字符) |
| 0x02FE | uint16 | 写口令解锁 |

### 3.4 命令寄存器 (写触发动作，0x0300–0x030F)

| 地址 | 写入值 → 动作 |
|---|---|
| 0x0300 | 0x0001 = 软复位 |
| 0x0300 | 0x0002 = 清错误 |
| 0x0300 | 0x0003 = 立即标定 (用当前位置为零) |
| 0x0300 | 0x0004 = 触发自标定油 ε_r |
| 0x0301 | 0x4321 = 进入 OTA 模式 (停止测量) |

### 3.5 状态字 (0x0014, bit 定义)

| Bit | 含义 |
|---|---|
| 0 | 测量有效 |
| 1 | Kalman 收敛 |
| 2 | 油温在工作范围 |
| 3 | 已校准 |
| 4 | OTA 模式 |
| 5 | 同步主机模式 |
| 6 | 多峰存在 (多径警告) |
| 7 | 油 ε_r 自学习进行中 |
| 8–15 | 保留 |

### 3.6 错误字 (0x0015, bit 定义，1=有错)

| Bit | 错误 |
|---|---|
| 0 | RF MMIC 通讯失败 |
| 1 | PLL 锁失败 |
| 2 | ADC 饱和 |
| 3 | 无回波 (信号丢失) |
| 4 | 油温超量程 |
| 5 | EEPROM 损坏 |
| 6 | 标定数据丢失 |
| 7 | 内部温度过高 (>105 °C) |
| 8 | 电源欠压 (<8 V) |
| 9 | SYNC 输入错误 |
| 10–15 | 保留 |

## 4. Input Registers (FC 0x04, 只读诊断)

| 地址 | 类型 | 描述 |
|---|---|---|
| 0x0000 | 1 | Modbus 帧总数 (low word) |
| 0x0001 | 1 | Modbus CRC 错误数 |
| 0x0002 | 1 | 上电小时计 |
| 0x0003 | 1 | 测量总次数 (low) |
| 0x0004 | 1 | (high) |
| 0x0005 | 1 | 最近 16 次主峰幅度均值 |
| 0x0006 | 1 | 最近 16 次主峰幅度方差 |
| 0x0007..0x0016 | 16 | 最近 16 次 SNR 历史 |
| 0x0020..0x002F | 16 | 故障日志最新 16 条 (循环) |

## 5. Device Identification (FC 0x2B)

| ObjectId | 内容 |
|---|---|
| 0x00 | VendorName: "Your Company Name" |
| 0x01 | ProductCode: "IRM-24G-V1" |
| 0x02 | MajorMinorRevision: "1.0" |
| 0x03 | VendorUrl: "https://..." |
| 0x04 | ProductName: "IRM Hydraulic Position Sensor" |
| 0x05 | ModelName: "IRM24-50-2000" |
| 0x06 | UserApplicationName: 用户写入 0x0114 中的标签 |

## 6. 与 IEC 61131-3 ST 控制器对接

```c
// 在 src/FB_CrossCoupledILC.st 上层调用：
modbus_read_holding(slave=1, addr=0x0004, count=2, &raw);
act_pos[i] := MEMCPY_INT_TO_REAL(raw); // mm
modbus_read_holding(slave=1, addr=0x0014, count=1, &status);
IF NOT (status AND 16#01) THEN
   // 测量无效，进入故障逻辑
END_IF
```

## 7. 多缸协调读取

每个 IRM 占一个 Modbus 地址。控制器轮询 N 个传感器：
- 单次读 0x0000–0x000B (12 reg) 完成一缸 ≈ 1.7 ms @ 19200 bps
- 10 缸总轮询 ~ 17 ms（远低于 ILC 1 ms 周期，需要换更高速波特或并行总线）

> **建议**：N>4 缸场景下用 115200 bps 或换 IO-Link Master + 总线
> 上 16 个 sensor 并行。Modbus 不是 IRM 多缸场景的首选。

## 8. 异常响应

| 异常码 | 含义 | 触发 |
|---|---|---|
| 01 | Illegal Function | 不支持的 FC |
| 02 | Illegal Data Address | 地址不存在 |
| 03 | Illegal Data Value | 写入值越界 |
| 04 | Slave Device Failure | 内部错误 |
| 06 | Slave Busy | OTA 进行中 |
