"""Streamlit — Document Evaluation Console。

包内 Web UI 实现，供 `agentic-rubric ui`（pip 安装）与根目录 `app.py`（Streamlit Cloud）共用。
调用链：run_phase1_pipeline / run_phase2_pipeline → agent / grader。
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from xml.sax.saxutils import escape

import streamlit as st
from openai import OpenAI

from aarrr_agent.errors import PipelineError
from aarrr_agent.pipeline import resolve_output_paths, run_phase1_pipeline, run_phase2_pipeline

st.set_page_config(
    page_title="Document Evaluation Console",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CONSOLE_CSS = """
<style>
  #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1180px; }
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
    letter-spacing: 0.06em; text-transform: uppercase;
    color: #1e40af; background: #eff6ff; border: 1px solid #bfdbfe;
    border-radius: 4px; padding: 0.35rem 0.65rem; text-align: right;
  }
  .section-label {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: #94a3b8; margin: 0 0 0.5rem 0;
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


def _inject_styles() -> None:
    st.markdown(_CONSOLE_CSS, unsafe_allow_html=True)


def _section(title: str) -> None:
    st.markdown(f'<p class="section-label">{title}</p>', unsafe_allow_html=True)


def _render_header() -> None:
    left, right = st.columns([6, 1])
    with left:
        st.markdown(
            '<div class="console-header">'
            '<p class="console-title">Document Evaluation Console</p>'
            '<p class="console-subtitle">Upload source materials, run a controlled review pipeline, '
            "and export auditable results.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            '<div style="text-align:right;padding-top:0.35rem;">'
            '<span class="badge-public">Public Demo</span>'
            "</div>",
            unsafe_allow_html=True,
        )


def _render_trace(trace_path: Path) -> None:
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        status = entry.get("status", "?")
        css = "trace-ok" if status == "ok" else "trace-fail"
        label = "PASS" if status == "ok" else "FAIL"
        tool = entry.get("tool", "?")
        dur = entry.get("duration_ms", "?")
        st.markdown(
            f'<div class="trace-row"><span class="{css}">[{label}]</span> '
            f"{tool} &nbsp;·&nbsp; {dur} ms</div>",
            unsafe_allow_html=True,
        )


def _render_grading_result(result) -> None:
    bd = result.score_breakdown

    _section("Results")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Final Score", f"{bd.final_score:.2f}")
    m2.metric("Hard Constraints", f"{bd.hard_score} / {bd.hard_max}")
    m3.metric("Soft Constraints", f"{bd.soft_score} / {bd.soft_max}")
    m4.metric("Optional Checks", f"{bd.optional_score} / {bd.optional_max}")

    c1, c2, c3 = st.columns(3)
    with c1:
        if bd.hard_max:
            st.progress(bd.hard_score / bd.hard_max, text="Hard")
    with c2:
        if bd.soft_max:
            st.progress(bd.soft_score / bd.soft_max, text="Soft")
    with c3:
        if bd.optional_max:
            st.progress(bd.optional_score / bd.optional_max, text="Optional")

    with st.expander("Hard Constraints — detail", expanded=False):
        for h in result.hard_constraints:
            mark = "PASS" if h.score else "FAIL"
            css = "result-pass" if h.score else "result-fail"
            st.markdown(
                f'<span class="{css}">{mark}</span> **{h.id}** — {escape(h.reason)}',
                unsafe_allow_html=True,
            )

    with st.expander("Soft Constraints — detail", expanded=False):
        for s in result.soft_constraints:
            st.markdown(f"**{s.id}** · score {s.score}/4 — {escape(s.reason)}")

    with st.expander("Optional Checks — detail", expanded=False):
        for o in result.optional_constraints:
            mark = "PASS" if o.score else "SKIP"
            css = "result-pass" if o.score else ""
            st.markdown(
                f'<span class="{css}">{mark}</span> **{o.id}** — {escape(o.reason)}',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<div class="notice-bar"><strong>Summary</strong><br>{escape(result.overall_comment)}</div>',
        unsafe_allow_html=True,
    )


_inject_styles()
_render_header()

st.markdown(
    '<div class="notice-bar">'
    "Credentials are required for each session. API keys are not stored, logged, or written to disk."
    "</div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    _section("Configuration")
    api_key = st.text_input(
        "Provider API Key",
        type="password",
        placeholder="Enter your provider API key",
        help="Used only for this session. Not persisted.",
    )
    base_url = st.text_input("API Base URL", value="https://api.deepseek.com")
    model = st.selectbox("Model", ["deepseek-chat", "deepseek-reasoner"], index=0)

    with st.expander("Advanced", expanded=False):
        st.caption(
            "Scoring weights are derived from rubric.json at runtime. "
            "Hard / soft / optional maxima are computed dynamically."
        )

_section("Input Files")
with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        query_file = st.file_uploader("Task Query", type=["txt"], help="query.txt")
    with c2:
        pdf_file = st.file_uploader("Source PDF", type=["pdf"], help="attachment.pdf")
    with c3:
        rubrics_file = st.file_uploader("Rubric JSON", type=["json"], help="rubrics.json")

if query_file and pdf_file and rubrics_file and not api_key:
    st.warning("Provider API Key is required before execution.")

_section("Execution")
with st.container(border=True):
    ready = all([query_file, pdf_file, rubrics_file, api_key])
    run_btn = st.button("Run Evaluation", type="primary", disabled=not ready, use_container_width=False)

if run_btn:
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

        _section("Phase 1 — Report Generation")
        phase1_status = st.status("Running report generation…", expanded=True)
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
                st.caption("Tool execution log")
                _render_trace(paths.trace_jsonl)
            phase1_status.update(label="Report generation complete", state="complete")
            phase1_ok = True
        except PipelineError as exc:
            phase1_status.update(label=f"{exc.code}: {exc.message}", state="error")
            st.stop()
        except Exception as exc:
            phase1_status.update(label=f"Report generation failed: {exc}", state="error")
            st.stop()

        _section("Phase 2 — Rubric Evaluation")
        phase2_status = st.status("Running rubric evaluation…", expanded=True)

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
                _render_grading_result(result)
                grading_bytes = paths.grading_json.read_bytes()
            phase2_status.update(label="Rubric evaluation complete", state="complete")
        except PipelineError as exc:
            phase2_status.update(label=f"{exc.code}: {exc.message}", state="error")
            if phase1_ok:
                st.warning("Phase 1 outputs remain available for download below.")
        except Exception as exc:
            phase2_status.update(label=f"Rubric evaluation failed: {exc}", state="error")
            if phase1_ok:
                st.warning("Phase 1 outputs remain available for download below.")

        if phase1_ok:
            _section("Output Files")
            with st.container(border=True):
                d1, d2, d3 = st.columns(3)
                with d1:
                    st.download_button(
                        "Download Report PDF",
                        paths.phase1_pdf.read_bytes(),
                        "phase1_output.pdf",
                        "application/pdf",
                        key="dl_pdf",
                        use_container_width=True,
                    )
                with d2:
                    if grading_bytes:
                        st.download_button(
                            "Download Grading JSON",
                            grading_bytes,
                            "grading_result.json",
                            "application/json",
                            key="dl_grade",
                            use_container_width=True,
                        )
                    else:
                        st.button(
                            "Download Grading JSON",
                            disabled=True,
                            use_container_width=True,
                            help="Available after Phase 2 completes successfully.",
                        )
                with d3:
                    st.download_button(
                        "Download Trace Log",
                        paths.trace_jsonl.read_bytes(),
                        "agent_trace.jsonl",
                        "text/plain",
                        key="dl_trace",
                        use_container_width=True,
                    )
