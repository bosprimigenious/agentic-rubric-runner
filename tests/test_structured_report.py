"""测试：结构化报告 JSON → Markdown / ExecutiveReport。"""

from aarrr_agent.structured_report import StructuredReport, structured_to_executive_report, structured_to_markdown

SAMPLE = {
    "title": "社交电商增长指标体系报告",
    "executive_summary": {
        "north_star": "有效交易用户数",
        "priority_actions": ["优化激活路径", "提升7日留存"],
    },
    "north_star_metric": {
        "name": "有效交易用户数",
        "reason": "综合反映增长质量。[E01]",
        "evidence_refs": ["E01"],
    },
    "aarrr_stages": [
        {
            "stage": "获客",
            "health_metric": "新增有效用户数",
            "diagnostic_metrics": ["CAC", "渠道转化率"],
        },
        {"stage": "激活", "health_metric": "首单转化率", "diagnostic_metrics": ["激活漏斗"]},
        {"stage": "留存", "health_metric": "7日留存率", "diagnostic_metrics": ["DAU/MAU"]},
        {"stage": "变现", "health_metric": "GMV", "diagnostic_metrics": ["ARPU"]},
        {"stage": "传播", "health_metric": "裂变系数K", "diagnostic_metrics": ["分享率"]},
    ],
    "warning_rules": [
        {"metric": "CAC/LTV", "green": "<1:3", "yellow": "1:3~1:2", "red": ">1:2"},
    ],
    "review_cadence": {"weekly": "复盘获客激活", "monthly": "复盘留存变现", "quarterly": "战略复盘"},
    "action_plan": ["建立数据看板", "完善预警体系"],
    "evidence_refs": ["E01", "E02"],
}


def test_structured_to_markdown_sections():
    report = StructuredReport.model_validate(SAMPLE)
    md = structured_to_markdown(report)
    assert "北极星指标" in md
    assert "AARRR 指标看板" in md
    assert "预警规则" in md
    assert "[E01]" in md
    assert "获客" in md


def test_structured_to_executive_report():
    report = StructuredReport.model_validate(SAMPLE)
    executive = structured_to_executive_report(report, run_id="20260615_120000")
    assert executive.north_star == "有效交易用户数"
    assert len(executive.aarrr_stages) == 5
