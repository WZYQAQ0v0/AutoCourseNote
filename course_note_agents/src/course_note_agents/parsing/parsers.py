"""Concrete parsers used by the phase-2 content parsing agent."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from course_note_agents.ingestion.fingerprint import logical_suffix
from course_note_agents.parsing.models import ParsedBlock, ParsedPage
from course_note_agents.parsing.text_utils import (
    clean_extracted_text,
    decode_best_effort,
    normalize_text,
    strip_html,
)


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".tex", ".csv"}
HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif"}


def parse_file_pages(file_entry: dict, language: str) -> tuple[list[ParsedPage], dict, list[str]]:
    path = Path(file_entry["absolute_path"])
    suffix = logical_suffix(path)
    document_role = file_entry.get("document_role", "miscellaneous")
    secondary_roles = file_entry.get("secondary_roles", [])

    if suffix == ".pdf":
        return parse_pdf(path, file_entry, language)
    if suffix in TEXT_EXTENSIONS:
        return parse_text_file(path, file_entry)
    if suffix in HTML_EXTENSIONS:
        return parse_html_file(path, file_entry)
    if suffix == ".docx":
        return parse_docx(path, file_entry)
    if suffix == ".pptx":
        return parse_pptx(path, file_entry)
    if suffix in IMAGE_EXTENSIONS:
        return parse_image(path, file_entry)

    warning = f"No parser implemented for extension {suffix}; emitted placeholder document."
    page = ParsedPage(
        page_number=1,
        text="",
        blocks=[],
        needs_ocr=bool(file_entry.get("needs_ocr")),
        warnings=[warning],
    )
    parser_info = {"name": "placeholder_parser", "version": "0.1", "strategy": "placeholder"}
    return [page], parser_info, [warning]


def parse_pdf(path: Path, file_entry: dict, language: str) -> tuple[list[ParsedPage], dict, list[str]]:
    warnings: list[str] = []
    try:
        import fitz  # type: ignore
    except Exception as exc:
        warning = f"PyMuPDF is not installed or failed to import: {exc}"
        page = ParsedPage(
            page_number=1,
            text="",
            blocks=[],
            needs_ocr=True,
            warnings=[warning],
        )
        return [page], {"name": "pdf_placeholder_parser", "version": "0.1"}, [warning]

    pages: list[ParsedPage] = []
    try:
        with fitz.open(path) as doc:
            for page_index, page in enumerate(doc, start=1):
                raw_text = page.get_text("text", sort=True) or ""
                text = clean_extracted_text(raw_text)
                blocks = _single_text_block(file_entry, page_index, text, source="pymupdf_page_text")
                needs_ocr = not bool(raw_text.strip())
                page_warnings = ["No extractable text found; OCR required."] if needs_ocr else []
                pages.append(
                    ParsedPage(
                        page_number=page_index,
                        text=text,
                        blocks=blocks,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        needs_ocr=needs_ocr,
                        warnings=page_warnings,
                    )
                )
    except Exception as exc:
        warning = f"PDF parsing failed: {exc}"
        page = ParsedPage(page_number=1, text="", blocks=[], needs_ocr=True, warnings=[warning])
        return [page], {"name": "pymupdf", "version": getattr(fitz, "version", "unknown")}, [warning]

    parser_info = {
        "name": "pymupdf",
        "version": str(getattr(fitz, "version", "unknown")),
        "strategy": "clean_page_text",
        "language": language,
    }
    return pages, parser_info, warnings


def parse_text_file(path: Path, file_entry: dict) -> tuple[list[ParsedPage], dict, list[str]]:
    text = clean_extracted_text(decode_best_effort(path.read_bytes()))
    page = _page_from_text(text, file_entry, parser_page_number=1)
    return [page], {"name": "plain_text_parser", "version": "0.1"}, []


def parse_html_file(path: Path, file_entry: dict) -> tuple[list[ParsedPage], dict, list[str]]:
    text = strip_html(decode_best_effort(path.read_bytes()))
    page = _page_from_text(text, file_entry, parser_page_number=1)
    return [page], {"name": "html_text_parser", "version": "0.1"}, []


def parse_docx(path: Path, file_entry: dict) -> tuple[list[ParsedPage], dict, list[str]]:
    warnings: list[str] = []
    texts: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"):
                if name in archive.namelist():
                    texts.append(_extract_text_from_xml(archive.read(name)))
    except Exception as exc:
        warnings.append(f"DOCX parsing failed: {exc}")
    text = clean_extracted_text("\n".join(texts))
    page = _page_from_text(text, file_entry, parser_page_number=1)
    page.warnings.extend(warnings)
    return [page], {"name": "docx_zip_xml_parser", "version": "0.1"}, warnings


def parse_pptx(path: Path, file_entry: dict) -> tuple[list[ParsedPage], dict, list[str]]:
    warnings: list[str] = []
    pages: list[ParsedPage] = []
    try:
        with zipfile.ZipFile(path) as archive:
            slide_names = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
            for page_number, name in enumerate(sorted(slide_names, key=_natural_key), start=1):
                text = clean_extracted_text(_extract_text_from_xml(archive.read(name)))
                pages.append(_page_from_text(text, file_entry, parser_page_number=page_number))
    except Exception as exc:
        warnings.append(f"PPTX parsing failed: {exc}")

    if not pages:
        pages.append(ParsedPage(page_number=1, text="", blocks=[], warnings=list(warnings)))
    return pages, {"name": "pptx_zip_xml_parser", "version": "0.1"}, warnings


def parse_image(path: Path, file_entry: dict) -> tuple[list[ParsedPage], dict, list[str]]:
    block = ParsedBlock(
        block_id=f"{file_entry['file_id']}:page:1:block:0001",
        type="image",
        text="",
        page_number=1,
        confidence=1.0,
        metadata={
            "source_path": str(path),
            "ocr_status": "pending",
            "reason": "Image content requires OCR before text extraction.",
        },
    )
    warning = "Image file requires OCR; no text extracted in this phase."
    page = ParsedPage(page_number=1, text="", blocks=[block], needs_ocr=True, warnings=[warning])
    return [page], {"name": "image_placeholder_parser", "version": "0.1"}, [warning]


def _page_from_text(text: str, file_entry: dict, parser_page_number: int) -> ParsedPage:
    text = clean_extracted_text(text)
    blocks = _single_text_block(file_entry, parser_page_number, text, source="clean_text_parser")
    return ParsedPage(page_number=parser_page_number, text=text, blocks=blocks, needs_ocr=False)


def _single_text_block(file_entry: dict, page_number: int, text: str, source: str) -> list[ParsedBlock]:
    if not text.strip():
        return []
    return [
        ParsedBlock(
            block_id=f"{file_entry['file_id']}:page:{page_number}:text",
            type="paragraph",
            text=text,
            page_number=page_number,
            bbox=None,
            confidence=0.9,
            metadata={"source": source, "granularity": "page_text"},
        )
    ]


def _extract_text_from_xml(raw: bytes) -> str:
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return normalize_text(decode_best_effort(raw))
    texts: list[str] = []
    for node in root.iter():
        if node.text and node.text.strip():
            texts.append(node.text.strip())
    return "\n".join(texts)


def _natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]
