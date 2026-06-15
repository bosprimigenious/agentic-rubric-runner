"""Streamlit Cloud 入口 — 从 GitHub 仓库根目录启动。

Streamlit Cloud 克隆本仓库后执行 `streamlit run app.py`。
依赖见 requirements.txt；业务逻辑在 aarrr_agent/ 包内。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 触发 web_app 模块（所有 Streamlit 组件在模块顶层注册）
import aarrr_agent.web_app  # noqa: E402, F401
