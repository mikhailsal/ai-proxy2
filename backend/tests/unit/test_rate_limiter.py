"""Tests for per-provider sliding-window rate limiter."""

import asyncio
import time

import pytest

from ai_proxy.config.settings import RateLimitConfig
from ai_proxy.core.rate_limiter import (
    ProviderRateLimiter,
    build_rate_limiters,
    get_rate_limiter,
    reset_rate_limiters,
)


@pytest.fixture(autouse=True)
def _clean_limiters():
    reset_rate_limiters()
    yield
    reset_rate_limiters()


class TestProviderRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_no_limit(self) -> None:
        limiter = ProviderRateLimiter("test", RateLimitConfig(rpm=0))
        await limiter.acquire()

    @pytest.mark.asyncio
    async def test_acquire_within_limit(self) -> None:
        limiter = ProviderRateLimiter("test", RateLimitConfig(rpm=5))
        for _ in range(5):
            await limiter.acquire()

    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit_waits(self) -> None:
        limiter = ProviderRateLimiter("test", RateLimitConfig(rpm=2))
        await limiter.acquire()
        await limiter.acquire()

        start = time.monotonic()
        task = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0.1)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        elapsed = time.monotonic() - start
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_sliding_window_expires(self) -> None:
        config = RateLimitConfig(rpm=2)
        limiter = ProviderRateLimiter("test", config)

        limiter._timestamps.clear()
        old_time = time.monotonic() - 61
        limiter._timestamps.append(old_time)
        limiter._timestamps.append(old_time + 0.01)

        await limiter.acquire()

    @pytest.mark.asyncio
    async def test_queue_full(self) -> None:
        limiter = ProviderRateLimiter("test", RateLimitConfig(rpm=1, max_queue=2))
        await limiter.acquire()

        tasks = []
        for _ in range(3):
            tasks.append(asyncio.create_task(limiter.acquire()))
        await asyncio.sleep(0.1)

        assert limiter.is_queue_full

        for t in tasks:
            t.cancel()
            with pytest.raises(asyncio.CancelledError):
                await t

    @pytest.mark.asyncio
    async def test_pending_count(self) -> None:
        limiter = ProviderRateLimiter("test", RateLimitConfig(rpm=1))
        assert limiter.pending_count == 0
        await limiter.acquire()

        task = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0.05)
        assert limiter.pending_count == 1

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.05)
        assert limiter.pending_count == 0

    @pytest.mark.asyncio
    async def test_cancellation_decrements_pending(self) -> None:
        limiter = ProviderRateLimiter("test", RateLimitConfig(rpm=1))
        await limiter.acquire()

        task = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0.05)
        assert limiter.pending_count == 1

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.05)
        assert limiter.pending_count == 0


class TestBuildRateLimiters:
    def test_build_with_rpm(self) -> None:
        from ai_proxy.config.settings import ProviderConfig

        providers = {
            "nvidia": ProviderConfig(
                endpoint="https://example.com/v1",
                rate_limit=RateLimitConfig(rpm=40),
            ),
            "openrouter": ProviderConfig(endpoint="https://example.com/v1"),
        }
        build_rate_limiters(providers)
        assert get_rate_limiter("nvidia") is not None
        assert get_rate_limiter("nvidia").rpm == 40
        assert get_rate_limiter("openrouter") is None

    def test_build_preserves_existing_limiter(self) -> None:
        from ai_proxy.config.settings import ProviderConfig

        providers = {
            "nvidia": ProviderConfig(
                endpoint="https://example.com/v1",
                rate_limit=RateLimitConfig(rpm=40),
            ),
        }
        build_rate_limiters(providers)
        first_limiter = get_rate_limiter("nvidia")

        build_rate_limiters(providers)
        assert get_rate_limiter("nvidia") is first_limiter

    def test_build_replaces_on_rpm_change(self) -> None:
        from ai_proxy.config.settings import ProviderConfig

        providers = {
            "nvidia": ProviderConfig(
                endpoint="https://example.com/v1",
                rate_limit=RateLimitConfig(rpm=40),
            ),
        }
        build_rate_limiters(providers)
        first_limiter = get_rate_limiter("nvidia")

        providers["nvidia"] = ProviderConfig(
            endpoint="https://example.com/v1",
            rate_limit=RateLimitConfig(rpm=60),
        )
        build_rate_limiters(providers)
        assert get_rate_limiter("nvidia") is not first_limiter
        assert get_rate_limiter("nvidia").rpm == 60

    def test_build_removes_limiter_when_rpm_cleared(self) -> None:
        from ai_proxy.config.settings import ProviderConfig

        providers = {
            "nvidia": ProviderConfig(
                endpoint="https://example.com/v1",
                rate_limit=RateLimitConfig(rpm=40),
            ),
        }
        build_rate_limiters(providers)
        assert get_rate_limiter("nvidia") is not None

        providers["nvidia"] = ProviderConfig(endpoint="https://example.com/v1")
        build_rate_limiters(providers)
        assert get_rate_limiter("nvidia") is None

    def test_reset(self) -> None:
        from ai_proxy.config.settings import ProviderConfig

        providers = {
            "nvidia": ProviderConfig(
                endpoint="https://example.com/v1",
                rate_limit=RateLimitConfig(rpm=40),
            ),
        }
        build_rate_limiters(providers)
        assert get_rate_limiter("nvidia") is not None

        reset_rate_limiters()
        assert get_rate_limiter("nvidia") is None
