"""Streamlit 可视化界面。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import streamlit as st
from openai import OpenAI

from aarrr_agent.errors import PipelineError
from aarrr_agent.pipeline import resolve_output_paths, run_pipeline

st.set_page_config(
    page_title="Agentic Document Evaluator",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Agentic Document Evaluator")
st.caption("输入文档 + 评分标准 → Agent 生成报告 → 自动评分 → 输出结果")

with st.sidebar:
    st.header("⚙️ 配置")
    api_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=os.getenv("DEEPSEEK_API_KEY", ""),
    )
    base_url = st.text_input("API Base URL", value="https://api.deepseek.com")
    model = st.selectbox("模型", ["deepseek-chat", "deepseek-reasoner"])
    st.divider()
    st.markdown("**评分公式**")
    st.code(
        "final = (hard+soft+opt) / (H_max+S_max+O_max) × 100\n"
        "分母从 rubrics.json 动态计算",
        language="text",
    )

col1, col2, col3 = st.columns(3)
with col1:
    query_file = st.file_uploader("📄 Query 文件", type=["txt"])
with col2:
    pdf_file = st.file_uploader("📎 附件 PDF", type=["pdf"])
with col3:
    rubrics_file = st.file_uploader("📊 Rubrics JSON", type=["json"])

ready = all([query_file, pdf_file, rubrics_file, api_key])
run_btn = st.button("▶ Run Pipeline", type="primary", disabled=not ready)

if run_btn:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        query_path = tmp / "query.txt"
        pdf_path = tmp / "attachment.pdf"
        rubrics_path = tmp / "rubrics.json"
        query_path.write_bytes(query_file.getvalue())
        pdf_path.write_bytes(pdf_file.getvalue())
        rubrics_path.write_bytes(rubrics_file.getvalue())

        phase1_pdf = tmp / "phase1_output.pdf"
        phase1_md = tmp / "phase1_output.md"
        grading_json = tmp / "grading_result.json"
        trace_jsonl = tmp / "agent_trace.jsonl"

        client = OpenAI(api_key=api_key, base_url=base_url)
        paths = resolve_output_paths(tmp)

        st.divider()
        st.subheader("Phase 1 — Agent 生成报告")
        phase1_status = st.status("Agent 运行中...", expanded=True)

        try:
            with phase1_status:
                result = run_pipeline(
                    query=query_path,
                    pdf=pdf_path,
                    rubrics=rubrics_path,
                    client=client,
                    model=model,
                    paths=paths,
                    skip_phase2=False,
                )
                trace_jsonl = paths.trace_jsonl
                phase1_pdf = paths.phase1_pdf
                grading_json = paths.grading_json
                for line in trace_jsonl.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    dur = entry.get("duration_ms", "?")
                    icon = "✅" if entry.get("status") == "ok" else "❌"
                    st.write(f"{icon} {entry.get('tool')}  {dur}ms")

            phase1_status.update(label="Phase 1 完成", state="complete")

            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "⬇ 下载 Phase 1 PDF",
                    phase1_pdf.read_bytes(),
                    "phase1_output.pdf",
                    "application/pdf",
                )
            with c2:
                st.download_button(
                    "⬇ 下载 Agent Trace",
                    trace_jsonl.read_bytes(),
                    "agent_trace.jsonl",
                    "text/plain",
                )
        except PipelineError as exc:
            phase1_status.update(label=str(exc), state="error")
            st.stop()
        except Exception as exc:
            phase1_status.update(label=f"Phase 1 失败: {exc}", state="error")
            st.stop()

        st.subheader("Phase 2 — Rubric 评分")
        phase2_status = st.status("评分完成", expanded=True)

        try:
            phase2_status.update(label="Phase 2 完成", state="complete")
            assert result is not None

            st.divider()
            st.subheader("📊 评分结果")
            bd = result.score_breakdown

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Final Score", f"{bd.final_score} / 100")
            m2.metric("Hard", f"{bd.hard_score} / {bd.hard_max}")
            m3.metric("Soft", f"{bd.soft_score} / {bd.soft_max}")
            m4.metric("Optional", f"{bd.optional_score} / {bd.optional_max}")

            if bd.hard_max:
                st.progress(bd.hard_score / bd.hard_max, text=f"Hard {bd.hard_score}/{bd.hard_max}")
            if bd.soft_max:
                st.progress(bd.soft_score / bd.soft_max, text=f"Soft {bd.soft_score}/{bd.soft_max}")
            if bd.optional_max:
                st.progress(
                    bd.optional_score / bd.optional_max,
                    text=f"Optional {bd.optional_score}/{bd.optional_max}",
                )

            with st.expander("Hard Constraints 逐条"):
                for h in result.hard_constraints:
                    st.markdown(f"{'✅' if h.score else '❌'} **{h.id}** — {h.reason}")

            with st.expander("Soft Constraints 逐条"):
                for s in result.soft_constraints:
                    st.markdown(f"**{s.id}** `{s.score}/4` — {s.reason}")

            with st.expander("Optional Constraints 逐条"):
                for o in result.optional_constraints:
                    st.markdown(f"{'✅' if o.score else '⬜'} **{o.id}** — {o.reason}")

            st.info(result.overall_comment)

            st.download_button(
                "⬇ 下载 grading_result.json",
                grading_json.read_bytes(),
                "grading_result.json",
                "application/json",
            )

        except PipelineError as exc:
            phase2_status.update(label=str(exc), state="error")
        except Exception as exc:
            phase2_status.update(label=f"Phase 2 失败: {exc}", state="error")
