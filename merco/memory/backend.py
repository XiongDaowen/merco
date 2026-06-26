"""MemoryBackend ABC + MemoryBackendRegistry"""
from __future__ import annotations

from abc import ABC, abstractmethod


class MemoryBackend(ABC):
    """记忆存储后端基类"""
    name: str = ""

    @abstractmethod
    def save(self, key: str, value, tags: list = None) -> None:
        """保存记忆"""
        ...

    @abstractmethod
    def load(self, key: str) -> dict | None:
        """加载记忆"""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除记忆"""
        ...

    @abstractmethod
    def list_keys(self, tag: str = None) -> list[str]:
        """列出所有记忆键"""
        ...

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        """搜索记忆"""
        ...


class MemoryBackendRegistry:
    """MemoryBackend 注册表"""

    def __init__(self):
        self._backends: dict[str, MemoryBackend] = {}

    def register(self, backend: MemoryBackend) -> None:
        self._backends[backend.name] = backend

    def get(self, name: str) -> MemoryBackend | None:
        return self._backends.get(name)

    def list(self) -> list[MemoryBackend]:
        return list(self._backends.values())
