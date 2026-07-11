"""E1 修訂驗證 — MIT Item 1「sub-floor holdout → two-way shadow-capped 退路」。
E1 verification for the MIT-flagged revision of Item 1: when the tail holdout is
too small to form three above-floor disjoint partitions, the trainer must fall
back to a two-way (train + single holdout) path that STILL produces a model
(verdict capped at shadow_only), instead of the over-blocking no-model regression
that violated spec §6.5's low-sample shadow band.

WHY THIS FILE EXISTS (為什麼另立本檔):
  MIT 指出 Item 1 的三分修復「過度封鎖」：實測 n=200/250/300/350 短跨度下 holdout≈0.1·n
  使 val=5–8 < 三分地板(10)，原修復直接 fail-closed → NO model —— 這相對舊 holdout>=10
  行為是 regression，且違反 §6.5「低樣本 band 無論指標都要有 shadow_only 模型」。本檔
  以三條 acceptance 鎖住修訂：
    (a) 小樣本(n=200，holdout≈0.1·n 三分不可行) → two_way_shadow_capped 路徑：有模型、
        verdict <= shadow_only、provenance 旗標齊備，而非 no-model；
    (b) 大樣本(n=900) 仍走 three_way：三分區兩兩互斥、ship-gate 指標取自 test 分區、
        ship 資格保留；
    (c) two-way 退路下 verdict 永遠不得 should_ship（純 verdict 邏輯，隔離封頂）。

METHOD (方法):
  - (a)/(b) 端到端：注入假 lightgbm（本 Mac 無 lightgbm），只 stub「重運算 IO 邊界」
    (lgb.train)，split / 分區 / 指標選列等業務邏輯全部真跑；不呼叫真正的 lgb.train。
  - (c) 純 verdict 邏輯：直接構造 QuantileTrainingResult 餵 generate_acceptance_report，
    零 lightgbm / 零 IO / 零 runtime。embargo_enforced=True 以隔離「two-way 封頂」與
    「embargo 封頂」，避免斷言 vacuous。
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from program_code.ml_training.quantile_trainer import (
    MIN_CALIBRATION_ROWS,
    MIN_HOLDOUT_TWO_WAY_ROWS,
    MIN_TEST_ROWS,
    MIN_VALIDATION_ROWS,
    PARTITION_MODE_THREE_WAY,
    PARTITION_MODE_TWO_WAY,
    SHIP_GATE_SOURCE_TEST_PARTITION,
    SHIP_GATE_SOURCE_TWO_WAY,
    EmbargoConfig,
    PerQuantileMetrics,
    QuantileTrainingConfig,
    QuantileTrainingResult,
    _partition_holdout_three_way,
    _split_tail_holdout,
    train_quantile_trio,
)
from program_code.ml_training.quantile_reports import (
    SAMPLE_GATE_PROD,
    SAMPLE_GATE_SHADOW,
    VERDICT_NO_SHIP,
    VERDICT_SHADOW,
    VERDICT_SHIP,
    generate_acceptance_report,
)

# verdict 序級：should_ship(2) > shadow_only(1) > no_ship(0)。
_VERDICT_RANK = {VERDICT_NO_SHIP: 0, VERDICT_SHADOW: 1, VERDICT_SHIP: 2}


# ══════════════════════════════════════════════════════════════════
# 假 lightgbm 邊界（同 Item 1 E4 檔的方法：只 stub lgb.train，其餘真跑）
# ══════════════════════════════════════════════════════════════════

_CAPTURED_VALID_ROWS: list = []


class _FakeDataset:
    def __init__(self, data, label=None, weight=None, feature_name=None, reference=None):
        self.data = np.asarray(data)
        self.label = label
        self.weight = weight


class _FakeBooster:
    """身分傳遞 predictor：predict(X)=X[:,0]。測試令 X[:,0]==全域列索引，
    故可從預測值反查每批預測讀了哪些原始列。"""

    def __init__(self, best_iteration: int):
        self.best_iteration = best_iteration

    def predict(self, X):
        return np.asarray(X)[:, 0].astype(np.float64)


def _fake_train(params, train_set, num_boost_round=100, valid_sets=None, callbacks=None):
    if valid_sets:
        for vs in valid_sets:
            _CAPTURED_VALID_ROWS.append(np.asarray(vs.data)[:, 0].astype(np.int64))
    return _FakeBooster(best_iteration=min(7, int(num_boost_round)))


def _fake_early_stopping(rounds, verbose=False):
    return lambda env: None


@pytest.fixture()
def fake_lightgbm(monkeypatch):
    _CAPTURED_VALID_ROWS.clear()
    mod = types.ModuleType("lightgbm")
    mod.Dataset = _FakeDataset
    mod.train = _fake_train
    mod.early_stopping = _fake_early_stopping
    monkeypatch.setitem(sys.modules, "lightgbm", mod)
    return mod


def _make_traceable_dataset(n: int, n_features: int = 4, seed: int = 7):
    """X[:,0]==全域列索引(float)，其餘欄雜訊；壓縮時間戳(1 分鐘 bar)使
    _split_tail_holdout 走 min_fraction≈0.1·n 尾段切分（holdout≈0.1·n）。"""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, n_features)).astype(np.float32)
    X[:, 0] = np.arange(n, dtype=np.float32)
    y = rng.standard_normal(n).astype(np.float32)
    ts = (np.arange(n, dtype=np.int64) * 60_000)
    return X, y, ts


# ══════════════════════════════════════════════════════════════════
# (a) 小樣本：holdout 三分不可行 → two_way_shadow_capped（有模型、非 no-model）
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("n", [200, 250, 300, 350])
def test_small_sample_subfloor_yields_two_way_shadow_model_not_no_model(fake_lightgbm, n):
    """MIT 引用的 regression band：n∈{200,250,300,350}、holdout≈0.1·n → 三分區的
    val=int(holdout·0.25) < 地板(10)，三分不可行。修訂後必須產出 two-way 模型
    （success=True + partition_mode=two_way_shadow_capped + provenance 旗標），
    而非 degenerate no-model。"""
    # 先用真實 split 函式確認此 n 確實落在「三分不可行、兩分可行」的 sub-floor 帶。
    _, holdout_idx = _split_tail_holdout(np.arange(n, dtype=np.int64) * 60_000, 7.0)
    val_idx, calib_idx, test_idx = _partition_holdout_three_way(holdout_idx)
    assert (
        len(val_idx) < MIN_VALIDATION_ROWS
        or len(calib_idx) < MIN_CALIBRATION_ROWS
        or len(test_idx) < MIN_TEST_ROWS
    ), f"n={n} 預期三分不可行，實得 val/calib/test={len(val_idx)}/{len(calib_idx)}/{len(test_idx)}"
    assert len(holdout_idx) >= MIN_HOLDOUT_TWO_WAY_ROWS  # 兩分退路可行

    X, y, ts = _make_traceable_dataset(n)
    cfg = QuantileTrainingConfig(
        n_estimators=40, early_stopping_rounds=8, bootstrap_iterations=32,
    )
    result = train_quantile_trio(
        features=X, labels=y, timestamps_ms=ts,
        feature_names=[f"f{i}" for i in range(X.shape[1])],
        strategy_name="ma_crossover", engine_mode="paper", config=cfg,
    )

    # 核心 acceptance：有模型，不是 no-model。
    assert result.success, result.error
    assert result.error == ""
    assert set(result.models.keys()) == {"q10", "q50", "q90"}
    # provenance 旗標明示走了 two-way 退路（隔離於 embargo 封頂之外的獨立證據）。
    assert result.partition_mode == PARTITION_MODE_TWO_WAY
    assert result.ship_gate_metric_source == SHIP_GATE_SOURCE_TWO_WAY
    # 兩分下：單一 holdout 三角色共用，n_validation/n_calibration/n_test 皆等於 holdout。
    assert result.n_validation == result.n_calibration == result.n_test == len(holdout_idx)

    # 驗收報告：verdict <= shadow_only（絕不 should_ship），且 report 溯源旗標齊備。
    report = generate_acceptance_report(result, cfg, include_train_serve_harness=False)
    assert _VERDICT_RANK[report["verdict"]] <= _VERDICT_RANK[VERDICT_SHADOW]
    assert report["verdict"] != VERDICT_SHIP
    assert report["partition_mode"] == PARTITION_MODE_TWO_WAY
    assert report["ship_gate_metric_source"] == SHIP_GATE_SOURCE_TWO_WAY


def test_genuinely_degenerate_holdout_still_fails_closed(fake_lightgbm):
    """真正退化（holdout < 兩分絕對下限）仍 fail-closed，非兩分放行。
    n=65 壓縮 → holdout≈6 < MIN_HOLDOUT_TWO_WAY_ROWS(10) → degenerate。"""
    n = 65
    X, y, ts = _make_traceable_dataset(n)
    result = train_quantile_trio(
        features=X, labels=y, timestamps_ms=ts,
        feature_names=[f"f{i}" for i in range(X.shape[1])],
        strategy_name="ma_crossover", engine_mode="paper",
        config=QuantileTrainingConfig(),
    )
    assert not result.success
    assert "degenerate split" in result.error


# ══════════════════════════════════════════════════════════════════
# (b) 大樣本：three_way 保留 —— 三分區兩兩互斥 + 指標取自 test 分區 + ship 資格保留
# ══════════════════════════════════════════════════════════════════

def test_large_sample_keeps_three_way_disjoint_and_test_sourced(fake_lightgbm):
    """n=900：holdout 夠大 → three_way；三分區兩兩互斥、指標源自 test 分區、
    分區列數守恆（val+calib+test==holdout）。與 sub-floor 退路互為對照。"""
    n = 900
    X, y, ts = _make_traceable_dataset(n)
    cfg = QuantileTrainingConfig(
        n_estimators=40, early_stopping_rounds=8, bootstrap_iterations=32,
    )
    result = train_quantile_trio(
        features=X, labels=y, timestamps_ms=ts,
        feature_names=[f"f{i}" for i in range(X.shape[1])],
        strategy_name="ma_crossover", engine_mode="paper", config=cfg,
    )
    assert result.success, result.error
    assert result.partition_mode == PARTITION_MODE_THREE_WAY
    assert result.ship_gate_metric_source == SHIP_GATE_SOURCE_TEST_PARTITION

    # oracle：獨立用真實 split 函式算出各分區列，反查結果讀到的列。
    train_idx, holdout_idx = _split_tail_holdout(ts, 7.0)
    val_idx, calib_idx, test_idx = _partition_holdout_three_way(holdout_idx)

    got_test_rows = set(np.rint(result.test_q50_pred).astype(int).tolist())
    got_calib_rows = set(np.rint(result.calibration_q50_pred).astype(int).tolist())
    assert _CAPTURED_VALID_ROWS, "fake lgb.train 未捕獲 valid_sets"
    got_val_rows = set(_CAPTURED_VALID_ROWS[0].tolist())

    # 三組列兩兩互斥（反洩漏核心）+ 命中 oracle 分區。
    assert got_val_rows == set(val_idx.tolist())
    assert got_calib_rows == set(calib_idx.tolist())
    assert got_test_rows == set(test_idx.tolist())
    assert got_val_rows.isdisjoint(got_calib_rows)
    assert got_val_rows.isdisjoint(got_test_rows)
    assert got_calib_rows.isdisjoint(got_test_rows)

    # 各過地板 + 分區列數守恆。
    assert result.n_validation >= MIN_VALIDATION_ROWS
    assert result.n_calibration >= MIN_CALIBRATION_ROWS
    assert result.n_test >= MIN_TEST_ROWS
    assert result.n_validation + result.n_calibration + result.n_test == result.n_holdout

    # report 溯源標記 = test_partition（未污染）。
    report = generate_acceptance_report(result, cfg, include_train_serve_harness=False)
    assert report["ship_gate_metric_source"] == SHIP_GATE_SOURCE_TEST_PARTITION
    assert report["partition_mode"] == PARTITION_MODE_THREE_WAY


# ══════════════════════════════════════════════════════════════════
# (c) 純 verdict 邏輯：two-way 退路下 verdict 永不 should_ship（隔離封頂）
# ══════════════════════════════════════════════════════════════════

def _make_shippable_result(
    *,
    n_labeled: int,
    partition_mode: str,
    ship_gate_metric_source: str,
) -> QuantileTrainingResult:
    """構造「五 metric gate 全過 + embargo 已強制」的成功結果，只變動 partition_mode /
    來源標記；用來隔離證明 two-way 封頂（非因 gate 失敗、非因 embargo 未強制）。"""
    def _m(alpha: float) -> PerQuantileMetrics:
        return PerQuantileMetrics(
            alpha=alpha,
            pinball_loss=0.5,
            pinball_loss_baseline_constant=1.0,
            pinball_skill=0.30,
            empirical_coverage=alpha,
            coverage_error_pp=1.5,
            best_iteration=50,
            n_train=400,
            n_holdout=100,
            linear_qr_pinball_loss=0.9,
            linear_qr_pinball_skill=0.10,
        )

    return QuantileTrainingResult(
        success=True,
        strategy_name="ma_crossover",
        engine_mode="demo",
        feature_names=["f0", "f1", "f2"],
        n_samples_total=n_labeled,
        n_samples_labeled=n_labeled,
        n_holdout=100,
        n_validation=25,
        n_calibration=25,
        n_test=50,
        partition_mode=partition_mode,
        ship_gate_metric_source=ship_gate_metric_source,
        models={"q10": object(), "q50": object(), "q90": object()},
        per_quantile_metrics={"q10": _m(0.10), "q50": _m(0.50), "q90": _m(0.90)},
        decile_lift_point=2.0,
        decile_lift_ci_lower=1.6,
        decile_lift_ci_upper=2.4,
        crossing_rate=0.005,
        feature_schema_hash="sha256:" + "0" * 16,
        feature_definition_hash="sha256:" + "1" * 16,
        embargo_config=EmbargoConfig(embargo_hours=24, holdout_tail_days=7.0),
        embargo_enforced=True,  # 隔離：確保封頂來自 two-way 而非 embargo
        embargo_overlap_count=0,
    )


@pytest.mark.parametrize(
    "n_labeled",
    [SAMPLE_GATE_SHADOW - 1, SAMPLE_GATE_SHADOW + 50, SAMPLE_GATE_PROD + 50],
)
def test_two_way_verdict_never_should_ship(n_labeled):
    """two-way 退路下，任何樣本桶（含 full 桶 + 全 gate 過，§6.5 本應 should_ship）
    verdict 都 <= shadow_only、絕不 should_ship。這是修訂的反洩漏封頂主張。"""
    cfg = QuantileTrainingConfig()
    res = _make_shippable_result(
        n_labeled=n_labeled,
        partition_mode=PARTITION_MODE_TWO_WAY,
        ship_gate_metric_source=SHIP_GATE_SOURCE_TWO_WAY,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert _VERDICT_RANK[report["verdict"]] <= _VERDICT_RANK[VERDICT_SHADOW]
    assert report["verdict"] != VERDICT_SHIP


def test_two_way_full_sample_all_gates_pass_is_capped_to_shadow():
    """關鍵情境：full 樣本 + 五 gate 全過 + embargo 已強制（本應 should_ship），
    因 partition_mode=two_way_shadow_capped 被硬性封頂 shadow_only，reason 誠實揭露。"""
    cfg = QuantileTrainingConfig()
    res = _make_shippable_result(
        n_labeled=SAMPLE_GATE_PROD + 50,
        partition_mode=PARTITION_MODE_TWO_WAY,
        ship_gate_metric_source=SHIP_GATE_SOURCE_TWO_WAY,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    # 五 metric gate 本身全過（證明封頂非因 gate 失敗），且 embargo 已強制（非 embargo 封頂）。
    assert report["all_hard_gates_pass"] is True
    assert report["embargo_enforced"] is True
    assert report["verdict"] == VERDICT_SHADOW
    assert "two-way holdout fallback" in report["verdict_reason"]


def test_control_three_way_full_sample_all_gates_pass_still_ships():
    """對照：three_way + full 樣本 + 全 gate 過 + embargo 已強制 → 正常 should_ship。
    證明 two-way 封頂只針對 two_way_shadow_capped，未過度封鎖合法 three_way ship 路徑
    （否則上面的封頂斷言變 vacuous）。"""
    cfg = QuantileTrainingConfig()
    res = _make_shippable_result(
        n_labeled=SAMPLE_GATE_PROD + 50,
        partition_mode=PARTITION_MODE_THREE_WAY,
        ship_gate_metric_source=SHIP_GATE_SOURCE_TEST_PARTITION,
    )
    report = generate_acceptance_report(res, cfg, include_train_serve_harness=False)
    assert report["verdict"] == VERDICT_SHIP
    assert report["partition_mode"] == PARTITION_MODE_THREE_WAY
    assert "two-way holdout fallback" not in report["verdict_reason"]
