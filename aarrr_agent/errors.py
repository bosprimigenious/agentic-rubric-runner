"""结构化流水线错误码。

E001 — LLM/API 调用失败或缺少 API Key
E002 — PDF 抽取无文本
E003 — Agent 未调用必要工具
E004 — 报告内容不完整（警告，非致命）
E005 — Grading JSON 校验失败
E006 — 中文字体未找到
E007 — 附件与任务领域不匹配（离题 PDF）
"""

from __future__ import annotations


class PipelineError(Exception):
    """带错误码的流水线异常，便于日志与界面展示。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")
