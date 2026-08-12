"""商品相关 API（CONTRACT 第 3 节 products 端点）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import models
from ..scheduler import scheduler
from .download import build_product_zip

router = APIRouter(prefix="/products", tags=["products"])


def _require_product(row_id: int) -> dict:
    product = models.get_product(row_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"商品记录 {row_id} 不存在")
    return product


@router.get("/{row_id}")
async def product_detail(row_id: int):
    """单商品详情（含 resources 列表）。"""
    product = _require_product(row_id)
    product["resources"] = models.list_resources(row_id)
    return product


@router.post("/{row_id}/retry")
async def retry_product(row_id: int):
    """重试单个失败商品：置回 pending 并触发所在任务继续抓取。"""
    product = _require_product(row_id)
    if product["status"] != "failed":
        raise HTTPException(status_code=409,
                            detail=f"商品状态 {product['status']} 不可重试")
    models.update_product(row_id, status="pending", _clear_error=True)

    task = models.get_task(product["task_id"])
    if task is None:  # pragma: no cover
        raise HTTPException(status_code=404, detail="所属任务不存在")
    if task["status"] == "running":
        pass                       # 调度循环会自然取到新 pending 商品
    elif task["status"] == "paused":
        scheduler.resume(task["id"])   # 唤醒暂停中的 job
    else:                          # pending / done / partial / cancelled
        scheduler.start(task["id"])    # 启动/重启处理 pending 商品

    return _require_product(row_id)


@router.get("/{row_id}/download")
async def product_download(row_id: int):
    """单商品 zip（仅打包成功资源）。"""
    product = _require_product(row_id)
    return build_product_zip(product)
