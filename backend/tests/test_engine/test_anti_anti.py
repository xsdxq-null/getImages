"""anti_anti.py 单元测试：指数退避值、UA 池、RateLimiter 最小间隔。"""
import asyncio

from app.engine.anti_anti import (
    USER_AGENTS,
    RateLimiter,
    exponential_backoff,
)


class TestExponentialBackoff:
    def test_values(self):
        assert exponential_backoff(0) == 1.0
        assert exponential_backoff(1) == 2.0
        assert exponential_backoff(2) == 4.0
        assert exponential_backoff(3) == 8.0

    def test_custom_base(self):
        assert exponential_backoff(2, base=3.0) == 9.0

    def test_negative_attempt_clamped(self):
        assert exponential_backoff(-1) == 1.0


class TestUserAgents:
    def test_count_and_format(self):
        assert len(USER_AGENTS) >= 5
        for ua in USER_AGENTS:
            assert ua.startswith("Mozilla/5.0")
            assert "Chrome/" in ua or "Edg/" in ua


class TestRateLimiter:
    def test_min_interval_enforced(self):
        async def scenario() -> float:
            limiter = RateLimiter(min_interval=0.05)
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            await limiter.acquire()
            await limiter.acquire()
            return loop.time() - t0

        elapsed = asyncio.run(scenario())
        assert elapsed >= 0.05 - 0.005

    def test_zero_interval_no_sleep(self):
        async def scenario() -> float:
            limiter = RateLimiter(min_interval=0.0)
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            await limiter.acquire()
            await limiter.acquire()
            return loop.time() - t0

        elapsed = asyncio.run(scenario())
        assert elapsed < 0.05
