"""测试：PDF 生成（中文字体）。"""

from pathlib import Path

import pytest

from aarrr_agent.pdf_gen import markdown_to_pdf, register_chinese_font


def test_register_chinese_font():
    font = register_chinese_font()
    assert font == "Chinese"


def test_markdown_to_pdf_chinese(tmp_path):
    out = tmp_path / "report.pdf"
    md = """# 社交电商增长指标方案

## 北极星指标

平台 **DAU** 为核心北极星指标，依据附件研究结论制定。

### 预警规则

| 指标 | 黄色预警 | 红色预警 |
|------|----------|----------|
| 次日留存 | <35% | <25% |
| 获客成本 | >120元 | >150元 |

- 获客：CAC、渠道转化率
- 激活：三秒激活率

1. 周度复盘获客与激活
2. 月度复盘留存与变现

---

> 所有数据须可追溯至附件原文。
"""
    markdown_to_pdf(md, str(out))
    assert out.exists()
    assert out.stat().st_size > 1500
