---
name: chapter-polishing-agent
description: Polish generated textbook chapters while preserving structure, citations, and source grounding. Use when refining chapter-level Markdown, applying self-check reports, improving readability, standardizing terminology, enriching memory-oriented sections, and producing polished_index.json before PDF layout.
---

# Chapter Polishing Agent

## 目标

对教材章节做精修，使语言、结构、术语和学习友好度达到最终 Markdown 标准。本阶段只做局部修复和表达优化，不重写全书架构。

## 输入与输出

- 输入：`runs/<slug>/textbook/textbook_index.json`。
- 输出：`runs/<slug>/polished/polished_index.json`、`polished_textbook.md`、`polished_chapters/*.md`、`polishing_reports/*.json`。
- Schema：`polished_index.schema.json`。

## 推荐命令

```powershell
course-note-polish `
  --textbook-index .\runs\<slug>\textbook\textbook_index.json `
  --output-dir .\runs\<slug>\polished `
  --llm-timeout-seconds 300 `
  --max-chapter-chars 36000 `
  --max-self-check-chars 24000 `
  --max-global-context-chars 18000
```

## 精修规则

- 按章节处理，保留标题层级、结构化引用、术语和题目来源；正文不逐行添加 `[来源: ...]`。
- 优先修复自检报告中的严重问题：漏讲、逻辑跳跃、题目无答案、章节重复、术语不一致。
- 语言要更通顺，但不能把课程资料没有的内容写成事实。
- 文科课程强化背诵要点、概念辨析、理论对比、论述题答题框架。
- 理工课程强化公式条件、推导步骤、算法边界、例题完整答案。

## 题目规则

- 任何已有题目都必须有完整答案或明确标记“资料未给答案”。
- 自编即时练习必须有参考答案，且考查内容能回溯到资料内出现过的例题或往年题知识点。
- 不新增无来源的往年题、试卷或虚构题源。
- 将 `1.4.1` 这类深层小数编号简化为中文“一、二、三”或项目符号。

## 验收清单

- `applied_fixes` 与 `remaining_issues` 合理。
- `polished_textbook.md` 章节完整，无大段空章。
- `polishing_reports/*.json` 中剩余问题都可解释为资料缺失或需人工裁决。
- 精修后 JSON/source_refs 仍可回溯，不丢失来源。
