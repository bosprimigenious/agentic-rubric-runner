"""测试：Phase 1 状态机。"""

import pytest

from aarrr_agent.errors import PipelineError
from aarrr_agent.phase1_state import Phase1State, Phase1StateMachine


def test_state_machine_enforces_order():
    sm = Phase1StateMachine()
    sm.record_tool("read_text")
    assert sm.state == Phase1State.NEED_PDF

    with pytest.raises(PipelineError, match="E003"):
        sm.assert_tool_allowed("write_pdf_report")

    sm.record_tool("read_pdf")
    sm.record_tool("extract_evidence_pack")
    assert sm.state == Phase1State.NEED_REPORT

    sm.record_tool("write_pdf_report")
    assert sm.state == Phase1State.DONE

    with pytest.raises(PipelineError, match="禁止继续"):
        sm.assert_tool_allowed("read_text")


def test_state_machine_requires_phase1_done():
    sm = Phase1StateMachine()
    sm.record_tool("read_text")
    sm.record_tool("read_pdf")
    sm.record_tool("extract_evidence_pack")
    sm.record_tool("write_structured_report")

    with pytest.raises(PipelineError, match="PHASE1_DONE"):
        sm.assert_complete(phase1_done=False)

    sm.assert_complete(phase1_done=True)
