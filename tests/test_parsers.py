"""解析器测试：直接喂真实接口响应，字段一改这里先红。"""
import json

from hunter.goofish import parsers


def _load(fixtures_dir, name):
    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


def test_parse_search_page(fixtures_dir):
    payload = _load(fixtures_dir, "search_page1.json")
    cards = parsers.parse_search_page(payload, 1)
    assert len(cards) == 6
    first = cards[0]
    assert first.item_id
    assert first.title
    assert first.price and first.price > 0
    assert first.seller_id
    assert first.link.startswith("https://www.goofish.com/")
    assert "包邮" in first.tags
    assert first.publish_at and len(first.publish_at) == 16


def test_parse_detail_labels_and_spec(fixtures_dir):
    payload = _load(fixtures_dir, "detail_item.json")
    detail = parsers.parse_detail(payload)
    assert detail is not None
    assert detail.item_id
    assert detail.labels.get("成色") == "几乎全新"
    assert detail.labels.get("拆修和功能") == "无任何维修"
    assert detail.spec == "16+512"
    assert detail.desc
    assert len(detail.images) >= 1
    assert detail.seller is not None
    assert detail.seller.seller_id
    assert detail.seller.reply_ratio is not None


def test_parse_seller_head(fixtures_dir):
    payload = _load(fixtures_dir, "seller_head.json")
    seller = parsers.parse_seller_head(payload)
    assert seller is not None
    assert seller.credit_level == 4
    assert seller.credit_text == "卖家信用优秀"
    assert seller.real_name is True


def test_spec_from_text():
    assert parsers.spec_from_text("16+512 黑色") == "16+512"
    assert parsers.spec_from_text("12＋256G 国行") == "12+256"
    assert parsers.spec_from_text("存储 256GB 全网通") == "256G"
    assert parsers.spec_from_text("没有规格") == ""


def test_as_float_handles_wan_and_currency():
    assert parsers.as_float("¥2,498") == 2498
    assert parsers.as_float("1.2万") == 12000
    assert parsers.as_float("暂无") is None
