"""测试：Grader 附件检索式选页。"""

from aarrr_agent.grader import load_rubrics
from aarrr_agent.retrieval import build_retrieval_keywords, retrieve_relevant_pages
from aarrr_agent.tools import read_pdf


def test_retrieve_prefers_keyword_pages():
    pdf = __import__("pathlib").Path("fixtures/attachment.pdf")
    if not pdf.exists():
        return
    raw = read_pdf(str(pdf))
    rubrics = load_rubrics("fixtures/rubrics.json")
    keywords = build_retrieval_keywords(rubrics, "社交电商 AARRR 增长指标")
    selected = retrieve_relevant_pages(raw, keywords=keywords, budget=8000)
    assert "[PAGE" in selected
    assert any(kw in selected for kw in ("留存", "获客", "AARRR", "增长", "社交"))
