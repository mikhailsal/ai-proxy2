"""Per-provider sliding-window rate limiter with async request queuing.

When a provider has a configured RPM limit, incoming requests that would
exceed the limit are held in an async queue until a slot opens up.  This
avoids rejecting clients with 429s for a rate limit that is *ours*, not
theirs — instead they simply experience slightly higher latency.
"""

import asyncio
import time
from collections import deque

import structlog

from ai_proxy.config.settings import RateLimitConfig

logger = structlog.get_logger()

_limiters: dict[str, "ProviderRateLimiter"] = {}


class ProviderRateLimiter:
    """Sliding-window RPM limiter with bounded async waiting."""

    def __init__(self, provider_name: str, config: RateLimitConfig) -> None:
        self.provider_name = provider_name
        self.rpm: int = config.rpm or 0
        self.max_queue: int = config.max_queue
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._pending: int = 0

    async def acquire(self) -> None:
        """Wait until a request slot is available within the RPM window."""
        if self.rpm <= 0:
            return

        async with self._lock:
            self._pending += 1

        try:
            while True:
                async with self._lock:
                    now = time.monotonic()
                    window_start = now - 60.0

                    while self._timestamps and self._timestamps[0] <= window_start:
                        self._timestamps.popleft()

                    if len(self._timestamps) < self.rpm:
                        self._timestamps.append(now)
                        self._pending -= 1
                        return

                    # Calculate wait time until oldest request exits the window
                    wait_seconds = self._timestamps[0] - window_start
                    wait_seconds = max(wait_seconds, 0.05)

                logger.debug(
                    "rate_limiter_waiting",
                    provider=self.provider_name,
                    wait_seconds=round(wait_seconds, 2),
                    active_in_window=len(self._timestamps),
                    pending=self._pending,
                )
                await asyncio.sleep(wait_seconds)
        except BaseException:
            async with self._lock:
                self._pending -= 1
            raise

    @property
    def is_queue_full(self) -> bool:
        return self._pending > self.max_queue

    @property
    def pending_count(self) -> int:
        return self._pending


def get_rate_limiter(provider_name: str) -> "ProviderRateLimiter | None":
    return _limiters.get(provider_name)


def build_rate_limiters(providers: dict) -> None:
    """Build rate limiter instances from provider configs.

    Called during startup and config hot-reload.
    """
    global _limiters
    new_limiters: dict[str, ProviderRateLimiter] = {}

    for name, prov_config in providers.items():
        rate_cfg = prov_config.rate_limit
        if rate_cfg.rpm and rate_cfg.rpm > 0:
            if name in _limiters and _limiters[name].rpm == rate_cfg.rpm:
                new_limiters[name] = _limiters[name]
            else:
                new_limiters[name] = ProviderRateLimiter(name, rate_cfg)
                logger.info(
                    "rate_limiter_configured",
                    provider=name,
                    rpm=rate_cfg.rpm,
                    max_queue=rate_cfg.max_queue,
                )

    _limiters = new_limiters


def reset_rate_limiters() -> None:
    global _limiters
    _limiters = {}
