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
        # 页面驱动：让闲鱼页面自己发搜索、我们只拦响应。
        # 前端改签名方式时直调会静默失效，这条路仍可用。
        payload = await self.hub.page_search(
            self.account,
            query.keyword,
            personal_only=query.personal_only,
            free_shipping=query.free_shipping,
            page_no=page,
        )
        return parsers.parse_search_page(payload, page)

    async def detail(self, item_id: str) -> Optional[ItemDetail]:
        payload = await self.hub.page_detail(self.account, str(item_id))
        if payload is None:
            # 页面偶尔没发出详情请求时，退回页面内直调
            payload = await self.hub.call(self.account, DETAIL_API, {"itemId": str(item_id)})
        return parsers.parse_detail(payload)

    async def seller_head(self, seller_id: str) -> Optional[SellerInfo]:
        payload = await self.hub.soft_call(self.account, SELLER_HEAD_API, {"userId": str(seller_id)})
        return parsers.parse_seller_head(payload) if payload else None
