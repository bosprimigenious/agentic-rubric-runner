"""从 PDF 抽取 Evidence Pack，供报告引用与评分检索。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

_AARRR_TAGS = ("获客", "激活", "留存", "变现", "传播", "AARRR")
_KEYWORDS = (
    "留存",
    "次日",
    "7日",
    "30日",
    "转化",
    "漏斗",
    "北极星",
    "DAU",
    "GMV",
    "CAC",
    "LTV",
    "裂变",
    "分享",
    "激活",
    "获客",
    "变现",
    "传播",
    "预警",
    "目标",
    "周度",
    "月度",
    "季度",
)


class EvidenceFact(BaseModel):
    id: str
    page: int
    text: str
    tags: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    source_pdf: str = ""
    facts: list[EvidenceFact] = Field(default_factory=list)


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


def _tag_fact(text: str) -> list[str]:
    tags = [t for t in _AARRR_TAGS if t in text]
    for kw in _KEYWORDS:
        if kw in text and kw not in tags:
            tags.append(kw)
    return tags[:6]


def _extract_sentences(page_text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？；\n])", page_text)
    sentences: list[str] = []
    for part in raw:
        s = re.sub(r"\s+", " ", part).strip()
        if len(s) >= 12:
            sentences.append(s)
    return sentences


def extract_evidence_pack(pdf_path: str, *, max_facts: int = 40) -> EvidencePack:
    """按页切分 PDF，抽取含增长/AARRR 关键词的事实句。"""
    from aarrr_agent.tools import read_pdf

    pdf_text = read_pdf(pdf_path)
    facts: list[EvidenceFact] = []
    seen: set[str] = set()

    for page_no, page_text in _split_pages(pdf_text):
        for sentence in _extract_sentences(page_text):
            if not any(kw in sentence for kw in _KEYWORDS):
                continue
            key = sentence[:80]
            if key in seen:
                continue
            seen.add(key)
            tags = _tag_fact(sentence)
            facts.append(
                EvidenceFact(
                    id=f"E{len(facts) + 1:02d}",
                    page=page_no,
                    text=sentence[:300],
                    tags=tags,
                )
            )
            if len(facts) >= max_facts:
                break
        if len(facts) >= max_facts:
            break

    if not facts:
        for page_no, page_text in _split_pages(pdf_text)[:3]:
            snippet = page_text[:200].strip()
            if snippet:
                facts.append(
                    EvidenceFact(
                        id=f"E{len(facts) + 1:02d}",
                        page=page_no,
                        text=snippet,
                        tags=["摘要"],
                    )
                )

    return EvidencePack(source_pdf=str(Path(pdf_path).name), facts=facts)


def save_evidence_pack(pack: EvidencePack, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pack.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_evidence_pack(path: str | Path) -> EvidencePack:
    return EvidencePack.model_validate_json(Path(path).read_text(encoding="utf-8"))


def format_evidence_for_prompt(pack: EvidencePack) -> str:
    if not pack.facts:
        return "（未抽取到证据条目）"
    lines = [f"- {f.id} [p.{f.page}] ({', '.join(f.tags) or '通用'}) {f.text}" for f in pack.facts]
    return "\n".join(lines)
