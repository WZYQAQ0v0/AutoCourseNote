"""Local resource indexing for phase-1 ingestion."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from course_note_agents.ingestion.classifier import classify_material
from course_note_agents.ingestion.content_probe import probe_file
from course_note_agents.ingestion.fingerprint import (
    guess_mime_type,
    is_supported_material,
    iso_modified_time,
    logical_suffix,
    sha256_file,
    should_skip_path,
)
from course_note_agents.ingestion.models import FileFingerprint, IndexedFile, Manifest


class LocalResourceIndexer:
    def __init__(
        self,
        materials_dir: Path | str,
        output_dir: Path | str,
        course_id: str,
        language: str = "zh-CN",
        include_hidden: bool = False,
        include_unsupported: bool = False,
        max_preview_chars: int = 8000,
    ) -> None:
        self.materials_dir = Path(materials_dir).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.course_id = course_id
        self.language = language
        self.include_hidden = include_hidden
        self.include_unsupported = include_unsupported
        self.max_preview_chars = max_preview_chars

    def build_manifest(self) -> Manifest:
        if not self.materials_dir.exists():
            raise FileNotFoundError(f"Materials directory does not exist: {self.materials_dir}")
        if not self.materials_dir.is_dir():
            raise NotADirectoryError(f"Materials path is not a directory: {self.materials_dir}")

        indexed_files: list[IndexedFile] = []
        skipped = Counter()
        seen_hashes: Counter[str] = Counter()

        for path in sorted(self.materials_dir.rglob("*")):
            if not path.is_file():
                continue
            if _is_relative_to(path.resolve(), self.output_dir):
                skipped["output_dir"] += 1
                continue
            if should_skip_path(path.relative_to(self.materials_dir), self.include_hidden):
                skipped["hidden_or_excluded"] += 1
                continue
            if not is_supported_material(path, self.include_unsupported):
                skipped["unsupported_or_generated"] += 1
                continue

            item = self._index_file(path)
            indexed_files.append(item)
            seen_hashes[item.sha256] += 1

        duplicate_count = sum(count - 1 for count in seen_hashes.values() if count > 1)
        role_counts = Counter(item.document_role for item in indexed_files)
        counts = {
            "total_files": len(indexed_files),
            "duplicate_files_by_sha256": duplicate_count,
            "by_role": dict(sorted(role_counts.items())),
            "skipped": dict(sorted(skipped.items())),
        }
        return Manifest(
            schema_version="phase1.manifest.v1",
            course_id=self.course_id,
            language=self.language,
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            materials_dir=str(self.materials_dir),
            output_dir=str(self.output_dir),
            counts=counts,
            files=indexed_files,
        )

    def _index_file(self, path: Path) -> IndexedFile:
        rel_path = path.relative_to(self.materials_dir).as_posix()
        fingerprint = FileFingerprint(
            path=rel_path,
            absolute_path=str(path.resolve()),
            extension=logical_suffix(path),
            mime_type=guess_mime_type(path),
            size_bytes=path.stat().st_size,
            modified_at=iso_modified_time(path),
            sha256=sha256_file(path),
        )
        probe = probe_file(path, self.max_preview_chars)
        classification = classify_material(Path(rel_path), probe)
        return IndexedFile(
            file_id=fingerprint.file_id,
            path=fingerprint.path,
            absolute_path=fingerprint.absolute_path,
            extension=fingerprint.extension,
            mime_type=fingerprint.mime_type,
            size_bytes=fingerprint.size_bytes,
            modified_at=fingerprint.modified_at,
            sha256=fingerprint.sha256,
            document_role=classification.document_role,
            confidence=classification.confidence,
            reason=classification.reason,
            next_pipeline=classification.next_pipeline,
            secondary_roles=classification.secondary_roles,
            processing_hints=classification.processing_hints,
            probe_method=probe.probe_method,
            page_count=probe.page_count,
            slide_count=probe.slide_count,
            word_count=probe.word_count,
            needs_ocr=probe.needs_ocr,
            signals=classification.signals,
            warnings=probe.warnings,
        )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
