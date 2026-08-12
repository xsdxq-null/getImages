"""全局配置（限速、并发、超时、重试、数据目录、日志目录）。

同时组装 engine.config.EngineConfig 供调度器注入 Fetcher（CONTRACT 第 4.7 节）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# backend/app/config.py → 项目根 getImages/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = BASE_DIR / "data"


@dataclass
class Settings:
    """后端全局配置。

    数据目录可通过环境变量 ``GETIMAGES_DATA_DIR`` 覆盖；
    测试通过 monkeypatch ``settings.data_dir`` 指向临时目录。
    """

    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("GETIMAGES_DATA_DIR") or DEFAULT_DATA_DIR))
    timeout: float = 30.0          # 单请求超时（秒）
    max_retries: int = 3           # 429/5xx 重试次数
    max_log_buffer: int = 2000     # 每任务内存日志缓冲条数（deque maxlen）
    default_rate_limit: float = 2.0   # 默认 秒/请求
    default_concurrency: int = 2      # 默认并发

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"


settings = Settings()


def build_engine_config(task: dict) -> "EngineConfig":
    """按任务参数（rate_limit/concurrency）组装 engine 的 EngineConfig。

    引擎为延迟导入（并行开发隔离）：engine 未就绪时退回同构的兜底 dataclass。
    """
    try:
        from app.engine.config import EngineConfig
    except ImportError:  # pragma: no cover - 引擎未就绪时的兜底
        from dataclasses import dataclass as _dc

        @_dc
        class EngineConfig:  # type: ignore[no-redef]
            rate_limit: float = 2.0
            concurrency: int = 2
            timeout: float = 30.0
            max_retries: int = 3
            user_agents: list = field(default_factory=list)

    return EngineConfig(
        rate_limit=float(task.get("rate_limit") or settings.default_rate_limit),
        concurrency=int(task.get("concurrency") or settings.default_concurrency),
        timeout=settings.timeout,
        max_retries=settings.max_retries,
    )
