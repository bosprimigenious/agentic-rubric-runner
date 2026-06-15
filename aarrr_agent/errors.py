"""结构化流水线错误码。"""

from __future__ import annotations


class PipelineError(Exception):
    """带错误码的流水线异常，便于日志与界面展示。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")
