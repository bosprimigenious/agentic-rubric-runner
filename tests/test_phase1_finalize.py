"""测试：Phase 1 完成校验与离题附件错误码。"""

import pytest

from aarrr_agent.agent import _finalize_phase1
from aarrr_agent.errors import PipelineError
from aarrr_agent.tools import Phase1ToolContext


def test_finalize_raises_e007_for_irrelevant_attachment(tmp_path):
    ctx = Phase1ToolContext(
        query_path=tmp_path / "query.txt",
        pdf_path=tmp_path / "attachment.pdf",
        pdf_output_path=tmp_path / "phase1_output.pdf",
    )
    ctx.attachment_relevant = False
    ctx._pdf_text_cache = "智能机器人实践训练指导书 嵌入式 单片机"

    trace = [
        {"tool": "read_text", "status": "ok"},
        {"tool": "read_pdf", "status": "ok"},
        {"tool": "extract_evidence_pack", "status": "ok"},
        {
            "tool": "write_pdf_report",
            "status": "error",
            "error": "[E007] 附件与社交电商/AARRR 增长领域不匹配，拒绝写入报告。",
        },
    ]

    with pytest.raises(PipelineError) as exc:
        _finalize_phase1(ctx, trace, phase1_done=True)

    assert exc.value.code == "E007"
    assert "领域校验" in exc.value.message or "不一致" in exc.value.message
