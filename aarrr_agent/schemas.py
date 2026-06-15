"""Pydantic 校验 Schema。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_ID_PATTERNS = {
    "H": re.compile(r"^H\d{2}$"),
    "S": re.compile(r"^S\d{2}$"),
    "O": re.compile(r"^O\d{2}$"),
}


def _validate_constraint_id(v: str, prefix: str) -> str:
    if not _ID_PATTERNS[prefix].match(v):
        raise ValueError(f"ID 格式错误: {v}，应为 {prefix}01 形式")
    return v


class HardConstraint(BaseModel):
    id: str
    score: Literal[0, 1]
    evidence: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reason: str

    @field_validator("id")
    @classmethod
    def check_id(cls, v: str) -> str:
        return _validate_constraint_id(v, "H")


class SoftConstraint(BaseModel):
    id: str
    score: int
    evidence: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reason: str

    @field_validator("id")
    @classmethod
    def check_id(cls, v: str) -> str:
        return _validate_constraint_id(v, "S")

    @field_validator("score")
    @classmethod
    def check_score_range(cls, v: int) -> int:
        if not 0 <= v <= 4:
            raise ValueError(f"soft score 必须在 0-4 之间，得到 {v}")
        return v


class OptionalConstraint(BaseModel):
    id: str
    score: Literal[0, 1]
    evidence: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reason: str

    @field_validator("id")
    @classmethod
    def check_id(cls, v: str) -> str:
        return _validate_constraint_id(v, "O")


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

    @model_validator(mode="after")
    def check_unique_ids(self) -> GradingResult:
        for group in (
            self.hard_constraints,
            self.soft_constraints,
            self.optional_constraints,
        ):
            ids = [c.id for c in group]
            if len(ids) != len(set(ids)):
                raise ValueError(f"存在重复评分 ID: {ids}")
        return self
