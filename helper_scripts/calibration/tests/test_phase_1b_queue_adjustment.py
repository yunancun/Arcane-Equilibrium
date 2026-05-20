"""
測試 phase_1b_queue_adjustment module — queue-aware bias 修正 pure-function 模組。

為什麼 fixture：純函數無 IO，全部 inline 數據即可；
PG integration 留給 historical regression CLI（手動跑 + report 輸出）。
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1b_queue_adjustment import (  # noqa: E402
    DEFAULT_QUEUE_WEIGHT,
    QueueDepthSample,
    apply_queue_adjustment,
    compute_queue_factor,
    select_same_side_depth,
)


def test_queue_factor_zero_when_my_qty_far_smaller():
    """my_qty << depth_5 → factor → 0（順位前）。"""
    factor = compute_queue_factor(my_qty=1.0, same_side_depth_5=10_000.0)
    assert factor is not None
    assert 0.0 < factor < 0.001  # 1 / 10001 ≈ 9.999e-5


def test_queue_factor_half_when_my_qty_equals_depth():
    """my_qty == depth_5 → factor = 0.5（順位中段）。"""
    factor = compute_queue_factor(my_qty=100.0, same_side_depth_5=100.0)
    assert factor == 0.5


def test_queue_factor_approaches_one_when_my_qty_dominates():
    """my_qty >> depth_5 → factor → 1（順位末）。"""
    factor = compute_queue_factor(my_qty=10_000.0, same_side_depth_5=1.0)
    assert factor is not None
    assert 0.999 < factor < 1.0


def test_queue_factor_none_when_depth_zero():
    """depth_5 == 0 → None（fail-closed，caller 退回 proxy 不調整）。"""
    assert compute_queue_factor(my_qty=100.0, same_side_depth_5=0.0) is None


def test_queue_factor_none_when_depth_negative():
    """depth_5 < 0 → None（不正常 input，fail-closed）。"""
    assert compute_queue_factor(my_qty=100.0, same_side_depth_5=-1.0) is None


def test_queue_factor_none_when_my_qty_zero():
    """my_qty == 0 → None（不正常 input，無 placement）。"""
    assert compute_queue_factor(my_qty=0.0, same_side_depth_5=100.0) is None


def test_queue_factor_none_when_depth_none():
    """depth_5 None → None（fail-closed）。"""
    assert compute_queue_factor(my_qty=100.0, same_side_depth_5=None) is None


def test_queue_factor_none_when_nan_inputs():
    """NaN inputs → None。"""
    assert compute_queue_factor(my_qty=float('nan'), same_side_depth_5=100.0) is None
    assert compute_queue_factor(my_qty=100.0, same_side_depth_5=float('nan')) is None


def test_apply_queue_adjustment_passthrough_when_factor_none():
    """queue_factor=None → 不調整（fail-closed 退回 proxy）。"""
    adj = apply_queue_adjustment(fill_probability_proxy=1.0, queue_factor=None)
    assert adj == 1.0


def test_apply_queue_adjustment_zero_proxy_returns_zero():
    """proxy=0（cross 沒發生） → 0（不會被 adjust 變成 negative）。"""
    adj = apply_queue_adjustment(fill_probability_proxy=0.0, queue_factor=0.5)
    assert adj == 0.0


def test_apply_queue_adjustment_default_weight():
    """default weight=0.40，factor=0.5 → 0.5 * 0.40 = 0.20 adjustment → 1 * 0.80 = 0.80。"""
    adj = apply_queue_adjustment(fill_probability_proxy=1.0, queue_factor=0.5)
    expected = 1.0 - DEFAULT_QUEUE_WEIGHT * 0.5
    assert abs(adj - expected) < 1e-9


def test_apply_queue_adjustment_factor_one_max_down_weight():
    """factor=1.0（極端順位末）→ adjustment = 1 - weight × 1 = 1 - 0.40 = 0.60。"""
    adj = apply_queue_adjustment(
        fill_probability_proxy=1.0, queue_factor=1.0, queue_weight=0.40,
    )
    assert abs(adj - 0.60) < 1e-9


def test_apply_queue_adjustment_clamps_weight_to_valid_range():
    """weight > 1 → clamp to 1；weight < 0 → clamp to 0。"""
    high = apply_queue_adjustment(1.0, queue_factor=0.5, queue_weight=2.0)
    # weight clamped to 1: adjustment = 1 - 1 * 0.5 = 0.5
    assert abs(high - 0.5) < 1e-9
    low = apply_queue_adjustment(1.0, queue_factor=0.5, queue_weight=-1.0)
    # weight clamped to 0: adjustment = 1 (no down-weight)
    assert abs(low - 1.0) < 1e-9


def test_apply_queue_adjustment_clamps_factor_to_valid_range():
    """factor > 1 / < 0 → clamped。"""
    high = apply_queue_adjustment(1.0, queue_factor=1.5, queue_weight=0.5)
    assert abs(high - 0.5) < 1e-9  # clamped factor=1 → 1 - 0.5 = 0.5
    low = apply_queue_adjustment(1.0, queue_factor=-0.5, queue_weight=0.5)
    assert abs(low - 1.0) < 1e-9  # clamped factor=0 → no down-weight


def test_apply_queue_adjustment_caps_proxy_at_one():
    """proxy slightly > 1（浮點 drift）→ cap to 1 then apply。"""
    adj = apply_queue_adjustment(1.0001, queue_factor=0.5, queue_weight=0.40)
    expected = 1.0 - 0.40 * 0.5
    assert abs(adj - expected) < 1e-9


def test_select_same_side_depth_long_close_uses_ask():
    """position_is_long=True → close=SELL → my order at ASK → same-side=ask_depth_5。"""
    sample = QueueDepthSample(
        ts_bucket_start=datetime(2026, 5, 18, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        bid_depth_5=1000.0,
        ask_depth_5=2000.0,
    )
    assert select_same_side_depth(position_is_long=True, depth_sample=sample) == 2000.0


def test_select_same_side_depth_short_close_uses_bid():
    """position_is_long=False → close=BUY → my order at BID → same-side=bid_depth_5。"""
    sample = QueueDepthSample(
        ts_bucket_start=datetime(2026, 5, 18, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        bid_depth_5=1000.0,
        ask_depth_5=2000.0,
    )
    assert select_same_side_depth(position_is_long=False, depth_sample=sample) == 1000.0


def test_select_same_side_depth_none_sample():
    """depth_sample=None → None（fail-closed）。"""
    assert select_same_side_depth(position_is_long=True, depth_sample=None) is None


def test_apply_queue_adjustment_with_base_rejection():
    """base_rejection_rate 與 queue 維度 multiplicative 互不干擾。
    proxy=1, base=0.5, queue_factor=0.5, weight=0.40 →
    adj = 1 * (1 - 0.5) * (1 - 0.40 * 0.5) = 0.5 * 0.8 = 0.40。
    """
    adj = apply_queue_adjustment(
        fill_probability_proxy=1.0,
        queue_factor=0.5,
        queue_weight=0.40,
        base_rejection_rate=0.5,
    )
    assert abs(adj - 0.40) < 1e-9


def test_apply_queue_adjustment_with_base_rejection_no_queue_data():
    """base_rejection 在 queue_factor=None 時仍套用（fail-closed 只退 queue 維度）。
    proxy=1, base=0.5, queue=None → adj = 1 * 0.5 * 1 = 0.5。
    """
    adj = apply_queue_adjustment(
        fill_probability_proxy=1.0,
        queue_factor=None,
        base_rejection_rate=0.5,
    )
    assert abs(adj - 0.5) < 1e-9


def test_apply_queue_adjustment_base_rejection_clamped():
    """base_rejection > 1 → clamp 1（adj=0）；< 0 → clamp 0（不調 base 維度）。"""
    high = apply_queue_adjustment(1.0, queue_factor=None, base_rejection_rate=1.5)
    assert high == 0.0
    low = apply_queue_adjustment(1.0, queue_factor=None, base_rejection_rate=-0.5)
    assert low == 1.0


def test_end_to_end_typical_close_buy_with_realistic_depth():
    """端到端：close BUY，my_qty=500，bid_depth_5=10000 → factor ≈ 0.0476 →
    adjusted = 1 * (1 - 0.40 * 0.0476) = 0.9810（即下調 ~1.9pp）。
    為什麼測 realistic：14d V094 sample 內常見比例（ARBUSDT qty 500 vs depth 10k+）。
    """
    sample = QueueDepthSample(
        ts_bucket_start=datetime(2026, 5, 18, tzinfo=timezone.utc),
        symbol="ARBUSDT",
        bid_depth_5=10_000.0,
        ask_depth_5=10_000.0,
    )
    depth = select_same_side_depth(position_is_long=False, depth_sample=sample)
    factor = compute_queue_factor(my_qty=500.0, same_side_depth_5=depth)
    adj = apply_queue_adjustment(1.0, queue_factor=factor, queue_weight=0.40)
    assert depth == 10_000.0
    assert factor is not None
    assert abs(factor - 500.0 / 10_500.0) < 1e-9
    expected_adj = 1.0 - 0.40 * (500.0 / 10_500.0)
    assert abs(adj - expected_adj) < 1e-9
