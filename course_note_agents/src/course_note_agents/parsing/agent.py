"""Content parsing agent orchestration."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_note_agents.parsing.llm_refiner import LLMTextRefiner
from course_note_agents.parsing.models import ParsedChunk, ParsedDocument, ParsedIndex, ParsedIndexEntry
from course_note_agents.parsing.parsers import parse_file_pages
from course_note_agents.parsing.text_utils import make_chunks_from_blocks, normalize_text


class ContentParsingAgent:
    """Turn phase-1 material manifest entries into structured parsed documents."""

    def __init__(
        self,
        manifest_path: Path | str,
        output_dir: Path | str | None = None,
        max_chunk_chars: int = 2400,
        llm_refiner: LLMTextRefiner | None = None,
        limit_documents: int | None = None,
        limit_pages_per_document: int | None = None,
        include_roles: set[str] | None = None,
        exclude_roles: set[str] | None = None,
    ) -> None:
        self.manifest_path = Path(manifest_path).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else self.manifest_path.parent.resolve()
        self.parsed_dir = self.output_dir / "parsed_documents"
        self.max_chunk_chars = max_chunk_chars
        self.llm_refiner = llm_refiner
        self.limit_documents = limit_documents
        self.limit_pages_per_document = limit_pages_per_document
        self.include_roles = include_roles
        self.exclude_roles = exclude_roles or set()

    def run(self) -> ParsedIndex:
        manifest = self._read_manifest()
        self.parsed_dir.mkdir(parents=True, exist_ok=True)

        entries: list[ParsedIndexEntry] = []
        status_counts: Counter[str] = Counter()
        needs_ocr_count = 0

        file_entries = self._filter_file_entries(manifest["files"])
        if self.limit_documents is not None:
            file_entries = file_entries[: self.limit_documents]

        for file_entry in file_entries:
            parsed_doc = self.parse_one(manifest, file_entry)
            doc_name = self._safe_doc_name(file_entry)
            doc_path = self.parsed_dir / f"{doc_name}.json"
            self._write_json(doc_path, parsed_doc.to_dict())

            needs_ocr = any(page.needs_ocr for page in parsed_doc.pages)
            needs_ocr_count += int(needs_ocr)
            status_counts[parsed_doc.parse_status] += 1
            entries.append(
                ParsedIndexEntry(
                    file_id=file_entry["file_id"],
                    source_path=file_entry["path"],
                    parsed_ref=str(doc_path.relative_to(self.output_dir).as_posix()),
                    document_role=file_entry["document_role"],
                    secondary_roles=list(file_entry.get("secondary_roles", [])),
                    page_count=len(parsed_doc.pages),
                    chunk_count=len(parsed_doc.chunks),
                    parse_status=parsed_doc.parse_status,
                    needs_ocr=needs_ocr,
                    warnings=list(parsed_doc.warnings),
                )
            )

        index = ParsedIndex(
            schema_version="phase2.parsed_index.v1",
            course_id=manifest["course_id"],
            language=manifest.get("language", "zh-CN"),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            manifest_ref=str(self.manifest_path),
            parsed_documents_dir=str(self.parsed_dir),
            counts={
                "total_documents": len(entries),
                "needs_ocr_documents": needs_ocr_count,
                "by_parse_status": dict(sorted(status_counts.items())),
            },
            documents=entries,
        )
        self._write_json(self.output_dir / "parsed_index.json", index.to_dict())
        return index

    def parse_one(self, manifest: dict[str, Any], file_entry: dict[str, Any]) -> ParsedDocument:
        pages, parser_info, warnings = parse_file_pages(file_entry, manifest.get("language", "zh-CN"))
        if self.limit_pages_per_document is not None and len(pages) > self.limit_pages_per_document:
            pages = pages[: self.limit_pages_per_document]
            warnings = [
                *warnings,
                f"Document parsing limited to first {self.limit_pages_per_document} pages for this run.",
            ]
            parser_info = {
                **parser_info,
                "page_limit": self.limit_pages_per_document,
            }
        if self.llm_refiner is not None:
            before = self._llm_stats_snapshot()
            pages = self.llm_refiner.refine_pages(file_entry, pages, manifest.get("language", "zh-CN"))
            after = self._llm_stats_snapshot()
            parser_info = {
                **parser_info,
                "llm_refiner": {
                    "enabled": True,
                    "attempted_pages": after["attempted_pages"] - before["attempted_pages"],
                    "refined_pages": after["refined_pages"] - before["refined_pages"],
                    "skipped_pages": after["skipped_pages"] - before["skipped_pages"],
                    "failed_pages": after["failed_pages"] - before["failed_pages"],
                },
            }
        page_texts = [page.text for page in pages if page.text.strip()]
        linear_text = normalize_text("\n\n".join(page_texts))

        block_dicts: list[dict[str, Any]] = []
        for page in pages:
            for block in page.blocks:
                block_dicts.append(asdict(block))

        chunk_dicts = make_chunks_from_blocks(file_entry["file_id"], block_dicts, self.max_chunk_chars)
        chunks = [ParsedChunk(**chunk) for chunk in chunk_dicts]

        page_warnings = [warning for page in pages for warning in page.warnings]
        all_warnings = list(dict.fromkeys([*warnings, *page_warnings]))
        parse_status = self._parse_status(pages, linear_text, all_warnings)

        return ParsedDocument(
            schema_version="phase2.parsed_document.v1",
            course_id=manifest["course_id"],
            language=manifest.get("language", "zh-CN"),
            file={
                "file_id": file_entry["file_id"],
                "path": file_entry["path"],
                "absolute_path": file_entry["absolute_path"],
                "extension": file_entry["extension"],
                "mime_type": file_entry["mime_type"],
                "document_role": file_entry["document_role"],
                "secondary_roles": file_entry.get("secondary_roles", []),
                "next_pipeline": file_entry.get("next_pipeline"),
            },
            parser=parser_info,
            parse_status=parse_status,
            pages=pages,
            chunks=chunks,
            linear_text=linear_text,
            warnings=all_warnings,
        )

    def _read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest does not exist: {self.manifest_path}")
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _filter_file_entries(self, file_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for entry in file_entries:
            role = str(entry.get("document_role", ""))
            if self.include_roles is not None and role not in self.include_roles:
                continue
            if role in self.exclude_roles:
                continue
            filtered.append(entry)
        return filtered

    def _llm_stats_snapshot(self) -> dict[str, int]:
        if self.llm_refiner is None:
            return {"attempted_pages": 0, "refined_pages": 0, "skipped_pages": 0, "failed_pages": 0}
        return {
            "attempted_pages": self.llm_refiner.stats.attempted_pages,
            "refined_pages": self.llm_refiner.stats.refined_pages,
            "skipped_pages": self.llm_refiner.stats.skipped_pages,
            "failed_pages": self.llm_refiner.stats.failed_pages,
        }

    @staticmethod
    def _parse_status(pages: list, linear_text: str, warnings: list[str]) -> str:
        if linear_text:
            return "success_with_warnings" if warnings else "success"
        if any(page.needs_ocr for page in pages):
            return "requires_ocr"
        return "empty"

    @staticmethod
    def _safe_doc_name(file_entry: dict[str, Any]) -> str:
        digest = file_entry["sha256"][:16]
        stem = Path(file_entry["path"]).stem
        safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem).strip("_")
        if not safe_stem:
            safe_stem = "document"
        return f"{safe_stem[:60]}__{digest}"

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
