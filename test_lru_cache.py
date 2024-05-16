from pathlib import Path

import pytest

import lru_cache
from lru_cache import LRUCache, PersistentLRUCache


@pytest.fixture()
def cache() -> LRUCache:
    return LRUCache()


@pytest.fixture()
def file_cache(tmp_path: Path) -> PersistentLRUCache:
    return PersistentLRUCache(filename=tmp_path / "cache.pickle")


def test_eq(cache: LRUCache) -> None:
    assert cache == cache
    assert cache != LRUCache()
    assert cache != 42


def test_hash(cache: LRUCache) -> None:
    assert hash(cache) == hash(cache)
    assert hash(cache) != hash(LRUCache())


def test_item_get_set(cache: LRUCache) -> None:
    assert cache["key"] is None

    cache["key"] = 1
    assert cache["key"] == 1
    assert cache["key"] == 1

    cache["key"] = 2
    assert cache["key"] == 2


def test_item_del(cache: LRUCache) -> None:
    cache["key"] = 1
    assert cache["key"] == 1
    del cache["key"]
    assert cache["key"] is None


def test_repr(cache: LRUCache) -> None:
    assert repr(cache) == "<LRUCache 0 items, 45 bytes>"
    cache["key"] = 1
    assert repr(cache) == "<LRUCache 1 items, 54 bytes>"


def test_contains(cache: LRUCache) -> None:
    assert "key" not in cache
    cache["key"] = 1
    assert "key" in cache
    assert "key2" not in cache


def test_len(cache: LRUCache) -> None:
    assert len(cache) == 0
    cache["key"] = 1
    assert len(cache) == 1


def test_list(cache: LRUCache) -> None:
    cache["key1"] = 1
    cache["key2"] = 2
    cache["key3"] = 3
    assert list(cache) == ["key1", "key2", "key3"]


def test_keys(cache: LRUCache) -> None:
    cache["key1"] = 1
    cache["key2"] = 2
    cache["key3"] = 3
    assert list(cache.keys()) == ["key1", "key2", "key3"]


def test_values(cache: LRUCache) -> None:
    cache["key1"] = 1
    cache["key2"] = 2
    cache["key3"] = 3
    assert list(cache.values()) == [1, 2, 3]


def test_items(cache: LRUCache) -> None:
    cache["key1"] = 1
    cache["key2"] = 2
    cache["key3"] = 3
    assert list(cache.items()) == [("key1", 1), ("key2", 2), ("key3", 3)]


def test_get(cache: LRUCache) -> None:
    assert "key" not in cache
    assert cache.get("key", 42) == 42
    assert "key" not in cache

    cache["key"] = 1
    assert "key" in cache
    assert cache.get("key") == 1


def test_clear(cache: LRUCache) -> None:
    cache["key1"] = 1
    cache["key2"] = 2
    cache["key3"] = 3
    assert len(cache) == 3
    cache.clear()
    assert len(cache) == 0


def test_get_or_load(cache: LRUCache) -> None:
    def load_value() -> int:
        return 42

    assert len(cache) == 0
    assert cache.get_or_load("key", load_value) == 42
    assert len(cache) == 1
    assert cache.get_or_load("key", load_value) == 42
    assert len(cache) == 1


def test_trim_max_items() -> None:
    cache = LRUCache(max_items=10)
    for i in range(20):
        cache[i] = i
    assert len(cache) > 10
    cache.trim()
    assert len(cache) <= 10


def test_trim_max_items_zero() -> None:
    cache = LRUCache(max_items=0)
    for i in range(3):
        cache[i] = i
    cache.trim()
    assert len(cache) == 0


def test_trim_max_bytesize() -> None:
    cache = LRUCache(max_bytesize=1024)
    for i in range(300):
        cache[i] = i
    assert cache.bytesize() > 1024
    cache.trim()
    assert cache.bytesize() <= 1024


def test_decorator(cache: LRUCache) -> None:
    @cache
    def fib(n: int) -> int:
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)

    assert len(cache) == 0
    assert fib(10) == 55
    assert len(cache) == 11


def test_open_managed(tmp_path: Path) -> None:
    path = tmp_path / "cache.pickle"
    assert not path.exists()

    cache = lru_cache.open(path)
    cache["key"] = 1
    assert cache["key"] == 1

    assert not path.exists()
    cache.close()
    assert path.exists()

    cache = lru_cache.open(tmp_path / "cache.pickle")
    assert cache["key"] == 1
    assert path.exists()


def test_open_context(tmp_path: Path) -> None:
    path = tmp_path / "cache.pickle"
    assert not path.exists()

    with lru_cache.open(path) as cache:
        cache["key"] = 1
        assert cache["key"] == 1
    assert path.exists()

    with lru_cache.open(tmp_path / "cache.pickle") as cache:
        assert cache["key"] == 1
    assert path.exists()


def test_open_context_saves_on_exception(tmp_path: Path) -> None:
    path = tmp_path / "cache.pickle"
    assert not path.exists()

    try:
        with lru_cache.open(path) as cache:
            cache["key"] = 1
            raise Exception("oops")
    except Exception:
        pass
    finally:
        assert path.exists()


def test_open_doesnt_write_empty_cache(tmp_path: Path) -> None:
    path = tmp_path / "cache.pickle"
    assert not path.exists()
    with lru_cache.open(path) as cache:
        assert len(cache) == 0
    assert not path.exists()
