# 24 GHz RF 前端原理图描述

围绕 Infineon **BGT24MTR12** 的单板原理图。本文档描述每个功能块、
信号流向、关键节点参数、PCB 注意点。配套 BOM 见 [bom.md](bom.md)。

## 1. MMIC 概览：BGT24MTR12

- 工作频率 24.0 – 24.25 GHz (ISM)
- 内置：fractional-N PLL、VCO、PA、LNA、I/Q Mixer、IF 缓冲
- Tx 功率 +6 ~ +11 dBm 可编程
- Rx NF 约 12 dB
- 控制接口 SPI (chirp 参数、增益、模式)
- 封装 VQFN-32 (5×5 mm)
- 单 3.3 V 供电（内部分压到 1.8 V 模拟核）

> Pin-to-pin 备选：**Silicon Radar TRX_024_xxx** (略低集成度，需外
> 加 PLL 参考)，PCB 占位预留。

## 2. 顶层框图

```
                          ┌─────────────────────────────────┐
                          │           BGT24MTR12            │
   50 MHz TCXO ──REF──────►│ REF_IN                           │
   (Si Linear SiT5356)    │                                 │
                          │   PLL ── VCO ── PA ── TX_OUT────►├──► 探针 (TX/RX 共用)
   STM32 SPI ─────CS,SCK,│ ──┐                              │           │
              SDI,SDO──►│ │  │   LO ──► Mixer_I ◄─ LNA ◄─RX │◄──────────┘
                          │  │                              │
                          │  │   ──► Mixer_Q ◄─────────────┐│
                          │ INT (锁定/告警)                ││
                          └───┬───────┬────────┬───────────┘│
                              │ IF_I  │ IF_Q  │  ANA_REF  │
                              ▼       ▼       ▼            │
                          IF_AMP_I  IF_AMP_Q                │
                             │       │                      │
                             ▼       ▼                      │
                        ADS5263 (ADC, dual 14-bit) ──► STM32 (SPI/SAI)
```

注意 BGT24MTR12 内部已有 TX/RX 共用一组天线端口设计，但需要外部
**SPDT 开关**或**单端循环器** (24 GHz 循环器昂贵、不实用)，**本设
计采用** Tx 与 Rx 端口各接一支同轴探针（双探针方案）或**外接 SPDT
+ 单探针**。下面给出双方案对比。

### 2.1 单探针 + SPDT 开关方案（推荐 V1）

```
                         ┌─ SPDT_TX ◄── BGT24MTR12 TX
   探针 ─── 共用 ────────┤
                         └─ SPDT_RX ──► BGT24MTR12 RX
```

- 开关：HMC547ALC3 (DC–28 GHz, 28 dB iso, IL 1.8 dB)
- 在每个 chirp 期间快速切换：TX-ON 发射、瞬时 TX-OFF / RX-ON 接收
- BGT24MTR12 是 FMCW 连续波，**TX 与 RX 同时工作**，所以 SPDT 不
  适合。**改用定向耦合器**才是正解，见 2.3。

### 2.2 双探针方案

```
   探针 A (TX) ◄── BGT24MTR12 TX
   探针 B (RX) ──► BGT24MTR12 RX
   两个探针在端盖上相邻 ~ λ_oil
```

优点：电气简单。缺点：机械上多一个承压窗、TX→RX 直耦严重，距离短
时被本振近场污染。**不推荐**。

### 2.3 定向耦合器单探针方案（**推荐 V1**）

```
                                       ┌─── 探针 (TX/RX 共用)
                                       │
                            ┌──────────┴──────────┐
                            │  90° 混合耦合器     │
                            │  (rat-race / branch)│
   BGT24MTR12 TX_OUT ──IN───┤                     ├── ISO ── 50 Ω 终端
   BGT24MTR12 RX_IN ◄──CPL──┤                     │
                            └─────────────────────┘
```

- 在 PCB 上用**微带 rat-race** 或 **brand-line 90°耦合器**实现
- 隔离 IN ↔ CPL ≥ 25 dB，把 TX 漏到 RX 抑制到 −25 dB 量级
- 板上加 5 dB 衰减焊盘补充隔离

> **最终选型**：定向耦合器单探针 + 微带 rat-race 在 Rogers RO4350B
> 上实现。占地约 8×8 mm，0.3 dB IL。

## 3. PLL / Chirp 生成

BGT24MTR12 内置 fractional-N PLL，可直接通过 SPI 配置 chirp：

| 参数 | 寄存器 | 值 |
|---|---|---|
| f_start | CHIRP_F0 | 24.000 GHz |
| f_stop | CHIRP_F1 | 24.250 GHz |
| T_ramp | CHIRP_T | 250 µs |
| T_reset | CHIRP_RST | 50 µs |
| Chirps/frame | N_CHIRP | 3 (用于多脉冲平均) |
| 参考频率 | REF_DIV | 50 MHz / 1 |

**参考时钟选型**：
- SiTime SiT5356 TCXO，50.000 MHz，±0.5 ppm，相位噪声 −130 dBc/Hz @ 10kHz
- 24 GHz PLL 输出相位噪声目标 −85 dBc/Hz @ 100 kHz offset
- 等价测距相位噪声贡献 σ_d_PN ≈ 50 µm @ 1 m

## 4. IF 通道

```
   BGT24MTR12 IF_I/Q ──► 共模缓冲 ──► 抗混叠 LPF ──► PGA ──► ADC
   (Diff, 1 V_pp)          OPA1612      8 阶 BSL fc=30 kHz   ADS5263
```

详细：

| 节点 | 信号特征 |
|---|---|
| IF_I/Q 差分对 | ±0.5 V，1 V_pp，DC – 25 kHz 频率 |
| LPF 拓扑 | Sallen-Key 双二阶级联，Bessel 30 kHz |
| PGA | TI LMP8358，可编程 1×/10×/100× |
| ADC | TI ADS5263，4 通道 14-bit 100 MSps |
| ADC 时钟 | 由 STM32H7 SAI 提供同步采样 |

ADC 输出经 SAI 直接 DMA 到 STM32H7 内部 SRAM，由 DMA 触发 FFT。

## 5. 电源树

```
   Vin (9–32 V)
      │ TVS SMBJ33CA
      │ PMOS 反接保护 (PMV45EP)
      │
      ├── Buck #1  TPS54360  ──► 5.0 V / 1 A   (LDO 输入)
      │      └── LDO LP5907    3.3 V_D    (MCU + 外围)
      │
      ├── Buck #2  TPS54160  ──► 3.6 V / 0.5 A
      │      └── LDO ADM7172  3.3 V_RF (低噪声, 10 µVrms)
      │      └── LDO ADM7172  1.8 V_RF (BGT24 内核)
      │
      ├── Buck #3  TPS54160  ──► 2.5 V / 0.3 A  (ADC AVDD)
      │
      └── 隔离侧 (接口板)  通过基带板栈板连接 → 见 05-interface-board
```

要点：
- RF 电源 3.3 V_RF 必须用 LDO，**禁止开关电源直供 BGT24**（相位噪
  声会被开关纹波调制）
- 每个 LDO 输出加 1 µF + 10 nF + 100 pF 三档去耦
- BGT24 每根电源 pin 独立去耦，PCB 上紧贴芯片
- 整机 24 V 输入时静态电流 < 70 mA，功耗 < 1.7 W

## 6. 时钟与同步

| 时钟 | 用途 | 频率 |
|---|---|---|
| TCXO #1 | BGT24 PLL 参考 | 50.000 MHz |
| TCXO #2 | STM32 + ADC | 25.000 MHz (内部 PLL 倍频到 480 MHz) |
| SYNC_IN | 多缸同步触发输入 | 1 kHz 脉冲 |
| SYNC_OUT | 同步触发输出 (链式) | 1 kHz |

多缸场景：第一台传感器作为 master，输出 SYNC_OUT 给其他 slave。
所有 IRM 共享同一时刻的 chirp 起点，时间戳同步 ≤ 1 µs。

## 7. 关键测试点 (出厂 FCT)

| 测试点 | 信号 | 期望值 |
|---|---|---|
| TP_TX | TX 探针输入端 (耦合监测) | +7 dBm ± 1 dB |
| TP_LO | LO 监测耦合 | −15 dBm |
| TP_IFI | IF_I 差分中点 | 1.65 V (DC bias) |
| TP_IFQ | IF_Q 差分中点 | 1.65 V |
| TP_REF | 50 MHz 参考 | +6 dBm sine, jitter < 2 ps |
| TP_ADC_CLK | ADC 采样时钟 | 50 MSps, 3.3 V LVCMOS |
| TP_SYNC | 同步脉冲 | 1 kHz, 50 % duty |

## 8. PCB 关键约束

- **基材**：Rogers RO4350B (ε_r=3.48, tanδ=0.0037) 顶层 RF；FR4
  Tg170 内层数字/电源
- **层叠**：6 层 (RF/GND/Sig/PWR/Sig/RF_bot)
- **过孔**：背钻 + 围地过孔栏 (via fence) 围绕 BGT24
- **微带**：50 Ω 单端宽度 0.46 mm (Rogers 0.254 mm 介质)
- **耦合器**：rat-race 周长 = 1.5 · λ_g 在 24 GHz
- **GND 隔离**：模拟地 / 数字地 / 隔离地分区，单点星接到电源入口
- **EMC 屏蔽**：RF 子板覆盖金属屏蔽罩 (BMI-S-220)
- **板间互联**：BGA 焊球或板对板连接器 (Samtec ERM/ERF) 接到基带板

## 9. ESD / 浪涌保护

| 端口 | 保护器件 |
|---|---|
| Vin | SMBJ33CA TVS + PMOS 反接 |
| 同步 I/O | PESD3V3 双向 TVS |
| ADC 输入 | 差分 TVS 阵列 PESD2CAN |
| 探针 SMA（如外接） | ESD 隔离电容 + 限幅器 |

## 10. EVT 板布局示意

```
     ┌────────────────────────────────────────────┐
     │  RF 区 (屏蔽罩内)                          │
     │  ┌─────┐    ┌──── 耦合器 ────┐             │
     │  │TCXO │    │                │  探针       │
     │  └─────┘    │   BGT24MTR12   │   ●         │
     │             │                │             │
     │             └────────────────┘             │
     ├────────────────────────────────────────────┤
     │  IF / ADC 区                               │
     │  [OPA] [LPF] [PGA] [ADS5263]               │
     ├────────────────────────────────────────────┤
     │  数字区                                    │
     │  [STM32H743] [EEPROM] [板对板连接器→接口板] │
     ├────────────────────────────────────────────┤
     │  电源区                                    │
     │  [Buck1] [Buck2] [Buck3] [LDOs] [TVS]      │
     └────────────────────────────────────────────┘
                            │
                  外壳 M12 / DT04-5P 连接器
```

整板 PCB 估算 50 × 30 mm，可塞入 Φ32 mm 外壳。
