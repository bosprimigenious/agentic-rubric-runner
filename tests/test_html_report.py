"""测试：Markdown 解析与 HTML 报告渲染。"""

from pathlib import Path

import pytest

from aarrr_agent.html_pdf import render_markdown_report, weasyprint_available
from aarrr_agent.html_report import render_executive_html
from aarrr_agent.md_report_parser import markdown_fragment_to_html, parse_markdown_report

SAMPLE_MD = """# 社交电商平台增长指标体系报告

## 管理层摘要

- 优化激活路径
- 提升 7 日留存
- 建立裂变追踪

## 北极星指标

**有效交易用户数** 为核心北极星，衡量平台真实增长。

## AARRR 指标看板

| 阶段 | 健康指标 | 诊断指标 |
|------|----------|----------|
| 获客 | 新增有效用户数 | CAC、渠道转化率 |
| 激活 | 首单转化率 | 激活漏斗完成率 |
| 留存 | 7 日留存率 | 月活/日活比 |
| 变现 | GMV | ARPU、客单价 |
| 传播 | 裂变系数 K | 分享率 |

## 预警规则

| 指标 | 正常 | 黄色预警 | 红色预警 |
|------|------|----------|----------|
| CAC/LTV | 绿色 <1:3 | 黄色 1:3~1:2 | 红色 >1:2 |
| 7日留存 | 绿色 >40% | 黄色 30-40% | 红色 <30% |

## 复盘节奏

周度复盘获客与激活，月度复盘留存与变现。
"""


def test_parse_markdown_report_extracts_sections():
    report = parse_markdown_report(SAMPLE_MD, run_id="20260615_153000", model="deepseek-chat")
    assert "社交电商平台" in report.title
    assert report.north_star == "有效交易用户数"
    assert len(report.aarrr_stages) == 5
    assert report.aarrr_stages[0].name == "获客"
    assert report.aarrr_stages[0].health_metric == "新增有效用户数"
    assert len(report.warning_rows) >= 1
    assert report.run_id == "20260615_153000"


def test_markdown_fragment_to_html_table_and_list():
    html = markdown_fragment_to_html(
        "| 指标 | 值 |\n|------|----|\n| DAU | 10万 |\n\n- 条目一\n- 条目二"
    )
    assert "<table>" in html
    assert "<ul>" in html
    assert "DAU" in html


def test_render_executive_html_contains_cover_and_flow():
    report = parse_markdown_report(SAMPLE_MD)
    html = render_executive_html(report)
    assert "<!DOCTYPE html>" in html
    assert "管理层摘要" in html
    assert "AARRR 增长链路" in html
    assert "获客" in html
    assert "@page" in html


def test_render_markdown_report_writes_html(tmp_path):
    pdf_path = tmp_path / "phase1_output.pdf"
    html_path, pdf_out, renderer = render_markdown_report(
        SAMPLE_MD,
        pdf_path,
        renderer="reportlab",
    )
    assert html_path.exists()
    assert html_path.suffix == ".html"
    assert "社交电商平台" in html_path.read_text(encoding="utf-8")
    assert pdf_out.exists()
    assert renderer == "reportlab"


@pytest.mark.skipif(not weasyprint_available(), reason="WeasyPrint 未安装或系统依赖缺失")
def test_render_markdown_report_weasyprint_pdf(tmp_path):
    pdf_path = tmp_path / "phase1_output.pdf"
    _, pdf_out, renderer = render_markdown_report(SAMPLE_MD, pdf_path, renderer="html")
    assert renderer == "html"
    assert pdf_out.stat().st_size > 1000
