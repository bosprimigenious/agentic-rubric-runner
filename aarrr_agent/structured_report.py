"""结构化报告 JSON → Markdown / ExecutiveReport。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, model_validator

from aarrr_agent.report_models import AARRRStage, ExecutiveReport, MetricCard, WarningRow


def _format_action_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        parts: list[str] = []
        for key in ("priority", "action", "timeline", "description", "title", "owner"):
            val = item.get(key)
            if val:
                parts.append(str(val))
        if parts:
            return " · ".join(parts)
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def _format_alert_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        parts: list[str] = []
        for key in ("condition", "threshold", "action", "description", "response", "trigger"):
            val = item.get(key)
            if val:
                parts.append(str(val))
        if parts:
            return "；".join(parts)
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def _coerce_warning_rules(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        rows: list[dict[str, Any]] = []
        for row in value:
            if isinstance(row, dict):
                rows.append(
                    {
                        "metric": str(
                            row.get("metric") or row.get("indicator") or row.get("name") or ""
                        ),
                        "green": str(row.get("green") or row.get("normal") or ""),
                        "yellow": str(row.get("yellow") or ""),
                        "red": str(row.get("red") or ""),
                    }
                )
            else:
                rows.append({"metric": str(row), "green": "", "yellow": "", "red": ""})
        return rows

    if not isinstance(value, dict):
        return []

    if any(k in value for k in ("metric", "green", "yellow", "red", "normal")):
        return _coerce_warning_rules([value])

    merged: dict[str, dict[str, str]] = {}
    for level, col in (
        ("yellow_alerts", "yellow"),
        ("red_alerts", "red"),
        ("green_alerts", "green"),
        ("alerts", "yellow"),
    ):
        alerts = value.get(level)
        if not isinstance(alerts, list):
            continue
        for idx, item in enumerate(alerts):
            if isinstance(item, dict):
                metric = str(
                    item.get("metric")
                    or item.get("indicator")
                    or item.get("name")
                    or f"指标{idx + 1}"
                )
            else:
                metric = f"指标{idx + 1}"
            merged.setdefault(metric, {"metric": metric, "green": "", "yellow": "", "red": ""})
            merged[metric][col] = _format_alert_item(item)

    if merged:
        return list(merged.values())

    return [
        {"metric": str(key), "yellow": _format_alert_item(val)}
        for key, val in value.items()
        if not isinstance(val, (list, dict)) or key.endswith("_alerts")
    ]


def _coerce_aarrr_stages(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"stage": str(item)} for item in value]
    if isinstance(value, dict):
        stages: list[dict[str, Any]] = []
        for key, item in value.items():
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("stage", key)
                stages.append(row)
            else:
                stages.append({"stage": str(key), "health_metric": str(item)})
        return stages
    return []


def coerce_structured_report_data(data: Any) -> dict[str, Any]:
    """将 LLM 常见 JSON 变体归一化为 StructuredReport 可接受形状。"""
    if not isinstance(data, dict):
        return {"title": str(data or "增长指标体系报告")}

    out = dict(data)

    if isinstance(out.get("executive_summary"), str):
        out["executive_summary"] = {"overview": out["executive_summary"]}
    elif out.get("executive_summary") is None:
        out["executive_summary"] = {}

    ns = out.get("north_star_metric")
    if isinstance(ns, str):
        out["north_star_metric"] = {"name": ns}
    elif ns is None:
        out["north_star_metric"] = {}

    out["aarrr_stages"] = _coerce_aarrr_stages(out.get("aarrr_stages"))
    out["warning_rules"] = _coerce_warning_rules(out.get("warning_rules"))

    action_plan = out.get("action_plan")
    if isinstance(action_plan, list):
        out["action_plan"] = [_format_action_item(item) for item in action_plan]
    elif isinstance(action_plan, dict):
        out["action_plan"] = [_format_action_item(action_plan)]
    elif action_plan is None:
        out["action_plan"] = []
    else:
        out["action_plan"] = [_format_action_item(action_plan)]

    refs = out.get("evidence_refs")
    if isinstance(refs, str):
        out["evidence_refs"] = [refs]
    elif refs is None:
        out["evidence_refs"] = []

    appendix = out.get("appendix_sections")
    if appendix is None:
        out["appendix_sections"] = []
    elif isinstance(appendix, dict):
        out["appendix_sections"] = [appendix]

    cadence = out.get("review_cadence")
    if isinstance(cadence, str):
        out["review_cadence"] = {"overview": cadence}
    elif cadence is None:
        out["review_cadence"] = {}

    out.setdefault("title", "增长指标体系报告")
    return out


class StructuredReport(BaseModel):
    title: str
    executive_summary: dict[str, Any] = Field(default_factory=dict)
    north_star_metric: dict[str, Any] = Field(default_factory=dict)
    aarrr_stages: list[dict[str, Any]] = Field(default_factory=list)
    warning_rules: list[dict[str, Any]] = Field(default_factory=list)
    review_cadence: dict[str, Any] = Field(default_factory=dict)
    action_plan: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    appendix_sections: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_payload(cls, data: Any) -> Any:
        return coerce_structured_report_data(data)


def structured_to_markdown(report: StructuredReport) -> str:
    """将结构化报告转为 Markdown（含证据引用）。"""
    lines = [f"# {report.title}", ""]

    es = report.executive_summary
    if es:
        lines.extend(["## 管理层摘要", ""])
        overview = es.get("overview") or es.get("summary")
        if overview:
            lines.append(str(overview))
            lines.append("")
        for key in ("north_star", "key_risks", "priority_actions"):
            val = es.get(key)
            if isinstance(val, list):
                lines.append(f"**{key}**：")
                lines.extend(f"- {item}" for item in val)
            elif val:
                lines.append(f"**{key}**：{val}")
        lines.append("")

    ns = report.north_star_metric
    if ns:
        lines.extend(["## 北极星指标", ""])
        name = ns.get("name") or ns.get("metric") or ""
        if name:
            lines.append(f"**{name}**")
        reason = ns.get("reason") or ns.get("rationale") or ""
        if reason:
            lines.append(reason)
        refs = ns.get("evidence_refs") or report.evidence_refs[:2]
        if refs:
            lines.append(f"证据引用：{', '.join(f'[{r}]' for r in refs)}")
        lines.append("")

    if report.aarrr_stages:
        lines.extend(
            [
                "## AARRR 指标看板",
                "",
                "| 阶段 | 健康指标 | 诊断指标 | 预警 |",
                "|------|----------|----------|------|",
            ]
        )
        for stage in report.aarrr_stages:
            diag = stage.get("diagnostic_metrics") or stage.get("diagnostics") or []
            if isinstance(diag, list):
                diag_text = "、".join(str(d) for d in diag)
            else:
                diag_text = str(diag)
            lines.append(
                f"| {stage.get('stage', stage.get('name', ''))} "
                f"| {stage.get('health_metric', '')} "
                f"| {diag_text} "
                f"| {stage.get('warning', '')} |"
            )
        lines.append("")

    if report.warning_rules:
        lines.extend(
            [
                "## 预警规则",
                "",
                "| 指标 | 正常 | 黄色预警 | 红色预警 |",
                "|------|------|----------|----------|",
            ]
        )
        for row in report.warning_rules:
            lines.append(
                f"| {row.get('metric', '')} "
                f"| {row.get('green', row.get('normal', ''))} "
                f"| {row.get('yellow', '')} "
                f"| {row.get('red', '')} |"
            )
        lines.append("")

    rc = report.review_cadence
    if rc:
        lines.extend(["## 复盘节奏", ""])
        for period in ("weekly", "monthly", "quarterly", "周度", "月度", "季度"):
            if period in rc:
                lines.append(f"- **{period}**：{rc[period]}")
        lines.append("")

    if report.action_plan:
        lines.extend(["## 行动建议", ""])
        lines.extend(f"- {item}" for item in report.action_plan)
        lines.append("")

    for sec in report.appendix_sections:
        title = sec.get("title", "附录")
        body = sec.get("body", "")
        lines.extend([f"## {title}", "", body, ""])

    if report.evidence_refs:
        lines.extend(["## 证据索引", ""])
        lines.extend(f"- [{ref}]" for ref in report.evidence_refs)
        lines.append("")

    return "\n".join(lines)


def structured_to_executive_report(
    report: StructuredReport,
    *,
    run_id: str = "",
    model: str = "",
) -> ExecutiveReport:
    ns_name = report.north_star_metric.get("name") or report.north_star_metric.get("metric") or ""
    es = report.executive_summary
    bullets: list[str] = []
    for key in ("priority_actions", "key_risks"):
        val = es.get(key)
        if isinstance(val, list):
            bullets.extend(str(v) for v in val[:3])

    cards: list[MetricCard] = []
    if ns_name:
        cards.append(MetricCard(label="北极星指标", value=ns_name))
    if bullets:
        cards.append(MetricCard(label="优先动作", value=bullets[0][:40]))

    stages: list[AARRRStage] = []
    for s in report.aarrr_stages:
        diag = s.get("diagnostic_metrics") or s.get("diagnostics") or []
        stages.append(
            AARRRStage(
                name=str(s.get("stage", s.get("name", ""))),
                health_metric=str(s.get("health_metric", "")),
                diagnostic_metrics=[str(d) for d in diag] if isinstance(diag, list) else [],
                warning=str(s.get("warning", "")),
            )
        )

    warnings: list[WarningRow] = []
    for row in report.warning_rules:
        warnings.append(
            WarningRow(
                metric=str(row.get("metric", "")),
                green=str(row.get("green", row.get("normal", ""))),
                yellow=str(row.get("yellow", "")),
                red=str(row.get("red", "")),
            )
        )

    return ExecutiveReport(
        title=report.title,
        north_star=ns_name,
        north_star_reason=str(report.north_star_metric.get("reason", "")),
        summary_bullets=bullets,
        summary_cards=cards[:3],
        aarrr_stages=stages,
        warning_rows=warnings,
        run_id=run_id,
        model=model,
    )
