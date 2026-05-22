"""CLI for the phase-2 content parsing agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.model_gateway.openai_compatible import LLMConfig, OpenAICompatibleClient
from course_note_agents.parsing.agent import ContentParsingAgent
from course_note_agents.parsing.llm_refiner import build_refiner


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = PROJECT_ROOT / "runs" / "my_course" / "ingest" / "manifest.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-parse",
        description="Parse files listed in a phase-1 manifest into structured text documents.",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help=f"Path to phase-1 manifest.json. Defaults to {DEFAULT_MANIFEST}.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Run output directory. Defaults to the manifest parent directory.",
    )
    parser.add_argument(
        "--max-chunk-chars",
        type=int,
        default=2400,
        help="Maximum characters per parsed chunk for downstream agents.",
    )
    parser.add_argument(
        "--limit-documents",
        type=int,
        default=None,
        help="Parse only the first N documents from the manifest. Useful for LLM smoke tests.",
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        help="Parse only the first N pages per document. Useful for LLM smoke tests.",
    )
    parser.add_argument(
        "--include-roles",
        default=None,
        help="Comma-separated document roles to include, e.g. lecture_slides,assignment.",
    )
    parser.add_argument(
        "--exclude-roles",
        default=None,
        help="Comma-separated document roles to exclude, e.g. past_exam,solution.",
    )
    parser.add_argument(
        "--llm-mode",
        choices=["auto", "off", "require"],
        default="auto",
        help="Use LLM cleanup: auto uses it when env config is complete; require errors if unavailable; off disables it.",
    )
    parser.add_argument(
        "--llm-provider",
        default=None,
        help="Provider name for env defaults, e.g. openai, deepseek, compatible.",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="Model name. Defaults to COURSE_NOTE_LLM_MODEL.",
    )
    parser.add_argument(
        "--llm-base-url",
        default=None,
        help="OpenAI-compatible base URL. Defaults to provider/env config.",
    )
    parser.add_argument(
        "--llm-api-key-env",
        default="COURSE_NOTE_LLM_API_KEY",
        help="Environment variable that contains the API key.",
    )
    parser.add_argument(
        "--llm-max-page-chars",
        type=int,
        default=6000,
        help="Maximum characters sent to the LLM per page.",
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=int,
        default=60,
        help="LLM request timeout per page.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    llm_refiner = _build_llm_refiner(args)
    agent = ContentParsingAgent(
        manifest_path=Path(args.manifest),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        max_chunk_chars=args.max_chunk_chars,
        llm_refiner=llm_refiner,
        limit_documents=args.limit_documents,
        limit_pages_per_document=args.limit_pages,
        include_roles=_parse_roles(args.include_roles),
        exclude_roles=_parse_roles(args.exclude_roles) or set(),
    )
    index = agent.run()
    print(f"Parsed index written: {agent.output_dir / 'parsed_index.json'}")
    print(f"Parsed documents dir: {agent.parsed_dir}")
    print(f"Documents: {index.counts['total_documents']}")
    print(f"Needs OCR: {index.counts['needs_ocr_documents']}")
    print("Parse statuses:")
    for status, count in index.counts["by_parse_status"].items():
        print(f"  - {status}: {count}")
    if llm_refiner is not None:
        print("LLM cleanup:")
        print(f"  - attempted pages: {llm_refiner.stats.attempted_pages}")
        print(f"  - refined pages: {llm_refiner.stats.refined_pages}")
        print(f"  - skipped pages: {llm_refiner.stats.skipped_pages}")
        print(f"  - failed pages: {llm_refiner.stats.failed_pages}")
    return 0


def _parse_roles(raw: str | None) -> set[str] | None:
    if raw is None:
        return None
    roles = {item.strip() for item in raw.split(",") if item.strip()}
    return roles or None


def _build_llm_refiner(args) -> object | None:
    if args.llm_mode == "off":
        return None

    config = LLMConfig.from_env(
        provider=args.llm_provider,
        model=args.llm_model,
        base_url=args.llm_base_url,
        api_key_env=args.llm_api_key_env,
        timeout_seconds=args.llm_timeout_seconds,
        max_retries=2,
    )
    if config is None:
        if args.llm_mode == "require":
            raise SystemExit(
                "LLM cleanup was required, but configuration is incomplete. "
                "Set COURSE_NOTE_LLM_API_KEY, COURSE_NOTE_LLM_MODEL, and optionally "
                "COURSE_NOTE_LLM_PROVIDER/COURSE_NOTE_LLM_BASE_URL."
            )
        print("LLM cleanup: disabled because API key/model/base URL is not fully configured.")
        return None

    client = OpenAICompatibleClient(config)
    print(f"LLM cleanup: enabled via provider={config.provider}, model={config.model}")
    return build_refiner(client, max_page_chars=args.llm_max_page_chars)
