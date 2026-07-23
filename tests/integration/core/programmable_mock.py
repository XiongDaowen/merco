"""可编程 LLM Mock + Response DSL"""
from __future__ import annotations

import asyncio
from typing import Callable

from merco.core.llm.base import ModelProvider


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


class ProgrammableModelProvider(ModelProvider):
    """可编程 LLM mock，支持预设队列、动态序列、条件分支、异常注入"""

    name = "mock"

    def __init__(self):
        self._queue: list[Response] = []
        self._sequence_fn: Callable[[int], Response] | None = None
        self._conditions: list[tuple[Callable, Response]] = []
        self.calls: list[dict] = []

    def expect(self, responses: list[Response]) -> "ProgrammableModelProvider":
        self._queue = list(responses)
        self._sequence_fn = None
        return self

    def expect_sequence(
        self, fn: Callable[[int], Response]
    ) -> "ProgrammableModelProvider":
        self._sequence_fn = fn
        self._queue = []
        return self

    def when(
        self, condition: Callable, response: Response
    ) -> "ProgrammableModelProvider":
        self._conditions.append((condition, response))
        return self

    def _select(self, messages: list[dict]) -> Response:
        for cond, resp in self._conditions:
            try:
                if cond(messages):
                    return resp
            except Exception:
                continue
        if self._sequence_fn is not None:
            idx = len(self.calls)
            return self._sequence_fn(idx)
        if self._queue:
            return self._queue.pop(0)
        raise RuntimeError("ProgrammableModelProvider: no more responses queued")

    async def chat(self, messages: list[dict], **kwargs) -> dict:
        response = self._select(messages)
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if response.delay:
            await asyncio.sleep(response.delay)
        if response.error is not None:
            raise response.error
        if response.tool_calls:
            return {
                "content": response.content,
                "tool_calls": response.tool_calls,
            }
        return {"content": response.content, "tool_calls": []}

    async def chat_stream(self, messages: list[dict], **kwargs):
        resp = await self.chat(messages, **kwargs)
        yield resp
