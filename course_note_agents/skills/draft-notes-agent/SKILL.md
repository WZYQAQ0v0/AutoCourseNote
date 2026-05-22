---
name: draft-notes-agent
description: Generate source-grounded first-pass course notes from parsed course materials. Use when converting parsed_index.json into per-document Markdown/JSON drafts, extracting knowledge points, questions, answers, examples, memorization items, and open issues while preserving citations.
---

# Draft Notes Agent

## 目标

按单份资料生成第一版结构化笔记。初稿应忠实、完整、可审查，为后续审查补充和教材编写提供材料。

## 输入与输出

- 输入：`runs/<slug>/parsed/parsed_index.json`。
- 输出：`runs/<slug>/draft/draft_index.json`、`draft_notes/*.json`、`draft_notes/*.md`、`combined_draft.md`。
- Schema：`draft_index.schema.json`、`draft_document.schema.json`。

## 推荐命令

```powershell
course-note-draft `
  --parsed-index .\runs\<slug>\parsed\parsed_index.json `
  --output-dir .\runs\<slug>\draft `
  --llm-timeout-seconds 240 `
  --max-input-chars 26000
```

## 写作规则

- 每份资料独立生成，不在本阶段强行合并全课程结构。
- 保留结构化来源：文件名、页码/幻灯片号、资料角色写入 `evidence_refs`，正文不逐行添加 `[来源: ...]`。
- 标出不确定项和资料缺口，写入 `open_issues`。
- 文科/记忆型课程：完整整理概念、人物、事件、流派、时代背景、论述框架、背诵要点。
- 理工/题目型课程：整理定义、公式、推导、算法、例题、完整解题过程。
- 往年题或 PPT 中出现的题目必须保留题干，并尽可能抽取答案和解析；不得只写“思路略”。

## 禁止事项

- 不凭空添加教材中没有的知识点。
- 不把图形噪声当作知识点。
- 不把单份资料改写成全书总论。
- 不因资料没有答案而编造标准答案；可以标为“资料未给出完整答案”。

## 验收清单

- 每个 draft 都能追溯到一个 parsed document。
- `combined_draft.md` 可直接阅读，不是 JSON 拼接残片。
- `open_issues` 真实反映缺口，不把失败吞掉。
- 中文术语保持统一，不无故中英混用。
