"""Chapter-level textbook polishing agent."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from course_note_agents.markdown_cleanup import clean_visible_markdown
from course_note_agents.polishing.models import PolishedChapter, PolishedTextbookIndex
from course_note_agents.polishing.prompts import CHAPTER_POLISH_SYSTEM_PROMPT, chapter_polish_user_prompt


class JSONChatClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        ...


class TextbookPolishingAgent:
    def __init__(
        self,
        textbook_index_path: Path | str,
        output_dir: Path | str | None,
        client: JSONChatClient,
        max_chapter_chars: int = 36000,
        max_self_check_chars: int = 24000,
        max_global_context_chars: int = 18000,
        limit_chapters: int | None = None,
    ) -> None:
        self.textbook_index_path = Path(textbook_index_path).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else self.textbook_index_path.parent.resolve()
        self.polished_dir = self.output_dir / "polished_chapters"
        self.reports_dir = self.output_dir / "polishing_reports"
        self.client = client
        self.max_chapter_chars = max_chapter_chars
        self.max_self_check_chars = max_self_check_chars
        self.max_global_context_chars = max_global_context_chars
        self.limit_chapters = limit_chapters

    def run(self) -> PolishedTextbookIndex:
        textbook_index = self._read_json(self.textbook_index_path)
        source_base = self.textbook_index_path.parent
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.polished_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._clear_generated_files(self.polished_dir, "*.md")
        self._clear_generated_files(self.reports_dir, "*.json")

        original_textbook = (source_base / textbook_index["textbook_markdown_ref"]).read_text(encoding="utf-8")
        self_check_context = self._self_check_context(source_base, textbook_index)
        global_context = self._global_context(source_base, textbook_index)
        appendix = self._extract_appendix(original_textbook)

        chapters = list(textbook_index.get("chapters", []))
        if self.limit_chapters is not None:
            chapters = chapters[: self.limit_chapters]

        chapter_entries: list[PolishedChapter] = []
        polished_parts: list[str] = [self._extract_preface(original_textbook)]
        all_warnings: list[str] = []
        total_fixes = 0
        total_remaining = 0

        for chapter in chapters:
            chapter_path = source_base / chapter["markdown_ref"]
            chapter_markdown = chapter_path.read_text(encoding="utf-8")
            try:
                result = self._polish_one_chapter(chapter, chapter_markdown, self_check_context, global_context)
            except RuntimeError as exc:
                result = {
                    "chapter_id": chapter.get("chapter_id"),
                    "title": chapter.get("title"),
                    "polished_markdown": chapter_markdown,
                    "applied_fixes": [],
                    "remaining_issues": [f"本章模型精修失败，已保留原文：{exc}"],
                    "consistency_notes": [],
                    "source_refs": chapter.get("source_refs", []),
                    "warnings": ["model_polish_failed"],
                }
            polished_markdown = str(result.get("polished_markdown") or chapter_markdown).strip()
            complete, rejection_reason = self._polished_markdown_is_complete(chapter_markdown, polished_markdown)
            if not complete:
                polished_markdown = chapter_markdown
                warnings = result.get("warnings")
                if not isinstance(warnings, list):
                    warnings = []
                warnings.append("polished_markdown_rejected_as_incomplete")
                result["warnings"] = warnings
                remaining_issues = result.get("remaining_issues")
                if not isinstance(remaining_issues, list):
                    remaining_issues = []
                remaining_issues.append(rejection_reason)
                result["remaining_issues"] = remaining_issues
            polished_markdown = self._postprocess_markdown(
                polished_markdown,
                title=str(result.get("title") or chapter.get("title") or "未命名章节"),
            )

            chapter_id = str(result.get("chapter_id") or chapter.get("chapter_id"))
            title = str(result.get("title") or chapter.get("title") or chapter_id)
            filename = f"{chapter_id}_{self._safe_name(title)}.md"
            markdown_ref = f"polished_chapters/{filename}"
            (self.output_dir / markdown_ref).write_text(polished_markdown.rstrip() + "\n", encoding="utf-8")

            report = {
                "chapter_id": chapter_id,
                "title": title,
                "applied_fixes": result.get("applied_fixes", []),
                "remaining_issues": result.get("remaining_issues", []),
                "consistency_notes": result.get("consistency_notes", []),
                "source_refs": result.get("source_refs", []),
                "warnings": result.get("warnings", []),
            }
            report_ref = f"polishing_reports/{chapter_id}.json"
            self._write_json(self.output_dir / report_ref, report)

            applied_fixes = [str(item) for item in result.get("applied_fixes", []) if item]
            remaining_issues = [str(item) for item in result.get("remaining_issues", []) if item]
            warnings = [str(item) for item in result.get("warnings", []) if item]
            all_warnings.extend(warnings)
            total_fixes += len(applied_fixes)
            total_remaining += len(remaining_issues)
            source_refs = [str(ref) for ref in result.get("source_refs", []) if ref]
            if not source_refs:
                source_refs = [str(ref) for ref in chapter.get("source_refs", []) if ref]
            chapter_entries.append(
                PolishedChapter(
                    chapter_id=chapter_id,
                    title=title,
                    markdown_ref=markdown_ref,
                    source_refs=list(dict.fromkeys(source_refs)),
                    applied_fix_count=len(applied_fixes),
                    remaining_issue_count=len(remaining_issues),
                    warnings=warnings,
                )
            )
            polished_parts.append(polished_markdown)

        if appendix:
            polished_parts.append(appendix)
        polished_markdown_ref = "polished_textbook.md"
        full_polished_markdown = clean_visible_markdown(
            "\n\n".join(part.strip() for part in polished_parts if part.strip())
        )
        (self.output_dir / polished_markdown_ref).write_text(
            full_polished_markdown.rstrip() + "\n",
            encoding="utf-8",
        )

        index = PolishedTextbookIndex(
            schema_version="phase6.polished_textbook_index.v1",
            course_id=textbook_index["course_id"],
            language=textbook_index.get("language", "zh-CN"),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            textbook_index_ref=str(self.textbook_index_path),
            polished_markdown_ref=polished_markdown_ref,
            polished_chapters_dir=str(self.polished_dir),
            polishing_reports_dir=str(self.reports_dir),
            glossary_ref=self._copy_optional_ref(source_base, textbook_index.get("glossary_ref")),
            symbols_ref=self._copy_optional_ref(source_base, textbook_index.get("symbols_ref")),
            citations_ref=self._copy_optional_ref(source_base, textbook_index.get("citations_ref")),
            chapters=chapter_entries,
            counts={
                "chapters": len(chapter_entries),
                "applied_fixes": total_fixes,
                "remaining_issues": total_remaining,
                "warnings": len(all_warnings),
            },
        )
        self._write_json(self.output_dir / "polished_index.json", index.to_dict())
        return index

    @staticmethod
    def _polished_markdown_is_complete(original: str, candidate: str) -> tuple[bool, str]:
        original = original.strip()
        candidate = candidate.strip()
        if not candidate:
            return False, "Polished chapter is empty."
        if len(original) >= 1200 and len(candidate) < int(len(original) * 0.65):
            return False, f"Polished chapter is too short ({len(candidate)}/{len(original)} chars)."
        original_headings = TextbookPolishingAgent._heading_set(original)
        if original_headings:
            candidate_headings = TextbookPolishingAgent._heading_set(candidate)
            missing = [heading for heading in original_headings if heading not in candidate_headings]
            if len(missing) > max(1, len(original_headings) // 3):
                return False, "Polished chapter is missing too many headings: " + ", ".join(missing[:5])
        return True, ""

    @staticmethod
    def _heading_set(markdown: str) -> list[str]:
        return [
            match.group(2).strip()
            for match in re.finditer(r"^(#{2,4})\s+(.+)$", markdown, flags=re.MULTILINE)
            if match.group(2).strip()
        ]

    def _polish_one_chapter(
        self,
        chapter: dict[str, Any],
        chapter_markdown: str,
        self_check_context: str,
        global_context: str,
    ) -> dict[str, Any]:
        chapter_id = str(chapter.get("chapter_id") or "")
        title = str(chapter.get("title") or chapter_id)
        metadata = json.dumps(chapter, ensure_ascii=False, indent=2)
        return self.client.chat_json(
            [
                {"role": "system", "content": CHAPTER_POLISH_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": chapter_polish_user_prompt(
                        chapter_id=chapter_id,
                        title=title,
                        chapter_markdown=chapter_markdown[: self.max_chapter_chars],
                        chapter_metadata_json=metadata[:8000],
                        self_check_context=self_check_context[: self.max_self_check_chars],
                        global_style_context=global_context[: self.max_global_context_chars],
                    ),
                },
            ]
        )

    def _self_check_context(self, source_base: Path, textbook_index: dict[str, Any]) -> str:
        parts: list[str] = []
        for check in textbook_index.get("self_checks", []):
            report_ref = check.get("report_ref")
            if not report_ref:
                continue
            report_path = source_base / str(report_ref)
            if not report_path.exists():
                continue
            report = self._read_json(report_path)
            parts.append(
                json.dumps(
                    {
                        "iteration": check.get("iteration"),
                        "pass": report.get("pass"),
                        "severe_issues": report.get("severe_issues", []),
                        "structure_issues": report.get("structure_issues", []),
                        "coverage_notes": report.get("coverage_notes", []),
                        "example_alignment_issues": report.get("example_alignment_issues", []),
                        "terminology_issues": report.get("terminology_issues", []),
                        "revision_plan": report.get("revision_plan", []),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return "\n\n".join(parts)

    def _global_context(self, source_base: Path, textbook_index: dict[str, Any]) -> str:
        parts: list[str] = []
        outline_ref = textbook_index.get("outline_ref")
        if outline_ref and (source_base / str(outline_ref)).exists():
            outline = self._read_json(source_base / str(outline_ref))
            parts.append("## Outline\n" + json.dumps(outline, ensure_ascii=False, indent=2)[:9000])
        for label, ref_key in (("Glossary", "glossary_ref"), ("Symbols", "symbols_ref"), ("Citations", "citations_ref")):
            ref = textbook_index.get(ref_key)
            if ref and (source_base / str(ref)).exists():
                parts.append(f"## {label}\n" + (source_base / str(ref)).read_text(encoding="utf-8")[:5000])
        return "\n\n".join(parts)

    @staticmethod
    def _extract_preface(markdown: str) -> str:
        lines = markdown.splitlines()
        if not lines:
            return "# 课程复习教材"
        starts = [idx for idx, line in enumerate(lines) if line.startswith("# ")]
        if len(starts) <= 1:
            return lines[0]
        return "\n".join(lines[: starts[1]]).strip()

    @staticmethod
    def _extract_appendix(markdown: str) -> str:
        marker = "# 附录：历年题原文与答案资料"
        index = markdown.find(marker)
        if index < 0:
            return ""
        return markdown[index:].strip()

    def _copy_optional_ref(self, source_base: Path, ref: str | None) -> str | None:
        if not ref:
            return None
        src = source_base / ref
        if not src.exists():
            return None
        dst = self.output_dir / Path(ref).name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return dst.name

    @staticmethod
    def _postprocess_markdown(markdown: str, title: str) -> str:
        markdown = _remove_unknown_source_placeholders(markdown)
        markdown = _fix_growth_order(markdown)
        markdown = clean_visible_markdown(markdown)
        if not markdown.lstrip().startswith("# "):
            markdown = f"# {title}\n\n{markdown.strip()}"
        return markdown.strip()

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


def _remove_unknown_source_placeholders(markdown: str) -> str:
    bad_markers = ("补充材料", "未提供", "占位", "建议插入其他年份")
    output: list[str] = []
    for line in markdown.splitlines():
        if any(marker in line for marker in bad_markers) and not line.strip().startswith(">"):
            continue
        output.append(line)
    return "\n".join(output)


def _fix_growth_order(markdown: str) -> str:
    patterns = [
        (r"(- n（线性）\n)(- n log log n)", r"\2\n\1"),
        (r"(- n \(与n同阶[^)]*\)\n)(- n log log n)", r"\2\n\1"),
        (r"(\d+\. n（线性）\n\s*\d+\. log\(n!\)[^\n]*\n\s*\d+\. .*?\n\s*)(\d+\. n log log n[^\n]*)", r"\2\n\1"),
    ]
    fixed = markdown
    for pattern, replacement in patterns:
        fixed = re.sub(pattern, replacement, fixed)
    return fixed
