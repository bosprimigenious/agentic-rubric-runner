"""测试：分数重算。"""

from aarrr_agent.grader import recalculate_scores
from aarrr_agent.schemas import (
    GradingResult,
    HardConstraint,
    OptionalConstraint,
    ScoreBreakdown,
    SoftConstraint,
)


def test_recalculate_weighted_score():
    result = GradingResult(
        hard_constraints=[HardConstraint(id=f"H{i:02d}", score=1 if i <= 14 else 0, reason="t") for i in range(1, 16)],
        soft_constraints=[SoftConstraint(id=f"S{i:02d}", score=3, reason="t") for i in range(1, 7)],
        optional_constraints=[
            OptionalConstraint(id=f"O{i:02d}", score=1 if i <= 2 else 0, reason="t") for i in range(1, 4)
        ],
        score_breakdown=ScoreBreakdown(
            hard_score=0, hard_max=0, soft_score=0, soft_max=0,
            optional_score=0, optional_max=0, final_score=0,
        ),
        overall_comment="test",
    )
    result = recalculate_scores(result, "fixtures/rubrics.json")
    assert result.score_breakdown.hard_max == 15
    assert result.score_breakdown.soft_max == 24
    assert result.score_breakdown.optional_max == 3
    hard_part = round(14 / 15 * 50, 2)
    soft_part = round(18 / 24 * 30, 2)
    opt_part = round(2 / 3 * 20, 2)
    expected = round(hard_part + soft_part + opt_part, 2)
    assert result.score_breakdown.final_score == expected
