"""Textbook writing agent."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from course_note_agents.markdown_cleanup import clean_visible_markdown
from course_note_agents.textbook.models import SelfCheckReport, TextbookChapter, TextbookIndex
from course_note_agents.textbook.prompts import (
    CHAPTER_WRITER_SYSTEM_PROMPT,
    OUTLINE_SYSTEM_PROMPT,
    REVISION_SYSTEM_PROMPT,
    SELF_CHECK_SYSTEM_PROMPT,
    STRUCTURE_REVIEW_SYSTEM_PROMPT,
    chapter_user_prompt,
    outline_user_prompt,
    revision_user_prompt,
    self_check_user_prompt,
    structure_review_user_prompt,
)


class JSONChatClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        ...


class TextbookWritingAgent:
    def __init__(
        self,
        review_index_path: Path | str,
        output_dir: Path | str | None,
        client: JSONChatClient,
        max_outline_context_chars: int = 45000,
        max_chapter_context_chars: int = 36000,
        max_self_check_chars: int = 60000,
        self_check_iterations: int = 2,
        max_self_check_iterations: int | None = None,
        limit_chapters: int | None = None,
    ) -> None:
        self.review_index_path = Path(review_index_path).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else self.review_index_path.parent.resolve()
        self.chapters_dir = self.output_dir / "textbook_chapters"
        self.reports_dir = self.output_dir / "self_checks"
        self.client = client
        self.max_outline_context_chars = max_outline_context_chars
        self.max_chapter_context_chars = max_chapter_context_chars
        self.max_self_check_chars = max_self_check_chars
        self.self_check_iterations = max(0, self_check_iterations)
        if max_self_check_iterations is None:
            self.max_self_check_iterations = 0 if self.self_check_iterations == 0 else max(self.self_check_iterations, 4)
        else:
            self.max_self_check_iterations = max(self.self_check_iterations, max(0, max_self_check_iterations))
        self.limit_chapters = limit_chapters

    def run(self) -> TextbookIndex:
        review_index = self._read_json(self.review_index_path)
        review_base = self.review_index_path.parent
        reviewed_docs = [
            (entry, self._read_json(review_base / entry["reviewed_ref"]))
            for entry in review_index.get("documents", [])
        ]
        reviewed_docs = self._sort_reviewed_docs(reviewed_docs)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._clear_generated_files(self.chapters_dir, "*.md")
        self._clear_generated_files(self.reports_dir, "*.json")

        review_context = self._review_context(reviewed_docs, self.max_outline_context_chars)
        outline = self._build_outline(review_context, reviewed_docs)
        outline = self._review_outline(outline, review_context)
        outline = self._sanitize_outline_for_available_sources(outline, reviewed_docs)
        outline_path = self.output_dir / "textbook_outline.json"
        self._write_json(outline_path, outline)

        exam_context = self._exam_context(reviewed_docs, max_chars=18000)
        known_years = self._known_years(reviewed_docs)
        chapter_entries, chapter_markdowns, glossary, symbols, citations = self._write_chapters(
            outline, reviewed_docs, exam_context, known_years
        )
        appendix = self._exam_appendix(reviewed_docs)
        textbook_markdown = self._assemble_textbook(outline, chapter_markdowns, appendix)

        self_checks, textbook_markdown = self._self_check_and_revise(outline, textbook_markdown)
        textbook_markdown = clean_visible_markdown(textbook_markdown)

        textbook_ref = "textbook.md"
        (self.output_dir / textbook_ref).write_text(textbook_markdown.rstrip() + "\n", encoding="utf-8")
        glossary_ref = "glossary.json"
        symbols_ref = "symbols.json"
        citations_ref = "citations.json"
        self._write_json(self.output_dir / glossary_ref, {"items": self._dedupe_by_key(glossary, "term")})
        self._write_json(self.output_dir / symbols_ref, {"items": self._dedupe_by_key(symbols, "symbol")})
        self._write_json(self.output_dir / citations_ref, {"items": citations})

        index = TextbookIndex(
            schema_version="phase5.textbook_index.v1",
            course_id=review_index["course_id"],
            language=review_index.get("language", "zh-CN"),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            review_index_ref=str(self.review_index_path),
            outline_ref=str(outline_path.relative_to(self.output_dir).as_posix()),
            textbook_markdown_ref=textbook_ref,
            chapters_dir=str(self.chapters_dir),
            glossary_ref=glossary_ref,
            symbols_ref=symbols_ref,
            citations_ref=citations_ref,
            self_checks=self_checks,
            chapters=chapter_entries,
            counts={
                "chapters": len(chapter_entries),
                "glossary_terms": len(self._dedupe_by_key(glossary, "term")),
                "symbols": len(self._dedupe_by_key(symbols, "symbol")),
                "citations": len(citations),
                "self_check_iterations": len(self_checks),
            },
        )
        self._write_json(self.output_dir / "textbook_index.json", index.to_dict())
        return index

    def _build_outline(
        self,
        review_context: str,
        reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> dict[str, Any]:
        try:
            return self.client.chat_json(
                [
                    {"role": "system", "content": OUTLINE_SYSTEM_PROMPT},
                    {"role": "user", "content": outline_user_prompt(review_context)},
                ]
            )
        except RuntimeError as exc:
            if "valid JSON" not in str(exc):
                raise
            return self._fallback_outline(reviewed_docs, str(exc))

    def _review_outline(self, outline: dict[str, Any], review_context: str) -> dict[str, Any]:
        try:
            result = self.client.chat_json(
                [
                    {"role": "system", "content": STRUCTURE_REVIEW_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": structure_review_user_prompt(
                            json.dumps(outline, ensure_ascii=False, indent=2),
                            review_context[: self.max_outline_context_chars],
                        ),
                    },
                ]
            )
        except RuntimeError as exc:
            if "valid JSON" not in str(exc):
                raise
            outline["structure_review"] = {
                "approved": False,
                "findings": [{"severity": "medium", "issue": "结构审查返回非标准 JSON", "action": str(exc)}],
            }
            return outline
        revised = result.get("revised_outline")
        if isinstance(revised, dict) and revised.get("chapters"):
            revised["structure_review"] = {
                "approved": bool(result.get("approved")),
                "findings": result.get("findings", []),
            }
            return revised
        outline["structure_review"] = {"approved": bool(result.get("approved")), "findings": result.get("findings", [])}
        return outline

    @staticmethod
    def _sanitize_outline_for_available_sources(
        outline: dict[str, Any],
        reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> dict[str, Any]:
        has_exam = any(entry.get("document_role") == "past_exam" for entry, _doc in reviewed_docs)
        if has_exam:
            return outline
        exam_markers = ("历年题", "往年题", "真题", "试卷", "past exam", "exam appendix")
        chapters = []
        removed = []
        for chapter in outline.get("chapters", []):
            title = str(chapter.get("title", ""))
            chapter_id = str(chapter.get("chapter_id", ""))
            haystack = f"{title} {chapter_id}".lower()
            if any(marker.lower() in haystack for marker in exam_markers):
                removed.append({"chapter_id": chapter_id, "title": title})
                continue
            chapters.append(chapter)
        if removed:
            outline["chapters"] = chapters
            findings = outline.setdefault("source_sanitization", [])
            if isinstance(findings, list):
                findings.append(
                    {
                        "action": "removed_exam_chapters_without_exam_sources",
                        "removed": removed,
                    }
                )
            logic = str(outline.get("pedagogical_logic", ""))
            logic = re.sub(r"，?全书末尾设[^。]*历年题[^。]*。?", "。", logic)
            logic = logic.replace("与历年题附录", "").replace("、历年题附录", "").replace("历年题附录", "")
            outline["pedagogical_logic"] = logic
            style = outline.get("style_guide")
            if isinstance(style, list):
                outline["style_guide"] = [
                    item for item in style if not any(marker in str(item) for marker in ("历年题", "往年题", "真题"))
                ]
        outline["chapters"] = TextbookWritingAgent._normalize_chapter_titles_and_order(outline.get("chapters", []))
        return outline

    @staticmethod
    def _normalize_chapter_titles_and_order(chapters: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = [chapter for chapter in chapters if isinstance(chapter, dict)]
        for chapter in normalized:
            refs = TextbookWritingAgent._source_refs_from_chapter_plan(chapter)
            source_title = TextbookWritingAgent._source_title_from_refs(refs)
            current_title = str(chapter.get("title", ""))
            if source_title and re.search(r"第[一二三四五六七八九十百\d]+讲", current_title):
                chapter["title"] = source_title

        def key(chapter: dict[str, Any]) -> tuple[int, tuple[int, int, str], str]:
            title = str(chapter.get("title", ""))
            if "导学" in title or "使用说明" in title:
                return (0, (0, 0, ""), title)
            if "总结" in title or "综合思考" in title:
                return (2, (1, 10**6, ""), title)
            refs = TextbookWritingAgent._source_refs_from_chapter_plan(chapter)
            source_text = " ".join(refs) or title
            return (1, TextbookWritingAgent._source_order_key(source_text), title)

        return sorted(normalized, key=key)

    @staticmethod
    def _source_title_from_refs(refs: list[str]) -> str:
        for ref in refs:
            name = Path(ref).stem
            if not re.search(r"第[一二三四五六七八九十百\d]+讲", name):
                continue
            name = re.sub(r"[（(]\s*20\d{2}\s*[）)]", "", name)
            name = re.sub(r"[（(]?(审查补充版|修订版|合并版)[）)]?", "", name)
            return name.strip(" -_－—、：:（）()")
        return ""

    def _write_chapters(
        self,
        outline: dict[str, Any],
        reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]],
        exam_context: str,
        known_years: set[str],
    ) -> tuple[list[TextbookChapter], list[str], list[dict], list[dict], list[dict]]:
        chapters = list(outline.get("chapters", []))
        if self.limit_chapters is not None:
            chapters = chapters[: self.limit_chapters]

        entries: list[TextbookChapter] = []
        chapter_markdowns: list[str] = []
        glossary: list[dict] = []
        symbols: list[dict] = []
        citations: list[dict] = []
        review_context = self._review_context(reviewed_docs, self.max_chapter_context_chars)

        for index, chapter in enumerate(chapters, start=1):
            try:
                result = self.client.chat_json(
                    [
                        {"role": "system", "content": CHAPTER_WRITER_SYSTEM_PROMPT},
                        {"role": "user", "content": chapter_user_prompt(chapter, outline, review_context, exam_context)},
                    ]
                )
            except RuntimeError as exc:
                result = self._fallback_chapter_result(chapter, reviewed_docs, index, str(exc))
            chapter_id = str(result.get("chapter_id") or chapter.get("chapter_id") or f"ch{index:02d}")
            title = str(result.get("title") or chapter.get("title") or f"第{index}章")
            markdown = str(result.get("markdown") or "").strip()
            markdown = self._sanitize_generated_markdown(markdown, known_years)
            if not markdown:
                markdown = f"## {title}\n\n> 本章生成失败：模型返回空正文。"
            filename = f"{chapter_id}_{self._safe_name(title)}.md"
            path = self.chapters_dir / filename
            path.write_text(markdown.rstrip() + "\n", encoding="utf-8")

            glossary.extend(item for item in result.get("glossary_terms", []) if isinstance(item, dict))
            symbols.extend(item for item in result.get("symbols", []) if isinstance(item, dict))
            citations.extend(item for item in result.get("citations", []) if isinstance(item, dict))
            entries.append(
                TextbookChapter(
                    chapter_id=chapter_id,
                    title=title,
                    markdown_ref=str(path.relative_to(self.output_dir).as_posix()),
                    source_refs=self._collect_source_refs(result),
                    open_issues=[str(item) for item in result.get("open_issues", []) if item],
                    suggested_figures=[item for item in result.get("suggested_figures", []) if isinstance(item, dict)],
                )
            )
            chapter_markdowns.append(f"# {title}\n\n{markdown}")
        return entries, chapter_markdowns, glossary, symbols, citations

    def _fallback_chapter_result(
        self,
        chapter: dict[str, Any],
        reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]],
        index: int,
        reason: str,
    ) -> dict[str, Any]:
        title = str(chapter.get("title") or f"第{index}章")
        chapter_id = str(chapter.get("chapter_id") or f"ch{index:02d}")
        source_refs = self._source_refs_from_chapter_plan(chapter)
        matched_docs = [
            (entry, doc)
            for entry, doc in reviewed_docs
            if not source_refs or str(entry.get("source_path", "")) in source_refs
        ]
        if not matched_docs:
            matched_docs = reviewed_docs[:1]
        material_parts: list[str] = []
        remaining_issues: list[str] = [f"本章 LLM 写作调用失败，已保留审查笔记作为兜底正文：{reason[:300]}"]
        for entry, doc in matched_docs:
            source_path = str(entry.get("source_path", "unknown"))
            body = str(doc.get("revised_markdown") or doc.get("markdown") or "").strip()
            if doc.get("remaining_open_issues"):
                remaining_issues.extend(str(item) for item in doc.get("remaining_open_issues", []) if item)
            if body:
                material_parts.append(f"### 来源材料：{source_path}\n\n{body[:12000]}")
        markdown = "\n\n".join(
            [
                "## 本章导学",
                "本章使用审查补充后的来源笔记生成兜底版本，重点保留原始知识点、概念、论述框架和可背诵内容，供后续精修 Agent 继续处理。",
                "## 核心材料整理",
                "\n\n".join(material_parts) if material_parts else "> 未找到可用审查笔记正文。",
                "## 记忆背诵清单",
                "- 请根据上方来源材料逐条背诵核心概念、人物/事件/观点、理论脉络和论述要点。\n- 本章为兜底正文，后续可由精修 Agent 或人工复核进一步压缩为背诵提纲。",
                "## 待补与核查",
                "\n".join(f"- {item}" for item in dict.fromkeys(remaining_issues)),
            ]
        )
        return {
            "chapter_id": chapter_id,
            "title": title,
            "markdown": markdown,
            "glossary_terms": [],
            "symbols": [],
            "citations": [{"claim": f"{title} 兜底正文来自审查笔记", "source_refs": source_refs}],
            "open_issues": remaining_issues,
            "suggested_figures": [],
        }

    @staticmethod
    def _source_refs_from_chapter_plan(chapter: dict[str, Any]) -> list[str]:
        refs: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "source_refs" and isinstance(item, list):
                        refs.extend(str(ref) for ref in item if ref)
                    else:
                        visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(chapter)
        return list(dict.fromkeys(refs))

    def _self_check_and_revise(
        self,
        outline: dict[str, Any],
        textbook_markdown: str,
    ) -> tuple[list[SelfCheckReport], str]:
        reports: list[SelfCheckReport] = []
        current = textbook_markdown
        outline_json = json.dumps(outline, ensure_ascii=False, indent=2)
        if self.max_self_check_iterations <= 0:
            return reports, current

        for iteration in range(1, self.max_self_check_iterations + 1):
            check_markdown = self._self_check_excerpt(current)
            try:
                report = self.client.chat_json(
                    [
                        {"role": "system", "content": SELF_CHECK_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": self_check_user_prompt(
                                check_markdown,
                                outline_json[:20000],
                                iteration,
                            ),
                        },
                    ]
                )
            except RuntimeError as exc:
                report = {
                    "pass": False,
                    "severe_issues": [],
                    "structure_issues": [],
                    "coverage_notes": [],
                    "example_alignment_issues": [],
                    "terminology_issues": [],
                    "revision_plan": [],
                    "parser_warning": f"Self-check returned invalid JSON; kept current textbook. {exc}",
                }
            report_ref = f"self_checks/self_check_{iteration}.json"
            self._write_json(self.output_dir / report_ref, report)
            severe_count = len(report.get("severe_issues", [])) if isinstance(report.get("severe_issues"), list) else 0
            revision_ref = None
            if report.get("revision_plan") or severe_count:
                try:
                    revision = self.client.chat_json(
                        [
                            {"role": "system", "content": REVISION_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": revision_user_prompt(
                                    current[: self.max_self_check_chars],
                                    json.dumps(report, ensure_ascii=False, indent=2),
                                ),
                            },
                        ]
                    )
                except RuntimeError as exc:
                    revision = {
                        "revised_markdown": current,
                        "changes": [],
                        "unresolved_issues": [f"修订阶段返回非标准 JSON，已保留当前版本：{exc}"],
                    }
                revision_ref = f"self_checks/revision_{iteration}.json"
                candidate = str(revision.get("revised_markdown") or "")
                revision_applied = False
                if candidate:
                    revision_applied, rejection_reason = self._revision_is_complete(current, candidate)
                    if revision_applied:
                        current = candidate
                    else:
                        revision["rejection_reason"] = rejection_reason
                        unresolved = revision.get("unresolved_issues")
                        if not isinstance(unresolved, list):
                            unresolved = []
                        unresolved.append(
                            "Revision was not applied because it appears incomplete; kept the previous full textbook."
                        )
                        revision["unresolved_issues"] = unresolved
                revision["applied"] = revision_applied
                self._write_json(self.output_dir / revision_ref, revision)
            reports.append(
                SelfCheckReport(
                    iteration=iteration,
                    report_ref=report_ref,
                    pass_status=bool(report.get("pass")),
                    severe_issue_count=severe_count,
                    revision_ref=revision_ref,
                )
            )
            if iteration >= self.self_check_iterations and severe_count == 0:
                break
        return reports, current

    def _self_check_excerpt(self, markdown: str) -> str:
        if len(markdown) <= self.max_self_check_chars:
            return markdown

        parts = [part for part in re.split(r"(?m)(?=^#\s+)", markdown) if part.strip()]
        if not parts:
            return markdown[: self.max_self_check_chars]

        per_part_budget = max(120, self.max_self_check_chars // len(parts))
        excerpts: list[str] = []
        for part in parts:
            if len(part) <= per_part_budget:
                excerpts.append(part.rstrip())
                continue
            marker = "\n\n...[content omitted for distributed self-check]...\n\n"
            available = max(40, per_part_budget - len(marker))
            head_budget = max(30, int(available * 0.75))
            tail_budget = max(0, available - head_budget)
            excerpts.append(
                part[:head_budget].rstrip()
                + marker
                + (part[-tail_budget:].lstrip() if tail_budget else "")
            )
        return "\n\n".join(excerpts)[: self.max_self_check_chars]

    @staticmethod
    def _revision_is_complete(current: str, candidate: str) -> tuple[bool, str]:
        candidate = candidate.strip()
        current = current.strip()
        if not candidate:
            return False, "revision is empty"

        current_len = len(current)
        candidate_len = len(candidate)
        if current_len >= 1000 and candidate_len < int(current_len * 0.7):
            return False, f"revision is too short ({candidate_len}/{current_len} chars)"

        current_lines = current.count("\n") + 1
        candidate_lines = candidate.count("\n") + 1
        if current_lines >= 50 and candidate_lines < max(20, current_lines // 2):
            return False, f"revision has too few lines ({candidate_lines}/{current_lines})"

        current_headings = TextbookWritingAgent._top_level_headings(current)
        if current_headings:
            candidate_headings = set(TextbookWritingAgent._top_level_headings(candidate))
            missing = [heading for heading in current_headings if heading not in candidate_headings]
            allowed_missing = max(0, len(current_headings) // 10)
            if len(missing) > allowed_missing:
                preview = ", ".join(missing[:5])
                return False, f"revision is missing top-level headings: {preview}"
        return True, ""

    @staticmethod
    def _top_level_headings(markdown: str) -> list[str]:
        return [
            match.group(1).strip()
            for match in re.finditer(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
            if match.group(1).strip()
        ]

    def _assemble_textbook(self, outline: dict[str, Any], chapters: list[str], appendix: str) -> str:
        title = outline.get("book_title") or "课程复习教材"
        logic = outline.get("pedagogical_logic") or ""
        style = outline.get("style_guide") or []
        preface = [
            f"# {title}",
            "",
            "## 使用说明",
            "",
            "本教材由审查后的课程笔记自动融合生成，当前版本用于后续审查与排版，不是最终出版稿。",
            f"整体编排逻辑：{logic}",
            "",
            "风格约定：",
            *[f"- {item}" for item in style],
        ]
        parts = ["\n".join(preface).rstrip(), "\n\n".join(chapters).rstrip()]
        if appendix.strip():
            parts.append(appendix.rstrip())
        return "\n\n".join(part for part in parts if part).rstrip() + "\n"

    def _exam_appendix(self, reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
        parts = ["# 附录：历年题原文与答案资料", ""]
        exam_docs = [entry for entry, _doc in reviewed_docs if entry.get("document_role") == "past_exam"]
        if not exam_docs:
            return ""
        if len(exam_docs) > 1:
            parts.extend(
                [
                    "## 版本说明",
                    "",
                    "以下往年题资料按来源文件分别列出。若原卷、答案版或答案修订版之间存在题面差异，视为不同资料版本；本附录不强行合并改写，便于回溯原始来源。",
                    "",
                ]
            )
        has_exam = False
        for entry, doc in reviewed_docs:
            if entry.get("document_role") != "past_exam":
                continue
            has_exam = True
            parts.append(f"## {entry['source_path']}")
            parts.append("")
            parts.append("以下内容来自解析后的往年题/答案资料，尽量保持原始题面与答案信息，用于后续排版 Agent 单独整理。")
            parts.append("")
            parts.append(doc.get("revised_markdown", "").strip())
            parts.append("")
        if not has_exam:
            parts.append("当前资料集中未识别到往年题。")
        return "\n".join(parts)

    def _review_context(
        self,
        reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]],
        max_chars: int,
    ) -> str:
        parts: list[str] = []
        if not reviewed_docs or max_chars <= 0:
            return ""
        per_doc_budget = max(1200, max_chars // len(reviewed_docs))
        for entry, doc in reviewed_docs:
            header = (
                f"## {doc.get('title') or entry['title']}\n"
                f"来源文件：{entry['source_path']}\n"
                f"类型：{entry['document_role']}\n"
                f"剩余问题：{doc.get('remaining_open_issues', [])}\n"
            )
            body_budget = max(300, per_doc_budget - len(header) - 10)
            body = str(doc.get("revised_markdown", ""))
            item = f"{header}正文：\n{body[:body_budget]}\n"
            parts.append(item)
            if len("\n\n".join(parts)) >= max_chars:
                break
        return "\n\n".join(parts)[:max_chars]

    @staticmethod
    def _exam_context(reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]], max_chars: int) -> str:
        text = "\n\n".join(
            f"## {entry['source_path']}\n{doc.get('revised_markdown', '')}"
            for entry, doc in reviewed_docs
            if entry.get("document_role") == "past_exam"
        )
        return text[:max_chars]

    @staticmethod
    def _fallback_outline(
        reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]],
        reason: str,
    ) -> dict[str, Any]:
        chapters: list[dict[str, Any]] = []
        lecture_docs = [(entry, doc) for entry, doc in reviewed_docs if entry.get("document_role") == "lecture_slides"]
        source_docs = lecture_docs or reviewed_docs
        total = max(1, len(source_docs))
        for index, (entry, doc) in enumerate(source_docs, start=1):
            title = str(doc.get("title") or Path(entry.get("source_path", f"第{index}讲")).stem)
            source_ref = str(entry.get("source_path", ""))
            chapters.append(
                {
                    "chapter_id": f"ch{index:02d}",
                    "title": title,
                    "weight": round(1 / total, 4),
                    "rationale": "由对应课件资料自动生成的保守章节。",
                    "bridge_from_previous": "承接上一讲内容。" if index > 1 else "课程起点。",
                    "sections": [
                        {
                            "section_id": f"ch{index:02d}-sec01",
                            "title": "本讲导学与核心概念",
                            "subsections": [
                                {
                                    "title": "知识点梳理",
                                    "knowledge_points": [title],
                                    "source_refs": [source_ref],
                                    "exam_relevance": "medium",
                                }
                            ],
                        },
                        {
                            "section_id": f"ch{index:02d}-sec02",
                            "title": "方法、材料细节与题目解析",
                            "subsections": [
                                {
                                    "title": "重点材料与练习",
                                    "knowledge_points": ["完整知识点覆盖", "题目或背诵自测"],
                                    "source_refs": [source_ref],
                                    "exam_relevance": "high",
                                }
                            ],
                        },
                        {
                            "section_id": f"ch{index:02d}-sec03",
                            "title": "章末总结、记忆清单与自测",
                            "subsections": [
                                {
                                    "title": "来源化复习",
                                    "knowledge_points": ["背诵要点", "练习答案或论述框架"],
                                    "source_refs": [source_ref],
                                    "exam_relevance": "medium",
                                }
                            ],
                        },
                    ],
                }
            )
        return {
            "book_title": TextbookWritingAgent._infer_course_title(reviewed_docs),
            "subject_profile": {
                "domain_type": "mixed",
                "learning_priority": "根据输入资料自适应组织：题目型内容保留完整解析，记忆型内容保证知识点文字完整。",
            },
            "pedagogical_logic": "按输入资料顺序组织，逐讲覆盖核心概念、重要材料、题目解析或背诵清单与章末复习。",
            "style_guide": [
                "中文讲解优先",
                "所有知识点必须尽量完整覆盖",
                "题目型内容给出完整解答过程",
                "记忆型内容给出背诵清单和参考答案",
            ],
            "chapters": chapters,
            "glossary_candidates": [],
            "symbol_candidates": [],
            "question_plan": [],
            "memorization_plan": [],
            "conflicts": [{"topic": "outline_generation", "description": "LLM 大纲 JSON 无法解析，已使用保守目录。", "resolution_policy": reason[:300]}],
        }

    @staticmethod
    def _infer_course_title(reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
        for entry, doc in reviewed_docs:
            title = TextbookWritingAgent._clean_course_title_candidate(str(doc.get("title") or ""))
            if title:
                return f"{title}复习教材"
            source_stem = TextbookWritingAgent._clean_course_title_candidate(
                Path(str(entry.get("source_path", ""))).stem
            )
            if source_stem:
                return f"{source_stem}复习教材"
        return "课程复习教材"

    @staticmethod
    def _clean_course_title_candidate(value: str) -> str:
        value = str(value).strip()
        if not value:
            return ""
        value = re.sub(r"\.(pptx?|pdf|docx?|txt|md)$", "", value, flags=re.IGNORECASE)
        value = re.sub(r"[（(]\s*20\d{2}\s*[）)]", "", value)
        value = re.sub(r"[（(]?(审查补充版|修订版|合并版)[）)]?", "", value)
        value = re.sub(r"^\s*第[一二三四五六七八九十百\d]+讲\s*", "", value)
        value = re.sub(r"^\s*(?:lecture|lect|lec)?\s*\d{1,3}\s*[-_.－—、]?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"(课程介绍|导论|绪论|概论|总论)\s*$", "", value)
        return value.strip(" -_－—、：:（）()")

    @staticmethod
    def _sort_reviewed_docs(
        reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        indexed_docs = list(enumerate(reviewed_docs))
        indexed_docs.sort(
            key=lambda item: (
                TextbookWritingAgent._source_order_key(
                    " ".join(
                        [
                            str(item[1][0].get("source_path", "")),
                            str(item[1][1].get("title", "")),
                        ]
                    )
                ),
                item[0],
            )
        )
        return [doc for _index, doc in indexed_docs]

    @staticmethod
    def _source_order_key(value: str) -> tuple[int, int, str]:
        normalized = value.lower()
        match = re.search(r"第([一二三四五六七八九十百\d]+)讲", value)
        if match:
            return (0, TextbookWritingAgent._parse_chinese_ordinal(match.group(1)), normalized)
        match = re.search(r"\b(?:lecture|lect|lec)\s*(\d{1,3})\b", normalized)
        if match:
            return (0, int(match.group(1)), normalized)
        match = re.search(r"^\s*(\d{1,3})\s*[-_.－—、]", value)
        if match:
            return (0, int(match.group(1)), normalized)
        return (1, 10**6, normalized)

    @staticmethod
    def _parse_chinese_ordinal(value: str) -> int:
        if value.isdigit():
            return int(value)
        digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        if value == "十":
            return 10
        if "十" in value:
            left, _, right = value.partition("十")
            tens = digits.get(left, 1) if left else 1
            ones = digits.get(right, 0) if right else 0
            return tens * 10 + ones
        return digits.get(value, 10**6)

    @staticmethod
    def _known_years(reviewed_docs: list[tuple[dict[str, Any], dict[str, Any]]]) -> set[str]:
        source_text = "\n".join(str(entry.get("source_path", "")) for entry, _doc in reviewed_docs)
        return set(re.findall(r"(?:19|20)\d{2}", source_text))

    @staticmethod
    def _sanitize_generated_markdown(markdown: str, known_years: set[str]) -> str:
        if not markdown:
            return markdown
        lines = markdown.splitlines()
        output: list[str] = []
        skip_heading_level: int | None = None
        for line in lines:
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if skip_heading_level is not None:
                if heading and len(heading.group(1)) <= skip_heading_level:
                    skip_heading_level = None
                else:
                    continue
            if heading:
                title = heading.group(2)
                if "其他年份" in title and len(known_years) <= 1:
                    skip_heading_level = len(heading.group(1))
                    continue
            years = set(re.findall(r"(?:19|20)\d{2}", line))
            unknown_years = years - known_years
            if unknown_years and any(marker in line for marker in ("未提供", "占位", "建议插入")):
                continue
            output.append(line)
        return clean_visible_markdown("\n".join(output))

    @staticmethod
    def _collect_source_refs(result: dict[str, Any]) -> list[str]:
        refs: list[str] = []
        for item in result.get("citations", []):
            if isinstance(item, dict):
                refs.extend(str(ref) for ref in item.get("source_refs", []) if ref)
        return list(dict.fromkeys(refs))

    @staticmethod
    def _dedupe_by_key(items: list[dict], key: str) -> list[dict]:
        seen: set[str] = set()
        deduped: list[dict] = []
        for item in items:
            value = str(item.get(key, "")).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            deduped.append(item)
        return deduped

    @staticmethod
    def _safe_name(value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_")
        return safe[:60] or "chapter"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _clear_generated_files(directory: Path, pattern: str) -> None:
        if not directory.exists():
            return
        for path in directory.glob(pattern):
            if path.is_file():
                path.unlink()
