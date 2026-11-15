"""市场基准测试：同规格优先、样本不足退回全局、极端值要砍掉。"""
from hunter.scoring.market import build_market, percentile, trim_outliers


def test_prefers_same_spec_when_enough_samples():
    samples = [
        (2400, "12+256"), (2500, "12+256"), (2550, "12+256"), (2600, "12+256"),
        (3200, "16+512"), (3300, "16+512"),
    ]
    market = build_market(samples, item_spec="12+256", min_samples=4)
    assert market.count == 4
    assert "同规格" in market.basis
    assert 2400 <= market.median <= 2600


def test_falls_back_to_all_when_spec_samples_thin():
    samples = [(2400, "12+256"), (3200, "16+512"), (3300, "16+512")]
    market = build_market(samples, item_spec="12+256", min_samples=4)
    assert market.count == 3
    assert "全部" in market.basis
    assert market.median == 3200


def test_outliers_are_trimmed():
    prices = [2500, 2520, 2480, 2550, 2490, 2505, 100, 9000]
    kept = trim_outliers(prices)
    assert 100 not in kept and 9000 not in kept
    assert len(kept) == 6


def test_discount_and_not_ready():
    samples = [(2000, ""), (2500, ""), (3000, "")]
    market = build_market(samples, min_samples=3)
    assert market.ready
    assert market.discount_pct(2000) == 20.0
    empty = build_market([], min_samples=3)
    assert not empty.ready
    assert empty.discount_pct(1000) is None


def test_percentile_small_sample():
    assert percentile([10], 0.5) == 10
    assert percentile([10, 20], 0.5) == 15
