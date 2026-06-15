"""关键词检索：为 Grader 选取相关 PDF 页，替代简单截断。"""

from __future__ import annotations

import re
from typing import Any

from aarrr_agent.config import PROMPT_ATTACHMENT_BUDGET

_STOPWORDS = frozenset({"的", "是", "在", "和", "与", "或", "及", "为", "了", "必须", "需要", "文档"})


def _split_pages(pdf_text: str) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    for chunk in re.split(r"(?=\[PAGE \d+\])", pdf_text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"\[PAGE (\d+)\]\s*(.*)", chunk, re.DOTALL)
        if m:
            pages.append((int(m.group(1)), m.group(2).strip()))
    return pages


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for word in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", text):
        if word not in _STOPWORDS:
            tokens.add(word.lower() if word.isascii() else word)
    return tokens


def build_retrieval_keywords(rubrics: dict[str, Any], query_text: str) -> set[str]:
    keywords: set[str] = set()
    rubric = rubrics.get("rubric", {})
    for group in ("hard_constraints", "soft_constraints", "optional_constraints"):
        for item in rubric.get(group, []):
            keywords |= _tokenize(item.get("description", ""))
            keywords |= _tokenize(item.get("reference_facts", ""))
    keywords |= _tokenize(query_text)
    extra = ("留存", "获客", "激活", "变现", "传播", "北极星", "预警", "漏斗", "AARRR", "周度", "月度", "季度")
    keywords.update(extra)
    return keywords


def retrieve_relevant_pages(
    pdf_text: str,
    *,
    keywords: set[str],
    budget: int = PROMPT_ATTACHMENT_BUDGET,
) -> str:
    """按关键词命中数排序选页，在预算内拼接。"""
    if len(pdf_text) <= budget:
        return pdf_text

    pages = _split_pages(pdf_text)
    if not pages:
        return pdf_text[:budget]

    scored: list[tuple[int, int, str]] = []
    for page_no, body in pages:
        hits = sum(1 for kw in keywords if kw in body)
        scored.append((hits, page_no, body))

    scored.sort(key=lambda x: (-x[0], x[1]))

    selected: list[str] = []
    total = 0
    used_pages: set[int] = set()

    for hits, page_no, body in scored:
        if hits == 0 and selected:
            continue
        block = f"[PAGE {page_no}]\n{body}"
        if total + len(block) > budget:
            if not selected:
                selected.append(block[:budget])
            break
        selected.append(block)
        total += len(block)
        used_pages.add(page_no)

    omitted = len(pages) - len(used_pages)
    note = f"\n\n[NOTE: 检索式选取 {len(used_pages)} 页，省略 {omitted} 页]"
    result = "\n\n".join(selected)
    if len(result) + len(note) <= budget:
        return result + note
    return result[:budget]
