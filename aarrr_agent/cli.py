"""Typer CLI：agentic-rubric / aarrr-agent。"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import typer
from openai import OpenAI
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from aarrr_agent.acceptance import run_acceptance_gate
from aarrr_agent.benchmark import evaluate_agent_run, run_benchmark
from aarrr_agent.config import PROJECT_ROOT
from aarrr_agent.env import load_project_env
from aarrr_agent.errors import PipelineError
from aarrr_agent.grader import run_phase2_grader
from aarrr_agent.pipeline import (
    OutputPaths,
    make_run_id,
    resolve_output_paths,
    run_phase1_pipeline,
    run_phase2_pipeline,
)
from aarrr_agent.reporting import print_score_summary
from aarrr_agent.schemas import GradingResult

app = typer.Typer(
    name="agentic-rubric",
    help="文档约束型评审流水线：报告生成 + Rubric 评分",
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


def _prepare_paths(
    out: Path | None,
    phase1_out: Path | None = None,
    grading_out: Path | None = None,
    trace_out: Path | None = None,
) -> OutputPaths:
    rid = make_run_id()
    base_out = out if out is not None else Path("outputs") / rid
    paths = resolve_output_paths(base_out, run_id=rid)
    if phase1_out:
        paths.phase1_pdf = phase1_out
        paths.phase1_md = phase1_out.with_suffix(".md")
        paths.phase1_html = phase1_out.with_suffix(".html")
    if grading_out:
        paths.grading_json = grading_out
    if trace_out:
        paths.trace_jsonl = trace_out
    return paths


def _print_run_header(paths: OutputPaths) -> None:
    console.print(f"run_id:   [bold]{paths.run_id}[/bold]")
    console.print(f"输出目录: [cyan]{paths.directory.resolve()}[/cyan]")


def _print_phase1_artifacts(paths: OutputPaths, turns: int) -> None:
    console.print(f"[green]✓[/green] Phase 1 完成（{turns} 步工具调用）")
    console.print(f"  MD    → {paths.phase1_md}")
    console.print(f"  HTML  → {paths.phase1_html}")
    console.print(f"  PDF   → {paths.phase1_pdf}")
    console.print(f"  Trace → {paths.trace_jsonl}")
    console.print(f"  Meta  → {paths.run_meta}")


def _print_phase2_artifacts(paths: OutputPaths) -> None:
    console.print(f"[green]✓[/green] Phase 2 完成")
    console.print(f"  Grade → {paths.grading_json}")
    console.print(f"  Report MD → {paths.grading_report_md}")
    console.print(f"  Report HTML → {paths.grading_report_html}")


def _handle_pipeline_error(exc: PipelineError) -> None:
    console.print(f"[red]{exc.code}[/red] {exc.message}")
    raise typer.Exit(1) from exc


@app.command()
def phase1(
    query: Path = typer.Option(..., "--query", help="任务描述 query.txt"),
    pdf: Path = typer.Option(..., "--pdf", help="附件 PDF"),
    out: Path | None = typer.Option(None, "--out", help="输出目录，例如 outputs/demo"),
    phase1_out: Path | None = typer.Option(None, "--phase1-out", help="覆盖 Phase 1 PDF 路径"),
    trace_out: Path | None = typer.Option(None, "--trace-out", help="覆盖 trace 路径"),
    model: str = typer.Option("deepseek-chat", "--model", envvar="DEEPSEEK_MODEL"),
    renderer: str = typer.Option(
        "auto",
        "--renderer",
        envvar="PDF_RENDERER",
        help="PDF 渲染器: auto|html|reportlab",
    ),
) -> None:
    """只运行 Phase 1：Agent 生成报告与 PDF（不读取 rubrics.json）。"""
    import os

    os.environ["PDF_RENDERER"] = renderer
    paths = _prepare_paths(out, phase1_out=phase1_out, trace_out=trace_out)
    client = make_client()

    console.rule("[bold blue]Phase 1 — Agent 生成报告")
    _print_run_header(paths)

    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Agent 运行中...", total=None)
            turns = run_phase1_pipeline(
                query=query,
                pdf=pdf,
                client=client,
                model=model,
                paths=paths,
            )
            progress.update(task, description="[green]Phase 1 完成")
    except PipelineError as exc:
        _handle_pipeline_error(exc)

    _print_phase1_artifacts(paths, turns)


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
    renderer: str = typer.Option(
        "auto",
        "--renderer",
        envvar="PDF_RENDERER",
        help="PDF 渲染器: auto|html|reportlab",
    ),
) -> None:
    """完整双阶段流水线：Agent 生成报告 + Rubric 自动评分。"""
    import os

    os.environ["PDF_RENDERER"] = renderer
    paths = _prepare_paths(out, phase1_out, grading_out, trace_out)
    client = make_client()
    t0 = time.perf_counter()

    console.rule("[bold blue]Document Evaluation — Full Pipeline")
    _print_run_header(paths)

    console.rule("[bold cyan]Phase 1 — Agent 生成报告")
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Agent 运行中...", total=None)
            phase1_turns = run_phase1_pipeline(
                query=query,
                pdf=pdf,
                client=client,
                model=model,
                paths=paths,
            )
            progress.update(task, description="[green]Phase 1 完成")
    except PipelineError as exc:
        _handle_pipeline_error(exc)

    _print_phase1_artifacts(paths, phase1_turns)

    if skip_phase2:
        console.print("[yellow]已跳过 Phase 2（--skip-phase2）[/yellow]")
        return

    console.rule("[bold cyan]Phase 2 — Rubric 评分")
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("评分中...", total=None)
            result = run_phase2_pipeline(
                query=query,
                pdf=pdf,
                rubrics=rubrics,
                client=client,
                model=model,
                paths=paths,
                phase1_turns=phase1_turns,
                duration_seconds=time.perf_counter() - t0,
            )
            progress.update(task, description="[green]Phase 2 完成")
    except PipelineError as exc:
        _handle_pipeline_error(exc)

    _print_phase2_artifacts(paths)
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
    console.rule("[bold blue]Phase 2 — Rubric 评分")
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
        _handle_pipeline_error(exc)

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


@app.command("eval-run")
def eval_run(
    out: Path = typer.Option(..., "--out", help="已完成运行的输出目录"),
    rubrics: Path | None = typer.Option(None, "--rubrics", help="可选：评分标准 rubrics.json"),
) -> None:
    """对一次已完成运行生成 agent_eval.json。"""
    if not out.exists():
        console.print(f"[red]输出目录不存在: {out}[/red]")
        raise typer.Exit(1)
    paths = resolve_output_paths(out, run_id=out.name)
    result = evaluate_agent_run(paths, rubrics_path=rubrics, status="completed")
    console.print(f"[green]✓[/green] Agent Eval → {out / 'agent_eval.json'}")
    console.print(f"agent_score: [bold]{result['agent_score']:.2f}[/bold] / 100")
    if result.get("report_score") is not None:
        console.print(f"report_score: {result['report_score']:.2f} / 100")
    if result.get("failure_types"):
        console.print(f"failure_types: {', '.join(result['failure_types'])}")


@app.command()
def bench(
    manifest: Path = typer.Option(..., "--manifest", help="Benchmark manifest JSON"),
    out: Path = typer.Option(Path("outputs/bench"), "--out", help="Benchmark 输出目录"),
    model: str = typer.Option("deepseek-chat", "--model", envvar="DEEPSEEK_MODEL"),
    renderer: str = typer.Option(
        "auto",
        "--renderer",
        envvar="PDF_RENDERER",
        help="PDF 渲染器: auto|html|reportlab",
    ),
) -> None:
    """运行 Agent benchmark case suite，并生成汇总报告。"""
    client = make_client()
    console.rule("[bold blue]Agent Benchmark")
    console.print(f"manifest: [cyan]{manifest}[/cyan]")
    console.print(f"输出目录: [cyan]{out.resolve()}[/cyan]")
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Benchmark 运行中...", total=None)
            summary = run_benchmark(
                manifest_path=manifest,
                out=out,
                client=client,
                model=model,
                renderer=renderer,
            )
            progress.update(task, description="[green]Benchmark 完成")
    except PipelineError as exc:
        _handle_pipeline_error(exc)

    console.print(f"[green]✓[/green] {out / 'agent_benchmark_result.json'}")
    console.print(f"[green]✓[/green] {out / 'agent_benchmark_report.md'}")
    console.print(f"benchmark_score: [bold]{summary['benchmark_score']:.2f}[/bold] / 100")
    console.print(f"success_rate: {summary['success_rate']:.2%}")
    console.print(f"release_gate: {'PASS' if summary['release']['passed'] else 'BLOCK'}")


@app.command()
def acceptance(
    manifest: Path = typer.Option(
        Path("fixtures/benchmarks/agent_cases.json"),
        "--manifest",
        help="Benchmark manifest JSON",
    ),
    benchmark_result: Path = typer.Option(
        Path("outputs/bench/agent_benchmark_result.json"),
        "--benchmark-result",
        help="Benchmark result JSON",
    ),
    baseline: Path | None = typer.Option(None, "--baseline", help="Optional baseline benchmark JSON"),
    out: Path = typer.Option(Path("outputs/acceptance_summary.json"), "--out", help="Acceptance summary JSON"),
    mode: str = typer.Option("live", "--mode", help="offline|live|release"),
) -> None:
    """Fail-closed acceptance gate for local, CI, and release workflows."""
    if mode not in {"offline", "live", "release"}:
        console.print("[red]mode 必须是 offline、live 或 release[/red]")
        raise typer.Exit(1)

    summary = run_acceptance_gate(
        manifest_path=manifest,
        benchmark_result_path=benchmark_result,
        baseline_path=baseline,
        out_path=out,
        mode=mode,  # type: ignore[arg-type]
    )
    status = summary["status"]
    color = "green" if status in {"READY", "OFFLINE_OK"} else "red"
    console.print(f"[{color}]{status}[/{color}] → {out}")
    if summary["blockers"]:
        for blocker in summary["blockers"]:
            console.print(f"[red]- {blocker['id']}:[/red] {blocker['reason']}")
        raise typer.Exit(1)
    if summary["warnings"]:
        for warning in summary["warnings"]:
            console.print(f"[yellow]- {warning['id']}:[/yellow] {warning['reason']}")


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
    console.print(
        f"运行: agentic-rubric phase1 --query {target}/query.txt "
        f"--pdf {target}/attachment.pdf --out {target}/outputs"
    )


def resolve_web_app_path() -> Path:
    """定位 Streamlit 入口脚本（pip 安装后使用包内 web_app.py）。"""
    packaged = Path(__file__).resolve().parent / "web_app.py"
    if packaged.exists():
        return packaged
    repo_root = Path(__file__).resolve().parent.parent / "app.py"
    if repo_root.exists():
        return repo_root
    raise FileNotFoundError("未找到 Streamlit 入口：aarrr_agent/web_app.py")


@app.command()
def ui() -> None:
    """启动 Streamlit Web 界面（需安装 [web] 额外依赖）。"""
    if importlib.util.find_spec("streamlit") is None:
        console.print("[red]未安装 Web 依赖，无法启动 Streamlit 控制台。[/red]")
        console.print(
            "请运行: pip install \"agentic-rubric-runner[web] "
            "@ git+https://github.com/bosprimigenious/agentic-rubric-runner.git\""
        )
        console.print("或本地开发: pip install -e \".[web]\"")
        raise typer.Exit(1)
    try:
        app_path = resolve_web_app_path()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[cyan]启动 Streamlit: {app_path}[/cyan]")
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path)]))


def main() -> None:
    load_project_env()
    app()


if __name__ == "__main__":
    main()
