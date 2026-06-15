"""测试：报告内容完整性检查。"""

from aarrr_agent.validation import REQUIRED_REPORT_KEYWORDS, validate_report_content


def test_validate_report_content_complete():
    content = "\n".join(REQUIRED_REPORT_KEYWORDS) + "\n[E01]\n" + "x" * 1600
    assert validate_report_content(content) == []


def test_validate_report_content_missing_keyword():
    issues = validate_report_content("短内容")
    assert any("北极星" in i for i in issues)
    assert any("过短" in i for i in issues)
