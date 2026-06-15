"""LLM 调用封装：超时与重试。"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from aarrr_agent.config import API_TIMEOUT_SECONDS, MAX_LLM_RETRIES
from aarrr_agent.errors import PipelineError


def call_chat_completion(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    temperature: float = 0.2,
    retries: int = MAX_LLM_RETRIES,
) -> Any:
    """统一 Chat Completions 调用，带超时与重试。"""
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "timeout": API_TIMEOUT_SECONDS,
            }
            if tools is not None:
                kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice

            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            last_error = exc
            print(f"[LLM] 第 {attempt}/{retries} 次调用失败: {exc}")

    raise PipelineError(
        "E001",
        f"LLM 调用失败，已重试 {retries} 次: {last_error}",
    )
