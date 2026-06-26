"""MemoryBackend + Registry 单测"""
import pytest
from merco.memory.backend import MemoryBackend, MemoryBackendRegistry


class DummyBackend(MemoryBackend):
    name = "dummy"

    def __init__(self):
        self._data: dict[str, dict] = {}

    def save(self, key, value, tags=None):
        self._data[key] = {"key": key, "value": value, "tags": tags or []}

    def load(self, key):
        return self._data.get(key)

    def delete(self, key):
        self._data.pop(key, None)

    def list_keys(self, tag=None):
        if tag:
            return [k for k, v in self._data.items() if tag in v.get("tags", [])]
        return list(self._data.keys())

    def search(self, query):
        results = []
        for v in self._data.values():
            if query.lower() in str(v).lower():
                results.append(v)
        return results


class TestMemoryBackendABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            MemoryBackend()  # noqa

    def test_concrete_subclass_works(self):
        b = DummyBackend()
        b.save("k1", "v1")
        assert b.load("k1")["value"] == "v1"


class TestMemoryBackendRegistry:
    def test_register_and_get(self):
        reg = MemoryBackendRegistry()
        reg.register(DummyBackend())
        assert reg.get("dummy") is not None
        assert reg.get("nonexistent") is None

    def test_list(self):
        reg = MemoryBackendRegistry()
        reg.register(DummyBackend())
        assert len(reg.list()) == 1
