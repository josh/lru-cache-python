# lru-cache

A simple persisted LRU cache Python module.

Pretty much [`shelve`](https://docs.python.org/3/library/shelve.html), but self evicting. Design to work well when persisting data between GitHub Action runs with [actions/cache](https://github.com/actions/cache).

## Usage

```python
import lru_cache

with lru_cache.open("cache.pickle", max_bytesize=lru_cache.bytesize(kb=5)) as cache:
    cache["answer"] = 42
```

Or using click with it's resource manager:

```python
import click
import lru_cache

@click.group()
@click.option("--cache-path", default="cache.pickle", type=click.Path(writable=True))
@click.pass_context
def cli(ctx, cache_path):
    ctx.obj = ctx.with_resource(lru_cache.open(cache_path))

@cli.command()
@click.pass_obj
def incr(cache: lru_cache.LRUCache):
    cache["count"] = count = cache.get("count", 0) + 1
    click.echo(f"count: {count}")
```

## Installation

Not officially published on Python Package Index (PyPI), but you can install it directly from GitHub:

```sh
$ pip install git+https://github.com/josh/lru-cache-py.git
```

or just download the file:

```sh
$ curl -L https://github.com/josh/lru-cache-py/releases/latest/download/lru_cache.py >lru_cache.py
```
