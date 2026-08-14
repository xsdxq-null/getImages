"""单商品抓取流水线：fetch → extract → 逐资源下载 → manifest.json。

CONTRACT.md 第 4.6 节（调度器唯一入口）。单资源失败不中断整体流程。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.engine.constants import (
    KIND_DETAIL_IMAGE,
    KIND_DETAIL_VIDEO,
    KIND_MAIN_IMAGE,
    KIND_MAIN_VIDEO,
    product_id_from_url,
    resource_filename,
)
from app.engine.downloader import DownloadResult, download_media
from app.engine.extractor import MediaSet, extract_media
from app.engine.fetcher import Fetcher, FetcherError

logger = logging.getLogger(__name__)

# 四类资源（kind, MediaSet 字段）
_RESOURCE_GROUPS = [
    (KIND_MAIN_IMAGE, "main_images"),
    (KIND_DETAIL_IMAGE, "detail_images"),
    (KIND_MAIN_VIDEO, "main_videos"),
    (KIND_DETAIL_VIDEO, "detail_videos"),
]


@dataclass
class CrawlResult:
    product_id: str
    title: str | None
    success: bool
    error: str | None
    resources: list[dict] = field(default_factory=list)  # [{kind,url,file_path,size,status}]


async def crawl_product(
    fetcher: Fetcher,
    url: str,
    dest_dir: Path,
    referer: str | None = None,
) -> CrawlResult:
    """抓取单个商品：获取页面 → 提取四类媒体 → 逐资源下载 → 写 manifest.json。

    单个资源下载失败不中断，记入 ``resources`` 的 ``status``；
    ``success`` 仅表示抓取主流程（fetch/extract/manifest）完成，
    整体任务成败由调用方（调度器）根据 resources 自行判定。
    """
    dest_dir = Path(dest_dir)
    pid = product_id_from_url(url)
    if pid is None:
        return CrawlResult(
            product_id="", title=None, success=False,
            error=f"无法从 URL 提取商品 ID: {url}", resources=[],
        )

    # ---- 1. 获取页面 ----
    try:
        result = await fetcher.fetch(url, referer=referer)
    except FetcherError as e:
        logger.error("[%s] 页面获取失败: %s", pid, e)
        _write_manifest(dest_dir, pid, url, None, [], "failed", error=str(e))
        return CrawlResult(product_id=pid, title=None, success=False, error=str(e))

    if result.status_code >= 400 or not result.html:
        msg = f"页面获取失败 HTTP {result.status_code}（strategy={result.strategy}）"
        logger.error("[%s] %s", pid, msg)
        _write_manifest(dest_dir, pid, url, None, [], "failed", error=msg)
        return CrawlResult(product_id=pid, title=None, success=False, error=msg)

    # ---- 2. 提取媒体 ----
    page_url = result.final_url or url
    media: MediaSet = extract_media(result.html, page_url)
    logger.info(
        "[%s] 提取完成: 主图%d 主视%d 详情图%d 详情视%d",
        pid,
        len(media.main_images), len(media.main_videos),
        len(media.detail_images), len(media.detail_videos),
    )

    # ---- 2.1 内容级检测：四类资源全空 → 视为异常（反爬跳转页 / 媒体不可提取）----
    if (
        not media.main_images
        and not media.main_videos
        and not media.detail_images
        and not media.detail_videos
    ):
        if media.title is None:
            if _is_login_wall(result.html):
                msg = (
                    f"页面要求登录（登录墙/地区限制），未提取到商品数据，"
                    f"请先运行 python -m app.engine.login 登录后重启后端重试"
                    f"（strategy={result.strategy}）"
                )
            elif _is_anti_bot_page(result.html):
                msg = (
                    f"被目标站反爬验证拦截（x5sec/滑块验证），页面无可提取数据，"
                    f"可能需要有效登录态或更换网络/降低频率"
                    f"（strategy={result.strategy}）"
                )
            else:
                msg = (
                    f"页面未提取到商品数据（标题与四类资源均为空），"
                    f"可能被反爬拦截或页面结构变更（strategy={result.strategy}）"
                )
        else:
            msg = (
                f"页面可访问但未提取到任何媒体资源（标题: {media.title[:50]}），"
                f"可能媒体被反爬隐藏或结构变更（strategy={result.strategy}）"
            )
        logger.warning("[%s] %s", pid, msg)
        _write_manifest(dest_dir, pid, url, media.title, [], "failed", error=msg)
        return CrawlResult(product_id=pid, title=media.title, success=False, error=msg)

    # ---- 3. 逐资源下载（单资源失败不中断） ----
    resources: list[dict] = []
    for kind, attr in _RESOURCE_GROUPS:
        urls: list[str] = getattr(media, attr)
        for index, media_url in enumerate(urls, start=1):
            filename = resource_filename(kind, index)
            dr: DownloadResult = await download_media(
                media_url, dest_dir, filename, referer=page_url
            )
            resources.append({
                "kind": kind,
                "url": media_url,
                "file_path": dr.file_path,
                "size": dr.size,
                "status": dr.status,
            })
            level = logger.warning if dr.status == "failed" else logger.info
            level("[%s] %s -> %s (%s)", pid, kind, filename, dr.status)

    # ---- 4. manifest.json ----
    failed = [r for r in resources if r["status"] != "done"]
    manifest_status = "partial" if failed else "done"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        _write_manifest(
            dest_dir, pid, url, media.title, resources, manifest_status,
        )
    except OSError as e:
        msg = f"写入 manifest 失败: {e}"
        logger.error("[%s] %s", pid, msg)
        return CrawlResult(
            product_id=pid, title=media.title, success=False, error=msg,
            resources=resources,
        )

    return CrawlResult(
        product_id=pid,
        title=media.title,
        success=True,
        error=None,
        resources=resources,
    )


_LOGIN_WALL_MARKERS = ("login.alibaba.com", "icbuLogin", "mini_login")

# x5sec/滑块等反爬验证页特征（需至少命中 2 个才判定，避免误伤正常页面）
_ANTI_BOT_MARKERS = ("x5sec", "captcha", "slider", "verify")


def _is_login_wall(html: str) -> bool:
    """识别阿里巴巴登录墙/地区限制页：HTTP 200 但内容为登录跳转脚本（无商品数据）。

    特征：页面含登录跳转引用（login.alibaba.com / icbuLogin / mini_login），
    且脚本声明 action=login，或页面极小且无 <title>（真实商品页数百 KB）。
    """
    if not html:
        return False
    has_login_ref = any(m in html for m in _LOGIN_WALL_MARKERS)
    has_action_login = '"action": "login"' in html
    tiny_page = len(html) < 20_000 and "<title>" not in html
    return has_login_ref and (has_action_login or tiny_page)


def _is_anti_bot_page(html: str) -> bool:
    """识别 x5sec/滑块验证等反爬验证页（HTTP 200 但无可提取的商品数据）。

    特征：命中至少 2 个反爬关键词（x5sec/captcha/slider/verify），
    且页面不含真实商品数据（window.detailData），避免误判正常页。
    """
    if not html or "window.detailData" in html:
        return False
    lowered = html.lower()
    hits = sum(1 for m in _ANTI_BOT_MARKERS if m in lowered)
    return hits >= 2


def _write_manifest(
    dest_dir: Path,
    product_id: str,
    url: str,
    title: str | None,
    resources: list[dict],
    status: str,
    error: str | None = None,
) -> None:
    """生成 manifest.json（字段：product_id/title/抓取时间/四类资源路径/status）。"""
    by_kind: dict[str, list[str]] = {
        KIND_MAIN_IMAGE: [],
        KIND_DETAIL_IMAGE: [],
        KIND_MAIN_VIDEO: [],
        KIND_DETAIL_VIDEO: [],
    }
    for r in resources:
        if r["status"] == "done":
            by_kind.setdefault(r["kind"], []).append(Path(r["file_path"]).name)

    manifest = {
        "product_id": product_id,
        "url": url,
        "title": title,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "main_images": by_kind[KIND_MAIN_IMAGE],
        "detail_images": by_kind[KIND_DETAIL_IMAGE],
        "main_videos": by_kind[KIND_MAIN_VIDEO],
        "detail_videos": by_kind[KIND_DETAIL_VIDEO],
    }
    if error:
        manifest["error"] = error
    dest_dir.mkdir(parents=True, exist_ok=True)
    with open(dest_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
