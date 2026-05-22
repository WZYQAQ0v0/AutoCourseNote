"""Text normalization and lightweight segmentation helpers."""

from __future__ import annotations

import re
from html import unescape


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_extracted_text(text: str) -> str:
    """Clean PDF/Office extracted text into readable page-level prose.

    The parser's job is to provide useful text to downstream agents, not to
    perfectly preserve page geometry. This removes common slide/PDF extraction
    noise such as orphan bullet glyphs, standalone punctuation, and one-letter
    pseudo-bullets produced by symbol fonts.
    """
    text = normalize_text(text)
    if not text:
        return ""

    cleaned_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = _clean_extracted_line(raw_line)
        if not line:
            continue
        cleaned_lines.append(line)

    return _join_reading_lines(cleaned_lines)


def strip_html(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_extracted_text(unescape(text))


def decode_best_effort(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def make_chunks_from_blocks(
    file_id: str,
    blocks: list[dict],
    max_chars: int = 2400,
) -> list[dict]:
    chunks: list[dict] = []
    current_text: list[str] = []
    current_blocks: list[str] = []
    page_start: int | None = None
    page_end: int | None = None

    def flush() -> None:
        nonlocal current_text, current_blocks, page_start, page_end
        text = normalize_text("\n\n".join(current_text))
        if not text:
            current_text = []
            current_blocks = []
            page_start = None
            page_end = None
            return
        chunk_index = len(chunks) + 1
        evidence_refs = [f"{file_id}#page={page_start}"] if page_start is not None else [file_id]
        chunks.append(
            {
                "chunk_id": f"{file_id}:chunk:{chunk_index:04d}",
                "type": "content",
                "text": text,
                "page_start": page_start,
                "page_end": page_end,
                "block_ids": list(current_blocks),
                "evidence_refs": evidence_refs,
                "metadata": {},
            }
        )
        current_text = []
        current_blocks = []
        page_start = None
        page_end = None

    for block in blocks:
        text = block.get("text", "").strip()
        if not text:
            continue
        page = block.get("page_number")
        if page_start is None:
            page_start = page
        page_end = page
        if sum(len(item) for item in current_text) + len(text) > max_chars:
            flush()
            page_start = page
            page_end = page
        current_text.append(text)
        current_blocks.append(block["block_id"])
    flush()
    return chunks


def _clean_extracted_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""

    line = re.sub(r"^[•●○▪▫◦■□◆◇➢➤▶▷▸\-\*·]+\s*", "", line)
    line = re.sub(r"^(?:p|n|u|l|v|o)\s+(?=[\u4e00-\u9fffA-Za-z0-9])", "", line)
    line = re.sub(r"^[\u2022\uf0b7\uf06e\uf070]\s*", "", line)
    line = normalize_text(line)

    if _is_noise_line(line):
        return ""
    return line


def _is_noise_line(line: str) -> bool:
    if not line:
        return True
    if re.fullmatch(r"[\W_]+", line, flags=re.UNICODE):
        return True
    if re.fullmatch(r"[A-Za-z]", line):
        return True
    if re.fullmatch(r"\d{1,3}", line):
        return True
    if len(line) <= 2 and not re.search(r"[\u4e00-\u9fff0-9]", line):
        return True
    return False


def _join_reading_lines(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current = ""

    for line in lines:
        if not current:
            current = line
            continue

        if _should_start_new_line(current, line):
            paragraphs.append(current)
            current = line
        else:
            current = f"{current} {line}"

    if current:
        paragraphs.append(current)

    return normalize_text("\n".join(paragraphs))


def _should_start_new_line(previous: str, current: str) -> bool:
    if re.match(r"^\d{1,3}\s+", current):
        return True
    if re.match(r"^第\s*\d+\s*[章节题]", current):
        return True
    if re.match(r"^[一二三四五六七八九十]+、", current):
        return True
    if previous.endswith(("。", "！", "？", "；", ";", ".", "!", "?")) and len(current) > 8:
        return True
    return False



