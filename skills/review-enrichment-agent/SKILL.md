---
name: review-enrichment-agent
description: Review, correct, and enrich first-draft course notes. Use when checking draft notes against parsed sources, filling missing explanations, expanding terse content, separating questions from answers in mixed exam files, producing reviewed notes, and preserving unresolved issues instead of inventing facts.
---

# Review Enrichment Agent

## 目标

把单份资料初稿修成更可靠、更完整、更易懂的审查版笔记。本阶段可补充解释，但必须以原资料和相邻资料为依据。

## 输入与输出

- 输入：`runs/<slug>/draft/draft_index.json`。
- 输出：`runs/<slug>/review/review_index.json`、`reviewed_notes/*.json`、`reviewed_notes/*.md`、`combined_reviewed.md`。
- Schema：`review_index.schema.json`、`reviewed_document.schema.json`。

## 推荐命令

```powershell
course-note-review `
  --draft-index .\runs\<slug>\draft\draft_index.json `
  --output-dir .\runs\<slug>\review `
  --llm-timeout-seconds 240 `
  --max-source-chars 26000 `
  --max-related-chars 14000
```

## 审查重点

- 修复知识错误、概念混淆、逻辑跳跃和解释过短。
- 将“只有结论”的内容补成“概念-原因-例子/应用-易错点”。
- 对题目给出完整解答过程：考点定位、解题思路、步骤、答案、常见错误、知识回顾。
- 对答案和题目混在一起的文件，按题号、答案标记、解析段落拆出结构，但不拆物理文件。
- 文科课程补足背诵提纲、概念辨析、时间线、人物/理论关系、论述题框架。

## 冲突处理

- PPT、作业答案、往年题解析互相冲突时，优先保留更直接、更正式的来源。
- 不能裁决时写入 `remaining_open_issues`，并在正文中以“资料存在不同表述”提示。
- 不用常识覆盖课程资料；课程内部定义优先。

## 验收清单

- `total_findings` 和 `total_supplements` 反映真实审查工作。
- `remaining_open_issues` 只保留无法自动确认的问题。
- 题目不再只有思路，至少包含可执行的解题步骤和最终答案或资料缺失说明。
- 增补内容有结构化来源依据，不出现无来源的新章节；正文不逐行添加 `[来源: ...]`。
