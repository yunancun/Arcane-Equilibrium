"""Tests for DB-backed GUI performance metrics.

DB 真實績效指標測試：驗證 Demo/Paper/Live 共用的 canonical metric contract。
"""

from __future__ import annotations

import os
import sys
from typing import Any


_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_CONTROL_API_DIR = os.path.dirname(_TEST_DIR)
if _CONTROL_API_DIR not in sys.path:
    sys.path.insert(0, _CONTROL_API_DIR)

from app.trading_true_metrics import build_performance_metrics  # noqa: E402


def _metric(metrics: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Return one metric by key for concise assertions.

    依 key 取出單個 metric，讓斷言保持精簡。
    """
    return next(m for m in metrics if m["key"] == key)


def test_build_performance_metrics_prefers_mlde_edge_quality() -> None:
    """MLDE edge rows drive edge quality when available.

    有 MLDE edge rows 時，平均淨邊際與勝率使用費後 bps 口徑。
    """
    metrics = build_performance_metrics(
        {
            "account_metrics": {
                "total_fills": 12,
                "net_pnl": -3.5,
                "gross_pnl": 1.2,
                "total_fees": 4.7,
                "funding_pnl": 0.0,
            },
            "account_metrics_today": {"net_pnl": 0.75},
            "account_metrics_24h": {"net_pnl": -1.25},
            "trade_metrics": {
                "metric_source": "trading.fills_close_realized",
                "metric_unit": "usdt",
                "total_round_trips": 4,
                "win_rate": 0.25,
                "win_loss_ratio": 0.8,
                "largest_win": 2.0,
                "largest_loss": -5.0,
                "avg_loss": 3.0,
            },
            "edge_metrics": {
                "metric_source": "learning.mlde_edge_training_rows",
                "metric_unit": "bps",
                "total_round_trips": 3,
                "avg_net_bps": -7.25,
                "win_rate": 0.3333,
                "win_loss_ratio": 1.4,
                "largest_win": 11.0,
                "largest_loss": -18.0,
                "avg_loss": 6.0,
            },
            "risk_metrics": {
                "metric_source": "trading.fills_close_realized",
                "max_drawdown_pct": 2.5,
                "sharpe_ratio": -0.6,
                "avg_holding_period_sec": 420.0,
            },
        },
        total_ai_cost=0.042,
    )

    assert _metric(metrics, "total_fills_7d")["value"] == 12
    assert _metric(metrics, "net_pnl_today")["value"] == 0.75
    assert _metric(metrics, "net_pnl_24h")["value"] == -1.25
    assert _metric(metrics, "avg_net_edge")["value"] == -7.25
    assert _metric(metrics, "avg_net_edge")["unit"] == "bps"
    assert _metric(metrics, "win_rate")["value"] == 0.3333
    assert _metric(metrics, "total_ai_cost")["value"] == 0.042
    assert _metric(metrics, "max_drawdown")["value"] == 2.5
    assert _metric(metrics, "avg_hold_time")["value"] == 420.0


def test_build_performance_metrics_uses_fallback_risk_when_db_risk_missing() -> None:
    """Fallback Rust metrics fill risk fields when DB risk is unavailable.

    DB risk 缺資料時，使用 Rust snapshot fallback 補回回撤、Sharpe 與持倉時間。
    """
    metrics = build_performance_metrics(
        {
            "account_metrics": {},
            "account_metrics_today": {},
            "account_metrics_24h": {},
            "trade_metrics": {
                "metric_source": "trading.fills_close_realized",
                "metric_unit": "usdt",
                "total_round_trips": 2,
                "avg_net_bps": 0.0,
                "win_rate": 0.5,
                "win_loss_ratio": 1.1,
                "largest_win": 4.0,
                "largest_loss": -2.0,
                "avg_loss": 2.0,
            },
            "edge_metrics": {"total_round_trips": 0},
            "risk_metrics": {},
        },
        fallback_metrics={
            "drawdown_metrics": {"max_drawdown_pct": 1.75},
            "sharpe_ratio": {"sharpe_ratio": 0.32},
            "holding_period_metrics": {"avg_holding_period_sec": 90},
            "pnl_summary": {"total_ai_cost": 0.5},
        },
    )

    assert _metric(metrics, "round_trips_7d")["value"] == 2
    assert _metric(metrics, "largest_win")["unit"] == "usdt"
    assert _metric(metrics, "max_drawdown")["value"] == 1.75
    assert _metric(metrics, "sharpe_ratio")["value"] == 0.32
    assert _metric(metrics, "avg_hold_time")["value"] == 90
    assert _metric(metrics, "total_ai_cost")["value"] == 0.5
