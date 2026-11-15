"""市场基准：同规格、近 30 天、去极端值之后的中位价。

价格分不拿当前页均价硬算：12+256 和 16+512 混在一起不可比，一两个配件价就能把均价带偏。
这里做三件事：按规格分组、用中位数和四分位、样本不够就退回「全部」并明说依据。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from hunter.models import MarketStats


def percentile(values: list[float], ratio: float) -> float:
    """线性插值分位数：样本只有 2 个时也能给出合理的中间价。"""
    if not values:
        raise ValueError("empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * max(0.0, min(1.0, ratio))
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def trim_outliers(prices: list[float]) -> list[float]:
    """砍掉明显不是「整机」的极端值：低于中位数 35% 或高于 220%。"""
    if len(prices) < 5:
        return prices
    mid = percentile(prices, 0.5)
    if mid <= 0:
        return prices
    kept = [price for price in prices if mid * 0.35 <= price <= mid * 2.2]
    return kept or prices


def fmt_storage(bucket: str) -> str:
    if bucket.isdigit():
        size = int(bucket)
        if size >= 1024:
            return f"{size / 1024:g}TB"
        return f"{size}G"
    return bucket or "未知规格"


def build_market(
    samples: Iterable[tuple[float, str]],
    *,
    item_spec: str = "",
    min_samples: int = 4,
) -> MarketStats:
    buckets: dict[str, list[float]] = defaultdict(list)
    everything: list[float] = []
    for price, spec in samples:
        if price is None or price <= 0:
            continue
        everything.append(float(price))
        buckets[(spec or "").strip()].append(float(price))

    same_spec = buckets.get(item_spec.strip(), []) if item_spec else []
    if item_spec and len(same_spec) >= min_samples:
        prices, basis = same_spec, f"同规格 {fmt_storage(item_spec)} · {len(same_spec)} 个样本"
    else:
        prices = everything
        basis = f"全部在售 · {len(everything)} 个样本"

    prices = trim_outliers(prices)
    if not prices:
        return MarketStats(spec_key=item_spec, basis="样本不足")

    return MarketStats(
        count=len(prices),
        median=round(percentile(prices, 0.5), 2),
        p25=round(percentile(prices, 0.25), 2),
        p75=round(percentile(prices, 0.75), 2),
        minimum=round(min(prices), 2),
        maximum=round(max(prices), 2),
        spec_key=item_spec,
        basis=basis,
    )
