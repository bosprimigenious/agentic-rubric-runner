"""Phase 1 报告内容完整性检查。"""

from __future__ import annotations

from aarrr_agent.config import MIN_REPORT_CONTENT_CHARS

REQUIRED_REPORT_KEYWORDS = [
    "北极星指标",
    "关键健康指标",
    "诊断指标",
    "AARRR",
    "获客",
    "激活",
    "留存",
    "变现",
    "传播",
    "目标值",
    "黄色预警",
    "红色预警",
    "周度",
    "月度",
    "季度",
]


def validate_report_content(content: str) -> list[str]:
    """返回缺失项列表；空列表表示通过基本完整性检查。"""
    issues: list[str] = []
    for keyword in REQUIRED_REPORT_KEYWORDS:
        if keyword not in content:
            issues.append(f"缺少关键词: {keyword}")
    if len(content) < MIN_REPORT_CONTENT_CHARS:
        issues.append(f"报告内容过短 ({len(content)} 字符，建议 ≥ {MIN_REPORT_CONTENT_CHARS})")
    return issues
