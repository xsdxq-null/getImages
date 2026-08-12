"""SQLite 连接与建表（tasks/products/resources 三表，字段按 CONTRACT 第 2 节）。

- 数据库路径默认 ``data/app.db``，``data/`` 目录自动创建；
- 用 stdlib ``sqlite3`` + 模块级写锁保证多线程安全（调度器线程 + 请求线程）；
- 每次操作新建连接，避免跨线程连接复用问题。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import settings

_db_path: str | None = None
_write_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL DEFAULT '',
  url_file TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  total INTEGER NOT NULL DEFAULT 0,
  succeeded INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  rate_limit REAL NOT NULL DEFAULT 2.0,
  concurrency INTEGER NOT NULL DEFAULT 2,
  created_at TEXT,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  product_id TEXT,
  url TEXT,
  title TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS resources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES products(id),
  kind TEXT NOT NULL,
  url TEXT,
  file_path TEXT,
  size INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  retries INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_products_task ON products(task_id);
CREATE INDEX IF NOT EXISTS idx_resources_product ON resources(product_id);
CREATE INDEX IF NOT EXISTS idx_resources_url ON resources(product_id, url);
"""


def init_db(db_path: str | Path | None = None) -> str:
    """建表（幂等）。``data/`` 目录自动创建。返回实际数据库路径。"""
    global _db_path
    if db_path is None:
        db_path = settings.db_path
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _db_path = str(db_path)
    with _connect() as conn:
        conn.executescript(SCHEMA)
    return _db_path


def current_db_path() -> str:
    """当前数据库路径（未 init 时按 settings 计算，但不创建）。"""
    return _db_path or str(settings.db_path)


@contextmanager
def _connect():
    """新建一个连接，事务提交并关闭。"""
    conn = sqlite3.connect(_db_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connection():
    """对外数据访问入口：串行化所有写操作（单进程规模足够）。"""
    with _write_lock:
        with _connect() as conn:
            yield conn
