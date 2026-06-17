"""测试：Phase 1 状态机。"""

import pytest

from aarrr_agent.errors import PipelineError
from aarrr_agent.phase1_state import Phase1State, Phase1StateMachine
from aarrr_agent.agent import _tool_choice_for_state, _tools_for_state


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


def test_phase1_tools_are_filtered_by_state():
    assert [tool["function"]["name"] for tool in _tools_for_state(Phase1State.START)] == ["read_text"]
    assert [tool["function"]["name"] for tool in _tools_for_state(Phase1State.NEED_PDF)] == ["read_pdf"]
    assert [tool["function"]["name"] for tool in _tools_for_state(Phase1State.NEED_EVIDENCE)] == ["extract_evidence_pack"]
    assert [tool["function"]["name"] for tool in _tools_for_state(Phase1State.NEED_REPORT)] == ["write_structured_report"]


def test_phase1_tool_choice_is_state_driven():
    assert _tool_choice_for_state(Phase1State.START) == {"type": "function", "function": {"name": "read_text"}}
    assert _tool_choice_for_state(Phase1State.NEED_PDF) == {"type": "function", "function": {"name": "read_pdf"}}
    assert _tool_choice_for_state(Phase1State.NEED_EVIDENCE) == {"type": "function", "function": {"name": "extract_evidence_pack"}}
    assert _tool_choice_for_state(Phase1State.NEED_REPORT) == {"type": "function", "function": {"name": "write_structured_report"}}
    assert _tool_choice_for_state(Phase1State.DONE) == "none"
