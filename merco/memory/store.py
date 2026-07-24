"""记忆存储引擎 — facade，委托给 MemoryBackend"""
from __future__ import annotations

from typing import Optional

from .backend import MemoryBackend
from .backends.json_backend import JSONBackend


class MemoryStore:
    """持久化记忆存储"""

    def __init__(self, base_path: str = None, backend: MemoryBackend = None):
        if backend:
            self.backend = backend
        else:
            self.backend = JSONBackend(base_path or "~/.merco/memory")

    def save(self, key: str, value, tags: list = None):
        return self.backend.save(key, value, tags)

    def load(self, key: str) -> Optional[dict]:
        return self.backend.load(key)

    def delete(self, key: str):
        return self.backend.delete(key)

    def list_keys(self, tag: str = None) -> list[str]:
        return self.backend.list_keys(tag)

    def search(self, query: str) -> list[dict]:
        return self.backend.search(query)
