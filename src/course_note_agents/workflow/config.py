"""Configuration loading for the full course-note workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib


STAGES = ("ingest", "parse", "draft", "review", "textbook", "polish", "layout")


@dataclass(frozen=True)
class WorkflowConfig:
    config_path: Path
    base_dir: Path
    raw: dict[str, Any]

    @property
    def course_id(self) -> str:
        return str(self.raw.get("course", {}).get("course_id") or "course").strip()

    @property
    def run_prefix(self) -> str:
        return str(self.raw.get("course", {}).get("run_prefix") or self.course_id).strip()

    @property
    def language(self) -> str:
        return str(self.raw.get("course", {}).get("language") or "zh-CN").strip()

    @property
    def materials_dir(self) -> Path:
        return self.resolve_path(str(self.raw.get("course", {}).get("materials_dir") or "materials"))

    @property
    def runs_dir(self) -> Path:
        return self.resolve_path(str(self.raw.get("paths", {}).get("runs_dir") or "runs"))

    @property
    def dry_run(self) -> bool:
        return bool(self.raw.get("workflow", {}).get("dry_run", False))

    @property
    def selected_stages(self) -> list[str]:
        workflow = self.raw.get("workflow", {})
        start_at = str(workflow.get("start_at") or "ingest")
        stop_after = str(workflow.get("stop_after") or "layout")
        if start_at not in STAGES:
            raise ValueError(f"Unknown start_at stage: {start_at}")
        if stop_after not in STAGES:
            raise ValueError(f"Unknown stop_after stage: {stop_after}")
        start_index = STAGES.index(start_at)
        stop_index = STAGES.index(stop_after)
        if start_index > stop_index:
            raise ValueError("workflow.start_at must not come after workflow.stop_after.")
        skipped = {str(item) for item in workflow.get("skip_stages", [])}
        unknown = skipped - set(STAGES)
        if unknown:
            raise ValueError(f"Unknown skip_stages values: {', '.join(sorted(unknown))}")
        return [stage for stage in STAGES[start_index : stop_index + 1] if stage not in skipped]

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    def stage_dir(self, stage: str) -> Path:
        section = self.section(stage)
        explicit = str(section.get("output_dir") or "").strip()
        if explicit:
            return self.resolve_path(explicit)
        suffixes = {
            "parse": "parsed",
            "polish": "polished",
            "layout": "book_pdf",
        }
        suffix = suffixes.get(stage, stage)
        return self.runs_dir / self.run_prefix / suffix

    def resolve_path(self, value: str) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return (self.base_dir / path).resolve()


def load_config(path: str | Path) -> WorkflowConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file does not exist: {config_path}")
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a TOML table.")
    return WorkflowConfig(config_path=config_path, base_dir=config_path.parent, raw=raw)
