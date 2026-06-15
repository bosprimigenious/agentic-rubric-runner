"""项目配置常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = PROJECT_ROOT / "fonts"

# Agent 循环上限（read_text + read_pdf + 生成报告 + write_pdf_report 通常需 4-6 轮）
MAX_AGENT_TURNS = 20

# Phase 2 评分重试次数
MAX_GRADING_ATTEMPTS = 3

# Phase 2 prompt 中附件文本预算（字符数）；未超限时全文放入，超出时按页截取
PROMPT_ATTACHMENT_BUDGET = 100_000
