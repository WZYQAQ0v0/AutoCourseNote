"""LLM-based page text cleanup for parsed course materials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from course_note_agents.model_gateway.openai_compatible import OpenAICompatibleClient
from course_note_agents.parsing.models import ParsedBlock, ParsedPage
from course_note_agents.parsing.text_utils import clean_extracted_text


class JSONChatClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]]) -> dict:
        ...


@dataclass(slots=True)
class LLMRefinerStats:
    attempted_pages: int = 0
    refined_pages: int = 0
    skipped_pages: int = 0
    failed_pages: int = 0


class LLMTextRefiner:
    def __init__(
        self,
        client: JSONChatClient,
        max_page_chars: int = 6000,
        min_page_chars: int = 20,
    ) -> None:
        self.client = client
        self.max_page_chars = max_page_chars
        self.min_page_chars = min_page_chars
        self.stats = LLMRefinerStats()

    def refine_pages(self, file_entry: dict, pages: list[ParsedPage], language: str) -> list[ParsedPage]:
        refined_pages: list[ParsedPage] = []
        for page in pages:
            refined_pages.append(self.refine_page(file_entry, page, language))
        return refined_pages

    def refine_page(self, file_entry: dict, page: ParsedPage, language: str) -> ParsedPage:
        text = page.text.strip()
        if page.needs_ocr or len(text) < self.min_page_chars:
            self.stats.skipped_pages += 1
            return page

        self.stats.attempted_pages += 1
        prompt_text = text[: self.max_page_chars]
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _user_prompt(
                    file_entry=file_entry,
                    page_number=page.page_number,
                    language=language,
                    text=prompt_text,
                    truncated=len(text) > len(prompt_text),
                ),
            },
        ]

        try:
            result = self.client.chat_json(messages)
            clean_text = clean_extracted_text(str(result.get("clean_text", "")))
            confidence = _safe_float(result.get("confidence"), default=0.75)
        except Exception as exc:
            self.stats.failed_pages += 1
            page.warnings.append(f"LLM cleanup failed; kept local cleaned text: {exc}")
            return page

        self.stats.refined_pages += 1
        page.text = clean_text
        page.blocks = _single_refined_block(file_entry, page, clean_text, confidence)
        page.warnings.extend(str(item) for item in result.get("warnings", []) if item)
        return page


def build_refiner(client: OpenAICompatibleClient | None, max_page_chars: int = 6000) -> LLMTextRefiner | None:
    if client is None:
        return None
    return LLMTextRefiner(client=client, max_page_chars=max_page_chars)


_SYSTEM_PROMPT = """你是中文课程材料整理 Agent。你的任务是把 PDF/PPT 提取出的混乱页文本整理成给后续知识抽取 Agent 使用的干净正文。

严格要求：
1. 只保留有实际教学意义的文字：标题、概念、定义、定理、条文、人物事件、作品观点、方法步骤、公式说明、例题题干、答案解析、重要说明。
2. 删除图形/流程图/坐标图/示意图中的零散标签、轴标签、孤立节点、装饰性文字、页眉页脚、页码、版权信息和无意义符号。
3. 如果一页几乎全是图示标签，没有可整理成句的正文，返回空字符串。
4. 不要补充原文没有的信息，不要解释，不要扩写。
5. 保持中文，必要的英文术语和公式可保留。
6. 只输出 JSON 对象，格式为：
{"clean_text": "...", "discarded_noise_summary": "...", "confidence": 0.0, "warnings": []}
"""


def _user_prompt(file_entry: dict, page_number: int, language: str, text: str, truncated: bool) -> str:
    truncated_note = "文本因长度限制被截断。" if truncated else "文本未截断。"
    return f"""课程材料信息：
- 文件名：{file_entry.get("path")}
- 主类型：{file_entry.get("document_role")}
- 辅助类型：{file_entry.get("secondary_roles", [])}
- 页码：{page_number}
- 语言：{language}
- {truncated_note}

请整理以下页文本，删除图形标签噪声，只保留可读正文：

<<<PAGE_TEXT
{text}
PAGE_TEXT>>>
"""


def _single_refined_block(file_entry: dict, page: ParsedPage, text: str, confidence: float) -> list[ParsedBlock]:
    if not text:
        return []
    return [
        ParsedBlock(
            block_id=f"{file_entry['file_id']}:page:{page.page_number}:llm_text",
            type="paragraph",
            text=text,
            page_number=page.page_number,
            bbox=None,
            confidence=confidence,
            metadata={"source": "llm_text_refiner", "granularity": "page_text"},
        )
    ]


def _safe_float(value, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))
