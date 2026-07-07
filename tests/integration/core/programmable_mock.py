"""可编程 LLM Mock + Response DSL"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Callable


_counter = [0]


class Response:
    """LLM 响应构造器"""

    def __init__(
        self,
        content: str = "",
        tool_calls: list | None = None,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls if tool_calls is not None else []
        self.error = error
        self.delay = delay

    @classmethod
    def content(cls, text: str, *, delay: float = 0.0) -> "Response":
        return cls(content=text, delay=delay)

    @classmethod
    def tool_call(
        cls, name: str, arguments: dict, *, id: str | None = None
    ) -> "Response":
        if id is None:
            _counter[0] += 1
            id = f"manual_{_counter[0] - 1}"
        return cls(
            tool_calls=[
                {
                    "id": id,
                    "name": name,
                    "arguments": arguments,
                }
            ]
        )

    @classmethod
    def error(cls, exc: Exception) -> "Response":
        return cls(error=exc)