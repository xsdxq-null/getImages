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
    cookie: str = ""  # 登录 cookie（可空；由 app.config 从环境变量 / data/cookie.txt 注入）
    login_state_path: str = ""  # playwright 登录态 storage state 文件（可空）
    proxy: str = ""  # 代理 server（playwright 不走系统代理；httpx/curl_cffi 自动读环境变量）
