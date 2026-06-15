"""Agent 工具：PDF/文本读取、证据抽取与报告写入。"""

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
from aarrr_agent.evidence import extract_evidence_pack, format_evidence_for_prompt, load_evidence_pack, save_evidence_pack
from aarrr_agent.html_pdf import render_markdown_report
from aarrr_agent.phase1_state import Phase1StateMachine, WRITE_TOOLS
from aarrr_agent.structured_report import StructuredReport, structured_to_executive_report, structured_to_markdown
from aarrr_agent.html_report import render_executive_html
from aarrr_agent.validation import self_check_report, validate_report_content

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_text",
            "description": "读取 query.txt 任务描述（必须第一步调用）",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "读取附件 PDF 文本（必须在 read_text 之后调用）",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "PDF 文件路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_evidence_pack",
            "description": (
                "从附件 PDF 抽取证据包 evidence_pack.json（必须在 read_pdf 之后、写报告之前调用）。"
                "报告中的关键事实须引用证据编号，如 [E01]。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "PDF 文件路径（附件）"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "self_check_report",
            "description": (
                "对报告草稿做完整性自检（可选，建议在 write 之前调用）。"
                "返回缺失章节与证据引用问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "报告 Markdown 草稿"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_structured_report",
            "description": (
                "提交结构化报告 JSON 并渲染为 MD/HTML/PDF（推荐，必须最后调用之一）。"
                "关键事实须在 evidence_refs 或正文中标注 [E01] 等证据编号。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "report": {
                        "type": "object",
                        "description": (
                            "结构化报告，含 title, executive_summary, north_star_metric, "
                            "aarrr_stages, warning_rules, review_cadence, action_plan, evidence_refs"
                        ),
                    },
                    "path": {"type": "string", "description": "PDF 输出路径"},
                },
                "required": ["report", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_pdf_report",
            "description": (
                "将 Markdown 报告写入并渲染为 PDF（备选，必须最后调用之一）。"
                "正文中须包含 [E01] 形式证据引用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "完整 Markdown 报告"},
                    "path": {"type": "string", "description": "PDF 输出路径"},
                },
                "required": ["content", "path"],
            },
        },
    },
]


@dataclass
class Phase1ToolContext:
    """Phase 1 工具执行上下文：路径白名单 + 状态机。"""

    query_path: Path
    pdf_path: Path
    pdf_output_path: Path
    state: Phase1StateMachine = field(default_factory=Phase1StateMachine)
    evidence_path: Path = field(init=False)
    _allowed_reads: set[Path] = field(init=False, repr=False)
    _allowed_writes: set[Path] = field(init=False, repr=False)
    _pdf_text_cache: str | None = field(default=None, repr=False)
    attachment_relevant: bool | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.query_path = Path(self.query_path).resolve()
        self.pdf_path = Path(self.pdf_path).resolve()
        self.pdf_output_path = Path(self.pdf_output_path).resolve()
        self.evidence_path = self.pdf_output_path.parent / "evidence_pack.json"
        self._allowed_reads = {self.query_path, self.pdf_path}
        self._allowed_writes = {self.pdf_output_path, self.evidence_path}

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
        if resolved not in self._allowed_writes and resolved != self.pdf_output_path.resolve():
            raise PermissionError(
                f"Phase 1 不允许写入此路径: {path}。"
                f"仅允许: {self.pdf_output_path} 或 {self.evidence_path}"
            )
        return resolved


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def read_text_phase1(path: str, ctx: Phase1ToolContext) -> str:
    allowed = ctx.assert_read_allowed(path)
    return allowed.read_text(encoding="utf-8")


def read_pdf(path: str) -> str:
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
    allowed = ctx.assert_read_allowed(path)
    text = read_pdf(str(allowed))
    ctx._pdf_text_cache = text
    from aarrr_agent.attachment_relevance import assess_attachment_domain

    ctx.attachment_relevant = assess_attachment_domain(text)["relevant"]
    return text


def run_extract_evidence_pack(pdf_path: str, ctx: Phase1ToolContext) -> str:
    from aarrr_agent.attachment_relevance import assess_attachment_domain

    allowed = ctx.assert_read_allowed(pdf_path)
    pack = extract_evidence_pack(str(allowed))
    assessment = assess_attachment_domain(
        ctx._pdf_text_cache or "",
        ctx.query_path.read_text(encoding="utf-8") if ctx.query_path.exists() else "",
    )
    save_evidence_pack(pack, ctx.evidence_path)
    preview = format_evidence_for_prompt(pack)
    ctx.attachment_relevant = assessment["relevant"]

    if not assessment["relevant"]:
        warning = (
            f"[E007 警告] 附件与任务领域不匹配（领域词 {assessment['domain_hit_count']}，"
            f"离题信号 {assessment['off_domain_hit_count']}）。"
            "不得编造附件中不存在的社交电商/AARRR 事实；"
            "禁止将 DNS/实验报告等内容强行类比为增长指标。"
        )
        return f"{warning}\n\n证据包已生成: {ctx.evidence_path}（共 {len(pack.facts)} 条）。\n\n{preview[:2000]}"

    return (
        f"证据包已生成: {ctx.evidence_path}（共 {len(pack.facts)} 条）。"
        f"报告须引用证据编号 [E01] 等。\n\n{preview[:2000]}"
    )


def run_self_check_report(content: str) -> str:
    result = self_check_report(content)
    return json.dumps(result, ensure_ascii=False)


def write_structured_report(report_data: dict[str, Any], pdf_path: str, ctx: Phase1ToolContext | None = None) -> str:
    pdf = Path(pdf_path).resolve()
    if ctx is not None:
        pdf = ctx.assert_write_allowed(pdf_path)
        from aarrr_agent.attachment_relevance import assess_attachment_domain

        attachment_body = ctx._pdf_text_cache or ""
        if attachment_body and not assess_attachment_domain(attachment_body)["relevant"]:
            assessment = assess_attachment_domain(attachment_body)
            raise PipelineError(
                "E007",
                "附件与社交电商/AARRR 增长领域不匹配，拒绝写入结构化报告。"
                f"离题信号：{', '.join(assessment['off_domain_hits'][:6]) or '无'}。"
                "请上传与任务一致的源文档 PDF。",
            )

    report = StructuredReport.model_validate(report_data)
    markdown = structured_to_markdown(report)
    issues = validate_report_content(markdown)
    if issues:
        print(f"[E004 警告] 结构化报告可能不完整: {issues}")

    pdf.parent.mkdir(parents=True, exist_ok=True)
    md_path = pdf.with_suffix(".md")
    md_path.write_text(markdown, encoding="utf-8")

    run_id = pdf.parent.name if pdf.parent.name.startswith("20") else ""
    exec_report = structured_to_executive_report(report, run_id=run_id)
    html_path = pdf.with_suffix(".html")
    html_path.write_text(render_executive_html(exec_report), encoding="utf-8")

    from aarrr_agent.html_pdf import html_to_pdf, weasyprint_available

    renderer = "html"
    try:
        if weasyprint_available():
            html_to_pdf(html_path.read_text(encoding="utf-8"), pdf)
        else:
            from aarrr_agent.pdf_gen import markdown_to_pdf
            markdown_to_pdf(markdown, str(pdf))
            renderer = "reportlab"
    except Exception:
        from aarrr_agent.pdf_gen import markdown_to_pdf
        markdown_to_pdf(markdown, str(pdf))
        renderer = "reportlab"

    structured_path = pdf.with_suffix(".structured.json")
    structured_path.write_text(report.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    return (
        f"结构化报告已生成: PDF={pdf}，HTML={html_path}，Markdown={md_path}，"
        f"JSON={structured_path}（渲染器: {renderer}）"
    )


def write_pdf_report(content: str, pdf_path: str, ctx: Phase1ToolContext | None = None) -> str:
    if ctx is not None:
        pdf = ctx.assert_write_allowed(pdf_path)
        from aarrr_agent.attachment_relevance import assess_attachment_domain, detect_forced_analogy_report

        attachment_body = ctx._pdf_text_cache or ""
        if attachment_body:
            assessment = assess_attachment_domain(attachment_body)
            if not assessment["relevant"]:
                detail = ", ".join(assessment["off_domain_hits"][:6]) or "领域词不足"
                if detect_forced_analogy_report(content, attachment_body):
                    raise PipelineError(
                        "E007",
                        "报告将离题附件强行类比为增长指标（如 DNS→AARRR），拒绝写入。"
                        f"离题信号：{detail}。请使用与任务领域一致的附件。",
                    )
                raise PipelineError(
                    "E007",
                    "附件与社交电商/AARRR 增长领域不匹配，拒绝写入报告。"
                    f"离题信号：{detail}。请上传正确的源文档 PDF。",
                )
    else:
        pdf = Path(pdf_path).resolve()

    issues = validate_report_content(content)
    if issues:
        print(f"[E004 警告] 报告可能不完整: {issues}")

    pdf.parent.mkdir(parents=True, exist_ok=True)
    md_path = pdf.with_suffix(".md")
    md_path.write_text(content, encoding="utf-8")

    run_id = pdf.parent.name if pdf.parent.name.startswith("20") else ""
    _, _, renderer_used = render_markdown_report(content, pdf, run_id=run_id)
    return (
        f"报告已生成: PDF={pdf}，Markdown={md_path}（渲染器: {renderer_used}）"
    )


def fit_text_to_budget(text: str, budget: int = PROMPT_ATTACHMENT_BUDGET) -> str:
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
    preview: dict[str, Any] = {}
    for key, value in tool_args.items():
        if isinstance(value, str) and len(value) > 120:
            preview[key] = f"{value[:120]}...({len(value)} chars)"
        elif key == "report" and isinstance(value, dict):
            preview[key] = f"{{...}} ({len(json.dumps(value, ensure_ascii=False))} chars)"
        else:
            preview[key] = value
    return preview


def dispatch_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    trace: list[dict[str, Any]],
    ctx: Phase1ToolContext | None = None,
) -> str:
    if ctx is not None:
        ctx.state.assert_tool_allowed(tool_name)

    step = len(trace) + 1
    t0 = time.perf_counter()
    entry: dict[str, Any] = {
        "step": step,
        "tool": tool_name,
        "args_preview": _sanitize_args_for_trace(tool_args),
        "status": "running",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if ctx is not None:
        entry["phase1_state"] = ctx.state.state.value
    trace.append(entry)

    try:
        if tool_name == "read_text":
            result = read_text_phase1(tool_args["path"], ctx) if ctx else read_text(tool_args["path"])
        elif tool_name == "read_pdf":
            result = read_pdf_phase1(tool_args["path"], ctx) if ctx else read_pdf(tool_args["path"])
        elif tool_name == "extract_evidence_pack":
            if ctx is None:
                raise ValueError("extract_evidence_pack 需要 Phase 1 上下文")
            result = run_extract_evidence_pack(tool_args["path"], ctx)
        elif tool_name == "self_check_report":
            result = run_self_check_report(tool_args["content"])
        elif tool_name == "write_structured_report":
            result = write_structured_report(tool_args["report"], tool_args["path"], ctx=ctx)
            entry["path"] = tool_args["path"]
        elif tool_name == "write_pdf_report":
            result = write_pdf_report(tool_args["content"], tool_args["path"], ctx=ctx)
            entry["path"] = tool_args["path"]
        else:
            raise ValueError(f"未知工具: {tool_name}")

        if ctx is not None:
            ctx.state.record_tool(tool_name)
            entry["phase1_state"] = ctx.state.state.value

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
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for item in trace:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
