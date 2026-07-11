"""E4 反洩漏驗證 — Item 1 三分 holdout「兩兩互斥 + 回報指標取自 test 分區」。
E4 anti-leakage verification for Item 1: the three tail-holdout partitions are
pairwise disjoint and the reported ship-gate metrics read ONLY the test partition.

WHY THIS FILE EXISTS (為什麼另立 E4 檔):
  E1 已在 test_quantile_trainer.py 加了兩個端到端測試,但它們 `pytest.importorskip
  ("lightgbm")` —— 本 Mac 無 lightgbm,故那兩個「回報指標讀 test 分區」的端到端
  證明在 Mac 一律 SKIP。本 E4 檔用「純 numpy + 假 lightgbm 邊界」把同一條路徑跑起來,
  完全不呼叫真正的 lgb.train:驗證的是 split / index 邏輯,不是 LightGBM 本身。

METHOD (方法):
  1) 性質測試:直接對真實的 `_split_tail_holdout` + `_partition_holdout_three_way`
     斷言「train / val / calib / test 四段是原索引空間的乾淨切分」(兩兩互斥、聯集恰
     為全體、無重複)。純 numpy,零外部相依。
  2) 端到端追列:注入一個假 lightgbm,其 Booster.predict(X) 回傳「特徵第 0 欄」。測試
     資料刻意令 X[:,0] == 全域列索引,因此可從 result.test_*_pred / calibration_*_pred
     以及 fit 實際看到的 valid_sets「反查」每個分區到底讀了哪些原始列,進而證明:
       - val(early-stopping 選模型)/ calib(CQR 校準)/ test(回報指標)三組列兩兩互斥;
       - 回報的 ship-gate 指標(pinball_skill / coverage / decile-lift / crossing)以及
         快取的 test_labels / test_*_pred 全部、且只、來自 test 分區。
  這符合 mock 規則:只 stub「重運算 IO 邊界」(LightGBM 訓練),split / 指標選列等業務
  邏輯全部真跑。
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from program_code.ml_training.quantile_trainer import (
    QuantileTrainingConfig,
    MIN_CALIBRATION_ROWS,
    MIN_TEST_ROWS,
    MIN_VALIDATION_ROWS,
    _partition_holdout_three_way,
    _split_tail_holdout,
    compute_coverage_error,
    pinball_loss,
    train_quantile_trio,
)
from program_code.ml_training.quantile_reports import generate_acceptance_report


# ══════════════════════════════════════════════════════════════════
# Part 1 — 純 numpy 性質測試:真實 split 函式構成原索引空間的乾淨四切分
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "n,tail_days,compress",
    [
        (200, 7.0, True),    # 壓縮時間戳 → _split_tail_holdout 走 min_fraction fallback
        (400, 7.0, False),   # 真實 7d 時間窗
        (900, 7.0, False),
        (137, 14.0, False),  # funding_arb-like 14d 尾段
        (75, 7.0, True),     # 貼近下限
    ],
)
def test_train_val_calib_test_is_clean_partition_of_index_space(n, tail_days, compress):
    """真實 `_split_tail_holdout` → `_partition_holdout_three_way` 串起來後,
    train / val / calib / test 必須是「原 n 列索引」的乾淨切分:
      - 兩兩互斥;
      - 聯集恰等於 {0..n-1}(無列遺漏);
      - 每列恰屬一段(無重複)。
    這是 claim-0002 反洩漏的地基:選模型 / 校準 / 回報三者永不共用資料列,且沒有任何
    訓練列偷偷混進 holdout。"""
    if compress:
        # 壓縮到 < tail_days 的跨度,逼 _split_tail_holdout 用 min_fraction 尾段切分。
        ts = np.arange(n, dtype=np.int64) * 60_000  # 每列相隔 1 分鐘
    else:
        # 每列相隔 1 小時 → 足以覆蓋 tail_days 時間窗路徑。
        ts = np.arange(n, dtype=np.int64) * 3_600_000

    train_idx, holdout_idx = _split_tail_holdout(ts, tail_days)
    val_idx, calib_idx, test_idx = _partition_holdout_three_way(holdout_idx)

    s_train = set(train_idx.tolist())
    s_val = set(val_idx.tolist())
    s_calib = set(calib_idx.tolist())
    s_test = set(test_idx.tolist())

    # 兩兩互斥(含 train,證明沒有訓練列洩漏進任何 holdout 分區)。
    assert s_train.isdisjoint(s_val)
    assert s_train.isdisjoint(s_calib)
    assert s_train.isdisjoint(s_test)
    assert s_val.isdisjoint(s_calib)
    assert s_val.isdisjoint(s_test)
    assert s_calib.isdisjoint(s_test)

    # 聯集恰為全體 {0..n-1},且四段大小合計 == n(無遺漏、無重複)。
    assert s_train | s_val | s_calib | s_test == set(range(n))
    assert len(s_train) + len(s_val) + len(s_calib) + len(s_test) == n

    # 時間語意:val 最舊、test 最新;holdout 整段的時間戳都不小於 train 的最大時間戳。
    assert ts[max(train_idx)] <= ts[min(holdout_idx)]
    if len(val_idx) and len(calib_idx):
        assert val_idx[-1] < calib_idx[0]
    if len(calib_idx) and len(test_idx):
        assert calib_idx[-1] < test_idx[0]
    # test 承載 ship-gate,應為 holdout 內最大分區。
    assert len(test_idx) >= len(val_idx)
    assert len(test_idx) >= len(calib_idx)


# ══════════════════════════════════════════════════════════════════
# Part 2 — 假 lightgbm 端到端追列:證明回報指標「只讀」test 分區
# ══════════════════════════════════════════════════════════════════

# fit 實際看到的 early-stopping 驗證集列索引(由假 lgb.train 記錄)。
_CAPTURED_VALID_ROWS: list = []


class _FakeDataset:
    """僅保存 data,供假 train 讀回 valid_sets 用。"""

    def __init__(self, data, label=None, weight=None, feature_name=None, reference=None):
        self.data = np.asarray(data)
        self.label = label
        self.weight = weight


class _FakeBooster:
    """身分傳遞 predictor:predict(X)=X[:,0]。測試令 X[:,0]==全域列索引,
    故可從預測值反查「這批預測讀了哪些原始列」。"""

    def __init__(self, best_iteration: int):
        self.best_iteration = best_iteration

    def predict(self, X):
        return np.asarray(X)[:, 0].astype(np.float64)


def _fake_train(params, train_set, num_boost_round=100, valid_sets=None, callbacks=None):
    # 記錄 early-stopping 驗證集實際看到的列(用於證明 val 與 calib/test 互斥),不做真訓練。
    if valid_sets:
        for vs in valid_sets:
            _CAPTURED_VALID_ROWS.append(np.asarray(vs.data)[:, 0].astype(np.int64))
    return _FakeBooster(best_iteration=min(7, int(num_boost_round)))


def _fake_early_stopping(rounds, verbose=False):
    return lambda env: None  # no-op callback;假 train 不使用


@pytest.fixture()
def fake_lightgbm(monkeypatch):
    """注入假 lightgbm 到 sys.modules,使 train_quantile_trio 端到端跑起來但
    不呼叫真正的 lgb.train(本 Mac 無 lightgbm)。"""
    _CAPTURED_VALID_ROWS.clear()
    mod = types.ModuleType("lightgbm")
    mod.Dataset = _FakeDataset
    mod.train = _fake_train
    mod.early_stopping = _fake_early_stopping
    monkeypatch.setitem(sys.modules, "lightgbm", mod)
    return mod


def _make_traceable_dataset(n: int, n_features: int = 4, seed: int = 7):
    """建構可追列資料:X[:,0]==全域列索引(float),其餘欄為雜訊;時間戳單調遞增。"""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, n_features)).astype(np.float32)
    X[:, 0] = np.arange(n, dtype=np.float32)  # 令第 0 欄 = 全域列索引,供反查
    y = rng.standard_normal(n).astype(np.float32)
    ts = (np.arange(n, dtype=np.int64) * 60_000)  # 每列 1 分鐘 → 走 fractional holdout
    return X, y, ts


def test_reported_metrics_read_only_test_partition_end_to_end(fake_lightgbm):
    """端到端(假 lgb):證明 val/calib/test 三組列兩兩互斥,且回報 ship-gate 指標與
    快取 test_* 全部、且只、來自 test 分區。此為 E1 因缺 lightgbm 在 Mac 跳過的證明。"""
    n = 900
    X, y, ts = _make_traceable_dataset(n)
    cfg = QuantileTrainingConfig(
        n_estimators=60, early_stopping_rounds=10, bootstrap_iterations=64,
    )

    result = train_quantile_trio(
        features=X, labels=y, timestamps_ms=ts,
        feature_names=[f"f{i}" for i in range(X.shape[1])],
        strategy_name="ma_crossover", engine_mode="paper", config=cfg,
    )
    assert result.success, result.error

    # ── 用真實 split 函式獨立算出「本應」的各分區全域列索引(oracle)。
    train_idx, holdout_idx = _split_tail_holdout(ts, 7.0)
    val_idx, calib_idx, test_idx = _partition_holdout_three_way(holdout_idx)

    # ── 從結果反查各分區實際讀到的全域列索引。
    #    test_*_pred == b.predict(X_test) == X_test[:,0] == test 分區全域列索引。
    got_test_rows = set(np.rint(result.test_q50_pred).astype(int).tolist())
    got_calib_rows = set(np.rint(result.calibration_q50_pred).astype(int).tolist())
    # fit 的 valid_sets 全域列索引(3 個分位 fit 應完全相同)。
    assert _CAPTURED_VALID_ROWS, "fake lgb.train 未捕獲任何 valid_sets"
    got_val_rows = set(_CAPTURED_VALID_ROWS[0].tolist())
    for cap in _CAPTURED_VALID_ROWS[1:]:
        assert set(cap.tolist()) == got_val_rows  # 三分位 early-stopping 用同一 val 集

    # ── (A) 三分區各自讀的列 == oracle 分區列(index 邏輯正確)。
    assert got_val_rows == set(val_idx.tolist())
    assert got_calib_rows == set(calib_idx.tolist())
    assert got_test_rows == set(test_idx.tolist())

    # ── (B) 三組列「兩兩互斥」(反洩漏核心)。
    assert got_val_rows.isdisjoint(got_calib_rows)
    assert got_val_rows.isdisjoint(got_test_rows)
    assert got_calib_rows.isdisjoint(got_test_rows)

    # ── (C) 回報指標「只讀」test 分區:
    #    快取 test_labels 逐列等於 labels[test_idx];PerQuantileMetrics.n_holdout==n_test。
    assert len(result.test_labels) == result.n_test == len(test_idx)
    assert np.array_equal(np.asarray(result.test_labels), y[test_idx])
    for q in ("q10", "q50", "q90"):
        assert result.per_quantile_metrics[q].n_holdout == result.n_test

    #    獨立在 test 分區重算 coverage 與 pinball_loss,必須逐位命中回報值
    #    → 證明回報指標是 test 列的純函數(未參與選模型/校準)。
    for q, alpha in (("q10", 0.10), ("q50", 0.50), ("q90", 0.90)):
        pred_test = X[test_idx, 0].astype(np.float64)  # == b.predict(X_test)
        exp_cov, exp_err = compute_coverage_error(y[test_idx], pred_test, alpha)
        exp_loss = pinball_loss(y[test_idx], pred_test, alpha)  # 回報用未加權 pinball
        m = result.per_quantile_metrics[q]
        assert m.empirical_coverage == pytest.approx(exp_cov, abs=1e-9)
        assert m.coverage_error_pp == pytest.approx(exp_err, abs=1e-9)
        assert m.pinball_loss == pytest.approx(exp_loss, abs=1e-9)

    #    反證(falsifier):若回報指標誤讀 calib 列,值會不同。pinball_loss 隨列集變動
    #    (非飽和),故「calib 列算出的 loss」必不等於回報值 → 證明上面等式非巧合、
    #    且回報指標確實排除了 calib 分區。
    for q, alpha in (("q10", 0.10), ("q50", 0.50), ("q90", 0.90)):
        calib_pred = X[calib_idx, 0].astype(np.float64)
        calib_loss = pinball_loss(y[calib_idx], calib_pred, alpha)
        assert calib_loss != pytest.approx(
            result.per_quantile_metrics[q].pinball_loss, abs=1e-9
        )

    # ── (D) 分區列數守恆:val+calib+test == n_holdout == 整段 holdout。
    assert result.n_validation >= MIN_VALIDATION_ROWS
    assert result.n_calibration >= MIN_CALIBRATION_ROWS
    assert result.n_test >= MIN_TEST_ROWS
    assert result.n_validation + result.n_calibration + result.n_test == result.n_holdout
    assert result.n_holdout == len(holdout_idx)

    # ── (E) train 全域列不與任何 holdout 分區重疊(無訓練列洩漏)。
    train_rows = set(train_idx.tolist())
    assert train_rows.isdisjoint(got_val_rows | got_calib_rows | got_test_rows)


def test_acceptance_report_declares_test_partition_provenance(fake_lightgbm):
    """驗收報告(以真實 fake-lgb 訓練結果生成,非手工 mock)必須明示 ship-gate 指標
    來源 = test_partition,且三分區列數與 n_holdout 一致。"""
    X, y, ts = _make_traceable_dataset(900)
    cfg = QuantileTrainingConfig(n_estimators=40, early_stopping_rounds=8, bootstrap_iterations=32)
    result = train_quantile_trio(
        features=X, labels=y, timestamps_ms=ts,
        feature_names=[f"f{i}" for i in range(X.shape[1])],
        strategy_name="ma_crossover", engine_mode="paper", config=cfg,
    )
    assert result.success, result.error

    report = generate_acceptance_report(result, cfg, include_train_serve_harness=False)
    assert report["ship_gate_metric_source"] == "test_partition"
    assert report["n_test"] == result.n_test
    assert report["n_validation"] == result.n_validation
    assert report["n_calibration"] == result.n_calibration
    assert report["n_validation"] + report["n_calibration"] + report["n_test"] == report["n_holdout"]


def test_degenerate_holdout_fails_closed_below_floor(fake_lightgbm):
    """holdout 太小 → 無法形成三個過地板分區 → success=False(fail-closed → 下游 no_ship),
    而非靜默用退化分區回報。純 index 路徑,不需真 lgb。"""
    # 65 列 + 壓縮時間戳 → holdout≈min_fraction 10%≈6 列 < 三分地板 → degenerate。
    n = 65
    rng = np.random.default_rng(11)
    X = rng.standard_normal((n, 4)).astype(np.float32)
    X[:, 0] = np.arange(n, dtype=np.float32)
    y = rng.standard_normal(n).astype(np.float32)
    ts = np.arange(n, dtype=np.int64) * 60_000

    result = train_quantile_trio(
        features=X, labels=y, timestamps_ms=ts,
        feature_names=[f"f{i}" for i in range(4)],
        strategy_name="ma_crossover", engine_mode="paper",
        config=QuantileTrainingConfig(),
    )
    assert not result.success
    assert "degenerate split" in result.error
