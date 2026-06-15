"""Pydantic 校验 Schema。"""

from typing import Literal

from pydantic import BaseModel, field_validator


class HardConstraint(BaseModel):
    id: str
    score: Literal[0, 1]
    reason: str


class SoftConstraint(BaseModel):
    id: str
    score: int
    reason: str

    @field_validator("score")
    @classmethod
    def check_score_range(cls, v: int) -> int:
        if not 0 <= v <= 4:
            raise ValueError(f"soft score 必须在 0-4 之间，得到 {v}")
        return v


class OptionalConstraint(BaseModel):
    id: str
    score: Literal[0, 1]
    reason: str


class ScoreBreakdown(BaseModel):
    hard_score: int
    hard_max: int
    soft_score: int
    soft_max: int
    optional_score: int
    optional_max: int
    final_score: float


class GradingResult(BaseModel):
    hard_constraints: list[HardConstraint]
    soft_constraints: list[SoftConstraint]
    optional_constraints: list[OptionalConstraint]
    score_breakdown: ScoreBreakdown
    overall_comment: str
