import atexit
import contextlib
import io
import logging
import pickle
import sys
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
from typing import Any, ParamSpec, TypeVar
from weakref import WeakSet

__version__ = "1.0.1"
__author__ = "Joshua Peek"
__copyright__ = "Copyright 2024 Joshua Peek"
__license__ = "MIT"

_logger = logging.getLogger("lru_cache")
_caches: WeakSet["PersistentLRUCache"] = WeakSet()

_SENTINEL = object()
_KWD_MARK = ("__KWD_MARK__",)

T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")


def bytesize(gb: int = 0, mb: int = 0, kb: int = 0, b: int = 0) -> int:
    return gb << 30 | mb << 20 | kb << 10 | b


def format_bytesize(size: int) -> str:
    """Formats an integer representing a byte size into a human-readable string."""
    s: float = float(size)
    if s < 1024:
        return f"{s} B"
    s /= 1024
    if s < 1024:
        return f"{s:.1f} KB"
    s /= 1024
    if s < 1024:
        return f"{s:.1f} MB"
    s /= 1024
    return f"{s:.1f} GB"


DEFAULT_MAX_ITEMS = sys.maxsize
DEFAULT_MAX_BYTESIZE = bytesize(mb=10)


class LRUCache(MutableMapping[Hashable, Any]):
    """An LRU cache that acts like a dict and a configurable max size."""

    _data: OrderedDict[Hashable, Any]
    _max_items: int
    _max_bytesize: int
    _did_change: bool = False
    _needs_trim: bool = True

    def __init__(
        self,
        max_items: int = DEFAULT_MAX_ITEMS,
        max_bytesize: int = DEFAULT_MAX_BYTESIZE,
    ) -> None:
        """Create a new LRUCache."""
        self._data = OrderedDict()
        self._max_items = max_items
        self._max_bytesize = max_bytesize

    def __repr__(self) -> str:
        count = len(self)
        size = format_bytesize(self.bytesize())
        return f"<LRUCache {count} items, {size}>"

    def __eq__(self, other: Any) -> bool:
        return other is self

    def __hash__(self) -> int:
        return id(self)

    def __contains__(self, key: Hashable) -> bool:
        """Return True if key is in the cache."""
        return key in self._data

    def __iter__(self) -> Iterator[Hashable]:
        """Iterate over keys in the cache."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of items in the cache."""
        return len(self._data)

    def __getitem__(self, key: Hashable) -> Any:
        """Return value for key in cache, else None."""
        value = self._data[key]
        _logger.debug("hit key=%s", key)
        self._did_change = True
        self._data.move_to_end(key, last=True)
        return value

    def __setitem__(self, key: Hashable, value: Any) -> None:
        """Set value for key in cache."""
        _logger.debug("set key=%s", key)
        self._did_change = True
        self._needs_trim = True
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
        self._needs_trim = False
        self._data.clear()

    def trim(self) -> int:
        """Trim the cache to fit within the max bytesize."""
        if not self._needs_trim:
            _logger.debug("skipping trim")
            return 0

        sorted_keys = list(self._data.keys())
        count = 0

        def _pop() -> None:
            nonlocal count
            key = sorted_keys.pop(0)
            self._did_change = True
            del self._data[key]
            count += 1

        while len(self._data) > self._max_items:
            _pop()

        buf = BytesIO()
        while self._bytesize(buf) > self._max_bytesize:
            _pop()

        self._needs_trim = False
        if count > 0:
            _logger.warning("trimmed %i items", count)
        return count

    def bytesize(self) -> int:
        """Return the persisted size of the cache in bytes."""
        return self._bytesize(BytesIO())

    def _bytesize(self, buf: BytesIO) -> int:
        buf.seek(0)
        p = pickle.Pickler(buf, protocol=pickle.HIGHEST_PROTOCOL)
        p.dump(self._data)
        return buf.tell()

    def get_or_load(self, key: Hashable, load_value: Callable[[], T]) -> T:
        """Get value for key in cache, else load the value and store it in the cache."""
        value: T = self._data.get(key, _SENTINEL)
        if value is _SENTINEL:
            _logger.debug("miss key=%s", key)
            value = load_value()
            self._did_change = True
            self._needs_trim = True
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
            return self.get_or_load(key, lambda: func(*args, **kwds))

        return update_wrapper(_inner, func)


class PersistentLRUCache(LRUCache, contextlib.AbstractContextManager["LRUCache"]):
    """A managed LRUCache that is persist to disk."""

    _file: io.BufferedRandom | None = None
    filename: Path
    closed: bool = False

    def __init__(
        self,
        filename: Path | str,
        max_items: int = DEFAULT_MAX_ITEMS,
        max_bytesize: int = DEFAULT_MAX_BYTESIZE,
    ) -> None:
        self.filename = Path(filename)
        super().__init__(max_items=max_items, max_bytesize=max_bytesize)
        self._load()
        _caches.add(self)

    def __del__(self) -> None:
        if not self.closed:
            self.close()

    def __enter__(self) -> "PersistentLRUCache":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _open(self) -> io.BufferedRandom:
        if self._file:
            return self._file
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.filename.touch(exist_ok=True)
        self._file = self.filename.open(mode="rb+")
        _logger.debug("opened cache %d '%s'", self._file.fileno(), self.filename)
        return self._file

    def _load(self) -> None:
        if not self.filename.exists():
            _logger.debug("cache not found: '%s'", self.filename)
            return

        f = self._open()
        self._data.update(pickle.load(f))
        self._did_change = False

        _logger.info(
            "loaded cache: '%s' (%i items, %s bytes)",
            self.filename,
            len(self),
            format_bytesize(self.bytesize()),
        )

    def save(self) -> None:
        """Save the cache to disk."""
        if self._did_change is False:
            _logger.debug("no changes to save")
            return

        self.trim()
        _logger.info(
            "saving cache: '%s' (%i items, %s)",
            self.filename,
            len(self),
            format_bytesize(self.bytesize()),
        )
        f = self._open()
        f.seek(0)
        pickle.dump(self._data, f, pickle.HIGHEST_PROTOCOL)
        self._did_change = False

    def close(self) -> None:
        """Close the cache and save it to disk."""
        if self.closed:
            assert self._file is None, "file should be closed"
            raise ValueError("cache is already closed")
        self.save()
        if self._file:
            fd = self._file.fileno()
            self._file.close()
            self._file = None
            _logger.debug("closed cache %d '%s'", fd, self.filename)
        self.closed = True


def open(
    filename: Path | str,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_bytesize: int = DEFAULT_MAX_BYTESIZE,
) -> PersistentLRUCache:
    return PersistentLRUCache(
        filename=filename,
        max_items=max_items,
        max_bytesize=max_bytesize,
    )


def _close_atexit() -> None:
    open_caches = [cache for cache in _caches if not cache.closed]
    if open_caches:
        _logger.warning("closing open %d caches", len(open_caches))
    for cache in open_caches:
        cache.close()


atexit.register(_close_atexit)
