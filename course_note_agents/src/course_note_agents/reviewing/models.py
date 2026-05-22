"""Data models for reviewed notes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ReviewFinding:
    severity: str
    issue: str
    action: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReviewedDocument:
    schema_version: str
    course_id: str
    language: str
    source: dict[str, Any]
    reviewer: dict[str, Any]
    title: str
    revised_markdown: str
    findings: list[ReviewFinding]
    supplements: list[str]
    remaining_open_issues: list[str]
    evidence_refs: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewIndexEntry:
    file_id: str
    source_path: str
    reviewed_ref: str
    document_role: str
    title: str
    finding_count: int
    supplement_count: int
    remaining_issue_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReviewIndex:
    schema_version: str
    course_id: str
    language: str
    generated_at: str
    draft_index_ref: str
    reviewed_documents_dir: str
    combined_markdown_ref: str
    counts: dict[str, Any]
    documents: list[ReviewIndexEntry]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

