"""Shared cleanup helpers for visible Markdown artifacts."""

from __future__ import annotations

import re


_VISIBLE_SOURCE_TAG_RE = re.compile(r"\s*[\[【]\s*(?:来源|资料来源|引用|证据)\s*[:：][^\]】\n]{0,500}[\]】]")
_DEEP_DECIMAL_HEADING_RE = re.compile(r"^(#{1,6}\s+)\d+(?:\.\d+){2,}[.、．]?\s*(.+)$")
_DEEP_DECIMAL_LINE_RE = re.compile(r"^(\s*)(\d+(?:\.\d+){2,})[.、．]?\s*(.+)$")


def clean_visible_markdown(markdown: str) -> str:
    """Remove noisy visible provenance tags and over-deep decimal numbering."""
    if not markdown:
        return markdown
    markdown = remove_visible_source_tags(markdown)
    markdown = simplify_deep_decimal_numbering(markdown)
    return markdown.strip()


def remove_visible_source_tags(markdown: str) -> str:
    """Remove inline tags like ``[来源: ...]`` while keeping structured refs elsewhere."""
    output: list[str] = []
    for line in markdown.splitlines():
        original = line
        line = _VISIBLE_SOURCE_TAG_RE.sub("", line)
        line = re.sub(r"[ \t]{2,}", " ", line).rstrip()
        if original.strip() and not line.strip():
            continue
        output.append(line)
    return _collapse_blank_lines("\n".join(output))


def simplify_deep_decimal_numbering(markdown: str) -> str:
    """Simplify visible prefixes such as ``1.4.1`` in headings and list-like lines."""
    output: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            output.append(line)
            continue
        if in_fence:
            output.append(line)
            continue

        heading = _DEEP_DECIMAL_HEADING_RE.match(line)
        if heading:
            output.append(f"{heading.group(1)}{heading.group(2).strip()}")
            continue

        item = _DEEP_DECIMAL_LINE_RE.match(line)
        if item and not stripped.startswith(("http://", "https://")):
            ordinal = _chinese_ordinal_from_decimal_prefix(item.group(2))
            output.append(f"{item.group(1)}{ordinal}、{item.group(3).strip()}")
            continue

        output.append(line)
    return "\n".join(output)


def _collapse_blank_lines(markdown: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", markdown)


def _chinese_ordinal_from_decimal_prefix(prefix: str) -> str:
    try:
        value = int(prefix.split(".")[-1])
    except ValueError:
        return "一"
    return _to_chinese_number(value)


def _to_chinese_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value <= 0:
        return str(value)
    if value < 10:
        return digits[value]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + digits[value % 10]
    if value < 100:
        tens, ones = divmod(value, 10)
        return digits[tens] + "十" + (digits[ones] if ones else "")
    return str(value)
