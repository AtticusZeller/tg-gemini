"""Tests for RateLimiter."""

import asyncio
import time

import pytest

from tg_gemini.ratelimit import RateLimiter


class TestRateLimiterDisabled:
    def test_allow_when_disabled(self) -> None:
        rl = RateLimiter(max_messages=0)
        assert rl.allow("user1") is True

    def test_allow_multiple_times_when_disabled(self) -> None:
        rl = RateLimiter(max_messages=0)
        for _ in range(100):
            assert rl.allow("user") is True


class TestRateLimiterAllow:
    def test_allow_within_limit(self) -> None:
        rl = RateLimiter(max_messages=3, window_secs=60.0)
        assert rl.allow("u") is True
        assert rl.allow("u") is True
        assert rl.allow("u") is True

    def test_deny_when_exceeded(self) -> None:
        rl = RateLimiter(max_messages=2, window_secs=60.0)
        rl.allow("u")
        rl.allow("u")
        assert rl.allow("u") is False

    def test_multiple_keys_independent(self) -> None:
        rl = RateLimiter(max_messages=1, window_secs=60.0)
        assert rl.allow("a") is True
        assert rl.allow("b") is True
        assert rl.allow("a") is False
        assert rl.allow("b") is False

    def test_window_slides_expire(self) -> None:
        rl = RateLimiter(max_messages=2, window_secs=1.0)
        now = time.monotonic()
        # Manually place an expired timestamp in the bucket
        rl._buckets["u"] = [now - 2.0]  # already expired
        # Should allow since expired entry doesn't count
        assert rl.allow("u") is True
        assert rl.allow("u") is True

    def test_one_expired_one_fresh(self) -> None:
        rl = RateLimiter(max_messages=1, window_secs=1.0)
        now = time.monotonic()
        rl._buckets["u"] = [now - 2.0]  # expired
        # After filtering, bucket is empty → should allow
        assert rl.allow("u") is True

    def test_at_exactly_limit_boundary(self) -> None:
        rl = RateLimiter(max_messages=3, window_secs=60.0)
        for _ in range(3):
            assert rl.allow("u") is True
        assert rl.allow("u") is False


class TestRateLimiterCleanup:
    def test_cleanup_removes_stale_buckets(self) -> None:
        rl = RateLimiter(max_messages=1, window_secs=1.0)
        now = time.monotonic()
        rl._buckets["stale"] = [now - 5.0]  # all expired
        rl._buckets["fresh"] = [now]
        rl._cleanup()
        assert "stale" not in rl._buckets
        assert "fresh" in rl._buckets

    def test_cleanup_keeps_partially_fresh_bucket(self) -> None:
        rl = RateLimiter(max_messages=2, window_secs=10.0)
        now = time.monotonic()
        rl._buckets["u"] = [now - 20.0, now]  # one stale, one fresh
        rl._cleanup()
        # Not removed because one timestamp is still fresh (all() check)
        assert "u" in rl._buckets

    def test_cleanup_empty_buckets_removed(self) -> None:
        rl = RateLimiter(max_messages=1, window_secs=5.0)
        now = time.monotonic()
        rl._buckets["gone"] = [now - 10.0]
        rl._cleanup()
        assert "gone" not in rl._buckets


class TestRateLimiterLifecycle:
    async def test_start_stop(self) -> None:
        rl = RateLimiter(cleanup_interval_secs=100.0)
        await rl.start()
        assert rl._cleanup_task is not None
        assert not rl._cleanup_task.done()
        await rl.stop()
        assert rl._cleanup_task is None

    async def test_stop_without_start(self) -> None:
        rl = RateLimiter()
        await rl.stop()  # should not raise

    async def test_start_idempotent_replacement(self) -> None:
        rl = RateLimiter(cleanup_interval_secs=100.0)
        await rl.start()
        first_task = rl._cleanup_task
        await rl.start()  # second start creates new task
        # First task is still running (no cancellation)
        assert rl._cleanup_task is not first_task
        await rl.stop()
        if first_task and not first_task.done():
            first_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first_task

    async def test_cleanup_loop_runs(self) -> None:
        rl = RateLimiter(max_messages=1, window_secs=1.0, cleanup_interval_secs=0.05)
        now = time.monotonic()
        rl._buckets["stale"] = [now - 5.0]

        await rl.start()
        await asyncio.sleep(0.15)  # let cleanup loop run at least once
        await rl.stop()

        assert "stale" not in rl._buckets


class TestRateLimitConfig:
    def test_defaults(self) -> None:
        from tg_gemini.config import RateLimitConfig

        cfg = RateLimitConfig()
        assert cfg.max_messages == 0
        assert cfg.window_secs == 60.0

    def test_custom(self) -> None:
        from tg_gemini.config import RateLimitConfig

        cfg = RateLimitConfig(max_messages=10, window_secs=30.0)
        assert cfg.max_messages == 10
        assert cfg.window_secs == 30.0

    def test_negative_rejected(self) -> None:
        from pydantic import ValidationError

        from tg_gemini.config import RateLimitConfig

        with pytest.raises(ValidationError):
            RateLimitConfig(max_messages=-1)

    def test_app_config_has_rate_limit(self) -> None:
        from tg_gemini.config import AppConfig, RateLimitConfig, TelegramConfig

        cfg = AppConfig(telegram=TelegramConfig(token="t"))
        assert isinstance(cfg.rate_limit, RateLimitConfig)
        assert cfg.rate_limit.max_messages == 0
