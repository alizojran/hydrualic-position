#!/usr/bin/env python3
"""
生成 KiCad 8 工程的占位 schematic 与 board 文件。

KiCad 的 .kicad_sch / .kicad_pcb 包含逐元素的 (x, y) 几何信息，
真正的元件放置和走线**必须在 KiCad GUI 中完成**。本脚本只生成可
以被 KiCad 正确打开的"空"工程骨架：
- 顶层 schematic (irm-sensor.kicad_sch) — 带两张分页指针
- RF 主板 schematic (rf-mainboard.kicad_sch) — 空白
- 接口板 schematic (interface-board.kicad_sch) — 空白
- PCB (irm-sensor.kicad_pcb) — 空白

用户后续在 KiCad 中打开 irm-sensor.kicad_pro，从 irm-symbols 库放
置元件，按 generate_netlist.py 输出的网络表实施连线。
"""
from __future__ import annotations

import os
import uuid as _uuid

HW = os.path.join(os.path.dirname(__file__), "..")


def new_uuid() -> str:
    return str(_uuid.uuid4())


def sch_header(title: str, rev: str = "0.1", company: str = "") -> str:
    return f'''(kicad_sch
  (version 20231120)
  (generator "irm_gen")
  (generator_version "8.0")
  (uuid "{new_uuid()}")
  (paper "A3")
  (title_block
    (title "{title}")
    (date "2026-05-17")
    (rev "{rev}")
    (company "{company}")
    (comment 1 "IRM 24 GHz FMCW Hydraulic Position Sensor")
    (comment 2 "See docs/02-rf-frontend/24ghz-schematic.md for design notes")
  )
  (lib_symbols)
  (sheet_instances
    (path "/" (page "1"))
  )
)
'''


def root_sch() -> str:
    """根 schematic, 含两个 hierarchical sheet 指针"""
    u_root = new_uuid()
    u_rf = new_uuid()
    u_if = new_uuid()
    return f'''(kicad_sch
  (version 20231120)
  (generator "irm_gen")
  (generator_version "8.0")
  (uuid "{u_root}")
  (paper "A3")
  (title_block
    (title "IRM Sensor - Top")
    (date "2026-05-17")
    (rev "0.1-EVT")
    (company "")
    (comment 1 "Hierarchical design: RF mainboard + interface board")
    (comment 2 "See docs/ for design analysis")
  )
  (lib_symbols)
  (sheet
    (at 50.8 50.8)
    (size 50.8 30.48)
    (fields_autoplaced yes)
    (stroke (width 0.1524) (type solid))
    (fill (color 0 0 0 0.0000))
    (uuid "{u_rf}")
    (property "Sheetname" "RF Mainboard"
      (at 50.8 50.08 0)
      (effects (font (size 1.27 1.27)) (justify left bottom)))
    (property "Sheetfile" "rf-mainboard.kicad_sch"
      (at 50.8 81.92 0)
      (effects (font (size 1.27 1.27)) (justify left top)))
    (instances
      (project "irm-sensor"
        (path "/{u_root}"
          (page "2"))))
  )
  (sheet
    (at 127 50.8)
    (size 50.8 30.48)
    (fields_autoplaced yes)
    (stroke (width 0.1524) (type solid))
    (fill (color 0 0 0 0.0000))
    (uuid "{u_if}")
    (property "Sheetname" "Interface Board"
      (at 127 50.08 0)
      (effects (font (size 1.27 1.27)) (justify left bottom)))
    (property "Sheetfile" "interface-board.kicad_sch"
      (at 127 81.92 0)
      (effects (font (size 1.27 1.27)) (justify left top)))
    (instances
      (project "irm-sensor"
        (path "/{u_root}"
          (page "3"))))
  )
  (sheet_instances
    (path "/" (page "1"))
  )
)
'''


def pcb_blank() -> str:
    return f'''(kicad_pcb
  (version 20240108)
  (generator "irm_gen")
  (generator_version "8.0")
  (general
    (thickness 1.6)
    (legacy_teardrops no)
  )
  (paper "A3")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1")
    (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
    (50 "User.1" user)
    (51 "User.2" user)
    (52 "User.3" user)
    (53 "User.4" user)
    (54 "User.5" user)
    (55 "User.6" user)
    (56 "User.7" user)
    (57 "User.8" user)
    (58 "User.9" user)
  )
  (setup
    (pad_to_mask_clearance 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros no)
      (usegerberextensions no)
      (usegerberattributes yes)
      (usegerberadvancedattributes yes)
      (creategerberjobfile yes)
      (dashed_line_dash_ratio 12.000000)
      (dashed_line_gap_ratio 3.000000)
      (svgprecision 4)
      (plotframeref no)
      (mode 1)
      (useauxorigin no)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (pdf_front_fp_property_popups yes)
      (pdf_back_fp_property_popups yes)
      (dxfpolygonmode yes)
      (dxfimperialunits yes)
      (dxfusepcbnewfont yes)
      (psnegative no)
      (psa4output no)
      (plotreference yes)
      (plotvalue yes)
      (plotfptext yes)
      (plotinvisibletext no)
      (sketchpadsonfab no)
      (subtractmaskfromsilk no)
      (outputformat 1)
      (mirror no)
      (drillshape 1)
      (scaleselection 1)
      (outputdirectory "build/")
    )
  )
  (net 0 "")
)
'''


def main() -> None:
    files = {
        "irm-sensor.kicad_sch": root_sch(),
        "rf-mainboard.kicad_sch": sch_header(
            "RF Mainboard - 24 GHz FMCW Radar Transceiver",
            rev="0.1-EVT",
        ),
        "interface-board.kicad_sch": sch_header(
            "Interface Board - Analog + IO-Link + RS-485",
            rev="0.1-EVT",
        ),
        "irm-sensor.kicad_pcb": pcb_blank(),
    }
    for name, content in files.items():
        path = os.path.join(HW, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
