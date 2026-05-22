"""File discovery and fingerprinting."""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".ppt",
    ".pptx",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".markdown",
    ".tex",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".csv",
    ".xls",
    ".xlsx",
}

GENERATED_OR_NON_MATERIAL_EXTENSIONS = {
    ".aux",
    ".bbl",
    ".bcf",
    ".blg",
    ".fdb_latexmk",
    ".fls",
    ".log",
    ".out",
    ".pid",
    ".pyc",
    ".synctex.gz",
    ".toc",
}

EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def logical_suffix(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".synctex.gz"):
        return ".synctex.gz"
    return path.suffix.lower()


def should_skip_path(path: Path, include_hidden: bool = False) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIR_NAMES:
        return True
    if not include_hidden and any(part.startswith(".") for part in path.parts):
        return True
    return False


def is_supported_material(path: Path, include_unsupported: bool = False) -> bool:
    suffix = logical_suffix(path)
    if suffix in GENERATED_OR_NON_MATERIAL_EXTENSIONS:
        return False
    return include_unsupported or suffix in SUPPORTED_EXTENSIONS


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def guess_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type:
        return mime_type
    suffix = logical_suffix(path)
    if suffix == ".pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def iso_modified_time(path: Path) -> str:
    stat = path.stat()
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

