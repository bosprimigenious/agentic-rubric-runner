"""测试：对外链接常量与文档一致。"""

from pathlib import Path

from aarrr_agent.config import GITHUB_PAGES_URL, GITHUB_REPO_URL, STREAMLIT_APP_URL


def test_streamlit_url_in_readme_and_docs():
    readme = Path("README.md").read_text(encoding="utf-8")
    docs = Path("docs/index.html").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert STREAMLIT_APP_URL in readme
    assert "Deploy Console" in readme
    assert STREAMLIT_APP_URL in docs
    assert "Deploy Console" in docs
    assert STREAMLIT_APP_URL in pyproject
    assert GITHUB_PAGES_URL in readme
    assert GITHUB_REPO_URL in readme
