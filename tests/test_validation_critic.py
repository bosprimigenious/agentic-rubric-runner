"""测试：报告自检 Critic。"""

from aarrr_agent.validation import self_check_report, validate_report_content

GOOD_MD = """# 报告

## 北极星指标
**GMV** [E01]

## 管理层摘要
获客 激活 留存 变现 传播
健康指标与诊断指标分层说明

## 目标值
关键指标目标值

## 预警规则
黄色预警 红色预警

## 复盘节奏
周度 月度 季度
""" + "x" * 1600


def test_self_check_report_passes_complete_draft():
    result = self_check_report(GOOD_MD)
    assert result["passed"] is True
    assert result["issues"] == []


def test_self_check_report_flags_missing_evidence():
    bad = GOOD_MD.replace("[E01]", "")
    result = self_check_report(bad)
    assert result["passed"] is False
    assert any("证据" in i for i in result["issues"])


def test_validate_report_content_keywords():
    issues = validate_report_content("短")
    assert issues
