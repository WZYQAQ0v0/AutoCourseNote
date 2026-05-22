"""Minimal OpenAI-compatible chat-completions client.

This intentionally uses only the Python standard library so the project can
work with OpenAI, DeepSeek, or any OpenAI-compatible endpoint without adding a
provider SDK dependency.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "compatible": "",
}


@dataclass(slots=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str
    timeout_seconds: int = 60
    max_retries: int = 2

    @classmethod
    def from_env(
        cls,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "COURSE_NOTE_LLM_API_KEY",
        timeout_seconds: int = 60,
        max_retries: int = 2,
    ) -> "LLMConfig | None":
        resolved_provider = (provider or os.getenv("COURSE_NOTE_LLM_PROVIDER") or "openai").strip()
        resolved_model = (model or os.getenv("COURSE_NOTE_LLM_MODEL") or "").strip()
        api_key = os.getenv(api_key_env, "").strip()
        resolved_base_url = (
            base_url
            or os.getenv("COURSE_NOTE_LLM_BASE_URL")
            or PROVIDER_BASE_URLS.get(resolved_provider, "")
        ).strip()

        if not api_key or not resolved_model or not resolved_base_url:
            return None
        return cls(
            provider=resolved_provider,
            model=resolved_model,
            api_key=api_key,
            base_url=resolved_base_url.rstrip("/"),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            return self._post_chat(payload)
        except RuntimeError as exc:
            # Some compatible providers do not support response_format. Retry
            # once with an explicit prompt-only JSON instruction.
            if "response_format" not in str(exc):
                raise
            fallback_payload = dict(payload)
            fallback_payload.pop("response_format", None)
            return self._post_chat(fallback_payload)

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.base_url}/chat/completions"
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "course-note-agents/0.1",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"LLM HTTP {exc.code}: {body}")
                if exc.code not in {408, 409, 429, 500, 502, 503, 504} or attempt >= self.config.max_retries:
                    raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"LLM request failed: {exc}")
                if attempt >= self.config.max_retries:
                    raise last_error from exc
            time.sleep(min(2.0 * (attempt + 1), 6.0))
        else:
            raise RuntimeError(f"LLM request failed: {last_error}")

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LLM response shape: {data}") from exc

        if isinstance(content, list):
            content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise RuntimeError(f"Unexpected LLM content type: {type(content).__name__}")

        return _parse_json_content(content)


def _parse_json_content(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        repaired = _escape_invalid_json_backslashes(content)
        if repaired != content:
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError:
                parsed = _parse_loose_markdown_json(content)
        else:
            parsed = _parse_loose_markdown_json(content)
        if parsed is None:
            raise RuntimeError(f"LLM did not return valid JSON: {content[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM JSON response must be an object.")
    return _normalize_parsed_text_fields(parsed)


def _parse_loose_markdown_json(content: str) -> dict[str, Any] | None:
    """Recover common provider output with raw multiline Markdown strings.

    Some OpenAI-compatible providers occasionally return an object like
    ``{"revised_markdown": "# title\n...", "changes": [...]}`` but place real
    newline characters inside the quoted Markdown value. That is not valid
    JSON, although the surrounding object is otherwise machine-readable.
    """

    for markdown_key in ("revised_markdown", "polished_markdown", "markdown"):
        key_pattern = re.compile(rf'"{re.escape(markdown_key)}"\s*:\s*"')
        key_match = key_pattern.search(content)
        if key_match is None:
            continue
        start = key_match.end()
        delimiters = list(re.finditer(r'"\s*,\s*"[A-Za-z_][A-Za-z0-9_]*"\s*:', content[start:], flags=re.DOTALL))
        if not delimiters:
            prefix = content[: key_match.start()]
            markdown = content[start:]
            end_match = re.search(r'"\s*}\s*$', markdown, flags=re.DOTALL)
            if end_match:
                markdown = markdown[: end_match.start()]
            recovered = _extract_loose_prefix_string_fields(prefix)
            recovered[markdown_key] = _decode_json_string_fragment(markdown)
            return recovered
        delimiter = delimiters[-1]
        markdown = content[start : start + delimiter.start()]
        suffix = content[start + delimiter.start() + 1 :]
        suffix_object = "{" + suffix.lstrip(" \t\r\n,")
        try:
            parsed_suffix = json.loads(suffix_object)
        except json.JSONDecodeError:
            parsed_suffix = {}
            for list_key in (
                "changes",
                "applied_fixes",
                "remaining_issues",
                "consistency_notes",
                "source_refs",
                "unresolved_issues",
                "warnings",
            ):
                values = _extract_loose_string_list(suffix_object, list_key)
                if values is not None:
                    parsed_suffix[list_key] = values
        if not isinstance(parsed_suffix, dict):
            return None
        return {markdown_key: _decode_json_string_fragment(markdown), **parsed_suffix}
    return None


def _extract_loose_prefix_string_fields(content: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for match in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"([^"]*)"\s*,', content, flags=re.DOTALL):
        fields[match.group(1)] = match.group(2)
    return fields


def _decode_json_string_fragment(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def _escape_invalid_json_backslashes(content: str) -> str:
    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", content)


def _normalize_parsed_text_fields(data: dict[str, Any]) -> dict[str, Any]:
    markdown_keys = {"markdown", "revised_markdown", "polished_markdown"}
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        if key in markdown_keys and isinstance(value, str):
            normalized[key] = _normalize_markdown_newlines(value)
        elif isinstance(value, dict):
            normalized[key] = _normalize_parsed_text_fields(value)
        elif isinstance(value, list):
            normalized[key] = [
                _normalize_parsed_text_fields(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            normalized[key] = value
    return normalized


def _normalize_markdown_newlines(value: str) -> str:
    literal_newlines = value.count("\\n")
    if literal_newlines < 3:
        return value
    real_newlines = value.count("\n")
    if literal_newlines <= max(3, real_newlines * 3):
        return value
    return value.replace("\\r\\n", "\n").replace("\\n", "\n")


def _extract_loose_string_list(content: str, key: str) -> list[str] | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*\[(.*?)\]', content, flags=re.DOTALL)
    if match is None:
        return None
    return [item.group(1) for item in re.finditer(r'"([^"]*)"', match.group(1), flags=re.DOTALL)]
