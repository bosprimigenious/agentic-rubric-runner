"""项目配置常量。"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = PROJECT_ROOT / "fonts"

# 对外链接（README / GitHub Pages / About 请与此保持一致）
GITHUB_PAGES_URL = "https://bosprimigenious.github.io/agentic-rubric-runner/"
STREAMLIT_APP_URL = "https://agentic-rubric-runner.streamlit.app/"
GITHUB_REPO_URL = "https://github.com/bosprimigenious/agentic-rubric-runner"

# PDF 渲染器：auto（先试 WeasyPrint，失败回退 ReportLab）| html | reportlab
PDF_RENDERER = os.getenv("PDF_RENDERER", "auto")

# Agent 循环上限（read_text + read_pdf + 生成报告 + write_pdf_report 通常需 4-6 轮）
MAX_AGENT_TURNS = 20

# Phase 2 评分重试次数
MAX_GRADING_ATTEMPTS = 3

# LLM 调用重试次数
MAX_LLM_RETRIES = 3

# Phase 2 prompt 中附件文本预算（字符数）；未超限时全文放入，超出时按页截取
PROMPT_ATTACHMENT_BUDGET = 100_000

# OpenAI SDK 请求超时（秒）
API_TIMEOUT_SECONDS = 120.0

# Phase 1 报告最短字符数警告阈值
MIN_REPORT_CONTENT_CHARS = 1500
