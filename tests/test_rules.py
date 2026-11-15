"""打分规则测试：好货要高分、硬伤要劝退、贵货不能装便宜。"""
from hunter.models import MarketStats, SellerInfo
from hunter.scoring.rules import condition_grade, score_item, seller_trust


def _market(median=2600.0, count=8):
    return MarketStats(count=count, median=median, p25=2400, p75=2800,
                       minimum=2100, maximum=3200, basis=f"同规格 16+512 · {count} 个样本")


def _seller(**kwargs):
    base = dict(
        seller_id="1", nick="个人玩家", credit_level=6, credit_text="卖家信用极好",
        reg_days=2000, item_count=6, reply_ratio=92, zhima=True, real_name=True,
    )
    base.update(kwargs)
    return SellerInfo(**base)


def test_cheap_almost_new_good_seller_scores_high():
    result = score_item(
        title="vivo X200 Pro 16+512 几乎全新",
        price=2100,
        market=_market(),
        labels={"成色": "几乎全新", "拆修和功能": "无任何维修", "版本": "大陆国行"},
        desc="全套箱说全，电池健康 98%，无拆修",
        seller=_seller(),
        publish_at=None,
        want_cnt=2,
        transport_fee=0,
        keyword="vivo x200 pro",
        spec="16+512",
    )
    assert result.score >= 75, result
    assert result.verdict in {"强烈推荐", "值得看"}
    assert "比同规格 16+512 中位价低" in " ".join(result.reasons)
    assert result.discount_pct and result.discount_pct > 15


def test_water_damage_is_hard_skip():
    result = score_item(
        title="vivo X200 Pro 进水过",
        price=1200,
        market=_market(),
        labels={"成色": "9成新"},
        desc="之前进过水，现在正常使用",
        seller=_seller(),
        keyword="vivo x200 pro",
    )
    assert "进水" in result.flags
    assert result.verdict == "放弃"


def test_locked_overseas_model_is_hard_skip():
    result = score_item(
        title="出一台苹果17pro 256G 美版超雪内置卡贴",
        price=4880,
        market=_market(median=6800),
        labels={"成色": "几乎全新", "版本": "海外有锁"},
        desc="全原装，插卡即用，顺丰包邮",
        seller=_seller(),
        keyword="iphone 17 pro",
    )
    assert "有锁/卡贴机" in result.flags
    assert result.verdict == "放弃"
    assert result.score <= 60


def test_accessory_listing_is_hard_skip():
    result = score_item(
        title="全新 vivo X300 Pro 摄影师套装 原装包装",
        price=1100,
        market=_market(median=4100),
        labels={},
        desc="原装包装盒，不含手机",
        seller=_seller(),
        keyword="vivo x300 pro",
    )
    assert "疑似配件/非整机" in result.flags
    assert result.verdict == "放弃"
    assert result.score <= 35


def test_overpriced_scores_low():
    result = score_item(
        title="vivo X200 Pro 16+512",
        price=3400,
        market=_market(),
        labels={"成色": "几乎全新"},
        desc="",
        seller=_seller(),
        keyword="vivo x200 pro",
    )
    assert result.score < 60
    assert "高" in " ".join(result.reasons)


def test_merchant_signals_penalized():
    result = score_item(
        title="vivo X200 Pro 全新未拆封 批量出",
        price=2300,
        market=_market(),
        labels={"成色": "全新未拆封"},
        desc="工作室批量，长期收售",
        seller=_seller(item_count=200),
        keyword="vivo x200 pro",
    )
    assert "疑似商家" in result.flags
    trust, _ = seller_trust(_seller(item_count=200))
    assert trust < 0.6


def test_condition_grade_unknown_is_neutral():
    grade, name = condition_grade({}, "只有一句描述")
    assert grade == 0.55
    assert name == "未标注成色"


def test_title_mismatch_penalized():
    matched = score_item(
        title="vivo X200 Pro 12+256", price=2400, market=_market(),
        labels={"成色": "几乎全新"}, seller=_seller(), keyword="vivo x200 pro",
    )
    mismatched = score_item(
        title="小米 15 Ultra 12+256", price=2400, market=_market(),
        labels={"成色": "几乎全新"}, seller=_seller(), keyword="vivo x200 pro",
    )
    assert mismatched.score < matched.score
    assert "标题未命中关键词" in mismatched.flags
