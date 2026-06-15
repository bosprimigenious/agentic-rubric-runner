"""测试：附件领域门控。"""

from aarrr_agent.attachment_relevance import (
    assess_attachment_domain,
    detect_forced_analogy_report,
    enforce_attachment_gate,
    h15_failed,
)
from aarrr_agent.grader import load_rubrics
from aarrr_agent.schemas import (
    GradingResult,
    HardConstraint,
    OptionalConstraint,
    ScoreBreakdown,
    SoftConstraint,
)


def test_cherry_pdf_not_relevant():
    text = "大樱桃优质高产栽培技术 土壤施肥 病虫害防治 果树修剪"
    result = assess_attachment_domain(text)
    assert not result["relevant"]
    assert result["off_domain_hit_count"] >= 1


def test_dns_lab_not_relevant():
    text = "DNS 中继服务器 实验报告 计算机网络 配置步骤"
    result = assess_attachment_domain(text)
    assert not result["relevant"]


def test_fixtures_attachment_relevant():
    from pathlib import Path

    from aarrr_agent.tools import read_pdf

    pdf = Path("fixtures/attachment.pdf")
    if not pdf.exists():
        return
    text = read_pdf(str(pdf))
    result = assess_attachment_domain(text)
    assert result["relevant"]


def test_query_does_not_inflate_attachment_relevance():
    dns = "DNS 中继服务器 RCODE select() dnsrelay 实验报告 bupt"
    query = "社交电商 AARRR 获客 激活 留存 变现 传播 北极星"
    result = assess_attachment_domain(dns, query)
    assert not result["relevant"]


def test_detect_forced_analogy_dns_report():
    dns = "DNS 中继服务器 select() RCODE dnsperf"
    report = "北极星指标如同 select() 主循环，获客类比 config_load 加载配置"
    assert detect_forced_analogy_report(report, dns)


def test_gate_caps_score_for_irrelevant_attachment():
    rubrics = load_rubrics("fixtures/rubrics.json")
    result = GradingResult(
        hard_constraints=[
            HardConstraint(id=f"H{i:02d}", score=1, reason="模型给分") for i in range(1, 16)
        ],
        soft_constraints=[
            SoftConstraint(id=f"S{i:02d}", score=4, reason="implied good") for i in range(1, 7)
        ],
        optional_constraints=[
            OptionalConstraint(id=f"O{i:02d}", score=1, reason="ok") for i in range(1, 4)
        ],
        score_breakdown=ScoreBreakdown(
            hard_score=15, hard_max=15, soft_score=24, soft_max=24,
            optional_score=3, optional_max=3, final_score=100,
        ),
        overall_comment="well structured",
    )
    gated, assessment = enforce_attachment_gate(
        result,
        rubrics,
        "大樱桃栽培技术 土壤 病虫害",
    )
    assert not assessment["relevant"]
    assert gated.hard_constraints[0].score == 1  # H01 PDF
    assert gated.hard_constraints[1].score == 0  # H02
    assert gated.hard_constraints[14].score == 0  # H15
    assert all(s.score == 0 for s in gated.soft_constraints)

    from aarrr_agent.grader import recalculate_scores

    final = recalculate_scores(gated, "fixtures/rubrics.json")
    assert final.score_breakdown.final_score < 10


def test_h15_failure_triggers_gate():
    """即使领域检测误判为相关，H15 未通过也应触发程序门控。"""
    rubrics = load_rubrics("fixtures/rubrics.json")
    growth_text = "社交电商 AARRR 用户增长 获客 激活 留存 变现 传播 北极星 GMV"
    result = GradingResult(
        hard_constraints=[
            HardConstraint(id=f"H{i:02d}", score=1, reason="模型给分") for i in range(1, 16)
        ],
        soft_constraints=[
            SoftConstraint(id=f"S{i:02d}", score=4, reason="implied good") for i in range(1, 7)
        ],
        optional_constraints=[
            OptionalConstraint(id=f"O{i:02d}", score=1, reason="ok") for i in range(1, 4)
        ],
        score_breakdown=ScoreBreakdown(
            hard_score=14, hard_max=15, soft_score=24, soft_max=24,
            optional_score=3, optional_max=3, final_score=96.67,
        ),
        overall_comment="well structured",
    )
    result.hard_constraints[14].score = 0
    result.hard_constraints[14].reason = "附件为 DNS 报告，事实不可追溯"

    assert assess_attachment_domain(growth_text)["relevant"]
    assert h15_failed(result)

    gated, assessment = enforce_attachment_gate(
        result,
        rubrics,
        growth_text,
        report_text="正常增长报告，无 DNS 类比",
    )
    assert assessment["relevant"]
    assert gated.hard_constraints[0].score == 1
    assert gated.hard_constraints[1].score == 0
    assert gated.hard_constraints[14].score == 0
    assert all(s.score == 0 for s in gated.soft_constraints)

    from aarrr_agent.grader import recalculate_scores

    final = recalculate_scores(gated, "fixtures/rubrics.json")
    assert final.score_breakdown.final_score < 10
