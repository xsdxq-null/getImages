"""constants.py 单元测试：命名规则、商品 ID 提取、URL 列表解析。"""
import pytest

from app.engine.constants import (
    KIND_DETAIL_IMAGE,
    KIND_DETAIL_VIDEO,
    KIND_MAIN_IMAGE,
    KIND_MAIN_VIDEO,
    parse_url_list,
    product_id_from_url,
    resource_filename,
)


class TestResourceFilename:
    def test_main_image(self):
        assert resource_filename(KIND_MAIN_IMAGE, 1) == "main_001.jpg"
        assert resource_filename(KIND_MAIN_IMAGE, 100) == "main_100.jpg"

    def test_detail_image(self):
        assert resource_filename(KIND_DETAIL_IMAGE, 3) == "detail_003.jpg"

    def test_main_video(self):
        assert resource_filename(KIND_MAIN_VIDEO, 1) == "main_video_01.mp4"
        assert resource_filename(KIND_MAIN_VIDEO, 12) == "main_video_12.mp4"

    def test_detail_video(self):
        assert resource_filename(KIND_DETAIL_VIDEO, 2) == "detail_video_02.mp4"

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError):
            resource_filename("unknown_kind", 1)

    def test_zero_index_raises(self):
        with pytest.raises(ValueError):
            resource_filename(KIND_MAIN_IMAGE, 0)


class TestProductIdFromUrl:
    def test_basic(self):
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/1234567890.html"
        ) == "1234567890"

    def test_no_extension(self):
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/1234567890"
        ) == "1234567890"

    def test_min_length_ok(self):
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/12345"
        ) == "12345"

    def test_too_short(self):
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/1234.html"
        ) is None

    def test_slug_prefix(self):
        # 阿里真实链接：/product-detail/<slug>_<productId>.html
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/MyProduct_1234567890.html"
        ) == "1234567890"

    def test_slug_prefix_real_world(self):
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/"
            "6-Styles-Leaf-Tray-Silicone-Mold_1601705630752.html"
        ) == "1601705630752"
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/"
            "LHY-Black-Detachable-Lace-Fake-Collar_1600380474007.html"
            "?spm=a27aq.38837228.2794179700.5.59be7eb7pWlTC9"
        ) == "1600380474007"

    def test_slug_prefix_too_short(self):
        assert product_id_from_url(
            "https://www.alibaba.com/product-detail/MyProduct_1234.html"
        ) is None

    def test_empty_and_invalid(self):
        assert product_id_from_url("") is None
        assert product_id_from_url("not a url") is None
        assert product_id_from_url("https://www.alibaba.com/") is None
        assert product_id_from_url(None) is None


class TestParseUrlList:
    TXT = (
        "https://www.alibaba.com/product-detail/1234567890.html\n"
        "https://www.alibaba.com/product-detail/9876543210.html\n"
    )
    INVALID_TXT = (
        "# 注释行\n"
        "\n"
        "https://www.alibaba.com/product-detail/1234567890.html\n"
        "https://www.alibaba.com/product-detail/1234.html\n"  # id 不足 5 位
        "https://www.example.com/not-a-product\n"
        "not a url\n"
        "ftp://www.alibaba.com/product-detail/5555555555.html\n"
    )
    CSV = (
        "name,url,price\n"
        "A,https://www.alibaba.com/product-detail/1234567890.html,10\n"
        "B,https://www.alibaba.com/product-detail/9876543210.html,20\n"
    )

    def test_txt_one_per_line(self):
        urls = parse_url_list(self.TXT)
        assert urls == [
            "https://www.alibaba.com/product-detail/1234567890.html",
            "https://www.alibaba.com/product-detail/9876543210.html",
        ]

    def test_real_world_slug_urls(self):
        text = (
            "https://www.alibaba.com/product-detail/"
            "6-Styles-Leaf-Tray-Silicone-Mold_1601705630752.html\n"
            "https://www.alibaba.com/product-detail/"
            "LHY-Black-Detachable-Lace-Fake-Collar_1600380474007.html"
            "?spm=a27aq.38837228.2794179700.5.59be7eb7pWlTC9\n"
        )
        assert parse_url_list(text) == [
            "https://www.alibaba.com/product-detail/"
            "6-Styles-Leaf-Tray-Silicone-Mold_1601705630752.html",
            "https://www.alibaba.com/product-detail/"
            "LHY-Black-Detachable-Lace-Fake-Collar_1600380474007.html"
            "?spm=a27aq.38837228.2794179700.5.59be7eb7pWlTC9",
        ]

    def test_invalid_filtered(self):
        urls = parse_url_list(self.INVALID_TXT)
        assert urls == ["https://www.alibaba.com/product-detail/1234567890.html"]

    def test_csv_url_column(self):
        urls = parse_url_list(self.CSV)
        assert urls == [
            "https://www.alibaba.com/product-detail/1234567890.html",
            "https://www.alibaba.com/product-detail/9876543210.html",
        ]

    def test_dedupe_keep_order(self):
        text = (
            "https://www.alibaba.com/product-detail/1234567890.html\n"
            "https://www.alibaba.com/product-detail/9876543210.html\n"
            "https://www.alibaba.com/product-detail/1234567890.html\n"
        )
        assert parse_url_list(text) == [
            "https://www.alibaba.com/product-detail/1234567890.html",
            "https://www.alibaba.com/product-detail/9876543210.html",
        ]

    def test_empty(self):
        assert parse_url_list("") == []
        assert parse_url_list("   \n\n") == []
        assert parse_url_list(None) == []

    def test_csv_header_only(self):
        assert parse_url_list("name,url,price\n") == []
