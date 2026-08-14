"""fetcher.py 单元测试：三层递进与降级逻辑（monkeypatch 各层，不连外网、不依赖 playwright）。"""
import asyncio

import pytest

from app.engine.config import EngineConfig
from app.engine.fetcher import Fetcher, FetcherError, FetchResult

URL = "https://www.alibaba.com/product-detail/1234567890.html"


def _run(coro):
    return asyncio.run(coro)


class TestFetcher:
    def test_httpx_success(self, monkeypatch):
        async def fake_httpx(self, url, referer=None):
            return FetchResult(200, "<html>ok</html>", url, "httpx")

        monkeypatch.setattr(Fetcher, "_fetch_httpx", fake_httpx)
        f = Fetcher(EngineConfig())
        result = _run(f.fetch(URL))
        assert result.strategy == "httpx"
        assert result.status_code == 200
        assert result.html == "<html>ok</html>"

    def test_degrade_403_to_curl_cffi(self, monkeypatch):
        """L1 返回 None（403 降级信号）→ L2 成功。"""
        async def fake_httpx(self, url, referer=None):
            return None

        async def fake_curl(self, url, referer=None):
            return FetchResult(200, "<html>curl</html>", url, "curl_cffi")

        monkeypatch.setattr(Fetcher, "_fetch_httpx", fake_httpx)
        monkeypatch.setattr(Fetcher, "_fetch_curl_cffi", fake_curl)
        f = Fetcher(EngineConfig())
        result = _run(f.fetch(URL))
        assert result.strategy == "curl_cffi"

    def test_all_layers_fail_raises_fetcher_error(self, monkeypatch):
        """L1/L2 均降级、L3 playwright 不可用时抛 FetcherError。"""
        async def fake_httpx(self, url, referer=None):
            return None

        async def fake_curl(self, url, referer=None):
            return None

        async def fake_pw(self, url, referer=None):
            raise FetcherError("playwright 浏览器未安装，无法使用 L3")

        monkeypatch.setattr(Fetcher, "_fetch_httpx", fake_httpx)
        monkeypatch.setattr(Fetcher, "_fetch_curl_cffi", fake_curl)
        monkeypatch.setattr(Fetcher, "_fetch_playwright", fake_pw)
        f = Fetcher(EngineConfig())
        with pytest.raises(FetcherError):
            _run(f.fetch(URL))

    def test_rate_limiter_used(self, monkeypatch):
        """Fetcher 默认携带 rate_limit=2.0 的限速器。"""
        f = Fetcher(EngineConfig())
        assert f.rate_limiter.min_interval == 2.0

    def test_cookie_in_headers(self):
        """配置了登录 cookie 时，请求头自动携带 Cookie（供 httpx/curl_cffi）。"""
        f = Fetcher(EngineConfig(cookie="a=1; b=2"))
        headers = f._browser_headers(URL, referer=None)
        assert headers.get("Cookie") == "a=1; b=2"

    def test_no_cookie_by_default(self):
        """未配置 cookie 时请求头不含 Cookie（保持原有行为）。"""
        f = Fetcher(EngineConfig())
        assert "Cookie" not in f._browser_headers(URL, referer=None)
