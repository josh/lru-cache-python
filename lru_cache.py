import atexit
import logging
import pickle
from collections import OrderedDict
from collections.abc import (
    Callable,
    Hashable,
    ItemsView,
    Iterator,
    KeysView,
    MutableMapping,
    ValuesView,
)
from functools import _make_key, update_wrapper
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Any, ParamSpec, TypeVar, cast

__author__ = "Joshua Peek"
__url__ = "https://raw.githubusercontent.com/josh/py-lru-cache/main/lru_cache.py"
__license__ = "MIT"
__copyright__ = "Copyright 2024 Joshua Peek"

_logger = logging.getLogger("lru_cache")
_caches_to_save: list["LRUCache"] = []

_SENTINEL = object()
_KWD_MARK = ("__KWD_MARK__",)

P = ParamSpec("P")
R = TypeVar("R")


class LRUCache(MutableMapping[Hashable, Any]):
    """Persisted least recently used key-value cache."""

    filename: Path | None
    _data: OrderedDict[Hashable, Any]
    _max_bytesize: int
    _did_change: bool = False

    def __init__(
        self,
        filename: Path | str | None = None,
        max_bytesize: int = 1024 * 1024,  # 1 MB
        save_on_exit: bool = False,
    ) -> None:
        """Create a new LRUCache."""
        self.filename = None
        if filename:
            self.filename = Path(filename)
        self._data = OrderedDict()
        self._max_bytesize = max_bytesize
        self._load()
        if save_on_exit:
            _caches_to_save.append(self)

    def __repr__(self) -> str:
        count = len(self)
        size = self.bytesize()
        return f"<LRUCache {count} items, {size} bytes>"

    def __contains__(self, key: Hashable) -> bool:
        """Return True if key is in the cache."""
        return key in self._data

    def __iter__(self) -> Iterator[Hashable]:
        """Iterate over keys in the cache."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of items in the cache."""
        return len(self._data)

    def __getitem__(self, key: Hashable) -> Any | None:
        """Return value for key in cache, else None."""
        value = self._data.get(key, _SENTINEL)
        if value is _SENTINEL:
            _logger.debug("miss key=%s", key)
            return None
        else:
            _logger.debug("hit key=%s", key)
            self._did_change = True
            self._data.move_to_end(key, last=True)
            return value

    def __setitem__(self, key: Hashable, value: Any) -> None:
        """Set value for key in cache."""
        _logger.debug("set key=%s", key)
        self._did_change = True
        self._data[key] = value
        self._data.move_to_end(key, last=True)

    def __delitem__(self, key: Hashable) -> None:
        """Delete key from cache."""
        _logger.debug("del key=%s", key)
        self._did_change = True
        del self._data[key]

    def keys(self) -> KeysView[Hashable]:
        """Return an iterator over the keys in the cache."""
        return self._data.keys()

    def values(self) -> ValuesView[Any]:
        """Return an iterator over the values in the cache."""
        return self._data.values()

    def items(self) -> ItemsView[Hashable, Any]:
        """Return an iterator over the items in the cache."""
        return self._data.items()

    def get(self, key: Hashable, default: Any = None) -> Any | None:
        """Return value for key in cache, else default."""
        value = self._data.get(key, _SENTINEL)
        if value is _SENTINEL:
            _logger.debug("miss key=%s", key)
            return default
        else:
            _logger.debug("hit key=%s", key)
            self._did_change = True
            self._data.move_to_end(key, last=True)
            return value

    def clear(self) -> None:
        """Clear the cache."""
        _logger.debug("clear")
        self._did_change = True
        self._data.clear()

    def _load(self) -> None:
        if self.filename is None:
            return

        if not self.filename.exists():
            _logger.debug("persisted cache not found: %s", self.filename)
            return

        with self.filename.open("rb") as f:
            self._data.update(pickle.load(f))
        self._did_change = False

    def save(self) -> None:
        """Save the cache to disk."""
        if not self.filename:
            _logger.error("failed to save LRU cache: no path provided")
            return

        if self._did_change is False:
            _logger.info("no changes to save")
            return

        self.trim()
        _logger.debug("saving cache: %s", self.filename)
        if isinstance(self.filename, Path):
            self.filename.parent.mkdir(parents=True, exist_ok=True)
        with self.filename.open("wb") as f:
            pickle.dump(self._data, f, pickle.HIGHEST_PROTOCOL)

    def close(self) -> None:
        self.save()

    def trim(self) -> int:
        """Trim the cache to fit within the max bytesize."""
        sorted_keys = list(self._data.keys())
        count = 0
        buf = BytesIO()
        while True:
            buf.seek(0)
            p = pickle.Pickler(buf, protocol=pickle.HIGHEST_PROTOCOL)
            p.dump(self._data)
            if buf.tell() < self._max_bytesize:
                break
            key = sorted_keys.pop(0)
            self._did_change = True
            del self._data[key]
            count += 1
        if count > 0:
            _logger.debug("trimmed %i items", count)
        return count

    def bytesize(self) -> int:
        """Return the persisted size of the cache in bytes."""
        buf = BytesIO()
        p = pickle.Pickler(buf, protocol=pickle.HIGHEST_PROTOCOL)
        p.dump(self._data)
        return buf.tell()

    def get_or_load(self, key: Hashable, load_value: Callable[[], Any]) -> Any:
        """Get value for key in cache, else load the value and store it in the cache."""
        value = self._data.get(key, _SENTINEL)
        if value is _SENTINEL:
            _logger.debug("miss key=%s", key)
            value = load_value()
            self._did_change = True
            self._data[key] = value
            return value
        else:
            _logger.debug("hit key=%s", key)
            self._did_change = True
            self._data.move_to_end(key, last=True)
            return value

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        def _inner(*args: P.args, **kwds: P.kwargs) -> R:
            keys = _make_key(args=args, kwds=kwds, typed=True, kwd_mark=_KWD_MARK)
            assert isinstance(keys, list)
            key = (func.__module__, func.__name__, *keys)
            value = self.get_or_load(key, lambda: func(*args, **kwds))
            return cast(R, value)

        return update_wrapper(_inner, func)

    def __enter__(self) -> "LRUCache":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.save()


def open(filename: Path | str) -> LRUCache:
    return LRUCache(filename=filename)


def _save_caches() -> None:
    for cache in _caches_to_save:
        cache.save()


atexit.register(_save_caches)
