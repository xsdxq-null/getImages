"""crawler.py 单元测试：完整流水线、manifest 生成、单资源失败不中断。"""
import asyncio
import json
from pathlib import Path

from app.engine.crawler import crawl_product
from app.engine.downloader import DownloadResult
from app.engine.fetcher import FetcherError, FetchResult
from tests.test_engine.samples import SAMPLE_HTML

VALID_URL = "https://www.alibaba.com/product-detail/1234567890.html"


def _run(coro):
    return asyncio.run(coro)


class FakeFetcher:
    def __init__(self, html=SAMPLE_HTML, status=200):
        self._html = html
        self._status = status

    async def fetch(self, url, referer=None):
        return FetchResult(self._status, self._html, url, "httpx")


async def _fake_download_ok(url, dest_dir, filename, referer=None):
    p = Path(dest_dir) / filename
    p.write_bytes(b"x")
    return DownloadResult(str(p), 1, "done", False, False, None)


async def _fake_download_fail(url, dest_dir, filename, referer=None):
    p = Path(dest_dir) / filename
    return DownloadResult(str(p), 0, "failed", False, False, "simulated failure")


class TestCrawlProduct:
    def test_full_pipeline_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.engine.crawler.download_media", _fake_download_ok)
        result = _run(crawl_product(FakeFetcher(), VALID_URL, tmp_path))

        assert result.success is True
        assert result.product_id == "1234567890"
        assert result.title == "Test Product Title"
        assert result.error is None
        assert len(result.resources) == 8  # 2 主图 + 2 详情图 + 2 主视 + 2 详情视
        assert all(r["status"] == "done" for r in result.resources)
        assert result.resources[0]["kind"] == "main_image"

        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["product_id"] == "1234567890"
        assert manifest["title"] == "Test Product Title"
        assert manifest["status"] == "done"
        assert manifest["main_images"] == ["main_001.jpg", "main_002.jpg"]
        assert manifest["detail_images"] == ["detail_001.jpg", "detail_002.jpg"]
        assert manifest["main_videos"] == ["main_video_01.mp4", "main_video_02.mp4"]
        assert manifest["detail_videos"] == ["detail_video_01.mp4", "detail_video_02.mp4"]
        assert "fetched_at" in manifest
        assert "url" in manifest

    def test_resource_failure_not_interrupting(self, tmp_path, monkeypatch):
        """全部资源失败 → manifest status=partial，但 CrawlResult.success 仍为 True（主流程完成）。"""
        monkeypatch.setattr("app.engine.crawler.download_media", _fake_download_fail)
        result = _run(crawl_product(FakeFetcher(), VALID_URL, tmp_path))

        assert result.success is True
        assert len(result.resources) == 8
        assert all(r["status"] == "failed" for r in result.resources)

        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "partial"
        assert manifest["main_images"] == []

    def test_fetch_error(self, tmp_path, monkeypatch):
        class BadFetcher(FakeFetcher):
            async def fetch(self, url, referer=None):
                raise FetcherError("playwright 浏览器未安装，无法使用 L3")

        result = _run(crawl_product(BadFetcher(), VALID_URL, tmp_path))
        assert result.success is False
        assert result.error is not None
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "failed"

    def test_http_error(self, tmp_path, monkeypatch):
        result = _run(crawl_product(FakeFetcher(html="", status=403), VALID_URL, tmp_path))
        assert result.success is False
        assert "403" in (result.error or "")

    def test_anti_bot_redirect_page_failed(self, tmp_path, monkeypatch):
        """反爬跳转页（200 但无商品数据）→ 内容级检测标记失败而非虚假成功。"""
        redirect_html = """
        <html><body>
          <a id="a-link"></a>
          <script>var link = document.getElementById("a-link");
          link.href = "/verify";</script>
        </body></html>
        """
        result = _run(
            crawl_product(FakeFetcher(html=redirect_html, status=200), VALID_URL, tmp_path)
        )
        assert result.success is False
        assert result.error is not None
        assert "未提取到商品数据" in (result.error or "")
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "failed"

    def test_title_without_media_failed(self, tmp_path, monkeypatch):
        """页面有标题但四类资源全空 → 标记失败而非虚假 done。"""
        title_only_html = """
        <html><head><title>Some Product</title></head><body>
        <script>
        window.detailData = {"product": {"subject": "Some Product",
          "mediaItems": [], "productHtmlDescription": "<p>no media</p>"}};
        </script>
        </body></html>
        """
        result = _run(
            crawl_product(FakeFetcher(html=title_only_html, status=200), VALID_URL, tmp_path)
        )
        assert result.success is False
        assert result.error is not None
        assert "未提取到任何媒体资源" in (result.error or "")
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "failed"
        assert manifest["title"] == "Some Product"

    def test_invalid_url(self, tmp_path, monkeypatch):
        result = _run(
            crawl_product(
                FakeFetcher(), "https://www.example.com/not-a-product", tmp_path
            )
        )
        assert result.success is False
        assert result.product_id == ""
        assert result.error is not None
