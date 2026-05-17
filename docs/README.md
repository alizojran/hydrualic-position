# IRM 雷达式液压缸位置传感器 — 设计资料

集成雷达测量 (Integrated Radar Measurement, IRM) 位置传感器的端到端工程
设计资料。目标是产出 DVT 量产级的双频段 (24 GHz + 77 GHz) 传感器，给
本仓库 `src/` 下的多缸 ILC 控制器提供高精度行程反馈。

## 目录索引

| 模块 | 路径 | 主要内容 |
|---|---|---|
| 总体 | [00-overview/01-plan.md](00-overview/01-plan.md) | 工程总方案 (v2)、里程碑、风险 |
| 需求 | [00-overview/02-system-requirements.md](00-overview/02-system-requirements.md) | SRS、可追溯需求矩阵 |
| 链路预算 | [01-link-budget/24ghz-link-budget.md](01-link-budget/24ghz-link-budget.md) | 24 GHz 发射功率、衰减、SNR、分辨率 |
| 波导分析 | [01-link-budget/waveguide-analysis.md](01-link-budget/waveguide-analysis.md) | 圆波导模式、截止频率、多模问题 |
| 数值脚本 | [01-link-budget/link_budget.py](01-link-budget/link_budget.py) | 可运行的链路预算与波导计算 |
| RF 前端 | [02-rf-frontend/24ghz-schematic.md](02-rf-frontend/24ghz-schematic.md) | BGT24MTR12 前端原理图描述 |
| BOM | [02-rf-frontend/bom.md](02-rf-frontend/bom.md) | 关键元器件选型与替代清单 |
| 天线/探针 | [03-antenna-waveguide/probe-design.md](03-antenna-waveguide/probe-design.md) | 同轴探针 + 模式启动器设计 |
| 仿真计划 | [03-antenna-waveguide/hfss-cst-simulation-plan.md](03-antenna-waveguide/hfss-cst-simulation-plan.md) | HFSS/CST 项目结构、扫描矩阵 |
| 承压窗 | [04-pressure-window/pressure-window-design.md](04-pressure-window/pressure-window-design.md) | 介质窗机械+电气设计 |
| 接口板 | [05-interface-board/interface-schematic.md](05-interface-board/interface-schematic.md) | 模拟+IO-Link+RS-485 三合一 |
| Modbus | [05-interface-board/modbus-register-map.md](05-interface-board/modbus-register-map.md) | Modbus RTU 寄存器表 |
| IO-Link | [05-interface-board/iolink-iodd-draft.md](05-interface-board/iolink-iodd-draft.md) | IO-Link 参数与 IODD 草案 |
| 算法 | [06-algorithm/scherr-ayhan-algorithm.md](06-algorithm/scherr-ayhan-algorithm.md) | Scherr–Ayhan 组合 FFT+CZT+相位算法推导与扩展 |
| 算法仿真 | [06-algorithm/scherr_ayhan_sim.py](06-algorithm/scherr_ayhan_sim.py) | 可运行 Python 仿真 (Monte-Carlo + CRB) |

## 当前阶段

P1 — 链路预算 + 关键设计文档 (本目录全部内容)
下一步：开始 24 GHz 链路 PoC 板硬件设计 (KiCad)。

## 与控制器的关系

```
                            ┌──────── 本仓库 src/ ────────┐
液压缸 ─► IRM 传感器 ─CAN/RS-485/模拟─► FB_CrossCoupledILC ─► 阀控制
   ▲                                          │
   └──────────── 力 / 位置闭环 ────────────────┘
```

IRM 把"活塞绝对位置"以 1–2 kHz 上送给 ILC，ILC 根据多缸同步残差与
历史迭代修正阀指令。传感器分辨率 (≤0.2 mm) 与刷新率 (1 kHz) 是
确保 ILC 收敛速度的关键。
