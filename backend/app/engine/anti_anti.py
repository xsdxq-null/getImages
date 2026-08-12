"""反爬应对：UA 池、指数退避、全局限速。CONTRACT.md 第 4.2 节。"""
from __future__ import annotations

import asyncio
import random

# ≥5 条真实 Chrome/Edge 桌面 UA
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def exponential_backoff(attempt: int, base: float = 2.0) -> float:
    """指数退避间隔：``base ** attempt`` 秒（2^0=1s, 2^1=2s, 2^2=4s…）。"""
    return base ** max(attempt, 0)


def random_user_agent() -> str:
    """随机选取一条 UA。"""
    return random.choice(USER_AGENTS)


class RateLimiter:
    """全局最小间隔限速器（asyncio）。

    保证任意两次 ``acquire()`` 返回之间的时间间隔不小于 ``min_interval`` 秒；
    通过锁保证并发安全。
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            loop_time = asyncio.get_running_loop().time()
            wait = self.min_interval - (loop_time - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
                loop_time = asyncio.get_running_loop().time()
            self._last = loop_time
