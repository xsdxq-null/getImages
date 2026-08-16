"""fetcher.py 单元测试：三层递进与降级逻辑（monkeypatch 各层，不连外网、不依赖 playwright）。"""
import asyncio

import pytest

from app.engine.config import EngineConfig
from app.engine.fetcher import Fetcher, FetcherError, FetchResult, _is_intercept_page

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

    def test_httpx_intercept_page_degrades_to_curl_cffi(self, monkeypatch):
        """L1 返回 HTTP 200 但为登录墙页（rgv587）→ 内容级识别后降级 L2。"""
        wall = (
            '<a id="a-link"></a><script>'
            'localStorage.x5referer=window.location.href;'
            'window._config_={"action": "login"};'
            'host="https://login.alibaba.com/newlogin/icbuLogin.htm?return_url=";'
            "</script><!--rgv587_flag:sm-->"
        )

        async def fake_httpx(self, url, referer=None):
            return FetchResult(200, wall, url, "httpx")

        async def fake_curl(self, url, referer=None):
            return FetchResult(
                200, '<script>window.detailData = {"product": {}}</script>', url, "curl_cffi"
            )

        monkeypatch.setattr(Fetcher, "_fetch_httpx", fake_httpx)
        monkeypatch.setattr(Fetcher, "_fetch_curl_cffi", fake_curl)
        f = Fetcher(EngineConfig())
        result = _run(f.fetch(URL))
        assert result.strategy == "curl_cffi"
        assert "window.detailData" in result.html

    def test_httpx_real_page_no_degrade(self, monkeypatch):
        """L1 返回真实商品页（含 window.detailData）→ 不降级，直接返回。"""
        async def fake_httpx(self, url, referer=None):
            return FetchResult(
                200, '<script>window.detailData = {"product": {}}</script>', url, "httpx"
            )

        monkeypatch.setattr(Fetcher, "_fetch_httpx", fake_httpx)
        f = Fetcher(EngineConfig())
        result = _run(f.fetch(URL))
        assert result.strategy == "httpx"
        assert "window.detailData" in result.html

    def test_curl_cffi_intercept_page_degrades_to_playwright(self, monkeypatch):
        """L2 也返回拦截页时继续降级 L3（playwright）。"""
        wall = '<script>rgv587_flag:sm login.alibaba.com "action": "login"</script>'

        async def fake_httpx(self, url, referer=None):
            return FetchResult(200, wall, url, "httpx")

        async def fake_curl(self, url, referer=None):
            return FetchResult(200, wall, url, "curl_cffi")

        async def fake_pw(self, url, referer=None):
            return FetchResult(200, "<html>pw</html>", url, "playwright")

        monkeypatch.setattr(Fetcher, "_fetch_httpx", fake_httpx)
        monkeypatch.setattr(Fetcher, "_fetch_curl_cffi", fake_curl)
        monkeypatch.setattr(Fetcher, "_fetch_playwright", fake_pw)
        f = Fetcher(EngineConfig())
        result = _run(f.fetch(URL))
        assert result.strategy == "playwright"

    def test_is_intercept_page_real_page_not_false_positive(self):
        """真实商品页即使含 login.alibaba.com 字样（页脚/JS 配置）也不误判为拦截页。"""
        html = (
            '<script>window.detailData = {"globalData": {"product": {}}}</script>'
            '<a href="https://login.alibaba.com/newlogin/icbuLogin.htm">login</a>'
        )
        assert _is_intercept_page(html) is False

    def test_is_intercept_page_login_wall(self):
        """登录墙页（无 detailData + 多特征）识别为拦截页。"""
        html = '<script>rgv587_flag:sm "action": "login" login.alibaba.com</script>'
        assert _is_intercept_page(html) is True

    def test_is_intercept_page_desc_json_not_matched(self):
        """desc 接口 JSON 响应（无拦截特征）不判定为拦截页。"""
        html = '{"data": {"productHtmlDescription": "<p>desc</p>"}, "success": true}'
        assert _is_intercept_page(html) is False
