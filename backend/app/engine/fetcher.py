"""三层递进抓取器：httpx → curl_cffi（TLS 指纹）→ playwright（浏览器兜底）。

CONTRACT.md 第 4.3 节。403 不盲目重试直接降级下一层；429/5xx 指数退避重试（最多
config.max_retries 次）；playwright 为 lazy import，未安装/浏览器缺失时抛
``FetcherError`` 并说明原因，不影响 L1/L2 的正常工作。
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.engine.anti_anti import RateLimiter, exponential_backoff
from app.engine.config import EngineConfig

logger = logging.getLogger(__name__)


class FetcherError(Exception):
    """抓取器无法完成请求（如 playwright 未安装、浏览器缺失）。"""


@dataclass
class FetchResult:
    status_code: int
    html: str
    final_url: str
    strategy: str  # "httpx" | "curl_cffi" | "playwright"


class Fetcher:
    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.rate_limiter = RateLimiter(config.rate_limit)
        self._http_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    async def fetch(self, url: str, referer: str | None = None) -> FetchResult:
        """三层递进抓取页面；L1/L2 返回 None 时降级到下一层。"""
        result = await self._fetch_httpx(url, referer)
        if result is not None:
            return result
        result = await self._fetch_curl_cffi(url, referer)
        if result is not None:
            return result
        # L3：playwright 未安装/浏览器缺失时在此抛 FetcherError
        return await self._fetch_playwright(url, referer)

    async def aclose(self) -> None:
        """释放 httpx 连接池（可选调用）。"""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------ #
    # L1 httpx
    # ------------------------------------------------------------------ #
    async def _fetch_httpx(self, url: str, referer: str | None) -> FetchResult | None:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                follow_redirects=True, timeout=self.config.timeout
            )
        headers = self._browser_headers(url, referer)
        for attempt in range(self.config.max_retries + 1):
            await self.rate_limiter.acquire()
            try:
                resp = await self._http_client.get(url, headers=headers)
            except httpx.HTTPError as e:
                logger.warning("[httpx] 请求异常 %s: %s，降级", url, e)
                return None
            if resp.status_code == 403:
                logger.info("[httpx] HTTP 403，不盲目重试，降级 curl_cffi")
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < self.config.max_retries:
                    delay = exponential_backoff(attempt)
                    logger.warning(
                        "[httpx] HTTP %s，%.1fs 后重试(%d/%d)",
                        resp.status_code, delay, attempt + 1, self.config.max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning("[httpx] HTTP %s 重试耗尽，降级", resp.status_code)
                return None
            if 200 <= resp.status_code < 300:
                return FetchResult(resp.status_code, resp.text, str(resp.url), "httpx")
            logger.info("[httpx] HTTP %s，降级 curl_cffi", resp.status_code)
            return None
        return None

    # ------------------------------------------------------------------ #
    # L2 curl_cffi（TLS 指纹模拟）
    # ------------------------------------------------------------------ #
    async def _fetch_curl_cffi(self, url: str, referer: str | None) -> FetchResult | None:
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError as e:
            logger.warning("[curl_cffi] 未安装: %s，降级 playwright", e)
            return None
        headers = self._browser_headers(url, referer)
        for attempt in range(self.config.max_retries + 1):
            await self.rate_limiter.acquire()
            try:
                async with AsyncSession(impersonate="chrome") as session:
                    resp = await session.get(
                        url,
                        headers=headers,
                        timeout=self.config.timeout,
                        allow_redirects=True,
                    )
            except Exception as e:
                logger.warning("[curl_cffi] 请求异常 %s: %s，降级", url, e)
                return None
            if resp.status_code == 403:
                logger.info("[curl_cffi] HTTP 403，降级 playwright")
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < self.config.max_retries:
                    delay = exponential_backoff(attempt)
                    logger.warning(
                        "[curl_cffi] HTTP %s，%.1fs 后重试(%d/%d)",
                        resp.status_code, delay, attempt + 1, self.config.max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning("[curl_cffi] HTTP %s 重试耗尽，降级", resp.status_code)
                return None
            if 200 <= resp.status_code < 300:
                return FetchResult(resp.status_code, resp.text, str(resp.url), "curl_cffi")
            logger.info("[curl_cffi] HTTP %s，降级 playwright", resp.status_code)
            return None
        return None

    # ------------------------------------------------------------------ #
    # L3 playwright（lazy import）
    # ------------------------------------------------------------------ #
    async def _fetch_playwright(self, url: str, referer: str | None) -> FetchResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise FetcherError(
                "playwright 未安装，无法使用 L3 浏览器兜底（请 pip install playwright）"
            ) from e

        headers = self._browser_headers(url, referer)
        ua = headers.pop("User-Agent")
        # 登录态：login_state.json 存在时恢复（由 python -m app.engine.login 生成）
        storage_state: str | None = None
        if self.config.login_state_path:
            state_file = Path(self.config.login_state_path)
            if state_file.is_file():
                storage_state = str(state_file)
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        user_agent=ua,
                        extra_http_headers=headers,
                        storage_state=storage_state,
                        proxy={"server": self.config.proxy} if self.config.proxy else None,
                    )
                    page = await context.new_page()
                    resp = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=int(self.config.timeout * 1000),
                    )
                    html = await page.content()
                    status = resp.status if resp is not None else 200
                    return FetchResult(status, html, page.url, "playwright")
                finally:
                    await browser.close()
        except FetcherError:
            raise
        except Exception as e:
            msg = str(e)
            if "Executable doesn't exist" in msg or "playwright install" in msg:
                raise FetcherError(
                    "playwright 浏览器未安装，无法使用 L3 浏览器兜底"
                    "（请运行 playwright install chromium）"
                ) from e
            raise FetcherError(f"playwright 抓取失败: {e}") from e

    # ------------------------------------------------------------------ #
    # 请求头
    # ------------------------------------------------------------------ #
    def _browser_headers(self, url: str, referer: str | None) -> dict[str, str]:
        ua = random.choice(self.config.user_agents)
        headers = {
            "User-Agent": ua,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Chromium";v="126", "Not.A/Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Referer": referer or "https://www.alibaba.com/",
        }
        # 登录态：config.cookie 由 app.config 从环境变量 / data/cookie.txt 注入
        if self.config.cookie:
            headers["Cookie"] = self.config.cookie
        return headers
