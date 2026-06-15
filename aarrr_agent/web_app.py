"""Streamlit — 文档评审控制台。"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aarrr_agent.errors import PipelineError

_SESSION_KEY = "run_outputs"

_CONSOLE_CSS = """
<style>
  footer {visibility: hidden;}
  .block-container {padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1180px;}
  .notice-bar {
    font-size: 0.82rem; color: #475569; background: #f8fafc;
    border: 1px solid #e2e8f0; border-radius: 6px;
    padding: 0.65rem 0.9rem; margin-bottom: 1.25rem;
  }
  div[data-testid="stSidebar"] {
    background-color: #f8fafc; border-right: 1px solid #e2e8f0;
  }
  div[data-testid="stMetric"] {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 6px; padding: 0.65rem 0.75rem;
  }
  div[data-testid="stMetric"] label { font-size: 0.75rem; color: #64748b; }
  .trace-row {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.8rem; color: #334155; padding: 0.2rem 0;
  }
  .trace-ok { color: #15803d; }
  .trace-fail { color: #b91c1c; }
  .result-pass { color: #15803d; font-weight: 600; }
  .result-fail { color: #b91c1c; font-weight: 600; }
  .result-warn { color: #b45309; font-weight: 600; }
  .file-ok {
    font-size: 0.88rem; color: #334155; background: #f8fafc;
    border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.55rem 0.75rem;
  }
  .file-empty { font-size: 0.88rem; color: #94a3b8; }
  .summary-card {
    font-size: 0.9rem; color: #334155; background: #eff6ff;
    border: 1px solid #bfdbfe; border-left: 4px solid #1e40af;
    border-radius: 8px; padding: 0.9rem 1rem; margin: 0.75rem 0 1rem 0;
  }
</style>
"""


def _inject_styles(st) -> None:
    st.markdown(_CONSOLE_CSS, unsafe_allow_html=True)


def _section(st, title: str) -> None:
    st.markdown(f"**{title}**")


def _init_session(st) -> None:
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = None


def _clear_session(st) -> None:
    st.session_state[_SESSION_KEY] = None


def _app_version() -> str:
    try:
        from importlib.metadata import version

        return version("agentic-rubric-runner")
    except Exception:
        return "0.5.0"


def _render_header(st) -> None:
    st.title("文档评审控制台")
    st.caption(
        f"上传任务材料，运行受控评审流水线，导出可审计结果。（管线 v{_app_version()}）"
    )


def _parse_trace_bytes(trace_bytes: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in trace_bytes.decode("utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _render_trace_entries(st, entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        status = entry.get("status", "?")
        css = "trace-ok" if status == "ok" else "trace-fail"
        label = "通过" if status == "ok" else "失败"
        tool = entry.get("tool", "?")
        state = entry.get("phase1_state", "")
        dur = entry.get("duration_ms", "?")
        state_tag = f" &nbsp;·&nbsp; {state}" if state else ""
        st.markdown(
            f'<div class="trace-row"><span class="{css}">[{label}]</span> '
            f"{tool}{state_tag} &nbsp;·&nbsp; {dur} ms</div>",
            unsafe_allow_html=True,
        )


def _file_status_badge(name: str | None, size_bytes: int = 0) -> str:
    if name:
        return (
            f'<div class="file-ok">已选择 <strong>{escape(name)}</strong>'
            f" · {size_bytes / 1024:.1f} KB</div>"
        )
    return '<div class="file-empty">未选择文件</div>'


def _constraint_detail(item, score_label: str) -> str:
    parts = [
        f'<span id="{escape(item.id)}"></span>',
        f"**{item.id}** · {score_label}",
    ]
    if getattr(item, "evidence", None):
        ev = "；".join(item.evidence[:3])
        parts.append(f"<br>证据：{escape(ev)}")
    if getattr(item, "missing", None):
        miss = "；".join(item.missing[:3])
        parts.append(f'<br><span class="result-fail">缺口：{escape(miss)}</span>')
    parts.append(f"<br>{escape(item.reason)}")
    return "".join(parts)


def _render_grading_result(st, result, summary: dict[str, Any] | None = None) -> None:
    bd = result.score_breakdown
    if summary is None:
        from aarrr_agent.grading_report import build_executive_summary

        summary = build_executive_summary(result, "fixtures/rubrics.json")
    verdict_css = {
        "通过": "result-pass",
        "待改进": "result-warn",
        "未通过": "result-fail",
    }.get(summary["verdict"], "result-warn")

    st.markdown(
        f'<div class="summary-card">'
        f'<strong>管理层摘要</strong><br>'
        f'本次评审：<span class="{verdict_css}">{escape(summary["verdict"])}</span><br>'
        f'最终得分：<strong>{bd.final_score:.2f}</strong> / 100<br>'
        f'主要缺口：{escape(summary["gaps_text"])}<br>'
        f'建议动作：{escape(summary["actions_text"])}'
        f"</div>",
        unsafe_allow_html=True,
    )

    _section(st, "评分结果")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("最终得分", f"{bd.final_score:.2f}")
    m2.metric("硬约束", f"{bd.hard_score} / {bd.hard_max}")
    m3.metric("软约束", f"{bd.soft_score} / {bd.soft_max}")
    m4.metric("可选项", f"{bd.optional_score} / {bd.optional_max}")

    c1, c2, c3 = st.columns(3)
    with c1:
        if bd.hard_max:
            st.progress(bd.hard_score / bd.hard_max, text="硬约束")
    with c2:
        if bd.soft_max:
            st.progress(bd.soft_score / bd.soft_max, text="软约束")
    with c3:
        if bd.optional_max:
            st.progress(bd.optional_score / bd.optional_max, text="可选")

    with st.expander("硬约束明细", expanded=False):
        for h in result.hard_constraints:
            mark = "通过" if h.score else "未通过"
            css = "result-pass" if h.score else "result-fail"
            st.markdown(
                f'<span class="{css}">{mark}</span> {_constraint_detail(h, "硬约束")}',
                unsafe_allow_html=True,
            )

    with st.expander("软约束明细", expanded=False):
        for s in result.soft_constraints:
            st.markdown(_constraint_detail(s, f"得分 {s.score}/4"), unsafe_allow_html=True)

    with st.expander("可选项明细", expanded=False):
        for o in result.optional_constraints:
            mark = "已满足" if o.score else "未满足"
            css = "result-pass" if o.score else "result-fail"
            st.markdown(
                f'<span class="{css}">{mark}</span> {_constraint_detail(o, "可选项")}',
                unsafe_allow_html=True,
            )

    if summary and summary.get("gaps"):
        _section(st, "缺口导航")
        links = " · ".join(
            f'<a href="#{escape(g["id"])}">{escape(g["id"])}</a>' for g in summary["gaps"][:6]
        )
        st.markdown(f'<div class="notice-bar">{links}</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="notice-bar"><strong>总评</strong><br>{escape(result.overall_comment)}</div>',
        unsafe_allow_html=True,
    )


def _render_cached_results(st, outputs: dict[str, Any]) -> None:
    from aarrr_agent.schemas import GradingResult

    if outputs.get("attachment_hint"):
        st.info(outputs["attachment_hint"])

    _section(st, "Phase 1 — 报告生成")
    st.success(outputs.get("phase1_message", "报告生成完成"))
    st.caption("工具调用日志")
    _render_trace_entries(st, outputs["trace_entries"])

    if outputs.get("phase2_ok") and outputs.get("grading_result"):
        _section(st, "Phase 2 — Rubric 评分")
        st.success(outputs.get("phase2_message", "Rubric 评分完成"))
        result = GradingResult.model_validate(outputs["grading_result"])
        _render_grading_result(st, result, outputs.get("executive_summary"))
    elif outputs.get("phase2_error"):
        _section(st, "Phase 2 — Rubric 评分")
        st.error(outputs["phase2_error"])

    if outputs.get("phase1_ok"):
        _section(st, "输出文件")
        with st.container(border=True):
            d1, d2, d3, d4, d5 = st.columns(5)
            with d1:
                st.download_button(
                    "下载报告 PDF",
                    outputs["pdf_bytes"],
                    "phase1_output.pdf",
                    "application/pdf",
                    key="dl_pdf_cached",
                    use_container_width=True,
                )
            with d2:
                if outputs.get("html_bytes"):
                    st.download_button(
                        "下载报告 HTML",
                        outputs["html_bytes"],
                        "phase1_output.html",
                        "text/html",
                        key="dl_html_cached",
                        use_container_width=True,
                    )
                else:
                    st.button(
                        "下载报告 HTML",
                        disabled=True,
                        use_container_width=True,
                        key="dl_html_disabled",
                    )
            with d3:
                if outputs.get("grading_report_md_bytes"):
                    st.download_button(
                        "下载评审报告 MD",
                        outputs["grading_report_md_bytes"],
                        "grading_report.md",
                        "text/markdown",
                        key="dl_grade_md_cached",
                        use_container_width=True,
                    )
                else:
                    st.button("下载评审报告 MD", disabled=True, use_container_width=True, key="dl_grade_md_disabled")
                if outputs.get("grading_report_html_bytes"):
                    st.download_button(
                        "下载评审报告 HTML",
                        outputs["grading_report_html_bytes"],
                        "grading_report.html",
                        "text/html",
                        key="dl_grade_html_cached",
                        use_container_width=True,
                    )
            with d4:
                if outputs.get("grading_bytes"):
                    st.download_button(
                        "下载评分 JSON",
                        outputs["grading_bytes"],
                        "grading_result.json",
                        "application/json",
                        key="dl_grade_cached",
                        use_container_width=True,
                    )
                else:
                    st.button(
                        "下载评分 JSON",
                        disabled=True,
                        use_container_width=True,
                        help="Phase 2 成功完成后可下载。",
                        key="dl_grade_disabled",
                    )
            with d5:
                st.download_button(
                    "下载审计轨迹",
                    outputs["trace_bytes"],
                    "agent_trace.jsonl",
                    "text/plain",
                    key="dl_trace_cached",
                    use_container_width=True,
                )


def _execute_pipeline(
    *,
    query_bytes: bytes,
    pdf_bytes: bytes,
    rubrics_bytes: bytes,
    api_key: str,
    base_url: str,
    model: str,
    pdf_filename: str = "attachment.pdf",
) -> dict[str, Any]:
    from openai import OpenAI

    from aarrr_agent.pipeline import resolve_output_paths, run_phase1_pipeline, run_phase2_pipeline

    outputs: dict[str, Any] = {
        "phase1_ok": False,
        "phase2_ok": False,
        "pdf_bytes": b"",
        "html_bytes": b"",
        "grading_bytes": None,
        "grading_report_md_bytes": None,
        "grading_report_html_bytes": None,
        "executive_summary": None,
        "trace_bytes": b"",
        "trace_entries": [],
        "grading_result": None,
        "phase1_message": "",
        "phase2_message": "",
        "phase2_error": None,
        "attachment_hint": None,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        query_path = tmp / "query.txt"
        pdf_path = tmp / "attachment.pdf"
        rubrics_path = tmp / "rubrics.json"
        query_path.write_bytes(query_bytes)
        pdf_path.write_bytes(pdf_bytes)
        rubrics_path.write_bytes(rubrics_bytes)

        attachment_hint: str | None = None
        try:
            from aarrr_agent.attachment_relevance import format_e007_user_message, preflight_attachment_pdf

            assessment = preflight_attachment_pdf(str(pdf_path))
            if not assessment["relevant"]:
                attachment_hint = format_e007_user_message(assessment, filename=pdf_filename)
        except Exception:
            attachment_hint = None

        client = OpenAI(api_key=api_key, base_url=base_url)
        paths = resolve_output_paths(tmp)
        t0 = time.perf_counter()
        phase1_turns = 0

        try:
            phase1_turns = run_phase1_pipeline(
                query=query_path,
                pdf=pdf_path,
                client=client,
                model=model,
                paths=paths,
            )
            trace_bytes = paths.trace_jsonl.read_bytes()
            outputs["phase1_ok"] = True
            outputs["phase1_message"] = "报告生成完成"
            outputs["pdf_bytes"] = paths.phase1_pdf.read_bytes()
            if paths.phase1_html.exists():
                outputs["html_bytes"] = paths.phase1_html.read_bytes()
            outputs["trace_bytes"] = trace_bytes
            outputs["trace_entries"] = _parse_trace_bytes(trace_bytes)
        except PipelineError:
            raise

        try:
            result = run_phase2_pipeline(
                query=query_path,
                pdf=pdf_path,
                rubrics=rubrics_path,
                client=client,
                model=model,
                paths=paths,
                phase1_turns=phase1_turns,
                duration_seconds=time.perf_counter() - t0,
            )
            from aarrr_agent.grading_report import build_executive_summary

            outputs["phase2_ok"] = True
            outputs["phase2_message"] = "Rubric 评分完成"
            outputs["grading_bytes"] = paths.grading_json.read_bytes()
            outputs["grading_result"] = result.model_dump()
            outputs["executive_summary"] = build_executive_summary(result, str(rubrics_path))
            if paths.grading_report_md.exists():
                outputs["grading_report_md_bytes"] = paths.grading_report_md.read_bytes()
            if paths.grading_report_html.exists():
                outputs["grading_report_html_bytes"] = paths.grading_report_html.read_bytes()
        except PipelineError as exc:
            outputs["phase2_error"] = f"{exc.code}: {exc.message}"
        except Exception as exc:
            outputs["phase2_error"] = f"Rubric 评分失败：{exc}"

        outputs["attachment_hint"] = attachment_hint

    return outputs


def run_console(*, configure_page: bool = True) -> None:
    """渲染 Streamlit 控制台。"""
    import streamlit as st

    if configure_page:
        st.set_page_config(
            page_title="文档评审控制台",
            layout="wide",
            initial_sidebar_state="expanded",
            menu_items={
                "Get help": "https://github.com/bosprimigenious/agentic-rubric-runner",
                "Report a bug": "https://github.com/bosprimigenious/agentic-rubric-runner/issues",
                "About": "文档评审控制台 — 可审计的 Rubric 流水线。",
            },
        )

    _init_session(st)
    _inject_styles(st)
    _render_header(st)

    st.markdown(
        '<div class="notice-bar">'
        "每次会话需自备 API 密钥。密钥不会存储、记录或写入磁盘。"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        _section(st, "配置")
        api_key = st.text_input(
            "API 密钥",
            type="password",
            placeholder="请输入 DeepSeek API 密钥",
            help="仅用于本次会话，不会持久化。",
        )
        base_url = st.text_input("API 地址", value="https://api.deepseek.com")
        model = st.selectbox("模型", ["deepseek-chat", "deepseek-reasoner"], index=0)

        with st.expander("高级选项", expanded=False):
            st.caption(
                "评分权重由 rubrics.json 在运行时动态计算，"
                "硬约束 / 软约束 / 可选项满分随 Rubric 条目数变化。"
            )

        if st.session_state[_SESSION_KEY]:
            if st.button("清除本次结果", use_container_width=True):
                _clear_session(st)
                st.rerun()

    _section(st, "输入文件")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            query_file = st.file_uploader("任务描述", type=["txt"], help="query.txt")
            st.markdown(
                _file_status_badge(
                    query_file.name if query_file else None,
                    len(query_file.getvalue()) if query_file else 0,
                ),
                unsafe_allow_html=True,
            )
        with c2:
            pdf_file = st.file_uploader(
                "源文档 PDF",
                type=["pdf"],
                help="可上传任意 PDF；若与 query 领域不一致，Phase 2 将自动压低得分。",
            )
            st.markdown(
                _file_status_badge(
                    pdf_file.name if pdf_file else None,
                    len(pdf_file.getvalue()) if pdf_file else 0,
                ),
                unsafe_allow_html=True,
            )
        with c3:
            rubrics_file = st.file_uploader("评分标准", type=["json"], help="rubrics.json")
            st.markdown(
                _file_status_badge(
                    rubrics_file.name if rubrics_file else None,
                    len(rubrics_file.getvalue()) if rubrics_file else 0,
                ),
                unsafe_allow_html=True,
            )

    if query_file and pdf_file and rubrics_file and not api_key:
        st.warning("运行前请先填写 API 密钥。")

    _section(st, "执行")
    with st.container(border=True):
        ready = all([query_file, pdf_file, rubrics_file, api_key])
        run_btn = st.button("运行评审", type="primary", disabled=not ready, use_container_width=True)

    if run_btn and ready:
        with st.status("正在运行评审流水线（Phase 1 → Phase 2）…", expanded=True) as status:
            try:
                st.session_state[_SESSION_KEY] = _execute_pipeline(
                    query_bytes=query_file.getvalue(),
                    pdf_bytes=pdf_file.getvalue(),
                    rubrics_bytes=rubrics_file.getvalue(),
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    pdf_filename=pdf_file.name or "attachment.pdf",
                )
                status.update(label="评审完成", state="complete")
            except PipelineError as exc:
                status.update(label=f"运行失败：{exc}", state="error")
                st.error(str(exc))
                st.session_state[_SESSION_KEY] = None
                st.stop()
            except Exception as exc:
                status.update(label=f"运行失败：{exc}", state="error")
                st.session_state[_SESSION_KEY] = None
                st.stop()
        st.rerun()

    if st.session_state[_SESSION_KEY]:
        st.divider()
        st.caption("以下为最近一次评审结果（下载文件不会清除缓存，无需重新运行）。")
        _render_cached_results(st, st.session_state[_SESSION_KEY])


if __name__ == "__main__":
    run_console()
