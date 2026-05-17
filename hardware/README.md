# IRM 雷达式位置传感器 — KiCad 工程

这是 `docs/` 下设计文档对应的 KiCad 8 工程骨架，包含：
- 自定义符号库 (BGT24MTR12, L6360, 等 12 个)
- 自定义封装库 (承压窗组件、SMA edge-launch、rat-race 耦合器)
- 项目文件、网表类规则、库表
- Python 网表生成器 (输出 KiCad netlist + 人可读 wire-list + BOM CSV)

## 1. 工程目录

```
hardware/
├── irm-sensor.kicad_pro           # KiCad 项目文件
├── irm-sensor.kicad_sch           # 根 schematic (含两张分页)
├── rf-mainboard.kicad_sch         # RF 主板原理图 (空白, 待填)
├── interface-board.kicad_sch      # 接口板原理图 (空白, 待填)
├── irm-sensor.kicad_pcb           # PCB (空白, 待布局)
├── sym-lib-table                  # 符号库表
├── fp-lib-table                   # 封装库表
├── libraries/
│   ├── irm-symbols.kicad_sym      # 12 个自定义符号
│   └── irm-footprints.pretty/     # 3 个自定义封装
│       ├── PRESSURE_WINDOW_Probe.kicad_mod
│       ├── SMA_EdgeLaunch_PE91175.kicad_mod
│       └── RatRace_Coupler_24GHz.kicad_mod
├── scripts/
│   ├── generate_symbols.py        # 生成符号库
│   ├── generate_project_files.py  # 生成 .kicad_sch / .kicad_pcb 占位
│   └── generate_netlist.py        # 生成 netlist + wire-list + BOM
└── build/                         # 脚本输出 (gitignored)
    ├── rf-mainboard.net
    ├── rf-mainboard-wires.md      # ⭐ 关键参考：每根 net + 每个元件
    ├── bom-rf-mainboard.csv
    ├── interface-board.net
    ├── interface-board-wires.md
    └── bom-interface-board.csv
```

## 2. 设计哲学：脚本作蓝本，KiCad 作画板

远程文本环境无法直接操作 KiCad GUI，所以工作流是：

```
docs/02-rf-frontend/*.md          (设计意图: 框图 + 选型)
        │
        ▼
hardware/scripts/generate_*.py    (定型: 符号 + 封装 + 网络表)
        │
        ▼
hardware/build/*.md / *.net       (机器可读 + 人可读蓝本)
        │
        ▼
KiCad GUI (本地)                  (实际绘图: 放置 + 走线 + 布局)
        │
        ▼
irm-sensor.kicad_pcb              (最终交付)
```

脚本是**单一真相源**：要修改电路，改 `generate_netlist.py` 中的元件
与连接定义，重新跑脚本，重新对照 KiCad 中的原理图。

## 3. 在 KiCad 中打开

需要 **KiCad 8.0+**。在 Linux/macOS/Windows 上：

```bash
# 1. 先跑脚本生成所有文件
python3 hardware/scripts/generate_symbols.py
python3 hardware/scripts/generate_project_files.py
python3 hardware/scripts/generate_netlist.py

# 2. 用 KiCad 打开
kicad hardware/irm-sensor.kicad_pro
```

打开后看到的是：
- 顶层 schematic 有两个分页 (RF Mainboard / Interface Board)
- 两个分页都是空白
- `irm-symbols` 库已加载（项目设置中），可以从 schematic 编辑器
  `Place → Add Symbol → irm-symbols` 调用

## 4. 实际绘图工作流

### 4.1 原理图填充

打开 `rf-mainboard.kicad_sch`，参照 `build/rf-mainboard-wires.md` 逐项：

1. 放置元件 — 从库栏拖入 (irm-symbols + KiCad 内置 Device / Connector)
2. 改参考位号 — 按 wire-list 中的 Ref 命名 (U1, C100, ...)
3. 走线 — 对照 wire-list 的"网络连接"逐 net 连
4. 加电源符号 (Place → Power Port)
5. 加分页 I/O Port (用于跨分页连接)
6. Schematic ERC → 应该零错误

接口板同上。

### 4.2 直接从网表生 PCB (跳过原理图)

> 适用于：先验证 PCB 布局可行性、不想画原理图、或想原型快速迭代

```
KiCad → File → New Project from Existing  (或直接打开 .kicad_pro)
PCB Editor → File → Import → Netlist  →  hardware/build/rf-mainboard.net
```

KiCad 会自动放置所有元件 (overlap)，你拉开布局即可。这是工程师常
用的"跳过 schematic"快速验证流程。

### 4.3 PCB 布局原则

参见 `docs/02-rf-frontend/24ghz-schematic.md` §8 "PCB 关键约束"：
- RF 区用 RO4350B (顶层混压)
- 50 Ω 微带 0.46 mm 宽
- BGT24MTR12 与 rat-race 紧靠
- 探针/承压窗的 PCB 焊盘紧贴板边
- BMI-S-220 屏蔽罩覆盖 RF 区

工程文件已经在 net class 里预设：
- `RF_50ohm` — 0.46 mm 宽，红色
- `LVDS` — 差分对 0.13/0.15
- `Power_HighCurrent` — 0.6 mm 宽

## 5. 自定义符号 / 封装清单

### 5.1 符号 (`irm-symbols.kicad_sym`, 12 个)

| Symbol | 引脚 | 用途 |
|---|---|---|
| BGT24MTR12 | 33 | 24 GHz FMCW 收发 (Infineon) |
| ADS5263 | 32 | 16-bit 4-ch ADC (TI) |
| L6360 | 25 | IO-Link Class B (ST) |
| ISO1500 | 16 | 隔离 RS-485 (ADI) |
| ADuM141D | 16 | 数字隔离器 (ADI) |
| DAC8830 | 8 | 16-bit DAC (TI) |
| TPS54360 | 9 | 60V Buck (TI) |
| ADM7172 | 9 | 超低噪 LDO (ADI) |
| SiT5356_TCXO | 4 | 50 MHz TCXO (SiTime) |
| PRESSURE_WINDOW | 4 | 蓝宝石承压窗 + 探针 (机械) |
| COAX_LAUNCHER | 2 | SMA edge-launch |
| RATRACE_COUPLER | 4 | 24 GHz 180° rat-race |

### 5.2 封装 (`irm-footprints.pretty/`, 3 个)

| Footprint | 说明 |
|---|---|
| PRESSURE_WINDOW_Probe | 中央 RF 焊盘 + 双侧 GND + 机械孔 |
| SMA_EdgeLaunch_PE91175 | Pasternack PE91175 板边 SMA |
| RatRace_Coupler_24GHz | 24.125 GHz rat-race 微带环 (仿真后微调) |

> ⚠️ 三个自制封装是**初稿**：rat-race 几何尤其需要在 HFSS/CST
> 仿真后回填 (参见 `docs/03-antenna-waveguide/`)。

## 6. 修改电路 = 改脚本，不要改 KiCad

工程惯例上 KiCad GUI 修改的 .kicad_sch 是真相源。但本工程为远程
开发协作设计，**反过来**：
- 真相源 = `hardware/scripts/generate_netlist.py`
- KiCad 是渲染器 + PCB 布局工具

加一颗电容、改一根连线：先改脚本、跑脚本、再把 wire-list 的 diff
人工同步到 KiCad schematic 中。这样所有人 review 时只看 PR 的脚本
diff，不用 diff KiCad 的二进制 (其实是 S-expression，但仍混乱)。

## 7. 当前进度 (检查清单)

- [x] KiCad 项目骨架 + 库表
- [x] 自定义符号 12 个
- [x] 自定义封装 3 个 (初稿)
- [x] 网表 + Wire-list + BOM 生成
- [ ] 在 KiCad GUI 中放置元件与连线 (人工)
- [ ] HFSS/CST 仿真完成后回填 rat-race 几何
- [ ] PCB 布局 (RF 区 + 数字区 + 接口板)
- [ ] 阻抗仿真 + DRC
- [ ] 出图制造文件 (Gerber + 钻孔 + Pick&Place)

## 8. 常见问题

**Q: 我没有 KiCad 8，能用 KiCad 7 打开吗？**
A: 不能直接，KiCad 7 不支持 8 的文件 version 20231120。需把 KiCad 8
   导出为 7 兼容格式。建议直接升级到 8 (开源免费)。

**Q: 自制封装的 `Roundedrect_rratio` / `roundrect_rratio` 报错？**
A: KiCad 文件格式在 8.x 多个小版本间有微调。如果打开报错，最快
   办法是在 KiCad Footprint Editor 里手动重存一次。

**Q: 我想直接拿 PCB 出去打样, schematic 不画了？**
A: 见 §4.2，可以跳过 schematic 直接导网表到 PCB 编辑器。**前提是
   你信得过 generate_netlist.py 中的连线**。建议至少画一次 schematic
   过 ERC，发现脚本错误。

**Q: STM32H743 的引脚我没全填完？**
A: 对。脚本只填了 ~30 个关键功能引脚 (SPI/I2C/UART/SAI/QSPI/电源)。
   实际 LQFP-144 有 144 引脚，剩下大多是 GPIO 或 NC。在 KiCad 中
   用内置 `MCU_ST_STM32H7:STM32H743ZITx` 符号会自动展开全部引脚。

## 9. 下一步

按 `docs/00-overview/01-plan.md` 的里程碑，本工程目前在 **P1 末 → P2 初**：
- P1 (链路预算 + 仿真) ✓
- P2 (RF Demo 板) — 当前，需要：
  - [ ] 在 KiCad 完成 schematic 实际放置
  - [ ] HFSS rat-race + 探针仿真，回填几何
  - [ ] PCB 第一次布局 + DRC pass
  - [ ] 出 Gerber，开样
