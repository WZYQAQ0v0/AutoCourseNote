"""CLI for textbook writing."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.model_gateway.openai_compatible import LLMConfig, OpenAICompatibleClient
from course_note_agents.textbook.agent import TextbookWritingAgent


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REVIEW_INDEX = PROJECT_ROOT / "runs" / "my_course" / "review" / "review_index.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-textbook",
        description="Write a complete textbook-style note set from reviewed notes.",
    )
    parser.add_argument("--review-index", default=str(DEFAULT_REVIEW_INDEX))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key-env", default="COURSE_NOTE_LLM_API_KEY")
    parser.add_argument("--llm-timeout-seconds", type=int, default=240)
    parser.add_argument("--max-outline-context-chars", type=int, default=45000)
    parser.add_argument("--max-chapter-context-chars", type=int, default=36000)
    parser.add_argument("--max-self-check-chars", type=int, default=60000)
    parser.add_argument("--self-check-iterations", type=int, default=2)
    parser.add_argument("--max-self-check-iterations", type=int, default=4)
    parser.add_argument("--limit-chapters", type=int, default=None)
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
            "Textbook writing requires LLM configuration. Set COURSE_NOTE_LLM_API_KEY, "
            "COURSE_NOTE_LLM_MODEL, and optionally COURSE_NOTE_LLM_PROVIDER/COURSE_NOTE_LLM_BASE_URL."
        )

    print(f"Textbook writing: provider={config.provider}, model={config.model}")
    agent = TextbookWritingAgent(
        review_index_path=Path(args.review_index),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        client=OpenAICompatibleClient(config),
        max_outline_context_chars=args.max_outline_context_chars,
        max_chapter_context_chars=args.max_chapter_context_chars,
        max_self_check_chars=args.max_self_check_chars,
        self_check_iterations=args.self_check_iterations,
        max_self_check_iterations=args.max_self_check_iterations,
        limit_chapters=args.limit_chapters,
    )
    index = agent.run()
    print(f"Textbook index written: {agent.output_dir / 'textbook_index.json'}")
    print(f"Textbook markdown: {agent.output_dir / index.textbook_markdown_ref}")
    print(f"Outline: {agent.output_dir / index.outline_ref}")
    print(f"Chapters: {len(index.chapters)}")
    print(f"Self-check iterations: {len(index.self_checks)}")
    return 0
