"""测试：Agent 工具消息协议（tool_calls 与 tool 回复顺序）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from aarrr_agent.agent import _execute_tool_turn, _message_to_dict
from aarrr_agent.tools import Phase1ToolContext


@dataclass
class _Fn:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _Fn


def _assistant_with_tools(*calls: tuple[str, str, str]) -> SimpleNamespace:
    """构造带 tool_calls 的 assistant message。"""
    return SimpleNamespace(
        role="assistant",
        content=None,
        tool_calls=[
            _ToolCall(id=tc_id, function=_Fn(name=name, arguments=args))
            for tc_id, name, args in calls
        ],
    )


@pytest.fixture
def ctx(tmp_path):
    query = tmp_path / "query.txt"
    pdf = tmp_path / "attachment.pdf"
    out = tmp_path / "phase1_output.pdf"
    query.write_text("基于附件输出社交电商 AARRR 指标方案", encoding="utf-8")
    pdf.write_bytes(Path("fixtures/attachment.pdf").read_bytes())
    return Phase1ToolContext(query_path=query, pdf_path=pdf, pdf_output_path=out)


def test_message_to_dict_sets_null_content_for_tool_calls():
    msg = _assistant_with_tools(
        ("call_1", "read_text", '{"path": "/tmp/query.txt"}'),
    )
    data = _message_to_dict(msg)
    assert data["content"] is None
    assert len(data["tool_calls"]) == 1


def test_execute_tool_turn_no_user_message_between_tool_responses(ctx):
    trace: list[dict] = []
    messages: list[dict] = []
    msg = _assistant_with_tools(
        ("call_read", "read_text", f'{{"path": "{ctx.query_path}"}}'),
    )
    messages.append(_message_to_dict(msg))

    _execute_tool_turn(msg, messages, trace, ctx)

    assert [m["role"] for m in messages] == ["assistant", "tool"]
    assert messages[-1]["tool_call_id"] == "call_read"


def test_execute_tool_turn_multiple_tools_all_get_responses(ctx):
    trace: list[dict] = []
    messages: list[dict] = []
    msg = _assistant_with_tools(
        ("call_1", "read_text", f'{{"path": "{ctx.query_path}"}}'),
        ("call_2", "read_pdf", f'{{"path": "{ctx.pdf_path}"}}'),
    )
    messages.append(_message_to_dict(msg))

    # 并行两个工具时第二个会因状态机顺序失败，但仍须返回 tool 消息
    _execute_tool_turn(msg, messages, trace, ctx)

    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert {m["tool_call_id"] for m in tool_msgs} == {"call_1", "call_2"}
    assert all(m["role"] in {"assistant", "tool"} for m in messages)
