"""将 Agent 生成的 Markdown 解析为 ExecutiveReport 结构。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from aarrr_agent.report_models import AARRRStage, ExecutiveReport, MetricCard, ReportSection, WarningRow

_AARRR_NAMES = ("获客", "激活", "留存", "变现", "传播")
_SUMMARY_KEYS = ("执行摘要", "管理层摘要", "摘要", "核心结论", "总结")
_NORTH_STAR_KEYS = ("北极星", "北极星指标")
_AARRR_KEYS = ("aarrr", "五阶段", "指标看板", "增长链路", "阶段指标")
_WARNING_KEYS = ("预警", "告警", "阈值")


def _slug(title: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-") or "section"


def _inline_md(text: str) -> str:
    text = xml_escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    return text


def _parse_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.count("|") < 2:
        return None
    return [c.strip() for c in stripped.strip("|").split("|")]


def _is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\|[\s\-:|]+\|$", line.strip()))


def markdown_fragment_to_html(text: str) -> str:
    """将章节 Markdown 片段转为 HTML（段落、列表、表格）。"""
    if not text.strip():
        return ""

    lines = text.splitlines()
    parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("### "):
            parts.append(f"<h3>{_inline_md(stripped[4:].strip())}</h3>")
            i += 1
            continue

        if stripped.startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row_line = lines[i].strip()
                if not _is_table_sep(row_line):
                    cells = _parse_table_row(row_line)
                    if cells:
                        rows.append(cells)
                i += 1
            if rows:
                parts.append(_table_html(rows))
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            items: list[str] = []
            while i < len(lines) and (
                lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")
            ):
                items.append(f"<li>{_inline_md(lines[i].strip()[2:])}</li>")
                i += 1
            parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        num = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if num:
            items = []
            while i < len(lines):
                m = re.match(r"^(\d+)\.\s+(.*)$", lines[i].strip())
                if not m:
                    break
                items.append(f"<li>{_inline_md(m.group(2))}</li>")
                i += 1
            parts.append("<ol>" + "".join(items) + "</ol>")
            continue

        if stripped.startswith(">"):
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            parts.append(f'<blockquote class="quote">{_inline_md(" ".join(quote))}</blockquote>')
            continue

        para: list[str] = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("#", "-", "*", "|", ">")):
            if re.match(r"^\d+\.\s+", lines[i].strip()):
                break
            para.append(lines[i].strip())
            i += 1
        parts.append(f"<p>{_inline_md(' '.join(para))}</p>")

    return "\n".join(parts)


def _table_html(rows: list[list[str]]) -> str:
    head = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    html = ["<table><thead><tr>"]
    html.extend(f"<th>{_inline_md(c)}</th>" for c in head)
    html.append("</tr></thead><tbody>")
    for row in body:
        html.append("<tr>")
        for cell in row:
            cls = _warning_cell_class(cell)
            if cls:
                html.append(f'<td class="{cls}">{_inline_md(cell)}</td>')
            else:
                html.append(f"<td>{_inline_md(cell)}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def _warning_cell_class(cell: str) -> str:
    if any(k in cell for k in ("红色", "红预警", "严重")):
        return "warn-red"
    if any(k in cell for k in ("黄色", "黄预警", "关注")):
        return "warn-yellow"
    if any(k in cell for k in ("绿色", "正常", "健康")):
        return "warn-green"
    return ""


def _split_sections(md: str) -> tuple[str, dict[str, str]]:
    title = "增长指标体系报告"
    sections: dict[str, str] = {}
    current_key = "__intro__"
    buf: list[str] = []

    for line in md.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if buf:
                sections[current_key] = "\n".join(buf).strip()
            current_key = line[3:].strip()
            buf = []
            continue
        buf.append(line)

    if buf:
        sections[current_key] = "\n".join(buf).strip()
    return title, sections


def _match_section(keys: tuple[str, ...], sections: dict[str, str]) -> str:
    for name, body in sections.items():
        if any(k in name for k in keys):
            return body
    return ""


def _extract_bullets(text: str, limit: int = 5) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ")):
            bullets.append(s[2:].strip())
        elif re.match(r"^\d+\.\s+", s):
            bullets.append(re.sub(r"^\d+\.\s+", "", s).strip())
        if len(bullets) >= limit:
            break
    return bullets


def _first_paragraph(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "-", "*", "|", ">")):
            return s
    return ""


def _parse_aarrr_stages(text: str) -> list[AARRRStage]:
    stages: list[AARRRStage] = []
    by_name: dict[str, AARRRStage] = {}

    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        if _is_table_sep(line):
            continue
        cells = _parse_table_row(line)
        if not cells:
            continue
        joined = "".join(cells)
        for name in _AARRR_NAMES:
            if name in joined:
                stage = by_name.setdefault(name, AARRRStage(name=name))
                if len(cells) >= 2 and cells[1] and cells[1] != name:
                    stage.health_metric = cells[1]
                if len(cells) >= 3:
                    stage.diagnostic_metrics = [c for c in cells[2:] if c]
                break

    for name in _AARRR_NAMES:
        if name in by_name:
            stages.append(by_name[name])
        else:
            stages.append(AARRRStage(name=name))

    if not any(s.health_metric for s in stages):
        chunk = text
        for name in _AARRR_NAMES:
            m = re.search(rf"{name}[:：]\s*([^\n]+)", chunk)
            if m:
                by_name[name] = AARRRStage(name=name, health_metric=m.group(1).strip())
        stages = [by_name.get(n, AARRRStage(name=n)) for n in _AARRR_NAMES]

    return stages


def _parse_warning_rows(text: str) -> list[WarningRow]:
    rows: list[WarningRow] = []
    for line in text.splitlines():
        if not line.strip().startswith("|") or _is_table_sep(line):
            continue
        cells = _parse_table_row(line)
        if not cells or cells[0] in ("指标", "阶段", "Metric"):
            continue
        row = WarningRow(metric=cells[0])
        for cell in cells[1:]:
            if "绿" in cell or "正常" in cell:
                row.green = cell
            elif "黄" in cell:
                row.yellow = cell
            elif "红" in cell:
                row.red = cell
        if row.green or row.yellow or row.red:
            rows.append(row)
    return rows


def parse_markdown_report(md_content: str, *, run_id: str = "", model: str = "") -> ExecutiveReport:
    title, sections = _split_sections(md_content)

    summary_text = _match_section(_SUMMARY_KEYS, sections) or sections.get("__intro__", "")
    north_text = _match_section(_NORTH_STAR_KEYS, sections)
    aarrr_text = _match_section(_AARRR_KEYS, sections)
    warning_text = _match_section(_WARNING_KEYS, sections)

    north_star = _first_paragraph(north_text) or ""
    m = re.search(r"\*\*(.+?)\*\*", north_text)
    if m:
        north_star = m.group(1)

    summary_bullets = _extract_bullets(summary_text) or _extract_bullets(md_content, limit=3)
    cards: list[MetricCard] = []
    if north_star:
        cards.append(MetricCard(label="北极星指标", value=north_star))
    if summary_bullets:
        cards.append(MetricCard(label="优先动作", value=summary_bullets[0][:40]))
    if len(summary_bullets) > 1:
        cards.append(MetricCard(label="核心关注", value=summary_bullets[1][:40]))

    used_keys = set()
    for keys in (_SUMMARY_KEYS, _NORTH_STAR_KEYS, _AARRR_KEYS, _WARNING_KEYS):
        for name in sections:
            if any(k in name for k in keys):
                used_keys.add(name)
    used_keys.add("__intro__")

    body_sections: list[ReportSection] = []
    for name, body in sections.items():
        if name in used_keys or not body.strip():
            continue
        body_sections.append(
            ReportSection(
                title=name,
                anchor=_slug(name),
                body_html=markdown_fragment_to_html(body),
            )
        )

    return ExecutiveReport(
        title=title,
        north_star=north_star,
        north_star_reason=_first_paragraph(north_text.split("\n", 1)[1] if "\n" in north_text else ""),
        summary_bullets=summary_bullets,
        summary_cards=cards[:3],
        aarrr_stages=_parse_aarrr_stages(aarrr_text or md_content),
        warning_rows=_parse_warning_rows(warning_text or md_content),
        sections=body_sections,
        run_id=run_id,
        model=model,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
