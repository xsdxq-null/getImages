"""downloader.py 单元测试：断点续传、0 字节失败、格式转换（用 monkeypatch 模拟 httpx，不连外网）。"""
import asyncio
import io
from contextlib import asynccontextmanager

import pytest
from PIL import Image

import app.engine.downloader as downloader
from app.engine.downloader import download_media


# ---------------------------------------------------------------------- #
# httpx 模拟
# ---------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        if isinstance(self._payload, (bytes, bytearray)):
            yield bytes(self._payload)
        else:
            for chunk in self._payload:
                yield chunk


class FakeAsyncClient:
    """返回可控响应的 AsyncClient 替身。"""

    response_factory = None

    def __init__(self, *args, **kwargs):
        self._resp = (
            FakeAsyncClient.response_factory()
            if callable(FakeAsyncClient.response_factory)
            else FakeResponse(200, b"default")
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        yield self._resp


@pytest.fixture
def fake_httpx(monkeypatch):
    monkeypatch.setattr(downloader.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------- #
# 用例
# ---------------------------------------------------------------------- #
class TestDownloadMedia:
    def test_download_success(self, tmp_path, fake_httpx):
        FakeAsyncClient.response_factory = lambda: FakeResponse(200, b"hello-bytes")
        result = _run(download_media("https://cdn.example.com/a.jpg", tmp_path, "main_001.jpg"))
        assert result.status == "done"
        assert result.skipped is False
        assert result.size == len(b"hello-bytes")
        target = tmp_path / "main_001.jpg"
        assert target.exists()
        assert target.read_bytes() == b"hello-bytes"

    def test_resume_skips_existing(self, tmp_path):
        """已存在且 size>0 → skipped=True，不触发网络请求（未 patch httpx 也应通过）。"""
        target = tmp_path / "main_001.jpg"
        target.write_bytes(b"existing-data")
        result = _run(download_media("https://cdn.example.com/a.jpg", tmp_path, "main_001.jpg"))
        assert result.status == "done"
        assert result.skipped is True
        assert result.size == len(b"existing-data")
        assert target.read_bytes() == b"existing-data"  # 未被覆盖

    def test_zero_bytes_fails(self, tmp_path, fake_httpx):
        FakeAsyncClient.response_factory = lambda: FakeResponse(200, b"")
        result = _run(download_media("https://cdn.example.com/a.jpg", tmp_path, "main_002.jpg"))
        assert result.status == "failed"
        assert result.error is not None
        assert not (tmp_path / "main_002.jpg").exists()

    def test_http_error_fails(self, tmp_path, fake_httpx):
        FakeAsyncClient.response_factory = lambda: FakeResponse(404, b"")
        result = _run(download_media("https://cdn.example.com/a.jpg", tmp_path, "main_003.jpg"))
        assert result.status == "failed"
        assert "404" in (result.error or "")

    def test_png_converted_to_jpg(self, tmp_path, fake_httpx):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), (255, 0, 0)).save(buf, "PNG")
        FakeAsyncClient.response_factory = lambda: FakeResponse(200, buf.getvalue())
        result = _run(download_media("https://cdn.example.com/a.png", tmp_path, "main_004.jpg"))
        assert result.status == "done"
        assert result.converted is True
        with Image.open(tmp_path / "main_004.jpg") as img:
            assert img.format == "JPEG"

    def test_convert_failure_keeps_original(self, tmp_path, fake_httpx):
        payload = b"<html>not-an-image</html>"
        FakeAsyncClient.response_factory = lambda: FakeResponse(200, payload)
        result = _run(download_media("https://cdn.example.com/a.avif", tmp_path, "main_005.jpg"))
        assert result.status == "done"
        assert result.converted is False
        assert (tmp_path / "main_005.jpg").read_bytes() == payload

    def test_video_kept_as_mp4(self, tmp_path, fake_httpx):
        FakeAsyncClient.response_factory = lambda: FakeResponse(200, b"fake-mp4-bytes")
        result = _run(download_media("https://cdn.example.com/v.mp4", tmp_path, "main_video_01.mp4"))
        assert result.status == "done"
        assert result.converted is False
        assert (tmp_path / "main_video_01.mp4").read_bytes() == b"fake-mp4-bytes"
