"""测试：Phase 1 完成校验。"""

import pytest

from aarrr_agent.agent import _finalize_phase1
from aarrr_agent.errors import PipelineError
from aarrr_agent.phase1_state import Phase1State
from aarrr_agent.tools import Phase1ToolContext


def test_finalize_raises_e003_when_claimed_done_without_write(tmp_path):
    ctx = Phase1ToolContext(
        query_path=tmp_path / "query.txt",
        pdf_path=tmp_path / "attachment.pdf",
        pdf_output_path=tmp_path / "phase1_output.pdf",
    )
    ctx.attachment_relevant = False
    ctx._pdf_text_cache = "樱桃栽培 土壤 病虫害"

    trace = [
        {"tool": "read_text", "status": "ok"},
        {"tool": "read_pdf", "status": "ok"},
        {"tool": "extract_evidence_pack", "status": "ok"},
    ]

    with pytest.raises(PipelineError) as exc:
        _finalize_phase1(ctx, trace, phase1_done=True)

    assert exc.value.code == "E003"


def test_finalize_passes_when_write_completed_despite_irrelevant_attachment(tmp_path):
    ctx = Phase1ToolContext(
        query_path=tmp_path / "query.txt",
        pdf_path=tmp_path / "attachment.pdf",
        pdf_output_path=tmp_path / "phase1_output.pdf",
    )
    ctx.attachment_relevant = False
    ctx.state.record_tool("read_text")
    ctx.state.record_tool("read_pdf")
    ctx.state.record_tool("extract_evidence_pack")
    ctx.state.record_tool("write_pdf_report")

    trace = [{"tool": "write_pdf_report", "status": "ok"}]

    _finalize_phase1(ctx, trace, phase1_done=True)
    assert ctx.state.state == Phase1State.DONE
