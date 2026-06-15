"""Phase 1 报告内容完整性检查与自检 Critic。"""

from __future__ import annotations

import re

from aarrr_agent.config import MIN_REPORT_CONTENT_CHARS

REQUIRED_REPORT_KEYWORDS = [
    "北极星",
    "健康指标",
    "诊断指标",
    "获客",
    "激活",
    "留存",
    "变现",
    "传播",
    "目标",
    "黄色预警",
    "红色预警",
    "周",
    "月",
    "季",
]

_AARRR_STAGES = ("获客", "激活", "留存", "变现", "传播")
_EVIDENCE_REF = re.compile(r"\[E\d{2}\]")


def validate_report_content(content: str) -> list[str]:
    """返回缺失项列表；空列表表示通过基本完整性检查。"""
    issues: list[str] = []
    for keyword in REQUIRED_REPORT_KEYWORDS:
        if keyword not in content:
            issues.append(f"缺少关键词: {keyword}")
    for stage in _AARRR_STAGES:
        if stage not in content:
            issues.append(f"缺少 AARRR 阶段: {stage}")
    if len(content) < MIN_REPORT_CONTENT_CHARS:
        issues.append(f"报告内容过短 ({len(content)} 字符，建议 ≥ {MIN_REPORT_CONTENT_CHARS})")
    if not _EVIDENCE_REF.search(content):
        issues.append("缺少证据引用（格式 [E01]）")
    return issues


def self_check_report(content: str) -> dict[str, list[str]]:
    """结构化自检：返回 passed / issues。"""
    issues = validate_report_content(content)
    checks = {
        "单一北极星指标": bool(re.search(r"北极星", content)) and content.count("北极星") >= 1,
        "五阶段覆盖": all(s in content for s in _AARRR_STAGES),
        "健康/诊断分层": "健康指标" in content and "诊断指标" in content,
        "目标值": "目标" in content,
        "红黄预警": "黄色预警" in content and "红色预警" in content,
        "周月季机制": all(k in content for k in ("周", "月", "季")),
        "证据引用": bool(_EVIDENCE_REF.search(content)),
    }
    for name, ok in checks.items():
        if not ok:
            issues.append(f"自检未通过: {name}")
    return {"passed": not issues, "issues": issues, "checks": checks}
