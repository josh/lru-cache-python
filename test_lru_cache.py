from pathlib import Path

import pytest

from lru_cache import LRUCache


@pytest.fixture()
def memory_cache() -> LRUCache:
    return LRUCache(max_bytesize=1024)


@pytest.fixture()
def file_cache(tmp_path: Path) -> LRUCache:
    return LRUCache(path=tmp_path / "cache.pickle", max_bytesize=1024)


def test_item_get_set(memory_cache: LRUCache) -> None:
    assert memory_cache["key"] is None

    memory_cache["key"] = 1
    assert memory_cache["key"] == 1
    assert memory_cache["key"] == 1

    memory_cache["key"] = 2
    assert memory_cache["key"] == 2


def test_item_del(memory_cache: LRUCache) -> None:
    memory_cache["key"] = 1
    assert memory_cache["key"] == 1
    del memory_cache["key"]
    assert memory_cache["key"] is None


def test_contains(memory_cache: LRUCache) -> None:
    assert "key" not in memory_cache
    memory_cache["key"] = 1
    assert "key" in memory_cache
    assert "key2" not in memory_cache


def test_len(memory_cache: LRUCache) -> None:
    assert len(memory_cache) == 0
    memory_cache["key"] = 1
    assert len(memory_cache) == 1


def test_list(memory_cache: LRUCache) -> None:
    memory_cache["key1"] = 1
    memory_cache["key2"] = 2
    memory_cache["key3"] = 3
    assert list(memory_cache) == ["key1", "key2", "key3"]


def test_items(memory_cache: LRUCache) -> None:
    memory_cache["key1"] = 1
    memory_cache["key2"] = 2
    memory_cache["key3"] = 3
    assert list(memory_cache.items()) == [("key1", 1), ("key2", 2), ("key3", 3)]


def test_get_or_load(memory_cache: LRUCache) -> None:
    def load_value() -> int:
        return 42

    assert len(memory_cache) == 0
    assert memory_cache.get("key", load_value) == 42
    assert len(memory_cache) == 1
    assert memory_cache.get("key", load_value) == 42
    assert len(memory_cache) == 1


def test_trim(file_cache: LRUCache) -> None:
    for i in range(300):
        file_cache[i] = i
    assert file_cache.bytesize() > 1024
    file_cache.trim()
    assert file_cache.bytesize() <= 1024
