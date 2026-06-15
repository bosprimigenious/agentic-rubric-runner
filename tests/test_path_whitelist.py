"""测试：Phase 1 路径白名单。"""

import pytest

from aarrr_agent.tools import Phase1ToolContext, read_text_phase1


def test_phase1_blocks_rubrics_read():
    ctx = Phase1ToolContext(
        query_path="fixtures/query.txt",
        pdf_path="fixtures/attachment.pdf",
        pdf_output_path="phase1_output.pdf",
    )
    with pytest.raises(PermissionError):
        read_text_phase1("fixtures/rubrics.json", ctx)


def test_phase1_allows_query_read():
    ctx = Phase1ToolContext(
        query_path="fixtures/query.txt",
        pdf_path="fixtures/attachment.pdf",
        pdf_output_path="phase1_output.pdf",
    )
    text = read_text_phase1("fixtures/query.txt", ctx)
    assert len(text) > 0
