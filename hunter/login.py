"""扫码登录：打开一个可见的浏览器窗口，等用户登完，自动存登录态。

不依赖浏览器扩展：点一次「打开登录窗口」，扫码后自动保存（cookie 落在 profile 目录里）。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from hunter.goofish.session import BrowserHub, HOME
from hunter.logbus import BUS


async def interactive_login(
    hub: BrowserHub,
    account: str,
    *,
    timeout: int = 300,
    poll: float = 2.0,
) -> dict:
    BUS.emit("info", f"正在打开登录窗口（{account}），请在浏览器里扫码…", account=account)
    ctx = await hub.context(account, headless=False)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    try:
        await page.goto(HOME, wait_until="domcontentloaded", timeout=45_000)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"打开页面失败：{exc}"}

    waited = 0.0
    while waited < timeout:
        state = await hub.login_state(account)
        if state["logged_in"]:
            await page.goto(HOME, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(1.5)
            if (await hub.login_state(account))["logged_in"]:
                path = await hub.save_state(account)
                BUS.emit("ok", f"登录成功，登录态已保存到 {path.name}", account=account)
                return {"ok": True, "state": str(path)}
        await asyncio.sleep(poll)
        waited += poll
        if int(waited) % 30 == 0:
            BUS.emit("info", f"仍在等待扫码（已等 {int(waited)} 秒）", account=account)
    BUS.emit("error", "登录超时，窗口未检测到登录态", account=account)
    return {"ok": False, "error": "登录超时"}


async def check_login(hub: BrowserHub, account: str) -> dict:
    try:
        ctx = await hub.context(account)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        if page.url in {"about:blank", ""}:
            await page.goto(HOME, wait_until="domcontentloaded", timeout=30_000)
        return await hub.login_state(account)
    except Exception as exc:  # noqa: BLE001
        return {"logged_in": False, "detail": str(exc)}
