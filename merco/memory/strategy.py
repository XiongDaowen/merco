"""Memory 保存触发策略 — 监听 Hook 事件，构造 SaveItem 喂给 Pipeline"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod

from .save_pipeline import SaveItem

logger = logging.getLogger("merco.memory.strategy")


class MemorySaveStrategy(ABC):
    """监听事件，构造 SaveItem 喂给 Pipeline"""

    name: str = ""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    @abstractmethod
    async def on_event(self, event: str, **kwargs) -> None: ...


class ExplicitRememberStrategy(MemorySaveStrategy):
    """/remember <text> 显式存一条记忆"""
    name = "explicit_remember"

    def subscribe(self, hooks) -> None:
        """注册到 HookRegistry"""
        hooks.on("command.remember", self._on_remember)

    async def on_event(self, event: str, **kwargs) -> None:
        """兼容直接调用（测试用）"""
        await self._on_remember(**kwargs)

    async def _on_remember(self, text: str, key: str = "", **kwargs) -> None:
        if not key:
            key = self._derive_key(text)
        item = SaveItem(key=key, value=text, source="user")
        await self.pipeline.save(item)

    @staticmethod
    def _derive_key(text: str) -> str:
        """从文本生成稳定 key: user_<前20字净化>_<hash8>"""
        h = hashlib.md5(text.encode()).hexdigest()[:8]
        prefix = re.sub(r"\W+", "_", text[:20].strip()).strip("_")
        return f"user_{prefix}_{h}" if prefix else f"user_{h}"


class SessionEndExtractStrategy(MemorySaveStrategy):
    """session.destroy 时用 LLM 抽取 1-3 条 insight 记忆"""
    name = "session_end_extract"

    EXTRACT_PROMPT = """从以下对话中抽取 1-3 条值得长期记住的关键信息（用户偏好、事实、决策）。
仅返回 JSON 数组，每条形如 {{"key": "snake_case_key", "value": "原文", "tags": ["tag1"]}}。
没有值得记的就返回 []。

对话：
{messages}
"""

    def __init__(self, pipeline, llm, *,
                 session_store=None, max_per_session: int = 3,
                 min_messages: int = 5):
        super().__init__(pipeline)
        self.llm = llm
        self._session_store = session_store
        self.max = max_per_session
        self.min_msgs = min_messages

    def subscribe(self, hooks) -> None:
        hooks.on("session.destroy", self._on_destroy)

    async def on_event(self, event: str, **kwargs) -> None:
        """兼容直接调用（测试用）"""
        await self._on_destroy(**kwargs)

    async def _on_destroy(self, session_id: str = "", **kwargs) -> None:
        if not self._session_store or not session_id:
            return
        try:
            messages = self._session_store.load_messages(session_id)
        except Exception as e:
            logger.warning("加载 session 消息失败: %s", e)
            return
        if not messages or len(messages) < self.min_msgs:
            return

        prompt = self.EXTRACT_PROMPT.format(
            messages=self._format_messages(messages)
        )
        try:
            response = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                tools=None, tool_choice="none",
            )
        except Exception as e:
            logger.warning("LLM 抽取失败，跳过: %s", e)
            return

        items = self._parse_llm_output(response.get("content", ""), session_id)
        for item in items:
            await self.pipeline.save(item)

    @staticmethod
    def _format_messages(messages: list) -> str:
        """压缩消息为 LLM 提示（仅 role + content）"""
        lines = []
        for m in messages:
            role = m.get("role", "?")
            content = (m.get("content") or "").strip()
            if content:
                lines.append(f"[{role}] {content[:200]}")
        return "\n".join(lines)

    def _parse_llm_output(self, content: str, session_id: str) -> list[SaveItem]:
        """解析 LLM JSON 输出为 SaveItem 列表"""
        content = (content or "").strip()
        # 尝试提取 ```json ... ``` 包裹
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
        try:
            data = json.loads(content)
        except (ValueError, TypeError) as e:
            logger.warning("LLM 输出解析失败: %s", e)
            return []
        if not isinstance(data, list):
            return []
        items = []
        for entry in data[:3]:  # 兜底再 cap
            if not isinstance(entry, dict):
                continue
            key = entry.get("key", "").strip()
            value = entry.get("value", "").strip()
            if not key or not value:
                continue
            tags = entry.get("tags", []) or []
            if not isinstance(tags, list):
                tags = []
            items.append(SaveItem(
                key=key, value=value, source="extracted",
                tags=[str(t) for t in tags], session_id=session_id,
            ))
        return items[:self.max]
