"""Markdown 转 PDF（reportlab + 中文字体）。"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from aarrr_agent.config import FONTS_DIR

_FONT_REGISTERED = False
_FONT_NAME = "Chinese"


def _candidate_font_paths() -> list[Path]:
    """按平台优先级查找可用中文字体。"""
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
    """注册中文字体，全局只注册一次。"""
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

    raise RuntimeError(
        "未找到可用中文字体。请将 NotoSansCJK-Regular.ttc 放入 fonts/ 目录，"
        "或确保系统已安装微软雅黑/黑体等中文字体。"
    )


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    return {
        "h1": ParagraphStyle(
            "h1", fontName=font_name, fontSize=18, spaceAfter=12, leading=24
        ),
        "h2": ParagraphStyle(
            "h2", fontName=font_name, fontSize=14, spaceAfter=8, leading=20
        ),
        "h3": ParagraphStyle(
            "h3", fontName=font_name, fontSize=12, spaceAfter=6, leading=18
        ),
        "body": ParagraphStyle(
            "body", fontName=font_name, fontSize=10, spaceAfter=4, leading=16
        ),
    }


def _para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text), style)


def _parse_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.count("|") < 2:
        return None
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    return cells


def _is_table_separator(line: str) -> bool:
    return bool(re.match(r"^\|[\s\-:|]+\|$", line.strip()))


def markdown_to_pdf(md_content: str, output_path: str) -> None:
    """将 Markdown 内容转换为 PDF。"""
    font_name = register_chinese_font()
    styles = _build_styles(font_name)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story: list = []
    lines = md_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            story.append(Spacer(1, 6))
            i += 1
            continue

        if stripped.startswith("# "):
            story.append(_para(stripped[2:], styles["h1"]))
            i += 1
            continue
        if stripped.startswith("## "):
            story.append(_para(stripped[3:], styles["h2"]))
            i += 1
            continue
        if stripped.startswith("### "):
            story.append(_para(stripped[4:], styles["h3"]))
            i += 1
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
                col_count = max(len(r) for r in table_rows)
                normalized = [r + [""] * (col_count - len(r)) for r in table_rows]
                table = Table(normalized, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (-1, -1), font_name),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 8))
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            story.append(_para("• " + stripped[2:], styles["body"]))
        else:
            story.append(_para(stripped, styles["body"]))
        i += 1

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)
