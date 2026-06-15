"""评审报告生成、总评清洗与管理层摘要。"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

from aarrr_agent.schemas import GradingResult

_SCORE_LINE_PATTERNS = (
    r"(?i)\bfinal\s+score\b[^.\n]{0,40}[\d.]+%?",
    r"(?i)\boverall\s+score\b[^.\n]{0,40}[\d.]+%?",
    r"(?i)\bscore\s+breakdown\b[^.\n]{0,80}",
    r"最终得分[：:为是]?\s*[\d.]+%?",
    r"总分[：:为是]?\s*[\d.]+%?",
    r"综合得分[：:为是]?\s*[\d.]+%?",
    r"final_score[：:为是]?\s*[\d.]+%?",
    r"得分[：:为是]\s*0?\.\d{1,3}\b",
    r"The final score is\s*[\d.]+%?",
)


def _load_rubrics(rubrics_path: str) -> dict[str, Any]:
    return json.loads(Path(rubrics_path).read_text(encoding="utf-8"))


def sanitize_overall_comment(text: str) -> str:
    """移除模型总评中自报的分数，避免与程序重算结果矛盾。"""
    cleaned = text.strip()
    for pattern in _SCORE_LINE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip(" \n-—·")


def _constraint_description_map(rubrics: dict[str, Any]) -> dict[str, str]:
    rubric = rubrics["rubric"]
    mapping: dict[str, str] = {}
    for prefix, key in (("H", "hard_constraints"), ("S", "soft_constraints"), ("O", "optional_constraints")):
        for i, item in enumerate(rubric[key], 1):
            mapping[f"{prefix}{i:02d}"] = item["description"]
    return mapping


def collect_gaps(result: GradingResult, rubrics_path: str) -> list[dict[str, str]]:
    """提取未通过硬约束、未满足可选项、软约束低分项。"""
    rubrics = _load_rubrics(rubrics_path)
    desc_map = _constraint_description_map(rubrics)
    gaps: list[dict[str, str]] = []

    for item in result.hard_constraints:
        if not item.score:
            gaps.append(
                {
                    "id": item.id,
                    "level": "硬约束",
                    "title": desc_map.get(item.id, item.id),
                    "detail": item.reason,
                }
            )

    for item in result.soft_constraints:
        if item.score < 3:
            gaps.append(
                {
                    "id": item.id,
                    "level": "软约束",
                    "title": desc_map.get(item.id, item.id),
                    "detail": f"得分 {item.score}/4 — {item.reason}",
                }
            )

    for item in result.optional_constraints:
        if not item.score:
            gaps.append(
                {
                    "id": item.id,
                    "level": "可选项",
                    "title": desc_map.get(item.id, item.id),
                    "detail": item.reason,
                }
            )

    return gaps


def build_action_items(gaps: list[dict[str, str]], limit: int = 3) -> list[str]:
    actions: list[str] = []
    for gap in gaps[:limit]:
        title = gap["title"]
        if "可视化" in title or "漏斗" in title:
            actions.append(f"补充 {gap['id']} 相关图表或漏斗可视化")
        elif gap["level"] == "硬约束":
            actions.append(f"优先修复 {gap['id']}：{title}")
        else:
            actions.append(f"加强 {gap['id']}：{title}")
    if not actions:
        actions.append("维持当前质量，按周/月/季节奏持续复盘指标")
    return actions


def build_executive_summary(result: GradingResult, rubrics_path: str) -> dict[str, Any]:
    bd = result.score_breakdown
    gaps = collect_gaps(result, rubrics_path)
    failed_hard = [g for g in gaps if g["level"] == "硬约束"]

    if failed_hard:
        verdict = "未通过"
    elif bd.final_score >= 85:
        verdict = "通过"
    elif bd.final_score >= 60:
        verdict = "待改进"
    else:
        verdict = "未通过"

    gap_labels = [f"{g['id']} {g['title']}" for g in gaps[:3]]
    actions = build_action_items(gaps)

    return {
        "verdict": verdict,
        "final_score": bd.final_score,
        "hard_score": bd.hard_score,
        "hard_max": bd.hard_max,
        "soft_score": bd.soft_score,
        "soft_max": bd.soft_max,
        "optional_score": bd.optional_score,
        "optional_max": bd.optional_max,
        "gaps": gaps,
        "gap_labels": gap_labels,
        "gaps_text": "；".join(gap_labels) if gap_labels else "无明显缺口",
        "actions": actions,
        "actions_text": "；".join(actions),
    }


def build_display_comment(result: GradingResult, rubrics_path: str) -> str:
    """生成程序可信的总评文本（含核定分数 + 定性评价）。"""
    summary = build_executive_summary(result, rubrics_path)
    qualitative = sanitize_overall_comment(result.overall_comment)

    lines = [
        f"程序核定最终得分：{summary['final_score']:.2f} / 100（{summary['verdict']}）",
        (
            f"硬约束 {summary['hard_score']}/{summary['hard_max']} · "
            f"软约束 {summary['soft_score']}/{summary['soft_max']} · "
            f"可选项 {summary['optional_score']}/{summary['optional_max']}"
        ),
    ]
    if summary["gap_labels"]:
        lines.append(f"主要缺口：{summary['gaps_text']}")
    lines.append(f"建议动作：{summary['actions_text']}")
    if qualitative:
        lines.extend(["", "评审意见：", qualitative])
    return "\n".join(lines)


def finalize_grading_result(
    result: GradingResult,
    rubrics_path: str,
    *,
    attachment_text: str = "",
    query_text: str = "",
    report_text: str = "",
) -> GradingResult:
    """校准、附件门控、重算分数并生成可信总评。"""
    from aarrr_agent.attachment_relevance import enforce_attachment_gate
    from aarrr_agent.grading_calibration import calibrate_grading_result
    from aarrr_agent.grader import recalculate_scores

    rubrics = _load_rubrics(rubrics_path)
    result = calibrate_grading_result(result)
    if attachment_text.strip():
        result, assessment = enforce_attachment_gate(
            result,
            rubrics,
            attachment_text,
            query_text,
            report_text=report_text,
        )
    result = recalculate_scores(result, rubrics_path)
    result.overall_comment = build_display_comment(result, rubrics_path)
    return result


def render_grading_report_md(result: GradingResult, rubrics_path: str) -> str:
    summary = build_executive_summary(result, rubrics_path)
    bd = result.score_breakdown
    lines = [
        "# 评审报告",
        "",
        "## 管理层摘要",
        "",
        f"- **评审结论**：{summary['verdict']}",
        f"- **最终得分**：{bd.final_score:.2f} / 100",
        f"- **硬约束**：{bd.hard_score} / {bd.hard_max}",
        f"- **软约束**：{bd.soft_score} / {bd.soft_max}",
        f"- **可选项**：{bd.optional_score} / {bd.optional_max}",
        f"- **主要缺口**：{summary['gaps_text']}",
        f"- **建议动作**：{summary['actions_text']}",
        "",
        "## 总评",
        "",
        result.overall_comment,
        "",
        "## 主要缺口",
        "",
    ]

    if summary["gaps"]:
        for gap in summary["gaps"]:
            lines.append(f"- **{gap['id']}**（{gap['level']}）{gap['title']}")
            lines.append(f"  - {gap['detail']}")
    else:
        lines.append("- 无显著缺口")

    lines.extend(["", "## 硬约束明细", ""])
    for item in result.hard_constraints:
        mark = "通过" if item.score else "未通过"
        lines.append(f"- **{item.id}** [{mark}] {item.reason}")

    lines.extend(["", "## 软约束明细", ""])
    for item in result.soft_constraints:
        lines.append(f"- **{item.id}** 得分 {item.score}/4 — {item.reason}")

    lines.extend(["", "## 可选项明细", ""])
    for item in result.optional_constraints:
        mark = "已满足" if item.score else "未满足"
        lines.append(f"- **{item.id}** [{mark}] {item.reason}")

    return "\n".join(lines) + "\n"


def render_grading_report_html(result: GradingResult, rubrics_path: str) -> str:
    summary = build_executive_summary(result, rubrics_path)
    bd = result.score_breakdown
    verdict_color = "#15803d" if summary["verdict"] == "通过" else "#b45309"
    if summary["verdict"] == "未通过":
        verdict_color = "#b91c1c"

    gap_items = "".join(
        f"<li><strong>{escape(g['id'])}</strong>（{escape(g['level'])}）"
        f"{escape(g['title'])}<br><span class='muted'>{escape(g['detail'])}</span></li>"
        for g in summary["gaps"]
    ) or "<li>无显著缺口</li>"

    def _rows(items, score_fmt):
        return "".join(
            f"<tr><td>{escape(i.id)}</td><td>{score_fmt(i)}</td>"
            f"<td>{escape(i.reason)}</td></tr>"
            for i in items
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>评审报告</title>
  <style>
    body {{ font-family: "Microsoft YaHei", sans-serif; color: #1e293b; margin: 24px; }}
    h1, h2 {{ color: #1e3a5f; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; margin: 16px 0; background: #f8fafc; }}
    .verdict {{ color: {verdict_color}; font-weight: 700; }}
    .muted {{ color: #64748b; font-size: 0.92rem; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.92rem; }}
    th {{ background: #1e40af; color: #fff; text-align: left; padding: 8px; }}
    td {{ border: 1px solid #cbd5e1; padding: 8px; vertical-align: top; }}
  </style>
</head>
<body>
  <h1>评审报告</h1>
  <div class="card">
    <h2>管理层摘要</h2>
    <p>评审结论：<span class="verdict">{escape(summary['verdict'])}</span></p>
    <p>最终得分：<strong>{bd.final_score:.2f}</strong> / 100</p>
    <p>硬约束 {bd.hard_score}/{bd.hard_max} · 软约束 {bd.soft_score}/{bd.soft_max} · 可选项 {bd.optional_score}/{bd.optional_max}</p>
    <p>主要缺口：{escape(summary['gaps_text'])}</p>
    <p>建议动作：{escape(summary['actions_text'])}</p>
  </div>
  <h2>总评</h2>
  <p>{escape(result.overall_comment).replace(chr(10), '<br>')}</p>
  <h2>主要缺口</h2>
  <ul>{gap_items}</ul>
  <h2>硬约束明细</h2>
  <table><thead><tr><th>编号</th><th>结果</th><th>说明</th></tr></thead>
  <tbody>{_rows(result.hard_constraints, lambda i: '通过' if i.score else '未通过')}</tbody></table>
  <h2>软约束明细</h2>
  <table><thead><tr><th>编号</th><th>得分</th><th>说明</th></tr></thead>
  <tbody>{_rows(result.soft_constraints, lambda i: f'{i.score}/4')}</tbody></table>
  <h2>可选项明细</h2>
  <table><thead><tr><th>编号</th><th>结果</th><th>说明</th></tr></thead>
  <tbody>{_rows(result.optional_constraints, lambda i: '已满足' if i.score else '未满足')}</tbody></table>
</body>
</html>
"""
