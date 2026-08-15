"""extractor.py 单元测试：detailData 提取、big/normal 优先级、描述 HTML 解析、urljoin。"""
from app.engine.extractor import extract_media, extract_media_from_description
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

    def test_extract_media_from_description(self):
        """desc API 返回的 productHtmlDescription → 提取详情图（含懒加载与协议相对路径）。"""
        desc_html = """
        <DIV id="detail_decorate_root">
          <img src="//sc04.alicdn.com/kf/Habc123.jpg" />
          <img data-src="https://sc04.alicdn.com/kf/Hdef456.jpg" />
          <img src="https://u.alicdn.com/js/5v/esite/img/img-placeholder.png" />
          <video src="https://video.alicdn.com/v/xx.mp4"></video>
          <img src="data:image/png;base64,AAAA" />
        </DIV>
        """
        images, videos = extract_media_from_description(desc_html, SAMPLE_PRODUCT_URL)
        assert images == [
            "https://sc04.alicdn.com/kf/Habc123.jpg",
            "https://sc04.alicdn.com/kf/Hdef456.jpg",
        ]
        assert videos == ["https://video.alicdn.com/v/xx.mp4"]

    def test_extract_media_detail_many_module(self):
        """detailManyImage 模块限定：只取模块内 data-src，src 占位图与模块外 img 不取。"""
        desc_html = """
        <DIV id="detail_decorate_root">
          <DIV module-title="detailSingleImage" class="J_module">
            <IMG src="//u.alicdn.com/js/5v/esite/img/img-placeholder.png"
                 data-src="//sc04.alicdn.com/kf/Hfirst.jpg" />
          </DIV>
          <DIV module-title="detailManyImage" class="J_module">
            <IMG src="//u.alicdn.com/js/5v/esite/img/img-placeholder.png"
                 data-src="//sc04.alicdn.com/kf/Hone.jpg" />
            <IMG src="//sc04.alicdn.com/kf/Htwo.jpg" />
          </DIV>
          <IMG src="//sc04.alicdn.com/kf/Houtside.jpg" />
        </DIV>
        """
        images, videos = extract_media_from_description(desc_html, SAMPLE_PRODUCT_URL)
        # 只取 detailManyImage 内 data-src（Htwo 是 src 非 data-src，不取）；
        # detailSingleImage 与模块外 img 均不取
        assert images == ["https://sc04.alicdn.com/kf/Hone.jpg"]
        assert videos == []

    def test_extract_media_skip_anchor_wrapped(self):
        """a 标签包裹的 img（公司简介/外链图）不提取：直接包裹与间接包裹均跳过，普通 img 正常提取。"""
        desc_html = """
        <DIV id="detail_decorate_root">
          <DIV module-title="detailManyImage" class="J_module">
            <IMG data-src="//sc04.alicdn.com/kf/Hnormal1.jpg" />
            <A href="https://www.alibaba.com/company"><IMG data-src="//sc04.alicdn.com/kf/Hcompany.jpg" /></A>
            <A href="https://www.alibaba.com/"><SPAN><IMG data-src="//sc04.alicdn.com/kf/Hcompany2.jpg" /></SPAN></A>
            <IMG data-src="//sc04.alicdn.com/kf/Hnormal2.jpg" />
          </DIV>
        </DIV>
        """
        images, _ = extract_media_from_description(desc_html, SAMPLE_PRODUCT_URL)
        assert images == [
            "https://sc04.alicdn.com/kf/Hnormal1.jpg",
            "https://sc04.alicdn.com/kf/Hnormal2.jpg",
        ]
