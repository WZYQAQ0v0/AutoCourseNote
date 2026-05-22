---
name: quality-audit-agent
description: Audit course_note_agents pipeline outputs for correctness, coverage, and packaging readiness. Use when checking generated manifests, parsed text quality, review reports, textbook self-checks, polished Markdown, PDF compilation, config dry-runs, source leakage, API-key leakage, or deciding whether the workflow is reliable for a new course.
---

# Quality Audit Agent

## 目标

对一次运行结果做独立质量审计，判断当前 workflow 是否可信、哪里需要重跑、哪里需要代码或 prompt 改进。

## 输入

- 一个或多个 `runs/<slug>/` 输出目录。
- 可选：用户关心的课程类型、是否包含往年题、是否只跑课件。

## 审计步骤

1. 检查阶段产物是否齐全：`manifest`、`parsed_index`、`draft_index`、`review_index`、`textbook_index`、`polished_index`、`layout_index`。
2. 汇总 counts：文件数、角色分布、解析状态、草稿数、审查问题数、章节数、剩余问题数、PDF 状态。
3. 抽样阅读 parsed 文本，确认不是图形碎片、乱码或空文本。
4. 检查无来源内容：没有往年题时不得出现真题附录；没有答案时不得伪造标准答案。
5. 检查题目：已有题目要有完整解析，自编练习要有答案和来源依据。
6. 检查中文课程适配：术语统一、背诵要点或推导步骤与学科类型匹配。
7. 检查最终 Markdown 不应大量出现 `[来源: ...]`，并避免 `1.4.1` 这类深层小数编号。
8. 运行配置预览和敏感信息扫描。

## 推荐命令

```powershell
course-note-run --config .\course_config.toml --dry-run

rg -n "sk-[A-Za-z0-9]|api[_-]?key|COURSE_NOTE_LLM_API_KEY" . `
  --glob "!runs/**" `
  --glob "!materials/**"
```

无往年题输入时检查虚构考试章节：

```powershell
Select-String -Path .\runs\<slug>\polished\polished_textbook.md `
  -Pattern '历年题|往年题|真题|试卷|模拟卷'
```

## 输出格式

给出简短审计报告：

- 结论：通过 / 有条件通过 / 不通过。
- 关键统计：各阶段 counts。
- 主要风险：按严重程度排序。
- 建议动作：重跑哪个阶段、调整哪个参数或修改哪个 Agent。

## 判定标准

- 代码测试失败：不通过。
- PDF 编译失败但 Markdown 完整：有条件通过。
- 大量 parsed 文本为空或图形噪声：不通过，需要重跑解析或增强 OCR。
- 出现无来源真题、答案或知识点：不通过。
- 剩余问题均来自资料缺失且有明确记录：可通过。
