"""shift1_compliance + is_oos_gap 聚焦測試（M3 leak-free PIT producers，P3b）。

覆蓋（對映 PA P3b §C/§D + MIT §1.1/§1.2）：
  shift1_compliance（薄 adapter 重用 feature_engineering_validator）：
    - clean feature → leak_free=True。
    - leaky SQL（CURRENT ROW）→ fail → leak_free=False。
    - 樣本不足 → DEFER → leak_free=False（fail-closed，never auto-pass thin data）。
    - source_class="shift1_compliance"。
  is_oos_gap（check_oos_gap；distinct 名 dodge sample_weight_sensitivity namesake）：
    - clean split → leak_free=True。
    - temporal separation 違反 → leak_free=False。
    - purge violation → leak_free=False。
    - embargo 不足 → leak_free=False。
    - shuffle（interleaved）→ leak_free=False。
    - source_class="is_oos_gap"。

Mac-tested（純 compute）。Linux E4 + MIT sign-off owed。
"""

from __future__ import annotations

import random

import pytest

from program_code.ml_training.shift1_compliance import (
    SOURCE_CLASS as SHIFT1_SOURCE_CLASS,
    check_shift1_compliance,
)
from program_code.ml_training.is_oos_gap import (
    SOURCE_CLASS as IS_OOS_SOURCE_CLASS,
    check_oos_gap,
)


# ═══════════════════════════════════════════════════════════════════════════════
# shift1_compliance
# ═══════════════════════════════════════════════════════════════════════════════


def test_shift1_source_class_tag():
    """source_class = 'shift1_compliance'（M3 typed tag）。"""
    assert SHIFT1_SOURCE_CLASS == "shift1_compliance"


def test_shift1_clean_feature_leak_free():
    """穩定 feature（leak-vs-clean corr 接近）→ leak_free=True。"""
    random.seed(7)
    n = 200
    window = 30
    base = [random.gauss(0, 1) for _ in range(n)]
    feat = list(base)
    fwd = [0.5 * base[i] + random.gauss(0, 0.3) for i in range(n)]
    res = check_shift1_compliance(
        {"stable": feat}, fwd, window=window,
        compute_exprs={"stable": "... ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING"},
    )
    assert res.source_class == "shift1_compliance"
    assert res.leak_free is True
    assert res.per_feature[0]["verdict"] == "pass"
    # static leak-free SQL proof 命中。
    assert res.per_feature[0]["static"]["leakfree_sql"] is True


def test_shift1_leaky_sql_fails():
    """leaky SQL（CURRENT ROW）→ fail → leak_free=False。"""
    random.seed(1)
    n = 60
    fwd = [random.gauss(0, 1) for _ in range(n)]
    feat = [random.gauss(0, 1) for _ in range(n)]
    res = check_shift1_compliance(
        {"leaky": feat}, fwd, window=10,
        compute_exprs={"leaky": "x OVER (ORDER BY ts ROWS BETWEEN 10 PRECEDING AND CURRENT ROW)"},
    )
    assert res.leak_free is False
    assert res.per_feature[0]["verdict"] == "fail"


def test_shift1_thin_data_defers_not_pass():
    """樣本不足 → DEFER → leak_free=False（fail-closed，never auto-pass thin data）。"""
    res = check_shift1_compliance({"f": [1.0, 2.0, 3.0]}, [0.1, 0.2, 0.3], window=30)
    assert res.leak_free is False  # DEFER → 非 leak-free 斷言
    assert res.per_feature[0]["verdict"] == "defer"
    assert res.per_feature[0]["empirical"]["insufficient_sample"] is True


def test_shift1_empty_features_fail_closed():
    """無 feature → leak_free=False（空集不 auto-pass）。"""
    res = check_shift1_compliance({}, [], window=10)
    assert res.leak_free is False
    assert "no_features_provided" in res.reasons


def test_shift1_any_defer_makes_not_leak_free():
    """多 feature 任一 DEFER → 整體 leak_free=False（fail-closed）。"""
    random.seed(7)
    n = 200
    window = 30
    base = [random.gauss(0, 1) for _ in range(n)]
    fwd = [0.5 * base[i] + random.gauss(0, 0.3) for i in range(n)]
    # 一個 clean（足樣本）+ 一個 thin（DEFER）。
    res = check_shift1_compliance(
        {"stable": list(base), "thin": [1.0, 2.0]}, fwd, window=window,
    )
    assert res.leak_free is False  # thin 的 DEFER 使整體非 leak-free


# ═══════════════════════════════════════════════════════════════════════════════
# is_oos_gap（check_oos_gap）
# ═══════════════════════════════════════════════════════════════════════════════


def test_is_oos_source_class_tag():
    """source_class = 'is_oos_gap'（M3 typed tag；namesake 區隔保留字串）。"""
    assert IS_OOS_SOURCE_CLASS == "is_oos_gap"


def test_oos_clean_split_leak_free():
    """clean split（train→gap→test，embargo 足，purge 0，無 shuffle）→ leak_free=True。"""
    train = list(range(50))
    test = list(range(60, 80))
    label_end = [t + 3 for t in train]
    res = check_oos_gap(train, test, label_end, label_horizon_bars=3, embargo_bars=5)
    assert res.source_class == "is_oos_gap"
    assert res.leak_free is True
    assert res.temporal_separation_ok is True
    assert res.embargo_sufficient is True
    assert res.purge_violations == 0
    assert res.shuffle_detected is False


def test_oos_temporal_separation_violation():
    """max(train) >= min(test) → temporal separation 違反 → leak_free=False。"""
    train = list(range(50))
    test = list(range(40, 60))  # overlap with train
    label_end = [t + 1 for t in train]
    res = check_oos_gap(train, test, label_end, label_horizon_bars=1, embargo_bars=0)
    assert res.leak_free is False
    assert res.temporal_separation_ok is False


def test_oos_purge_violation():
    """train label window 伸進 test → purge violation → leak_free=False。"""
    train = list(range(50))
    test = list(range(50, 70))
    label_end = [t + 5 for t in train]  # 末幾筆 label 窗 (45+5=50..) 進 test
    res = check_oos_gap(train, test, label_end, label_horizon_bars=5, embargo_bars=0)
    assert res.leak_free is False
    assert res.purge_violations > 0


def test_oos_embargo_insufficient():
    """embargo gap < embargo_bars → leak_free=False。"""
    train = list(range(50))
    test = list(range(52, 70))  # gap = 2
    label_end = [t for t in train]  # no purge
    res = check_oos_gap(train, test, label_end, label_horizon_bars=0, embargo_bars=10)
    assert res.leak_free is False
    assert res.embargo_sufficient is False


def test_oos_shuffle_interleaved():
    """test 嵌進 train 時間範圍（interleaved）→ shuffle_detected → leak_free=False。"""
    train = list(range(50))
    test = [25, 80]  # 25 落在 train [0,49] 內
    label_end = [t + 1 for t in train]
    res = check_oos_gap(train, test, label_end, label_horizon_bars=1, embargo_bars=0)
    assert res.leak_free is False
    assert res.shuffle_detected is True


def test_oos_shuffle_nonmonotonic_fold():
    """fold 內非單調（KFold-shuffle 把時間打散）→ shuffle_detected。"""
    train = [0, 5, 3, 8, 1]  # 非單調
    test = list(range(20, 30))
    label_end = [t + 1 for t in train]
    res = check_oos_gap(train, test, label_end, label_horizon_bars=1, embargo_bars=0)
    assert res.shuffle_detected is True
    assert res.leak_free is False


def test_oos_empty_fold_fail_closed():
    """train/test 任一空 → leak_free=False（fail-closed）。"""
    res = check_oos_gap([], [1, 2, 3], [], label_horizon_bars=1, embargo_bars=0)
    assert res.leak_free is False
    assert "empty_train_or_test_fold" in res.reasons
