"""通知文案测试：一条推送必须能让人立刻做决定。"""
from hunter.notify import digest_text, format_alert, in_quiet_hours


def test_alert_contains_price_market_and_question():
    item = {
        "item_id": "1001",
        "title": "个人自用 vivo X200 Pro 16+512 几乎全新",
        "price": 2200,
        "area": "江苏",
        "seller_nick": "小明",
        "labels_json": {"成色": "几乎全新", "拆修和功能": "无任何维修"},
        "link": "https://www.goofish.com/item?id=1001",
    }
    score = {
        "score": 88,
        "verdict": "强烈推荐",
        "market_median": 2699,
        "discount_pct": 18.5,
        "reasons": ["比同规格 512G 中位价低 18.5%"],
        "flags": ["包邮"],
        "llm": {"ask_seller": "电池健康还有多少？", "summary": "值得聊"},
    }
    title, body = format_alert(item, score)
    assert "88分" in title
    assert "¥2,200" in body
    assert "中位 ¥2,699" in body
    assert "低 19%" in body or "低 18%" in body
    assert "几乎全新" in body
    assert "电池健康还有多少" in body
    assert "goofish.com/item" in body


def test_digest_lists_candidates():
    alerts = [
        {"score": {"score": 90}, "item": {"price": 2200, "title": "A"}},
        {"score": {"score": 70}, "item": {"price": 2600, "title": "B"}},
    ]
    title, body = digest_text(alerts)
    assert "2 条" in title
    assert "90分" in body and "70分" in body


def test_quiet_hours_parsing_is_defensive():
    assert in_quiet_hours("") is False
    assert in_quiet_hours("not-a-range") is False
    # 全天区间
    assert in_quiet_hours("00:00-23:59") is True
