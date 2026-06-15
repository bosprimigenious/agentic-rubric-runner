"""测试：Mock Agent 工具循环（状态机 + dispatch）。"""

import json
from pathlib import Path

import pytest

from aarrr_agent.tools import Phase1ToolContext, dispatch_tool
from tests.test_structured_report import SAMPLE


@pytest.fixture
def ctx(tmp_path):
    query = tmp_path / "query.txt"
    pdf = tmp_path / "attachment.pdf"
    out = tmp_path / "phase1_output.pdf"
    query.write_text("基于附件输出社交电商 AARRR 指标方案", encoding="utf-8")
    pdf.write_bytes(Path("fixtures/attachment.pdf").read_bytes())
    return Phase1ToolContext(query_path=query, pdf_path=pdf, pdf_output_path=out)


def test_mock_agent_tool_sequence(ctx):
    trace: list[dict] = []

    dispatch_tool("read_text", {"path": str(ctx.query_path)}, trace, ctx=ctx)
    dispatch_tool("read_pdf", {"path": str(ctx.pdf_path)}, trace, ctx=ctx)
    dispatch_tool("extract_evidence_pack", {"path": str(ctx.pdf_path)}, trace, ctx=ctx)

    md = """# 报告\n\n## 北极星指标\n**GMV** [E01]\n\n## 管理层摘要\n获客激活留存变现传播\n健康指标 诊断指标\n目标值 黄色预警 红色预警\n周度 月度 季度\n"""
    dispatch_tool(
        "write_pdf_report",
        {"content": md, "path": str(ctx.pdf_output_path)},
        trace,
        ctx=ctx,
    )

    assert len(trace) == 4
    assert trace[0]["tool"] == "read_text"
    assert trace[-1]["tool"] == "write_pdf_report"
    assert ctx.state.state.value == "done"
    assert ctx.evidence_path.exists()


def test_mock_agent_rejects_out_of_order(ctx):
    trace: list[dict] = []
    with pytest.raises(Exception):
        dispatch_tool("read_pdf", {"path": str(ctx.pdf_path)}, trace, ctx=ctx)


def test_mock_agent_self_check_and_structured_report(ctx):
    trace: list[dict] = []

    dispatch_tool("read_text", {"path": str(ctx.query_path)}, trace, ctx=ctx)
    dispatch_tool("read_pdf", {"path": str(ctx.pdf_path)}, trace, ctx=ctx)
    dispatch_tool("extract_evidence_pack", {"path": str(ctx.pdf_path)}, trace, ctx=ctx)

    md_preview = "# 草稿\n北极星 获客 激活 留存 变现 传播\n健康指标 诊断指标\n目标值 黄色预警 红色预警\n周度 月度 季度\n[E01]\n" + "x" * 1600
    check = dispatch_tool("self_check_report", {"content": md_preview}, trace, ctx=ctx)
    check_data = json.loads(check)
    assert check_data["passed"] is True

    dispatch_tool(
        "write_structured_report",
        {"report": SAMPLE, "path": str(ctx.pdf_output_path)},
        trace,
        ctx=ctx,
    )

    assert ctx.pdf_output_path.with_suffix(".md").exists()
    assert ctx.pdf_output_path.with_suffix(".structured.json").exists()
    assert trace[-1]["tool"] == "write_structured_report"
    assert all("phase1_state" in e for e in trace)


def test_write_allowed_for_off_domain_attachment(ctx):
    trace: list[dict] = []
    dispatch_tool("read_text", {"path": str(ctx.query_path)}, trace, ctx=ctx)
    dispatch_tool("read_pdf", {"path": str(ctx.pdf_path)}, trace, ctx=ctx)
    ctx._pdf_text_cache = "DNS 中继服务器 RCODE select() dnsrelay dnsperf 实验报告 bupt"
    dispatch_tool("extract_evidence_pack", {"path": str(ctx.pdf_path)}, trace, ctx=ctx)

    md = "# 报告\n北极星 GMV\n获客 激活 留存 变现 传播\n健康指标 诊断指标\n目标值 黄色预警 红色预警\n周度 月度 季度\n"
    result = dispatch_tool(
        "write_pdf_report",
        {"content": md, "path": str(ctx.pdf_output_path)},
        trace,
        ctx=ctx,
    )
    assert "报告已生成" in result
    assert ctx.pdf_output_path.with_suffix(".md").exists()
