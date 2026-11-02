from datetime import timedelta

from app.domain.auth.throttle import MAX_FAILED_SIGN_INS, SIGN_IN_LOCKOUT, SignInThrottle
from tests.fakes import FakeClock

KEY = "ana@acme.com"


def _throttle() -> tuple[SignInThrottle, FakeClock]:
    clock = FakeClock()
    return SignInThrottle(clock=clock), clock


def _fail(throttle: SignInThrottle, times: int, key: str = KEY) -> None:
    for _ in range(times):
        throttle.record_failure(key)


def test_values() -> None:
    assert MAX_FAILED_SIGN_INS == 5
    assert timedelta(minutes=15) == SIGN_IN_LOCKOUT


def test_locks_after_max_failures() -> None:
    throttle, _ = _throttle()
    _fail(throttle, 4)
    assert throttle.retry_after(KEY) is None

    _fail(throttle, 1)

    assert throttle.retry_after(KEY) == timedelta(minutes=15)


def test_retry_after_counts_down() -> None:
    throttle, clock = _throttle()
    _fail(throttle, 5)

    clock.advance(timedelta(minutes=10))

    assert throttle.retry_after(KEY) == timedelta(minutes=5)


def test_lock_lifts_after_the_window() -> None:
    throttle, clock = _throttle()
    _fail(throttle, 5)

    clock.advance(timedelta(minutes=15))

    assert throttle.retry_after(KEY) is None


def test_window_slides() -> None:
    throttle, clock = _throttle()
    for _ in range(5):
        throttle.record_failure(KEY)
        clock.advance(timedelta(minutes=1))

    clock.advance(timedelta(minutes=9))  # 14 minutes after the first failure
    assert throttle.retry_after(KEY) == timedelta(minutes=1)
    # The first failure has left the window; four remain, so the key is open.
    clock.advance(timedelta(minutes=1))
    assert throttle.retry_after(KEY) is None


def test_success_clears_failures() -> None:
    throttle, _ = _throttle()
    _fail(throttle, 5)

    throttle.clear(KEY)

    assert throttle.retry_after(KEY) is None


def test_keys_are_independent() -> None:
    throttle, _ = _throttle()
    _fail(throttle, 5)

    assert throttle.retry_after("bo@acme.com") is None


def test_stale_keys_are_pruned() -> None:
    throttle, clock = _throttle()
    for n in range(1025):
        throttle.record_failure(f"user{n}@acme.com")

    clock.advance(SIGN_IN_LOCKOUT)
    throttle.record_failure(KEY)

    assert len(throttle) == 1


def test_stale_keys_are_pruned_below_any_size_threshold() -> None:
    throttle, clock = _throttle()
    _fail(throttle, 1, key="a@acme.com")
    _fail(throttle, 1, key="b@acme.com")

    clock.advance(SIGN_IN_LOCKOUT)
    throttle.record_failure(KEY)

    assert len(throttle) == 1


def test_a_refreshed_key_moves_behind_stale_ones() -> None:
    throttle, clock = _throttle()
    _fail(throttle, 1, key="a@acme.com")
    clock.advance(timedelta(minutes=1))
    _fail(throttle, 1, key="b@acme.com")
    clock.advance(timedelta(minutes=9))
    _fail(throttle, 1, key="a@acme.com")

    clock.advance(timedelta(minutes=6))  # 16 minutes after the start
    throttle.record_failure(KEY)

    # b's newest failure left the window; a's did not.
    assert len(throttle) == 2


def test_an_emptied_key_is_pruned() -> None:
    throttle, clock = _throttle()
    _fail(throttle, 1, key="a@acme.com")
    clock.advance(SIGN_IN_LOCKOUT)
    assert throttle.retry_after("a@acme.com") is None  # empties a's deque

    throttle.record_failure(KEY)

    assert len(throttle) == 1
