"""商品 API 测试：单商品详情（含 resources）、retry、单商品 zip。"""
from __future__ import annotations

import io
import zipfile

from app import config as app_config
from app import models


def make_urls(n: int = 2) -> list[str]:
    """生成 n 个合法商品 URL（末段 ≥5 位纯数字）。"""
    return [f"https://www.alibaba.com/product-detail/{10000000000 + i}.html"
            for i in range(n)]


def _create_task(client) -> dict:
    resp = client.post(
        "/api/tasks",
        files={"file": ("urls.txt", "\n".join(make_urls(2)).encode(), "text/plain")},
        data={"name": "任务"},
    )
    assert resp.status_code == 201
    return resp.json()


def _first_product(client, task_id: int) -> dict:
    resp = client.get(f"/api/tasks/{task_id}/products")
    assert resp.status_code == 200
    return resp.json()["items"][0]


class TestProductDetail:
    def test_detail_with_resources(self, client):
        task = _create_task(client)
        p = _first_product(client, task["id"])
        resp = client.get(f"/api/products/{p['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == p["id"]
        assert data["task_id"] == task["id"]
        assert data["product_id"]  # 业务商品 ID
        assert data["url"].startswith("https://")
        assert "resources" in data and data["resources"] == []

    def test_detail_404(self, client):
        assert client.get("/api/products/99999").status_code == 404


class TestRetry:
    def test_retry_failed_product(self, client, fake_scheduler):
        task = _create_task(client)
        p = _first_product(client, task["id"])
        models.update_product(p["id"], status="failed", error="模拟失败")
        resp = client.post(f"/api/products/{p['id']}/retry")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["error"] is None
        # pending 任务 retry → 触发调度 start
        assert ("start", task["id"]) in fake_scheduler.calls

    def test_retry_non_failed_409(self, client, fake_scheduler):
        task = _create_task(client)
        p = _first_product(client, task["id"])
        resp = client.post(f"/api/products/{p['id']}/retry")
        assert resp.status_code == 409
        assert "detail" in resp.json()

    def test_retry_404(self, client):
        assert client.post("/api/products/99999/retry").status_code == 404


class TestProductDownload:
    def test_product_download_zip(self, client):
        task = _create_task(client)
        p = _first_product(client, task["id"])
        ddir = app_config.settings.downloads_dir / str(task["id"]) / p["product_id"]
        ddir.mkdir(parents=True, exist_ok=True)
        img = ddir / "detail_001.jpg"
        img.write_bytes(b"IMG")
        models.upsert_resource(p["id"], "detail_image", "https://cdn.example/d.jpg",
                               "done", str(img), 3)

        resp = client.get(f"/api/products/{p['id']}/download")
        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert f"{p['product_id']}/detail_001.jpg" in names
