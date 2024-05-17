# lru-cache

A simple persisted LRU cache Python module.

Pretty much [`shelve`](https://docs.python.org/3/library/shelve.html), but self evicting. Design to work well when persisting data between GitHub Action runs with [actions/cache](https://github.com/actions/cache).

## Usage

```python
import lru_cache

with lru_cache.open("cache.pickle") as cache:
    cache["answer"] = 42
```

## Installation

Not officially published on Python Package Index (PyPI), but you can install by downloading the file directly.

```sh
$ curl https://raw.githubusercontent.com/josh/py-lru-cache/main/lru_cache.py >lru_cache.py
```
