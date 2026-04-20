"""
Tests for Optuna TPE parameter optimizer.
Optuna TPE 參數優化器測試。

MODULE_NOTE (EN): 8 self-contained tests — no PG, no IPC needed.
  Mocks IPC calls where needed. Validates study naming, search space
  filtering, distribution types, EV_net math, config defaults, and
  insufficient-data early return.
MODULE_NOTE (中): 8 個自包含測試 — 無需 PG、無需 IPC。
  需要時 mock IPC 調用。驗證 study 命名、搜索空間過濾、分佈類型、
  EV_net 數學、配置默認值、數據不足的提前返回。
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

# Conditional import — skip all if optuna not available
# 條件導入 — optuna 不可用時跳過所有測試
optuna = pytest.importorskip("optuna")

from program_code.ml_training.optuna_optimizer import (
    OptunaConfig,
    apply_bh_fdr,
    build_search_space,
    compute_ev_net,
    compute_multi_objective_metrics,
    create_study,
    run_multi_objective_optimization,
    run_optimization,
)
from optuna.distributions import FloatDistribution, IntDistribution


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 測試夾具
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_journal(tmp_path):
    """Temporary journal file for Optuna studies / Optuna study 的臨時日誌文件"""
    return str(tmp_path / "test_studies.log")


@pytest.fixture
def sample_param_ranges_json() -> str:
    """Sample param_ranges JSON matching Rust ParamRange structure.
    匹配 Rust ParamRange 結構的示例 param_ranges JSON。
    """
    ranges = [
        {
            "name": "cooldown_ms",
            "min": 60000.0,
            "max": 3600000.0,
            "step": 60000.0,
            "agent_adjustable": True,
            "db_persisted": True,
        },
        {
            "name": "adx_threshold",
            "min": 10.0,
            "max": 50.0,
            "step": 1.0,
            "agent_adjustable": True,
            "db_persisted": True,
        },
        {
            "name": "default_qty",
            "min": 0.001,
            "max": 1e12,
            "step": None,
            "agent_adjustable": False,
            "db_persisted": True,
        },
        {
            "name": "higher_tf_alpha",
            "min": 0.001,
            "max": 0.05,
            "step": None,
            "agent_adjustable": True,
            "db_persisted": True,
        },
        {
            "name": "volume_threshold",
            "min": 1.0,
            "max": 5.0,
            "step": 0.1,
            "agent_adjustable": True,
            "db_persisted": True,
        },
    ]
    return json.dumps(ranges)


@pytest.fixture
def winning_fills() -> list[dict]:
    """Fills with mostly wins / 以勝單為主的成交"""
    return [
        {"pnl": 10.0},
        {"pnl": 15.0},
        {"pnl": 20.0},
        {"pnl": -5.0},
        {"pnl": 12.0},
        {"pnl": -3.0},
        {"pnl": 8.0},
        {"pnl": 18.0},
    ]


@pytest.fixture
def losing_fills() -> list[dict]:
    """Fills with all losses / 全為虧損的成交"""
    return [
        {"pnl": -10.0},
        {"pnl": -15.0},
        {"pnl": -20.0},
        {"pnl": -5.0},
        {"pnl": -8.0},
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests / 測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateStudy:
    """Tests for create_study / create_study 測試"""

    def test_create_study_naming(self, tmp_journal: str) -> None:
        """Study name follows {strategy}_{symbol}_{regime} convention.
        Study 名稱遵循 {strategy}_{symbol}_{regime} 約定。
        """
        config = OptunaConfig(sqlite_path=tmp_journal)
        study = create_study("ma_crossover", "BTCUSDT", "trending", config)

        assert study.study_name == "ma_crossover_BTCUSDT_trending"


class TestBuildSearchSpace:
    """Tests for build_search_space / build_search_space 測試"""

    def test_build_search_space_filters_non_adjustable(
        self, sample_param_ranges_json: str
    ) -> None:
        """Only agent_adjustable=true params are included in the space.
        僅 agent_adjustable=true 的參數被包含在搜索空間中。
        """
        space = build_search_space(sample_param_ranges_json)

        # "default_qty" has agent_adjustable=false — must be excluded
        # "default_qty" 的 agent_adjustable=false — 必須被排除
        assert "default_qty" not in space
        assert "cooldown_ms" in space
        assert "adx_threshold" in space
        assert "higher_tf_alpha" in space
        assert "volume_threshold" in space
        assert len(space) == 4

    def test_build_search_space_types(
        self, sample_param_ranges_json: str
    ) -> None:
        """Int distribution for step>=1 with integer bounds; float otherwise.
        step>=1 且整數邊界用 IntDistribution；否則用 FloatDistribution。
        """
        space = build_search_space(sample_param_ranges_json)

        # cooldown_ms: step=60000, min=60000, max=3600000 — all integer-valued → Int
        assert isinstance(space["cooldown_ms"], IntDistribution)

        # adx_threshold: step=1.0, min=10.0, max=50.0 — integer-valued → Int
        assert isinstance(space["adx_threshold"], IntDistribution)

        # higher_tf_alpha: step=None, min=0.001, max=0.05 → Float (continuous)
        assert isinstance(space["higher_tf_alpha"], FloatDistribution)

        # volume_threshold: step=0.1 (< 1.0) → Float with step
        assert isinstance(space["volume_threshold"], FloatDistribution)
        assert space["volume_threshold"].step == 0.1


class TestComputeEvNet:
    """Tests for compute_ev_net / compute_ev_net 測試"""

    def test_compute_ev_net_positive(self, winning_fills: list[dict]) -> None:
        """Mostly winning fills produce positive EV_net.
        以勝單為主的成交產生正 EV_net。
        """
        ev = compute_ev_net(winning_fills)
        assert ev > 0.0, f"Expected positive EV, got {ev}"

    def test_compute_ev_net_no_fills(self) -> None:
        """Empty fills list returns 0.0 / 空成交列表返回 0.0"""
        assert compute_ev_net([]) == 0.0

    def test_compute_ev_net_all_losses(self, losing_fills: list[dict]) -> None:
        """All-loss fills produce negative EV_net.
        全虧損成交產生負 EV_net。
        """
        ev = compute_ev_net(losing_fills)
        assert ev < 0.0, f"Expected negative EV, got {ev}"

        # Verify the math manually / 手動驗證數學
        # p=0, avg_loss=11.6, c_loss=0.0006*11.6
        # EV = 0 - 1*(11.6 + 0.00696) = -11.60696
        expected = -(11.6 + 0.0006 * 11.6)
        assert abs(ev - expected) < 1e-6, f"Expected ~{expected}, got {ev}"


class TestOptunaConfig:
    """Tests for OptunaConfig defaults / OptunaConfig 默認值測試"""

    def test_optuna_config_defaults(self) -> None:
        """Verify default configuration values.
        驗證默認配置值。
        """
        from program_code.ml_training.optuna_optimizer import DEFAULT_JOURNAL_PATH

        cfg = OptunaConfig()
        # Default honours OPENCLAW_DATA_DIR (Mac compat); compare via the module
        # constant rather than a hardcoded path.
        # 默認尊重 OPENCLAW_DATA_DIR（Mac 相容）；用模組常量比較而非硬編碼路徑。
        assert cfg.sqlite_path == DEFAULT_JOURNAL_PATH
        assert cfg.sqlite_path.endswith("/optuna_studies.log")
        assert cfg.n_trials == 30
        assert cfg.min_fills_required == 80


class TestRunOptimization:
    """Tests for run_optimization / run_optimization 測試"""

    def test_run_optimization_insufficient_data(
        self, tmp_journal: str, sample_param_ranges_json: str
    ) -> None:
        """Returns early with warning when fills < min_fills_required.
        當成交數 < min_fills_required 時提前返回並警告。
        """
        config = OptunaConfig(sqlite_path=tmp_journal, min_fills_required=80)
        # Only 5 fills — far below the 80 threshold
        # 僅 5 筆成交 — 遠低於 80 的門檻
        few_fills = [{"pnl": 1.0}] * 5

        result = run_optimization(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            regime="trending",
            fills=few_fills,
            param_ranges_json=sample_param_ranges_json,
            config=config,
        )

        assert result["status"] == "insufficient_data"
        assert result["n_trials"] == 0
        assert result["best_params"] == {}
        assert result["best_value"] == 0.0
        assert "5" in result["error"]
        assert "80" in result["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3b-07: Benjamini-Hochberg FDR tests / BH-FDR 測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestBHFDR:
    """Tests for apply_bh_fdr() — multiple comparison correction.
    apply_bh_fdr() 多重比較校正測試。"""

    def test_all_significant_pass(self):
        """All very small p-values → all rejected."""
        p = [0.001, 0.002, 0.003, 0.004]
        rejected, adj = apply_bh_fdr(p, alpha=0.05)
        assert all(rejected)
        assert len(adj) == 4
        assert all(0.0 <= a <= 1.0 for a in adj)

    def test_all_null_no_reject(self):
        """All large p-values → none rejected."""
        p = [0.6, 0.7, 0.8, 0.9]
        rejected, _ = apply_bh_fdr(p, alpha=0.05)
        assert not any(rejected)

    def test_known_textbook_example(self):
        """Known BH worked example: m=4, alpha=0.05.
        p = [0.005, 0.01, 0.04, 0.5]
        thresholds (k/m)*alpha = 0.0125, 0.025, 0.0375, 0.05
        Compare sorted: 0.005<=0.0125 ✓, 0.01<=0.025 ✓, 0.04<=0.0375 ✗
        Largest k satisfying: 2 → reject ranks 1 and 2.
        """
        p = [0.5, 0.005, 0.04, 0.01]
        rejected, _ = apply_bh_fdr(p, alpha=0.05)
        # Original positions: 0.005 (idx1) and 0.01 (idx3) should be rejected
        assert rejected[1] is True
        assert rejected[3] is True
        assert rejected[0] is False
        assert rejected[2] is False

    def test_adjusted_p_monotone_in_order(self):
        """Adjusted p-values when sorted should be monotone non-decreasing."""
        p = [0.001, 0.005, 0.02, 0.04, 0.5, 0.9]
        _, adj = apply_bh_fdr(p, alpha=0.05)
        sorted_adj = sorted(adj)
        for i in range(len(sorted_adj) - 1):
            assert sorted_adj[i] <= sorted_adj[i + 1] + 1e-12

    def test_nan_treated_as_one(self):
        """NaN/None p-values → conservative 1.0, not rejected."""
        p = [0.001, float("nan"), None, 0.002]
        rejected, adj = apply_bh_fdr(p, alpha=0.05)
        assert rejected[0]
        assert rejected[3]
        assert not rejected[1]
        assert not rejected[2]
        assert adj[1] >= 0.99
        assert adj[2] >= 0.99

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            apply_bh_fdr([])

    def test_alpha_out_of_range(self):
        with pytest.raises(ValueError):
            apply_bh_fdr([0.01, 0.02], alpha=0.0)
        with pytest.raises(ValueError):
            apply_bh_fdr([0.01, 0.02], alpha=1.0)

    def test_order_preserved(self):
        """Output ordering matches input ordering, not sorted."""
        p = [0.9, 0.001, 0.5]
        rejected, adj = apply_bh_fdr(p, alpha=0.05)
        assert len(rejected) == 3
        assert rejected[1] is True  # 0.001 in middle position
        assert adj[1] < adj[0]
        assert adj[1] < adj[2]


# ═══════════════════════════════════════════════════════════════════════════════
# 3b-08: Multi-objective Pareto tests / 多目標 Pareto 測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestMultiObjective:
    """Tests for run_multi_objective_optimization() and metric helper."""

    def test_compute_metrics_empty(self):
        s, mdd, t = compute_multi_objective_metrics([], {}, {})
        assert s == 0.0
        assert mdd == 0.0
        assert t == 0.0

    def test_compute_metrics_basic_pnls(self):
        # 3 wins, 2 losses → positive sharpe, finite drawdown
        fills = [
            {"pnl": 2.0, "qty": 1.0},
            {"pnl": -1.0, "qty": 1.0},
            {"pnl": 3.0, "qty": 1.0},
            {"pnl": -2.0, "qty": 1.0},
            {"pnl": 4.0, "qty": 1.0},
        ]
        s, mdd, t = compute_multi_objective_metrics(fills, {}, {})
        assert s > 0
        assert mdd >= 0
        assert t == 5.0  # 5 fills × qty 1.0

    def test_compute_metrics_with_notional(self):
        fills = [
            {"pnl": 1.0, "notional": 100.0},
            {"pnl": -0.5, "notional": 200.0},
        ]
        _, _, t = compute_multi_objective_metrics(fills, {}, {})
        assert t == 300.0

    def test_run_multi_objective_insufficient_data(self):
        result = run_multi_objective_optimization(
            "ma_crossover",
            "BTCUSDT",
            "trending",
            fills=[{"pnl": 1.0}] * 5,
            param_ranges_json="[]",
            config=OptunaConfig(n_trials=5, min_fills_required=80),
        )
        assert result["status"] == "insufficient_data"
        assert result["pareto_front"] == []

    def test_run_multi_objective_no_adjustable_params(self):
        ranges = json.dumps([
            {"name": "fixed", "min": 1.0, "max": 2.0,
             "step": None, "agent_adjustable": False, "db_persisted": True},
        ])
        result = run_multi_objective_optimization(
            "ma_crossover",
            "BTCUSDT",
            "trending",
            fills=[{"pnl": 1.0}] * 100,
            param_ranges_json=ranges,
            config=OptunaConfig(n_trials=5, min_fills_required=10),
        )
        assert result["status"] == "no_adjustable_params"

    def test_run_multi_objective_returns_pareto_front(self, tmp_path):
        ranges = json.dumps([
            {"name": "adx_threshold", "min": 10.0, "max": 50.0,
             "step": 1.0, "agent_adjustable": True, "db_persisted": True},
            {"name": "cooldown_ms", "min": 60000.0, "max": 600000.0,
             "step": 60000.0, "agent_adjustable": True, "db_persisted": True},
        ])
        # Mixed pnls so all three objectives have variance
        fills = [{"pnl": (i % 5) - 2, "qty": 1.0} for i in range(120)]
        cfg = OptunaConfig(
            sqlite_path=str(tmp_path / "mo_studies.log"),
            n_trials=12,
            min_fills_required=50,
        )
        result = run_multi_objective_optimization(
            "ma_crossover",
            "BTCUSDT",
            "trending",
            fills=fills,
            param_ranges_json=ranges,
            config=cfg,
        )
        assert result["status"] == "success"
        assert result["n_trials"] >= 1
        assert len(result["pareto_front"]) >= 1
        # Each pareto entry has the three objectives
        first = result["pareto_front"][0]
        assert "sharpe" in first
        assert "max_drawdown" in first
        assert "turnover" in first
        assert "params" in first
