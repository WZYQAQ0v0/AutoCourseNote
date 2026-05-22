"""Book layout and PDF generation agent."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_note_agents.layout.markdown_latex import MarkdownLatexRenderer
from course_note_agents.layout.models import LayoutIndex


class BookLayoutAgent:
    def __init__(
        self,
        input_index_path: Path | str,
        output_dir: Path | str | None,
        compile_pdf: bool = True,
        xelatex_path: str | None = None,
        cjk_main_font: str = "NotoSerifSC-VF.ttf",
        cjk_sans_font: str = "NotoSansSC-VF.ttf",
        compile_timeout_seconds: int = 180,
    ) -> None:
        self.input_index_path = Path(input_index_path).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else self.input_index_path.parent.resolve()
        self.compile_pdf = compile_pdf
        self.xelatex_path = xelatex_path or shutil.which("xelatex")
        self.cjk_main_font = cjk_main_font
        self.cjk_sans_font = cjk_sans_font
        self.compile_timeout_seconds = compile_timeout_seconds

    def run(self) -> LayoutIndex:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        source_index = self._read_json(self.input_index_path)
        source_base = self.input_index_path.parent
        markdown_ref = self._markdown_ref(source_index)
        markdown_path = source_base / markdown_ref
        markdown = markdown_path.read_text(encoding="utf-8")

        renderer = MarkdownLatexRenderer(
            cjk_main_font=self.cjk_main_font,
            cjk_sans_font=self.cjk_sans_font,
        )
        title = self._title_from_markdown(markdown)
        tex = renderer.render_document(markdown, title=title)
        tex_ref = "book.tex"
        tex_path = self.output_dir / tex_ref
        tex_path.write_text(tex, encoding="utf-8")

        compile_status = "skipped"
        compile_log_ref: str | None = None
        pdf_ref: str | None = None
        if self.compile_pdf:
            compile_status, compile_log_ref, pdf_ref = self._compile(tex_path)

        index = LayoutIndex(
            schema_version="phase7.layout_index.v1",
            course_id=source_index["course_id"],
            language=source_index.get("language", "zh-CN"),
            generated_at=datetime.now(tz=timezone.utc).isoformat(),
            source_index_ref=str(self.input_index_path),
            source_markdown_ref=str(markdown_path),
            tex_ref=tex_ref,
            pdf_ref=pdf_ref,
            compile_status=compile_status,
            compile_log_ref=compile_log_ref,
            counts={
                "chapters": renderer.stats.chapters,
                "sections": renderer.stats.sections,
                "tables": renderer.stats.tables,
                "code_blocks": renderer.stats.code_blocks,
                "source_markdown_chars": len(markdown),
            },
        )
        self._write_json(self.output_dir / "layout_index.json", index.to_dict())
        return index

    def _compile(self, tex_path: Path) -> tuple[str, str | None, str | None]:
        if not self.xelatex_path:
            log_ref = "compile.log"
            (self.output_dir / log_ref).write_text("xelatex was not found on PATH.\n", encoding="utf-8")
            return "missing_xelatex", log_ref, None

        logs: list[str] = []
        command = [
            self.xelatex_path,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-output-directory",
            str(self.output_dir),
            str(tex_path),
        ]
        status = "success"
        for run_index in range(1, 3):
            completed = subprocess.run(
                command,
                cwd=self.output_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.compile_timeout_seconds,
            )
            logs.append(f"===== xelatex run {run_index} =====\n")
            logs.append(completed.stdout)
            logs.append(completed.stderr)
            if completed.returncode != 0:
                status = "failed"
                break
        log_ref = "compile.log"
        (self.output_dir / log_ref).write_text("\n".join(logs), encoding="utf-8")
        pdf_path = self.output_dir / "book.pdf"
        return status, log_ref, "book.pdf" if pdf_path.exists() and status == "success" else None

    @staticmethod
    def _markdown_ref(source_index: dict[str, Any]) -> str:
        schema = source_index.get("schema_version")
        if schema == "phase6.polished_textbook_index.v1":
            return str(source_index["polished_markdown_ref"])
        if schema == "phase5.textbook_index.v1":
            return str(source_index["textbook_markdown_ref"])
        raise ValueError(f"Unsupported source index schema: {schema}")

    @staticmethod
    def _title_from_markdown(markdown: str) -> str:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return "课程复习教材"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
