"""Data models for textbook generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TextbookChapter:
    chapter_id: str
    title: str
    markdown_ref: str
    source_refs: list[str]
    open_issues: list[str] = field(default_factory=list)
    suggested_figures: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SelfCheckReport:
    iteration: int
    report_ref: str
    pass_status: bool
    severe_issue_count: int
    revision_ref: str | None = None


@dataclass(slots=True)
class TextbookIndex:
    schema_version: str
    course_id: str
    language: str
    generated_at: str
    review_index_ref: str
    outline_ref: str
    textbook_markdown_ref: str
    chapters_dir: str
    glossary_ref: str
    symbols_ref: str
    citations_ref: str
    self_checks: list[SelfCheckReport]
    chapters: list[TextbookChapter]
    counts: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

