"""一键登录工具：弹出真实浏览器窗口引导用户登录阿里巴巴，自动保存登录态。

用法（在 backend/ 目录下，先激活虚拟环境）：

    python -m app.engine.login

登录完成后自动生成（位于 data/，已被 .gitignore 忽略，敏感信息不入库）：

    data/cookie.txt          # name=value; ... 供 httpx / curl_cffi 快速层携带
    data/login_state.json    # playwright storage state 供浏览器层兜底

前置依赖：``pip install playwright && playwright install chromium``（一次性）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.config import settings

LOGIN_URL = "https://www.alibaba.com/"


async def _run() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:  # pragma: no cover - 环境缺失提示
        raise SystemExit(
            "playwright 未安装，请先执行：pip install playwright && playwright install chromium"
        ) from e

    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False)
        except Exception as e:  # pragma: no cover - 浏览器缺失提示
            raise SystemExit(
                "chromium 未安装，请先执行：playwright install chromium\n"
                f"（原始错误: {e}）"
            ) from e
        try:
            # 代理：playwright 不走系统代理，从 settings.proxy 读取（环境变量 PLAYWRIGHT_PROXY 等）
            context = await browser.new_context(
                proxy={"server": settings.proxy} if settings.proxy else None
            )
            page = await context.new_page()
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:  # pragma: no cover - 网络异常
            await browser.close()
            raise SystemExit(f"打开阿里巴巴页面失败: {e}") from e

        print(">>> 请在打开的浏览器窗口中登录阿里巴巴国际站（和平时上网一样）")
        print(">>> 登录成功后，回到本终端按回车键，保存登录态并退出")
        try:
            input()
        except EOFError:  # pragma: no cover - 非交互环境
            pass

        # cookie.txt：只取阿里巴巴主站域（.alibaba.com）的 cookie，避免跨域/同名 cookie
        # 冲突干扰（如多个 XSRF-TOKEN、login.alibaba.com 的会话 cookie）
        cookies = await context.cookies(
            urls=["https://www.alibaba.com/", "https://alibaba.com/"]
        )
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        (data_dir / "cookie.txt").write_text(cookie_str, encoding="utf-8")
        # login_state.json：保留全量 storage state（playwright 按域名自动匹配，无冲突问题）
        state = await context.storage_state()
        (data_dir / "login_state.json").write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
        await browser.close()

    print(">>> 登录态已保存：")
    print(f"    data/cookie.txt（{len(cookies)} 个 cookie）")
    print("    data/login_state.json")
    print(">>> 重启后端后即可抓取需登录的商品；cookie 过期后重跑本命令刷新。")


def main() -> None:
    try:
        asyncio.run(_run())
    except SystemExit as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pragma: no cover - 兜底
        print(f"登录失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
