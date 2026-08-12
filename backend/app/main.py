"""FastAPI 入口：挂路由 + CORS（本地开发）+ 生产静态托管前端产物。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db
from .api import products, tasks
from .config import BASE_DIR

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # 首次启动自动建表（data/ 自动创建）
    yield


app = FastAPI(title="getImages API", version="1.0.0", lifespan=lifespan)

# 本地开发 CORS（Vite dev server）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api")
app.include_router(products.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# 生产模式静态托管 frontend/dist（若存在）；API 路由已优先挂载
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
