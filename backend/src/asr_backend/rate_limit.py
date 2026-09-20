"""Rate limits on the sign-in and sign-up routes (#59).

The limiter keeps its counts in this process's memory. That is enough for the
single-instance pilot deploy (#65), but the counts are lost on restart and are
not shared between instances, so a second instance would need a shared store
(Redis or the database) before this can be relied on.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request

from asr_backend.settings import settings

# How many checks between sweeps that drop keys with no hits left in the window.
_SWEEP_EVERY = 1000


class SlidingWindowLimiter:
    """Allows `limit` hits per key in any window of `window_seconds`."""

    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._checks = 0
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Records a hit. Returns None if allowed, else whole seconds until it would be."""
        with self._lock:
            now = self.clock()
            self._checks += 1
            if self._checks % _SWEEP_EVERY == 0:
                self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            self._drop_expired(hits, now)
            if len(hits) >= self.limit:
                return max(1, math.ceil(hits[0] + self.window_seconds - now))
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._checks = 0

    def _drop_expired(self, hits: deque[float], now: float) -> None:
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()

    def _sweep(self, now: float) -> None:
        for key in list(self._hits):
            self._drop_expired(self._hits[key], now)
            if not self._hits[key]:
                del self._hits[key]


class AttemptLimiter:
    """Limits attempts per client IP and, separately, per email.

    The per-IP limit slows one machine trying many accounts; the per-email limit
    slows many machines trying one account. The per-email limit also lets anyone
    who knows an address lock its owner out for a while: an accepted cost, since
    the alternative is unlimited password guessing.
    """

    def __init__(self, per_ip: SlidingWindowLimiter, per_email: SlidingWindowLimiter):
        self.per_ip = per_ip
        self.per_email = per_email

    def enforce(self, request: Request, email: str) -> None:
        """Counts this attempt, or raises 429 with a Retry-After header."""
        waits = [
            wait
            for wait in (
                self.per_ip.hit(client_ip(request)),
                self.per_email.hit(email),
            )
            if wait is not None
        ]
        if waits:
            retry_after = max(waits)
            raise HTTPException(
                status_code=429,
                detail=f"Too many attempts. Try again in {_describe_wait(retry_after)}.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        self.per_ip.reset()
        self.per_email.reset()


def _describe_wait(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} seconds"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def client_ip(request: Request) -> str:
    """The caller's address.

    Behind a reverse proxy every request arrives from the proxy's address, which
    would put all users in one per-IP bucket. With TRUSTED_PROXY_COUNT set to the
    number of proxies in front of the app, the address is taken from that many
    hops from the right of X-Forwarded-For, where our own proxies wrote it. The
    left side is client-supplied and never trusted.
    """
    hops_from_right = settings.trusted_proxy_count
    if hops_from_right > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if len(hops) >= hops_from_right:
            return hops[-hops_from_right]
    return request.client.host if request.client else "unknown"


# /login and the invitation accept-login share one budget, and /register and
# accept-register share another, so the second route is not a way around the first.
login_attempts = AttemptLimiter(
    per_ip=SlidingWindowLimiter(limit=30, window_seconds=5 * 60),
    per_email=SlidingWindowLimiter(limit=10, window_seconds=15 * 60),
)
register_attempts = AttemptLimiter(
    per_ip=SlidingWindowLimiter(limit=10, window_seconds=60 * 60),
    per_email=SlidingWindowLimiter(limit=5, window_seconds=60 * 60),
)


def reset_all() -> None:
    login_attempts.reset()
    register_attempts.reset()
