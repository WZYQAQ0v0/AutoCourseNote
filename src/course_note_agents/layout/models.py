"""Data models for book layout artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class LayoutIndex:
    schema_version: str
    course_id: str
    language: str
    generated_at: str
    source_index_ref: str
    source_markdown_ref: str
    tex_ref: str
    pdf_ref: str | None
    compile_status: str
    compile_log_ref: str | None
    counts: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
