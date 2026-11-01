import time
from collections import deque
from collections.abc import Callable
from datetime import timedelta

MAX_FAILED_SIGN_INS = 5
SIGN_IN_LOCKOUT = timedelta(minutes=15)


class SignInThrottle:
    """Locks a key (an email) after too many failed sign-ins inside a sliding window.

    It reads a monotonic clock, not the wall clock, so a clock step can
    neither reorder its keys nor stretch a lock.

    ponytail: in-process memory — per process, and a restart clears it. That
    fits the single-process monolith (ADR-0002). Upgrade path: a DB-backed
    counter if Atlas ever runs several workers.
    """

    def __init__(
        self,
        max_failures: int = MAX_FAILED_SIGN_INS,
        window: timedelta = SIGN_IN_LOCKOUT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window = window.total_seconds()
        self._clock = clock
        # Ordered by each key's newest failure (dicts keep insertion order).
        self._failures: dict[str, deque[float]] = {}

    def __len__(self) -> int:
        return len(self._failures)

    def retry_after(self, key: str) -> timedelta | None:
        """How long the key stays locked, or None when it may try again."""
        now = self._clock()
        failures = self._live(key, now)
        if len(failures) < self._max_failures:
            return None
        return timedelta(seconds=failures[-self._max_failures] + self._window - now)

    def record_failure(self, key: str) -> None:
        now = self._clock()
        # The front key has the oldest newest-failure, so the loop stops at the
        # first live key and pops each key at most once: amortized O(1).
        while self._failures:
            oldest = next(iter(self._failures))
            newest = self._failures[oldest]
            if newest and newest[-1] + self._window > now:
                break
            del self._failures[oldest]
        failures = self._failures.pop(key, deque())
        failures.append(now)
        self._failures[key] = failures  # re-insert: moves the key to the back

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)

    def _live(self, key: str, now: float) -> deque[float]:
        """The key's failures still inside the window (older ones are dropped)."""
        failures = self._failures.get(key, deque())
        while failures and failures[0] + self._window <= now:
            failures.popleft()
        return failures
