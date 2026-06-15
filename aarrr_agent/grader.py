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
from aarrr_agent.grading_report import finalize_grading_result
from aarrr_agent.retrieval import build_retrieval_keywords, retrieve_relevant_pages
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
                item = dict(by_id[cid])
                item.setdefault("evidence", [])
                item.setdefault("missing", [])
                normalized.append(item)
            else:
                normalized.append(
                    {
                        "id": cid,
                        "score": 0,
                        "evidence": [],
                        "missing": ["评分项缺失"],
                        "reason": "评分项缺失，默认 0 分",
                    }
                )
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
    加权公式（hard_max / soft_max / optional_max 从 rubrics.json 动态计算）：
      final = (hard/hard_max)×50 + (soft/soft_max)×30 + (optional/optional_max)×20
    """
    rubrics = load_rubrics(rubrics_path)
    rubric = rubrics["rubric"]

    hard_score = sum(c.score for c in result.hard_constraints)
    hard_max = len(rubric["hard_constraints"])

    soft_score = sum(c.score for c in result.soft_constraints)
    soft_max = len(rubric["soft_constraints"]) * 4

    optional_score = sum(c.score for c in result.optional_constraints)
    optional_max = len(rubric["optional_constraints"])

    hard_rate = hard_score / hard_max if hard_max else 0.0
    soft_rate = soft_score / soft_max if soft_max else 0.0
    optional_rate = optional_score / optional_max if optional_max else 0.0
    final_score = round(hard_rate * 50 + soft_rate * 30 + optional_rate * 20, 2)

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
    attachment_raw = _clean_extracted_text(read_pdf(attachment_pdf_path))
    keywords = build_retrieval_keywords(rubrics, query_text)
    attachment_text = retrieve_relevant_pages(attachment_raw, keywords=keywords)

    prompt = f"""你是一名严格、保守的文档评审员。请根据以下评分标准，对候选人提交的文档逐项打分。

评分条目编号（reason 中必须使用这些 id）：
{id_map["mapping_text"]}

评分标准（rubrics.json）：
{rubrics_text}

原始任务（query）：
{query_text}

参考附件（事实来源，不得引入附件之外的信息；以下为检索到的相关页）：
{attachment_text}

待评文档（Phase 1 产出）：
候选人提交了 PDF：{phase1_pdf_path}
以下为该 PDF 对应的 Markdown 源文（优先以此评分）。
若 PDF 由该内容生成，则“输出为 PDF”类硬约束视为满足。

{phase1_text}

评分规则：
- hard_constraints：每项 0（未满足）或 1（满足）
- soft_constraints：每项 0–4 分，严格对照 rubrics 中各档描述
- optional_constraints：每项 0（未满足）或 1（已满足）
- 每项必须提供 evidence（支持给分的证据）与 missing（缺失点），无则填空数组
- 必须对每一条 rubric 评分，不得遗漏
- 若附件与社交电商/AARRR 增长无关（如农业、DNS 实验、课程报告），needs_reference=是 的硬约束必须 0 分
- 证据不足、表述模糊、仅“隐含/implied”而未明确呈现时，应给低分
- needs_reference=是 的条目，reason 必须注明附件出处，格式：[来源: 第3页] 或 [来源: 章节名]
- 不得将行业常识、外部 benchmark 当作附件事实；附件未写明的内容不能作为给分依据
- 可视化/图表类要求：必须有明确图表或漏斗结构，不能仅凭“AARRR 结构隐含漏斗”给满分
- 软约束给分保守：完全满足才给 4 分；部分满足 2–3 分；明显缺失 0–1 分
- 所有 reason 与 overall_comment 必须使用中文
- overall_comment 只做定性总评，禁止出现任何分数、百分比、final_score、score_breakdown

仅输出合法 JSON，不要 markdown 代码块，不要 JSON 之外的解释：
{{
  "hard_constraints": [{{"id": "H01", "score": 1, "evidence": ["..."], "missing": [], "reason": "..."}}],
  "soft_constraints": [{{"id": "S01", "score": 3, "evidence": ["..."], "missing": ["..."], "reason": "..."}}],
  "optional_constraints": [{{"id": "O01", "score": 0, "evidence": [], "missing": ["..."], "reason": "..."}}],
  "score_breakdown": {{
    "hard_score": 0, "hard_max": 0,
    "soft_score": 0, "soft_max": 0,
    "optional_score": 0, "optional_max": 0,
    "final_score": 0.0
  }},
  "overall_comment": "用中文写定性评价，不要写分数。"
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
            return finalize_grading_result(
                result,
                rubrics_path,
                attachment_text=attachment_raw,
                query_text=query_text,
                report_text=phase1_text,
            )

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
