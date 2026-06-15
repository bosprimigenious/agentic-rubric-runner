"""附件领域相关性检测与评分门控。"""

from __future__ import annotations

import re
from typing import Any

from aarrr_agent.schemas import GradingResult

# 任务期望附件应包含的增长/AARRR 领域词（仅用于附件正文检测）
_DOMAIN_KEYWORDS = (
    "社交电商",
    "AARRR",
    "用户增长",
    "获客",
    "激活",
    "留存",
    "变现",
    "传播",
    "北极星",
    "GMV",
    "留存率",
    "病毒系数",
    "终身价值",
    "获客成本",
    "裂变",
    "分享推荐",
    "拼团",
    "社交电商",
)

# 明显偏离任务领域的信号（附件中出现则视为离题源文档）
_OFF_DOMAIN_SIGNALS = (
    "樱桃",
    "栽培",
    "果树",
    "DNS",
    "dns",
    "中继",
    "中继服务器",
    "RCODE",
    "dig ",
    "FORMERR",
    "select()",
    "dnsrelay",
    "dnsperf",
    "计算机组成",
    "实验报告",
    "电路",
    "汇编",
    "农作物",
    "病虫害",
    "土壤",
    "G网",
    "路由表",
    "域名解析",
)

# 报告强行套用离题附件时的典型幻觉措辞
_FORCED_ANALOGY = re.compile(
    r"DNS|select\s*\(|RCODE|dnsrelay|dnsperf|上游中继|本地解析|主循环|client_fd|upstream",
    re.I,
)


def assess_attachment_domain(attachment_text: str, query_text: str = "") -> dict[str, Any]:
    """
    检测附件是否属于任务要求的领域。
    注意：仅以附件正文为准，不把 query 关键词混入（避免 DNS 附件因 query 误判为相关）。
    """
    body = attachment_text[:120000]
    domain_hits = [kw for kw in _DOMAIN_KEYWORDS if kw in body]
    off_hits = [kw for kw in _OFF_DOMAIN_SIGNALS if kw in body]

    # 至少 3 个领域词，且显著多于离题信号
    relevant = len(domain_hits) >= 3 and len(domain_hits) > len(off_hits)

    # query 仅作辅助说明，不参与 relevant 判定
    _ = query_text

    return {
        "relevant": relevant,
        "domain_hits": domain_hits,
        "off_domain_hits": off_hits,
        "domain_hit_count": len(domain_hits),
        "off_domain_hit_count": len(off_hits),
    }


def detect_forced_analogy_report(report_text: str, attachment_text: str) -> bool:
    """报告是否将离题附件（如 DNS 实验）强行类比为增长指标。"""
    assessment = assess_attachment_domain(attachment_text)
    if assessment["relevant"]:
        return False
    return bool(_FORCED_ANALOGY.search(report_text))


def enforce_attachment_gate(
    result: GradingResult,
    rubrics: dict[str, Any],
    attachment_text: str,
    query_text: str = "",
    report_text: str = "",
) -> tuple[GradingResult, dict[str, Any]]:
    """
    附件与任务领域不匹配时，程序强制压低分数。
    离题附件场景下仅保留 H01（PDF 格式）可能为 1，其余硬约束归零。
    """
    assessment = assess_attachment_domain(attachment_text, query_text)
    forced_analogy = detect_forced_analogy_report(report_text, attachment_text)
    if assessment["relevant"] and not forced_analogy:
        return result, assessment

    rubric = rubrics["rubric"]
    gate_reason = (
        f"程序门控：附件与社交电商/AARRR 增长领域不匹配"
        f"（附件领域词 {assessment['domain_hit_count']} 个，"
        f"离题信号 {assessment['off_domain_hit_count']} 个："
        f"{', '.join(assessment['off_domain_hits'][:6]) or '无'}）。"
    )
    if forced_analogy:
        gate_reason += " 报告将离题附件（如 DNS 实验）强行类比为增长指标，事实不可追溯。"

    for i, item in enumerate(rubric["hard_constraints"], 1):
        cid = f"H{i:02d}"
        hc = next(c for c in result.hard_constraints if c.id == cid)
        # 离题附件：仅 PDF 格式类硬约束可保留
        if cid == "H01":
            continue
        hc.score = 0
        hc.missing = list(dict.fromkeys([*hc.missing, "附件领域不匹配或事实伪造"]))
        hc.reason = f"{gate_reason} 原评审：{hc.reason}"

    for sc in result.soft_constraints:
        sc.score = 0
        sc.missing = list(dict.fromkeys([*sc.missing, "离题附件不支持软约束给分"]))
        sc.reason = f"{gate_reason} 原评审：{sc.reason}"

    for oc in result.optional_constraints:
        oc.score = 0
        oc.missing = list(dict.fromkeys([*oc.missing, "离题附件"]))
        oc.reason = f"{gate_reason} 原评审：{oc.reason}"

    return result, assessment
