"""Phase 2 Rubric 评分与分数重算。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from aarrr_agent.config import MAX_GRADING_ATTEMPTS
from aarrr_agent.errors import PipelineError
from aarrr_agent.llm import call_chat_completion
from aarrr_agent.schemas import GradingResult, ScoreBreakdown
from aarrr_agent.tools import fit_text_to_budget, read_pdf, read_text


def load_rubrics(rubrics_path: str) -> dict[str, Any]:
    return json.loads(Path(rubrics_path).read_text(encoding="utf-8"))


def build_constraint_id_map(rubrics: dict[str, Any]) -> dict[str, str]:
    """生成 H01/S01/O01 等 ID 与 rubric 条目的对应关系说明。"""
    rubric = rubrics["rubric"]
    lines: list[str] = []

    for i, item in enumerate(rubric["hard_constraints"], 1):
        cid = f"H{i:02d}"
        lines.append(f"{cid}: {item['description']}")

    for i, item in enumerate(rubric["soft_constraints"], 1):
        cid = f"S{i:02d}"
        lines.append(f"{cid}: {item['description']}")

    for i, item in enumerate(rubric["optional_constraints"], 1):
        cid = f"O{i:02d}"
        lines.append(f"{cid}: {item['description']}")

    return {"mapping_text": "\n".join(lines)}


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
    return text.strip()


def _normalize_grading_data(data: dict[str, Any], rubrics: dict[str, Any]) -> dict[str, Any]:
    """确保每条 rubric 都有对应评分项，缺失则补 0 分。"""
    rubric = rubrics["rubric"]

    def index_by_id(items: list[dict[str, Any]], prefix: str, count: int) -> list[dict[str, Any]]:
        by_id = {item["id"]: item for item in items}
        normalized: list[dict[str, Any]] = []
        for i in range(1, count + 1):
            cid = f"{prefix}{i:02d}"
            if cid in by_id:
                normalized.append(by_id[cid])
            else:
                normalized.append({"id": cid, "score": 0, "reason": "评分项缺失，默认 0 分"})
        return normalized

    data["hard_constraints"] = index_by_id(
        data.get("hard_constraints", []), "H", len(rubric["hard_constraints"])
    )
    data["soft_constraints"] = index_by_id(
        data.get("soft_constraints", []), "S", len(rubric["soft_constraints"])
    )
    data["optional_constraints"] = index_by_id(
        data.get("optional_constraints", []), "O", len(rubric["optional_constraints"])
    )
    return data


def recalculate_scores(result: GradingResult, rubrics_path: str) -> GradingResult:
    """
    不信任模型计算的 breakdown 数字，程序强制重算 final_score。
    公式：总得分率 = (hard + soft + optional) / (hard_max + soft_max + optional_max) * 100
    """
    rubrics = load_rubrics(rubrics_path)
    rubric = rubrics["rubric"]

    hard_score = sum(c.score for c in result.hard_constraints)
    hard_max = len(rubric["hard_constraints"])

    soft_score = sum(c.score for c in result.soft_constraints)
    soft_max = len(rubric["soft_constraints"]) * 4

    optional_score = sum(c.score for c in result.optional_constraints)
    optional_max = len(rubric["optional_constraints"])

    total_score = hard_score + soft_score + optional_score
    total_max = hard_max + soft_max + optional_max
    final_score = round(total_score / total_max * 100, 2) if total_max else 0.0

    result.score_breakdown = ScoreBreakdown(
        hard_score=hard_score,
        hard_max=hard_max,
        soft_score=soft_score,
        soft_max=soft_max,
        optional_score=optional_score,
        optional_max=optional_max,
        final_score=final_score,
    )
    return result


def _clean_extracted_text(text: str) -> str:
    """轻度清理 PDF 抽取文本，减少排版噪音对评分的影响。"""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def load_submitted_document(phase1_pdf_path: str, phase1_md_path: str | None = None) -> str:
    """
    加载 Phase 1 提交内容。
    优先读取 Markdown 源文件（结构最完整），不存在时再从 PDF 反抽文本。
    """
    md = Path(phase1_md_path) if phase1_md_path else Path(phase1_pdf_path).with_suffix(".md")
    if md.exists():
        print(f"[Phase 2] 使用 Markdown 源文件评分: {md}")
        return md.read_text(encoding="utf-8")

    print(f"[Phase 2] Markdown 不存在，回退到 PDF 文本抽取: {phase1_pdf_path}")
    return _clean_extracted_text(read_pdf(phase1_pdf_path))


def run_phase2_grader(
    phase1_pdf_path: str,
    rubrics_path: str,
    query_path: str,
    attachment_pdf_path: str,
    client: OpenAI,
    model: str,
    phase1_md_path: str | None = None,
) -> GradingResult:
    rubrics = load_rubrics(rubrics_path)
    id_map = build_constraint_id_map(rubrics)

    rubrics_text = read_text(rubrics_path)
    phase1_text = load_submitted_document(phase1_pdf_path, phase1_md_path)
    query_text = read_text(query_path)
    attachment_text = fit_text_to_budget(_clean_extracted_text(read_pdf(attachment_pdf_path)))

    prompt = f"""You are a strict evaluator. Grade the submitted document against the rubrics below.

RUBRIC ITEM IDS (use exactly these ids):
{id_map["mapping_text"]}

RUBRICS:
{rubrics_text}

ORIGINAL QUERY:
{query_text}

REFERENCE ATTACHMENT (source PDF):
{attachment_text}

SUBMITTED DOCUMENT (Phase 1 output):
{phase1_text}

SCORING RULES:
- hard_constraints: 0 (fail) or 1 (pass) per item
- soft_constraints: 0–4 per item based on tier descriptions in rubrics
- optional_constraints: 0 (absent) or 1 (present) per item
- Grade EVERY rubric item listed above. Do not skip any.
- Be strict. If evidence is missing or vague, score low.
- For items with needs_reference=是, verify facts against the attachment.

Output ONLY valid JSON, no markdown fences, no explanation outside JSON:
{{
  "hard_constraints": [{{"id": "H01", "score": 1, "reason": "..."}}],
  "soft_constraints": [{{"id": "S01", "score": 3, "reason": "..."}}],
  "optional_constraints": [{{"id": "O01", "score": 1, "reason": "..."}}],
  "score_breakdown": {{
    "hard_score": 0, "hard_max": 0,
    "soft_score": 0, "soft_max": 0,
    "optional_score": 0, "optional_max": 0,
    "final_score": 0.0
  }},
  "overall_comment": "..."
}}"""

    last_error: Exception | None = None
    raw = ""

    for attempt in range(MAX_GRADING_ATTEMPTS):
        try:
            response = call_chat_completion(
                client,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )

            raw = _strip_json_fences(response.choices[0].message.content or "")
            data = json.loads(raw)
            data = _normalize_grading_data(data, rubrics)
            result = GradingResult(**data)
            return recalculate_scores(result, rubrics_path)

        except PipelineError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < MAX_GRADING_ATTEMPTS - 1:
                print(f"[Phase 2] 第 {attempt + 1} 次尝试失败，重试... ({exc})")

    raise PipelineError(
        "E005",
        f"Grading JSON 校验失败（{MAX_GRADING_ATTEMPTS} 次重试后）: {last_error}",
    )
