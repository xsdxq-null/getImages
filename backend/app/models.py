"""数据访问层：tasks/products/resources 三表建表/插入/查询/更新/聚合。

- 任务进度聚合：total / succeeded / failed / progress(0-100)；
- 商品资源计数：resource_counts = {kind: {done, total}}；
- 时间统一 ISO 8601 字符串（UTC）。
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _product_id_from_url(url: str) -> str | None:
    """延迟导入引擎工具；引擎未就绪时兜底提取（末段纯数字 ≥5 位）。"""
    try:
        from app.engine.constants import product_id_from_url
    except ImportError:  # pragma: no cover - 引擎未就绪时的兜底
        import re

        def product_id_from_url(u: str) -> str | None:  # type: ignore[no-redef]
            m = re.search(r"(\d{5,})(?:\.\w+)?$", u)
            return m.group(1) if m else None

    return product_id_from_url(url)


# --------------------------------------------------------------------------- #
# tasks
# --------------------------------------------------------------------------- #
def create_task(name: str, url_file: str, urls: list[str],
                rate_limit: float, concurrency: int) -> dict | None:
    now = now_iso()
    with db.connection() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (name,url_file,status,total,succeeded,failed,"
            "rate_limit,concurrency,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name or "", url_file or "", "pending", len(urls), 0, 0,
             rate_limit, concurrency, now),
        )
        task_id = cur.lastrowid
        for u in urls:
            conn.execute(
                "INSERT INTO products (task_id,product_id,url,status) VALUES (?,?,?,?)",
                (task_id, _product_id_from_url(u), u, "pending"),
            )
    return get_task(task_id)


def get_task(task_id: int) -> dict | None:
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        return None
    task = dict(row)
    task.update(task_stats(task_id))
    task["progress"] = _progress(task)
    return task


def list_tasks(page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    with db.connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
    items = []
    for r in rows:
        t = dict(r)
        t.update(task_stats(t["id"]))
        t["progress"] = _progress(t)
        items.append(t)
    return items, total


def update_task_status(task_id: int, status: str | None = None,
                       started_at: str | None = None,
                       finished_at: str | None = None) -> None:
    sets, params = [], []
    if status is not None:
        sets.append("status=?"); params.append(status)
    if started_at is not None:
        sets.append("started_at=?"); params.append(started_at)
    if finished_at is not None:
        sets.append("finished_at=?"); params.append(finished_at)
    if not sets:
        return
    params.append(task_id)
    with db.connection() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", params)


def task_stats(task_id: int) -> dict:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END),0) AS succeeded, "
            "COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),0) AS failed "
            "FROM products WHERE task_id=?",
            (task_id,),
        ).fetchone()
    return dict(row)


def _progress(task: dict) -> int:
    total = task.get("total") or 0
    if total <= 0:
        return 0
    return round((task.get("succeeded") or 0) / total * 100)


# --------------------------------------------------------------------------- #
# products
# --------------------------------------------------------------------------- #
def list_products(task_id: int, page: int = 1, page_size: int = 20,
                  status: str | None = None) -> tuple[list[dict], int]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    where, params = "task_id=?", [task_id]
    if status:
        where += " AND status=?"
        params.append(status)
    counts = resource_counts_for_task(task_id)
    with db.connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM products WHERE {where}",
                             params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM products WHERE {where} ORDER BY id LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["resource_counts"] = counts.get(d["id"], {})
        items.append(d)
    return items, total


def get_product(row_id: int) -> dict | None:
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id=?", (row_id,)).fetchone()
    return dict(row) if row else None


def update_product(row_id: int, status: str | None = None, error: str | None = None,
                   title: str | None = None, fetched_at: str | None = None,
                   _clear_error: bool = False) -> None:
    sets, params = [], []
    if status is not None:
        sets.append("status=?"); params.append(status)
    if error is not None:
        sets.append("error=?"); params.append(error)
    if _clear_error:
        sets.append("error=NULL")
    if title is not None:
        sets.append("title=?"); params.append(title)
    if fetched_at is not None:
        sets.append("fetched_at=?"); params.append(fetched_at)
    if not sets:
        return
    params.append(row_id)
    with db.connection() as conn:
        conn.execute(f"UPDATE products SET {', '.join(sets)} WHERE id=?", params)


def next_pending_product(task_id: int) -> dict | None:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE task_id=? AND status='pending' "
            "ORDER BY id LIMIT 1",
            (task_id,),
        ).fetchone()
    return dict(row) if row else None


def reset_fetching(task_id: int) -> None:
    """中断/暂停后把 fetching 商品复位为 pending（断点续传）。"""
    with db.connection() as conn:
        conn.execute(
            "UPDATE products SET status='pending' WHERE task_id=? AND status='fetching'",
            (task_id,),
        )


# --------------------------------------------------------------------------- #
# resources
# --------------------------------------------------------------------------- #
def upsert_resource(product_row_id: int, kind: str, url: str, status: str,
                    file_path: str | None = None, size: int | None = None) -> None:
    with db.connection() as conn:
        row = conn.execute(
            "SELECT id, retries FROM resources WHERE product_id=? AND url=?",
            (product_row_id, url),
        ).fetchone()
        if row is not None:
            retries = row["retries"] + (1 if status == "failed" else 0)
            conn.execute(
                "UPDATE resources SET kind=?, status=?, file_path=?, size=?, retries=? "
                "WHERE id=?",
                (kind, status, file_path, size or 0, retries, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO resources (product_id,kind,url,file_path,size,status,retries) "
                "VALUES (?,?,?,?,?,?,?)",
                (product_row_id, kind, url, file_path, size or 0, status, 0),
            )


def list_resources(product_row_id: int) -> list[dict]:
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM resources WHERE product_id=? ORDER BY id",
            (product_row_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_resources_selection(product_row_id: int, selected_ids: list[int]) -> None:
    """批量设置商品下资源的选中状态：id 在 selected_ids 的置 1，其余置 0。"""
    selected_ids = [int(i) for i in selected_ids]
    with db.connection() as conn:
        conn.execute("UPDATE resources SET selected=0 WHERE product_id=?", (product_row_id,))
        if selected_ids:
            placeholders = ",".join("?" * len(selected_ids))
            conn.execute(
                f"UPDATE resources SET selected=1 WHERE product_id=? AND id IN ({placeholders})",
                (product_row_id, *selected_ids),
            )


def resource_counts_for_task(task_id: int) -> dict[int, dict[str, dict]]:
    """任务下每商品的四类资源完成计数：{product_id: {kind: {"done": n, "total": m}}}。"""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT r.product_id AS pid, r.kind AS kind, r.status AS status, COUNT(*) AS c "
            "FROM resources r JOIN products p ON r.product_id = p.id "
            "WHERE p.task_id=? GROUP BY r.product_id, r.kind, r.status",
            (task_id,),
        ).fetchall()
    out: dict[int, dict[str, dict]] = {}
    for r in rows:
        pid = r["pid"]
        kind_map = out.setdefault(pid, {})
        entry = kind_map.setdefault(r["kind"], {"done": 0, "total": 0})
        entry["total"] += r["c"]
        if r["status"] == "done":
            entry["done"] += r["c"]
    return out


def task_download_resources(task_id: int) -> list[dict]:
    """任务下所有成功资源（供 zip 打包）。"""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT p.id AS product_row_id, p.product_id AS product_no, "
            "r.kind AS kind, r.file_path AS file_path, r.url AS url "
            "FROM resources r JOIN products p ON r.product_id = p.id "
            "WHERE p.task_id=? AND r.status='done' AND r.file_path IS NOT NULL "
            "AND r.file_path<>'' AND r.selected=1",
            (task_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def product_download_resources(product_row_id: int) -> list[dict]:
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT kind, file_path, url FROM resources "
            "WHERE product_id=? AND status='done' AND file_path IS NOT NULL "
            "AND file_path<>'' AND selected=1",
            (product_row_id,),
        ).fetchall()
    return [dict(r) for r in rows]
