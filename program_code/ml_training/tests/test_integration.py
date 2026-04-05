"""
Phase 3b integration test — Optuna TPE → Thompson Sampling pipeline.
Phase 3b 集成測試 — Optuna TPE → Thompson Sampling 管線。

MODULE_NOTE (EN): End-to-end test of the 2-layer optimization pipeline.
  Uses synthetic data (no PG, no IPC, no running engine required).
MODULE_NOTE (中): 兩層優化管線的端到端測試。
  使用合成數據（無需 PG、IPC 或運行中的引擎）。
"""

from __future__ import annotations

import pytest
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Module imports with graceful fallback / 模組導入，優雅降級
# ─────────────────────────────────────────────────────────────────────────────

try:
    from program_code.ml_training.optuna_optimizer import compute_ev_net
except ImportError:
    compute_ev_net = None  # type: ignore[assignment]

try:
    from program_code.ml_training.thompson_sampling import (
        NIGPosterior,
        empirical_bayes_init,
        update_posterior,
        select_next_arm,
        posteriors_to_dict,
        posteriors_from_dict,
    )
except ImportError:
    NIGPosterior = None  # type: ignore[assignment, misc]
    empirical_bayes_init = None  # type: ignore[assignment]
    update_posterior = None  # type: ignore[assignment]
    select_next_arm = None  # type: ignore[assignment]
    posteriors_to_dict = None  # type: ignore[assignment]
    posteriors_from_dict = None  # type: ignore[assignment]

try:
    from program_code.ml_training.cpcv_validator import validate_cpcv, CPCVResult
except ImportError:
    validate_cpcv = None  # type: ignore[assignment]
    CPCVResult = None  # type: ignore[assignment, misc]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / 輔助函數
# ─────────────────────────────────────────────────────────────────────────────

# Reproducible RNG / 可重現隨機數生成器
_RNG = np.random.default_rng(seed=42)

# Synthetic strategy-symbol pairs / 合成的策略-幣種對
_PAIRS = [
    ("ma_crossover", "BTCUSDT"),
    ("ma_crossover", "ETHUSDT"),
    ("bb_reversion", "BTCUSDT"),
    ("bb_reversion", "ETHUSDT"),
]


def _make_fills(n: int, rng: np.random.Generator) -> list[dict]:
    """Generate synthetic fills with random PnL (mix of wins and losses).
    生成含隨機 PnL（勝負混合）的合成成交。

    Args:
        n: number of fills / 成交數量
        rng: numpy random generator / numpy 隨機生成器

    Returns:
        list of fill dicts with 'pnl' and 'fee' keys / 含 'pnl' 和 'fee' 鍵的成交字典列表
    """
    fills: list[dict] = []
    for _ in range(n):
        # ~55% chance positive, ~45% negative → slight positive edge
        # ~55% 正值機率, ~45% 負值 → 微正優勢
        pnl = float(rng.normal(loc=0.5, scale=5.0))
        fee = abs(pnl) * 0.0006
        fills.append({"pnl": pnl, "fee": fee})
    return fills


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Optuna EV → Thompson Sampling pipeline
# 測試 1: Optuna EV → Thompson Sampling 管線
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    compute_ev_net is None or empirical_bayes_init is None,
    reason="optuna_optimizer or thompson_sampling not importable",
)
def test_optuna_to_ts_pipeline() -> None:
    """Full pipeline: synthetic fills → EV_net → TS init → update → select → serialize.
    完整管線：合成成交 → EV_net → TS 初始化 → 更新 → 選擇 → 序列化。"""
    rng = np.random.default_rng(seed=42)

    # Step 1: Generate synthetic fills — 100 per pair, 2 strategies × 2 symbols = 400 total
    # 步驟 1: 生成合成成交 — 每對 100 筆, 2 策略 × 2 幣種 = 共 400 筆
    pair_fills: dict[str, list[dict]] = {}
    for strat, sym in _PAIRS:
        key = f"{strat}_{sym}"
        pair_fills[key] = _make_fills(100, rng)

    # Step 2: Compute EV_net for each pair / 步驟 2: 計算每對的 EV_net
    ev_values: dict[str, float] = {}
    for key, fills in pair_fills.items():
        ev = compute_ev_net(fills)
        ev_values[key] = ev
        # EV should be finite / EV 應為有限值
        assert np.isfinite(ev), f"EV_net for {key} is not finite: {ev}"

    # Step 3: Initialize NIG posteriors via empirical Bayes / 步驟 3: 用 empirical Bayes 初始化 NIG 後驗
    posteriors: dict[str, NIGPosterior] = {}
    for key, ev in ev_values.items():
        posteriors[key] = empirical_bayes_init([ev])

    assert len(posteriors) == len(_PAIRS), (
        f"Expected {len(_PAIRS)} posteriors, got {len(posteriors)} / "
        f"期望 {len(_PAIRS)} 個後驗，得到 {len(posteriors)} 個"
    )

    # Step 4: 5 iterations — select arm, simulate observation, update posterior
    # 步驟 4: 5 次迭代 — 選臂、模擬觀測、更新後驗
    for _ in range(5):
        arm = select_next_arm(posteriors)
        assert arm in posteriors, (
            f"Selected arm '{arm}' not in posteriors / "
            f"選定臂 '{arm}' 不在後驗中"
        )
        # Simulate a random PnL observation for the selected arm / 為選定臂模擬隨機 PnL 觀測
        observation = float(rng.normal(loc=0.3, scale=2.0))
        posteriors[arm] = update_posterior(posteriors[arm], observation)

    # Step 5: Verify final state / 步驟 5: 驗證最終狀態
    # All posteriors should have n_trials >= 0 (some may not have been selected)
    # 所有後驗的 n_trials >= 0（部分可能未被選中）
    total_trials = sum(p.n_trials for p in posteriors.values())
    assert total_trials >= 5, (
        f"Expected >=5 total trials, got {total_trials} / "
        f"期望 >=5 總試驗數，得到 {total_trials}"
    )

    # select_next_arm should still return a valid key / select_next_arm 仍應返回有效鍵
    final_arm = select_next_arm(posteriors)
    assert final_arm in posteriors

    # Serialization roundtrip / 序列化往返測試
    serialized = posteriors_to_dict(posteriors)
    assert isinstance(serialized, dict)
    assert len(serialized) == len(posteriors)

    deserialized = posteriors_from_dict(serialized)
    assert isinstance(deserialized, dict)
    assert set(deserialized.keys()) == set(posteriors.keys())

    # Verify deserialized values match / 驗證反序列化值匹配
    for key in posteriors:
        orig = posteriors[key]
        restored = deserialized[key]
        assert restored.mu == pytest.approx(orig.mu, abs=1e-10), (
            f"mu mismatch for {key} / {key} 的 mu 不匹配"
        )
        assert restored.n_trials == orig.n_trials, (
            f"n_trials mismatch for {key} / {key} 的 n_trials 不匹配"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: CPCV with mock model / 測試 2: 使用模擬模型的 CPCV
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    validate_cpcv is None,
    reason="cpcv_validator not importable",
)
def test_cpcv_with_mock_model() -> None:
    """CPCV validation with synthetic data and mock model_fn.
    使用合成數據和模擬 model_fn 的 CPCV 驗證。"""
    rng = np.random.default_rng(seed=42)

    n_samples = 500

    # Step 1: Synthetic timestamps spanning 180 days (in epoch seconds)
    # 步驟 1: 跨 180 天的合成時間戳（epoch 秒）
    start_ts = 1_700_000_000.0  # arbitrary start / 任意起點
    end_ts = start_ts + 180 * 24 * 3600  # +180 days / +180 天
    timestamps = np.linspace(start_ts, end_ts, n_samples)

    # Step 2: Synthetic features (500 × 10) and labels (500,)
    # 步驟 2: 合成特徵 (500 × 10) 和標籤 (500,)
    X = rng.standard_normal((n_samples, 10))
    y = rng.standard_normal(n_samples)

    # Step 3: Mock model_fn — returns fixed metrics regardless of input
    # 步驟 3: 模擬 model_fn — 無論輸入均返回固定指標
    def mock_model_fn(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict:
        """Mock model returning constant metrics / 返回常量指標的模擬模型。"""
        return {"rmse": 0.5, "correlation": 0.3, "sharpe": 0.8}

    # Step 4: Run CPCV validation / 步驟 4: 運行 CPCV 驗證
    result = validate_cpcv(X, y, timestamps, "trending", mock_model_fn)

    # Step 5: Verify results / 步驟 5: 驗證結果
    assert isinstance(result, CPCVResult), (
        f"Expected CPCVResult, got {type(result)} / 期望 CPCVResult，得到 {type(result)}"
    )

    # 4 fold_metrics (default n_folds=4) / 4 個折疊指標（默認 n_folds=4）
    assert len(result.fold_metrics) == 4, (
        f"Expected 4 fold_metrics, got {len(result.fold_metrics)} / "
        f"期望 4 個 fold_metrics，得到 {len(result.fold_metrics)}"
    )

    # mean_sharpe > 0 (mock returns 0.8 for every fold) / mean_sharpe > 0（模擬每折返回 0.8）
    assert result.mean_sharpe > 0, (
        f"Expected mean_sharpe > 0, got {result.mean_sharpe} / "
        f"期望 mean_sharpe > 0，得到 {result.mean_sharpe}"
    )

    # power_estimate > 0 (500 samples across 4 folds is plenty)
    # power_estimate > 0（500 樣本 4 折足夠）
    assert result.power_estimate > 0, (
        f"Expected power_estimate > 0, got {result.power_estimate} / "
        f"期望 power_estimate > 0，得到 {result.power_estimate}"
    )

    # strategy_type matches input / strategy_type 匹配輸入
    assert result.strategy_type == "trending", (
        f"Expected strategy_type='trending', got '{result.strategy_type}' / "
        f"期望 strategy_type='trending'，得到 '{result.strategy_type}'"
    )

    # embargo_hours == 24 for trending strategies / trending 策略的 embargo_hours == 24
    assert result.embargo_hours == 24, (
        f"Expected embargo_hours=24, got {result.embargo_hours} / "
        f"期望 embargo_hours=24，得到 {result.embargo_hours}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Full pipeline roundtrip — EV → CPCV → Thompson Sampling
# 測試 3: 完整管線往返 — EV → CPCV → Thompson Sampling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    any(fn is None for fn in [compute_ev_net, validate_cpcv, empirical_bayes_init]),
    reason="one or more required modules not importable",
)
def test_full_pipeline_roundtrip() -> None:
    """Complete pipeline: Optuna EV → CPCV validation → Thompson Sampling allocation.
    完整管線：Optuna EV → CPCV 驗證 → Thompson Sampling 資源分配。"""
    rng = np.random.default_rng(seed=42)

    # 3 synthetic strategy-symbol pairs / 3 個合成策略-幣種對
    pairs = [
        ("ma_crossover", "BTCUSDT"),
        ("bb_reversion", "ETHUSDT"),
        ("momentum", "SOLUSDT"),
    ]

    # Shared synthetic data for CPCV (reused across pairs for simplicity)
    # 共用合成數據（為簡便起見跨對重用）
    n_samples = 500
    start_ts = 1_700_000_000.0
    end_ts = start_ts + 180 * 24 * 3600
    timestamps = np.linspace(start_ts, end_ts, n_samples)
    X = rng.standard_normal((n_samples, 10))
    y = rng.standard_normal(n_samples)

    def mock_model_fn(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict:
        """Mock model returning constant metrics / 返回常量指標的模擬模型。"""
        return {"rmse": 0.5, "correlation": 0.3, "sharpe": 0.8}

    # Step 1: Compute EV_net for each pair / 步驟 1: 計算每對的 EV_net
    ev_values: dict[str, float] = {}
    for strat, sym in pairs:
        key = f"{strat}_{sym}"
        fills = _make_fills(100, rng)
        ev = compute_ev_net(fills)
        ev_values[key] = ev
        assert np.isfinite(ev), f"EV_net not finite for {key} / {key} 的 EV_net 非有限值"

    # Step 2: CPCV validation for each pair / 步驟 2: 每對的 CPCV 驗證
    cpcv_results: dict[str, CPCVResult] = {}
    for strat, sym in pairs:
        key = f"{strat}_{sym}"
        # Use strategy name for embargo lookup / 使用策略名進行 embargo 查找
        result = validate_cpcv(X, y, timestamps, strat, mock_model_fn)
        cpcv_results[key] = result
        assert result.mean_sharpe > 0, (
            f"CPCV mean_sharpe <= 0 for {key} / {key} 的 CPCV mean_sharpe <= 0"
        )

    # Step 3: Initialize TS posteriors from EV values / 步驟 3: 從 EV 值初始化 TS 後驗
    posteriors: dict[str, NIGPosterior] = {}
    for key, ev in ev_values.items():
        posteriors[key] = empirical_bayes_init([ev])

    # Step 4: Update TS posteriors with CPCV mean_sharpe as observations
    # 步驟 4: 使用 CPCV mean_sharpe 作為觀測更新 TS 後驗
    for key, cpcv_res in cpcv_results.items():
        posteriors[key] = update_posterior(posteriors[key], cpcv_res.mean_sharpe)

    # Step 5: Select next arm / 步驟 5: 選擇下一臂
    selected_arm = select_next_arm(posteriors)

    # Step 6: Verify full chain produced a valid arm key
    # 步驟 6: 驗證完整鏈條產生了有效的臂鍵
    assert selected_arm in posteriors, (
        f"Selected arm '{selected_arm}' not in posteriors / "
        f"選定臂 '{selected_arm}' 不在後驗中"
    )

    # All posteriors should have exactly 1 trial (from the CPCV Sharpe update)
    # 所有後驗應恰好有 1 次試驗（來自 CPCV Sharpe 更新）
    for key, post in posteriors.items():
        assert post.n_trials == 1, (
            f"Expected n_trials=1 for {key}, got {post.n_trials} / "
            f"期望 {key} 的 n_trials=1，得到 {post.n_trials}"
        )
