"""阿里巴巴国际站商品抓取引擎 · 常量与命名规则。

字段/签名以 CONTRACT.md 第 4.1 节为准。
"""
from __future__ import annotations

import csv
import re
from urllib.parse import urlsplit

# 四类媒体资源的 kind 常量（与数据库 resources.kind 取值一致）
KIND_MAIN_IMAGE = "main_image"
KIND_DETAIL_IMAGE = "detail_image"
KIND_MAIN_VIDEO = "main_video"
KIND_DETAIL_VIDEO = "detail_video"

# kind → 落盘文件名前缀（见 CONTRACT 第 7 节目录命名规则；
# image 拼 "_NNN.jpg"，video 拼 "_video_NN.mp4"，故 video 前缀同为 main/detail）
_KIND_PREFIXES = {
    KIND_MAIN_IMAGE: "main",
    KIND_DETAIL_IMAGE: "detail",
    KIND_MAIN_VIDEO: "main",
    KIND_DETAIL_VIDEO: "detail",
}

_IMAGE_KINDS = {KIND_MAIN_IMAGE, KIND_DETAIL_IMAGE}
_VIDEO_KINDS = {KIND_MAIN_VIDEO, KIND_DETAIL_VIDEO}

_PRODUCT_ID_RE = re.compile(r"^\d{5,}$")


def resource_filename(kind: str, index: int) -> str:
    """按 kind 与序号生成落盘文件名。

    - main_image/detail_image：``f"{prefix}_{index:03d}.jpg"``（main_001.jpg / detail_001.jpg）
    - main_video/detail_video：``f"{prefix}_video_{index:02d}.mp4"``（main_video_01.mp4 / detail_video_01.mp4）
    """
    prefix = _KIND_PREFIXES.get(kind)
    if prefix is None:
        raise ValueError(f"未知资源 kind: {kind!r}")
    if index < 1:
        raise ValueError(f"资源序号必须从 1 开始，收到 {index}")
    if kind in _IMAGE_KINDS:
        return f"{prefix}_{index:03d}.jpg"
    return f"{prefix}_video_{index:02d}.mp4"


def product_id_from_url(url: str) -> str | None:
    """从商品详情页 URL 提取商品 ID：URL 末段纯数字（至少 5 位）。

    兼容阿里巴巴国际站两种真实链接格式：
    - ``https://www.alibaba.com/product-detail/1234567890.html``（纯数字末段）
    - ``https://www.alibaba.com/product-detail/MyProduct_1234567890.html``（``<slug>_<id>`` 末段）
    末段会先去掉扩展名再判定；不满足（如不含纯数字段、不足 5 位）返回 None。
    """
    if not url or not isinstance(url, str):
        return None
    try:
        path = urlsplit(url).path.rstrip("/")
    except ValueError:
        return None
    if not path:
        return None
    last = path.split("/")[-1]
    # 去掉扩展名（如 .html / .htm），再判定是否为纯数字
    if "." in last:
        stem = last.split(".")[0]
    else:
        stem = last
    if _PRODUCT_ID_RE.fullmatch(stem):
        return stem
    # 兼容 <slug>_<productId> 格式：取 "_" 之后的纯数字段
    if "_" in stem:
        tail = stem.rsplit("_", 1)[1]
        if _PRODUCT_ID_RE.fullmatch(tail):
            return tail
    return None


def _is_valid_product_url(url: str) -> bool:
    """判定 URL 是否为可抓取的合法商品详情页链接。"""
    return (url.startswith("http://") or url.startswith("https://")) and (
        product_id_from_url(url) is not None
    )


def parse_url_list(text: str) -> list[str]:
    """解析 URL 列表文本（txt 每行一个 / csv 含 url 列）。

    - csv：若表头含 ``url`` 列（不区分大小写）则取该列，跳过表头；
    - txt：整行作为一个 URL；
    - 剔除空白行、``#`` 注释行与非法 URL（非 http(s) 或无法提取商品 ID）；
    - 去重且保持首次出现顺序。
    """
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    if not lines:
        return []

    # 尝试按 CSV 解析，探测表头中的 url 列
    url_col: int | None = None
    rows: list[list[str]] = []
    try:
        rows = list(csv.reader(lines))
    except Exception:  # csv 解析异常则退化为逐行文本
        rows = [[ln] for ln in lines]

    if rows:
        header = rows[0]
        for i, cell in enumerate(header):
            if cell.strip().lower() == "url":
                url_col = i
                break

    urls: list[str] = []
    seen: set[str] = set()
    for row_idx, row in enumerate(rows):
        # 存在 url 列时，表头行本身跳过
        if url_col is not None and row_idx == 0:
            continue
        if url_col is not None:
            if url_col >= len(row):
                continue
            candidate = row[url_col].strip()
        else:
            candidate = (row[0] if row else "").strip()
        if not candidate:
            continue
        if candidate in seen:
            continue
        if not _is_valid_product_url(candidate):
            continue
        seen.add(candidate)
        urls.append(candidate)
    return urls
