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


class TestResourceSelection:
    def _setup_two_resources(self, client) -> tuple[dict, dict, dict]:
        """创建任务 → 商品 → 两个 done 资源，返回 (task, product, [r1, r2])。"""
        task = _create_task(client)
        p = _first_product(client, task["id"])
        ddir = app_config.settings.downloads_dir / str(task["id"]) / p["product_id"]
        ddir.mkdir(parents=True, exist_ok=True)
        f1, f2 = ddir / "img_001.jpg", ddir / "img_002.jpg"
        f1.write_bytes(b"A")
        f2.write_bytes(b"B")
        models.upsert_resource(p["id"], "detail_image", "https://cdn.example/1.jpg",
                               "done", str(f1), 1)
        models.upsert_resource(p["id"], "detail_image", "https://cdn.example/2.jpg",
                               "done", str(f2), 1)
        resp = client.get(f"/api/products/{p['id']}")
        rs = resp.json()["resources"]
        assert len(rs) == 2
        return task, p, rs

    def _zip_names(self, client, product_id: int) -> list[str]:
        resp = client.get(f"/api/products/{product_id}/download")
        assert resp.status_code == 200
        return zipfile.ZipFile(io.BytesIO(resp.content)).namelist()

    def test_default_all_selected(self, client):
        task, p, rs = self._setup_two_resources(client)
        # 默认全部 selected=1，下载包含两个资源
        assert all(r["selected"] == 1 for r in rs)
        names = self._zip_names(client, p["id"])
        assert len(names) == 2
        assert any("img_001.jpg" in n for n in names)
        assert any("img_002.jpg" in n for n in names)

    def test_save_selection_filters_download(self, client):
        task, p, rs = self._setup_two_resources(client)
        # 只选第一个
        resp = client.put(
            f"/api/products/{p['id']}/resources/selection",
            json={"selected_ids": [rs[0]["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["selected_count"] == 1
        # 详情返回最新选中状态
        data = client.get(f"/api/products/{p['id']}").json()
        sel = {r["id"]: r["selected"] for r in data["resources"]}
        assert sel[rs[0]["id"]] == 1 and sel[rs[1]["id"]] == 0
        # 下载只含选中的资源
        names = self._zip_names(client, p["id"])
        assert len(names) == 1 and "img_001.jpg" in names[0]

    def test_deselect_all_zip_empty(self, client):
        task, p, rs = self._setup_two_resources(client)
        resp = client.put(
            f"/api/products/{p['id']}/resources/selection",
            json={"selected_ids": []},
        )
        assert resp.status_code == 200
        # 全不选 → zip 无文件
        resp = client.get(f"/api/products/{p['id']}/download")
        assert resp.status_code == 200
        assert zipfile.ZipFile(io.BytesIO(resp.content)).namelist() == []

    def test_selection_404(self, client):
        resp = client.put(
            "/api/products/99999/resources/selection",
            json={"selected_ids": [1]},
        )
        assert resp.status_code == 404
