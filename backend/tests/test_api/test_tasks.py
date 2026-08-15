"""任务 API 测试：创建/parse/分页/控制/下载 409/zip/SSE。

调度器在控制端点被 FakeScheduler 替换，不触发真实抓取、不连网络。
"""
from __future__ import annotations

import io
import zipfile

from app import config as app_config
from app import models


def make_urls(n: int = 2) -> list[str]:
    """生成 n 个合法商品 URL（末段 ≥5 位纯数字）。"""
    return [f"https://www.alibaba.com/product-detail/{10000000000 + i}.html"
            for i in range(n)]


TXT_URLS = "\n".join(make_urls(2))


def _create_task(client, content: bytes | None = None, name="测试任务",
                 **data) -> dict:
    body = content if content is not None else TXT_URLS.encode("utf-8")
    payload = {"name": name}
    payload.update(data)
    resp = client.post(
        "/api/tasks",
        files={"file": ("urls.txt", body, "text/plain")},
        data=payload,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreateAndParse:
    def test_create_task_with_txt_upload(self, client):
        task = _create_task(client)
        assert task["id"] > 0
        assert task["status"] == "pending"
        assert task["total"] == 2
        assert task["succeeded"] == 0
        assert task["failed"] == 0
        assert task["progress"] == 0
        assert task["rate_limit"] == 2.0
        assert task["concurrency"] == 2
        assert task["url_file"] == "urls.txt"

    def test_create_task_with_csv(self, client):
        csv_body = "name,url,note\np1,%s,ok\np2,%s,no\n" % (
            make_urls(2)[0], make_urls(2)[1])
        task = _create_task(client, content=csv_body.encode("utf-8"))
        assert task["total"] == 2

    def test_create_task_invalid_file_400(self, client):
        resp = client.post(
            "/api/tasks",
            files={"file": ("bad.txt", b"not a url\nanother bad\n", "text/plain")},
            data={"name": "bad"},
        )
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_create_task_custom_params(self, client):
        task = _create_task(client, rate_limit="1.5", concurrency="3")
        assert task["rate_limit"] == 1.5
        assert task["concurrency"] == 3

    def test_parse_endpoint(self, client):
        body = (
            "# comment\n"
            "https://www.alibaba.com/product-detail/1111111111.html\n"
            "https://www.alibaba.com/product-detail/1111111111.html\n"  # 重复
            "not-a-url\n"
        ).encode("utf-8")
        resp = client.post(
            "/api/tasks/parse",
            files={"file": ("urls.txt", body, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["invalid"] == 2          # 1 重复 + 1 非法
        assert data["product_ids"] == ["1111111111"]


class TestTaskList:
    def test_list_pagination(self, client):
        for _ in range(3):
            _create_task(client)
        resp = client.get("/api/tasks", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        # items 含聚合字段
        assert {"total", "succeeded", "failed", "progress"} <= set(data["items"][0])

    def test_task_detail(self, client):
        task = _create_task(client)
        resp = client.get(f"/api/tasks/{task['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == task["id"]
        assert resp.json()["progress"] == 0

    def test_task_detail_404(self, client):
        assert client.get("/api/tasks/99999").status_code == 404


class TestTaskDelete:
    def test_delete_task_and_files(self, client):
        """删除任务：DB 记录级联删除 + 磁盘文件（下载/上传/日志）清理。"""
        from app import config as app_config

        task = _create_task(client)
        tid = task["id"]
        # 造磁盘文件
        ddir = app_config.settings.downloads_dir / str(tid)
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / "img.jpg").write_bytes(b"X")
        up = app_config.settings.uploads_dir / f"task_{tid}.txt"
        up.write_bytes(b"urls")
        app_config.settings.logs_dir.mkdir(parents=True, exist_ok=True)
        log = app_config.settings.logs_dir / f"task_{tid}.log"
        log.write_bytes(b"log")

        resp = client.delete(f"/api/tasks/{tid}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # DB：任务、商品、资源均删
        assert client.get(f"/api/tasks/{tid}").status_code == 404
        # 磁盘文件清空
        assert not ddir.exists()
        assert not up.exists()
        assert not log.exists()

    def test_delete_running_409(self, client, fake_scheduler):
        """运行中任务不可删除。"""
        task = _create_task(client)
        client.post(f"/api/tasks/{task['id']}/start")  # → running
        resp = client.delete(f"/api/tasks/{task['id']}")
        assert resp.status_code == 409
        # 任务仍在
        assert client.get(f"/api/tasks/{task['id']}").status_code == 200

    def test_delete_404(self, client):
        assert client.delete("/api/tasks/99999").status_code == 404

    def test_batch_delete(self, client, fake_scheduler):
        """批量删除：正常删除 + 跳过运行中 + 跳过不存在。"""
        t1 = _create_task(client)   # pending → 可删
        t2 = _create_task(client)   # 置为 running → 跳过
        t3 = _create_task(client)   # pending → 可删
        client.post(f"/api/tasks/{t2['id']}/start")  # running

        resp = client.post(
            "/api/tasks/batch-delete",
            json={"ids": [t1["id"], t2["id"], t3["id"], 99999]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["deleted"]) == {t1["id"], t3["id"]}
        assert data["skipped"] == [
            {"id": t2["id"], "reason": "running"},
            {"id": 99999, "reason": "not_found"},
        ]
        # t2 仍存在
        assert client.get(f"/api/tasks/{t2['id']}").status_code == 200


class TestTaskControl:
    def test_start(self, client, fake_scheduler):
        task = _create_task(client)
        resp = client.post(f"/api/tasks/{task['id']}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert ("start", task["id"]) in fake_scheduler.calls

    def test_pause(self, client, fake_scheduler):
        task = _create_task(client)
        client.post(f"/api/tasks/{task['id']}/start")
        resp = client.post(f"/api/tasks/{task['id']}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"
        assert ("pause", task["id"]) in fake_scheduler.calls

    def test_cancel(self, client, fake_scheduler):
        task = _create_task(client)
        client.post(f"/api/tasks/{task['id']}/start")
        resp = client.post(f"/api/tasks/{task['id']}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        assert ("cancel", task["id"]) in fake_scheduler.calls

    def test_resume(self, client, fake_scheduler):
        task = _create_task(client)
        client.post(f"/api/tasks/{task['id']}/start")
        client.post(f"/api/tasks/{task['id']}/cancel")
        resp = client.post(f"/api/tasks/{task['id']}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert ("resume", task["id"]) in fake_scheduler.calls

    def test_illegal_transition_409(self, client, fake_scheduler):
        task = _create_task(client)
        # pending 状态不可取消
        assert client.post(f"/api/tasks/{task['id']}/cancel").status_code == 409
        # 非 running 不可暂停
        assert client.post(f"/api/tasks/{task['id']}/pause").status_code == 409
        # 非终态不可 resume（pending）
        assert client.post(f"/api/tasks/{task['id']}/resume").status_code == 409


class TestTaskDownload:
    def test_download_409_when_running(self, client):
        task = _create_task(client)
        models.update_task_status(task["id"], status="running")
        resp = client.get(f"/api/tasks/{task['id']}/download")
        assert resp.status_code == 409
        assert "detail" in resp.json()

    def test_download_zip_ok(self, client, tmp_path):
        task = _create_task(client)
        task_id = task["id"]
        prods = client.get(f"/api/tasks/{task_id}/products").json()["items"]
        p = prods[0]
        # 构造成功资源文件 + resources 行
        ddir = app_config.settings.downloads_dir / str(task_id) / p["product_id"]
        ddir.mkdir(parents=True, exist_ok=True)
        img = ddir / "main_001.jpg"
        img.write_bytes(b"IMG-DATA")
        vid = ddir / "main_video_01.mp4"
        vid.write_bytes(b"VIDEO-DATA")
        (ddir / "manifest.json").write_text("{}", encoding="utf-8")
        models.upsert_resource(p["id"], "main_image", "https://cdn.example/x.jpg",
                               "done", str(img), 8)
        models.upsert_resource(p["id"], "main_video", "https://cdn.example/x.mp4",
                               "done", str(vid), 10)
        models.update_product(p["id"], status="done")
        models.update_task_status(task_id, status="done")

        resp = client.get(f"/api/tasks/{task_id}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        prefix = f"{task_id}/{p['product_id']}/"
        assert prefix + "main_001.jpg" in names
        assert prefix + "main_video_01.mp4" in names
        assert prefix + "manifest.json" in names
        assert zf.read(prefix + "main_001.jpg") == b"IMG-DATA"


class TestLogsSSE:
    def test_log_stream_generator(self, client):
        """调度器 log_stream 生成器：先发缓冲日志，EventSource 兼容帧（data: JSON）。

        注：TestClient/httpx ASGITransport 对无限流全缓冲（app 结束才返回 body），
        故在生成器层直接验证（迭代前 2 条后主动断开）。
        """
        task = _create_task(client)
        import asyncio

        from app.scheduler import scheduler  # 真实调度器（不替换）
        scheduler.log(task["id"], "info", "hello world")
        scheduler.log(task["id"], "error", "boom", product_id="1111111111")

        async def collect() -> list[str]:
            frames: list[str] = []
            async for frame in scheduler.log_stream(task["id"]):
                frames.append(frame)
                if len(frames) >= 2:
                    break
            return frames

        frames = asyncio.run(collect())
        assert len(frames) >= 2
        body = "".join(frames)
        assert body.startswith("data: ")
        assert "hello world" in body
        assert "boom" in body

    def test_logs_endpoint_streaming(self, client, monkeypatch):
        """HTTP 端点：content-type/缓存头/帧格式；用有限流替身验证端点封装。"""
        task = _create_task(client)
        from app.api import tasks as tasks_api

        async def fake_stream(task_id):
            yield 'data: {"level": "info", "message": "hello world"}\n\n'
            yield 'data: {"level": "error", "message": "boom"}\n\n'

        monkeypatch.setattr(tasks_api.scheduler, "log_stream", fake_stream)
        with client.stream("GET", f"/api/tasks/{task['id']}/logs") as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            assert r.headers.get("cache-control") == "no-cache"
            body = "".join(r.iter_text())
        assert body.count("data: ") == 2
        assert "hello world" in body
        assert "boom" in body
