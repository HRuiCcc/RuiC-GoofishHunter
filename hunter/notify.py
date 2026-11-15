"""通知：把「发现了什么」讲成一条能立刻做决定的消息。

设计要点：
- 只在分数过线时发，不重复发（同一商品同一分数只发一次）；
- 消息里一定带「市场价 + 省了多少 + 卖家画像 + 该问什么」；
- 静默时段只入站内收件箱，不推手机。
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Optional

import httpx

from hunter.logbus import BUS


def in_quiet_hours(spec: str) -> bool:
    """spec 形如 23:30-08:00，跨午夜。"""
    try:
        start_text, end_text = spec.split("-")
        start = dtime.fromisoformat(start_text.strip())
        end = dtime.fromisoformat(end_text.strip())
    except (ValueError, AttributeError):
        return False
    now = datetime.now().time()
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def format_alert(item: dict, score: dict, *, base_url: str = "") -> tuple[str, str]:
    price = item.get("price") or 0
    median = score.get("market_median")
    discount = score.get("discount_pct")
    flags = score.get("flags") or []
    reasons = score.get("reasons") or []
    llm = score.get("llm") or {}

    lines = [f"{item.get('title', '')[:60]}"]
    price_line = f"¥{price:,.0f}"
    if median:
        price_line += f" · 中位 ¥{median:,.0f}"
    if discount:
        price_line += f" · 低 {discount:.0f}%"
    lines.append(price_line)
    if item.get("area"):
        lines.append(f"📍 {item['area']}" + (f" · {item['seller_nick']}" if item.get("seller_nick") else ""))
    detail_labels = item.get("labels_json") or {}
    if isinstance(detail_labels, dict):
        bits = [detail_labels.get(key) for key in ("成色", "拆修和功能", "存储容量") if detail_labels.get(key)]
        if bits:
            lines.append(" · ".join(bits))
    if reasons:
        lines.append("理由：" + "；".join(reasons[:3]))
    if flags:
        lines.append("注意：" + "、".join(flags[:4]))
    if llm.get("ask_seller"):
        lines.append(f"问卖家：{llm['ask_seller']}")
    if llm.get("summary"):
        lines.append(f"AI：{llm['summary']}")
    link = item.get("link") or f"https://www.goofish.com/item?id={item.get('item_id')}"
    lines.append(link)
    title = f"【{score.get('score', 0)}分·{score.get('verdict', '')}】{item.get('title', '')[:24]}"
    return title, "\n".join(lines)


def _channels(settings: dict[str, str]) -> list[str]:
    raw = settings.get("notify_channels") or ""
    return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]


async def send(title: str, body: str, settings: dict[str, str]) -> dict[str, bool]:
    channels = _channels(settings)
    if not channels:
        return {}
    results: dict[str, bool] = {}
    async with httpx.AsyncClient(timeout=12) as client:
        for channel in channels:
            try:
                results[channel] = await _send_one(client, channel, title, body, settings)
            except Exception as exc:  # noqa: BLE001
                results[channel] = False
                BUS.emit("warn", f"通知 {channel} 发送失败：{exc}")
    return results


async def _send_one(client: httpx.AsyncClient, channel: str, title: str, body: str,
                    settings: dict[str, str]) -> bool:
    if channel == "ntfy":
        url = settings.get("ntfy_url", "").strip()
        if not url:
            return False
        response = await client.post(url, content=body.encode("utf-8"),
                                     headers={"Title": title.encode("utf-8").decode("latin-1", "ignore"),
                                              "Tags": "moneybag"})
        return response.status_code < 300

    if channel == "bark":
        url = settings.get("bark_url", "").strip().rstrip("/")
        if not url:
            return False
        response = await client.post(f"{url}/{title}/{body}".replace("\n", " "),
                                     params={"group": "闲鱼猎手"})
        return response.status_code < 300

    if channel == "telegram":
        token = settings.get("telegram_token", "").strip()
        chat = settings.get("telegram_chat", "").strip()
        if not token or not chat:
            return False
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": f"{title}\n\n{body}", "disable_web_page_preview": False},
        )
        return response.status_code < 300

    if channel == "wecom":
        url = settings.get("wecom_url", "").strip()
        if not url:
            return False
        response = await client.post(url, json={
            "msgtype": "markdown",
            "markdown": {"content": f"**{title}**\n{body}"},
        })
        return response.status_code < 300 and (response.json().get("errcode") == 0)

    if channel == "webhook":
        url = settings.get("webhook_url", "").strip()
        if not url:
            return False
        response = await client.post(url, json={"title": title, "body": body})
        return response.status_code < 300

    return False


def digest_text(alerts: list[dict]) -> tuple[str, str]:
    lines = [f"本轮捡到 {len(alerts)} 条候选："]
    for entry in alerts[:8]:
        score = entry.get("score", {})
        item = entry.get("item", {})
        lines.append(
            f"· {score.get('score', 0)}分 ¥{item.get('price') or 0:,.0f} {item.get('title', '')[:28]}"
        )
    title = f"闲鱼猎手 · {len(alerts)} 条新候选"
    return title, "\n".join(lines)
