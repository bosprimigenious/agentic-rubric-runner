"""Streamlit — 文档评审控制台。"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from xml.sax.saxutils import escape

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_CONSOLE_CSS = """
<style>
  footer {visibility: hidden;}
  .block-container {padding-top: 1.25rem; padding-bottom: 2rem; max-width: 1180px;}
  .console-header { margin-bottom: 0.25rem; }
  .console-title {
    font-size: 1.65rem; font-weight: 650; letter-spacing: -0.02em;
    color: #0f172a; margin: 0; line-height: 1.25;
  }
  .console-subtitle {
    font-size: 0.92rem; color: #64748b; margin: 0.35rem 0 0 0; line-height: 1.5;
  }
  .badge-public {
    display: inline-block; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.06em;
    color: #1e40af; background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 4px; padding: 0.35rem 0.65rem; text-align: right;
  }
  .section-label {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em;
    color: #64748b; margin: 0 0 0.5rem 0;
  }
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
  .stDownloadButton button { border-radius: 6px; font-weight: 500; }
</style>
"""


def _inject_styles(st) -> None:
    st.markdown(_CONSOLE_CSS, unsafe_allow_html=True)


def _section(st, title: str) -> None:
    st.markdown(f'<p class="section-label">{title}</p>', unsafe_allow_html=True)


def _render_header(st) -> None:
    left, right = st.columns([6, 1])
    with left:
        st.markdown(
            '<div class="console-header">'
            '<p class="console-title">文档评审控制台</p>'
            '<p class="console-subtitle">上传任务材料，运行受控评审流水线，导出可审计结果。</p>'
            "</div>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            '<div style="text-align:right;padding-top:0.35rem;">'
            '<span class="badge-public">公开演示</span>'
            "</div>",
            unsafe_allow_html=True,
        )


def _render_trace(st, trace_path: Path) -> None:
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        status = entry.get("status", "?")
        css = "trace-ok" if status == "ok" else "trace-fail"
        label = "通过" if status == "ok" else "失败"
        tool = entry.get("tool", "?")
        dur = entry.get("duration_ms", "?")
        st.markdown(
            f'<div class="trace-row"><span class="{css}">[{label}]</span> '
            f"{tool} &nbsp;·&nbsp; {dur} ms</div>",
            unsafe_allow_html=True,
        )


def _render_grading_result(st, result) -> None:
    bd = result.score_breakdown

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
                f'<span class="{css}">{mark}</span> **{h.id}** — {escape(h.reason)}',
                unsafe_allow_html=True,
            )

    with st.expander("软约束明细", expanded=False):
        for s in result.soft_constraints:
            st.markdown(f"**{s.id}** · 得分 {s.score}/4 — {escape(s.reason)}")

    with st.expander("可选项明细", expanded=False):
        for o in result.optional_constraints:
            mark = "通过" if o.score else "跳过"
            css = "result-pass" if o.score else ""
            st.markdown(
                f'<span class="{css}">{mark}</span> **{o.id}** — {escape(o.reason)}',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<div class="notice-bar"><strong>总评</strong><br>{escape(result.overall_comment)}</div>',
        unsafe_allow_html=True,
    )


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

    _section(st, "输入文件")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            query_file = st.file_uploader("任务描述", type=["txt"], help="query.txt")
        with c2:
            pdf_file = st.file_uploader("源文档 PDF", type=["pdf"], help="attachment.pdf")
        with c3:
            rubrics_file = st.file_uploader("评分标准", type=["json"], help="rubrics.json")

    if query_file and pdf_file and rubrics_file and not api_key:
        st.warning("运行前请先填写 API 密钥。")

    _section(st, "执行")
    with st.container(border=True):
        ready = all([query_file, pdf_file, rubrics_file, api_key])
        run_btn = st.button("运行评审", type="primary", disabled=not ready, use_container_width=False)

    if not run_btn:
        return

    from openai import OpenAI

    from aarrr_agent.errors import PipelineError
    from aarrr_agent.pipeline import resolve_output_paths, run_phase1_pipeline, run_phase2_pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        query_path = tmp / "query.txt"
        pdf_path = tmp / "attachment.pdf"
        rubrics_path = tmp / "rubrics.json"
        query_path.write_bytes(query_file.getvalue())
        pdf_path.write_bytes(pdf_file.getvalue())
        rubrics_path.write_bytes(rubrics_file.getvalue())

        client = OpenAI(api_key=api_key, base_url=base_url)
        paths = resolve_output_paths(tmp)
        t0 = time.perf_counter()
        phase1_ok = False
        grading_bytes: bytes | None = None

        _section(st, "Phase 1 — 报告生成")
        phase1_status = st.status("正在生成报告…", expanded=True)
        phase1_turns = 0

        try:
            with phase1_status:
                phase1_turns = run_phase1_pipeline(
                    query=query_path,
                    pdf=pdf_path,
                    client=client,
                    model=model,
                    paths=paths,
                )
                st.caption("工具调用日志")
                _render_trace(st, paths.trace_jsonl)
            phase1_status.update(label="报告生成完成", state="complete")
            phase1_ok = True
        except PipelineError as exc:
            phase1_status.update(label=f"{exc.code}: {exc.message}", state="error")
            st.stop()
        except Exception as exc:
            phase1_status.update(label=f"报告生成失败：{exc}", state="error")
            st.stop()

        _section(st, "Phase 2 — Rubric 评分")
        phase2_status = st.status("正在执行 Rubric 评分…", expanded=True)

        try:
            with phase2_status:
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
                _render_grading_result(st, result)
                grading_bytes = paths.grading_json.read_bytes()
            phase2_status.update(label="Rubric 评分完成", state="complete")
        except PipelineError as exc:
            phase2_status.update(label=f"{exc.code}: {exc.message}", state="error")
            if phase1_ok:
                st.warning("Phase 1 产物仍可于下方下载。")
        except Exception as exc:
            phase2_status.update(label=f"Rubric 评分失败：{exc}", state="error")
            if phase1_ok:
                st.warning("Phase 1 产物仍可于下方下载。")

        if phase1_ok:
            _section(st, "输出文件")
            with st.container(border=True):
                d1, d2, d3 = st.columns(3)
                with d1:
                    st.download_button(
                        "下载报告 PDF",
                        paths.phase1_pdf.read_bytes(),
                        "phase1_output.pdf",
                        "application/pdf",
                        key="dl_pdf",
                        use_container_width=True,
                    )
                with d2:
                    if grading_bytes:
                        st.download_button(
                            "下载评分 JSON",
                            grading_bytes,
                            "grading_result.json",
                            "application/json",
                            key="dl_grade",
                            use_container_width=True,
                        )
                    else:
                        st.button(
                            "下载评分 JSON",
                            disabled=True,
                            use_container_width=True,
                            help="Phase 2 成功完成后可下载。",
                        )
                with d3:
                    st.download_button(
                        "下载审计轨迹",
                        paths.trace_jsonl.read_bytes(),
                        "agent_trace.jsonl",
                        "text/plain",
                        key="dl_trace",
                        use_container_width=True,
                    )


if __name__ == "__main__":
    run_console()
