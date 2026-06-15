"""Markdown 转 PDF（reportlab + 中文字体，专业排版）。"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from aarrr_agent.config import FONTS_DIR
from aarrr_agent.errors import PipelineError

_FONT_REGISTERED = False
_FONT_NAME = "Chinese"
_DOC_TITLE = "分析报告"

# 配色
PRIMARY = colors.HexColor("#1e3a5f")
ACCENT = colors.HexColor("#2563eb")
HEADER_BG = colors.HexColor("#eff6ff")
TABLE_HEADER_BG = colors.HexColor("#1e40af")
TABLE_HEADER_FG = colors.white
TABLE_ALT_BG = colors.HexColor("#f8fafc")
TABLE_BORDER = colors.HexColor("#cbd5e1")
TEXT_MUTED = colors.HexColor("#64748b")
HR_COLOR = colors.HexColor("#e2e8f0")


def _candidate_font_paths() -> list[Path]:
    candidates = [
        FONTS_DIR / "NotoSansCJK-Regular.ttc",
        FONTS_DIR / "NotoSansCJK-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    return [p for p in candidates if p.exists()]


def register_chinese_font() -> str:
    global _FONT_REGISTERED, _FONT_NAME
    if _FONT_REGISTERED:
        return _FONT_NAME

    for path in _candidate_font_paths():
        try:
            suffix = path.suffix.lower()
            if suffix == ".ttc":
                pdfmetrics.registerFont(TTFont(_FONT_NAME, str(path), subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(_FONT_NAME, str(path)))
            _FONT_REGISTERED = True
            return _FONT_NAME
        except Exception:
            continue

    raise PipelineError(
        "E006",
        "未找到可用中文字体。请将 NotoSansCJK-Regular.ttc 放入 fonts/ 目录，"
        "或确保系统已安装微软雅黑/黑体等中文字体。",
    )


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title",
            fontName=font_name,
            fontSize=22,
            leading=30,
            textColor=PRIMARY,
            spaceAfter=6,
            spaceBefore=0,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=TEXT_MUTED,
            spaceAfter=16,
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName=font_name,
            fontSize=16,
            leading=22,
            textColor=PRIMARY,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName=font_name,
            fontSize=13,
            leading=18,
            textColor=ACCENT,
            spaceBefore=12,
            spaceAfter=6,
            borderPadding=4,
        ),
        "h3": ParagraphStyle(
            "h3",
            fontName=font_name,
            fontSize=11,
            leading=16,
            textColor=PRIMARY,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=font_name,
            fontSize=10,
            leading=17,
            textColor=colors.HexColor("#334155"),
            spaceAfter=6,
            alignment=TA_JUSTIFY,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName=font_name,
            fontSize=10,
            leading=16,
            textColor=colors.HexColor("#334155"),
            leftIndent=14,
            bulletIndent=6,
            spaceAfter=4,
        ),
        "numbered": ParagraphStyle(
            "numbered",
            fontName=font_name,
            fontSize=10,
            leading=16,
            textColor=colors.HexColor("#334155"),
            leftIndent=18,
            spaceAfter=4,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            fontName=font_name,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155"),
        ),
        "table_header": ParagraphStyle(
            "table_header",
            fontName=font_name,
            fontSize=9,
            leading=13,
            textColor=TABLE_HEADER_FG,
        ),
        "blockquote": ParagraphStyle(
            "blockquote",
            fontName=font_name,
            fontSize=10,
            leading=16,
            textColor=TEXT_MUTED,
            leftIndent=12,
            borderColor=ACCENT,
            borderWidth=0,
            borderPadding=6,
            spaceAfter=8,
        ),
    }


def _inline_markup(text: str) -> str:
    """将常见 Markdown 行内语法转为 ReportLab Paragraph 可识别的标签。"""
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+?)`", r'<font color="#0f766e">\1</font>', text)
    return text


def _para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_inline_markup(text), style)


def _parse_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.count("|") < 2:
        return None
    return [c.strip() for c in stripped.strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    return bool(re.match(r"^\|[\s\-:|]+\|$", line.strip()))


def _is_hr(line: str) -> bool:
    s = line.strip()
    return s in {"---", "***", "___"} or bool(re.match(r"^(-{3,}|\*{3,}|_{3,})$", s))


def _extract_doc_title(md_content: str) -> str:
    for line in md_content.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return "分析报告"


def _draw_page_footer(canvas, doc, font_name: str, title: str) -> None:
    canvas.saveState()
    width, height = doc.pagesize

    canvas.setStrokeColor(HR_COLOR)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 1.6 * cm, width - doc.rightMargin, 1.6 * cm)

    canvas.setFont(font_name, 8)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(doc.leftMargin, 1.0 * cm, title[:40])
    canvas.drawRightString(width - doc.rightMargin, 1.0 * cm, f"第 {canvas.getPageNumber()} 页")

    canvas.restoreState()


def _title_banner(title: str, styles: dict[str, ParagraphStyle]) -> list:
    """首页标题区：色块 + 主标题。"""
    banner_data = [[_para(title, styles["title"])]]
    banner = Table(banner_data, colWidths=["100%"])
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    return [
        banner,
        Spacer(1, 4 * mm),
        _para("Document Evaluation Console — generated report", styles["subtitle"]),
        HRFlowable(width="100%", thickness=1, color=HR_COLOR, spaceBefore=2, spaceAfter=10),
    ]


def _build_table(
    rows: list[list[str]],
    font_name: str,
    styles: dict[str, ParagraphStyle],
    available_width: float,
) -> Table:
    col_count = max(len(r) for r in rows)
    normalized = [r + [""] * (col_count - len(r)) for r in rows]
    col_width = available_width / col_count

    table_data: list[list] = []
    for row_idx, row in enumerate(normalized):
        cell_style = styles["table_header"] if row_idx == 0 else styles["table_cell"]
        table_data.append([_para(cell, cell_style) for cell in row])

    table = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1)
    style_cmds: list = [
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.4, TABLE_BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), TABLE_HEADER_FG),
    ]
    for r in range(1, len(table_data)):
        if r % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, r), (-1, r), TABLE_ALT_BG))
    table.setStyle(TableStyle(style_cmds))
    return table


def markdown_to_pdf(md_content: str, output_path: str) -> None:
    """将 Markdown 内容转换为排版精美的 PDF。"""
    global _DOC_TITLE
    font_name = register_chinese_font()
    styles = _build_styles(font_name)
    _DOC_TITLE = _extract_doc_title(md_content)

    page_w, _ = A4
    margin_lr = 2.2 * cm
    content_width = page_w - 2 * margin_lr

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=margin_lr,
        rightMargin=margin_lr,
        topMargin=2.4 * cm,
        bottomMargin=2.2 * cm,
        title=_DOC_TITLE,
        author="Agentic Rubric Runner",
    )

    def on_page(canvas, _doc):
        _draw_page_footer(canvas, _doc, font_name, _DOC_TITLE)

    story: list = []
    lines = md_content.split("\n")
    i = 0
    first_h1_done = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            story.append(Spacer(1, 4))
            i += 1
            continue

        if _is_hr(stripped):
            story.append(HRFlowable(width="100%", thickness=0.8, color=HR_COLOR, spaceBefore=6, spaceAfter=10))
            i += 1
            continue

        if stripped.startswith("# "):
            title_text = stripped[2:].strip()
            if not first_h1_done:
                story.extend(_title_banner(title_text, styles))
                first_h1_done = True
            else:
                story.append(Spacer(1, 8))
                story.append(_para(title_text, styles["h1"]))
                story.append(
                    HRFlowable(width="30%", thickness=2, color=ACCENT, spaceBefore=0, spaceAfter=8, hAlign="LEFT")
                )
            i += 1
            continue

        if stripped.startswith("## "):
            block = [
                _para(stripped[3:].strip(), styles["h2"]),
                HRFlowable(width="100%", thickness=0.5, color=HR_COLOR, spaceBefore=0, spaceAfter=6),
            ]
            story.append(KeepTogether(block))
            i += 1
            continue

        if stripped.startswith("### "):
            story.append(_para(stripped[4:].strip(), styles["h3"]))
            i += 1
            continue

        if stripped.startswith("#### "):
            story.append(_para(stripped[5:].strip(), styles["h3"]))
            i += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            story.append(_para(" ".join(quote_lines), styles["blockquote"]))
            continue

        if stripped.startswith("|"):
            table_rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row_line = lines[i].strip()
                if not _is_table_separator(row_line):
                    cells = _parse_table_row(row_line)
                    if cells:
                        table_rows.append(cells)
                i += 1

            if table_rows:
                story.append(_build_table(table_rows, font_name, styles, content_width))
                story.append(Spacer(1, 10))
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            story.append(_para("• " + stripped[2:], styles["bullet"]))
            i += 1
            continue

        num_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if num_match:
            story.append(_para(f"{num_match.group(1)}. {num_match.group(2)}", styles["numbered"]))
            i += 1
            continue

        story.append(_para(stripped, styles["body"]))
        i += 1

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
