---
name: content-parsing-agent
description: Parse files from manifest.json into clean structured text for downstream course-note agents. Use when extracting text from PDFs, PPTX, DOCX, HTML, Markdown, plain text, CSV, or image placeholders; cleaning noisy slide text with an LLM; detecting scanned/image-only materials; or producing parsed_index.json and parsed_documents/*.json.
---

# Content Parsing Agent

## 目标

把 `manifest.json` 中的资料整理为“后续 Agent 能读懂的干净文本”。本阶段追求忠实抽取和降噪，不做知识扩写。

## 输入与输出

- 输入：`runs/<slug>/ingest/manifest.json`。
- 输出：`runs/<slug>/parsed/parsed_index.json` 和 `parsed_documents/*.json`。
- Schema：`parsed_index.schema.json`、`parsed_document.schema.json`。
- 下游依赖字段：`linear_text`、`pages`、`chunks`、`document_role`、`secondary_roles`、`warnings`、`parse_status`。

## 推荐命令

```powershell
course-note-parse `
  --manifest .\runs\<slug>\ingest\manifest.json `
  --output-dir .\runs\<slug>\parsed `
  --llm-mode auto `
  --max-chunk-chars 2600
```

课件图形标签噪声很重时，强制开启 LLM 清洗：

```powershell
course-note-parse `
  --manifest .\runs\<slug>\ingest\manifest.json `
  --output-dir .\runs\<slug>\parsed_llm `
  --llm-mode require
```

## 解析策略

- PDF：优先用 PyMuPDF 抽取每页正文；无可抽取文本时标记 `requires_ocr`。
- PPTX：从幻灯片 XML 抽取文本；重点删除装饰文字、坐标轴标签、零散图形标注。
- DOCX：读取正文、脚注、尾注、批注 XML。
- HTML/Markdown/TXT/CSV：做基础文本清洗。
- 图片：当前输出占位块并标记 OCR pending，不虚构图片文字。

## LLM 清洗规则

- 只保留具有教学意义的文字：标题、定义、定理、概念、人物事件、公式说明、题干、答案解析、重要说明。
- 删除图表碎片、页眉页脚、页码、版权、水印、无意义符号。
- 不补充原文没有的信息，不解释，不扩写。
- 对中文资料保持中文表达，保留必要英文术语和公式。
- 页文本太短、图片页、扫描页不要强行清洗成正文。

## 验收清单

- `parsed_index.json` 中 `by_parse_status` 没有异常大量 `empty`。
- PPT 的 `linear_text` 应是可成句正文，而不是单字符、坐标标签或图形残片堆积。
- 图片和扫描 PDF 被明确标记 `needs_ocr`，而不是静默丢失。
- 往年题和答案同文件时，题干、答案、解析标记在同一文本中保留下来，供后续 Agent 再区分。
