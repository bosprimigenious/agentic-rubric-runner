"""项目配置常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = PROJECT_ROOT / "fonts"

# final_score 权重：与题目示例 (14/15, 18/24, 2/3 → 82.5) 一致
SCORE_WEIGHTS = {
    "hard": 50.0,
    "soft": 30.0,
    "optional": 20.0,
}

# Agent 循环上限
MAX_AGENT_TURNS = 15

# Phase 2 评分重试次数
MAX_GRADING_ATTEMPTS = 3

# 附件文本截断长度（控制 prompt 大小）
ATTACHMENT_TEXT_LIMIT = 8000
