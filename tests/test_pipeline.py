"""流水线集成测试：用假接口跑完整一轮，锁住「搜索→去重→详情→打分→入库」的契约。"""
import asyncio

import pytest

from hunter import repo
from hunter.models import ItemCard, ItemDetail, MarketStats, SellerInfo, Watch
from hunter.pipeline import Pipeline


class FakeHub:
    def __init__(self):
        self.calls = 0

    def session_lock(self, account):
        import asyncio
        return asyncio.Lock()

    async def ensure_login(self, account, keyword=None):
        self.calls += 1

    async def close(self, account=None):
        return None


class FakeAPI:
    def __init__(self, cards):
        self.cards = cards
        self.detail_calls = 0

    async def search_page(self, query, page=1):
        return self.cards if page == 1 else []

    async def detail(self, item_id):
        self.detail_calls += 1
        return ItemDetail(
            item_id=item_id,
            title=f"vivo X200 Pro 16+512 {item_id}",
            price=2200.0,
            desc="个人自用，全套箱说全，电池健康 96%，无拆修，包邮",
            labels={"成色": "几乎全新", "存储容量": "512GB", "运行内存": "16GB", "版本": "大陆国行"},
            want_cnt=2,
            browse_cnt=30,
            transport_fee=0,
            seller=SellerInfo(seller_id="9001", nick="个人玩家", credit_level=6,
                              credit_text="卖家信用极好", reg_days=1800, item_count=5,
                              reply_ratio=95, zhima=True, real_name=True),
        )

    async def seller_head(self, seller_id):
        return SellerInfo(seller_id=seller_id, credit_text="卖家信用极好", credit_level=6)


def _card(item_id, price):
    return ItemCard(item_id=item_id, title=f"vivo X200 Pro 16+512 {item_id}", price=price,
                    price_display=f"¥{price:.0f}", seller_id="encrypted", seller_nick="个人玩家",
                    area="江苏", want_cnt=2, link=f"https://www.goofish.com/item?id={item_id}")


def test_pipeline_end_to_end(fresh_db, monkeypatch):
    monkeypatch.setattr("hunter.pipeline.GoofishAPI", lambda hub, account: FakeAPI([]))
    watch = repo.watch_create(Watch(name="vivo", keyword="vivo x200 pro", pages=1,
                                    interval_sec=300, min_score=60, notify=False))

    # 先造一点历史价格，让市场基准成立
    for index, price in enumerate([2400, 2500, 2600, 2550]):
        item_id = f"seed-{index}"
        repo.item_upsert_card(_card(item_id, price))
        repo.snapshot_add(item_id, watch.id, price, 1)

    cards = [_card("1001", 2200), _card("1002", 3000)]
    pipeline = Pipeline(hub=FakeHub())
    monkeypatch.setattr("hunter.pipeline.GoofishAPI", lambda hub, account: FakeAPI(cards))

    result = asyncio.run(pipeline.run_watch(watch.id))
    assert result["status"] == "ok"
    assert result["found"] == 2
    assert result["new"] == 2
    assert result["scored"] == 2

    cheap = repo.score_get("1001", watch.id)
    pricey = repo.score_get("1002", watch.id)
    assert cheap and cheap["score"] > pricey["score"]
    assert cheap["discount_pct"] > 0

    item = repo.item_get("1001")
    assert item["spec_key"] == "16+512"
    assert item["labels_json"]["成色"] == "几乎全新"
    assert item["seller_id"] == "9001"      # 详情里的数字 ID 覆盖了列表里的加密 ID
    assert repo.snapshot_seen_in_watch("1001", watch.id)

    # 第二轮：同一批商品、价格没变 → 不重复抓详情、不重复评分
    result2 = asyncio.run(pipeline.run_watch(watch.id))
    assert result2["new"] == 0
    assert result2["scored"] == 0


def test_pipeline_marks_login_failure(fresh_db, monkeypatch):
    watch = repo.watch_create(Watch(name="vivo", keyword="vivo x200 pro"))

    class ExpiredHub(FakeHub):
        async def ensure_login(self, account, keyword=None):
            from hunter.goofish.errors import LoginRequired

            raise LoginRequired("cookies expired")

    pipeline = Pipeline(hub=ExpiredHub())
    result = asyncio.run(pipeline.run_watch(watch.id))
    assert result["status"] == "login"
    account = repo.account_get_by_name("default")
    assert account and account["status"] == "login"
    runs = repo.runs_list(1)
    assert runs[0]["status"] == "login"
