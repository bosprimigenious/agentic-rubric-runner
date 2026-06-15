"""Phase 1 Agent tool-use 循环（状态机约束）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from aarrr_agent.config import MAX_AGENT_TURNS
from aarrr_agent.errors import PipelineError
from aarrr_agent.evidence import format_evidence_for_prompt, load_evidence_pack
from aarrr_agent.llm import call_chat_completion
from aarrr_agent.phase1_state import WRITE_TOOLS
from aarrr_agent.tools import TOOLS, Phase1ToolContext, dispatch_tool, save_trace

SYSTEM_PROMPT = """你是一个专业的增长分析 Agent，在受控状态机下完成任务。

必须按顺序调用工具（不可跳步、不可乱序）：
1. read_text — 读取 query.txt
2. read_pdf — 读取附件 PDF
3. extract_evidence_pack — 抽取证据包 evidence_pack.json
4. （可选）self_check_report — 对报告草稿自检
5. write_structured_report 或 write_pdf_report — 提交最终报告（必须最后调用）

重要约束：
- 必须通过工具读取文件，不得假设内容
- Phase 1 只能使用 query.txt 与附件 PDF
- 报告中所有关键事实必须来自附件，并引用证据编号，如：次日留存率是核心指标。[E01]
- 优先使用 write_structured_report 提交 JSON 结构化报告
- 报告须覆盖：单一北极星指标、健康/诊断分层、AARRR 五阶段、目标值、红黄预警、周/月/季复盘机制
- write 工具调用后不得再调用任何工具

结构化报告 JSON 示例字段：
title, executive_summary, north_star_metric, aarrr_stages, warning_rules, review_cadence, action_plan, evidence_refs

完成后输出 "PHASE1_DONE"。"""


def _message_to_dict(msg: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"role": msg.role}
    if msg.content is not None:
        data["content"] = msg.content
    if msg.tool_calls:
        data["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return data


def run_phase1_agent(
    query_path: str,
    pdf_path: str,
    pdf_output_path: str,
    client: OpenAI,
    model: str,
    trace: list[dict[str, Any]],
    emergency_trace_path: str = "agent_trace_emergency.jsonl",
) -> str:
    ctx = Phase1ToolContext(
        query_path=Path(query_path),
        pdf_path=Path(pdf_path),
        pdf_output_path=Path(pdf_output_path),
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"请完成任务。\n"
                f"任务文件：{ctx.query_path}\n"
                f"PDF 附件：{ctx.pdf_path}\n"
                f"PDF 输出：{pdf_output_path}\n"
                f"证据包输出：{ctx.evidence_path}"
            ),
        },
    ]

    report_content: str | None = None
    phase1_done = False

    for turn in range(MAX_AGENT_TURNS):
        print(f"[Agent] Turn {turn + 1}/{MAX_AGENT_TURNS} [state={ctx.state.state.value}]...")
        try:
            response = call_chat_completion(
                client,
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        except PipelineError:
            save_trace(trace, emergency_trace_path)
            raise

        msg = response.choices[0].message
        messages.append(_message_to_dict(msg))

        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)
                tool_result = dispatch_tool(tool_name, tool_args, trace, ctx=ctx)

                if tool_name == "write_pdf_report":
                    report_content = tool_args.get("content")
                elif tool_name == "write_structured_report":
                    from aarrr_agent.structured_report import structured_to_markdown, StructuredReport
                    report_content = structured_to_markdown(
                        StructuredReport.model_validate(tool_args.get("report", {}))
                    )
                elif tool_name == "extract_evidence_pack" and ctx.evidence_path.exists():
                    pack = load_evidence_pack(ctx.evidence_path)
                    messages.append(
                        {
                            "role": "user",
                            "content": f"证据包已就绪，写报告时请引用：\n{format_evidence_for_prompt(pack)[:3000]}",
                        }
                    )

                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": tool_result}
                )
            continue

        if msg.content and "PHASE1_DONE" in msg.content:
            phase1_done = True
            break

        if response.choices[0].finish_reason == "stop":
            break

    ctx.state.assert_complete(phase1_done=phase1_done)

    if not report_content:
        md_path = Path(pdf_output_path).with_suffix(".md")
        if md_path.exists():
            report_content = md_path.read_text(encoding="utf-8")
        else:
            raise RuntimeError("Agent 未生成报告内容")

    return report_content
