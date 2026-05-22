"""Data models for parsed course materials."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

BlockType = Literal[
    "title",
    "paragraph",
    "problem",
    "solution",
    "figure",
    "table",
    "formula",
    "image",
    "unknown",
]


@dataclass(slots=True)
class ParsedBlock:
    block_id: str
    type: BlockType
    text: str
    page_number: int | None = None
    bbox: list[float] | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str
    blocks: list[ParsedBlock]
    width: float | None = None
    height: float | None = None
    needs_ocr: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedChunk:
    chunk_id: str
    type: str
    text: str
    page_start: int | None
    page_end: int | None
    block_ids: list[str]
    evidence_refs: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    schema_version: str
    course_id: str
    language: str
    file: dict[str, Any]
    parser: dict[str, Any]
    parse_status: str
    pages: list[ParsedPage]
    chunks: list[ParsedChunk]
    linear_text: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParsedIndexEntry:
    file_id: str
    source_path: str
    parsed_ref: str
    document_role: str
    secondary_roles: list[str]
    page_count: int
    chunk_count: int
    parse_status: str
    needs_ocr: bool
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedIndex:
    schema_version: str
    course_id: str
    language: str
    generated_at: str
    manifest_ref: str
    parsed_documents_dir: str
    counts: dict[str, Any]
    documents: list[ParsedIndexEntry]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

