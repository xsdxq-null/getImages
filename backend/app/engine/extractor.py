"""页面媒体提取：detailData JSON + JSON-LD 主图 + productHtmlDescription 描述 HTML。

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

    - 主图/主图视频：``window.detailData`` JSON 中 ``product.mediaItems``
      （兼容新旧两种结构：旧版顶层 ``product``，新版 ``globalData.product``）；
      ``type=="image"`` 取 ``imageUrl.big`` 优先、``normal`` 兜底；
      ``type=="video"`` 取 mp4 视频 URL。
    - 主图补充：``application/ld+json`` 中 ``Product.image``（与 mediaItems 合并去重）。
    - 详情图/详情视频：``productHtmlDescription``（lxml 解析）中
      ``<img>`` / ``<video>`` / ``<source>`` / 内嵌 mp4 链接。
    - 相对 URL 一律用 ``page_url`` 补齐（urljoin）。
    """
    if not html:
        return MediaSet()

    data = _extract_detail_data(html)
    if data is None:
        # detailData 缺失（页面结构变更/被反爬）时，JSON-LD 主图兜底
        return MediaSet(main_images=_extract_ldjson_main_images(html, page_url))

    product = _extract_product(data)

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
    # 新版模块化详情图（nodeMap.module_description）：desc 接口对该类商品返回空，
    # 详情图直接以结构化字段内嵌在 detailData 中
    detail_images = _dedupe(detail_images + _extract_module_description_images(data, page_url))

    return MediaSet(
        title=title,
        main_images=_dedupe(main_images + _extract_ldjson_main_images(html, page_url)),
        main_videos=_dedupe(main_videos),
        detail_images=_dedupe(detail_images),
        detail_videos=_dedupe(detail_videos),
    )


# ---------------------------------------------------------------------- #
# detailData JSON
# ---------------------------------------------------------------------- #
# ---------------------------------------------------------------------- #
# JSON-LD 主图（application/ld+json 中 schema.org Product.image）
# ---------------------------------------------------------------------- #
def _extract_ldjson_main_images(html: str, page_url: str) -> list[str]:
    """从页面 JSON-LD 提取主图（schema.org ``Product.image``）。

    - 解析全部 ``<script type="application/ld+json">`` 块（顶层为对象或数组）；
    - 定位 ``@type`` 含 ``Product`` 的节点（兼容字符串 / 列表写法）；
    - 取 ``image`` 字段（字符串单图或数组多图），urljoin 补齐并去重；
    - 无 Product 节点 / JSON 解析失败时静默返回空列表（不干扰现有主图结果）。
    """
    try:
        tree = lxml.html.fromstring(html)
    except Exception:
        return []
    images: list[str] = []
    for script in tree.xpath('//script[@type="application/ld+json"]'):
        text = (script.text or "").strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict) or not _ldjson_has_type(node.get("@type"), "Product"):
                continue
            image = node.get("image")
            urls = image if isinstance(image, list) else ([image] if image else [])
            for u in urls:
                if isinstance(u, str) and _is_usable_url(u):
                    images.append(urljoin(page_url, u.strip()))
    return _dedupe(images)


def _ldjson_has_type(raw, target: str) -> bool:
    """JSON-LD 节点的 @type 是否包含指定类型（兼容字符串 / 列表）。"""
    types = raw if isinstance(raw, list) else [raw]
    return any(isinstance(t, str) and t.strip().lower() == target.lower() for t in types)


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


def _extract_product(data: dict) -> dict:
    """从 detailData 取 product 数据，兼容新旧两种页面结构。

    - 旧版：``detailData.product``（顶层 product 对象）；
    - 新版（2025+ 模块化页面）：``detailData.globalData.product``。
    """
    product = data.get("product")
    if not isinstance(product, dict) or not product:
        gd = data.get("globalData")
        if isinstance(gd, dict):
            product = gd.get("product")
    return product if isinstance(product, dict) else {}


def _extract_module_description_images(data: dict, page_url: str) -> list[str]:
    """新版模块化详情图：``nodeMap.module_description.privateData`` 中的图片。

    该形态商品 desc 接口返回空（无 productHtmlDescription），详情图以结构化
    字段内嵌在 detailData：``companyInfo.imageSetDetails[].details[].url``
    （公司介绍/工厂/生产流程等分组图）与 ``productDescription.details[].url``
    （产品描述规格图，Ai_Spec_Image）。仅取 ``type=="image"`` 项，urljoin 补齐。
    """
    if not isinstance(data, dict):
        return []
    try:
        node_map = data.get("nodeMap") or {}
        if not isinstance(node_map, dict):
            return []
        mod = node_map.get("module_description") or {}
        private = mod.get("privateData") if isinstance(mod, dict) else None
        if not isinstance(private, dict):
            return []
    except Exception:
        return []

    images: list[str] = []
    for section_key in ("companyInfo", "productDescription"):
        section = private.get(section_key)
        if not isinstance(section, dict):
            continue
        groups = section.get("imageSetDetails")
        if not isinstance(groups, list) or not groups:
            groups = [section]
        for group in groups:
            if not isinstance(group, dict):
                continue
            for item in group.get("details") or []:
                if not isinstance(item, dict) or item.get("type") != "image":
                    continue
                url = item.get("url")
                if isinstance(url, str) and url.strip():
                    images.append(urljoin(page_url, url.strip()))
    return _dedupe(images)


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
    """提取详情图：所有 detailSingleImage 模块 + 第一处 detailManyImage 模块的 data-src。

    - ``detailSingleImage`` 全部模块都取（含顶部 banner，不同商品结构不同，不做位置硬编码）；
    - ``detailManyImage`` **只取第一处**（多处时忽略其余，后续模块多为其他内容图）；
    - 仅取 ``data-src``（``src`` 为懒加载占位图，忽略）；
    - **a 标签包裹的 img 不提取**：img 的祖先链（到所属模块 div 为止）中存在 ``<a>`` 时跳过，
      此类图大概率是公司简介/外链图片（如 ``<a><img></a>`` 或 ``<a><span><img></span></a>``）。
    """
    try:
        tree = lxml.html.fromstring(detail_html)
    except Exception:
        return []
    images: list[str] = []

    def _append(img) -> None:
        src = img.get("data-src")
        if not src or not _is_usable_url(src):
            return
        if _has_anchor_ancestor(img, _module_of(img, tree)):
            return
        images.append(urljoin(page_url, src.strip()))

    # detailSingleImage：全部模块
    for div in tree.xpath(
        "//div[contains(translate(@module-title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'detailsingleimage')]"
    ):
        for img in div.xpath(".//img"):
            _append(img)

    # detailManyImage：只取第一处
    many_divs = tree.xpath(
        "//div[contains(translate(@module-title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'detailmanyimage')]"
    )
    if many_divs:
        for img in many_divs[0].xpath(".//img"):
            _append(img)
    return _dedupe(images)


def _module_of(img, tree) -> object:
    """返回 img 所属的模块 div（向上找到第一个含 module-title 的 div；找不到返回 tree 根）。"""
    node = img.getparent()
    while node is not None:
        if isinstance(node.tag, str) and node.get("module-title"):
            return node
        node = node.getparent()
    return tree


def _has_anchor_ancestor(img, module_div) -> bool:
    """img 的祖先链（到所属模块 div 为止）中是否存在 <a> 标签。"""
    node = img.getparent()
    while node is not None and node is not module_div:
        if isinstance(node.tag, str) and node.tag.lower() == "a":
            return True
        node = node.getparent()
    return False


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
