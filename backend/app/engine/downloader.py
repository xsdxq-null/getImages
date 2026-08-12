"""媒体资源下载：流式下载、格式转换（avif/webp→jpg）、断点续传。

CONTRACT.md 第 4.5 节。
"""
from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image

from app.engine.anti_anti import USER_AGENTS

logger = logging.getLogger(__name__)

# 图片类扩展名（需经 Pillow 处理，非 JPEG 源转为 jpg）
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp"}
# 视频类扩展名（保留原格式）
_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv"}

_DOWNLOAD_TIMEOUT = 30.0


@dataclass
class DownloadResult:
    file_path: str
    size: int
    status: str  # "done" | "failed"
    skipped: bool  # 断点续传跳过
    converted: bool  # 是否格式转换
    error: str | None


async def download_media(
    url: str,
    dest_dir: Path,
    filename: str,
    referer: str | None = None,
) -> DownloadResult:
    """下载单个媒体资源到 ``dest_dir/filename``。

    - 已存在且 size>0 → ``skipped=True``（断点续传，不再下载）；
    - httpx 流式下载，超时 30s；0 字节视为失败；
    - 图片（jpg/png/webp/avif 等）：非 JPEG 源用 Pillow 转 jpg
      （avif 依赖 pillow-avif-plugin）；转换失败保留原格式并 ``converted=False``；
    - 视频：保留 mp4 原格式。
    """
    dest_dir = Path(dest_dir)
    target = dest_dir / filename
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return DownloadResult(
            file_path=str(target), size=0, status="failed",
            skipped=False, converted=False, error=f"无法创建目录: {e}",
        )

    # 断点续传：目标已存在且非空则跳过
    if target.exists() and target.stat().st_size > 0:
        size = target.stat().st_size
        logger.info("跳过已存在资源 %s (size=%d)", target.name, size)
        return DownloadResult(
            file_path=str(target), size=size, status="done",
            skipped=True, converted=False, error=None,
        )

    tmp = dest_dir / (filename + ".part")
    try:
        tmp.unlink(missing_ok=True)  # 清理残留的临时文件
    except OSError:
        pass

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    if referer:
        headers["Referer"] = referer

    # 流式下载到临时文件
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_DOWNLOAD_TIMEOUT), follow_redirects=True
        ) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code != 200:
                    return DownloadResult(
                        file_path=str(target), size=0, status="failed",
                        skipped=False, converted=False,
                        error=f"下载失败 HTTP {resp.status_code}",
                    )
                with open(tmp, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            f.write(chunk)
    except Exception as e:
        return DownloadResult(
            file_path=str(target), size=0, status="failed",
            skipped=False, converted=False, error=f"下载异常: {e}",
        )

    # 0 字节校验
    if not tmp.exists() or tmp.stat().st_size == 0:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return DownloadResult(
            file_path=str(target), size=0, status="failed",
            skipped=False, converted=False, error="下载内容为空(0 字节)",
        )

    # 图片：非 JPEG 源转 jpg
    converted = False
    if target.suffix.lower() in _IMAGE_EXTS:
        converted = _convert_to_jpg(tmp)

    # 落盘（rename 保证原子性）
    try:
        os.replace(tmp, target)
    except OSError as e:
        return DownloadResult(
            file_path=str(target), size=0, status="failed",
            skipped=False, converted=False, error=f"写入文件失败: {e}",
        )

    size = target.stat().st_size
    logger.info("下载完成 %s (size=%d, converted=%s)", target.name, size, converted)
    return DownloadResult(
        file_path=str(target), size=size, status="done",
        skipped=False, converted=converted, error=None,
    )


def _convert_to_jpg(tmp: Path) -> bool:
    """尝试将图片转 jpg；转换失败保留原格式（返回 False）。"""
    try:
        with Image.open(tmp) as img:
            if (img.format or "").upper() == "JPEG":
                return False
            rgb = img.convert("RGB")
            rgb.save(tmp, "JPEG", quality=85)
            return True
    except Exception as e:
        logger.warning("图片转 jpg 失败，保留原格式: %s", e)
        return False
