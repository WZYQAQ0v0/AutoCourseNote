"""Manifest serialization helpers."""

from __future__ import annotations

import json
from pathlib import Path

from course_note_agents.ingestion.models import Manifest


def write_manifest(manifest: Manifest, output_dir: Path | str, pretty: bool = True) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "manifest.json"
    with target.open("w", encoding="utf-8") as stream:
        json.dump(
            manifest.to_dict(),
            stream,
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=False,
        )
        stream.write("\n")
    return target

