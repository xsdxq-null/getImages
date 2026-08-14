"""页面媒体提取：detailData JSON + productHtmlDescription 描述 HTML。

CONTRACT.md 第 4.4 节。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import lxml.html

logger = logging.getLogger(__name__)

# window.detailData = {...}
_DETAIL_DATA_RE = re.compile(r"window\.detailData\s*=\s*(\{)")
# 描述 HTML 内内嵌的 mp4 链接（含相对路径与带查询参数的 URL）
_MP4_RE = re.compile(r"([^\s\"'<>\\]+\.mp4[^\s\"'<>\\]*)", re.IGNORECASE)


@dataclass
class MediaSet:
    title: str | None = None
    main_images: list[str] = field(default_factory=list)
    main_videos: list[str] = field(default_factory=list)
    detail_images: list[str] = field(default_factory=list)
    detail_videos: list[str] = field(default_factory=list)


def extract_media(html: str, page_url: str) -> MediaSet:
    """从详情页 HTML 提取四类媒体资源（主图/主图视频/详情图/详情视频）。

    - 主图/主图视频：``window.detailData`` JSON 中 ``product.mediaItems``；
      ``type=="image"`` 取 ``imageUrl.big`` 优先、``normal`` 兜底；
      ``type=="video"`` 取 mp4 视频 URL。
    - 详情图/详情视频：``productHtmlDescription``（lxml 解析）中
      ``<img>`` / ``<video>`` / ``<source>`` / 内嵌 mp4 链接。
    - 相对 URL 一律用 ``page_url`` 补齐（urljoin）。
    """
    if not html:
        return MediaSet()

    data = _extract_detail_data(html)
    if data is None:
        return MediaSet()

    product = data.get("product") or {}
    if not isinstance(product, dict):
        product = {}

    # 标题
    title = None
    for key in ("subject", "title"):
        val = product.get(key)
        if isinstance(val, str) and val.strip():
            title = val.strip()
            break

    # 主图 / 主图视频
    main_images: list[str] = []
    main_videos: list[str] = []
    for item in product.get("mediaItems") or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").lower()
        if item_type == "image":
            src = _extract_image_url(item)
            if src:
                main_images.append(urljoin(page_url, src))
        elif item_type == "video":
            vurl = _extract_video_url(item)
            if vurl:
                main_videos.append(urljoin(page_url, vurl))

    # 详情描述 HTML
    detail_html = _extract_detail_html(product)
    detail_images: list[str] = []
    detail_videos: list[str] = []
    if detail_html:
        detail_images, detail_videos = _extract_from_description(detail_html, page_url)

    return MediaSet(
        title=title,
        main_images=_dedupe(main_images),
        main_videos=_dedupe(main_videos),
        detail_images=_dedupe(detail_images),
        detail_videos=_dedupe(detail_videos),
    )


# ---------------------------------------------------------------------- #
# detailData JSON
# ---------------------------------------------------------------------- #
def _extract_detail_data(html: str) -> dict | None:
    """定位 window.detailData 的 JSON 对象并做括号配平，避免非贪婪截断。"""
    m = _DETAIL_DATA_RE.search(html)
    if not m:
        logger.info("页面中未找到 window.detailData")
        return None
    start = html.index("{", m.start())
    end, depth, in_str, escape = start, 0, False, False
    for i in range(start, len(html)):
        c = html[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                # 统计连续反斜杠，偶数个反斜杠时后续引号才表示字符串结束
                backslashes = 1
                j = i + 1
                while j < len(html) and html[j] == "\\":
                    backslashes += 1
                    j += 1
                escape = backslashes % 2 == 1
                if escape:
                    i = j - 1
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    raw = html[start:end]
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("window.detailData JSON 解析失败: %s", e)
        return None
    return data if isinstance(data, dict) else None


def _extract_image_url(item: dict) -> str | None:
    """mediaItems 中 image 项的 URL：imageUrl.big 优先，normal 兜底。"""
    iu = item.get("imageUrl")
    if isinstance(iu, dict):
        for key in ("big", "normal", "summary", "url"):
            val = iu.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None
    if isinstance(iu, str) and iu.strip():
        return iu.strip()
    return None


def _extract_video_url(item: dict) -> str | None:
    """mediaItems 中 video 项的 mp4 URL（扫描常见字段）。"""
    candidates: list[str] = []
    vu = item.get("videoUrl")
    if isinstance(vu, dict):
        for val in vu.values():
            if isinstance(val, str) and val.strip():
                candidates.append(val.strip())
    elif isinstance(vu, str) and vu.strip():
        candidates.append(vu.strip())
    for key in ("videoSource", "sourceUrl", "playUrl", "source", "url"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())
    for cand in candidates:
        if ".mp4" in cand.lower():
            return cand
    return None


def _extract_detail_html(product: dict) -> str | None:
    """取 product 对象中的描述 HTML（兼容 productHtmlDescription 的常见位置）。"""
    val = product.get("productHtmlDescription")
    if not val:
        detail = product.get("detail")
        if isinstance(detail, dict):
            val = detail.get("productHtmlDescription")
    if isinstance(val, str) and val.strip():
        return val
    return None


# ---------------------------------------------------------------------- #
# 描述 HTML
# ---------------------------------------------------------------------- #
def extract_media_from_description(detail_html: str, page_url: str) -> tuple[list[str], list[str]]:
    """从 desc API 返回的 productHtmlDescription 提取详情图与视频。

    详情图规则：只取 ``module-title="detailManyImage"`` 模块内所有 ``data-src``
    （懒加载真实图；模块的 ``src`` 常为占位图，不采用）。模块缺失/为空时
    退化为通用描述提取（避免漏图）。已去重。
    """
    images = _extract_detail_many_images(detail_html, page_url)
    if images:
        return images, []
    return _extract_from_description(detail_html, page_url)


def _extract_detail_many_images(detail_html: str, page_url: str) -> list[str]:
    """提取 detailManyImage 模块内所有 img 的 data-src（仅 data-src，src 为占位图忽略）。"""
    try:
        tree = lxml.html.fromstring(detail_html)
    except Exception:
        return []
    images: list[str] = []
    for div in tree.xpath(
        "//div[contains(translate(@module-title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'detailmanyimage')]"
    ):
        for img in div.xpath(".//img"):
            src = img.get("data-src")
            if src and _is_usable_url(src):
                images.append(urljoin(page_url, src.strip()))
    return _dedupe(images)


def _extract_from_description(detail_html: str, page_url: str) -> tuple[list[str], list[str]]:
    images: list[str] = []
    videos: list[str] = []

    try:
        tree = lxml.html.fromstring(detail_html)
    except Exception as e:
        logger.warning("描述 HTML 解析失败，退化为正则提取: %s", e)
        tree = None

    if tree is not None:
        # 详情图：<img> src，空则取 data-src / data-original（懒加载兜底）
        for img in tree.xpath("//img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
            )
            if src and _is_usable_url(src):
                images.append(urljoin(page_url, src.strip()))
        # 详情视频：<video src> / <video><source src>
        for video in tree.xpath("//video"):
            src = video.get("src") or video.get("data-src")
            if not src:
                for s in video.xpath(".//source"):
                    src = s.get("src")
                    if src:
                        break
            if src and _is_usable_url(src):
                videos.append(urljoin(page_url, src.strip()))
        # 独立 <source>（未包裹在 video 内）
        for src in tree.xpath("//source/@src"):
            if src and _is_usable_url(src):
                videos.append(urljoin(page_url, src.strip()))

    # 描述内嵌 mp4 链接（相对/绝对）
    for m in _MP4_RE.finditer(detail_html):
        raw = m.group(1).strip()
        if raw.startswith("data:") or raw.startswith("javascript:"):
            continue
        if _is_usable_url(raw) and ".mp4" in raw.lower():
            videos.append(urljoin(page_url, raw))

    return _dedupe(images), _dedupe(videos)


def _is_usable_url(url: str) -> bool:
    """过滤掉 data:/javascript:/ 协议、纯锚点与懒加载占位图。"""
    u = url.strip()
    if not u:
        return False
    if u.startswith(("data:", "javascript:", "#", "about:")):
        return False
    # 懒加载占位图（如 u.alicdn.com/.../img-placeholder.png），非真实商品图
    if any(m in u.lower() for m in ("img-placeholder", "placeholder.png", "placeholder.jpg")):
        return False
    return True


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
