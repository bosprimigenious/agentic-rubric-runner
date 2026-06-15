"""测试：Pydantic Schema 校验。"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aarrr_agent.schemas import GradingResult, SoftConstraint


def test_grading_result_from_fixture_sample():
    sample = {
        "hard_constraints": [{"id": "H01", "score": 1, "reason": "ok"}],
        "soft_constraints": [{"id": "S01", "score": 3, "reason": "ok"}],
        "optional_constraints": [{"id": "O01", "score": 0, "reason": "n/a"}],
        "score_breakdown": {
            "hard_score": 1,
            "hard_max": 1,
            "soft_score": 3,
            "soft_max": 4,
            "optional_score": 0,
            "optional_max": 1,
            "final_score": 72.5,
        },
        "overall_comment": "test",
    }
    result = GradingResult(**sample)
    assert result.hard_constraints[0].score == 1


def test_soft_score_out_of_range():
    with pytest.raises(ValidationError):
        SoftConstraint(id="S01", score=5, reason="bad")


def test_grading_result_json_roundtrip():
    path = Path("fixtures/rubrics.json")
    assert path.exists()
    # 仅验证 rubrics 文件可被读取；完整 grading 由 recalculate 测试覆盖
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "rubric" in data
