# Course Note Agent Skills

本目录保存项目内置 skills，用于把各 Agent 的职责、输入输出、命令参数和质量边界固化下来。它们随 `course_note_agents` 打包，既可以作为 Codex/Copilot 类工具的项目上下文，也可以作为维护 Agent prompt 与 CLI 流程的操作手册。

## Skill 与 Agent 映射

| Skill | 对应职责 | 主要输入 | 主要输出 |
| --- | --- | --- | --- |
| `course-workflow-orchestrator` | 全流程编排与断点续跑决策 | `materials/<course>/` | 各阶段 `runs/<slug>/<stage>/` |
| `material-ingestion-agent` | 资料扫描、分类、去重 | 本地资料目录 | `manifest.json` |
| `content-parsing-agent` | 多格式解析、文本清洗、OCR 标记 | `manifest.json` | `parsed_index.json` |
| `draft-notes-agent` | 单资料初稿生成 | `parsed_index.json` | `draft_index.json` |
| `review-enrichment-agent` | 审查、纠错、补充解释 | `draft_index.json` | `review_index.json` |
| `textbook-writing-agent` | 全书目录与教材正文生成 | `review_index.json` | `textbook_index.json` |
| `chapter-polishing-agent` | 章节精修与一致性修复 | `textbook_index.json` | `polished_index.json` |
| `layout-pdf-agent` | Markdown 到 LaTeX/PDF | `polished_index.json` | `layout_index.json`、`book.pdf` |
| `quality-audit-agent` | 全流程质量审计 | `runs/<slug>/` | 审计报告 |

## 使用方式

项目内使用时，直接阅读对应目录下的 `SKILL.md`。如果未来要让 Codex 自动发现这些 skills，可将需要的 skill 复制或安装到 `$CODEX_HOME/skills`，但项目源码本身不依赖全局安装。

新增或修改 Agent 时，同步更新对应 skill，特别是：

- CLI 参数变化；
- 输入/输出 schema 变化；
- prompt 规则变化；
- 质量验收规则变化；
- 对中文、图片、往年题答案混排等边界情况的处理变化。
