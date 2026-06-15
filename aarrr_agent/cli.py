"""Typer CLI：agentic-rubric / aarrr-agent。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import typer
from openai import OpenAI
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from aarrr_agent.config import PROJECT_ROOT
from aarrr_agent.env import load_project_env
from aarrr_agent.errors import PipelineError
from aarrr_agent.grader import run_phase2_grader
from aarrr_agent.pipeline import make_run_id, resolve_output_paths, run_pipeline
from aarrr_agent.reporting import print_score_summary
from aarrr_agent.schemas import GradingResult
from aarrr_agent.tools import save_trace

app = typer.Typer(
    name="agentic-rubric",
    help="轻量、可审计的文档约束型 Agent 工作流：PDF 生成 + Rubric 评分",
    add_completion=False,
    no_args_is_help=True,
)
def _configure_stdio_utf8() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                except Exception:
                    pass


_configure_stdio_utf8()
console = Console(legacy_windows=False)


def make_client() -> OpenAI:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        console.print("[red][E001] 请设置环境变量 DEEPSEEK_API_KEY[/red]")
        raise typer.Exit(1)
    return OpenAI(
        api_key=key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


@app.command()
def run(
    query: Path = typer.Option(..., "--query", help="任务描述 query.txt"),
    pdf: Path = typer.Option(..., "--pdf", help="附件 PDF"),
    rubrics: Path = typer.Option(..., "--rubrics", help="评分标准 rubrics.json"),
    out: Path | None = typer.Option(None, "--out", help="输出目录，例如 outputs/demo"),
    phase1_out: Path | None = typer.Option(None, "--phase1-out", help="覆盖 Phase 1 PDF 路径"),
    grading_out: Path | None = typer.Option(None, "--grading-out", help="覆盖评分 JSON 路径"),
    trace_out: Path | None = typer.Option(None, "--trace-out", help="覆盖 trace 路径"),
    model: str = typer.Option("deepseek-chat", "--model", envvar="DEEPSEEK_MODEL"),
    skip_phase2: bool = typer.Option(False, "--skip-phase2", help="仅运行 Phase 1"),
) -> None:
    """完整双阶段流水线：Agent 生成报告 + Rubric 自动评分。"""
    rid = make_run_id()
    base_out = out if out is not None else Path("outputs") / rid
    paths = resolve_output_paths(base_out, run_id=rid)
    if phase1_out:
        paths.phase1_pdf = phase1_out
        paths.phase1_md = phase1_out.with_suffix(".md")
    if grading_out:
        paths.grading_json = grading_out
    if trace_out:
        paths.trace_jsonl = trace_out

    client = make_client()
    console.rule("[bold blue]Phase 1 + Phase 2 流水线")
    console.print(f"输出目录: [cyan]{paths.directory}[/cyan]  run_id={paths.run_id}")

    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("运行中...", total=None)
            result = run_pipeline(
                query=query,
                pdf=pdf,
                rubrics=rubrics,
                client=client,
                model=model,
                paths=paths,
                skip_phase2=skip_phase2,
            )
            progress.update(task, description="[green]完成")
    except PipelineError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[green]✓[/green] PDF   → {paths.phase1_pdf}")
    console.print(f"[green]✓[/green] MD    → {paths.phase1_md}")
    console.print(f"[green]✓[/green] Trace → {paths.trace_jsonl}")
    console.print(f"[green]✓[/green] Meta  → {paths.run_meta}")

    if result is not None:
        console.print(f"[green]✓[/green] Grade → {paths.grading_json}")
        print_score_summary(result)


@app.command()
def grade(
    phase1: Path = typer.Option(..., "--phase1", help="Phase 1 输出 PDF"),
    rubrics: Path = typer.Option(..., "--rubrics"),
    query: Path = typer.Option(..., "--query"),
    attachment: Path = typer.Option(..., "--attachment"),
    out: Path = typer.Option(Path("grading_result.json"), "--out"),
    model: str = typer.Option("deepseek-chat", "--model", envvar="DEEPSEEK_MODEL"),
) -> None:
    """单独运行 Phase 2 评分。"""
    client = make_client()
    try:
        result = run_phase2_grader(
            phase1_pdf_path=str(phase1),
            phase1_md_path=str(phase1.with_suffix(".md")),
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
    result_file: Path = typer.Argument(..., help="grading_result.json"),
) -> None:
    """校验 grading_result.json 并打印评分摘要。"""
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        result = GradingResult(**data)
        console.print("[green]✓ JSON 结构合法，Pydantic 校验通过[/green]")
        print_score_summary(result)
    except (json.JSONDecodeError, ValidationError, OSError) as exc:
        console.print(f"[red][E005] 校验失败: {exc}[/red]")
        raise typer.Exit(1) from exc


@app.command("inspect-trace")
def inspect_trace(
    trace_file: Path = typer.Argument(..., help="agent_trace.jsonl"),
) -> None:
    """查看 Agent 工具调用轨迹摘要。"""
    if not trace_file.exists():
        console.print(f"[red]文件不存在: {trace_file}[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Trace: {trace_file}", show_header=True)
    table.add_column("Step", style="bold")
    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("ms")
    table.add_column("Preview")

    for line in trace_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        table.add_row(
            str(entry.get("step", "?")),
            str(entry.get("tool", "?")),
            str(entry.get("status", "?")),
            str(entry.get("duration_ms", "-")),
            str(entry.get("result_preview", ""))[:60],
        )

    console.print(table)


@app.command()
def init(
    target: Path = typer.Argument(Path("my-task"), help="任务目录名"),
) -> None:
    """初始化任务目录模板。"""
    target.mkdir(parents=True, exist_ok=True)
    (target / "outputs").mkdir(exist_ok=True)

    query = target / "query.txt"
    if not query.exists():
        query.write_text(
            "请基于附件 PDF 输出一份结构化报告，并满足 rubrics 中的全部要求。\n",
            encoding="utf-8",
        )

    rubrics = target / "rubrics.json"
    if not rubrics.exists():
        rubrics.write_text(
            json.dumps(
                {
                    "rubric_summary": "示例 rubrics，请替换为正式评分标准",
                    "rubric": {
                        "hard_constraints": [],
                        "soft_constraints": [],
                        "optional_constraints": [],
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    env_example = Path(".env.example")
    if env_example.exists() and not (target / ".env.example").exists():
        pass

    fixture_pdf = PROJECT_ROOT / "fixtures" / "attachment.pdf"
    attachment = target / "attachment.pdf"
    if fixture_pdf.exists() and not attachment.exists():
        attachment.write_bytes(fixture_pdf.read_bytes())

    console.print(f"[green]✓[/green] 已创建 {target}/")
    console.print("  - query.txt")
    console.print("  - rubrics.json（模板）")
    if attachment.exists():
        console.print("  - attachment.pdf（来自 fixtures 示例）")
    else:
        console.print("  - attachment.pdf（请自行放入）")
    console.print("  - outputs/")
    console.print(f"运行: agentic-rubric run --query {target}/query.txt --pdf {target}/attachment.pdf --rubrics {target}/rubrics.json")


@app.command()
def ui() -> None:
    """启动 Streamlit Web 界面。"""
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    if not app_path.exists():
        console.print("[red]未找到 app.py，请在项目根目录运行 streamlit run app.py[/red]")
        raise typer.Exit(1)
    console.print("[cyan]启动 Streamlit...[/cyan]")
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path)]))


def main() -> None:
    load_project_env()
    app()


if __name__ == "__main__":
    main()
