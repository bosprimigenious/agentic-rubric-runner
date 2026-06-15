"""测试：Pydantic Schema 校验。"""

import pytest
from pydantic import ValidationError

from aarrr_agent.schemas import GradingResult, SoftConstraint


def test_grading_result_minimal():
    result = GradingResult(
        hard_constraints=[{"id": "H01", "score": 1, "reason": "ok"}],
        soft_constraints=[{"id": "S01", "score": 3, "reason": "ok"}],
        optional_constraints=[{"id": "O01", "score": 0, "reason": "n/a"}],
        score_breakdown={
            "hard_score": 1,
            "hard_max": 1,
            "soft_score": 3,
            "soft_max": 4,
            "optional_score": 0,
            "optional_max": 1,
            "final_score": 72.5,
        },
        overall_comment="test",
    )
    assert result.hard_constraints[0].score == 1


def test_soft_score_out_of_range():
    with pytest.raises(ValidationError):
        SoftConstraint(id="S01", score=5, reason="bad")
