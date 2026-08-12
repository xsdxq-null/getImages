"""抓取引擎配置。CONTRACT.md 第 4.7 节。"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.anti_anti import USER_AGENTS


@dataclass
class EngineConfig:
    """引擎运行配置（由后端 app/config.py 组装后注入 Fetcher）。"""

    rate_limit: float = 2.0  # 秒/请求（全局最小间隔）
    concurrency: int = 2
    timeout: float = 30.0
    max_retries: int = 3
    user_agents: list[str] = field(default_factory=lambda: list(USER_AGENTS))
