"""Agent 工具：PDF/文本读取与报告写入。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz

from aarrr_agent.config import PROMPT_ATTACHMENT_BUDGET
from aarrr_agent.errors import PipelineError
from aarrr_agent.pdf_gen import markdown_to_pdf
from aarrr_agent.validation import validate_report_content

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
            "name": "write_pdf_report",
            "description": (
                "将 Markdown 格式报告写入并渲染为 PDF，完成 Phase 1 产物。"
                "传入完整报告内容与 PDF 输出路径。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": (
                            "完整的 Markdown 报告内容，必须包含所有必需章节，"
                            "不得截断或省略任何章节"
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": "PDF 输出路径，例如 phase1_output.pdf",
                    },
                },
                "required": ["content", "path"],
            },
        },
    },
]


@dataclass
class Phase1ToolContext:
    """Phase 1 工具执行上下文：严格限制可读/可写路径。"""

    query_path: Path
    pdf_path: Path
    pdf_output_path: Path
    _allowed_reads: set[Path] = field(init=False, repr=False)
    _allowed_writes: set[Path] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.query_path = Path(self.query_path).resolve()
        self.pdf_path = Path(self.pdf_path).resolve()
        self.pdf_output_path = Path(self.pdf_output_path).resolve()
        self._allowed_reads = {self.query_path, self.pdf_path}
        self._allowed_writes = {self.pdf_output_path}

    def assert_read_allowed(self, path: str) -> Path:
        resolved = Path(path).resolve()
        if resolved not in self._allowed_reads:
            raise PermissionError(
                f"Phase 1 不允许读取此路径: {path}。"
                f"仅允许: {self.query_path} 或 {self.pdf_path}"
            )
        return resolved

    def assert_write_allowed(self, path: str) -> Path:
        resolved = Path(path).resolve()
        if resolved not in self._allowed_writes:
            raise PermissionError(
                f"Phase 1 不允许写入此路径: {path}。"
                f"仅允许: {self.pdf_output_path}"
            )
        return resolved


def read_text(path: str) -> str:
    """读取 UTF-8 纯文本文件（无路径限制，供 Phase 2 使用）。"""
    return Path(path).read_text(encoding="utf-8")


def read_text_phase1(path: str, ctx: Phase1ToolContext) -> str:
    """Phase 1 专用：仅允许读取 query.txt。"""
    allowed = ctx.assert_read_allowed(path)
    return allowed.read_text(encoding="utf-8")


def read_pdf(path: str) -> str:
    """
    抽取 PDF 全文，保留页码标记。
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
    text = "\n\n".join(pages)
    if not text.strip():
        raise PipelineError("E002", f"PDF 抽取无文本: {path}（可能是扫描件）")
    return text


def read_pdf_phase1(path: str, ctx: Phase1ToolContext) -> str:
    """Phase 1 专用：仅允许读取附件 PDF。"""
    allowed = ctx.assert_read_allowed(path)
    return read_pdf(str(allowed))


def write_pdf_report(content: str, pdf_path: str, ctx: Phase1ToolContext | None = None) -> str:
    """
    保存 Markdown 源文件并渲染 PDF。
    同时产出 .md 与 .pdf，便于 Phase 2 优先读取结构化源内容。
    """
    if ctx is not None:
        pdf = ctx.assert_write_allowed(pdf_path)
    else:
        pdf = Path(pdf_path).resolve()

    issues = validate_report_content(content)
    if issues:
        print(f"[E004 警告] 报告可能不完整: {issues}")

    pdf.parent.mkdir(parents=True, exist_ok=True)
    md_path = pdf.with_suffix(".md")
    md_path.write_text(content, encoding="utf-8")
    markdown_to_pdf(content, str(pdf))
    return f"PDF 报告已生成: {pdf}（Markdown 源文件: {md_path}）"


def fit_text_to_budget(text: str, budget: int = PROMPT_ATTACHMENT_BUDGET) -> str:
    """
    将文本适配到 prompt 预算。
    未超限时全文返回；超出时按 [PAGE N] 页边界截取，避免截断页内句子。
    """
    if len(text) <= budget:
        return text

    pages = re.split(r"(?=\[PAGE \d+\])", text)
    pages = [p for p in pages if p.strip()]

    kept: list[str] = []
    total = 0
    for page in pages:
        if total + len(page) > budget:
            break
        kept.append(page)
        total += len(page)

    omitted = len(pages) - len(kept)
    note = f"\n\n[NOTE: 因上下文长度限制，已省略后续 {omitted} 页内容]"
    result = "".join(kept).strip()
    if len(result) + len(note) <= budget:
        return result + note
    return result[:budget]


def _sanitize_args_for_trace(tool_args: dict[str, Any]) -> dict[str, Any]:
    """截断 trace 中的长字符串，避免 write_pdf_report.content 撑爆日志。"""
    preview: dict[str, Any] = {}
    for key, value in tool_args.items():
        if isinstance(value, str) and len(value) > 120:
            preview[key] = f"{value[:120]}...({len(value)} chars)"
        else:
            preview[key] = value
    return preview


def dispatch_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    trace: list[dict[str, Any]],
    ctx: Phase1ToolContext | None = None,
) -> str:
    """执行工具调用，记录到 trace，返回结果字符串。"""
    step = len(trace) + 1
    t0 = time.perf_counter()
    entry: dict[str, Any] = {
        "step": step,
        "tool": tool_name,
        "args_preview": _sanitize_args_for_trace(tool_args),
        "status": "running",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    trace.append(entry)

    try:
        if tool_name == "read_text":
            if ctx is None:
                result = read_text(tool_args["path"])
            else:
                result = read_text_phase1(tool_args["path"], ctx)
        elif tool_name == "read_pdf":
            if ctx is None:
                result = read_pdf(tool_args["path"])
            else:
                result = read_pdf_phase1(tool_args["path"], ctx)
        elif tool_name == "write_pdf_report":
            result = write_pdf_report(
                tool_args["content"],
                tool_args["path"],
                ctx=ctx,
            )
            entry["path"] = tool_args["path"]
        else:
            raise ValueError(f"未知工具: {tool_name}")

        entry["status"] = "ok"
        entry["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        entry["result_preview"] = result[:200]
        return result

    except Exception as exc:
        entry["status"] = "error"
        entry["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        entry["error"] = str(exc)
        raise


def save_trace(trace: list[dict[str, Any]], path: str) -> None:
    """将 Agent 工具调用轨迹保存为 JSONL。"""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for item in trace:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
