"""结构化报告 JSON → Markdown / ExecutiveReport。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aarrr_agent.report_models import AARRRStage, ExecutiveReport, MetricCard, WarningRow


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


def structured_to_markdown(report: StructuredReport) -> str:
    """将结构化报告转为 Markdown（含证据引用）。"""
    lines = [f"# {report.title}", ""]

    es = report.executive_summary
    if es:
        lines.extend(["## 管理层摘要", ""])
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
