---
name: course-workflow-orchestrator
description: Coordinate the full course_note_agents workflow from a local materials folder to reviewed Markdown and book-style PDF. Use when asked to run, resume, debug, or plan the whole multi-agent course-note pipeline, choose stage order, set run directories, or verify that outputs from ingestion, parsing, drafting, review, textbook writing, polishing, and layout connect correctly.
---

# Course Workflow Orchestrator

## 目标

把本地课程资料从 `materials/` 目录稳定推进到最终 `book.pdf`。总控只负责任务编排、阶段边界、参数选择和验收检查；不要把某个阶段的专业职责混到总控里。

## 默认约定

- 项目根目录为 `course_note_agents/`。
- 默认资料目录为 `materials/`，单门课建议放在 `materials/<course_name>/`。
- 每门课使用独立输出目录：`runs/<slug>/ingest`、`runs/<slug>/parsed` 等。
- API key 只通过环境变量传入，不写入任何文件。
- 中文课程默认使用 `--language zh-CN`。

## 全流程命令

```powershell
course-note-ingest `
  --materials-dir .\materials\<course> `
  --output-dir .\runs\<slug>\ingest `
  --course-id <slug> `
  --language zh-CN

course-note-parse `
  --manifest .\runs\<slug>\ingest\manifest.json `
  --output-dir .\runs\<slug>\parsed `
  --llm-mode auto `
  --max-chunk-chars 2600

course-note-draft `
  --parsed-index .\runs\<slug>\parsed\parsed_index.json `
  --output-dir .\runs\<slug>\draft `
  --llm-timeout-seconds 240 `
  --max-input-chars 26000

course-note-review `
  --draft-index .\runs\<slug>\draft\draft_index.json `
  --output-dir .\runs\<slug>\review `
  --llm-timeout-seconds 240 `
  --max-source-chars 26000 `
  --max-related-chars 14000

course-note-textbook `
  --review-index .\runs\<slug>\review\review_index.json `
  --output-dir .\runs\<slug>\textbook `
  --llm-timeout-seconds 300 `
  --max-outline-context-chars 70000 `
  --max-chapter-context-chars 80000 `
  --max-self-check-chars 120000 `
  --self-check-iterations 2 `
  --max-self-check-iterations 2

course-note-polish `
  --textbook-index .\runs\<slug>\textbook\textbook_index.json `
  --output-dir .\runs\<slug>\polished `
  --llm-timeout-seconds 300

course-note-layout `
  --input-index .\runs\<slug>\polished\polished_index.json `
  --output-dir .\runs\<slug>\book_pdf `
  --compile-timeout-seconds 300
```

## 编排规则

1. 先做小样本冒烟测试，再跑全量：使用 `--limit-documents`、`--limit-pages`、`--limit-chapters`。
2. 每个阶段只读取上一阶段的 index 文件，不直接猜测中间文件路径。
3. 如果只处理课件，解析阶段使用 `--include-roles lecture_slides`；如果包含往年题和答案，不要过滤掉 `past_exam` 或 `solution`。
4. 如果 `manifest.json` 中没有 `past_exam`，后续教材不得虚构“历年题”“真题”“模拟卷”章节。
5. 文科或记忆型课程优先完整覆盖概念、人物、事件、流派、论述框架；理工或题目型课程再提高推导和例题权重。
6. 任一阶段失败时，从最近成功的 index 继续，不重跑已经确认无误的前置阶段。

## 验收清单

- `manifest.json` 的 `counts.by_role` 与资料目录肉眼预期一致。
- `parsed_index.json` 中 `requires_ocr` 或 `needs_ocr_documents` 已被记录。
- `draft_index.json`、`review_index.json`、`textbook_index.json`、`polished_index.json` 均存在。
- `polishing_reports/*.json` 中没有严重结构性错误未处理。
- `layout_index.json` 的 `compile_status` 为 `success`，且 `book.pdf` 可打开。
- 运行 `course-note-run --config .\course_config.toml --dry-run`，确认配置能正确展开为各阶段命令。
