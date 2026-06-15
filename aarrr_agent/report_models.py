"""结构化报告数据模型（HTML 模板渲染用）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MetricCard(BaseModel):
    label: str
    value: str


class AARRRStage(BaseModel):
    name: str
    health_metric: str = ""
    diagnostic_metrics: list[str] = Field(default_factory=list)
    warning: str = ""


class ReportSection(BaseModel):
    title: str
    anchor: str
    body_html: str


class WarningRow(BaseModel):
    metric: str
    green: str = ""
    yellow: str = ""
    red: str = ""


class ExecutiveReport(BaseModel):
    title: str = "增长指标体系报告"
    subtitle: str = "北极星指标 · 五阶段看板 · 预警机制 · 复盘节奏"
    north_star: str = ""
    north_star_reason: str = ""
    summary_bullets: list[str] = Field(default_factory=list)
    summary_cards: list[MetricCard] = Field(default_factory=list)
    aarrr_stages: list[AARRRStage] = Field(default_factory=list)
    warning_rows: list[WarningRow] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    run_id: str = ""
    model: str = ""
    generated_at: str = ""
