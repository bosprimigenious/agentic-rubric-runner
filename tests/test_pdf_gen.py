"""测试：PDF 生成（中文字体）。"""

from pathlib import Path

import pytest

from aarrr_agent.pdf_gen import markdown_to_pdf, register_chinese_font


def test_register_chinese_font():
    font = register_chinese_font()
    assert font == "Chinese"


def test_markdown_to_pdf_chinese(tmp_path):
    out = tmp_path / "report.pdf"
    md = "# 标题\n\n北极星指标与 AARRR 获客激活留存变现传播。\n"
    markdown_to_pdf(md, str(out))
    assert out.exists()
    assert out.stat().st_size > 500
