"""CLI for running the full workflow from a config file."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.workflow.config import load_config
from course_note_agents.workflow.runner import WorkflowRunner


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "course_config.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-run",
        description="Run the course-note pipeline from course_config.toml.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help=f"Path to TOML config file. Defaults to {DEFAULT_CONFIG}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    return WorkflowRunner(config, dry_run=True if args.dry_run else None).run()


if __name__ == "__main__":
    raise SystemExit(main())
