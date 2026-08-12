"""任务调度器：后台 asyncio 逐商品抓取 + 内存日志中心 + 文件日志。

CONTRACT 第 5 节：
- ``start/pause/cancel/resume``：控制接口（幂等）；
- 每商品：products.status=fetching → crawl_product → 写 resources 行、
  更新 products 状态 → 任务结束置 done/partial 并写 finished_at；
- 暂停/取消用控制信号量检查点（每商品前后检查），取消后循环内抛
  CancelledError 结束任务；
- 日志写 ``data/logs/task_{id}.log`` 且内存 ``deque(maxlen=2000)`` 供 SSE；
- 单商品失败不中断整个任务。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from pathlib import Path

from . import models
from .config import build_engine_config, settings

logger = logging.getLogger(__name__)

_FILE_LOCK = threading.Lock()


class TaskScheduler:
    """单事件循环内的协作式任务调度器（单 worker 部署）。"""

    def __init__(self, config=None) -> None:
        self.config = config or settings
        self._jobs: dict[int, asyncio.Task] = {}
        self._events: dict[int, asyncio.Event] = {}   # 暂停/恢复控制信号量
        self._cancelled: set[int] = set()
        self._logs: dict[int, deque] = {}
        self._listeners: dict[int, list[asyncio.Queue]] = {}

    # ------------------------------------------------------------------ #
    # 控制接口（幂等）
    # ------------------------------------------------------------------ #
    def start(self, task_id: int) -> None:
        """启动/重启后台任务。已有运行中的 job 时忽略（幂等）。"""
        job = self._jobs.get(task_id)
        if job is not None and not job.done():
            return
        self._cancelled.discard(task_id)
        self._events[task_id] = asyncio.Event()
        self._events[task_id].set()
        self._logs.setdefault(task_id, deque(maxlen=self.config.max_log_buffer))
        self._listeners.setdefault(task_id, [])
        self._jobs[task_id] = asyncio.create_task(self._run(task_id))

    def pause(self, task_id: int) -> None:
        """清空控制信号量 → 检查点处等待恢复。"""
        ev = self._events.get(task_id)
        if ev is not None:
            ev.clear()
        self.log(task_id, "info", "任务已暂停")

    def cancel(self, task_id: int) -> None:
        """标记取消并唤醒检查点 → 循环抛 CancelledError 结束任务。"""
        self._cancelled.add(task_id)
        ev = self._events.get(task_id)
        if ev is not None:
            ev.set()
        self.log(task_id, "warning", "任务正在取消…")

    def resume(self, task_id: int) -> None:
        """恢复：已有 job 则唤醒；终态任务则重新启动（断点续传）。"""
        self._cancelled.discard(task_id)
        ev = self._events.get(task_id)
        if ev is None:
            ev = asyncio.Event()
            ev.set()
            self._events[task_id] = ev
        else:
            ev.set()
        job = self._jobs.get(task_id)
        if job is not None and not job.done():
            return
        self.start(task_id)
        self.log(task_id, "info", "任务已恢复运行")

    # ------------------------------------------------------------------ #
    # 日志中心
    # ------------------------------------------------------------------ #
    def log(self, task_id: int, level: str, message: str,
            product_id: str | None = None) -> None:
        entry = {
            "ts": models.now_iso(),
            "level": level,
            "product_id": product_id,
            "message": message,
        }
        # 内存缓冲（供 SSE 尾读）
        self._logs.setdefault(task_id, deque(maxlen=self.config.max_log_buffer))
        self._logs[task_id].append(entry)
        # 广播给 SSE 监听者（慢消费者丢弃）
        listeners = self._listeners.get(task_id)
        if listeners:
            for i in reversed(range(len(listeners))):
                try:
                    listeners[i].put_nowait(entry)
                except asyncio.QueueFull:
                    listeners.pop(i)
        # 文件日志
        self._write_file_log(task_id, entry)

    def _write_file_log(self, task_id: int, entry: dict) -> None:
        try:
            logs_dir = self.config.logs_dir
            logs_dir.mkdir(parents=True, exist_ok=True)
            pid = f"[{entry['product_id']}] " if entry.get("product_id") else ""
            line = f"{entry['ts']} [{entry['level']}] {pid}{entry['message']}\n"
            with _FILE_LOCK:
                with open(logs_dir / f"task_{task_id}.log", "a", encoding="utf-8") as f:
                    f.write(line)
        except OSError as e:  # pragma: no cover
            logger.warning("写任务日志失败: %s", e)

    def tail(self, task_id: int, limit: int = 200) -> list[dict]:
        """返回缓冲内最后 ``limit`` 条日志（供 SSE 先发）。"""
        buf = self._logs.get(task_id)
        if not buf:
            return []
        return list(buf)[-limit:]

    def subscribe(self, task_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._listeners.setdefault(task_id, []).append(q)
        return q

    def unsubscribe(self, task_id: int, queue: asyncio.Queue) -> None:
        listeners = self._listeners.get(task_id)
        if listeners and queue in listeners:
            listeners.remove(queue)

    async def log_stream(self, task_id: int):
        """SSE 事件流：先发缓冲内最后 200 条，再持续推送新日志。

        客户端断开（生成器被取消）时自动清理监听队列。
        """
        queue = self.subscribe(task_id)
        try:
            for entry in self.tail(task_id, 200):
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
            while True:
                entry = await queue.get()
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
        finally:
            self.unsubscribe(task_id, queue)

    # ------------------------------------------------------------------ #
    # 内部：任务主循环
    # ------------------------------------------------------------------ #
    async def _checkpoint(self, task_id: int) -> None:
        """每商品前后检查点：取消优先，其次暂停等待。"""
        if task_id in self._cancelled:
            raise asyncio.CancelledError("task cancelled")
        ev = self._events.get(task_id)
        if ev is not None and not ev.is_set():
            self.log(task_id, "info", "任务已暂停，等待恢复…")
            await ev.wait()
            if task_id in self._cancelled:
                raise asyncio.CancelledError("task cancelled")

    def _make_fetcher(self, engine_cfg):
        from app.engine.fetcher import Fetcher  # 延迟导入（引擎并行开发隔离）
        return Fetcher(engine_cfg)

    async def _run(self, task_id: int) -> None:
        fetcher = None
        try:
            task = await asyncio.to_thread(models.get_task, task_id)
            if task is None:  # pragma: no cover
                return
            started_at = task.get("started_at") or models.now_iso()
            await asyncio.to_thread(models.update_task_status, task_id,
                                    status="running", started_at=started_at)
            await asyncio.to_thread(models.reset_fetching, task_id)
            fetcher = self._make_fetcher(build_engine_config(task))
            self.log(task_id, "info", f"任务开始：共 {task['total']} 个商品")

            while True:
                await self._checkpoint(task_id)
                product = await asyncio.to_thread(models.next_pending_product, task_id)
                if product is None:
                    break
                product_no = product.get("product_id") or ""
                dest_dir = self.config.downloads_dir / str(task_id) / product_no
                self.log(task_id, "info", f"开始抓取商品 {product_no}", product_id=product_no)
                await asyncio.to_thread(models.update_product, product["id"], status="fetching")

                try:
                    result = await _crawl(product, dest_dir, fetcher)
                except asyncio.CancelledError:
                    await asyncio.to_thread(models.update_product, product["id"], status="pending")
                    raise
                except Exception as e:  # 单商品异常不中断任务
                    await asyncio.to_thread(models.update_product, product["id"],
                                            status="failed", error=f"抓取异常: {e}")
                    self.log(task_id, "error", f"商品 {product_no} 抓取异常: {e}",
                             product_id=product_no)
                    continue

                # 写 resources 行（同 URL 幂等更新，支持断点续传）
                done = 0
                for r in result.resources:
                    await asyncio.to_thread(
                        models.upsert_resource, product["id"], r["kind"], r["url"],
                        r["status"], r.get("file_path"), r.get("size"))
                    if r["status"] == "done":
                        done += 1

                # 判定商品成败
                if not result.success:
                    await asyncio.to_thread(models.update_product, product["id"],
                                            status="failed", error=result.error)
                    self.log(task_id, "error", f"商品 {product_no} 抓取失败: {result.error}",
                             product_id=product_no)
                elif result.resources and done == 0:
                    await asyncio.to_thread(models.update_product, product["id"],
                                            status="failed", error="全部资源下载失败")
                    self.log(task_id, "error", f"商品 {product_no} 全部资源下载失败",
                             product_id=product_no)
                else:
                    await asyncio.to_thread(models.update_product, product["id"],
                                            status="done", title=result.title,
                                            fetched_at=models.now_iso())
                    self.log(task_id, "info",
                             f"商品 {product_no} 完成（{done}/{len(result.resources)} 资源）",
                             product_id=product_no)

                await self._checkpoint(task_id)  # 商品后检查点

            # ---- 任务结束 ----
            stats = await asyncio.to_thread(models.task_stats, task_id)
            final = "done" if stats["failed"] == 0 else "partial"
            await asyncio.to_thread(models.update_task_status, task_id,
                                    status=final, finished_at=models.now_iso())
            self.log(task_id, "info",
                     f"任务结束：成功 {stats['succeeded']} 失败 {stats['failed']} → {final}")
        except asyncio.CancelledError:
            await asyncio.to_thread(models.update_task_status, task_id,
                                    status="cancelled", finished_at=models.now_iso())
            self.log(task_id, "warning", "任务已取消")
            raise
        except Exception as e:  # pragma: no cover - 防御性兜底
            await asyncio.to_thread(models.update_task_status, task_id,
                                    status="partial", finished_at=models.now_iso())
            self.log(task_id, "error", f"任务异常终止: {e}")
        finally:
            if fetcher is not None:
                try:
                    await fetcher.aclose()
                except Exception:  # pragma: no cover
                    pass
            self._jobs.pop(task_id, None)


async def _crawl(product: dict, dest_dir: Path, fetcher) -> object:
    """延迟导入 crawl_product 并执行（引擎并行开发隔离 + 真实网络隔离点）。"""
    from app.engine.crawler import crawl_product
    return await crawl_product(fetcher, product["url"], dest_dir,
                               referer=product["url"])


# 全局调度器单例（API 层引用）
scheduler = TaskScheduler()
