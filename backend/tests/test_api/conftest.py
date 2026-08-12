"""共享 fixtures：临时数据库、TestClient、假调度器。

测试不得连真实网络；调度器用 monkeypatch 的 FakeScheduler 替换，避免真实抓取。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config as app_config
from app import db as app_db
from app.main import app


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """每个测试用独立临时 data 目录与空数据库。"""
    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    app_db.init_db()
    yield


@pytest.fixture
def client(fresh_db):
    with TestClient(app) as c:
        yield c


class FakeScheduler:
    """记录控制调用、不触发真实抓取的替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def start(self, task_id):
        self.calls.append(("start", task_id))

    def pause(self, task_id):
        self.calls.append(("pause", task_id))

    def cancel(self, task_id):
        self.calls.append(("cancel", task_id))

    def resume(self, task_id):
        self.calls.append(("resume", task_id))

    async def log_stream(self, task_id):
        yield "data: {}\n\n"


@pytest.fixture
def fake_scheduler(monkeypatch):
    fake = FakeScheduler()
    monkeypatch.setattr("app.api.tasks.scheduler", fake)
    monkeypatch.setattr("app.api.products.scheduler", fake)
    return fake
