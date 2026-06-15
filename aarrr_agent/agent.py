"""Phase 1 Agent tool-use 循环。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from aarrr_agent.config import API_TIMEOUT_SECONDS, MAX_AGENT_TURNS
from aarrr_agent.errors import PipelineError
from aarrr_agent.tools import TOOLS, Phase1ToolContext, dispatch_tool, save_trace

SYSTEM_PROMPT = """你是一个专业的增长分析 Agent。

你的任务是：
1. 先调用 read_text 工具读取任务文件 query.txt
2. 再调用 read_pdf 工具读取学术附件 PDF
3. 基于以上内容，生成一份完整的中文指标方案报告（Markdown 格式）
4. 最后调用 write_pdf_report 工具将报告渲染为 PDF

重要约束：
- 你必须通过工具调用读取文件，不能假设文件内容
- Phase 1 只能使用 query.txt 和附件 PDF，不得读取其他文件（如 rubrics.json）
- 报告中引用的所有指标数据必须来自 PDF 附件，不得引入附件之外的信息
- 报告必须完全覆盖 query.txt 的所有要求
- 不要在 write_pdf_report 之前就停止，必须写完整报告

报告必须包含以下章节（顺序不强制）：
1. 北极星指标（单一指标，必须明确定义和选择理由）
2. 指标分层框架（关键健康指标 vs 诊断指标的区别）
3. AARRR 五阶段指标看板（获客/激活/留存/变现/传播各自的核心指标）
4. 目标值设定（每个关键指标的定量目标，附依据）
5. 预警规则（黄色预警阈值和红色预警阈值，建议用表格呈现）
6. 周/月/季度跟踪机制（每个周期的复盘重点和操作流程）
7. 可复盘指标看板结构说明
8. 行动建议与实施路径（可选但建议包含）

当你调用 write_pdf_report 并收到成功确认后，输出 "PHASE1_DONE" 表示完成。"""

REQUIRED_TOOLS = frozenset({"read_text", "read_pdf", "write_pdf_report"})


def _message_to_dict(msg: Any) -> dict[str, Any]:
    """将 OpenAI message 对象转为可序列化的 dict，供下一轮请求使用。"""
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
    """
    Phase 1 Agent 主循环。
    模型通过 tool-use 自主读取文件、生成报告并渲染 PDF。
    返回最终报告的 Markdown 内容。
    """
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
                f"任务文件路径：{ctx.query_path}\n"
                f"PDF 附件路径：{ctx.pdf_path}\n"
                f"PDF 输出路径：{pdf_output_path}"
            ),
        },
    ]

    report_content: str | None = None

    for turn in range(MAX_AGENT_TURNS):
        print(f"[Agent] Turn {turn + 1}/{MAX_AGENT_TURNS}...")
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                timeout=API_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            save_trace(trace, emergency_trace_path)
            raise PipelineError(
                "E001",
                f"API 失败（Turn {turn + 1}/{MAX_AGENT_TURNS}）: {exc}",
            ) from exc

        msg = response.choices[0].message
        messages.append(_message_to_dict(msg))

        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)

                tool_result = dispatch_tool(tool_name, tool_args, trace, ctx=ctx)

                if tool_name == "write_pdf_report":
                    report_content = tool_args.get("content")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    }
                )
            continue

        if msg.content and "PHASE1_DONE" in msg.content:
            break

        if response.choices[0].finish_reason == "stop":
            break

    called_tools = {entry["tool"] for entry in trace}
    missing = REQUIRED_TOOLS - called_tools
    if missing:
        raise RuntimeError(f"Agent 未调用必要工具: {', '.join(sorted(missing))}")

    if not report_content:
        md_path = Path(pdf_output_path).with_suffix(".md")
        if md_path.exists():
            report_content = md_path.read_text(encoding="utf-8")
        else:
            raise RuntimeError("Agent 未生成报告内容")

    return report_content
