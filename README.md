# getImages · 阿里巴巴国际站商品图片/视频抓取系统

电商运营与选品分析场景下，批量获取阿里巴巴国际站（Alibaba.com）商品详情页的**主图、详情图、主图视频、详情视频**四类媒体资源，按商品组织落盘并生成清单，支持任务管理与打包下载的全栈 Web 应用。

> 需求与验收：《PRD.md》｜技术方案：《交付文档.md》｜并行实施契约：《CONTRACT.md》｜验收记录：《验收记录.md》｜部署：《部署教程-本地.md》（本地/单机）·《部署教程-宝塔.md》（宝塔面板）

## 功能一览

- **URL 列表上传解析**：txt（每行一个）/ csv（含 `url` 列），自动去重、校验、提取商品 ID（F1）
- **四类资源提取**：`window.detailData.product.mediaItems` 主图/主图视频 + 描述 HTML 详情图/详情视频（F2）
- **媒体下载落盘**：`data/downloads/{task_id}/{product_id}/`，图片统一转 jpg（avif/webp 源）、视频保留 mp4（F3/F6）
- **manifest.json 清单**：商品 ID/标题/四类资源路径/抓取时间/状态（F4）
- **失败处理**：单商品失败不中断任务、429/5xx 指数退避、403 切换抓取策略、失败商品单独重试（F5）
- **任务管理**：创建/启动/暂停/取消/续跑（断点续传）、任务列表分页、历史记录（F7–F10）
- **实时进度与日志**：SSE 推送任务级/商品级进度与日志流（F11–F12）
- **结果下载**：全任务 zip 打包 / 单商品 zip（F13/F14）
- **反爬应对**：三层递进抓取（httpx → curl_cffi TLS 模拟 → Playwright）+ 内容级异常识别（403 降级 / 跳转页识别如实标记失败）

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.10+ · FastAPI · httpx · curl_cffi · lxml/BeautifulSoup4 · Pillow(+avif 插件) · Playwright（可选 L3） |
| 存储 | SQLite（`data/app.db`，零运维） |
| 前端 | Vue 3 · Vite · Element Plus · axios · vue-router |
| 测试 | pytest（引擎 49 + API 23，共 72 用例） |

## 快速开始

```bash
# 1) 后端（Python 3.10+）
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000   # 首次启动自动建表；托管 frontend/dist

# 2) 前端（开发模式，可选；生产构建产物已由后端托管）
cd frontend
npm install --registry=https://registry.npmmirror.com
npm run dev                                   # http://127.0.0.1:5173，/api 代理到 8000
```

访问 `http://127.0.0.1:8000/`：创建任务 → 上传 URL 列表 → 实时查看进度/日志 → 打包下载。

## 测试

```bash
cd backend
python -m pytest tests -q          # 全部 72 用例
python -m pytest tests/test_engine -q   # 引擎（提取/下载/反爬/命名）
python -m pytest tests/test_api -q      # API（任务/商品/下载/SSE）
```

## 目录结构

```text
backend/app/          # 后端：main/config/db/models/scheduler + api/ + engine/
backend/tests/        # 测试：test_engine / test_api
frontend/src/         # 前端：views/ components/ api/ router/
data/                 # 运行时（gitignore）：downloads/ app.db logs/
```

## 合规与已知限制

- 仅抓取**公开可见**数据，不登录、不破解验证码、不绕过付费墙；遵守目标站 robots.txt 与服务条款；素材版权归原权利人，产出仅限学习与研究等合法用途（详见《交付文档.md》§3.10）。
- 目标站 WAF 对无 cookie 首访返回 JS 跳转页：系统已做内容级识别并如实标记失败（不虚假成功）；真实商品抽样验收（A1/A2/A7）需在可达网络环境执行。
- L3 Playwright 兜底需 `playwright install chromium` 后启用（lazy import，不影响 L1/L2）。
