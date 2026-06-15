#!/usr/bin/env python3
"""AARRR Agent Pipeline — 双阶段入口：Phase 1 Agent + Phase 2 Rubric 评分。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from openai import OpenAI

from aarrr_agent.agent import run_phase1_agent
from aarrr_agent.grader import run_phase2_grader
from aarrr_agent.pdf_gen import markdown_to_pdf
from aarrr_agent.tools import save_trace


def main() -> None:
    parser = argparse.ArgumentParser(description="AARRR Agent Pipeline")
    parser.add_argument("--query", required=True, help="任务描述文件路径 (query.txt)")
    parser.add_argument("--pdf", required=True, help="学术附件 PDF 路径")
    parser.add_argument("--rubrics", required=True, help="评分标准 rubrics.json 路径")
    parser.add_argument("--phase1-out", default="phase1_output.pdf", help="Phase 1 PDF 输出路径")
    parser.add_argument("--grading-out", default="grading_result.json", help="Phase 2 评分输出路径")
    parser.add_argument("--trace-out", default="agent_trace.jsonl", help="Agent 工具调用轨迹")
    parser.add_argument(
        "--model",
        default=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        help="DeepSeek 模型名称",
    )
    parser.add_argument(
        "--skip-phase2",
        action="store_true",
        help="仅运行 Phase 1（调试用）",
    )
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误: 请设置环境变量 DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )

    trace: list[dict] = []
    md_path = args.phase1_out.rsplit(".", 1)[0] + ".md" if "." in args.phase1_out else args.phase1_out + ".md"

    print("[Phase 1] Starting Agent...")
    report_md = run_phase1_agent(
        query_path=args.query,
        pdf_path=args.pdf,
        report_output_path=md_path,
        client=client,
        model=args.model,
        trace=trace,
    )

    print("[Phase 1] Converting to PDF...")
    markdown_to_pdf(report_md, args.phase1_out)
    print(f"[Phase 1] Done → {args.phase1_out}")

    save_trace(trace, args.trace_out)
    print(f"[Trace] Saved → {args.trace_out}")

    if args.skip_phase2:
        return

    print("[Phase 2] Starting evaluator...")
    grading = run_phase2_grader(
        phase1_pdf_path=args.phase1_out,
        rubrics_path=args.rubrics,
        query_path=args.query,
        attachment_pdf_path=args.pdf,
        client=client,
        model=args.model,
    )

    with open(args.grading_out, "w", encoding="utf-8") as fh:
        json.dump(grading.model_dump(), fh, ensure_ascii=False, indent=2)
    print(f"[Phase 2] Done → {args.grading_out}")

    bd = grading.score_breakdown
    print(f"\n{'=' * 40}")
    print(f"Final Score: {bd.final_score}")
    print(f"Hard:     {bd.hard_score}/{bd.hard_max}")
    print(f"Soft:     {bd.soft_score}/{bd.soft_max}")
    print(f"Optional: {bd.optional_score}/{bd.optional_max}")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    main()
