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


from merco.memory.backends.json_backend import JSONBackend  # noqa: E402 - 与 TestJSONBackend 分组


class TestJSONBackend:
    def test_save_and_load(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", {"text": "hello"}, tags=["[user]"])
        record = b.load("k1")
        assert record["value"]["text"] == "hello"
        assert "[user]" in record["tags"]

    def test_delete(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", "v1")
        b.delete("k1")
        assert b.load("k1") is None

    def test_list_keys(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", "v1", tags=["[user]"])
        b.save("k2", "v2", tags=["[extracted]"])
        keys = b.list_keys()
        assert len(keys) == 2
        assert len(b.list_keys(tag="[user]")) == 1

    def test_search(self, tmp_path):
        b = JSONBackend(str(tmp_path))
        b.save("k1", {"text": "hello world"})
        b.save("k2", {"text": "goodbye"})
        results = b.search("hello")
        assert len(results) == 1
        assert results[0]["key"] == "k1"


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
