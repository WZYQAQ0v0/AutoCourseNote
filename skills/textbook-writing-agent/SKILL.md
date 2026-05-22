---
name: textbook-writing-agent
description: Assemble reviewed course notes into a complete textbook-style manuscript. Use when generating an adaptive chapter outline, merging multi-source reviewed notes, writing chapters with definitions, explanations, examples, exercises, glossary, symbols, citations, and self-check iterations for any discipline.
---

# Textbook Writing Agent

## 目标

从所有审查版笔记中生成一套完整教材式 Markdown。教材编写 Agent 负责全书结构、内容融合、章节写作、术语表、引用表和两轮自检。

## 输入与输出

- 输入：`runs/<slug>/review/review_index.json`。
- 输出：`runs/<slug>/textbook/textbook_index.json`、`textbook.md`、`textbook_outline.json`、`textbook_chapters/*.md`、`glossary.json`、`symbols.json`、`citations.json`、`self_checks/*.json`。
- Schema：`textbook_index.schema.json`。

## 推荐命令

```powershell
course-note-textbook `
  --review-index .\runs\<slug>\review\review_index.json `
  --output-dir .\runs\<slug>\textbook `
  --llm-timeout-seconds 300 `
  --max-outline-context-chars 70000 `
  --max-chapter-context-chars 80000 `
  --max-self-check-chars 120000 `
  --self-check-iterations 2 `
  --max-self-check-iterations 2
```

## 目录生成规则

- 先识别课程形态，再决定结构：可按讲次、主题、理论-方法-应用、历史-现状-前沿等组织。
- 覆盖所有核心知识点，章节权重与资料篇幅、讲授位置、题目频率成正比。
- 每章包含导学、正文、总结、思考题或自测。
- 没有往年题资料时，不生成“历年题”“真题”“模拟卷”章节。

## 内容融合规则

- 多源重复内容合并为最清晰的一版，保留必要的多角度解释。
- 冲突内容要标记来源并保守处理；无法裁决时写入脚注或问题清单。
- 所有关键定义、公式、题目、图表说明保留来源元数据，但 Markdown 正文不逐行添加 `[来源: ...]`。
- 首次出现术语进入 `glossary.json`；数学符号进入 `symbols.json`。

## 题目与练习规则

- 所有来自 PPT、作业、往年题的题目都要给完整解答过程，不能只写思路。
- 自行生成的即时练习必须只考查资料中已出现的例题、作业或往年题对应知识点，并附答案。
- 资料中的往年题要在教材最后单列原文附录，原封不动呈现；只有存在 `past_exam` 时才这样做。
- 文科课程可降低练习密度，但要提高背诵清单、辨析题、论述题框架和知识点完整性。
- 章节内标题保持轻量，不使用 `1.4.1` 这类深层小数编号；详细讲解内部用“一、二、三”或项目符号。

## 自检规则

- 至少执行两轮自检，检查章节顺序、前置知识、覆盖率、重复、题目是否先讲后练。
- 自检不得用过短修订稿覆盖完整正文。
- 网络或 LLM 失败时保留可读兜底正文，并记录 open issue。
