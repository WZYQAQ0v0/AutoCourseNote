"""Review and enrichment agent."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from course_note_agents.markdown_cleanup import clean_visible_markdown
from course_note_agents.reviewing.models import ReviewFinding, ReviewIndex, ReviewIndexEntry, ReviewedDocument
from course_note_agents.reviewing.prompts import SYSTEM_PROMPT, user_prompt


class JSONChatClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        ...


class ReviewEnrichmentAgent:
    def __init__(
        self,
        draft_index_path: Path | str,
        output_dir: Path | str | None,
        client: JSONChatClient,
        max_source_chars: int = 22000,
        max_related_chars: int = 12000,
        limit_documents: int | None = None,
    ) -> None:
        self.draft_index_path = Path(draft_index_path).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else self.draft_index_path.parent.resolve()
        self.reviewed_dir = self.output_dir / "reviewed_notes"
        self.client = client
        self.max_source_chars = max_source_chars
        self.max_related_chars = max_related_chars
        self.limit_documents = limit_documents

    def run(self) -> ReviewIndex:
        draft_index = self._read_json(self.draft_index_path)
        draft_base = self.draft_index_path.parent
        parsed_index = self._load_parsed_index(draft_index)
        parsed_base = Path(parsed_index["parsed_index_path"]).parent if parsed_index else None
        parsed_by_file_id = self._parsed_by_file_id(parsed_index) if parsed_index else {}

        self.reviewed_dir.mkdir(parents=True, exist_ok=True)
        draft_entries = draft_index["documents"]
        if self.limit_documents is not None:
            draft_entries = draft_entries[: self.limit_documents]

        all_drafts = [(entry, self._read_json(draft_base / entry["draft_ref"])) for entry in draft_index["documents"]]
        entries: list[ReviewIndexEntry] = []
        combined_parts: list[str] = []
        role_counts: Counter[str] = Counter()

        for entry in draft_entries:
            draft_doc = self._read_json(draft_base / entry["draft_ref"])
            parsed_doc = None
            if parsed_base is not None and entry["file_id"] in parsed_by_file_id:
                parsed_doc = self._read_json(parsed_base / parsed_by_file_id[entry["file_id"]]["parsed_ref"])
            reviewed = self.review_one(draft_index, entry, draft_doc, parsed_doc, all_drafts)

            reviewed_name = self._safe_review_name(entry)
            json_path = self.reviewed_dir / f"{reviewed_name}.json"
            md_path = self.reviewed_dir / f"{reviewed_name}.md"
            self._write_json(json_path, reviewed.to_dict())
            md_path.write_text(reviewed.revised_markdown.rstrip() + "\n", encoding="utf-8")

            role_counts[entry["document_role"]] += 1
            entries.append(
                ReviewIndexEntry(
                    file_id=entry["file_id"],
                    source_path=entry["source_path"],
                    reviewed_ref=str(json_path.relative_to(self.output_dir).as_posix()),
                    document_role=entry["document_role"],
                    title=reviewed.title,
                    finding_count=len(reviewed.findings),
                    supplement_count=len(reviewed.supplements),
                    remaining_issue_count=len(reviewed.remaining_open_issues),
                    warnings=reviewed.warnings,
                )
            )
            combined_parts.append(f"# {reviewed.title}\n\n{reviewed.revised_markdown.strip()}\n")

        combined_ref = "reviewed_notes/combined_reviewed.md"
        combined_path = self.output_dir / combined_ref
        combined_path.parent.mkdir(parents=True, exist_ok=True)
        combined_path.write_text("\n\n".join(combined_parts).rstrip() + "\n", encoding="utf-8")

        index = ReviewIndex(
            schema_version="phase4.review_index.v1",
            course_id=draft_index["course_id"],
            language=draft_index.get("language", "zh-CN"),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            draft_index_ref=str(self.draft_index_path),
            reviewed_documents_dir=str(self.reviewed_dir),
            combined_markdown_ref=combined_ref,
            counts={
                "total_reviewed": len(entries),
                "by_role": dict(sorted(role_counts.items())),
                "total_findings": sum(entry.finding_count for entry in entries),
                "total_supplements": sum(entry.supplement_count for entry in entries),
                "remaining_open_issues": sum(entry.remaining_issue_count for entry in entries),
            },
            documents=entries,
        )
        self._write_json(self.output_dir / "review_index.json", index.to_dict())
        return index

    def review_one(
        self,
        draft_index: dict[str, Any],
        entry: dict[str, Any],
        draft_doc: dict[str, Any],
        parsed_doc: dict[str, Any] | None,
        all_drafts: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> ReviewedDocument:
        source_context, source_refs, truncated_source = self._source_context(parsed_doc)
        related_context, truncated_related = self._related_context(entry, all_drafts)
        evidence_refs = list(dict.fromkeys([*draft_doc.get("evidence_refs", []), *source_refs]))

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_prompt(
                    source_path=entry["source_path"],
                    document_role=entry["document_role"],
                    draft_markdown=draft_doc.get("markdown", ""),
                    draft_open_issues=draft_doc.get("open_issues", []),
                    source_context=source_context,
                    related_context=related_context,
                    evidence_refs=evidence_refs,
                    truncated_source=truncated_source,
                    truncated_related=truncated_related,
                ),
            },
        ]
        result = self.client.chat_json(messages)
        title = str(result.get("title") or draft_doc.get("title") or Path(entry["source_path"]).stem)
        revised_markdown = clean_visible_markdown(str(result.get("revised_markdown") or draft_doc.get("markdown") or ""))
        if not revised_markdown:
            revised_markdown = f"## {title}\n\n> 审查补充失败：模型返回空正文。"

        warnings = [str(item) for item in result.get("warnings", []) if item]
        if truncated_source:
            warnings.append("Source context was truncated during review.")
        if truncated_related:
            warnings.append("Related draft context was truncated during review.")

        return ReviewedDocument(
            schema_version="phase4.reviewed_document.v1",
            course_id=draft_index["course_id"],
            language=draft_index.get("language", "zh-CN"),
            source={
                "file_id": entry["file_id"],
                "source_path": entry["source_path"],
                "draft_ref": entry["draft_ref"],
                "document_role": entry["document_role"],
            },
            reviewer={
                "name": "llm_review_enrichment_agent",
                "version": "0.1",
                "max_source_chars": self.max_source_chars,
                "max_related_chars": self.max_related_chars,
            },
            title=title,
            revised_markdown=revised_markdown,
            findings=self._findings(result.get("findings", [])),
            supplements=[str(item) for item in result.get("supplements", []) if item],
            remaining_open_issues=[str(item) for item in result.get("remaining_open_issues", []) if item],
            evidence_refs=[str(item) for item in result.get("evidence_refs", []) if item] or evidence_refs[:12],
            warnings=list(dict.fromkeys(warnings)),
        )

    def _load_parsed_index(self, draft_index: dict[str, Any]) -> dict[str, Any] | None:
        raw = draft_index.get("parsed_index_ref")
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = self.draft_index_path.parent / path
        if not path.exists():
            return None
        data = self._read_json(path)
        data["parsed_index_path"] = str(path)
        return data

    @staticmethod
    def _parsed_by_file_id(parsed_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {entry["file_id"]: entry for entry in parsed_index.get("documents", [])}

    def _source_context(self, parsed_doc: dict[str, Any] | None) -> tuple[str, list[str], bool]:
        if not parsed_doc:
            return "", [], False
        parts: list[str] = []
        refs: list[str] = []
        total = 0
        truncated = False
        for chunk in parsed_doc.get("chunks", []):
            text = str(chunk.get("text", "")).strip()
            if not text:
                continue
            chunk_refs = [str(ref) for ref in chunk.get("evidence_refs", [])]
            refs.extend(chunk_refs)
            item = text
            if total + len(item) > self.max_source_chars:
                remaining = self.max_source_chars - total
                if remaining > 500:
                    parts.append(item[:remaining])
                truncated = True
                break
            parts.append(item)
            total += len(item)
        return "\n\n".join(parts), list(dict.fromkeys(refs)), truncated

    def _related_context(
        self,
        current_entry: dict[str, Any],
        all_drafts: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> tuple[str, bool]:
        parts: list[str] = []
        total = 0
        truncated = False
        for entry, draft in all_drafts:
            if entry["file_id"] == current_entry["file_id"]:
                continue
            item = (
                f"## {draft.get('title') or entry['source_path']}\n"
                f"来源文件：{entry['source_path']}\n"
                f"类型：{entry['document_role']}\n"
                f"{str(draft.get('markdown', '')).strip()}\n"
            )
            if total + len(item) > self.max_related_chars:
                remaining = self.max_related_chars - total
                if remaining > 500:
                    parts.append(item[:remaining])
                truncated = True
                break
            parts.append(item)
            total += len(item)
        return "\n\n".join(parts), truncated

    @staticmethod
    def _findings(raw_findings: Any) -> list[ReviewFinding]:
        findings: list[ReviewFinding] = []
        if not isinstance(raw_findings, list):
            return findings
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            findings.append(
                ReviewFinding(
                    severity=str(item.get("severity", "low")),
                    issue=str(item.get("issue", "")),
                    action=str(item.get("action", "")),
                    evidence_refs=[str(ref) for ref in item.get("evidence_refs", []) if ref],
                )
            )
        return findings

    @staticmethod
    def _safe_review_name(entry: dict[str, Any]) -> str:
        digest = entry["file_id"].replace("sha256:", "")[:16]
        stem = Path(entry["source_path"]).stem
        safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem).strip("_")
        return f"{safe_stem[:60] or 'review'}__{digest}"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
