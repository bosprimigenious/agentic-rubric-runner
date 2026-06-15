"""独立验证 grading_result.json 的 Pydantic 结构。"""

from __future__ import annotations

import json
import sys

from pydantic import ValidationError

from aarrr_agent.schemas import GradingResult


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "grading_result.json"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    try:
        result = GradingResult(**data)
        print("✓ JSON 结构合法")
        print(f"✓ final_score = {result.score_breakdown.final_score}")
        print(f"  Hard:     {result.score_breakdown.hard_score}/{result.score_breakdown.hard_max}")
        print(f"  Soft:     {result.score_breakdown.soft_score}/{result.score_breakdown.soft_max}")
        print(f"  Optional: {result.score_breakdown.optional_score}/{result.score_breakdown.optional_max}")
    except ValidationError as exc:
        print(f"✗ 校验失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
