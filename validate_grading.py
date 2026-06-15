"""独立验证 grading_result.json 的 Pydantic 结构。"""

from __future__ import annotations

import json
import sys

from pydantic import ValidationError

from aarrr_agent.schemas import GradingResult


def _fmt_hard(score: int) -> str:
    return "✓" if score == 1 else "✗"


def _fmt_optional(score: int) -> str:
    return "✓" if score == 1 else "✗"


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "grading_result.json"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    try:
        result = GradingResult(**data)
    except ValidationError as exc:
        print(f"✗ 校验失败: {exc}")
        sys.exit(1)

    bd = result.score_breakdown
    print("✓ JSON 结构合法")
    print("✓ Pydantic schema 校验通过")
    print()
    print(f"Hard Constraints:  {bd.hard_score}/{bd.hard_max}")
    hard_line = " ".join(f"{c.id}{_fmt_hard(c.score)}" for c in result.hard_constraints)
    print(f"  {hard_line}")
    print()
    print(f"Soft Constraints:  {bd.soft_score}/{bd.soft_max}")
    soft_line = " ".join(f"{c.id}={c.score}" for c in result.soft_constraints)
    print(f"  {soft_line}")
    print()
    print(f"Optional:          {bd.optional_score}/{bd.optional_max}")
    opt_line = " ".join(f"{c.id}{_fmt_optional(c.score)}" for c in result.optional_constraints)
    print(f"  {opt_line}")
    print()
    print(f"Final Score: {bd.final_score} / 100")
    print()
    print(f"Overall: {result.overall_comment}")


if __name__ == "__main__":
    main()
