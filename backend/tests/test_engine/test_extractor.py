"""extractor.py 单元测试：detailData 提取、big/normal 优先级、描述 HTML 解析、urljoin。"""
import json

from app.engine.extractor import extract_media, extract_media_from_description
from tests.test_engine.samples import (
    SAMPLE_HTML,
    SAMPLE_LDJSON_HTML,
    SAMPLE_LDJSON_IMAGES,
    SAMPLE_PRODUCT_URL,
)


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

    def test_globaldata_product_path(self):
        """新版模块化页面：detailData.globalData.product.mediaItems 提取主图/视频/标题。"""
        html = """
        <script>window.detailData = {"globalData": {"product": {
          "subject": "新版商品标题",
          "mediaItems": [
            {"type": "image", "imageUrl": {"big": "https://sc04.alicdn.com/kf/Hone.jpg",
                                           "normal": "https://sc04.alicdn.com/kf/Hone.jpg_120x120.jpg"}},
            {"type": "image", "imageUrl": {"normal": "https://sc04.alicdn.com/kf/Htwo.jpg"}},
            {"type": "video", "videoSource": "https://video.alicdn.com/v/main.mp4"}
          ]
        }}};</script>
        """
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.title == "新版商品标题"
        assert ms.main_images == [
            "https://sc04.alicdn.com/kf/Hone.jpg",
            "https://sc04.alicdn.com/kf/Htwo.jpg",
        ]
        assert ms.main_videos == ["https://video.alicdn.com/v/main.mp4"]

    def test_globaldata_empty_falls_back_to_legacy(self):
        """新版 globalData.product 为空时，回退旧版顶层 product（不丢失数据）。"""
        html = """
        <script>window.detailData = {
          "globalData": {"product": {}},
          "product": {"subject": "旧版标题", "mediaItems": [
            {"type": "image", "imageUrl": {"big": "https://sc04.alicdn.com/kf/Hlegacy.jpg"}}
          ]}
        };</script>
        """
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.title == "旧版标题"
        assert ms.main_images == ["https://sc04.alicdn.com/kf/Hlegacy.jpg"]

    def test_module_description_detail_images(self):
        """新版模块化详情（desc 接口为空）：nodeMap.module_description.privateData 提取详情图。"""
        html = """
        <script>window.detailData = {
          "globalData": {"product": {"subject": "模块化商品",
            "mediaItems": [{"type": "image", "imageUrl": {"big": "https://sc04.alicdn.com/kf/Hmain.jpg"}}]}},
          "nodeMap": {"module_description": {"privateData": {
            "companyInfo": {"title": "公司介绍", "imageSetDetails": [
              {"details": [
                {"type": "image", "url": "https://sc04.alicdn.com/kf/Hcompany1.jpg"},
                {"type": "text", "text": "介绍文字"},
                {"type": "image", "url": "//sc04.alicdn.com/kf/Hcompany2.jpg"}]},
              {"details": [{"type": "image", "url": "https://sc04.alicdn.com/kf/Hfactory1.jpg"}]}
            ]},
            "productDescription": {"title": "Product Description", "details": [
              {"type": "text", "text": "描述文字"},
              {"type": "image", "url": "https://sc04.alicdn.com/kf/Hspec1.jpg"}
            ]}
          }}}
        };</script>
        """
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.detail_images == [
            "https://sc04.alicdn.com/kf/Hcompany1.jpg",
            "https://sc04.alicdn.com/kf/Hcompany2.jpg",
            "https://sc04.alicdn.com/kf/Hfactory1.jpg",
            "https://sc04.alicdn.com/kf/Hspec1.jpg",
        ]

    def test_module_description_missing_safe(self):
        """无 module_description 模块时详情图不受影响、不报错。"""
        html = """
        <script>window.detailData = {
          "globalData": {"product": {"subject": "普通商品", "mediaItems": [
            {"type": "image", "imageUrl": {"big": "https://sc04.alicdn.com/kf/Hmain.jpg"}}]}},
          "nodeMap": {}
        };</script>
        """
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.main_images == ["https://sc04.alicdn.com/kf/Hmain.jpg"]
        assert ms.detail_images == []

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
        """详情图 = 全部 detailSingleImage + 第一处 detailManyImage 的 data-src；src 占位图/模块外不取。"""
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
        # 全部 single 的 data-src + 第一处 many 的 data-src（Htwo 是 src 不取）；模块外不取
        assert images == [
            "https://sc04.alicdn.com/kf/Hfirst.jpg",
            "https://sc04.alicdn.com/kf/Hone.jpg",
        ]
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


class TestExtractMediaJsonLd:
    """JSON-LD（application/ld+json 中 schema.org Product.image）主图提取。"""

    def test_main_images_from_ldjson(self):
        """无 detailData 时，JSON-LD Product.image 数组作为主图来源。"""
        ms = extract_media(SAMPLE_LDJSON_HTML, SAMPLE_PRODUCT_URL)
        assert ms.main_images == SAMPLE_LDJSON_IMAGES

    def test_merge_with_media_items_dedupe(self):
        """detailData mediaItems 与 JSON-LD 主图合并去重：mediaItems 优先、JSON-LD 补充。"""
        html = """
        <script>window.detailData = {"product": {"mediaItems": [
          {"type": "image", "imageUrl": {"big": "%s"}},
          {"type": "image", "imageUrl": {"normal": "https://cdn.example.com/extra.jpg"}}
        ]}};</script>
        <script type="application/ld+json">%s</script>
        """ % (
            SAMPLE_LDJSON_IMAGES[0],
            '{"@type": "Product", "image": ' + json.dumps(SAMPLE_LDJSON_IMAGES) + "}",
        )
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        # mediaItems 2 张在前 + JSON-LD 6 张中仅去重掉重复的 1 张 → 共 7 张
        assert ms.main_images == [
            SAMPLE_LDJSON_IMAGES[0],
            "https://cdn.example.com/extra.jpg",
            *SAMPLE_LDJSON_IMAGES[1:],
        ]

    def test_type_as_list(self):
        """@type 为列表（["Product", "Thing"]）时同样识别为商品节点。"""
        html = """
        <script type="application/ld+json">{"@type": ["Product", "Thing"],
          "image": ["https://sc04.alicdn.com/kf/Hone.jpg", "https://sc04.alicdn.com/kf/Htwo.jpg"]}</script>
        """
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.main_images == [
            "https://sc04.alicdn.com/kf/Hone.jpg",
            "https://sc04.alicdn.com/kf/Htwo.jpg",
        ]

    def test_image_as_string(self):
        """image 字段为单字符串（单图）时正常提取。"""
        html = """
        <script type="application/ld+json">{"@type": "Product", "image": "//sc04.alicdn.com/kf/Hsingle.jpg"}</script>
        """
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.main_images == ["https://sc04.alicdn.com/kf/Hsingle.jpg"]

    def test_no_product_node(self):
        """页面仅含非 Product 类型（如 BreadcrumbList）时，主图为空且不报错。"""
        html = """
        <script type="application/ld+json">[{"@type": "BreadcrumbList", "itemListElement": []}]</script>
        """
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.main_images == []

    def test_invalid_json_ignored(self):
        """ld+json 内容非法时不抛异常，主图结果不受影响。"""
        html = '<script type="application/ld+json">not json{{{</script>'
        ms = extract_media(html, SAMPLE_PRODUCT_URL)
        assert ms.main_images == []
