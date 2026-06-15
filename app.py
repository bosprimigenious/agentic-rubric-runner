"""Streamlit Cloud 入口 — 从 GitHub 仓库根目录启动。

Streamlit Cloud 克隆本仓库后执行 `streamlit run app.py`。
依赖见 requirements.txt（`.[web]` 会安装 aarrr_agent 包）。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import aarrr_agent.web_app  # noqa: E402, F401
except Exception:
    import streamlit as st

    st.set_page_config(page_title="Document Evaluation Console", layout="wide")
    st.error("应用启动失败，请查看 Streamlit Cloud 日志。")
    st.code(traceback.format_exc())
