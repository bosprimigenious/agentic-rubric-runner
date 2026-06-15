"""Typer CLI 入口：run / grade / validate。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from openai import OpenAI
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from aarrr_agent.agent import run_phase1_agent
from aarrr_agent.errors import PipelineError
from aarrr_agent.grader import run_phase2_grader
from aarrr_agent.reporting import print_score_summary
from aarrr_agent.schemas import GradingResult
from aarrr_agent.tools import save_trace

app = typer.Typer(
    name="aarrr-agent",
    help="Agentic document evaluation pipeline — Phase 1 generates PDF, Phase 2 grades it.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def make_client() -> OpenAI:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        console.print("[red]错误：请设置环境变量 DEEPSEEK_API_KEY[/red]")
        raise typer.Exit(1)
    return OpenAI(
        api_key=key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


@app.command()
def run(
    query: Path = typer.Option(..., "--query", help="任务描述 query.txt"),
    pdf: Path = typer.Option(..., "--pdf", help="附件 PDF"),
    rubrics: Path = typer.Option(..., "--rubrics", help="评分标准 rubrics.json（仅 Phase 2）"),
    phase1_out: Path = typer.Option(Path("phase1_output.pdf"), "--phase1-out"),
    grading_out: Path = typer.Option(Path("grading_result.json"), "--grading-out"),
    trace_out: Path = typer.Option(Path("agent_trace.jsonl"), "--trace-out"),
    model: str = typer.Option("deepseek-chat", "--model", envvar="DEEPSEEK_MODEL"),
    skip_phase2: bool = typer.Option(False, "--skip-phase2", help="仅运行 Phase 1"),
) -> None:
    """完整双阶段流水线：Agent 生成报告 + Rubric 自动评分。"""
    client = make_client()
    trace: list[dict] = []
    md_path = phase1_out.with_suffix(".md")

    console.rule("[bold blue]Phase 1 — Agent 生成报告")
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Agent 运行中...", total=None)
            run_phase1_agent(
                query_path=str(query),
                pdf_path=str(pdf),
                pdf_output_path=str(phase1_out),
                client=client,
                model=model,
                trace=trace,
                emergency_trace_path=str(trace_out.with_name("agent_trace_emergency.jsonl")),
            )
            progress.update(task, description="[green]Phase 1 完成")
    except PipelineError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    save_trace(trace, str(trace_out))
    console.print(f"[green]✓[/green] Phase 1 PDF → {phase1_out}")
    console.print(f"[green]✓[/green] Markdown  → {md_path}")
    console.print(f"[green]✓[/green] Trace     → {trace_out}")

    if skip_phase2:
        raise typer.Exit(0)

    console.rule("[bold blue]Phase 2 — Rubric 评分")
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("评分中...", total=None)
            result = run_phase2_grader(
                phase1_pdf_path=str(phase1_out),
                phase1_md_path=str(md_path),
                rubrics_path=str(rubrics),
                query_path=str(query),
                attachment_pdf_path=str(pdf),
                client=client,
                model=model,
            )
            progress.update(task, description="[green]Phase 2 完成")
    except PipelineError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    grading_out.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"[green]✓[/green] 评分结果 → {grading_out}")
    print_score_summary(result)


@app.command()
def grade(
    phase1: Path = typer.Option(..., "--phase1", help="Phase 1 输出 PDF"),
    rubrics: Path = typer.Option(..., "--rubrics", help="评分标准 rubrics.json"),
    query: Path = typer.Option(..., "--query", help="原始 query.txt"),
    attachment: Path = typer.Option(..., "--attachment", help="原始附件 PDF"),
    out: Path = typer.Option(Path("grading_result.json"), "--out"),
    model: str = typer.Option("deepseek-chat", "--model", envvar="DEEPSEEK_MODEL"),
) -> None:
    """单独运行 Phase 2 评分。"""
    client = make_client()
    md_path = phase1.with_suffix(".md")
    try:
        result = run_phase2_grader(
            phase1_pdf_path=str(phase1),
            phase1_md_path=str(md_path),
            rubrics_path=str(rubrics),
            query_path=str(query),
            attachment_pdf_path=str(attachment),
            client=client,
            model=model,
        )
    except PipelineError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    out.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]✓[/green] {out}")
    print_score_summary(result)


@app.command()
def validate(
    result_file: Path = typer.Argument(..., help="grading_result.json 路径"),
) -> None:
    """校验 grading_result.json 并打印评分摘要。"""
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        result = GradingResult(**data)
        console.print("[green]✓ JSON 结构合法，Pydantic 校验通过[/green]")
        print_score_summary(result)
    except (json.JSONDecodeError, ValidationError, OSError) as exc:
        console.print(f"[red]✗ 校验失败: {exc}[/red]")
        raise typer.Exit(1) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
