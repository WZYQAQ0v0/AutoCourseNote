"""Draft note writing agent."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from course_note_agents.drafting.models import DraftDocument, DraftIndex, DraftIndexEntry
from course_note_agents.drafting.prompts import SYSTEM_PROMPT, user_prompt
from course_note_agents.markdown_cleanup import clean_visible_markdown


class JSONChatClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        ...


class DraftWritingAgent:
    def __init__(
        self,
        parsed_index_path: Path | str,
        output_dir: Path | str | None,
        client: JSONChatClient,
        max_input_chars: int = 22000,
        limit_documents: int | None = None,
    ) -> None:
        self.parsed_index_path = Path(parsed_index_path).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else self.parsed_index_path.parent.resolve()
        self.drafts_dir = self.output_dir / "draft_notes"
        self.client = client
        self.max_input_chars = max_input_chars
        self.limit_documents = limit_documents

    def run(self) -> DraftIndex:
        parsed_index = self._read_json(self.parsed_index_path)
        parsed_base = self.parsed_index_path.parent
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

        documents = parsed_index["documents"]
        if self.limit_documents is not None:
            documents = documents[: self.limit_documents]

        entries: list[DraftIndexEntry] = []
        combined_parts: list[str] = []
        role_counts: Counter[str] = Counter()

        for entry in documents:
            parsed_doc = self._read_json(parsed_base / entry["parsed_ref"])
            draft = self.write_one(parsed_index, entry, parsed_doc)
            draft_name = self._safe_draft_name(entry)
            draft_path = self.drafts_dir / f"{draft_name}.json"
            markdown_path = self.drafts_dir / f"{draft_name}.md"
            self._write_json(draft_path, draft.to_dict())
            markdown_path.write_text(draft.markdown.rstrip() + "\n", encoding="utf-8")

            role_counts[entry["document_role"]] += 1
            entries.append(
                DraftIndexEntry(
                    file_id=entry["file_id"],
                    source_path=entry["source_path"],
                    draft_ref=str(draft_path.relative_to(self.output_dir).as_posix()),
                    document_role=entry["document_role"],
                    title=draft.title,
                    key_point_count=len(draft.key_points),
                    evidence_refs=draft.evidence_refs,
                    open_issues=draft.open_issues,
                    warnings=draft.warnings,
                )
            )
            combined_parts.append(f"# {draft.title}\n\n{draft.markdown.strip()}\n")

        combined_ref = "draft_notes/combined_draft.md"
        combined_path = self.output_dir / combined_ref
        combined_path.parent.mkdir(parents=True, exist_ok=True)
        combined_path.write_text("\n\n".join(combined_parts).rstrip() + "\n", encoding="utf-8")

        index = DraftIndex(
            schema_version="phase3.draft_index.v1",
            course_id=parsed_index["course_id"],
            language=parsed_index.get("language", "zh-CN"),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            parsed_index_ref=str(self.parsed_index_path),
            draft_documents_dir=str(self.drafts_dir),
            combined_markdown_ref=combined_ref,
            counts={
                "total_drafts": len(entries),
                "by_role": dict(sorted(role_counts.items())),
            },
            documents=entries,
        )
        self._write_json(self.output_dir / "draft_index.json", index.to_dict())
        return index

    def write_one(self, parsed_index: dict[str, Any], entry: dict[str, Any], parsed_doc: dict[str, Any]) -> DraftDocument:
        text, evidence_refs, truncated = self._material_text(parsed_doc)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_prompt(
                    source_path=entry["source_path"],
                    document_role=entry["document_role"],
                    secondary_roles=entry.get("secondary_roles", []),
                    text=text,
                    evidence_refs=evidence_refs,
                    truncated=truncated,
                ),
            },
        ]
        result = self.client.chat_json(messages)
        title = str(result.get("title") or Path(entry["source_path"]).stem)
        markdown = clean_visible_markdown(str(result.get("markdown") or ""))
        if not markdown:
            markdown = f"## {title}\n\n> 初稿生成失败：模型返回空正文。"

        returned_refs = [str(item) for item in result.get("evidence_refs", []) if item]
        draft_refs = returned_refs or evidence_refs[:8]
        warnings = [str(item) for item in result.get("warnings", []) if item]
        if truncated:
            warnings.append("Input material was truncated before draft generation.")

        return DraftDocument(
            schema_version="phase3.draft_document.v1",
            course_id=parsed_index["course_id"],
            language=parsed_index.get("language", "zh-CN"),
            source={
                "file_id": entry["file_id"],
                "source_path": entry["source_path"],
                "parsed_ref": entry["parsed_ref"],
                "document_role": entry["document_role"],
                "secondary_roles": entry.get("secondary_roles", []),
            },
            writer={
                "name": "llm_draft_writer",
                "version": "0.1",
                "max_input_chars": self.max_input_chars,
            },
            title=title,
            markdown=markdown,
            key_points=[str(item) for item in result.get("key_points", []) if item],
            evidence_refs=draft_refs,
            open_issues=[str(item) for item in result.get("open_issues", []) if item],
            warnings=list(dict.fromkeys(warnings)),
        )

    def _material_text(self, parsed_doc: dict[str, Any]) -> tuple[str, list[str], bool]:
        parts: list[str] = []
        evidence_refs: list[str] = []
        total = 0
        truncated = False

        for chunk in parsed_doc.get("chunks", []):
            text = str(chunk.get("text", "")).strip()
            if not text:
                continue
            refs = [str(ref) for ref in chunk.get("evidence_refs", [])]
            if refs:
                evidence_refs.extend(refs)
            item = text
            if total + len(item) > self.max_input_chars:
                remaining = self.max_input_chars - total
                if remaining > 500:
                    parts.append(item[:remaining])
                truncated = True
                break
            parts.append(item)
            total += len(item)

        if not parts:
            fallback = str(parsed_doc.get("linear_text", ""))
            parts.append(fallback[: self.max_input_chars])
            truncated = len(fallback) > self.max_input_chars
            evidence_refs = [parsed_doc["file"]["file_id"]]

        unique_refs = list(dict.fromkeys(evidence_refs))
        return "\n\n".join(parts), unique_refs, truncated

    @staticmethod
    def _safe_draft_name(entry: dict[str, Any]) -> str:
        digest = entry["file_id"].replace("sha256:", "")[:16]
        stem = Path(entry["source_path"]).stem
        safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem).strip("_")
        return f"{safe_stem[:60] or 'draft'}__{digest}"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
