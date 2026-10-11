"""Failed-login rate limiting (in-process, sliding window).

A client is blocked after MAX_FAILURES failed logins within WINDOW_SECONDS, counted per client
address and per username separately, so guessing one account from many addresses and trying many
accounts from one address are both slowed. A successful login clears the username's count.
State lives in this process only: with several server workers each has its own counts, so run one
worker or add a shared store (for example Redis) before scaling out.
"""
import os
import threading
import time
from collections import deque

MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
WINDOW_SECONDS = float(os.getenv("LOGIN_WINDOW_SECONDS", "900"))

_lock = threading.Lock()
_failures: dict[str, deque[float]] = {}


def _recent(key: str, now: float) -> deque[float]:
    events = _failures.setdefault(key, deque())
    while events and now - events[0] > WINDOW_SECONDS:
        events.popleft()
    return events


def retry_after(keys: list[str]) -> int:
    """Seconds until one of the keys may try again, or 0 if none is blocked."""
    now = time.monotonic()
    with _lock:
        waits = []
        for key in keys:
            events = _recent(key, now)
            if len(events) >= MAX_FAILURES:
                waits.append(int(WINDOW_SECONDS - (now - events[0])) + 1)
        return max(waits, default=0)


def record_failure(keys: list[str]) -> None:
    now = time.monotonic()
    with _lock:
        for key in keys:
            _recent(key, now).append(now)


def clear(keys: list[str]) -> None:
    with _lock:
        for key in keys:
            _failures.pop(key, None)


def reset() -> None:
    """For tests only."""
    with _lock:
        _failures.clear()
