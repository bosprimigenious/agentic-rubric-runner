"""Streamlit Cloud 入口 — 从 GitHub 仓库根目录启动。"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

st.set_page_config(
    page_title="文档评审控制台",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    from aarrr_agent.web_app import run_console

    run_console(configure_page=False)
except Exception:
    st.error("应用启动失败，请查看 Streamlit Cloud 日志。")
    st.code(traceback.format_exc())
