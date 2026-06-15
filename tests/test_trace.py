"""测试：Agent trace 记录格式。"""

import json

from aarrr_agent.tools import Phase1ToolContext, _sanitize_args_for_trace, dispatch_tool, save_trace


def test_sanitize_args_truncates_long_strings():
    preview = _sanitize_args_for_trace({"content": "x" * 500, "path": "out.pdf"})
    assert "500 chars" in preview["content"]
    assert preview["path"] == "out.pdf"


def test_dispatch_tool_trace_fields(tmp_path):
    ctx = Phase1ToolContext(
        query_path=tmp_path / "query.txt",
        pdf_path=tmp_path / "a.pdf",
        pdf_output_path=tmp_path / "out.pdf",
    )
    (tmp_path / "query.txt").write_text("task content", encoding="utf-8")
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n")

    trace: list[dict] = []
    dispatch_tool(
        "read_text",
        {"path": str(tmp_path / "query.txt")},
        trace,
        ctx=ctx,
    )

    entry = trace[0]
    assert entry["step"] == 1
    assert entry["tool"] == "read_text"
    assert entry["status"] == "ok"
    assert "duration_ms" in entry
    assert "timestamp" in entry
    assert "task" in entry["result_preview"]


def test_save_trace_jsonl(tmp_path):
    trace = [
        {
            "step": 1,
            "tool": "read_text",
            "status": "ok",
            "timestamp": "2026-06-15T14:30:00Z",
            "duration_ms": 12,
            "result_preview": "hello",
        }
    ]
    out = tmp_path / "agent_trace.jsonl"
    save_trace(trace, str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert entry["tool"] == "read_text"
    assert entry["duration_ms"] == 12
