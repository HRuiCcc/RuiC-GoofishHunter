"""搜索参数测试：字符串必须和闲鱼页面真实发出去的一模一样。

fixture 来自 2026-11-15 实机点击筛选时抓到的请求体，见 docs/REVERSE-ENGINEERING.md。
"""
from hunter.goofish.query import SearchQuery


def test_default_filters_match_captured_request():
    query = SearchQuery(keyword="vivo x200 pro", personal_only=True, free_shipping=True)
    payload = query.payload(1)
    assert payload["propValueStr"]["searchFilter"] == "quickFilter:filterPersonal,filterFreePostage;"
    assert payload["sortField"] == "create"
    assert payload["sortValue"] == "desc"
    assert payload["fromFilter"] is True
    assert payload["pageNumber"] == 1
    assert payload["rowsPerPage"] == 30


def test_price_range_and_quick_filters_order():
    query = SearchQuery(
        keyword="vivo x200 pro", personal_only=True, free_shipping=True,
        min_price=2000, max_price=3000,
    )
    assert query.search_filter == (
        "priceRange:2000,3000;quickFilter:filterPersonal,filterFreePostage;"
    )


def test_min_price_only_uses_undefined():
    query = SearchQuery(keyword="x", personal_only=False, free_shipping=False, min_price=2000)
    assert query.search_filter == "priceRange:2000,undefined;"


def test_no_filters_default_sort():
    query = SearchQuery(keyword="x", personal_only=False, free_shipping=False, sort="default")
    payload = query.payload(2)
    assert payload["propValueStr"]["searchFilter"] == ""
    assert payload["fromFilter"] is False
    assert "sortField" not in payload
    assert payload["pageNumber"] == 2


def test_price_sort():
    query = SearchQuery(keyword="x", sort="price_asc", personal_only=False, free_shipping=False)
    payload = query.payload(1)
    assert payload["sortField"] == "price"
    assert payload["sortValue"] == "asc"
