"""测试共享样例（不依赖真实网络）。"""
import json

# 商品详情页 URL（末段纯数字 ≥5 位）
SAMPLE_PRODUCT_URL = "https://www.alibaba.com/product-detail/1234567890.html"

# 构造的样例页面 HTML：含 window.detailData JSON 与 productHtmlDescription
SAMPLE_HTML = """<!DOCTYPE html>
<html><head><title>Sample</title><script>
window.detailData = {
  "product": {
    "subject": "Test Product Title",
    "mediaItems": [
      {"type": "image", "imageUrl": {"normal": "https://cdn.example.com/normal_1.jpg", "big": "https://cdn.example.com/big_1.jpg"}},
      {"type": "image", "imageUrl": {"normal": "https://cdn.example.com/normal_2.jpg"}},
      {"type": "video", "videoUrl": {"mp4": "https://cdn.example.com/main_video_1.mp4"}},
      {"type": "video", "videoSource": "https://cdn.example.com/main_video_2.mp4"}
    ],
    "productHtmlDescription": "<div><img src='//cdn.example.com/detail_1.jpg'/><img data-src='/lazy/detail_2.jpg'/><video src='https://cdn.example.com/detail_video.mp4'></video><source src='/rel/video_extra.mp4'/></div>"
  }
};
</script></head><body></body></html>
"""

# 用户真实页面的 JSON-LD 主图（application/ld+json 数组：Product.image + ImageObject）
SAMPLE_LDJSON_IMAGES = [
    "https://sc04.alicdn.com/kf/H41e384ba28784cfca836c2db0e499f79x.jpg",
    "https://sc04.alicdn.com/kf/H223d82c3b57d43879eb2d92e9f71a9521.jpg",
    "https://sc04.alicdn.com/kf/H763a391a5cec45eeae1107de6e4db74ex.jpg",
    "https://sc04.alicdn.com/kf/H060c2275933442398edb6a448e43a337c.jpg",
    "https://sc04.alicdn.com/kf/H9190d65c51d84cbcadfadc463d3cf4e8c.jpg",
    "https://sc04.alicdn.com/kf/Hb19d9dccc3ce494da4b7bd209bb7c72e4.jpg",
]

SAMPLE_LDJSON_HTML = """<!DOCTYPE html>
<html><head><title>Sample</title><script type="application/ld+json">
[
  {
    "@context": "https://schema.org/",
    "@type": "Product",
    "@id": "1600806431341",
    "name": "Test Product",
    "image": %(images)s,
    "offers": {"@type": "Offer", "priceCurrency": "USD", "price": "12"}
  }%(image_objects)s
]
</script></head><body></body></html>
""" % {
    "images": json.dumps(SAMPLE_LDJSON_IMAGES),
    "image_objects": "".join(
        f',\n  {{"@context": "https://schema.org", "@type": "ImageObject", "contentUrl": "{u}"}}'
        for u in SAMPLE_LDJSON_IMAGES
    ),
}
