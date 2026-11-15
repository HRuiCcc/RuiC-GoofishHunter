"""闲鱼数据接口：搜索 / 详情 / 卖家主页。"""
from __future__ import annotations

from typing import Optional

from hunter.goofish import parsers
from hunter.goofish.query import SearchQuery
from hunter.goofish.session import (
    DETAIL_API,
    SEARCH_API,
    SELLER_HEAD_API,
    BrowserHub,
)
from hunter.models import ItemCard, ItemDetail, SellerInfo


class GoofishAPI:
    def __init__(self, hub: BrowserHub, account: str) -> None:
        self.hub = hub
        self.account = account

    async def search_page(self, query: SearchQuery, page: int = 1) -> list[ItemCard]:
        payload = await self.hub.call(self.account, SEARCH_API, query.payload(page))
        return parsers.parse_search_page(payload, page)

    async def detail(self, item_id: str) -> Optional[ItemDetail]:
        payload = await self.hub.call(self.account, DETAIL_API, {"itemId": str(item_id)})
        return parsers.parse_detail(payload)

    async def seller_head(self, seller_id: str) -> Optional[SellerInfo]:
        payload = await self.hub.call(self.account, SELLER_HEAD_API, {"userId": str(seller_id)})
        return parsers.parse_seller_head(payload)
