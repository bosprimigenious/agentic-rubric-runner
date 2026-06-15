"""将 ExecutiveReport 渲染为管理层 HTML 报告。"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from aarrr_agent.report_models import ExecutiveReport

_PKG_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = _PKG_DIR / "templates"
ASSETS_DIR = _PKG_DIR / "assets"


def _load_css() -> str:
    css_path = ASSETS_DIR / "executive_report.css"
    return css_path.read_text(encoding="utf-8")


def render_executive_html(report: ExecutiveReport) -> str:
    """用 Jinja2 模板生成完整 HTML 文档。"""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("executive_report.html")
    return template.render(report=report, css=_load_css())
