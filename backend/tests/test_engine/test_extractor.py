"""extractor.py 单元测试：detailData 提取、big/normal 优先级、描述 HTML 解析、urljoin。"""
from app.engine.extractor import extract_media
from tests.test_engine.samples import SAMPLE_HTML, SAMPLE_PRODUCT_URL


class TestExtractMedia:
    def test_title(self):
        ms = extract_media(SAMPLE_HTML, SAMPLE_PRODUCT_URL)
        assert ms.title == "Test Product Title"

    def test_main_images_big_priority(self):
        ms = extract_media(SAMPLE_HTML, SAMPLE_PRODUCT_URL)
        assert ms.main_images == [
            "https://cdn.example.com/big_1.jpg",   # big 优先
            "https://cdn.example.com/normal_2.jpg",  # 无 big 时 normal 兜底
        ]

    def test_main_videos(self):
        ms = extract_media(SAMPLE_HTML, SAMPLE_PRODUCT_URL)
        assert ms.main_videos == [
            "https://cdn.example.com/main_video_1.mp4",
            "https://cdn.example.com/main_video_2.mp4",
        ]

    def test_detail_images_relative_resolved(self):
        ms = extract_media(SAMPLE_HTML, SAMPLE_PRODUCT_URL)
        assert ms.detail_images == [
            "https://cdn.example.com/detail_1.jpg",      # // 协议相对补齐
            "https://www.alibaba.com/lazy/detail_2.jpg", # /lazy 相对补齐
        ]

    def test_detail_videos(self):
        ms = extract_media(SAMPLE_HTML, SAMPLE_PRODUCT_URL)
        assert ms.detail_videos == [
            "https://cdn.example.com/detail_video.mp4",   # <video src>
            "https://www.alibaba.com/rel/video_extra.mp4",  # <source src> 相对补齐
        ]

    def test_empty_html(self):
        ms = extract_media("", SAMPLE_PRODUCT_URL)
        assert ms.title is None
        assert ms.main_images == []
        assert ms.main_videos == []
        assert ms.detail_images == []
        assert ms.detail_videos == []

    def test_no_detail_data(self):
        ms = extract_media("<html><body>no data</body></html>", SAMPLE_PRODUCT_URL)
        assert ms.title is None
        assert ms.main_images == []
