"""CLI for book layout and PDF generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.layout.agent import BookLayoutAgent


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_INDEX = PROJECT_ROOT / "runs" / "my_course" / "polished" / "polished_index.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-layout",
        description="Render a polished textbook Markdown file to LaTeX and PDF.",
    )
    parser.add_argument("--input-index", default=str(DEFAULT_INPUT_INDEX))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--xelatex-path", default=None)
    parser.add_argument("--cjk-main-font", default="NotoSerifSC-VF.ttf")
    parser.add_argument("--cjk-sans-font", default="NotoSansSC-VF.ttf")
    parser.add_argument("--compile-timeout-seconds", type=int, default=180)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    agent = BookLayoutAgent(
        input_index_path=Path(args.input_index),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        compile_pdf=not args.no_compile,
        xelatex_path=args.xelatex_path,
        cjk_main_font=args.cjk_main_font,
        cjk_sans_font=args.cjk_sans_font,
        compile_timeout_seconds=args.compile_timeout_seconds,
    )
    index = agent.run()
    print(f"Layout index written: {agent.output_dir / 'layout_index.json'}")
    print(f"LaTeX source: {agent.output_dir / index.tex_ref}")
    if index.pdf_ref:
        print(f"PDF: {agent.output_dir / index.pdf_ref}")
    else:
        print(f"PDF status: {index.compile_status}")
    return 0
