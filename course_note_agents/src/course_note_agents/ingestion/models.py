"""Shared data models for phase-1 ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DocumentRole = Literal[
    "syllabus",
    "textbook",
    "lecture_slides",
    "assignment",
    "past_exam",
    "solution",
    "reference_paper",
    "notes",
    "miscellaneous",
]


PIPELINE_BY_ROLE: dict[str, str] = {
    "syllabus": "syllabus_parser",
    "textbook": "textbook_parser",
    "lecture_slides": "slide_parser",
    "assignment": "problem_set_parser",
    "past_exam": "exam_parser",
    "solution": "solution_parser",
    "reference_paper": "reference_parser",
    "notes": "note_parser",
    "miscellaneous": "generic_parser",
}


@dataclass(slots=True)
class FileFingerprint:
    path: str
    absolute_path: str
    extension: str
    mime_type: str
    size_bytes: int
    modified_at: str
    sha256: str

    @property
    def file_id(self) -> str:
        return f"sha256:{self.sha256}"


@dataclass(slots=True)
class ContentProbe:
    text_preview: str = ""
    page_count: int | None = None
    slide_count: int | None = None
    word_count: int = 0
    needs_ocr: bool = False
    probe_method: str = "none"
    warnings: list[str] = field(default_factory=list)
    structural_signals: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClassificationResult:
    document_role: DocumentRole
    confidence: float
    reason: str
    next_pipeline: str
    scores: dict[str, float]
    secondary_roles: list[DocumentRole] = field(default_factory=list)
    processing_hints: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IndexedFile:
    file_id: str
    path: str
    absolute_path: str
    extension: str
    mime_type: str
    size_bytes: int
    modified_at: str
    sha256: str
    document_role: DocumentRole
    confidence: float
    reason: str
    next_pipeline: str
    probe_method: str
    secondary_roles: list[DocumentRole] = field(default_factory=list)
    processing_hints: list[str] = field(default_factory=list)
    page_count: int | None = None
    slide_count: int | None = None
    word_count: int = 0
    needs_ocr: bool = False
    signals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Manifest:
    schema_version: str
    course_id: str
    language: str
    generated_at: str
    materials_dir: str
    output_dir: str
    counts: dict[str, Any]
    files: list[IndexedFile]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["files"] = [item.to_dict() for item in self.files]
        return data
