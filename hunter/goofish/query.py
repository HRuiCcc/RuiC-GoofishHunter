"""搜索条件 → mtop 请求体。

这些参数是从真实页面点筛选时抓下来的（见 docs/REVERSE-ENGINEERING.md）：
  - 个人闲置：propValueStr.searchFilter = "quickFilter:filterPersonal;"
  - 包邮：    ... = "quickFilter:filterFreePostage;"
  - 价格区间：... = "priceRange:2000,3000;quickFilter:...;"
  - 最新发布：sortField=create, sortValue=desc
知道这些之后就不需要点页面上的按钮了。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SORT_FIELDS = {
    "newest": ("create", "desc"),
    "price_asc": ("price", "asc"),
    "price_desc": ("price", "desc"),
    "default": ("", ""),
}


@dataclass
class SearchQuery:
    keyword: str
    sort: str = "newest"
    personal_only: bool = True
    free_shipping: bool = True
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    page_size: int = 30

    @property
    def search_filter(self) -> str:
        parts: list[str] = []
        if self.min_price is not None or self.max_price is not None:
            low = _num(self.min_price) or "undefined"
            high = _num(self.max_price) or "undefined"
            parts.append(f"priceRange:{low},{high}")
        quick: list[str] = []
        if self.personal_only:
            quick.append("filterPersonal")
        if self.free_shipping:
            quick.append("filterFreePostage")
        if quick:
            parts.append("quickFilter:" + ",".join(quick))
        return ";".join(parts) + (";" if parts else "")

    def payload(self, page: int) -> dict:
        sort_field, sort_value = SORT_FIELDS.get(self.sort, ("", ""))
        has_filter = bool(self.search_filter) or bool(sort_field)
        payload = {
            "pageNumber": page,
            "keyword": self.keyword,
            "fromFilter": has_filter,
            "rowsPerPage": self.page_size,
            "searchReqFromPage": "pcSearch",
            "extraFilterValue": "{}",
            "userPositionJson": "{}",
        }
        if sort_field:
            payload["sortField"] = sort_field
            payload["sortValue"] = sort_value
        # 点过筛选才会带这个字段；空串也是合法值
        payload["propValueStr"] = {"searchFilter": self.search_filter}
        return payload


def _num(value: Optional[float]) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"
