"""ResponseProvider - streaming/non-streaming assembly + rendering.

Extracted from agent.py. Uses agent.config (StreamingConfig), agent.context,
agent.session, agent.provider.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from rich.live import Live
from rich.panel import Panel
from rich.console import Group
from rich.markdown import Markdown

from merco.core.llm.error_ui import classify_error, build_error_panel

if TYPE_CHECKING:
    from merco.core.agent import Agent

logger = logging.getLogger("merco.agent")


def _build_reasoning_panel(text: str) -> Panel:
    return Panel(f"[dim]{text.rstrip()}[/dim]", border_style="dim",
                 title="🧠 思考中…", title_align="left", padding=(0, 1))


class ResponseProvider(ABC):
    """响应策略基类 — 工厂模式，Agent 不感知流/非流"""

    @abstractmethod
    async def get_response(self, agent: Agent, messages: list,
                           tools: list | None) -> dict:
        ...

class NonStreamingProvider(ResponseProvider):
    """非流式：一次 chat 返回完整响应"""

    async def get_response(self, agent: Agent, messages: list,
                           tools: list | None) -> dict:
        response = await agent.provider.chat(
            messages, tools=tools, tool_choice="auto")
        reasoning = response.get("reasoning", "")
        if reasoning and reasoning.strip():
            agent._render_reasoning(reasoning)
        return response

class StreamingProvider(ResponseProvider):
    """流式：thinking 用 Live Panel 逐 token 显示，content 不流"""

    async def get_response(self, agent: Agent, messages: list,
                           tools: list | None) -> dict:
        from merco.core.agent import console

        assembled: dict = {
            "role": "assistant", "content": "", "reasoning": "",
            "tool_calls": [], "finish_reason": None, "usage": None}
        reasoning_buf = ""
        content_buf = ""
        tc_buf: dict[int, dict] = {}

        stream_think = agent.config.streaming.think
        render_interval = agent.config.streaming.render_interval
        _last_render = 0.0
        _last_content_update = 0.0
        _content_update_interval = 0.3  # 300ms throttle for content panel

        # ── 初始等待提示（无 reasoning 时显示"⏳ 思考中…"，有则显示推理文字）──
        thinking_panel = Panel("[dim]⏳ 思考中…[/dim]", border_style="dim",
                      title="🧠 思考中…", title_align="left", padding=(0, 1))

        # ── content 面板延迟创建：收到第一个 content chunk 时才创建 ──
        content_panel = None  # lazy: created on first content chunk

        # ── 使用单个 Live 来显示 thinking 面板（content 面板延迟加入 Group）──
        live = Live(Group(thinking_panel), console=console, refresh_per_second=4,
                    transient=agent.config.streaming.think_transient)
        live.start()

        # ── 定时刷新任务：防止 API 返回慢时 thinking 面板卡顿 ──
        nonlocal_thinking_panel = [thinking_panel]  # mutable ref for closure
        nonlocal_content_panel: list[Panel | None] = [None]  # mutable ref for closure (lazy init)

        def _rebuild_group():
            """Rebuild Group with current panels"""
            if nonlocal_content_panel[0] is not None:
                return Group(nonlocal_thinking_panel[0], nonlocal_content_panel[0])
            return Group(nonlocal_thinking_panel[0])

        async def _refresh_thinking():
            while True:
                await asyncio.sleep(0.5)
                if reasoning_buf:
                    nonlocal_thinking_panel[0] = _build_reasoning_panel(reasoning_buf)
                    live.update(_rebuild_group())
        refresh_task = asyncio.create_task(_refresh_thinking())
        stream_error: Exception | None = None

        try:
            stream = agent.provider.chat_stream(messages, tools=tools)
            async for chunk in stream:
                # 取消检查点：如果任务被取消，立即退出
                current = asyncio.current_task()
                if current and current.cancelled():
                    live.stop()
                    # TODO: 此 checkpoint 无法覆盖「Cancel 在 __anext__ I/O 等待中到达」的情况
                    #      补救方案：加 except asyncio.CancelledError 兜底 handler，抽离保存逻辑。
                    #      优先级：低——窗口极小且用户主动取消，丢失的 partial content 是预期行为。
                    # 保存部分响应
                    assembled["reasoning"] = reasoning_buf
                    assembled["content"] = content_buf
                    if tc_buf:
                        assembled["tool_calls"] = [
                            {"id": v["id"], "name": v["name"],
                             "arguments": _json.loads(v["arguments"])
                             if v["arguments"] else {}}
                            for v in (tc_buf[i] for i in sorted(tc_buf))
                        ]
                    # 将部分响应添加到 context 和 session
                    if reasoning_buf or content_buf or tc_buf:
                        assistant_msg = {
                            "role": "assistant",
                            "content": content_buf,
                            "reasoning": reasoning_buf,
                        }
                        if tc_buf:
                            assistant_msg["tool_calls"] = assembled["tool_calls"]
                        logger.debug("StreamingProvider 中断: 将 reasoning(%d chars) 存入 context (这是唯一泄漏窗口)",
                                    len(reasoning_buf))
                        agent.context.add(assistant_msg)
                        agent.session.add_message("assistant", content_buf,
                                                  reasoning=reasoning_buf,
                                                  tool_calls=assembled.get("tool_calls"))
                    raise asyncio.CancelledError()
                r = chunk.get("reasoning", "")
                if r:
                    reasoning_buf += r
                    if stream_think:
                        now = time.monotonic()
                        if render_interval <= 0 or now - _last_render >= render_interval:
                            _last_render = now
                            nonlocal_thinking_panel[0] = _build_reasoning_panel(reasoning_buf)
                            live.update(_rebuild_group())
                content_buf += chunk.get("content", "")
                if content_buf.strip() and agent.config.streaming.content:
                    # Lazy init: create content_panel on first content chunk
                    if content_panel is None:
                        content_panel = Panel("", border_style="dim",
                                              title_align="left", padding=(0, 1))
                        nonlocal_content_panel[0] = content_panel
                    # Throttle updates to prevent excessive re-rendering
                    now = time.monotonic()
                    if now - _last_content_update >= _content_update_interval:
                        _last_content_update = now
                        content_panel.renderable = Markdown(content_buf)
                        live.update(_rebuild_group())
                for tc in chunk.get("tool_calls", []):
                    idx = tc["index"]
                    if idx not in tc_buf:
                        tc_buf[idx] = {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "arguments": ""}
                    if tc.get("id"): tc_buf[idx]["id"] = tc["id"]
                    if tc.get("name"): tc_buf[idx]["name"] = tc["name"]
                    tc_buf[idx]["arguments"] += tc.get("arguments", "")
                if chunk.get("finish_reason"):
                    assembled["finish_reason"] = chunk["finish_reason"]
                if chunk.get("usage"):
                    assembled["usage"] = chunk["usage"]
            # Final update to ensure all content is displayed
            if reasoning_buf:
                nonlocal_thinking_panel[0] = _build_reasoning_panel(reasoning_buf)
            if content_panel and content_buf.strip():
                content_panel.renderable = Markdown(content_buf)
            if reasoning_buf or (content_panel and content_buf.strip()):
                live.update(_rebuild_group())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            stream_error = e
            # logger.info：非 debug 模式（WARNING 阈值）不会输出到 stderr。
            logger.info("StreamingProvider API 错误: %s", e)
            logger.debug("StreamingProvider API 错误 traceback", exc_info=True)
            # 停止 Live，直接用 console.print 输出完整 ⚠ API 错误 Panel。
            # 每次 retry 各输出一个，自然堆叠。
            if live:
                live.stop()
            console.print(build_error_panel(classify_error(e)))
            agent._error_displayed_in_stream = True
            raise e
        finally:
            if 'refresh_task' in locals():
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass
            # live may have been stopped by except block; only stop if still active
            if live and live._started:
                live.stop()
            # re-raise — no additional output (error Panel already printed in except)
            if stream_error is not None:
                raise stream_error

        assembled["reasoning"] = reasoning_buf
        assembled["content"] = content_buf
        if tc_buf:
            assembled["tool_calls"] = [
                {"id": v["id"], "name": v["name"],
                 "arguments": _json.loads(v["arguments"])
                 if v["arguments"] else {}}
                for v in (tc_buf[i] for i in sorted(tc_buf))
            ]
        logger.debug(
            "stream done: finish=%s content=%d reasoning=%d tool_calls=%d%s",
            assembled.get("finish_reason"), len(assembled["content"]),
            len(assembled["reasoning"]), len(assembled["tool_calls"]),
            f" {[tc['name'] for tc in assembled['tool_calls']]}" if assembled["tool_calls"] else "")
        return assembled
