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
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from hunter.config import PATHS, RUNTIME
from hunter.goofish.errors import (
    ApiError,
    LoginRequired,
    RiskControl,
    SessionStale,
    TokenExpired,
)

HOME = "https://www.goofish.com/"
SEARCH_PAGE = "https://www.goofish.com/search?q={keyword}"
SEARCH_RESPONSE_FRAGMENT = "/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/"
DETAIL_RESPONSE_FRAGMENT = "/h5/mtop.taobao.idle.pc.detail/1.0/"
NEXT_PAGE_SELECTOR = (
    "button[class*='search-pagination-arrow-container']"
    ":has([class*='search-pagination-arrow-right']):not([disabled])"
)
SEARCH_API = "mtop.taobao.idlemtopsearch.pc.search"
DETAIL_API = "mtop.taobao.idle.pc.detail"
SELLER_HEAD_API = "mtop.idle.web.user.page.head"

# 无头浏览器在闲鱼这边是「能用」的，但必须伪装成移动端页面：
# 桌面 UA 的登录页会直接判「非法访问」，而移动端 UA + 触摸仿真可以正常出搜索结果。
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)
MOBILE_VIEWPORT = {"width": 412, "height": 915}
DESKTOP_VIEWPORT = {"width": 1440, "height": 900}

INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}};
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters)
);
"""

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
    if "TIMEOUT::" in text or "接口超时" in text:
        raise SessionStale(text)
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


def _kill_profile_browsers(profile: Path) -> int:
    """清掉还占着这个 profile 的浏览器进程。

    服务被强杀（launchd -k、崩溃、终端关掉）时，Playwright 来不及关浏览器，
    残留进程会一直锁着 profile，之后每次抓取都报「profile 被占用」。
    只杀命令行里写明这一份 user-data-dir 的进程，不碰用户自己的浏览器。
    """
    marker = f"--user-data-dir={profile}"
    try:
        listing = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except Exception:  # noqa: BLE001
        return 0
    killed = 0
    for line in listing.splitlines():
        line = line.strip()
        if marker not in line:
            continue
        pid_text = line.split(None, 1)[0]
        if not pid_text.isdigit() or int(pid_text) == os.getpid():
            continue
        try:
            os.kill(int(pid_text), signal.SIGTERM)
            killed += 1
        except Exception:  # noqa: BLE001
            pass
    return killed


class BrowserHub:
    """进程内唯一的浏览器管理器：一个账号一个持久化上下文。"""

    def __init__(self) -> None:
        self._pw = None
        self._contexts: dict[str, Any] = {}
        self._pages: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # 整轮扫描的串行锁：多个关注同时触发时，不能让它们抢同一个页面
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._last_call: dict[str, float] = {}
        self._warmed: set[str] = set()
        # 命中风控后的冷却截止时间（monotonic），避免调度器每 5 分钟继续撞网关
        self._cooldown_until: dict[str, float] = {}
        self._profile_locks: dict[str, Any] = {}
        # 每个账号当前上下文的（是否无头, 是否可见），请求不一致时重建
        self._modes: dict[str, tuple[bool, bool]] = {}

    def session_lock(self, account: str) -> asyncio.Lock:
        return self._session_locks.setdefault(account, asyncio.Lock())

    def start_cooldown(self, account: str, seconds: int) -> None:
        self._cooldown_until[account] = time.monotonic() + max(0, seconds)

    # ------------------------------------------------------------------ 生命周期
    async def _ensure_playwright(self):
        if self._pw is None:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
        return self._pw

    async def context(
        self,
        account: str,
        *,
        headless: Optional[bool] = None,
        minimized: Optional[bool] = None,
        mobile: Optional[bool] = None,
    ):
        want_headless = RUNTIME.headless if headless is None else headless
        want_minimized = RUNTIME.minimize_browser if minimized is None else minimized
        # 无头抓取走移动端仿真；登录窗口保留桌面形态，方便扫码
        use_mobile = want_headless if mobile is None else mobile
        mode = (want_headless, not want_minimized, use_mobile)

        existing = self._contexts.get(account)
        if existing is not None:
            # 抓取要后台、扫码要可见：模式变了就把旧窗口关掉重建
            if self._modes.get(account) == mode:
                return existing
            await self.restart(account)

        pw = await self._ensure_playwright()
        profile = PATHS.profiles / account
        profile.mkdir(parents=True, exist_ok=True)
        # 先确认没有第二个 hunter 进程（fcntl 锁），再清掉上一轮被强杀后遗留的浏览器。
        # 顺序不能反：反了会把正在干活的另一个进程的浏览器杀掉。
        self._acquire_profile_lock(account, profile)
        _kill_profile_browsers(profile)
        for stale in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            try:
                (profile / stale).unlink()
            except FileNotFoundError:
                pass
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(0.3)
        state_file = PATHS.states / f"{account}.json"

        options: dict[str, Any] = {
            "user_data_dir": str(profile),
            "headless": want_headless,
            "viewport": MOBILE_VIEWPORT if use_mobile else DESKTOP_VIEWPORT,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if use_mobile:
            options.update(
                {
                    "user_agent": MOBILE_UA,
                    "device_scale_factor": 2.625,
                    "is_mobile": True,
                    "has_touch": True,
                }
            )
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
            elif "processsingleton" in message or ("profile" in message and "in use" in message):
                # 端口进程没了但浏览器还挂着：清干净后再拉一次
                _kill_profile_browsers(profile)
                await asyncio.sleep(2.0)
                try:
                    ctx = await pw.chromium.launch_persistent_context(
                        channel=RUNTIME.browser_channel, **options
                    )
                except Exception as retry_exc:  # noqa: BLE001
                    self._release_profile_lock(account)
                    raise RuntimeError(
                        f"浏览器启动失败（{account}）：{_short_launch_error(str(retry_exc))}。"
                        "已尝试清理残留浏览器仍不成功，请手动关掉占用该 profile 的 Edge。"
                    ) from retry_exc
            else:
                self._release_profile_lock(account)
                reason = _short_launch_error(str(exc))
                raise RuntimeError(
                    f"浏览器启动失败（{account}）：{reason}。"
                    "如果另一个 hunter 进程或 Web 服务正在使用同一账号，请先停掉它。"
                ) from exc

        if use_mobile:
            await ctx.add_init_script(INIT_SCRIPT)

        # 持久化目录本身会保存 cookie；这里再补一次导入的登录态（跨机器迁移也靠它）
        if state_file.exists():
            try:
                snapshot = json.loads(state_file.read_text(encoding="utf-8"))
                cookies = snapshot.get("cookies") if isinstance(snapshot, dict) else snapshot
                if cookies:
                    # 只补 profile 里缺的 cookie，绝不用旧快照覆盖浏览器刚刷新的 _m_h5_tk。
                    # 旧实现每次启动都整份覆盖，过期 token 会把好会话打回 TIMEOUT。
                    current = await ctx.cookies()
                    have = {(c.get("name"), c.get("domain")) for c in current}
                    missing = [
                        c for c in cookies
                        if c.get("name") and (c.get("name"), c.get("domain")) not in have
                    ]
                    if missing:
                        await ctx.add_cookies(missing)
            except Exception:  # noqa: BLE001
                pass

        self._contexts[account] = ctx
        self._locks.setdefault(account, asyncio.Lock())
        self._modes[account] = mode
        if want_minimized and not want_headless:
            # 先快速试两次，缩短窗口闪现；页面就绪后在 ensure_login 里再确保一次
            await self.minimize(account, attempts=2)
        return ctx

    async def minimize(self, account: str, attempts: int = 6) -> bool:
        """把窗口最小化到 Dock：抓取照常跑，屏幕和焦点都不被占用。

        macOS 上命令行窗口位置参数无效（实测会被系统拉回屏内）；
        窗口刚建好时 CDP 的 setWindowBounds 也可能被忽略，所以重试几次。
        """
        ctx = self._contexts.get(account)
        if ctx is None:
            return False
        for _ in range(max(1, attempts)):
            try:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                cdp = await ctx.new_cdp_session(page)
                try:
                    info = await cdp.send("Browser.getWindowForTarget")
                    window_id = info["windowId"]
                    await cdp.send(
                        "Browser.setWindowBounds",
                        {"windowId": window_id, "bounds": {"windowState": "minimized"}},
                    )
                    await asyncio.sleep(0.3)
                    state = await cdp.send("Browser.getWindowBounds", {"windowId": window_id})
                    if (state.get("bounds") or {}).get("windowState") == "minimized":
                        # 标记成后台模式，后续抓取直接复用这个已收起的窗口
                        headless_flag, mobile_flag = self._modes.get(account, (False, True))[:2]
                        self._modes[account] = (headless_flag, False, mobile_flag)
                        return True
                finally:
                    await cdp.detach()
            except Exception:  # noqa: BLE001
                # 窗口收不起来不该影响抓取，下一轮再试
                pass
            await asyncio.sleep(0.4)
        return False

    async def restart(self, account: str) -> None:
        """关掉卡死的上下文，下一次调用会重新拉起浏览器并加载页面。"""
        ctx = self._contexts.pop(account, None)
        self._pages.pop(account, None)
        self._modes.pop(account, None)
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:  # noqa: BLE001
                pass
        self._release_profile_lock(account)
        print(f"[session] 已重建 {account} 的浏览器会话")

    async def page(self, account: str):
        ctx = await self.context(account)
        page = self._pages.get(account)
        if page is None or page.is_closed():
            try:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            except Exception:  # noqa: BLE001
                # 缓存里的上下文已经失效（浏览器被系统关掉/崩溃），重建一次
                await self.restart(account)
                ctx = await self.context(account)
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
            # 上次进程被强杀时浏览器可能还活着占着 profile，先清掉再试
            if _kill_profile_browsers(profile):
                for _ in range(6):
                    time.sleep(0.5)
                    handle = (profile / ".hunter.lock").open("w")
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError:
                        handle.close()
                        continue
                    self._profile_locks[account] = handle
                    return
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
            self._modes.pop(account, None)
            self._warmed.discard(account)
            if ctx:
                await ctx.close()
            _kill_profile_browsers(PATHS.profiles / account)
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

    async def ensure_login(self, account: str, *, keyword: Optional[str] = None) -> None:
        remaining = self._cooldown_until.get(account, 0.0) - time.monotonic()
        if remaining > 0:
            raise RiskControl(f"风控冷却中，还需约 {int(remaining // 60) + 1} 分钟")
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
        await self.warmup(account, keyword=keyword)

    async def warmup(self, account: str, *, keyword: Optional[str] = None) -> None:
        """让页面自己发一次搜索请求，给 mtop 会话「通电」。

        实测：无头浏览器冷启动时直接调 window.lib.mtop.request 会被网关回
        TIMEOUT::接口超时；先让闲鱼页面自己完成一次搜索（它带的签名/安全头是齐的），
        之后同一页面里的直调就会变成 SUCCESS。这一步每个上下文只需做一次。
        """
        if account in self._warmed:
            return
        page = await self.page(account)
        if not str(page.url).startswith(HOME.rstrip("/")):
            await self.goto_home(account)
        await asyncio.sleep(random.uniform(0.6, 1.2))
        target = SEARCH_PAGE.format(keyword=quote(keyword or "iphone"))
        try:
            async with page.expect_response(
                lambda response: (
                    SEARCH_RESPONSE_FRAGMENT in response.url
                    and response.request.method == "POST"
                ),
                timeout=30_000,
            ):
                await page.goto(target, wait_until="domcontentloaded", timeout=45_000)
        except Exception as exc:  # noqa: BLE001
            if str(page.url).startswith(("https://passport.", "https://login.")):
                raise LoginRequired("预热时被跳转到登录页，登录态已失效") from exc
            raise LoginRequired(f"预热失败：页面没有发出搜索请求（{exc}）") from exc
        await asyncio.sleep(random.uniform(0.8, 1.6))
        if "passport.goofish.com" in page.url or "login.taobao.com" in page.url:
            raise LoginRequired("预热时被跳转到登录页，登录态已失效")
        self._warmed.add(account)
        print(f"[session] {account} 已预热（关键词 {keyword or 'iphone'}）")

    def _search_response(self, response) -> bool:
        return (
            SEARCH_RESPONSE_FRAGMENT in response.url
            and response.request.method == "POST"
        )

    async def page_search(
        self,
        account: str,
        keyword: str,
        *,
        personal_only: bool = False,
        free_shipping: bool = False,
        page_no: int = 1,
    ) -> dict:
        """页面驱动的搜索：导航 + 拦截响应，不依赖页面内直调的签名环境。"""
        page = await self.page(account)
        if not str(page.url).startswith(HOME.rstrip("/")):
            await self.goto_home(account)
        target = SEARCH_PAGE.format(keyword=quote(keyword))
        latest: Optional[dict] = None
        try:
            async with page.expect_response(self._search_response, timeout=30_000) as info:
                await page.goto(target, wait_until="domcontentloaded", timeout=45_000)
            latest = await (await info.value).json()
        except Exception as exc:  # noqa: BLE001
            if "passport" in page.url or "login" in page.url:
                raise LoginRequired("搜索页被跳转到登录，登录态已失效") from exc
            raise ApiError(f"页面搜索失败：{exc}") from exc

        ret_text = " ".join(str(item) for item in (latest.get("ret") or []))
        if any(marker in ret_text for marker in RISK_MARKERS):
            self._cooldown_until[account] = time.monotonic() + RUNTIME.cooldown_sec
            raise RiskControl(ret_text)

        await asyncio.sleep(random.uniform(1.0, 1.8))
        if personal_only:
            filtered = await self._click_filter(page, "个人闲置")
            if filtered:
                latest = filtered
        if free_shipping:
            filtered = await self._click_filter(page, "包邮")
            if filtered:
                latest = filtered

        for _ in range(max(0, page_no - 1)):
            try:
                async with page.expect_response(self._search_response, timeout=30_000) as info:
                    await page.locator(NEXT_PAGE_SELECTOR).first.click(timeout=8_000)
                latest = await (await info.value).json()
            except Exception:  # noqa: BLE001
                break
            await asyncio.sleep(random.uniform(0.8, 1.4))
        return latest or {}

    async def _click_filter(self, page, label: str) -> Optional[dict]:
        try:
            chip = page.get_by_text(label, exact=True).first
            if not await chip.count():
                return None
            async with page.expect_response(self._search_response, timeout=20_000) as info:
                await chip.click(timeout=5_000)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            return await (await info.value).json()
        except Exception:  # noqa: BLE001
            return None

    async def page_detail(self, account: str, item_id: str) -> Optional[dict]:
        """页面驱动的详情：为一件商品开一个临时页，拦详情响应后立刻关掉。"""
        ctx = await self.context(account)
        await self._throttle(account)
        page = await ctx.new_page()
        try:
            async with page.expect_response(
                lambda r: DETAIL_RESPONSE_FRAGMENT in r.url and r.request.method == "POST",
                timeout=30_000,
            ) as info:
                await page.goto(
                    f"https://www.goofish.com/item?id={item_id}",
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )
            return await (await info.value).json()
        except Exception:  # noqa: BLE001
            return None
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass

        # 有头兜底模式下，页面就绪后窗口一定存在了，这时再收一次
        mode = self._modes.get(account)
        if mode and not mode[0] and not mode[1]:
            await self.minimize(account)

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
    async def soft_call(self, account: str, api: str, data: dict) -> Optional[dict]:
        """只试一次：超时/风控就当没有，不重建浏览器、不设冷却。

        用于卖家主页这类「有最好、没有也能继续」的补充数据，不能因为它
        把整轮扫描停掉或把浏览器的搜索页关掉。
        """
        try:
            page = await self.page(account)
            async with self._locks[account]:
                await self._throttle(account)
                result = await page.evaluate(CALL_JS, {"api": api, "data": data})
            classify(result)
            return result
        except Exception:  # noqa: BLE001
            return None

    async def call(self, account: str, api: str, data: dict, *, retries: int = 1) -> dict:
        for attempt in range(retries + 1):
            try:
                page = await self.page(account)
                async with self._locks[account]:
                    await self._throttle(account)
                    result = await page.evaluate(CALL_JS, {"api": api, "data": data})
                classify(result)
                self._cooldown_until.pop(account, None)
                return result
            except SessionStale:
                await self.restart(account)
                await asyncio.sleep(2.0)
                if attempt >= retries:
                    raise RiskControl(
                        "接口连续超时，已重建浏览器；直调通道暂不可用，已改用页面驱动"
                    )
                try:
                    await self.ensure_login(account)
                except Exception:  # noqa: BLE001
                    pass
            except TokenExpired:
                await self._refresh_token(account, page)
                self._warmed.discard(account)
                if attempt >= retries:
                    raise
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
        self._warmed.discard(account)
        await self.warmup(account)
