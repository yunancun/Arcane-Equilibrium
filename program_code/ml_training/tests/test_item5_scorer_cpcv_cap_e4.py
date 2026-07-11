"""E4 獨立驗證 — Item 5「legacy scorer：failing CPCV 封頂狀態」。
E4 independent verification for Item 5: a failing CPCV result caps the model status.

E4 與 E1 測試的分工（為何再寫一檔，而非只 reuse E1）：
  E1 的整條 train_scorer 路徑測試以 `pytest.importorskip("lightgbm")` 包裹，Mac 無
  lightgbm 時「SKIP」——意即「failing CPCV → status 封頂 → ship_eligible=0」這條
  端到端接線在本 Mac 上「未被實際執行」（只證了 `_derive_model_status` 純函式）。
  本檔用「僅 stub lightgbm 函式庫邊界」的方式，在 Mac 上真跑整條接線：
    validate_cpcv(passed=False) → _derive_model_status → result.status
    → result.metrics["ship_eligible"]/["cpcv_passed"] → metrics.json 供下游 honor。
  被 stub 的只有「重型外部 ML 函式庫」這個 IO/庫邊界（合法 mock 對象）；被驗的
  「狀態封頂決策」全程真跑（非 mock 業務邏輯）——LightGBM 的數值輸出根本不參與
  status 決策（status 只依賴 cpcv_result.passed 與 purge 後樣本數），故 stub 它不會
  遮蔽被測邏輯。零 runtime、零 DB、零 order、零 network。

驗收對應（acceptance = "test that a failing CPCV caps status"）：
  (A) 純函式層：_derive_model_status(False, ...) == "reference_only"（核心不變量）。
  (B) 接線層（Mac，stub lightgbm）：validate_cpcv 回 passed=False 時，train_scorer
      的 result.status=="reference_only" 且 metrics ship_eligible==0/cpcv_passed==0，
      且 purge provenance 與 rmse/correlation 並存（未被覆蓋）。
  (C) 對照組：passed=True 且樣本充足 → status=="ok"、ship_eligible==1（不誤封合法 ship）。
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from program_code.ml_training.scorer_trainer import _derive_model_status

_HOUR_MS = 3_600_000  # 1 小時的毫秒數 / one hour in milliseconds


def _hourly_ts_ms(n: int) -> np.ndarray:
    """每小時一筆、單調遞增的毫秒時間戳（>1e12 → 觸發 ms→s 自動偵測分支）。
    Monotonic hourly epoch-ms timestamps."""
    return (np.arange(n, dtype=np.float64) * _HOUR_MS) + 1_700_000_000_000.0


# =====================================================================
# (A) 純函式層：failing CPCV 直接封頂 / pure-function cap decision
# =====================================================================

def test_e4_failing_cpcv_caps_status_regardless_of_sample_count():
    """核心不變量：cpcv_passed=False → 無論訓練樣本多充足都封為 reference_only。
    這是 Item 5「a failing CPCV result caps the status」最小可證命題。"""
    # 樣本充足（遠高於 floor）也必須被 CPCV 失敗封頂。
    assert _derive_model_status(False, n_train_after_purge=1_000_000, min_train_floor=20) == "reference_only"
    # 樣本剛好等於 floor：仍因 CPCV 失敗而封頂（CPCV 失敗優先，fail-closed）。
    assert _derive_model_status(False, n_train_after_purge=20, min_train_floor=20) == "reference_only"


def test_e4_passing_cpcv_with_thin_train_still_caps():
    """對照：CPCV 通過但 purge 後樣本 < floor → holdout 指標不可信，仍封頂。
    證明封頂有第二道獨立閘（樣本不足），非只看 CPCV。"""
    assert _derive_model_status(True, n_train_after_purge=19, min_train_floor=20) == "reference_only"


def test_e4_healthy_run_not_over_capped():
    """對照：CPCV 通過且樣本 >= floor → ok。確保封頂不會過度封鎖合法 ship 路徑。
    邊界值：n == floor 應通過（>= floor 為可信）。"""
    assert _derive_model_status(True, n_train_after_purge=20, min_train_floor=20) == "ok"


# =====================================================================
# stub lightgbm 函式庫邊界（僅 IO/庫邊界，不 stub 業務邏輯）
# fake LightGBM: stub ONLY the heavy external library surface
# =====================================================================

class _FakeBooster:
    """假 LightGBM booster——只提供 train_scorer 最終 fit 會用到的表面。
    數值與狀態封頂無關，僅讓 rmse/correlation/save/importance 呼叫成立。"""

    def __init__(self, n_features: int) -> None:
        self._n_features = n_features
        self.best_iteration = 7  # 任意非零迭代數 / arbitrary non-zero

    def predict(self, X):
        # 取第一特徵欄作預測，使其有變異 → corrcoef 不退化為 nan。
        arr = np.asarray(X, dtype=np.float64)
        if arr.ndim == 2 and arr.shape[1] > 0:
            return arr[:, 0]
        return np.zeros(len(arr), dtype=np.float64)

    def save_model(self, path):
        # stub：寫佔位檔證明 save 路徑被走到（非真 LightGBM 序列化）。
        with open(path, "w") as fh:
            fh.write("FAKE_LGB_MODEL_E4\n")

    def feature_importance(self, importance_type: str = "gain"):
        # 回傳長度=n_features 的陣列，供 dict(zip(feature_names, .tolist())) 使用。
        return np.zeros(self._n_features, dtype=np.float64)


class _FakeDataset:
    """假 lgb.Dataset——只記住特徵數，供 fake train 回傳對應維度的 booster。"""

    def __init__(self, data, label=None, feature_name=None, reference=None):
        arr = np.asarray(data)
        self._n_features = arr.shape[1] if arr.ndim == 2 else 0


def _fake_train(params, train_set, num_boost_round=None, valid_sets=None, callbacks=None):
    # 不做任何真訓練；回傳與訓練資料同維度的假 booster。
    return _FakeBooster(getattr(train_set, "_n_features", 0))


def _fake_early_stopping(stopping_rounds, verbose: bool = False):
    # 佔位 callback；我們的 fake train 不會實際使用它。
    return "e4_fake_early_stopping_callback"


def _install_fake_lightgbm(monkeypatch) -> None:
    """把假 lightgbm 注入 sys.modules，讓 train_scorer 內 `import lightgbm as lgb`
    取到假模組。monkeypatch.setitem 保證測試後自動還原。"""
    fake = types.ModuleType("lightgbm")
    fake.Dataset = _FakeDataset
    fake.train = _fake_train
    fake.early_stopping = _fake_early_stopping
    monkeypatch.setitem(sys.modules, "lightgbm", fake)


def _make_cpcv_result(passed: bool):
    """構造一個受控的 CPCVResult（唯一「輸入」即 passed）。這不是 mock 業務邏輯——
    被測命題正是「給定 passed=False 的 CPCV 結果，狀態是否被封頂」，passed 即測試輸入。"""
    from program_code.ml_training.cpcv_validator import CPCVResult

    return CPCVResult(
        fold_metrics=[{"sharpe": -0.2 if not passed else 0.4, "fold": 0}],
        mean_sharpe=-0.2 if not passed else 0.4,
        std_sharpe=0.1,
        power_estimate=0.9,
        passed=passed,
        n_folds=4,
        embargo_hours=24,
        strategy_type="trending",
    )


# =====================================================================
# (B) 接線層（Mac，無 lightgbm）：failing CPCV → 端到端封頂
# =====================================================================

def test_e4_train_scorer_failing_cpcv_caps_status_on_mac(monkeypatch, tmp_path):
    """Item 5 主驗收（Mac 版）：validate_cpcv 回 passed=False 時，整條 train_scorer
    須把 status 封為 reference_only，並在 metrics.json 欄位留下可被下游 honor 的旗標。
    本測試在無 lightgbm 的 Mac 上真跑接線（stub 只碰函式庫邊界）。"""
    _install_fake_lightgbm(monkeypatch)

    from program_code.ml_training import cpcv_validator
    from program_code.ml_training.scorer_trainer import ScorerConfig, train_scorer

    # 攔截 validate_cpcv 回一個 passed=False 的結果（受控測試輸入）。
    # train_scorer 內以函式局部 `from ... import validate_cpcv` 取名，綁定的是模組屬性，
    # monkeypatch 模組屬性即生效（與 generate_folds/真 fold 訓練無關，故也不需 PG）。
    monkeypatch.setattr(cpcv_validator, "validate_cpcv", lambda *a, **k: _make_cpcv_result(False))

    rng = np.random.default_rng(20260711)
    n, k = 600, 4
    features = rng.normal(size=(n, k))
    labels = rng.normal(size=n)
    feature_names = [f"f{i}" for i in range(k)]
    timestamps = _hourly_ts_ms(n)

    cfg = ScorerConfig(output_dir=str(tmp_path), min_child_samples=10, n_estimators=20)
    result = train_scorer(
        features=features,
        labels=labels,
        feature_names=feature_names,
        config=cfg,
        timestamps=timestamps,
        strategy_type="trending",
    )

    # 模型仍成功產出（供參考），但狀態被 CPCV 失敗封頂。
    assert result.success is True, f"unexpected error: {result.error!r}"
    assert result.status == "reference_only"

    # 下游晉升器唯一需 honor 的機器旗標：ship_eligible=0、cpcv_passed=0。
    assert result.metrics["ship_eligible"] == 0.0
    assert result.metrics["cpcv_passed"] == 0.0

    # purge provenance 必須與 reported 指標並存於同一 metrics dict（→ metrics.json）；
    # 這道斷言同時守住「result.metrics.update 而非賦值」的回歸（勿覆蓋 cpcv_*/holdout_*）。
    assert result.metrics["holdout_purged_rows"] > 0
    assert result.metrics["holdout_embargo_hours"] == 24.0
    assert "rmse" in result.metrics and "correlation" in result.metrics
    assert "cpcv_mean_sharpe" in result.metrics


def test_e4_train_scorer_ship_eligible_when_cpcv_passes_on_mac(monkeypatch, tmp_path):
    """(C) 對照組（Mac 版）：CPCV 通過且樣本充足 → status ok、ship_eligible=1。
    證明封頂是「條件式」而非恆為 reference_only（否則就是壞掉的 always-cap）。"""
    _install_fake_lightgbm(monkeypatch)

    from program_code.ml_training import cpcv_validator
    from program_code.ml_training.scorer_trainer import ScorerConfig, train_scorer

    monkeypatch.setattr(cpcv_validator, "validate_cpcv", lambda *a, **k: _make_cpcv_result(True))

    rng = np.random.default_rng(11)
    n, k = 600, 4
    features = rng.normal(size=(n, k))
    labels = rng.normal(size=n)
    feature_names = [f"f{i}" for i in range(k)]
    timestamps = _hourly_ts_ms(n)

    cfg = ScorerConfig(output_dir=str(tmp_path), min_child_samples=10, n_estimators=20)
    result = train_scorer(
        features=features,
        labels=labels,
        feature_names=feature_names,
        config=cfg,
        timestamps=timestamps,
        strategy_type="trending",
    )

    assert result.success is True, f"unexpected error: {result.error!r}"
    assert result.status == "ok"
    assert result.metrics["ship_eligible"] == 1.0
    assert result.metrics["cpcv_passed"] == 1.0
