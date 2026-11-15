"""浏览器会话：不是去「点页面」，而是把浏览器当成一台带签名的 API 网关。

为什么这么绕：
- 裸 HTTP 直连 mtop 会被风控拦（实测 ret = RGV587_ERROR::SM）；
- 但页面里的 `window.lib.mtop.request` 自带签名与安全头，能在页面内直接拿到 JSON；
- 于是每个账号只维持一个后台页面，搜索/详情/卖家全部走页面内 mtop 调用，
  不为每件商品开详情页、不点筛选按钮，这是整条链路能跑快的关键。
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Optional

from hunter.config import PATHS, RUNTIME
from hunter.goofish.errors import (
    ApiError,
    LoginRequired,
    RiskControl,
    TokenExpired,
)

HOME = "https://www.goofish.com/"
SEARCH_API = "mtop.taobao.idlemtopsearch.pc.search"
DETAIL_API = "mtop.taobao.idle.pc.detail"
SELLER_HEAD_API = "mtop.idle.web.user.page.head"

CALL_JS = """
async ({api, data, v}) => {
    if (!(window.lib && typeof window.lib.mtop === 'function')) {
        return {__err: 'NO_MTOP'};
    }
    try {
        const r = await window.lib.mtop.request({
            api, v: v || '1.0', type: 'post', dataType: 'json', data
        });
        return {ret: (r && r.ret) || [], data: (r && r.data) || null};
    } catch (e) {
        return {
            __err: 'MTOP_ERROR',
            ret: (e && e.ret) || [String((e && e.message) || e)],
            retJson: (e && e.retJson) || null
        };
    }
}
"""

RISK_MARKERS = (
    "RGV587",
    "FAIL_SYS_USER_VALIDATE",
    "FAIL_SYS_TRAFFIC_LIMIT",
    "FAIL_SYS_ILLEGAL_ACCESS",
    "USER_VALIDATE",
    "baxia",
    "FAIL_SYS_SM_",
)
TOKEN_MARKERS = (
    "FAIL_SYS_TOKEN_EXOIRED",
    "FAIL_SYS_TOKEN_EXPIRED",
    "FAIL_SYS_TOKEN_EMPTY",
    "TOKEN_EXOIRED",
    "TOKEN_EMPTY",
    "FAIL_SYS_SESSION_EXPIRED",
)


def _ret_text(result: dict) -> str:
    ret = result.get("ret") or []
    if isinstance(ret, str):
        return ret
    return " ".join(str(item) for item in ret)


def classify(result: dict) -> None:
    """把一次调用结果分类，正常返回则什么都不做。"""
    if result.get("__err") == "NO_MTOP":
        raise TokenExpired("页面里没有 mtop 库（可能被重定向或页面未加载完）")
    text = _ret_text(result)
    if not text:
        return
    if "SUCCESS" in text:
        return
    if any(marker in text for marker in RISK_MARKERS):
        raise RiskControl(text)
    if any(marker in text for marker in TOKEN_MARKERS):
        raise TokenExpired(text)
    if "FAIL_SYS_" in text or "FAIL_BIZ_" in text:
        raise ApiError(text)
    raise ApiError(text)


def _short_launch_error(message: str) -> str:
    lowered = message.lower()
    if "target page, context or browser has been closed" in lowered:
        return "该账号的浏览器 profile 已被其它 Edge 窗口占用（同一个 profile 只能开一个）"
    if "processsingleton" in lowered or "profile" in lowered and "in use" in lowered:
        return "浏览器 profile 正在被占用"
    return message.splitlines()[0][:160]


class BrowserHub:
    """进程内唯一的浏览器管理器：一个账号一个持久化上下文。"""

    def __init__(self) -> None:
        self._pw = None
        self._contexts: dict[str, Any] = {}
        self._pages: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_call: dict[str, float] = {}
        self._profile_locks: dict[str, Any] = {}

    # ------------------------------------------------------------------ 生命周期
    async def _ensure_playwright(self):
        if self._pw is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
        return self._pw

    async def context(self, account: str, *, headless: Optional[bool] = None):
        if account in self._contexts:
            return self._contexts[account]
        pw = await self._ensure_playwright()
        profile = PATHS.profiles / account
        profile.mkdir(parents=True, exist_ok=True)
        self._acquire_profile_lock(account, profile)
        state_file = PATHS.states / f"{account}.json"

        options: dict[str, Any] = {
            "user_data_dir": str(profile),
            "headless": RUNTIME.headless if headless is None else headless,
            "viewport": {"width": 1440, "height": 900},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if RUNTIME.proxy:
            options["proxy"] = {"server": RUNTIME.proxy}
        else:
            # 本机系统代理经常是关掉的 Clash 端口，浏览器会直接 ERR_PROXY_CONNECTION_FAILED
            options["args"].append("--no-proxy-server")
        try:
            ctx = await pw.chromium.launch_persistent_context(
                channel=RUNTIME.browser_channel, **options
            )
        except Exception as exc:
            message = str(exc).lower()
            if "channel" in message or "distribution" in message:
                options.pop("channel", None)
                ctx = await pw.chromium.launch_persistent_context(**options)
            else:
                self._release_profile_lock(account)
                reason = _short_launch_error(str(exc))
                raise RuntimeError(
                    f"浏览器启动失败（{account}）：{reason}。"
                    "如果另一个 hunter 进程或 Web 服务正在使用同一账号，请先停掉它。"
                ) from exc

        # 持久化目录本身会保存 cookie；这里再补一次导入的登录态（跨机器迁移也靠它）
        if state_file.exists():
            try:
                snapshot = json.loads(state_file.read_text(encoding="utf-8"))
                cookies = snapshot.get("cookies") if isinstance(snapshot, dict) else snapshot
                if cookies:
                    await ctx.add_cookies([c for c in cookies if c.get("name")])
            except Exception:  # noqa: BLE001
                pass

        self._contexts[account] = ctx
        self._locks[account] = asyncio.Lock()
        return ctx

    async def page(self, account: str):
        ctx = await self.context(account)
        page = self._pages.get(account)
        if page is None or page.is_closed():
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            self._pages[account] = page
        return page

    async def goto_home(self, account: str) -> None:
        page = await self.page(account)
        await page.goto(HOME, wait_until="domcontentloaded", timeout=45_000)
        await asyncio.sleep(random.uniform(1.0, 2.0))

    def _acquire_profile_lock(self, account: str, profile: Path) -> None:
        """同一账号的浏览器 profile 不能被两个进程同时打开。"""
        try:
            import fcntl
        except ImportError:
            return
        handle = (profile / ".hunter.lock").open("w")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError(
                f"账号 {account} 的浏览器正被另一个进程占用。"
                "请先停掉另一个 hunter 进程，或只保留 Web 服务在运行。"
            ) from exc
        self._profile_locks[account] = handle

    def _release_profile_lock(self, account: str) -> None:
        handle = self._profile_locks.pop(account, None)
        if handle is None:
            return
        try:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_UN)
        except Exception:  # noqa: BLE001
            pass
        handle.close()

    async def close(self, account: Optional[str] = None) -> None:
        if account:
            ctx = self._contexts.pop(account, None)
            self._pages.pop(account, None)
            if ctx:
                await ctx.close()
            self._release_profile_lock(account)
            return
        for name in list(self._contexts):
            await self.close(name)
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    # ------------------------------------------------------------------ 登录态
    async def login_state(self, account: str) -> dict:
        page = await self.page(account)
        try:
            cookies = await page.context.cookies()
        except Exception:
            return {"logged_in": False, "detail": "页面不可用"}
        names = {cookie.get("name") for cookie in cookies}
        logged_in = "unb" in names and "_m_h5_tk" in names
        return {
            "logged_in": logged_in,
            "cookies": len(cookies),
            "detail": "已登录" if logged_in else "缺少 unb / _m_h5_tk，需要扫码登录",
        }

    async def ensure_login(self, account: str) -> None:
        page = await self.page(account)
        if not str(page.url).startswith(HOME.rstrip("/")):
            await self.goto_home(account)
        state = await self.login_state(account)
        if not state["logged_in"]:
            await self.goto_home(account)
            state = await self.login_state(account)
            if not state["logged_in"]:
                raise LoginRequired(state["detail"])
        ready = await page.evaluate("() => !!(window.lib && typeof window.lib.mtop === 'function')")
        if not ready:
            await page.reload(wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            ready = await page.evaluate("() => !!(window.lib && typeof window.lib.mtop === 'function')")
            if not ready:
                raise LoginRequired("页面没有加载出 mtop 运行库")

    async def save_state(self, account: str) -> Path:
        ctx = await self.context(account)
        PATHS.ensure()
        target = PATHS.states / f"{account}.json"
        await ctx.storage_state(path=str(target))
        return target

    async def import_state(self, account: str, snapshot_path: str) -> int:
        """导入浏览器扩展导出的快照（cookies 数组或完整增强快照）。"""
        raw = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        cookies = raw.get("cookies", raw if isinstance(raw, list) else [])
        normalized = []
        for cookie in cookies:
            item = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie.get("domain") or ".goofish.com",
                "path": cookie.get("path") or "/",
            }
            if cookie.get("expires"):
                item["expires"] = float(cookie["expires"])
            if cookie.get("httpOnly") is not None:
                item["httpOnly"] = bool(cookie["httpOnly"])
            if cookie.get("secure") is not None:
                item["secure"] = bool(cookie["secure"])
            item["sameSite"] = cookie.get("sameSite") or "Lax"
            normalized.append(item)
        ctx = await self.context(account)
        await ctx.add_cookies(normalized)
        PATHS.ensure()
        preserved = {
            "cookies": normalized,
            "env": raw.get("env") if isinstance(raw, dict) else None,
            "meta": raw.get("meta") if isinstance(raw, dict) else None,
        }
        (PATHS.states / f"{account}.json").write_text(
            json.dumps({k: v for k, v in preserved.items() if v}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        return len(normalized)

    # ------------------------------------------------------------------ mtop 调用
    async def call(self, account: str, api: str, data: dict, *, retries: int = 1) -> dict:
        page = await self.page(account)
        async with self._locks[account]:
            await self._throttle(account)
            for attempt in range(retries + 1):
                try:
                    result = await page.evaluate(CALL_JS, {"api": api, "data": data})
                    classify(result)
                    return result
                except TokenExpired:
                    if attempt >= retries:
                        raise
                    await self._refresh_token(account, page)
                except (ApiError, RiskControl, LoginRequired):
                    raise
            raise ApiError("mtop 调用未返回结果")

    async def _throttle(self, account: str) -> None:
        last = self._last_call.get(account, 0.0)
        wait = RUNTIME.call_interval - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait + random.uniform(0, 0.15))
        self._last_call[account] = time.monotonic()

    async def _refresh_token(self, account: str, page) -> None:
        await asyncio.sleep(random.uniform(0.6, 1.2))
        try:
            if str(page.url).startswith(HOME.rstrip("/")):
                await page.reload(wait_until="domcontentloaded", timeout=30_000)
            else:
                await page.goto(HOME, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            await page.goto(HOME, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(random.uniform(1.0, 2.0))
        state = await self.login_state(account)
        if not state["logged_in"]:
            raise LoginRequired("刷新后仍未登录")
