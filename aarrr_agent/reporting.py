"""CLI 与终端评分摘要输出。"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from aarrr_agent.schemas import GradingResult

console = Console()


def print_score_summary(result: GradingResult) -> None:
    """Rich 表格打印评分摘要。"""
    bd = result.score_breakdown
    table = Table(title=f"最终得分: {bd.final_score:.2f} / 100", show_header=True)
    table.add_column("类型", style="bold")
    table.add_column("得分")
    table.add_column("满分")
    table.add_column("明细")
    table.add_row(
        "硬约束",
        str(bd.hard_score),
        str(bd.hard_max),
        " ".join(
            f"[green]{h.id}[/green]" if h.score else f"[red]{h.id}[/red]"
            for h in result.hard_constraints
        ),
    )
    table.add_row(
        "软约束",
        str(bd.soft_score),
        str(bd.soft_max),
        " ".join(f"{s.id}={s.score}" for s in result.soft_constraints),
    )
    table.add_row(
        "可选项",
        str(bd.optional_score),
        str(bd.optional_max),
        " ".join(
            f"[green]{o.id}[/green]" if o.score else f"[red]{o.id}[/red]"
            for o in result.optional_constraints
        ),
    )
    console.print(table)
    console.print(f"\n[italic]{result.overall_comment}[/italic]")
