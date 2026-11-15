"""领域模型：贯穿抓取、打分、展示三层的稳定结构。

刻意不用 ORM —— 这个系统的查询都是「按分数排序 + 时间窗口聚合」，
写 SQL 比绕 ORM 更清楚，也更容易在测试里造假数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Watch:
    id: Optional[int] = None
    name: str = ""
    keyword: str = ""
    account_id: Optional[int] = None
    sort: str = "newest"            # newest | price_asc | price_desc | default
    pages: int = 2
    page_size: int = 30
    personal_only: bool = True
    free_shipping: bool = True
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_score: int = 60             # 超过这个分数才推送
    interval_sec: int = 300
    enabled: bool = True
    use_llm: bool = True
    notify: bool = True
    note: str = ""
    created_at: str = field(default_factory=now_iso)
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "Watch":
        data = dict(row)
        return cls(
            id=data["id"],
            name=data["name"],
            keyword=data["keyword"],
            account_id=data.get("account_id"),
            sort=data.get("sort") or "newest",
            pages=int(data.get("pages") or 2),
            page_size=int(data.get("page_size") or 30),
            personal_only=bool(data.get("personal_only")),
            free_shipping=bool(data.get("free_shipping")),
            min_price=data.get("min_price"),
            max_price=data.get("max_price"),
            min_score=int(data.get("min_score") or 60),
            interval_sec=int(data.get("interval_sec") or 300),
            enabled=bool(data.get("enabled")),
            use_llm=bool(data.get("use_llm")),
            notify=bool(data.get("notify")),
            note=data.get("note") or "",
            created_at=data.get("created_at") or now_iso(),
            last_run_at=data.get("last_run_at"),
            next_run_at=data.get("next_run_at"),
        )


@dataclass
class ItemCard:
    """搜索列表里的一张卡，字段都来自列表接口，不需要进详情页。"""
    item_id: str
    title: str
    price: Optional[float]
    price_display: str = ""
    original_price: Optional[float] = None
    area: str = ""
    seller_id: str = ""
    seller_nick: str = ""
    publish_at: Optional[str] = None
    pic: str = ""
    pics: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    category_id: str = ""
    want_cnt: Optional[int] = None
    link: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class SellerInfo:
    seller_id: str
    nick: str = ""
    city: str = ""
    reg_days: Optional[int] = None
    item_count: Optional[int] = None
    sold_count: Optional[int] = None
    credit_level: Optional[int] = None
    credit_text: str = ""
    zhima: bool = False
    real_name: bool = False
    reply_ratio: Optional[float] = None
    good_ratio: Optional[float] = None
    rate_total: Optional[int] = None
    tags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class ItemDetail:
    item_id: str
    title: str = ""
    price: Optional[float] = None
    original_price: Optional[float] = None
    desc: str = ""
    area: str = ""
    city: str = ""
    publish_at: Optional[str] = None
    want_cnt: Optional[int] = None
    browse_cnt: Optional[int] = None
    collect_cnt: Optional[int] = None
    sold_cnt: Optional[int] = None
    quantity: Optional[int] = None
    bargained: bool = False
    transport_fee: Optional[float] = None
    status: str = ""
    category_id: str = ""
    images: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    label_pairs: list[tuple[str, str]] = field(default_factory=list)
    seller: Optional[SellerInfo] = None
    raw: dict = field(default_factory=dict)

    @property
    def spec(self) -> str:
        """规格指纹：优先用闲鱼结构化标签，其次从标题里抠。返回如 16+512 / 512G。"""
        storage = self.labels.get("存储容量", "")
        ram = self.labels.get("运行内存", "")
        if ram or storage:
            ram_num = _first_int(ram)
            storage_num = _first_int(storage)
            unit = "T" if "T" in storage.upper() else ""
            if ram_num and storage_num:
                return f"{ram_num}+{storage_num}{unit}"
            if storage_num:
                return f"{storage_num}{unit}"
        return ""

    @property
    def condition(self) -> str:
        return self.labels.get("成色", "") or ""

    @property
    def repair(self) -> str:
        return self.labels.get("拆修和功能", "") or ""


@dataclass
class MarketStats:
    count: int = 0
    median: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    spec_key: str = ""
    basis: str = ""                 # 说明这份统计是按什么维度算的

    @property
    def ready(self) -> bool:
        return self.count >= 3 and self.median is not None

    def discount_pct(self, price: Optional[float]) -> Optional[float]:
        if price is None or not self.median:
            return None
        return round((self.median - price) / self.median * 100, 1)


@dataclass
class ScoreResult:
    score: int
    verdict: str                   # 强烈推荐 / 值得看 / 观望 / 放弃
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)
    market: Optional[MarketStats] = None
    spec_key: str = ""
    discount_pct: Optional[float] = None


def _first_int(text: str) -> Optional[int]:
    import re

    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None
