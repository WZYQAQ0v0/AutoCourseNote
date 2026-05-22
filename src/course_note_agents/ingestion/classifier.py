"""Explainable role classifier for local course materials."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

from course_note_agents.ingestion.fingerprint import logical_suffix
from course_note_agents.ingestion.models import (
    PIPELINE_BY_ROLE,
    ClassificationResult,
    ContentProbe,
    DocumentRole,
)


ROLES: tuple[DocumentRole, ...] = (
    "syllabus",
    "textbook",
    "lecture_slides",
    "assignment",
    "past_exam",
    "solution",
    "reference_paper",
    "notes",
    "miscellaneous",
)


NAME_KEYWORDS: dict[str, list[str]] = {
    "syllabus": [
        "syllabus",
        "outline",
        "calendar",
        "course_info",
        "教学大纲",
        "课程大纲",
        "课程说明",
        "考核方式",
    ],
    "textbook": [
        "textbook",
        "book",
        "chapter",
        "chap",
        "教材",
        "课本",
        "参考书",
        "第1章",
        "第2章",
        "第3章",
    ],
    "lecture_slides": [
        "lecture",
        "lect",
        "lec",
        "slides",
        "slide",
        "ppt",
        "课件",
        "讲义",
        "课堂",
        "第1讲",
        "第2讲",
        "第3讲",
    ],
    "assignment": [
        "assignment",
        "homework",
        "hw",
        "problem_set",
        "problem set",
        "exercise",
        "作业",
        "习题",
        "练习",
    ],
    "past_exam": [
        "exam",
        "midterm",
        "final",
        "quiz",
        "test",
        "mock",
        "sample",
        "往年",
        "真题",
        "试卷",
        "期中",
        "期末",
        "模拟题",
        "小测",
    ],
    "solution": [
        "solution",
        "solutions",
        "answer",
        "answers",
        "key",
        "解析",
        "答案",
        "参考答案",
        "解答",
        "题解",
    ],
    "reference_paper": [
        "paper",
        "article",
        "arxiv",
        "proceedings",
        "论文",
        "文献",
        "阅读材料",
        "reading",
        "tech_report",
    ],
    "notes": [
        "notes",
        "note",
        "summary",
        "review",
        "cheatsheet",
        "笔记",
        "总结",
        "复习",
        "速查",
    ],
}


CONTENT_KEYWORDS: dict[str, list[str]] = {
    "syllabus": [
        "course objective",
        "learning outcome",
        "grading",
        "office hours",
        "课程目标",
        "教学安排",
        "学时",
        "考核",
        "成绩评定",
    ],
    "textbook": [
        "chapter",
        "definition",
        "theorem",
        "proof",
        "lemma",
        "目录",
        "定义",
        "定理",
        "证明",
        "本章小结",
    ],
    "lecture_slides": [
        "agenda",
        "outline",
        "learning objectives",
        "today",
        "本节内容",
        "本章内容",
        "课堂内容",
        "回顾",
    ],
    "assignment": [
        "homework",
        "assignment",
        "due",
        "submit",
        "problem",
        "作业",
        "提交",
        "截止",
        "请完成",
    ],
    "past_exam": [
        "exam",
        "midterm",
        "final",
        "points",
        "marks",
        "考试时间",
        "满分",
        "得分",
        "选择题",
        "填空题",
        "简答题",
        "证明题",
    ],
    "solution": [
        "solution",
        "answer",
        "therefore",
        "解:",
        "解：",
        "答:",
        "答：",
        "证明:",
        "证明：",
        "解析",
        "答案",
    ],
    "reference_paper": [
        "abstract",
        "introduction",
        "related work",
        "references",
        "doi",
        "arxiv",
        "摘要",
        "参考文献",
    ],
    "notes": [
        "summary",
        "key points",
        "cheat sheet",
        "复习",
        "总结",
        "重点",
        "易错",
    ],
}


ZH_PRIORITY_KEYWORDS: dict[str, list[str]] = {
    "syllabus": [
        "教学大纲",
        "课程大纲",
        "课程简介",
        "课程说明",
        "教学日历",
        "教学安排",
        "考核方式",
        "成绩评定",
        "评分构成",
    ],
    "textbook": [
        "教材",
        "课本",
        "参考书",
        "电子教材",
        "第1章",
        "第2章",
        "第3章",
        "本章小结",
        "例题",
        "习题",
    ],
    "lecture_slides": [
        "课件",
        "讲义",
        "课堂",
        "第1讲",
        "第2讲",
        "第3讲",
        "第一讲",
        "第二讲",
        "第三讲",
        "习题课",
        "复习课",
    ],
    "assignment": [
        "作业",
        "大作业",
        "小作业",
        "实验报告",
        "实验题",
        "课后习题",
        "练习题",
        "习题",
        "提交",
        "截止",
    ],
    "past_exam": [
        "往年题",
        "历年题",
        "真题",
        "试卷",
        "期中",
        "期末",
        "考试",
        "模拟题",
        "样题",
        "小测",
        "复习题",
        "回忆版",
    ],
    "solution": [
        "答案",
        "参考答案",
        "标准答案",
        "答案要点",
        "解析",
        "详解",
        "解答",
        "题解",
        "评分标准",
        "解题过程",
    ],
    "reference_paper": [
        "论文",
        "文献",
        "阅读材料",
        "参考资料",
        "技术报告",
        "摘要",
        "参考文献",
    ],
    "notes": [
        "笔记",
        "课堂笔记",
        "复习笔记",
        "总结",
        "知识点",
        "重点",
        "易错点",
        "速查",
        "提纲",
    ],
}


EXTENSION_HINTS: dict[str, dict[str, float]] = {
    ".ppt": {"lecture_slides": 0.45},
    ".pptx": {"lecture_slides": 0.5},
    ".doc": {"assignment": 0.08, "solution": 0.08, "notes": 0.06},
    ".docx": {"assignment": 0.08, "solution": 0.08, "notes": 0.06},
    ".pdf": {"textbook": 0.08, "lecture_slides": 0.05, "reference_paper": 0.05},
    ".tex": {"notes": 0.18, "reference_paper": 0.1},
    ".md": {"notes": 0.18},
    ".markdown": {"notes": 0.18},
    ".txt": {"notes": 0.06},
    ".html": {"notes": 0.08},
    ".htm": {"notes": 0.08},
}


def classify_material(path: Path, probe: ContentProbe) -> ClassificationResult:
    scores: defaultdict[str, float] = defaultdict(float)
    signals: list[str] = []
    normalized_path = _normalize_for_match(str(path))
    text = _normalize_for_match(probe.text_preview[:12000])
    suffix = logical_suffix(path)

    for role, value in EXTENSION_HINTS.get(suffix, {}).items():
        _add(scores, signals, role, value, f"extension {suffix}")

    _score_keywords(scores, signals, normalized_path, NAME_KEYWORDS, "filename/path", 0.22)
    _score_keywords(scores, signals, text, CONTENT_KEYWORDS, "content", 0.12)
    _score_keywords(scores, signals, normalized_path, ZH_PRIORITY_KEYWORDS, "zh filename/path", 0.30)
    _score_keywords(scores, signals, text, ZH_PRIORITY_KEYWORDS, "zh content", 0.18)
    _score_structure(scores, signals, path, probe)

    problem_marker_count = _count_problem_markers(text)
    if problem_marker_count >= 5:
        _add(scores, signals, "assignment", 0.16, f"{problem_marker_count} problem markers")
        _add(scores, signals, "past_exam", 0.10, f"{problem_marker_count} problem markers")
    if _looks_like_scored_exam(text):
        _add(scores, signals, "past_exam", 0.28, "exam scoring/time markers")
    if _looks_like_zh_exam(text):
        _add(scores, signals, "past_exam", 0.34, "Chinese exam markers")
    if _looks_like_solution(text):
        _add(scores, signals, "solution", 0.30, "solution-style derivation markers")
    if _looks_like_zh_solution(text):
        _add(scores, signals, "solution", 0.34, "Chinese solution markers")
    looks_like_course_unit = _looks_like_numbered_course_unit(path, normalized_path, suffix)
    if looks_like_course_unit:
        _add(scores, signals, "lecture_slides", 0.32, "numbered Chinese course unit filename")

    if probe.needs_ocr:
        signals.append("needs OCR before high-confidence semantic classification")

    if not scores:
        return ClassificationResult(
            document_role="miscellaneous",
            confidence=0.35,
            reason="No reliable filename, extension, text, or structure signal matched a known course-material role.",
            next_pipeline=PIPELINE_BY_ROLE["miscellaneous"],
            scores={"miscellaneous": 0.0},
            secondary_roles=[],
            processing_hints=_processing_hints("miscellaneous", [], probe),
            signals=signals,
        )

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_role, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    mixed_exam_solution = _is_mixed_exam_solution(scores, text, normalized_path, problem_marker_count)
    if mixed_exam_solution and looks_like_course_unit and not _path_has_exam_marker(normalized_path):
        mixed_exam_solution = False
        signals.append("kept numbered course unit as lecture material despite assessment/answer-like text")

    if best_score < 0.16:
        best_role = "miscellaneous"
        confidence = 0.42
    else:
        margin = max(0.0, best_score - second_score)
        confidence = 0.48 + 0.35 * _saturate(best_score) + 0.17 * _saturate(margin * 1.5)
        confidence = min(0.97, round(confidence, 3))

    if mixed_exam_solution:
        best_role = "past_exam"
        confidence = max(confidence, 0.78)

    secondary_roles = _secondary_roles(best_role, scores, mixed_exam_solution)
    role_scores = {role: round(scores.get(role, 0.0), 3) for role in ROLES if scores.get(role, 0.0) > 0}
    if best_role == "miscellaneous":
        role_scores.setdefault("miscellaneous", 0.0)

    processing_hints = _processing_hints(best_role, secondary_roles, probe)
    next_pipeline = _resolve_pipeline(best_role, secondary_roles, probe)
    reason = _build_reason(best_role, confidence, ranked, signals, secondary_roles, processing_hints)
    return ClassificationResult(
        document_role=best_role,  # type: ignore[arg-type]
        confidence=confidence,
        reason=reason,
        next_pipeline=next_pipeline,
        scores=role_scores,
        secondary_roles=secondary_roles,
        processing_hints=processing_hints,
        signals=signals[:12],
    )


def _score_keywords(
    scores: defaultdict[str, float],
    signals: list[str],
    haystack: str,
    keyword_map: dict[str, list[str]],
    source: str,
    weight: float,
) -> None:
    if not haystack:
        return
    for role, keywords in keyword_map.items():
        matches = [keyword for keyword in keywords if _normalize_for_match(keyword) in haystack]
        if matches:
            value = weight * min(3, len(matches))
            _add(scores, signals, role, value, f"{source} keywords: {', '.join(matches[:3])}")


def _score_structure(
    scores: defaultdict[str, float],
    signals: list[str],
    path: Path,
    probe: ContentProbe,
) -> None:
    suffix = logical_suffix(path)
    if probe.slide_count:
        _add(scores, signals, "lecture_slides", 0.34, f"{probe.slide_count} PPTX slides")
    if probe.page_count:
        if probe.page_count >= 80:
            _add(scores, signals, "textbook", 0.18, f"{probe.page_count} PDF pages")
        elif probe.page_count <= 8 and suffix == ".pdf":
            _add(scores, signals, "assignment", 0.08, f"short PDF with {probe.page_count} pages")
            _add(scores, signals, "past_exam", 0.08, f"short PDF with {probe.page_count} pages")
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
        _add(scores, signals, "miscellaneous", 0.12, "image file")


def _looks_like_numbered_course_unit(path: Path, normalized_path: str, suffix: str) -> bool:
    if suffix not in {".pdf", ".ppt", ".pptx"}:
        return False
    name = path.name
    if _path_has_exam_marker(normalized_path):
        return False
    return bool(
        re.match(r"^\s*\d{1,2}\s*[-_.－—、]", name)
        or re.match(r"^\s*第[一二三四五六七八九十百\d]+讲", name)
        or re.match(r"^\s*(lecture|lect|lec)\s*\d+", normalized_path)
    )


def _path_has_exam_marker(normalized_path: str) -> bool:
    return any(
        marker in normalized_path
        for marker in (
            "exam",
            "final",
            "midterm",
            "quiz",
            "答案",
            "解析",
            "真题",
            "试卷",
            "期中",
            "期末",
            "考试",
            "模拟题",
        )
    )


def _count_problem_markers(text: str) -> int:
    if not text:
        return 0
    patterns = [
        r"\bproblem\s+\d+",
        r"\bquestion\s+\d+",
        r"\bexercise\s+\d+",
        r"第\s*\d+\s*题",
        r"[一二三四五六七八九十]+、",
        r"（\s*\d+\s*）",
        r"^\s*\d+\s*[).、]",
    ]
    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))
    return count


def _looks_like_scored_exam(text: str) -> bool:
    if not text:
        return False
    markers = [
        "考试时间",
        "闭卷",
        "开卷",
        "满分",
        "得分",
        "points",
        "marks",
        "midterm",
        "final exam",
    ]
    return sum(1 for marker in markers if marker in text) >= 2


def _looks_like_zh_exam(text: str) -> bool:
    if not text:
        return False
    markers = [
        "考试时间",
        "闭卷",
        "开卷",
        "满分",
        "得分",
        "分值",
        "选择题",
        "填空题",
        "判断题",
        "简答题",
        "计算题",
        "证明题",
        "试卷",
        "期末考试",
        "期中考试",
    ]
    return sum(1 for marker in markers if marker in text) >= 2


def _looks_like_solution(text: str) -> bool:
    if not text:
        return False
    markers = ["解:", "解：", "答:", "答：", "solution", "answer", "therefore", "证明:", "证明："]
    return sum(text.count(marker) for marker in markers) >= 2


def _looks_like_zh_solution(text: str) -> bool:
    if not text:
        return False
    strong_markers = ["参考答案", "标准答案", "答案要点", "评分标准", "题解", "详解"]
    if any(marker in text for marker in strong_markers):
        return True
    markers = [
        "解：",
        "解:",
        "答：",
        "答:",
        "证明：",
        "证明:",
        "解析",
        "因此",
        "所以",
        "由题意",
        "可得",
        "故",
    ]
    return sum(text.count(marker) for marker in markers) >= 3


def _is_mixed_exam_solution(
    scores: defaultdict[str, float],
    text: str,
    normalized_path: str,
    problem_marker_count: int,
) -> bool:
    exam_score = scores.get("past_exam", 0.0)
    solution_score = scores.get("solution", 0.0)
    if exam_score >= 0.28 and solution_score >= 0.22:
        return True
    path_has_exam = any(
        marker in normalized_path
        for marker in (
            "exam",
            "final",
            "midterm",
            "quiz",
            "往年",
            "历年",
            "真题",
            "试卷",
            "期末",
            "期中",
            "考试",
            "复习题",
        )
    )
    path_has_solution = any(
        marker in normalized_path
        for marker in ("solution", "answer", "答案", "解析", "解答", "题解", "评分标准")
    )
    if path_has_exam and path_has_solution:
        return True
    if problem_marker_count >= 3 and _looks_like_solution(text):
        return True
    return False


def _secondary_roles(
    best_role: str,
    scores: defaultdict[str, float],
    mixed_exam_solution: bool,
) -> list[DocumentRole]:
    secondary: list[DocumentRole] = []
    if mixed_exam_solution and best_role != "solution":
        secondary.append("solution")
    best_score = scores.get(best_role, 0.0)
    for role in ROLES:
        if role == best_role or role == "miscellaneous":
            continue
        score = scores.get(role, 0.0)
        if score >= 0.30 and score >= best_score * 0.55 and role not in secondary:
            secondary.append(role)
    return secondary[:4]


def _processing_hints(
    best_role: str,
    secondary_roles: list[DocumentRole],
    probe: ContentProbe,
) -> list[str]:
    hints: list[str] = []
    if probe.needs_ocr:
        hints.append("requires_ocr")
    if best_role == "past_exam" and "solution" in secondary_roles:
        hints.append("contains_exam_and_solution")
        hints.append("segment_questions_and_answers")
    if probe.probe_method in {"pdf_binary_sniff", "image_metadata"}:
        hints.append("semantic_confidence_limited_before_full_parsing")
    return hints


def _resolve_pipeline(
    best_role: str,
    secondary_roles: list[DocumentRole],
    probe: ContentProbe,
) -> str:
    if best_role == "past_exam" and "solution" in secondary_roles:
        base_pipeline = "exam_solution_parser"
    elif best_role == "miscellaneous" and probe.needs_ocr:
        base_pipeline = "ocr_generic_parser"
    else:
        base_pipeline = PIPELINE_BY_ROLE[best_role]
    if probe.needs_ocr and not base_pipeline.startswith("ocr_"):
        return f"ocr_then_{base_pipeline}"
    return base_pipeline


def _normalize_for_match(value: str) -> str:
    value = value.lower().replace("\\", "/")
    value = re.sub(r"[_\-]+", " ", value)
    return value


def _add(
    scores: defaultdict[str, float],
    signals: list[str],
    role: str,
    value: float,
    signal: str,
) -> None:
    scores[role] += value
    signals.append(f"{role}: +{value:.2f} from {signal}")


def _saturate(value: float) -> float:
    return 1.0 - math.exp(-max(0.0, value))


def _build_reason(
    best_role: str,
    confidence: float,
    ranked: list[tuple[str, float]],
    signals: list[str],
    secondary_roles: list[DocumentRole],
    processing_hints: list[str],
) -> str:
    top = ", ".join(f"{role}={score:.2f}" for role, score in ranked[:3])
    strongest = "; ".join(signals[:3]) if signals else "no detailed signal"
    extras = []
    if secondary_roles:
        extras.append(f"secondary roles: {', '.join(secondary_roles)}")
    if processing_hints:
        extras.append(f"hints: {', '.join(processing_hints)}")
    extra_text = f" {'; '.join(extras)}." if extras else ""
    return f"Classified as {best_role} with confidence {confidence:.3f}. Top scores: {top}. Strongest signals: {strongest}.{extra_text}"
