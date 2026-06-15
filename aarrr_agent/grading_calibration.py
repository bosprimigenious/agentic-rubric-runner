"""Phase 2 评分校准：抑制宽松倾向与模糊理由。"""

from __future__ import annotations

import re

from aarrr_agent.schemas import GradingResult, SoftConstraint

_VAGUE = re.compile(
    r"(?i)\b(implied|roughly|seems|appear(s)? to|maybe|probably)\b|似乎|大概|可能|隐含|推断",
)


def calibrate_grading_result(result: GradingResult) -> GradingResult:
    """对模型评分做保守校准。"""
    for item in result.soft_constraints:
        item.score = _calibrate_soft(item)
    for item in result.optional_constraints:
        text = f"{item.reason} {' '.join(item.missing)}"
        if _VAGUE.search(text) and item.score:
            item.score = 0
    return result


def _calibrate_soft(item: SoftConstraint) -> int:
    score = item.score
    text = f"{item.reason} {' '.join(item.evidence)} {' '.join(item.missing)}"

    if _VAGUE.search(text) and score > 2:
        score = min(score, 2)
    if item.missing and score >= 4:
        score = 3
    if not item.evidence and score >= 3:
        score = min(score, 2)
    return score
