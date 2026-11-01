from datetime import UTC, datetime, timedelta

from app.domain.auth.throttle import MAX_FAILED_SIGN_INS, SIGN_IN_LOCKOUT, SignInThrottle

T = datetime(2026, 1, 1, 12, tzinfo=UTC)
KEY = "ana@acme.com"


def _fail(throttle: SignInThrottle, times: int, at: datetime = T, key: str = KEY) -> None:
    for _ in range(times):
        throttle.record_failure(key, at)


def test_values() -> None:
    assert MAX_FAILED_SIGN_INS == 5
    assert timedelta(minutes=15) == SIGN_IN_LOCKOUT


def test_locks_after_max_failures() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 4)
    assert throttle.retry_after(KEY, T) is None

    _fail(throttle, 1)

    assert throttle.retry_after(KEY, T) == timedelta(minutes=15)


def test_retry_after_counts_down() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 5)

    assert throttle.retry_after(KEY, T + timedelta(minutes=10)) == timedelta(minutes=5)


def test_lock_lifts_after_the_window() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 5)

    assert throttle.retry_after(KEY, T + timedelta(minutes=15)) is None


def test_window_slides() -> None:
    throttle = SignInThrottle()
    for minute in range(5):
        throttle.record_failure(KEY, T + timedelta(minutes=minute))

    assert throttle.retry_after(KEY, T + timedelta(minutes=14)) == timedelta(minutes=1)
    # The failure at T has left the window; four remain, so the key is open.
    assert throttle.retry_after(KEY, T + timedelta(minutes=15)) is None


def test_success_clears_failures() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 5)

    throttle.clear(KEY)

    assert throttle.retry_after(KEY, T) is None


def test_keys_are_independent() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 5)

    assert throttle.retry_after("bo@acme.com", T) is None


def test_stale_keys_are_pruned() -> None:
    throttle = SignInThrottle()
    for n in range(1025):
        throttle.record_failure(f"user{n}@acme.com", T)

    throttle.record_failure(KEY, T + SIGN_IN_LOCKOUT)

    assert len(throttle) == 1


def test_stale_keys_are_pruned_below_any_size_threshold() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 1, key="a@acme.com")
    _fail(throttle, 1, key="b@acme.com")

    throttle.record_failure(KEY, T + SIGN_IN_LOCKOUT)

    assert len(throttle) == 1


def test_a_refreshed_key_moves_behind_stale_ones() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 1, key="a@acme.com")
    _fail(throttle, 1, at=T + timedelta(minutes=1), key="b@acme.com")
    _fail(throttle, 1, at=T + timedelta(minutes=10), key="a@acme.com")

    throttle.record_failure(KEY, T + timedelta(minutes=16))

    # b's newest failure left the window; a's did not.
    assert len(throttle) == 2


def test_an_emptied_key_is_pruned() -> None:
    throttle = SignInThrottle()
    _fail(throttle, 1, key="a@acme.com")
    later = T + SIGN_IN_LOCKOUT
    assert throttle.retry_after("a@acme.com", later) is None  # empties a's deque

    throttle.record_failure(KEY, later)

    assert len(throttle) == 1
