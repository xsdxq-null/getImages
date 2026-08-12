"""测试共享样例（不依赖真实网络）。"""

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
