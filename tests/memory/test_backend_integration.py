"""MemoryBackend backward compatibility integration tests"""

import os

from merco.memory.backends.json_backend import JSONBackend
from merco.memory.store import MemoryStore


def test_memory_store_no_backend_uses_json_default(tmp_path):
    """MemoryStore() without backend parameter -- auto uses JSONBackend"""
    store = MemoryStore(str(tmp_path / "memory"))
    store.save("k1", "hello")
    assert store.load("k1")["value"] == "hello"


def test_memory_store_with_explicit_backend(tmp_path):
    """MemoryStore(backend=JSONBackend(...)) delegates correctly"""
    backend = JSONBackend(str(tmp_path / "custom"))
    store = MemoryStore(backend=backend)
    store.save("k1", "v1")
    assert store.load("k1") is not None
    # verify file is created in the custom directory
    assert os.path.exists(str(tmp_path / "custom" / "k1.json"))


def test_memory_store_full_crud(tmp_path):
    """MemoryStore facade full CRUD"""
    store = MemoryStore(str(tmp_path / "memory"))
    # create
    store.save("k1", "v1", tags=["[user]"])
    # read
    assert store.load("k1") is not None
    # list
    assert "k1" in store.list_keys()
    assert "k1" in store.list_keys(tag="[user]")
    # search
    results = store.search("v1")
    assert len(results) == 1
    # delete
    store.delete("k1")
    assert store.load("k1") is None
