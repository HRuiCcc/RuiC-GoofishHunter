"""可解释的捡漏打分。

核心立场：先算「值不值得看」，再决定要不要花 AI 的钱。
分数 = 价格偏离 + 成色 + 卖家可信度 + 新鲜度 - 风险扣分，每一项都能在界面上拆开看。
不做「每个商品一次大模型判定」：先把规则分算清楚，AI 只在头部候选上补充判断。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from hunter.models import MarketStats, ScoreResult, SellerInfo

# ---------------------------------------------------------------- 成色
CONDITION_GRADES: list[tuple[tuple[str, ...], float, str]] = [
    (("全新未拆封", "未拆封"), 1.0, "全新未拆封"),
    (("几乎全新", "99新", "99 新", "仅拆封"), 0.95, "几乎全新"),
    (("全新",), 1.0, "全新"),
    (("95新", "95 新"), 0.82, "95新"),
    (("9成新", "90新", "9 成新"), 0.66, "9成新"),
    (("8成新", "80新", "8 成新"), 0.46, "8成新"),
    (("7成新", "7 成新", "6成新", "5成新"), 0.25, "7成新及以下"),
]

REPAIR_OK = ("无任何维修", "无维修", "未拆修", "无拆修", "全原", "原装无修")
BAD_PATTERNS: list[tuple[str, str, int, bool]] = [
    (r"进水|泡水|水洗|进过水", "进水", 26, True),
    (r"非原装|组装机|拼装机|翻新机|高仿|山寨|黑机|克隆机", "非原装/仿品", 30, True),
    (r"有锁|卡贴|黑解|超雪|激活锁|id\s*锁", "有锁/卡贴机", 30, True),
    (r"主板.{0,4}(修|换)|换过主板|大修", "主板维修", 22, True),
    (r"拆修|维修过|修过|换过屏|换屏|换过电池|更换过|售后修|修过主板", "拆修记录", 13, False),
    (r"暗病|时好时坏|偶尔死机|无法开机|开不了机", "功能异常", 20, False),
    (r"仅.{0,4}(?:自提|面交)|只.{0,4}(?:自提|面交|出本地)|本地自提|同城自提|不邮寄|不出外地|外地不出|外地不(?:出|邮|发)", "仅自提", 9, False),
    (r"商家|贩子|工作室|批量|回收|长期收|代拍", "疑似商家", 12, False),
    (r"无锁|可验机|验货宝", "", 0, False),   # 命中也不扣，占位说明这些不是风险
]

ACCESSORY_RE = re.compile(
    r"摄影套装|套装|包装盒|原装包装|空盒|盒子|配件|手柄|镜头盖|保护壳|手机壳|贴膜|钢化膜|"
    r"支架|充电器|数据线|收纳|模型机|样机|展示机|零件|主板|屏幕总成|仅包装|不含手机"
)

BATTERY_RE = re.compile(r"电池(?:健康|健康度|容量)?\s*[:：]?\s*(\d{2,3})\s*%")
ACCE_RE = re.compile(r"箱说全|全套|原盒|配件齐|原装充电器|带包装")

VERDICT_STRONG = "强烈推荐"
VERDICT_WATCH = "值得看"
VERDICT_HOLD = "观望"
VERDICT_SKIP = "放弃"


def condition_grade(labels: dict[str, str], desc: str = "") -> tuple[float, str]:
    label_text = (labels.get("成色") or "").strip()
    haystack = f"{label_text} {desc[:120]}"
    for keys, grade, name in CONDITION_GRADES:
        if any(key in haystack for key in keys):
            return grade, name
    if label_text:
        return 0.6, label_text
    return 0.55, "未标注成色"


NEGATION_PREFIX = re.compile(r"[无未没不]|非商家|不是商家|个人非|谢绝|勿")
NEGATION_SUFFIX = re.compile(r"^.{0,4}(?:勿扰|勿来|别来|谢绝|勿拍|滚)")
SHIPPING_WORDS = re.compile(r"包邮|可邮|支持邮寄|发快递|顺丰|快递发货")


def _risk_scan(text: str) -> tuple[list[str], int, bool]:
    """扫风险词，但「无拆修 / 未进水 / 二手贩子勿扰」这类否定句不算风险。"""
    flags: list[str] = []
    penalty = 0
    hard = False
    for pattern, label, weight, is_hard in BAD_PATTERNS:
        if not label:
            continue
        hit = False
        for match in re.finditer(pattern, text, re.IGNORECASE):
            prefix = text[max(0, match.start() - 4):match.start()]
            suffix = text[match.end():match.end() + 6]
            if NEGATION_PREFIX.search(prefix) or NEGATION_SUFFIX.search(suffix):
                continue
            # 「同城也可自提」但明确支持邮寄的，不算仅自提
            if label == "仅自提" and SHIPPING_WORDS.search(text):
                continue
            hit = True
            break
        if hit:
            flags.append(label)
            penalty += weight
            hard = hard or is_hard
    return flags, penalty, hard


def seller_trust(seller: Optional[SellerInfo], item_count_hint: Optional[int] = None) -> tuple[float, list[str]]:
    if seller is None:
        return 0.5, ["卖家信息缺失"]
    notes: list[str] = []
    score = 0.5
    level = seller.credit_level
    if level is not None:
        score = {6: 0.92, 5: 0.84, 4: 0.74, 3: 0.52}.get(level, 0.55)
        if seller.credit_text:
            notes.append(seller.credit_text)
    if seller.zhima:
        score += 0.06
    if seller.real_name:
        score += 0.04
    if seller.reg_days is not None:
        if seller.reg_days >= 1200:
            score += 0.06
            notes.append(f"注册 {seller.reg_days / 365:.1f} 年")
        elif seller.reg_days < 90:
            score -= 0.16
            notes.append("新注册账号")
    if seller.reply_ratio is not None and seller.reply_ratio >= 80:
        score += 0.04
    many_items = item_count_hint if item_count_hint is not None else seller.item_count
    if many_items is not None and many_items >= 150:
        score -= 0.6
        notes.append(f"在售 {many_items} 件，像商家")
    elif many_items is not None and many_items >= 80:
        score -= 0.4
        notes.append(f"在售 {many_items} 件，像商家")
    return max(0.0, min(1.0, score)), notes


def _freshness_points(publish_at: Optional[str]) -> tuple[int, Optional[float]]:
    if not publish_at:
        return 0, None
    try:
        published = datetime.fromisoformat(publish_at)
    except ValueError:
        return 0, None
    hours = (datetime.now() - published).total_seconds() / 3600
    if hours < 0:
        return 0, 0.0
    if hours <= 2:
        return 6, hours
    if hours <= 8:
        return 4, hours
    if hours <= 24:
        return 2, hours
    if hours <= 72:
        return 0, hours
    return -2, hours


def score_item(
    *,
    title: str,
    price: Optional[float],
    market: MarketStats,
    labels: Optional[dict[str, str]] = None,
    desc: str = "",
    seller: Optional[SellerInfo] = None,
    publish_at: Optional[str] = None,
    want_cnt: Optional[int] = None,
    transport_fee: Optional[float] = None,
    keyword: str = "",
    spec: str = "",
) -> ScoreResult:
    labels = labels or {}
    reasons: list[str] = []
    flags: list[str] = []
    breakdown: dict[str, float] = {}
    score = 50.0

    # 1) 价格偏离（权重最大）
    discount = market.discount_pct(price)
    if discount is None or not market.ready:
        breakdown["价格"] = 0
        reasons.append(f"市场样本不足（{market.basis}），价格暂时无法比较")
    elif discount >= 0:
        points = min(32.0, discount / 25 * 32)      # 低于中位 25% 就吃满
        breakdown["价格"] = round(points, 1)
        reasons.append(
            f"比{market.basis.split(' · ')[0]} 中位价低 {discount:.1f}%"
            f"（¥{price:,.0f} vs ¥{market.median:,.0f}）"
        )
    else:
        points = max(-30.0, discount * 1.2)
        breakdown["价格"] = round(points, 1)
        reasons.append(f"比中位价高 {abs(discount):.1f}%，不是捡漏价")
    score += breakdown["价格"]

    # 2) 成色
    grade, grade_name = condition_grade(labels, desc)
    condition_points = (grade - 0.5) * 22
    breakdown["成色"] = round(condition_points, 1)
    score += condition_points
    if grade >= 0.9:
        reasons.append(f"成色标注「{grade_name}」")
    elif grade <= 0.46:
        reasons.append(f"成色只有「{grade_name}」，后续折价空间大")

    # 3) 卖家
    trust, seller_notes = seller_trust(seller)
    seller_points = (trust - 0.5) * 18
    breakdown["卖家"] = round(seller_points, 1)
    score += seller_points
    if trust >= 0.8:
        reasons.append("卖家画像像个人：" + "、".join(seller_notes or ["信用极好"]))
    elif trust <= 0.35:
        reasons.append("卖家可信度偏低：" + "、".join(seller_notes or ["信息不足"]))

    # 4) 新鲜度 / 竞争度
    fresh_points, age_hours = _freshness_points(publish_at)
    breakdown["新鲜度"] = fresh_points
    score += fresh_points
    if age_hours is not None and age_hours <= 2:
        reasons.append("刚发布不到 2 小时，还有议价空间")

    demand_points = 0
    if want_cnt is not None:
        if want_cnt >= 30:
            demand_points = -3
            reasons.append(f"{want_cnt} 人想要，抢的人多")
        elif want_cnt <= 1:
            demand_points = 2
    breakdown["竞争"] = demand_points
    score += demand_points

    # 5) 赠品与邮费
    extras = 0
    if transport_fee == 0:
        extras += 2
        flags.append("包邮")
    if ACCE_RE.search(desc or ""):
        extras += 2
        reasons.append("描述里有全套/原盒等完整度信息")
    battery = BATTERY_RE.search(desc or "")
    if battery:
        health = int(battery.group(1))
        if health >= 95:
            extras += 2
            reasons.append(f"电池健康 {health}%")
        elif health < 85:
            extras -= 6
            flags.append(f"电池{health}%偏低")
    version = labels.get("版本", "")
    if version and "国行" not in version:
        extras -= 4
        flags.append(f"{version}")
    breakdown["加分项"] = extras
    score += extras

    # 6) 风险
    haystack = (
        f"{title} {desc} {labels.get('拆修和功能', '')} "
        f"{labels.get('成色', '')} {labels.get('版本', '')}"
    )
    risk_flags, risk_penalty, hard = _risk_scan(haystack)
    repair_label = labels.get("拆修和功能", "")
    if repair_label and any(word in repair_label for word in REPAIR_OK):
        risk_penalty = max(0, risk_penalty - 4)
        reasons.append(f"拆修情况：{repair_label}")
    for flag in risk_flags:
        if flag not in flags:
            flags.append(flag)
    breakdown["风险"] = -risk_penalty
    score += breakdown["风险"]
    if risk_flags:
        reasons.append("风险信号：" + "、".join(risk_flags))

    # 7) 配件 / 非整机
    if ACCESSORY_RE.search(title) or (
        market.ready and price is not None and price < (market.median or 0) * 0.45
        and not re.search(r"\d+\s*[+＋]\s*\d{2,4}|\d{3,4}\s*G", title, re.IGNORECASE)
    ):
        if "疑似配件/非整机" not in flags:
            flags.append("疑似配件/非整机")
        score -= 45
        breakdown["整机"] = -45
        hard = True

    # 8) 标题与关键词是否对得上
    if keyword:
        tokens = [token for token in re.split(r"\s+", keyword.strip().lower()) if len(token) >= 3]
        if tokens and not any(token in title.lower() for token in tokens):
            flags.append("标题未命中关键词")
            score -= 8
            breakdown["匹配"] = -8

    final = int(max(0, min(100, round(score))))
    # 成色是硬约束：7 成新的机器再便宜也不该排在「强烈推荐」
    if grade <= 0.35:
        final = min(final, 60)
    elif grade <= 0.5:
        final = min(final, 74)

    if hard:
        final = min(final, 35)
        verdict = VERDICT_SKIP
    elif final >= 80:
        verdict = VERDICT_STRONG
    elif final >= 65:
        verdict = VERDICT_WATCH
    elif final >= 50:
        verdict = VERDICT_HOLD
    else:
        verdict = VERDICT_SKIP

    return ScoreResult(
        score=final,
        verdict=verdict,
        reasons=reasons,
        flags=flags,
        breakdown=breakdown,
        market=market,
        spec_key=spec or market.spec_key,
        discount_pct=discount,
    )
