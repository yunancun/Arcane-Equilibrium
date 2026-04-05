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
    build_search_space,
    compute_ev_net,
    create_study,
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
        cfg = OptunaConfig()
        assert cfg.sqlite_path == "/tmp/openclaw/optuna_studies.log"
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
