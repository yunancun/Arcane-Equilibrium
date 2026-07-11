"""E1 自測 — Item 5「legacy scorer：CPCV 封頂 + 最終 holdout purge」。
E1 self-test for Item 5.

驗收對應（acceptance）：
  (1) failing CPCV caps status → 測 `_derive_model_status` 與（有 lightgbm 時）
      整條 train_scorer 路徑：cpcv_result.passed=False → status=="reference_only"
      且 metrics["ship_eligible"]==0.0、metrics["cpcv_passed"]==0.0。
  (2) reported metrics come from a purged split → 測 `_tail_holdout_train_indices`：
      回傳的訓練索引全 < split_idx（與 holdout pairwise disjoint），且移除了
      [test_start - max(purge, embargo), test_start) 窗口內的樣本。

為什麼拆出純函式測試（為何多數斷言不需 lightgbm）：
  Item 5 的兩個不變量（狀態封頂決策、holdout 清洗）都被抽成純 numpy 函式，
  可在無 lightgbm 的 Mac 直接跑真邏輯（非 mock）；整條 train_scorer 需 lightgbm，
  故以 importorskip 分離，避免 Mac 缺依賴時整檔 error。零 IO、零 runtime、零 DB。
"""

from __future__ import annotations

import numpy as np
import pytest

from program_code.ml_training.scorer_trainer import (
    _derive_model_status,
    _tail_holdout_train_indices,
)

_HOUR_MS = 3_600_000  # 1 小時的毫秒數


# ----- (1) 狀態封頂決策 / status-cap decision (pure) -----

def test_cpcv_fail_caps_to_reference_only():
    # CPCV 未通過 → 無論訓練樣本多少都封頂。
    assert _derive_model_status(False, n_train_after_purge=10_000, min_train_floor=20) == "reference_only"


def test_thin_train_after_purge_caps_even_when_cpcv_passed():
    # CPCV 通過但 purge 後訓練樣本低於門檻 → holdout 指標不可信，仍封頂。
    assert _derive_model_status(True, n_train_after_purge=5, min_train_floor=20) == "reference_only"


def test_healthy_run_stays_ok():
    # CPCV 通過且樣本充足 → ok（可晉升）。否則封頂會過度封鎖合法 ship。
    assert _derive_model_status(True, n_train_after_purge=10_000, min_train_floor=20) == "ok"


# ----- (2) 最終 holdout 的 purge + embargo (pure) -----

def _hourly_ts_ms(n: int) -> np.ndarray:
    # 每小時一筆、單調遞增的毫秒時間戳。
    return (np.arange(n, dtype=np.float64) * _HOUR_MS) + 1_700_000_000_000.0


def test_tail_purge_disjoint_and_bounded():
    n = 1000
    ts = _hourly_ts_ms(n)
    split_idx = int(n * 0.8)  # 800
    embargo_hours = 24.0
    label_window_hours = 4.0

    train_idx = _tail_holdout_train_indices(ts, split_idx, embargo_hours, label_window_hours)
    holdout_idx = np.arange(split_idx, n)

    # 不變量：訓練索引全 < split_idx，與 holdout pairwise disjoint。
    assert train_idx.max() < split_idx
    assert np.intersect1d(train_idx, holdout_idx).size == 0

    # 確有清洗：cutoff = test_start - max(24h, 4h) = split_idx 前 24 小時（=24 筆）。
    # 每小時一筆 → 應移除最接近邊界的 24 筆訓練樣本。
    purged = split_idx - len(train_idx)
    assert purged == 24, f"expected 24 purged rows, got {purged}"

    # 被保留的最後一筆訓練時間 <= test_start - 24h（cutoff）。
    cutoff = ts[split_idx] / 1000.0 - 24.0 * 3600.0
    kept_ts_sec = ts[train_idx] / 1000.0
    assert kept_ts_sec.max() <= cutoff + 1e-6


def test_tail_purge_label_window_dominates_embargo():
    # label_window(6h) > embargo(4h) 時，移除由 purge 主導：purge 用嚴格 >（ts>test_start-6h），
    # 每小時一筆 → 移除 index 155..159 = 5 筆（與 cpcv_validator 的 purge_before 邊界一致）。
    n = 200
    ts = _hourly_ts_ms(n)
    split_idx = 160
    train_idx = _tail_holdout_train_indices(ts, split_idx, embargo_hours=4.0, label_window_hours=6.0)
    purged = split_idx - len(train_idx)
    assert purged == 5


def test_degenerate_split_returns_all_train():
    # split_idx 觸及邊界（0 或 n）→ 無可清洗邊界，回傳原訓練索引（呼叫端另有 fail-closed）。
    ts = _hourly_ts_ms(50)
    assert _tail_holdout_train_indices(ts, 0, 24.0, 4.0).size == 0
    assert _tail_holdout_train_indices(ts, 50, 24.0, 4.0).size == 50


# ----- (1)+(2) 整條路徑（需 lightgbm）/ full train_scorer path -----

def test_train_scorer_caps_status_on_cpcv_fail(monkeypatch, tmp_path):
    """CPCV 判定 fail 時，train_scorer 須把 status 封頂為 reference_only，
    並在 metrics（→ metrics.json）留下 ship_eligible=0 / cpcv_passed=0 / purge provenance。"""
    pytest.importorskip("lightgbm")

    from program_code.ml_training import cpcv_validator
    from program_code.ml_training.scorer_trainer import (
        ScorerConfig,
        train_scorer,
    )
    from program_code.ml_training.cpcv_validator import CPCVResult

    rng = np.random.default_rng(0)
    n, k = 600, 4
    features = rng.normal(size=(n, k))
    labels = rng.normal(size=n)
    feature_names = [f"f{i}" for i in range(k)]
    timestamps = _hourly_ts_ms(n)

    # 攔截 validate_cpcv：train_scorer 以 `from ... import validate_cpcv` 於函式內取名，
    # 綁定的是模組屬性，monkeypatch 模組屬性即可生效。回傳一個 passed=False 結果。
    def _fake_validate_cpcv(*_args, **_kwargs) -> CPCVResult:
        return CPCVResult(
            fold_metrics=[{"sharpe": -0.2, "fold": 0}],
            mean_sharpe=-0.2,
            std_sharpe=0.1,
            power_estimate=0.9,
            passed=False,
            n_folds=k,
            embargo_hours=24,
            strategy_type="trending",
        )

    monkeypatch.setattr(cpcv_validator, "validate_cpcv", _fake_validate_cpcv)

    cfg = ScorerConfig(output_dir=str(tmp_path), min_child_samples=10, n_estimators=20)
    result = train_scorer(
        features=features,
        labels=labels,
        feature_names=feature_names,
        config=cfg,
        timestamps=timestamps,
        strategy_type="trending",
    )

    # 訓練成功完成（模型仍產出供參考），但狀態被封頂。
    assert result.success is True
    assert result.status == "reference_only"
    # 下游可據以拒絕晉升的機器旗標必須存在且為 0（且未被 rmse 賦值蓋掉）。
    assert result.metrics["ship_eligible"] == 0.0
    assert result.metrics["cpcv_passed"] == 0.0
    # purge provenance 與 reported 指標並存於同一 metrics dict（→ metrics.json）。
    assert "holdout_purged_rows" in result.metrics
    assert result.metrics["holdout_purged_rows"] > 0
    assert "rmse" in result.metrics and "correlation" in result.metrics


def test_train_scorer_ship_eligible_when_cpcv_passes(monkeypatch, tmp_path):
    """對照組：CPCV 通過且樣本充足 → status ok、ship_eligible=1，確保封頂不會誤封合法 ship。"""
    pytest.importorskip("lightgbm")

    from program_code.ml_training import cpcv_validator
    from program_code.ml_training.scorer_trainer import ScorerConfig, train_scorer
    from program_code.ml_training.cpcv_validator import CPCVResult

    rng = np.random.default_rng(1)
    n, k = 600, 4
    features = rng.normal(size=(n, k))
    labels = rng.normal(size=n)
    feature_names = [f"f{i}" for i in range(k)]
    timestamps = _hourly_ts_ms(n)

    def _fake_pass(*_args, **_kwargs) -> CPCVResult:
        return CPCVResult(
            fold_metrics=[{"sharpe": 0.4, "fold": 0}],
            mean_sharpe=0.4,
            std_sharpe=0.1,
            power_estimate=0.9,
            passed=True,
            n_folds=k,
            embargo_hours=24,
            strategy_type="trending",
        )

    monkeypatch.setattr(cpcv_validator, "validate_cpcv", _fake_pass)

    cfg = ScorerConfig(output_dir=str(tmp_path), min_child_samples=10, n_estimators=20)
    result = train_scorer(
        features=features,
        labels=labels,
        feature_names=feature_names,
        config=cfg,
        timestamps=timestamps,
        strategy_type="trending",
    )

    assert result.success is True
    assert result.status == "ok"
    assert result.metrics["ship_eligible"] == 1.0
    assert result.metrics["cpcv_passed"] == 1.0
