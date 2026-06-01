# FMCW 雷达论文中文翻译流程 / Translation pipeline

将博士论文 *FMCW-Radarsignalverarbeitung zur Entfernungsmessung mit hoher
Genauigkeit*（Steffen Scherr）的正文（第 1–6 章）从德语翻译为中文，并生成
Word 文档。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `extract.py` | 从源 PDF 解析结构化内容：标题层级、正文段落（德语），并将公式、图、表裁剪为图片（`img/`）。生成 `content.json`。 |
| `content.json` | 提取出的有序元素流（标题 / 段落 / 公式 / 图 / 表）。 |
| `german.jsonl` | 待翻译元素（标题、段落、图表标题）的德语原文，逐行一个 JSON。 |
| `trans/*.json` | 人工翻译的中文文本，键为 `content.json` 中的元素下标。 |
| `build_docx.py` | 合并 `content.json` + `trans/*.json` + `img/`，生成最终 Word 文档。 |

## 重新生成

```bash
python3 extract.py        # 由 PDF 重新生成 img/ 和 content.json
python3 build_docx.py     # 生成 ../FMCW雷达信号处理_中文译本.docx
```

需要 `PyMuPDF` 与 `python-docx`：`pip install PyMuPDF python-docx`

## 处理方式

- **正文**：德语 → 中文（保留参考文献编号 `[..]`、公式/图/表编号、章节交叉引用）。
- **公式**：从 PDF 原样裁剪为图片嵌入（语言无关，忠实呈现）。
- **图 / 表**：从 PDF 裁剪为图片嵌入，标题译为中文。
- **参考文献**：按要求保持原样，未翻译。
