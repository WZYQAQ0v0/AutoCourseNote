"""Run the course-note pipeline from a TOML config file."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from course_note_agents.drafting.cli import main as draft_main
from course_note_agents.ingestion.cli import main as ingest_main
from course_note_agents.layout.cli import main as layout_main
from course_note_agents.parsing.cli import main as parse_main
from course_note_agents.polishing.cli import main as polish_main
from course_note_agents.reviewing.cli import main as review_main
from course_note_agents.textbook.cli import main as textbook_main
from course_note_agents.workflow.config import WorkflowConfig


StageMain = Callable[[list[str] | None], int]


class WorkflowRunner:
    def __init__(self, config: WorkflowConfig, dry_run: bool | None = None) -> None:
        self.config = config
        self.dry_run = config.dry_run if dry_run is None else dry_run

    def run(self) -> int:
        for stage in self.config.selected_stages:
            argv = self.argv_for_stage(stage)
            print(f"\n=== {stage.upper()} ===")
            print(_format_command(_stage_command(stage), argv))
            if self.dry_run:
                continue
            code = _stage_main(stage)(argv)
            if code:
                return code
        if self.dry_run:
            print("\nDry run finished. No files were changed.")
        else:
            print("\nWorkflow finished.")
            print(f"Markdown: {self.config.stage_dir('polish') / 'polished_textbook.md'}")
            print(f"PDF: {self.config.stage_dir('layout') / 'book.pdf'}")
        return 0

    def argv_for_stage(self, stage: str) -> list[str]:
        builder = getattr(self, f"_argv_{stage}")
        return builder()

    def _argv_ingest(self) -> list[str]:
        section = self.config.section("ingest")
        argv = [
            "--materials-dir",
            str(self.config.materials_dir),
            "--output-dir",
            str(self.config.stage_dir("ingest")),
            "--course-id",
            self.config.course_id,
            "--language",
            self.config.language,
            "--max-preview-chars",
            str(_int(section, "max_preview_chars", 8000)),
        ]
        _flag(argv, "--include-hidden", section.get("include_hidden", False))
        _flag(argv, "--include-unsupported", section.get("include_unsupported", False))
        _flag(argv, "--compact", section.get("compact", False))
        return argv

    def _argv_parse(self) -> list[str]:
        section = self.config.section("parse")
        argv = [
            "--manifest",
            str(self.config.stage_dir("ingest") / "manifest.json"),
            "--output-dir",
            str(self.config.stage_dir("parse")),
            "--max-chunk-chars",
            str(_int(section, "max_chunk_chars", 2600)),
            "--llm-mode",
            str(section.get("llm_mode") or "auto"),
            "--llm-max-page-chars",
            str(_int(section, "llm_max_page_chars", 6000)),
            "--llm-timeout-seconds",
            str(_int(section, "llm_timeout_seconds", 60)),
        ]
        _append_llm_args(argv, self.config)
        _optional_int(argv, "--limit-documents", section.get("limit_documents"))
        _optional_int(argv, "--limit-pages", section.get("limit_pages"))
        _optional_roles(argv, "--include-roles", section.get("include_roles"))
        _optional_roles(argv, "--exclude-roles", section.get("exclude_roles"))
        return argv

    def _argv_draft(self) -> list[str]:
        section = self.config.section("draft")
        argv = [
            "--parsed-index",
            str(self.config.stage_dir("parse") / "parsed_index.json"),
            "--output-dir",
            str(self.config.stage_dir("draft")),
            "--llm-timeout-seconds",
            str(_int(section, "llm_timeout_seconds", 240)),
            "--max-input-chars",
            str(_int(section, "max_input_chars", 26000)),
        ]
        _append_llm_args(argv, self.config)
        _optional_int(argv, "--limit-documents", section.get("limit_documents"))
        return argv

    def _argv_review(self) -> list[str]:
        section = self.config.section("review")
        argv = [
            "--draft-index",
            str(self.config.stage_dir("draft") / "draft_index.json"),
            "--output-dir",
            str(self.config.stage_dir("review")),
            "--llm-timeout-seconds",
            str(_int(section, "llm_timeout_seconds", 240)),
            "--max-source-chars",
            str(_int(section, "max_source_chars", 26000)),
            "--max-related-chars",
            str(_int(section, "max_related_chars", 14000)),
        ]
        _append_llm_args(argv, self.config)
        _optional_int(argv, "--limit-documents", section.get("limit_documents"))
        return argv

    def _argv_textbook(self) -> list[str]:
        section = self.config.section("textbook")
        argv = [
            "--review-index",
            str(self.config.stage_dir("review") / "review_index.json"),
            "--output-dir",
            str(self.config.stage_dir("textbook")),
            "--llm-timeout-seconds",
            str(_int(section, "llm_timeout_seconds", 300)),
            "--max-outline-context-chars",
            str(_int(section, "max_outline_context_chars", 70000)),
            "--max-chapter-context-chars",
            str(_int(section, "max_chapter_context_chars", 80000)),
            "--max-self-check-chars",
            str(_int(section, "max_self_check_chars", 120000)),
            "--self-check-iterations",
            str(_int(section, "self_check_iterations", 2)),
            "--max-self-check-iterations",
            str(_int(section, "max_self_check_iterations", 2)),
        ]
        _append_llm_args(argv, self.config)
        _optional_int(argv, "--limit-chapters", section.get("limit_chapters"))
        return argv

    def _argv_polish(self) -> list[str]:
        section = self.config.section("polish")
        argv = [
            "--textbook-index",
            str(self.config.stage_dir("textbook") / "textbook_index.json"),
            "--output-dir",
            str(self.config.stage_dir("polish")),
            "--llm-timeout-seconds",
            str(_int(section, "llm_timeout_seconds", 300)),
            "--max-chapter-chars",
            str(_int(section, "max_chapter_chars", 36000)),
            "--max-self-check-chars",
            str(_int(section, "max_self_check_chars", 24000)),
            "--max-global-context-chars",
            str(_int(section, "max_global_context_chars", 18000)),
        ]
        _append_llm_args(argv, self.config)
        _optional_int(argv, "--limit-chapters", section.get("limit_chapters"))
        return argv

    def _argv_layout(self) -> list[str]:
        section = self.config.section("layout")
        argv = [
            "--input-index",
            str(self.config.stage_dir("polish") / "polished_index.json"),
            "--output-dir",
            str(self.config.stage_dir("layout")),
            "--cjk-main-font",
            str(section.get("cjk_main_font") or "NotoSerifSC-VF.ttf"),
            "--cjk-sans-font",
            str(section.get("cjk_sans_font") or "NotoSansSC-VF.ttf"),
            "--compile-timeout-seconds",
            str(_int(section, "compile_timeout_seconds", 300)),
        ]
        xelatex_path = str(section.get("xelatex_path") or "").strip()
        if xelatex_path:
            argv.extend(["--xelatex-path", xelatex_path])
        if not bool(section.get("compile_pdf", True)):
            argv.append("--no-compile")
        return argv


def _append_llm_args(argv: list[str], config: WorkflowConfig) -> None:
    llm = config.section("llm")
    mapping = [
        ("provider", "--llm-provider"),
        ("model", "--llm-model"),
        ("base_url", "--llm-base-url"),
        ("api_key_env", "--llm-api-key-env"),
    ]
    for key, flag in mapping:
        value = str(llm.get(key) or "").strip()
        if value:
            argv.extend([flag, value])


def _optional_int(argv: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    parsed = int(value)
    if parsed > 0:
        argv.extend([flag, str(parsed)])


def _optional_roles(argv: list[str], flag: str, value: Any) -> None:
    if not value:
        return
    if isinstance(value, str):
        raw = value.strip()
    else:
        raw = ",".join(str(item).strip() for item in value if str(item).strip())
    if raw:
        argv.extend([flag, raw])


def _flag(argv: list[str], flag: str, enabled: Any) -> None:
    if bool(enabled):
        argv.append(flag)


def _int(section: dict[str, Any], key: str, default: int) -> int:
    value = section.get(key, default)
    return int(default if value is None else value)


def _stage_main(stage: str) -> StageMain:
    return {
        "ingest": ingest_main,
        "parse": parse_main,
        "draft": draft_main,
        "review": review_main,
        "textbook": textbook_main,
        "polish": polish_main,
        "layout": layout_main,
    }[stage]


def _stage_command(stage: str) -> str:
    return {
        "ingest": "course-note-ingest",
        "parse": "course-note-parse",
        "draft": "course-note-draft",
        "review": "course-note-review",
        "textbook": "course-note-textbook",
        "polish": "course-note-polish",
        "layout": "course-note-layout",
    }[stage]


def _format_command(command: str, argv: list[str]) -> str:
    return " ".join([command, *(_quote(arg) for arg in argv)])


def _quote(value: str) -> str:
    if not value or any(ch.isspace() for ch in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value
