"""Data models for polished textbook artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class PolishedChapter:
    chapter_id: str
    title: str
    markdown_ref: str
    source_refs: list[str]
    applied_fix_count: int
    remaining_issue_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PolishedTextbookIndex:
    schema_version: str
    course_id: str
    language: str
    generated_at: str
    textbook_index_ref: str
    polished_markdown_ref: str
    polished_chapters_dir: str
    polishing_reports_dir: str
    glossary_ref: str | None
    symbols_ref: str | None
    citations_ref: str | None
    chapters: list[PolishedChapter]
    counts: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
