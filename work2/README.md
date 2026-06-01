# 两篇雷达论文中文翻译流程 / Translation pipeline

将两篇 IEEE 论文的正文从英文翻译为中文，并生成 Word 文档（保存在仓库根目录）：

| 源 PDF | 输出 Word |
| --- | --- |
| `High-Accuracy_Range_Detection_Radar_Sensor_for_Hydraulic_Cylinders.pdf`（IEEE Sensors Journal, 2014） | `../High-Accuracy_Range_Detection_Radar_Sensor_中文译本.docx` |
| `C2012_Ayhan_FMCWradarinoil-filledwaveguidesforrangedetectioninhydrauliccylinders.pdf`（EuRAD, 2012） | `../C2012_Ayhan_FMCW_oil-filled_waveguides_中文译本.docx` |

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `extract2.py` | 从源 PDF 解析双栏结构化内容：题名 / 作者 / 摘要 / 关键词、各级标题、正文段落（英文），并将显示公式、图、表自原文裁切为图片（`img_journal/`、`img_conf/`）。生成 `content_<doc>.json`。 |
| `content_journal.json` / `content_conf.json` | 提取出的有序元素流（题名 / 摘要 / 标题 / 段落 / 公式 / 图 / 表 / 参考文献）。 |
| `translations.py` | 人工中文译文（按 `content_*.json` 元素下标索引），生成 `trans_<doc>.json`。译文为 `""` 表示删除该元素（用于丢弃个别因双栏排版漏入正文的图注片段）。 |
| `trans_journal.json` / `trans_conf.json` | 下标 → 中文 的译文映射。 |
| `build_docx2.py` | 合并 `content_*.json` + `trans_*.json` + 图片，生成最终 Word 文档。 |

## 重新生成

```bash
pip install PyMuPDF python-docx
python3 work2/extract2.py      # 由 PDF 重新生成 img_*/ 和 content_*.json
python3 work2/translations.py  # 生成 trans_*.json
python3 work2/build_docx2.py   # 生成 ../*_中文译本.docx
```

## 处理方式

- **正文 / 摘要 / 标题 / 关键词**：英文 → 中文（保留参考文献编号 `[..]`、公式/图/表编号、章节交叉引用）。
- **显示公式**：从原文裁切为图片嵌入（语言无关，忠实呈现）。
- **图 / 表**：从原文裁切为图片嵌入，图注 / 表题译为中文。
- **参考文献**：按惯例保持原文，未翻译。
- **作者 / 单位、首页稿件信息脚注**：保持原文。
