---
name: layout-pdf-agent
description: Convert polished course-note Markdown into LaTeX and book-style PDF. Use when rendering polished_index.json, checking CJK fonts, compiling with XeLaTeX, diagnosing LaTeX errors, or producing book.tex, book.pdf, compile.log, and layout_index.json.
---

# Layout PDF Agent

## 目标

把精修后的 Markdown 转成可阅读、可打印的书籍风格 PDF。本阶段负责语义到 LaTeX 的转换、中文字体、目录、表格、公式和编译日志。

## 输入与输出

- 输入：`runs/<slug>/polished/polished_index.json`。
- 输出：`runs/<slug>/book_pdf/layout_index.json`、`book.tex`、`book.pdf`、`compile.log`。
- Schema：`layout_index.schema.json`。

## 推荐命令

```powershell
course-note-layout `
  --input-index .\runs\<slug>\polished\polished_index.json `
  --output-dir .\runs\<slug>\book_pdf `
  --compile-timeout-seconds 300
```

只生成 LaTeX 不编译：

```powershell
course-note-layout `
  --input-index .\runs\<slug>\polished\polished_index.json `
  --output-dir .\runs\<slug>\book_tex `
  --no-compile
```

## 排版规则

- 中文默认使用 XeLaTeX 和 CJK 字体；字体缺失时先记录错误，不静默产出坏 PDF。
- Markdown 标题映射为章节层级，表格和公式尽量保持语义。
- 不在排版阶段增删知识内容。
- 编译失败时保留 `book.tex` 和 `compile.log`，方便诊断。

## 常见处理

- 缺少 `xelatex`：使用 `--no-compile` 先产出 TeX，或安装 TeX Live/MiKTeX。
- 字体缺失：通过 `--cjk-main-font` 和 `--cjk-sans-font` 指定可用中文字体。
- LaTeX 特殊字符错误：回查 `book.tex` 对应章节，优先修 Markdown 转义规则。

## 验收清单

- `layout_index.json` 的 `compile_status` 为 `success`。
- `book.pdf` 存在且页数大于 0。
- `compile.log` 无致命错误。
- PDF 中中文、公式、目录和表格可读。
