---
name: material-ingestion-agent
description: Inventory and classify local course materials for course_note_agents. Use when scanning materials/, separating textbooks, lecture slides, assignments, past exams, solutions, images, notes, and miscellaneous files, checking duplicate files, or producing phase-1 manifest.json for later agents.
---

# Material Ingestion Agent

## 目标

把用户放入 `materials/` 的本地资料转成可信的 `manifest.json`。本阶段只做文件级识别、元数据记录、去重和处理提示，不解析正文。

## 输入与输出

- 输入：本地目录，默认 `materials/`，也可指定 `materials/<course_name>/`。
- 输出：`runs/<slug>/ingest/manifest.json`。
- Schema：`manifest.schema.json`。
- 关键字段：`document_role`、`secondary_roles`、`confidence`、`reason`、`processing_hints`、`needs_ocr`、`sha256`。

## 推荐命令

```powershell
course-note-ingest `
  --materials-dir .\materials\<course> `
  --output-dir .\runs\<slug>\ingest `
  --course-id <slug> `
  --language zh-CN
```

## 分类规则

- `lecture_slides`：PPT/PDF 课件、按“第几讲/lecture/课件”命名的材料。
- `textbook`：教材、讲义、book、chapter、参考书。
- `assignment`：作业、习题、problem set、实验任务。
- `past_exam`：往年题、真题、期中、期末、试卷、考试题。
- `solution`：答案、解析、参考解答。
- `notes`：学生笔记、复习提纲、课堂记录。
- `reference_paper`：论文、阅读材料、参考文献。
- `miscellaneous`：无法高置信分类的资料。

## 重要边界

- 往年题和答案经常在同一个文件内，这是正常情况。文件可保留为 `past_exam`，并在 `secondary_roles` 或 `processing_hints` 中体现答案/解析信号；不要强行拆文件。
- 图片文件应被纳入 manifest，并标记后续需要 OCR 或视觉解析。
- Office 临时锁文件、隐藏文件、重复文件应被跳过或明确记录，不进入主流程干扰结果。
- 课程介绍中的“考试方式”“选择题”等词不应单独导致课件被误判为往年题；文件名和上下文信号优先。

## 验收清单

- `counts.total_files` 不包含隐藏临时文件。
- `counts.duplicate_files_by_sha256` 合理，重复资料不会重复进入后续阶段。
- `by_role` 中课件、教材、作业、往年题数量与目录肉眼预期接近。
- 每个低置信分类都有 `reason` 或 `warnings` 方便后续回溯。
