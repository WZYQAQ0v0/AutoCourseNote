"""CLI for chapter-level textbook polishing."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.model_gateway.openai_compatible import LLMConfig, OpenAICompatibleClient
from course_note_agents.polishing.agent import TextbookPolishingAgent


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEXTBOOK_INDEX = PROJECT_ROOT / "runs" / "my_course" / "textbook" / "textbook_index.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-polish",
        description="Polish generated textbook chapters using self-check reports.",
    )
    parser.add_argument("--textbook-index", default=str(DEFAULT_TEXTBOOK_INDEX))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key-env", default="COURSE_NOTE_LLM_API_KEY")
    parser.add_argument("--llm-timeout-seconds", type=int, default=240)
    parser.add_argument("--max-chapter-chars", type=int, default=36000)
    parser.add_argument("--max-self-check-chars", type=int, default=24000)
    parser.add_argument("--max-global-context-chars", type=int, default=18000)
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
            "Textbook polishing requires LLM configuration. Set COURSE_NOTE_LLM_API_KEY, "
            "COURSE_NOTE_LLM_MODEL, and optionally COURSE_NOTE_LLM_PROVIDER/COURSE_NOTE_LLM_BASE_URL."
        )

    print(f"Textbook polishing: provider={config.provider}, model={config.model}")
    agent = TextbookPolishingAgent(
        textbook_index_path=Path(args.textbook_index),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        client=OpenAICompatibleClient(config),
        max_chapter_chars=args.max_chapter_chars,
        max_self_check_chars=args.max_self_check_chars,
        max_global_context_chars=args.max_global_context_chars,
        limit_chapters=args.limit_chapters,
    )
    index = agent.run()
    print(f"Polished index written: {agent.output_dir / 'polished_index.json'}")
    print(f"Polished textbook: {agent.output_dir / index.polished_markdown_ref}")
    print(f"Chapters: {len(index.chapters)}")
    print(f"Applied fixes: {index.counts['applied_fixes']}")
    print(f"Remaining issues: {index.counts['remaining_issues']}")
    return 0
