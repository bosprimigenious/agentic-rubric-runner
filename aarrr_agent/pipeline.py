"""共享流水线：输出路径、run 元数据、双阶段执行。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from aarrr_agent.agent import run_phase1_agent
from aarrr_agent.grader import run_phase2_grader
from aarrr_agent.grading_report import render_grading_report_html, render_grading_report_md
from aarrr_agent.schemas import GradingResult
from aarrr_agent.tools import save_trace


@dataclass
class OutputPaths:
    """一次运行的输出文件路径。"""

    directory: Path
    run_id: str
    phase1_pdf: Path
    phase1_md: Path
    phase1_html: Path
    evidence_pack: Path
    grading_json: Path
    grading_report_md: Path
    grading_report_html: Path
    trace_jsonl: Path
    run_meta: Path
    emergency_trace: Path


def make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def resolve_output_paths(out: Path | None = None, run_id: str | None = None) -> OutputPaths:
    """
    解析输出目录。
    - 未指定 out：写入当前目录
    - 指定 out：写入该目录（自动创建）
    """
    rid = run_id or make_run_id()
    if out is None:
        base = Path.cwd()
    else:
        base = out
        base.mkdir(parents=True, exist_ok=True)

    return OutputPaths(
        directory=base,
        run_id=rid,
        phase1_pdf=base / "phase1_output.pdf",
        phase1_md=base / "phase1_output.md",
        phase1_html=base / "phase1_output.html",
        evidence_pack=base / "evidence_pack.json",
        grading_json=base / "grading_result.json",
        grading_report_md=base / "grading_report.md",
        grading_report_html=base / "grading_report.html",
        trace_jsonl=base / "agent_trace.jsonl",
        run_meta=base / "run_meta.json",
        emergency_trace=base / "agent_trace_emergency.jsonl",
    )


def write_run_meta(
    paths: OutputPaths,
    *,
    model: str,
    query: Path,
    pdf: Path,
    rubrics: Path | None,
    duration_seconds: float,
    phase1_turns: int,
    final_score: float | None = None,
    status: str = "completed",
) -> None:
    meta = {
        "run_id": paths.run_id,
        "model": model,
        "status": status,
        "duration_seconds": round(duration_seconds, 2),
        "phase1_turns": phase1_turns,
        "final_score": final_score,
        "input_hash": {
            "query": sha256_file(query),
            "pdf": sha256_file(pdf),
        },
        "outputs": {
            "pdf": str(paths.phase1_pdf.name),
            "html": str(paths.phase1_html.name),
            "markdown": str(paths.phase1_md.name),
            "evidence_pack": str(paths.evidence_pack.name),
            "trace": str(paths.trace_jsonl.name),
        },
    }
    if rubrics is not None and rubrics.exists():
        meta["input_hash"]["rubrics"] = sha256_file(rubrics)
        meta["outputs"]["grading"] = str(paths.grading_json.name)
        meta["outputs"]["grading_report_md"] = str(paths.grading_report_md.name)
        meta["outputs"]["grading_report_html"] = str(paths.grading_report_html.name)

    paths.run_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def run_phase1_pipeline(
    *,
    query: Path,
    pdf: Path,
    client: OpenAI,
    model: str,
    paths: OutputPaths,
) -> int:
    """只执行 Phase 1：Agent 生成报告、trace 与 run_meta。返回 trace 步数。"""
    t0 = time.perf_counter()
    trace: list[dict] = []

    run_phase1_agent(
        query_path=str(query),
        pdf_path=str(pdf),
        pdf_output_path=str(paths.phase1_pdf),
        client=client,
        model=model,
        trace=trace,
        emergency_trace_path=str(paths.emergency_trace),
    )
    save_trace(trace, str(paths.trace_jsonl))
    write_run_meta(
        paths,
        model=model,
        query=query,
        pdf=pdf,
        rubrics=None,
        duration_seconds=time.perf_counter() - t0,
        phase1_turns=len(trace),
        status="phase1_only",
    )
    return len(trace)


def run_phase2_pipeline(
    *,
    query: Path,
    pdf: Path,
    rubrics: Path,
    client: OpenAI,
    model: str,
    paths: OutputPaths,
    phase1_turns: int,
    duration_seconds: float,
) -> GradingResult:
    """只执行 Phase 2：Rubric 评分并更新 run_meta。"""
    result = run_phase2_grader(
        phase1_pdf_path=str(paths.phase1_pdf),
        phase1_md_path=str(paths.phase1_md),
        rubrics_path=str(rubrics),
        query_path=str(query),
        attachment_pdf_path=str(pdf),
        client=client,
        model=model,
    )
    paths.grading_json.write_text(
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths.grading_report_md.write_text(
        render_grading_report_md(result, str(rubrics)),
        encoding="utf-8",
    )
    paths.grading_report_html.write_text(
        render_grading_report_html(result, str(rubrics)),
        encoding="utf-8",
    )
    write_run_meta(
        paths,
        model=model,
        query=query,
        pdf=pdf,
        rubrics=rubrics,
        duration_seconds=duration_seconds,
        phase1_turns=phase1_turns,
        final_score=result.score_breakdown.final_score,
        status="completed",
    )
    return result


def run_pipeline(
    *,
    query: Path,
    pdf: Path,
    rubrics: Path,
    client: OpenAI,
    model: str,
    paths: OutputPaths,
    skip_phase2: bool = False,
) -> GradingResult | None:
    """执行完整双阶段流水线，写入 paths 指定目录。"""
    t0 = time.perf_counter()
    phase1_turns = run_phase1_pipeline(
        query=query,
        pdf=pdf,
        client=client,
        model=model,
        paths=paths,
    )

    if skip_phase2:
        return None

    return run_phase2_pipeline(
        query=query,
        pdf=pdf,
        rubrics=rubrics,
        client=client,
        model=model,
        paths=paths,
        phase1_turns=phase1_turns,
        duration_seconds=time.perf_counter() - t0,
    )
