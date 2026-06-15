"""测试：评审报告生成与总评清洗。"""

from aarrr_agent.grading_report import (
    build_display_comment,
    finalize_grading_result,
    sanitize_overall_comment,
)
from aarrr_agent.schemas import (
    GradingResult,
    HardConstraint,
    OptionalConstraint,
    ScoreBreakdown,
    SoftConstraint,
)


def _sample_result(overall_comment: str) -> GradingResult:
    return GradingResult(
        hard_constraints=[HardConstraint(id=f"H{i:02d}", score=1, reason="满足") for i in range(1, 16)],
        soft_constraints=[SoftConstraint(id=f"S{i:02d}", score=4, reason="良好") for i in range(1, 7)],
        optional_constraints=[
            OptionalConstraint(id="O01", score=1, reason="已满足"),
            OptionalConstraint(id="O02", score=0, reason="缺少转化漏斗可视化"),
            OptionalConstraint(id="O03", score=1, reason="已满足"),
        ],
        score_breakdown=ScoreBreakdown(
            hard_score=0, hard_max=0, soft_score=0, soft_max=0,
            optional_score=0, optional_max=0, final_score=0,
        ),
        overall_comment=overall_comment,
    )


def test_sanitize_overall_comment_removes_wrong_score():
    raw = "Document quality is good. The final score is 0.976."
    cleaned = sanitize_overall_comment(raw)
    assert "0.976" not in cleaned
    assert "final score" not in cleaned.lower()


def test_finalize_grading_result_uses_program_score_in_comment():
    from pathlib import Path

    from aarrr_agent.tools import read_pdf

    attachment = ""
    fixture = Path("fixtures/attachment.pdf")
    if fixture.exists():
        attachment = read_pdf(str(fixture))

    result = finalize_grading_result(
        _sample_result("The final score is 0.976. 报告结构完整。"),
        "fixtures/rubrics.json",
        attachment_text=attachment,
    )
    assert result.score_breakdown.final_score > 70
    assert "0.976" not in result.overall_comment
    assert "程序核定最终得分" in result.overall_comment
    assert f"{result.score_breakdown.final_score:.2f}" in result.overall_comment


def test_build_display_comment_lists_unmet_optional():
    result = finalize_grading_result(_sample_result("整体较好。"), "fixtures/rubrics.json")
    comment = build_display_comment(result, "fixtures/rubrics.json")
    assert "O02" in comment or "缺口" in comment
