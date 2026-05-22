"""CLI for draft note generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.drafting.agent import DraftWritingAgent
from course_note_agents.model_gateway.openai_compatible import LLMConfig, OpenAICompatibleClient


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PARSED_INDEX = PROJECT_ROOT / "runs" / "my_course" / "parsed" / "parsed_index.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-draft",
        description="Generate first-draft course notes from parsed course materials.",
    )
    parser.add_argument(
        "--parsed-index",
        default=str(DEFAULT_PARSED_INDEX),
        help=f"Path to parsed_index.json. Defaults to {DEFAULT_PARSED_INDEX}.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to the parsed index parent.",
    )
    parser.add_argument("--llm-provider", default=None, help="Provider name, e.g. openai, deepseek, compatible.")
    parser.add_argument("--llm-model", default=None, help="Model name. Defaults to COURSE_NOTE_LLM_MODEL.")
    parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL.")
    parser.add_argument(
        "--llm-api-key-env",
        default="COURSE_NOTE_LLM_API_KEY",
        help="Environment variable that contains the API key.",
    )
    parser.add_argument("--llm-timeout-seconds", type=int, default=120)
    parser.add_argument("--max-input-chars", type=int, default=22000)
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
            "Draft generation requires LLM configuration. Set COURSE_NOTE_LLM_API_KEY, "
            "COURSE_NOTE_LLM_MODEL, and optionally COURSE_NOTE_LLM_PROVIDER/COURSE_NOTE_LLM_BASE_URL."
        )

    print(f"Draft writing: provider={config.provider}, model={config.model}")
    agent = DraftWritingAgent(
        parsed_index_path=Path(args.parsed_index),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        client=OpenAICompatibleClient(config),
        max_input_chars=args.max_input_chars,
        limit_documents=args.limit_documents,
    )
    index = agent.run()
    print(f"Draft index written: {agent.output_dir / 'draft_index.json'}")
    print(f"Draft documents dir: {agent.drafts_dir}")
    print(f"Combined draft: {agent.output_dir / index.combined_markdown_ref}")
    print(f"Drafts: {index.counts['total_drafts']}")
    return 0
