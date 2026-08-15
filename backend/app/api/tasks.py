"""任务相关 API（CONTRACT 第 3 节 tasks 端点）。"""
from __future__ import annotations

import shutil

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import models
from ..config import settings
from ..scheduler import scheduler
from .download import build_task_zip, require_downloadable

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskIds(BaseModel):
    """批量删除：要删除的任务 id 列表。"""
    ids: list[int]


def _cleanup_task_files(task_id: int) -> None:
    """清理任务磁盘文件（下载/上传/日志），容错：缺失/权限问题不阻断。"""
    paths = [
        settings.downloads_dir / str(task_id),
        settings.uploads_dir / f"task_{task_id}.txt",
        settings.logs_dir / f"task_{task_id}.log",
    ]
    for p in paths:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass


def _require_task(task_id: int) -> dict:
    task = models.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return task


def _parse_url_file(content: bytes) -> tuple[list[str], int]:
    """解析上传的 txt/csv 内容 → (有效 URL 列表, 无效条目数)。

    无效条目 = 非空非注释输入行数 - 去重后有效 URL 数（含重复/非法 URL）。
    """
    from app.engine.constants import parse_url_list  # 延迟导入（引擎隔离）

    # utf-8-sig：自动剥离 UTF-8 BOM（Windows 记事本等），无 BOM 时行为同 utf-8
    text = content.decode("utf-8-sig", errors="replace")
    urls = parse_url_list(text)
    raw_lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    invalid = len(raw_lines) - len(urls)
    return urls, max(0, invalid)


@router.post("", status_code=201)
async def create_task(
    file: UploadFile = File(..., description="txt/csv URL 列表"),
    name: str = Form(""),
    rate_limit: float = Form(settings.default_rate_limit),
    concurrency: int = Form(settings.default_concurrency),
):
    content = await file.read()
    urls, _ = _parse_url_file(content)
    if not urls:
        raise HTTPException(status_code=400, detail="文件中未解析到有效商品 URL")

    task = models.create_task(
        name=name,
        url_file=file.filename or "",
        urls=urls,
        rate_limit=rate_limit,
        concurrency=concurrency,
    )
    # 保存原始上传文件副本，供历史回溯
    try:
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        (settings.uploads_dir / f"task_{task['id']}.txt").write_bytes(content)
    except OSError:  # pragma: no cover
        pass
    return task


@router.post("/parse")
async def parse_file(file: UploadFile = File(...)):
    """解析 URL 列表文件并返回校验结果（供前端展示，PRD F1）。"""
    content = await file.read()
    urls, invalid = _parse_url_file(content)
    from app.engine.constants import product_id_from_url  # 延迟导入

    product_ids = [pid for u in urls if (pid := product_id_from_url(u))]
    return {
        "total": len(urls),
        "invalid": invalid,
        "product_ids": product_ids,
    }


@router.get("")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = models.list_tasks(page=page, page_size=page_size)
    return {"items": items, "total": total}


@router.post("/batch-delete")
async def batch_delete_tasks(body: TaskIds):
    """批量删除任务：跳过运行中/不存在的任务，返回实际删除与跳过列表。"""
    deleted: list[int] = []
    skipped: list[dict] = []
    for tid in body.ids:
        task = models.get_task(tid)
        if task is None:
            skipped.append({"id": tid, "reason": "not_found"})
            continue
        if task["status"] in ("running", "paused"):
            skipped.append({"id": tid, "reason": "running"})
            continue
        _cleanup_task_files(tid)
        models.delete_task(tid)
        deleted.append(tid)
    return {"ok": True, "deleted": deleted, "skipped": skipped}


@router.get("/{task_id}")
async def task_detail(task_id: int):
    return _require_task(task_id)


@router.delete("/{task_id}")
async def delete_task(task_id: int):
    """删除任务：级联删除 products/resources 记录与磁盘文件（下载/上传/日志）。

    运行中（running/paused）任务不可删除（409），需先取消。
    """
    task = _require_task(task_id)
    if task["status"] in ("running", "paused"):
        raise HTTPException(
            status_code=409,
            detail=f"任务状态为 {task['status']}，运行中不可删除，请先取消",
        )

    _cleanup_task_files(task_id)
    removed_resources = models.delete_task(task_id)
    return {
        "ok": True,
        "id": task_id,
        "removed_resources": removed_resources,
    }


@router.post("/{task_id}/start")
async def start_task(task_id: int):
    task = _require_task(task_id)
    if task["status"] != "pending":
        raise HTTPException(status_code=409,
                            detail=f"任务状态 {task['status']} 不可启动")
    models.update_task_status(task_id, status="running",
                              started_at=models.now_iso())
    scheduler.start(task_id)
    return _require_task(task_id)


@router.post("/{task_id}/pause")
async def pause_task(task_id: int):
    task = _require_task(task_id)
    if task["status"] != "running":
        raise HTTPException(status_code=409,
                            detail=f"任务状态 {task['status']} 不可暂停")
    models.update_task_status(task_id, status="paused")
    scheduler.pause(task_id)
    return _require_task(task_id)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: int):
    task = _require_task(task_id)
    if task["status"] not in ("running", "paused"):
        raise HTTPException(status_code=409,
                            detail=f"任务状态 {task['status']} 不可取消")
    models.update_task_status(task_id, status="cancelled")
    scheduler.cancel(task_id)
    return _require_task(task_id)


@router.post("/{task_id}/resume")
async def resume_task(task_id: int):
    task = _require_task(task_id)
    if task["status"] not in ("paused", "cancelled", "done", "partial"):
        raise HTTPException(status_code=409,
                            detail=f"任务状态 {task['status']} 不可恢复")
    models.update_task_status(task_id, status="running")
    scheduler.resume(task_id)
    return _require_task(task_id)


@router.get("/{task_id}/products")
async def task_products(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, pattern="^(pending|fetching|done|failed)$"),
):
    _require_task(task_id)
    items, total = models.list_products(task_id, page=page, page_size=page_size,
                                        status=status)
    return {"items": items, "total": total}


@router.get("/{task_id}/logs")
async def task_logs(task_id: int):
    """SSE：先发缓冲内最后 200 条，再持续推送新日志。"""
    _require_task(task_id)
    return StreamingResponse(
        scheduler.log_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{task_id}/download")
async def task_download(task_id: int):
    task = _require_task(task_id)
    require_downloadable(task)
    return build_task_zip(task)
