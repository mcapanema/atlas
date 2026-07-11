from app.infrastructure.repositories.batching import chunked


def test_chunked_splits_and_preserves_order() -> None:
    assert [list(c) for c in chunked([1, 2, 3, 4, 5], size=2)] == [[1, 2], [3, 4], [5]]


def test_chunked_empty_yields_nothing() -> None:
    assert list(chunked([], size=2)) == []


def test_chunked_default_size_is_below_sqlite_bind_limit() -> None:
    (chunk,) = chunked(list(range(900)))
    assert len(chunk) == 900
