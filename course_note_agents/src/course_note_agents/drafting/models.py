"""Data models for draft notes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DraftDocument:
    schema_version: str
    course_id: str
    language: str
    source: dict[str, Any]
    writer: dict[str, Any]
    title: str
    markdown: str
    key_points: list[str]
    evidence_refs: list[str]
    open_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DraftIndexEntry:
    file_id: str
    source_path: str
    draft_ref: str
    document_role: str
    title: str
    key_point_count: int
    evidence_refs: list[str]
    open_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DraftIndex:
    schema_version: str
    course_id: str
    language: str
    generated_at: str
    parsed_index_ref: str
    draft_documents_dir: str
    combined_markdown_ref: str
    counts: dict[str, Any]
    documents: list[DraftIndexEntry]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

