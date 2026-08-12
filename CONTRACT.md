# getImages · 实施接口契约（CONTRACT）

> 本契约是三个并行实施单元（引擎 / 后端 API+任务 / 前端）的唯一对齐依据。
> 任何一方不得修改本契约中已定字段与签名；如需变更，先汇报集成方（主代理）。

## 1. 目录结构

```text
getImages/
├─ backend/
│  ├─ app/
│  │  ├─ main.py          # FastAPI 入口（挂路由 + 静态托管前端产物）
│  │  ├─ config.py        # 全局配置（含 EngineConfig 组装）
│  │  ├─ db.py            # SQLite 连接与建表
│  │  ├─ models.py        # 数据访问层（tasks/products/resources 表操作）
│  │  ├─ api/             # tasks.py / products.py / download.py
│  │  ├─ scheduler.py     # 异步任务调度器 + 日志中心
│  │  └─ engine/          # ── 引擎单元（A 实施）──
│  │     ├─ constants.py  # kind 常量、命名规则
│  │     ├─ anti_anti.py  # UA 池、指数退避、RateLimiter
│  │     ├─ fetcher.py    # 三层递进获取
│  │     ├─ extractor.py  # detailData / 描述 HTML 媒体提取
│  │     ├─ downloader.py # 下载、格式转换、断点续传、校验
│  │     └─ crawler.py    # 单商品抓取流水线（调度器唯一入口）
│  ├─ requirements.txt
│  └─ tests/
├─ frontend/              # ── 前端单元（C 实施）──
│  ├─ src/
│  │  ├─ views/           # TaskListView.vue / TaskDetailView.vue / CreateTaskView.vue
│  │  ├─ components/      # ProgressPanel.vue / LogStream.vue / MediaPreview.vue / ProductDialog.vue
│  │  ├─ api/             # axios 封装
│  │  └─ App.vue / main.js
│  ├─ package.json
│  └─ vite.config.js
├─ data/                  # 运行时（gitignore）：downloads/{task_id}/{product_id}/…、app.db、logs/
├─ CONTRACT.md
└─ 交付文档.md
```

## 2. 数据模型（SQLite，B 实施 db.py/models.py）

| 表 | 字段 |
| --- | --- |
| `tasks` | id INTEGER PK, name TEXT, url_file TEXT, status TEXT, total INTEGER, succeeded INTEGER, failed INTEGER, rate_limit REAL, concurrency INTEGER, created_at TEXT, started_at TEXT, finished_at TEXT |
| `products` | id INTEGER PK, task_id INTEGER FK, product_id TEXT, url TEXT, title TEXT, status TEXT, error TEXT, fetched_at TEXT |
| `resources` | id INTEGER PK, product_id INTEGER FK, kind TEXT, url TEXT, file_path TEXT, size INTEGER, status TEXT, retries INTEGER |

- `tasks.status`：`pending | running | paused | cancelled | done | partial`
- `products.status`：`pending | fetching | done | failed`
- `resources.status`：`pending | downloading | done | failed`
- 时间统一存 ISO 8601 字符串（UTC）。
- 日志不落库；SSE 从内存日志中心读。

## 3. API 契约（B 实施；C 按此联调）

| 方法 | 路径 | 请求 / 响应要点 |
| --- | --- | --- |
| POST | `/api/tasks` | multipart：`file`(txt/csv)、`name`、`rate_limit`(秒/请求,默认 2.0)、`concurrency`(默认 2)。返回 `{id, name, status, total, ...}` |
| GET | `/api/tasks` | 分页 `?page=1&page_size=20` → `{items:[...], total}`，items 含聚合：`total/succeeded/failed/progress`(0-100) |
| GET | `/api/tasks/{id}` | 任务详情 + 聚合进度 |
| POST | `/api/tasks/{id}/start` | pending → running |
| POST | `/api/tasks/{id}/pause` | running → paused |
| POST | `/api/tasks/{id}/cancel` | running/paused → cancelled |
| POST | `/api/tasks/{id}/resume` | paused/cancelled/done/partial → running（断点续传） |
| GET | `/api/tasks/{id}/products` | 分页 + `?status=` 过滤；items 含每商品四类资源完成计数 |
| GET | `/api/tasks/{id}/logs` | SSE：`data: {"ts","level","product_id","message"}`；先发缓冲内最后 200 条再持续推送 |
| GET | `/api/tasks/{id}/download` | 全任务 zip（运行中返回 409） |
| GET | `/api/products/{id}` | 单商品详情（含 resources 列表） |
| POST | `/api/products/{id}/retry` | 重试单个失败商品 |
| GET | `/api/products/{id}/download` | 单商品 zip（Could，实现简单则做） |

错误统一 `{"detail": "..."}`；成功 JSON 直接返回对象/数组。

## 4. 引擎接口（A 实施；B 的 scheduler 只依赖 crawler）

### 4.1 constants.py
```python
KIND_MAIN_IMAGE = "main_image"
KIND_DETAIL_IMAGE = "detail_image"
KIND_MAIN_VIDEO = "main_video"
KIND_DETAIL_VIDEO = "detail_video"

def resource_filename(kind: str, index: int) -> str
# main_image/detail_image: f"{prefix}_{index:03d}.jpg"（prefix=main/detail）
# main_video/detail_video: f"{prefix}_video_{index:02d}.mp4"
def product_id_from_url(url: str) -> str | None
# 取 URL 末段纯数字（至少 5 位），否则 None
def parse_url_list(text: str) -> list[str]
# 支持 txt 每行一个 / csv 含 url 列；去重保序；剔除非法
```

### 4.2 anti_anti.py
```python
def exponential_backoff(attempt: int, base: float = 2.0) -> float   # 2^n 秒
USER_AGENTS: list[str]  # ≥5 条真实 Chrome/Edge UA

class RateLimiter:      # 全局间隔限速（令牌桶/最小间隔）
    def __init__(self, min_interval: float): ...
    async def acquire(self) -> None
```

### 4.3 fetcher.py
```python
@dataclass
class FetchResult:
    status_code: int
    html: str
    final_url: str
    strategy: str        # "httpx" | "curl_cffi" | "playwright"

class Fetcher:
    def __init__(self, config: EngineConfig): ...
    async def fetch(self, url: str, referer: str | None = None) -> FetchResult
    # 三层递进：L1 httpx（完整浏览器头）→ L2 curl_cffi（TLS 模拟）→ L3 playwright(lazy import)
    # 403 不盲目重试，直接降级下一层；429/5xx 指数退避重试（最多 3 次）
    # playwright 未安装/浏览器缺失时抛 FetcherError 并说明，不影响 L1/L2
```

### 4.4 extractor.py
```python
@dataclass
class MediaSet:
    title: str | None
    main_images: list[str]
    main_videos: list[str]
    detail_images: list[str]
    detail_videos: list[str]

def extract_media(html: str, page_url: str) -> MediaSet
# 主图/主图视频：正则 window.detailData JSON → product.mediaItems
#   type=="image" 取 imageUrl.big 优先、normal 兜底；type=="video" 取视频 mp4 URL
# 详情图/详情视频：productHtmlDescription（lxml）中 <img> / <video> / mp4 链接
# 相对 URL 用 page_url 补齐（urllib.parse.urljoin）
```

### 4.5 downloader.py
```python
@dataclass
class DownloadResult:
    file_path: str
    size: int
    status: str          # "done" | "failed"
    skipped: bool        # 断点续传跳过
    converted: bool      # 是否格式转换
    error: str | None

async def download_media(url: str, dest_dir: Path, filename: str,
                         referer: str | None = None) -> DownloadResult
# httpx 流式下载，超时 30s；0 字节/大小异常视为失败
# 已存在且 size>0 → skipped=True（断点续传）
# 图片：avif/webp 源用 Pillow 转 jpg（avif 需 pillow-avif-plugin），失败保留原格式 converted=False
# 视频：保留 mp4 原格式
```

### 4.6 crawler.py（B 的调度器唯一入口）
```python
@dataclass
class CrawlResult:
    product_id: str
    title: str | None
    success: bool
    error: str | None
    resources: list[dict]   # [{kind, url, file_path, size, status}]

async def crawl_product(fetcher: Fetcher, url: str, dest_dir: Path,
                        referer: str | None = None) -> CrawlResult
# 流程：fetch → extract → 逐资源 download → 生成 manifest.json（字段：
# product_id/title/抓取时间/四类资源路径/status）→ CrawlResult
# 单资源失败不中断，记入 resources 的 status；整体是否成功由调用方判定
```

### 4.7 EngineConfig（A 定义于 engine/config.py，B 的 app/config.py 组装后注入）
```python
@dataclass
class EngineConfig:
    rate_limit: float = 2.0      # 秒/请求
    concurrency: int = 2
    timeout: float = 30.0
    max_retries: int = 3
    user_agents: list[str] = field(default_factory=lambda: USER_AGENTS)
```

## 5. 调度器与日志（B 实施）

```python
class TaskScheduler:
    def __init__(self, config): ...
    def start(self, task_id: int) -> None       # 异步后台任务，幂等
    def pause(self, task_id) -> None
    def cancel(self, task_id) -> None
    def resume(self, task_id) -> None
    def log(self, task_id: int, level: str, message: str, product_id: str | None = None) -> None
    def log_stream(self, task_id: int): ...     # 供 SSE 读取（内存 deque(maxlen=2000) + asyncio.Queue 广播）
```
- 每个商品：products.status=fetching → crawl_product → 更新 resources 行与 products 状态；
- 任务结束：done（全部成功/部分成功且无 failed）或 partial（存在 failed）；写 finished_at；
- 日志同时追加写 `data/logs/task_{id}.log`（文件日志，供历史回溯，不落库）；
- 暂停/取消：信号量检查点（每商品前后检查），取消后循环内抛 CancelledError 结束任务。

## 6. 前端约定（C 实施）

- Vue 3 + Vite + Element Plus + axios；路由 `vue-router`（Hash 模式，便于 FastAPI 静态托管）。
- 页面：任务列表（默认首页）/ 创建任务 / 任务详情（进度+商品列表+日志流+操作）/ 商品弹窗（四类资源 Tabs 预览）。
- SSE 用 `EventSource`（`/api/tasks/{id}/logs`），页面卸载时关闭。
- 上传：`el-upload` 拖拽 + 点击；上传前前端解析文件统计有效商品数（可调后端 `/api/tasks/parse` —— 若 B 未实现该端点则前端仅做格式提示，以后端创建响应为准）。
  - **简化**：B 实现 `POST /api/tasks/parse`（multipart file → {total, invalid, product_ids[]}）以便前端展示校验结果（PRD F1）。
- Vite dev 代理 `/api` → `http://127.0.0.1:8000`；生产构建产物 `frontend/dist` 由 FastAPI 静态托管。
- 依赖安装用 npmmirror 镜像：`npm install --registry=https://registry.npmmirror.com`。

## 7. 命名与目录（落盘，A 实施于 downloader/crawler）

`data/downloads/{task_id}/{product_id}/`：
| 资源 | 命名 |
| --- | --- |
| 主图 | `main_001.jpg` … |
| 详情图 | `detail_001.jpg` … |
| 主图视频 | `main_video_01.mp4` … |
| 详情视频 | `detail_video_01.mp4` … |
| 清单 | `manifest.json` |

## 8. 并行分工（禁止越界写）

- **A**：`backend/app/engine/**` + `backend/tests/test_engine/**`
- **B**：`backend/app/` 下除 `engine/` 的全部 + `backend/tests/test_api/**` + `backend/requirements.txt`
- **C**：`frontend/**`
- 集成方（主代理）：`CONTRACT.md`、`.gitignore`、`data/`、文档。
