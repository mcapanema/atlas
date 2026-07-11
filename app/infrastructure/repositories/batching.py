"""Bounded IN(...) parameter lists for repository queries.

ponytail: SQLite's historical bind-parameter ceiling is 999 and its modern
default is 32766; 900 stays under both with headroom for a query's other
parameters, and is a harmless floor on PostgreSQL. Tune per-dialect only if
chunk count ever shows up in a profile.
"""

from collections.abc import Iterator, Sequence

BATCH_SIZE = 900


def chunked[T](items: Sequence[T], size: int | None = None) -> Iterator[Sequence[T]]:
    """Yield successive slices of at most `size` items (module default: BATCH_SIZE).

    BATCH_SIZE is read at call time so tests can monkeypatch it.
    """
    if size is None:
        size = BATCH_SIZE
    for start in range(0, len(items), size):
        yield items[start : start + size]
