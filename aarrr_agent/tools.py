"""Agent 工具：PDF/文本读取与报告写入。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_text",
            "description": "读取纯文本文件内容，用于读取 query.txt 等任务描述文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "读取 PDF 文件的文本内容，用于读取学术附件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "PDF 文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_report",
            "description": "将生成的 Markdown 格式报告写入文件，完成 Phase 1 产物",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "完整的 Markdown 报告内容",
                    },
                    "path": {"type": "string", "description": "输出文件路径"},
                },
                "required": ["content", "path"],
            },
        },
    },
]


def read_text(path: str) -> str:
    """读取 UTF-8 纯文本文件。"""
    return Path(path).read_text(encoding="utf-8")


def read_pdf(path: str) -> str:
    """
    抽取 PDF 全文，保留页码标记，供 Agent 分析。
    返回格式：每页用 [PAGE N] 分隔。
    """
    doc = fitz.open(path)
    pages: list[str] = []
    try:
        for i, page in enumerate(doc, 1):
            text = page.get_text("text").strip()
            if text:
                pages.append(f"[PAGE {i}]\n{text}")
    finally:
        doc.close()
    return "\n\n".join(pages)


def write_report(content: str, path: str) -> str:
    """将 Markdown 报告写入文件。"""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return f"报告已写入 {path}"


def dispatch_tool(tool_name: str, tool_args: dict[str, Any], trace: list[dict[str, Any]]) -> str:
    """执行工具调用，记录到 trace，返回结果字符串。"""
    trace.append({"tool": tool_name, "args": tool_args, "status": "running"})

    try:
        if tool_name == "read_text":
            result = read_text(tool_args["path"])
        elif tool_name == "read_pdf":
            result = read_pdf(tool_args["path"])
        elif tool_name == "write_report":
            result = write_report(tool_args["content"], tool_args["path"])
        else:
            result = f"未知工具: {tool_name}"

        trace[-1]["status"] = "ok"
        trace[-1]["result_preview"] = result[:200]
        return result

    except Exception as exc:
        trace[-1]["status"] = "error"
        trace[-1]["error"] = str(exc)
        raise


def save_trace(trace: list[dict[str, Any]], path: str) -> None:
    """将 Agent 工具调用轨迹保存为 JSONL。"""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for entry in trace:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
