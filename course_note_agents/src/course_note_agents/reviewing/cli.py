"""CLI for review and enrichment."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.model_gateway.openai_compatible import LLMConfig, OpenAICompatibleClient
from course_note_agents.reviewing.agent import ReviewEnrichmentAgent


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DRAFT_INDEX = PROJECT_ROOT / "runs" / "my_course" / "draft" / "draft_index.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-review",
        description="Review, correct, and enrich first-draft course notes.",
    )
    parser.add_argument("--draft-index", default=str(DEFAULT_DRAFT_INDEX))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key-env", default="COURSE_NOTE_LLM_API_KEY")
    parser.add_argument("--llm-timeout-seconds", type=int, default=180)
    parser.add_argument("--max-source-chars", type=int, default=22000)
    parser.add_argument("--max-related-chars", type=int, default=12000)
    parser.add_argument("--limit-documents", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LLMConfig.from_env(
        provider=args.llm_provider,
        model=args.llm_model,
        base_url=args.llm_base_url,
        api_key_env=args.llm_api_key_env,
        timeout_seconds=args.llm_timeout_seconds,
        max_retries=2,
    )
    if config is None:
        raise SystemExit(
            "Review requires LLM configuration. Set COURSE_NOTE_LLM_API_KEY, "
            "COURSE_NOTE_LLM_MODEL, and optionally COURSE_NOTE_LLM_PROVIDER/COURSE_NOTE_LLM_BASE_URL."
        )

    print(f"Review enrichment: provider={config.provider}, model={config.model}")
    agent = ReviewEnrichmentAgent(
        draft_index_path=Path(args.draft_index),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        client=OpenAICompatibleClient(config),
        max_source_chars=args.max_source_chars,
        max_related_chars=args.max_related_chars,
        limit_documents=args.limit_documents,
    )
    index = agent.run()
    print(f"Review index written: {agent.output_dir / 'review_index.json'}")
    print(f"Reviewed documents dir: {agent.reviewed_dir}")
    print(f"Combined reviewed notes: {agent.output_dir / index.combined_markdown_ref}")
    print(f"Reviewed: {index.counts['total_reviewed']}")
    print(f"Findings: {index.counts['total_findings']}")
    print(f"Supplements: {index.counts['total_supplements']}")
    print(f"Remaining issues: {index.counts['remaining_open_issues']}")
    return 0
