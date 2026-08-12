"""zip 打包：全任务 / 单商品下载。

- 用临时文件 + ``FileResponse`` 流式返回（大文件不占内存）；
- 仅打包成功资源（resources.status='done' 且文件存在）；
- zip 内目录结构与磁盘规则一致：``{task_id}/{product_id}/文件名``
  （单商品为 ``{product_id}/文件名``），并附带 ``manifest.json``。
"""
from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .. import models

ZIP_MEDIA_TYPE = "application/zip"


def build_task_zip(task: dict) -> FileResponse:
    task_id = task["id"]
    resources = models.task_download_resources(task_id)
    tmp = _write_zip(resources, root_prefix=str(task_id), nested=True)
    filename = f"task_{task_id}.zip"
    return FileResponse(tmp, media_type=ZIP_MEDIA_TYPE, filename=filename,
                        background=BackgroundTask(_cleanup, tmp))


def build_product_zip(product: dict) -> FileResponse:
    row_id = product["id"]
    product_no = product.get("product_id") or f"product_{row_id}"
    resources = models.product_download_resources(row_id)
    tmp = _write_zip(resources, root_prefix=product_no, nested=False)
    filename = f"product_{row_id}.zip"
    return FileResponse(tmp, media_type=ZIP_MEDIA_TYPE, filename=filename,
                        background=BackgroundTask(_cleanup, tmp))


def _write_zip(resources: list[dict], root_prefix: str, nested: bool) -> str:
    """打包 zip；``nested=True`` 为全任务（``{task_id}/{product_no}/``），
    ``nested=False`` 为单商品（``{product_no}/``）。"""
    fd, tmp = tempfile.mkstemp(suffix=".zip", prefix=f"{root_prefix}_")
    os.close(fd)
    written_manifest: set[str] = set()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in resources:
            fpath = Path(r["file_path"])
            if not fpath.exists():
                continue
            if nested:
                subdir = r["product_no"]
                arc = f"{root_prefix}/{subdir}/{fpath.name}"
                manifest_arc = f"{root_prefix}/{subdir}/manifest.json"
            else:
                arc = f"{root_prefix}/{fpath.name}"
                manifest_arc = f"{root_prefix}/manifest.json"
            zf.write(str(fpath), arc)
            manifest = fpath.parent / "manifest.json"
            if manifest.exists() and str(manifest) not in written_manifest:
                written_manifest.add(str(manifest))
                zf.write(str(manifest), manifest_arc)
    return tmp


def _cleanup(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def require_downloadable(task: dict) -> None:
    """运行中（running/paused）不允许打包，返回 409。"""
    if task["status"] in ("running", "paused"):
        raise HTTPException(
            status_code=409,
            detail=f"任务状态为 {task['status']}，运行中暂不可打包下载，请等待完成",
        )
