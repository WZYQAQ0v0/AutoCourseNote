"""Command line interface for phase-1 local ingestion."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_note_agents.ingestion.indexer import LocalResourceIndexer
from course_note_agents.ingestion.manifest import write_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MATERIALS_DIR = PROJECT_ROOT / "materials"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-note-ingest",
        description="Scan a local course-materials folder and write manifest.json.",
    )
    parser.add_argument(
        "--materials-dir",
        default=str(DEFAULT_MATERIALS_DIR),
        help=f"Folder containing user-provided materials. Defaults to {DEFAULT_MATERIALS_DIR}.",
    )
    parser.add_argument("--output-dir", required=True, help="Folder where manifest.json will be written.")
    parser.add_argument("--course-id", required=True, help="Stable course identifier, e.g. ml_2026_spring.")
    parser.add_argument(
        "--language",
        default="zh-CN",
        help="Primary material language. Defaults to zh-CN for Chinese course materials.",
    )
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden files and folders.")
    parser.add_argument(
        "--include-unsupported",
        action="store_true",
        help="Index unsupported extensions instead of skipping them.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON instead of pretty-printed JSON.",
    )
    parser.add_argument(
        "--max-preview-chars",
        type=int,
        default=8000,
        help="Maximum preview text characters used for lightweight classification.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    indexer = LocalResourceIndexer(
        materials_dir=Path(args.materials_dir),
        output_dir=Path(args.output_dir),
        course_id=args.course_id,
        language=args.language,
        include_hidden=args.include_hidden,
        include_unsupported=args.include_unsupported,
        max_preview_chars=args.max_preview_chars,
    )
    manifest = indexer.build_manifest()
    manifest_path = write_manifest(manifest, args.output_dir, pretty=not args.compact)

    counts = manifest.counts
    print(f"Manifest written: {manifest_path}")
    print(f"Indexed files: {counts['total_files']}")
    print(f"Duplicates by sha256: {counts['duplicate_files_by_sha256']}")
    print("Roles:")
    for role, count in counts["by_role"].items():
        print(f"  - {role}: {count}")
    if counts["skipped"]:
        print("Skipped:")
        for reason, count in counts["skipped"].items():
            print(f"  - {reason}: {count}")
    return 0
