"""UI 冒烟：逐个点导航和关键交互，确认不是「点了没反应」。

用法：先起服务，然后
    .venv/bin/python scripts/ui_smoke.py [http://127.0.0.1:7801]
"""
import asyncio
import sys

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7801"
NAV = [("关注", "/watches"), ("商品库", "/items"), ("运行", "/runs"), ("设置", "/settings"), ("概览", "/")]
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok  " if ok else " FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(name)


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        await page.goto(BASE, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(800)
        check("首屏渲染", (await page.locator("h1").first.inner_text()) == "概览")

        for label, path in NAV:
            await page.get_by_role("link", name=label, exact=True).first.click()
            await page.wait_for_timeout(700)
            url_ok = page.url.rstrip("/") == (BASE + path).rstrip("/")
            check(f"导航 {label}", url_ok, page.url)

        await page.goto(f"{BASE}/items", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.locator("tbody tr").first.click()
        await page.wait_for_timeout(700)
        check("商品抽屉", await page.locator("[role=dialog]").count() > 0)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)

        await page.get_by_text("卡片", exact=True).first.click()
        await page.wait_for_timeout(600)
        check("卡片视图", await page.locator("article").count() > 0)

        await page.goto(f"{BASE}/settings", wait_until="networkidle")
        await page.wait_for_timeout(800)
        await page.get_by_text("保存通知", exact=False).first.click()
        await page.wait_for_timeout(1000)
        check("保存 Toast", await page.locator(".toast-item").count() > 0)

        check("无控制台错误", not errors, "; ".join(errors[:2]))
        await browser.close()

    if FAILURES:
        print(f"\n{len(FAILURES)} 项失败：" + "、".join(FAILURES))
        return 1
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
