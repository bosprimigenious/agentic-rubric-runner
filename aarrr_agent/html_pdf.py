"""HTML/CSS 报告渲染与 PDF 导出（WeasyPrint + ReportLab fallback）。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aarrr_agent.config import PDF_RENDERER
from aarrr_agent.html_report import render_executive_html
from aarrr_agent.md_report_parser import parse_markdown_report
from aarrr_agent.pdf_gen import markdown_to_pdf

logger = logging.getLogger(__name__)


def _resolve_renderer(renderer: str | None = None) -> str:
    return (renderer or os.getenv("PDF_RENDERER") or PDF_RENDERER or "auto").lower()


def weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


def html_to_pdf(html_content: str, output_path: str | Path, *, base_url: str | Path | None = None) -> None:
    from weasyprint import HTML

    base = str(base_url or Path(__file__).resolve().parent)
    HTML(string=html_content, base_url=base).write_pdf(str(output_path))


def render_markdown_report(
    md_content: str,
    pdf_path: str | Path,
    *,
    run_id: str = "",
    model: str = "",
    renderer: str | None = None,
) -> tuple[Path, Path, str]:
    """
    解析 Markdown → HTML → PDF。
    返回 (html_path, pdf_path, renderer_used)。
    """
    pdf = Path(pdf_path)
    html_path = pdf.with_suffix(".html")
    mode = _resolve_renderer(renderer)

    report = parse_markdown_report(md_content, run_id=run_id, model=model)
    html_content = render_executive_html(report)
    html_path.write_text(html_content, encoding="utf-8")

    if mode == "reportlab":
        markdown_to_pdf(md_content, str(pdf))
        return html_path, pdf, "reportlab"

    if mode == "html" and not weasyprint_available():
        logger.warning("WeasyPrint 未安装，回退 ReportLab")
        markdown_to_pdf(md_content, str(pdf))
        return html_path, pdf, "reportlab"

    if mode in ("auto", "html"):
        try:
            html_to_pdf(html_content, pdf)
            return html_path, pdf, "html"
        except Exception as exc:
            if mode == "html":
                logger.warning("WeasyPrint 渲染失败，回退 ReportLab: %s", exc)
            else:
                logger.warning("WeasyPrint 不可用或渲染失败，回退 ReportLab: %s", exc)
            markdown_to_pdf(md_content, str(pdf))
            return html_path, pdf, "reportlab"

    markdown_to_pdf(md_content, str(pdf))
    return html_path, pdf, "reportlab"
