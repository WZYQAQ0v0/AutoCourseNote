"""Lightweight content probing before full document parsing."""

from __future__ import annotations

import re
import zipfile
from html import unescape
from pathlib import Path
from xml.etree import ElementTree

from course_note_agents.ingestion.fingerprint import logical_suffix
from course_note_agents.ingestion.models import ContentProbe


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".tex", ".csv", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif"}


def probe_file(path: Path, max_preview_chars: int = 8000) -> ContentProbe:
    suffix = logical_suffix(path)
    if suffix in TEXT_EXTENSIONS:
        return _probe_text_file(path, max_preview_chars)
    if suffix == ".docx":
        return _probe_docx(path, max_preview_chars)
    if suffix == ".pptx":
        return _probe_pptx(path, max_preview_chars)
    if suffix == ".pdf":
        return _probe_pdf(path, max_preview_chars)
    if suffix in IMAGE_EXTENSIONS:
        return ContentProbe(
            needs_ocr=True,
            probe_method="image_metadata",
            warnings=["Image files require OCR in the parsing phase."],
        )
    if suffix in {".doc", ".ppt", ".xls", ".xlsx"}:
        return ContentProbe(
            probe_method="binary_office_metadata",
            warnings=["Legacy or spreadsheet Office formats need conversion in the parsing phase."],
        )
    return ContentProbe(warnings=["Unsupported or unknown extension."])


def _probe_text_file(path: Path, max_preview_chars: int) -> ContentProbe:
    with path.open("rb") as stream:
        raw = stream.read(max_preview_chars * 6)
    text = _decode_best_effort(raw)
    if path.suffix.lower() in {".html", ".htm"}:
        text = _strip_xmlish_tags(text)
    return ContentProbe(
        text_preview=text[:max_preview_chars],
        word_count=_rough_word_count(text),
        probe_method="text",
    )


def _probe_docx(path: Path, max_preview_chars: int) -> ContentProbe:
    warnings: list[str] = []
    texts: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            for name in names:
                if name in {
                    "word/document.xml",
                    "word/footnotes.xml",
                    "word/endnotes.xml",
                    "word/comments.xml",
                }:
                    texts.append(_extract_text_from_xml(archive.read(name)))
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        warnings.append(f"Could not inspect DOCX package: {exc}")

    text = "\n".join(texts)
    return ContentProbe(
        text_preview=text[:max_preview_chars],
        word_count=_rough_word_count(text),
        probe_method="docx_zip_xml",
        warnings=warnings,
    )


def _probe_pptx(path: Path, max_preview_chars: int) -> ContentProbe:
    warnings: list[str] = []
    texts: list[str] = []
    slide_count = 0
    try:
        with zipfile.ZipFile(path) as archive:
            slide_names = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
            slide_count = len(slide_names)
            for name in sorted(slide_names)[:12]:
                texts.append(_extract_text_from_xml(archive.read(name)))
            note_names = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml")
            ]
            for name in sorted(note_names)[:4]:
                texts.append(_extract_text_from_xml(archive.read(name)))
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        warnings.append(f"Could not inspect PPTX package: {exc}")

    text = "\n".join(texts)
    return ContentProbe(
        text_preview=text[:max_preview_chars],
        slide_count=slide_count or None,
        word_count=_rough_word_count(text),
        probe_method="pptx_zip_xml",
        warnings=warnings,
        structural_signals={"slide_count": slide_count},
    )


def _probe_pdf(path: Path, max_preview_chars: int) -> ContentProbe:
    warnings: list[str] = []
    page_count: int | None = None
    text = ""

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:3])
        return ContentProbe(
            text_preview=text[:max_preview_chars],
            page_count=page_count,
            word_count=_rough_word_count(text),
            needs_ocr=not bool(text.strip()),
            probe_method="pypdf",
            warnings=warnings,
        )
    except Exception as exc:  # Optional dependency or malformed PDFs.
        warnings.append(f"pypdf unavailable or failed: {exc}")

    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:3])
        return ContentProbe(
            text_preview=text[:max_preview_chars],
            page_count=page_count,
            word_count=_rough_word_count(text),
            needs_ocr=not bool(text.strip()),
            probe_method="pypdf2",
            warnings=warnings,
        )
    except Exception as exc:
        warnings.append(f"PyPDF2 unavailable or failed: {exc}")

    raw = path.read_bytes()[: 2 * 1024 * 1024]
    latin = raw.decode("latin-1", errors="ignore")
    page_count = max(latin.count("/Type /Page"), latin.count("/Type/Page")) or None
    text = _strip_pdf_noise(latin)
    return ContentProbe(
        text_preview=text[:max_preview_chars],
        page_count=page_count,
        word_count=_rough_word_count(text),
        needs_ocr=not bool(text.strip()),
        probe_method="pdf_binary_sniff",
        warnings=warnings,
    )


def _extract_text_from_xml(raw: bytes) -> str:
    text_items: list[str] = []
    try:
        root = ElementTree.fromstring(raw)
        for node in root.iter():
            if node.text and node.text.strip():
                text_items.append(node.text.strip())
    except ElementTree.ParseError:
        text_items.append(_strip_xmlish_tags(_decode_best_effort(raw)))
    return "\n".join(text_items)


def _strip_xmlish_tags(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_space(unescape(text))


def _strip_pdf_noise(text: str) -> str:
    candidates = re.findall(r"\(([^()]{3,120})\)", text)
    if candidates:
        return _normalize_space(" ".join(candidates[:200]))
    printable = re.sub(r"[^\x09\x0a\x0d\x20-\x7E\u4e00-\u9fff]+", " ", text)
    return _normalize_space(printable[:12000])


def _decode_best_effort(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _normalize_space(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _rough_word_count(text: str) -> int:
    latin_words = re.findall(r"[A-Za-z0-9_]+", text)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    return len(latin_words) + len(cjk_chars)
