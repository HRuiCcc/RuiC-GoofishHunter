"""数据层测试：全局去重、快照只在变价时记、评分按关注隔离。"""
from hunter import repo
from hunter.models import ItemCard, ScoreResult, MarketStats, Watch


def _watch(name="vivo"):
    return repo.watch_create(Watch(name=name, keyword="vivo x200 pro", interval_sec=300))


def _card(item_id="1001", price=2400.0, title="vivo X200 Pro 16+512"):
    return ItemCard(item_id=item_id, title=title, price=price, price_display=f"¥{price:.0f}",
                    seller_id="s1", seller_nick="小明", area="江苏", want_cnt=3)


def test_watch_crud(fresh_db):
    watch = _watch()
    assert watch.id
    assert repo.watch_get(watch.id).name == "vivo"
    repo.watch_update(watch.id, {"min_score": 75, "enabled": False})
    updated = repo.watch_get(watch.id)
    assert updated.min_score == 75 and updated.enabled is False
    repo.watch_delete(watch.id)
    assert repo.watch_get(watch.id) is None


def test_item_is_globally_deduped(fresh_db):
    watch = _watch()
    assert repo.item_upsert_card(_card()) is True
    assert repo.item_upsert_card(_card()) is False
    assert repo.items_count() == 1
    assert repo.snapshot_seen_in_watch("1001", watch.id) is False
    repo.snapshot_add("1001", watch.id, 2400, 3)
    assert repo.snapshot_seen_in_watch("1001", watch.id) is True


def test_market_prices_only_include_watch_items(fresh_db):
    watch = _watch()
    repo.item_upsert_card(_card("1001", 2400))
    repo.item_upsert_card(_card("1002", 2600))
    repo.snapshot_add("1001", watch.id, 2400, 1)
    repo.snapshot_add("1002", watch.id, 2600, 1)
    prices = repo.market_prices(watch.id)
    assert sorted(price for price, _ in prices) == [2400.0, 2600.0]


def test_scores_are_isolated_per_watch(fresh_db):
    w1, w2 = _watch("a"), _watch("b")
    repo.item_upsert_card(_card())
    repo.score_upsert("1001", w1.id, ScoreResult(score=88, verdict="强烈推荐",
                                                 market=MarketStats(count=5, median=2600)))
    repo.score_upsert("1001", w2.id, ScoreResult(score=40, verdict="观望",
                                                 market=MarketStats(count=2, median=3000)))
    rows = repo.items_list(watch_id=w1.id, limit=10)
    assert len(rows) == 1 and rows[0]["score"] == 88
    assert repo.score_get("1001", w2.id)["score"] == 40


def test_items_list_orders_by_score(fresh_db):
    watch = _watch()
    for item_id, score in (("1001", 50), ("1002", 90), ("1003", 70)):
        repo.item_upsert_card(_card(item_id))
        repo.score_upsert(item_id, watch.id, ScoreResult(score=score, verdict="观望"))
    rows = repo.items_list(watch_id=watch.id, limit=10)
    assert [row["score"] for row in rows] == [90, 70, 50]


def test_feedback_roundtrip(fresh_db):
    repo.item_upsert_card(_card())
    repo.item_set_feedback("1001", "good", "已聊，卖家爽快")
    item = repo.item_get("1001")
    assert item["feedback"] == "good"
    assert item["feedback_note"] == "已聊，卖家爽快"


def test_overview_counts(fresh_db):
    watch = _watch()
    repo.item_upsert_card(_card())
    repo.score_upsert("1001", watch.id, ScoreResult(score=80, verdict="值得看"))
    stats = repo.overview_stats()
    assert stats["total_items"] == 1
    assert stats["active_watches"] == 1
    assert stats["by_verdict"]["值得看"] == 1
