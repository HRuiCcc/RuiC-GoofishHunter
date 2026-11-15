"""AI 复核：只在「值得看」以上的候选上调用，一次性问清三件事。

1. 这商品有没有描述里没写死的坑（暗病/翻新/货不对板）；
2. 还缺什么关键信息，需要问卖家什么；
3. 给一个和规则分对照的结论。

输出强制 JSON、失败即跳过 —— AI 是加分项，不是单点故障。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx

from hunter.models import ItemDetail, MarketStats, ScoreResult, SellerInfo

PROMPT_VERSION = "hunter-adj-1"

SYSTEM = """你是二手数码交易的老买家，擅长一眼看穿闲鱼商品描述里的坑。
你的任务不是复述参数，而是回答：这个价格 + 这条描述 + 这个卖家，值不值得去聊。
只输出 JSON，不要任何解释文字。"""

USER_TEMPLATE = """请评估这条闲鱼商品，输出严格 JSON：
{{
  "verdict": "buy|watch|skip",
  "confidence": 0.0-1.0,
  "condition": "你对实际成色的判断，一句话",
  "missing_info": ["必须问卖家才能确认的信息"],
  "risks": ["描述或图片里可能藏着的风险"],
  "ask_seller": "如果要私聊，第一句该问什么（一句话，具体）",
  "summary": "给买家的一句话结论"
}}

商品：{title}
标价：¥{price}
规格：{spec}
成色标签：{condition_label}
拆修标签：{repair_label}
卖家：{seller_desc}
市场：{market_desc}
规则打分：{score} 分（{verdict}），依据：{reasons}

描述：
{desc}
"""


def _api_key(settings: dict[str, str]) -> str:
    return (
        settings.get("llm_api_key")
        or os.getenv("HUNTER_LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )


def enabled(settings: dict[str, str]) -> bool:
    return settings.get("llm_enabled", "1") == "1" and bool(_api_key(settings))


def _seller_desc(seller: Optional[SellerInfo]) -> str:
    if not seller:
        return "未知"
    bits = [seller.nick or "匿名"]
    if seller.credit_text:
        bits.append(seller.credit_text)
    if seller.reg_days is not None:
        bits.append(f"注册 {seller.reg_days / 365:.1f} 年")
    if seller.item_count is not None:
        bits.append(f"在售 {seller.item_count} 件")
    if seller.reply_ratio is not None:
        bits.append(f"24h 回复率 {seller.reply_ratio:.0f}%")
    if seller.zhima:
        bits.append("芝麻认证")
    return "、".join(bits)


def _market_desc(market: MarketStats) -> str:
    if not market.ready:
        return market.basis or "样本不足"
    return (
        f"{market.basis}，中位 ¥{market.median:,.0f}，"
        f"四分位 ¥{market.p25:,.0f}–¥{market.p75:,.0f}"
    )


def build_prompt(
    *,
    title: str,
    price: Optional[float],
    detail: Optional[ItemDetail],
    seller: Optional[SellerInfo],
    market: MarketStats,
    result: ScoreResult,
) -> str:
    labels = detail.labels if detail else {}
    return USER_TEMPLATE.format(
        title=title,
        price=f"{price:,.0f}" if price else "未知",
        spec=detail.spec if detail else "",
        condition_label=labels.get("成色") or "未标注",
        repair_label=labels.get("拆修和功能") or "未标注",
        seller_desc=_seller_desc(seller),
        market_desc=_market_desc(market),
        score=result.score,
        verdict=result.verdict,
        reasons="；".join(result.reasons[:6]),
        desc=(detail.desc if detail else "")[:1200] or "（无描述）",
    )


def parse_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


async def adjudicate(
    *,
    title: str,
    price: Optional[float],
    detail: Optional[ItemDetail],
    seller: Optional[SellerInfo],
    market: MarketStats,
    result: ScoreResult,
    settings: dict[str, str],
) -> Optional[dict[str, Any]]:
    if not enabled(settings):
        return None
    base_url = (settings.get("llm_base_url") or "https://api.deepseek.com").rstrip("/")
    model = settings.get("llm_model") or "deepseek-flash"
    prompt = build_prompt(
        title=title, price=price, detail=detail, seller=seller, market=market, result=result
    )
    body = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {_api_key(settings)}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{base_url}/chat/completions", json=body, headers=headers
            )
            response.raise_for_status()
            payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        parsed = parse_json(content)
        if not parsed:
            return None
        parsed["prompt_version"] = PROMPT_VERSION
        parsed["model"] = model
        parsed["confidence"] = float(parsed.get("confidence") or 0)
        for key in ("missing_info", "risks"):
            if not isinstance(parsed.get(key), list):
                parsed[key] = []
        return parsed
    except Exception as exc:  # noqa: BLE001 - AI 失败不应该打断采集
        return {"error": f"{type(exc).__name__}: {exc}", "prompt_version": PROMPT_VERSION}
