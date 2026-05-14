from __future__ import annotations

from pathlib import Path

import pytest

from app.trading_true_metrics import build_performance_metrics


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"

EXPECTED_KEYS = [
    "total_fills_7d",
    "round_trips_7d",
    "attributed_trades_7d",
    "net_pnl_24h",
    "net_pnl_7d",
    "gross_pnl_7d",
    "total_fees_7d",
    "funding_7d",
    "total_ai_cost",
    "avg_net_edge",
    "win_rate",
    "win_loss_ratio",
    "largest_win",
    "largest_loss",
    "avg_loss",
    "max_drawdown",
    "sharpe_ratio",
    "avg_hold_time",
]


def test_static_gui_uses_non_empty_performance_metric_payload_fallback() -> None:
    common = (STATIC_DIR / "common.js").read_text(encoding="utf-8")

    assert "function ocPerformanceMetricsFromPayload(payload)" in common
    assert "if (top && top.length > 0) return top" in common
    assert "if (dbMetrics && dbMetrics.length > 0) return dbMetrics" in common


@pytest.mark.parametrize("filename", ["console.html", "tab-demo.html", "tab-live.html", "tab-paper.html"])
def test_static_gui_performance_metric_callers_use_canonical_payload_helper(filename: str) -> None:
    source = (STATIC_DIR / filename).read_text(encoding="utf-8")

    assert "ocPerformanceMetricsFromPayload(" in source
    assert "performance_metrics) ||" not in source
    assert "performance_metrics ||" not in source


def _db_metrics(engine_modes: list[str]) -> dict:
    return {
        "available": True,
        "source": "pg_trading_fills",
        "window_days": 7,
        "engine_modes": engine_modes,
        "edge_engine_modes": engine_modes,
        "account_metrics": {
            "total_fills": 22,
            "gross_pnl": 12.5,
            "total_fees": 1.25,
            "funding_pnl": -0.1,
            "net_pnl": 11.15,
        },
        "account_metrics_today": {
            "total_fills": 2,
            "gross_pnl": 1.8,
            "total_fees": 0.2,
            "funding_pnl": 0.1,
            "net_pnl": 1.7,
        },
        "account_metrics_24h": {
            "total_fills": 5,
            "gross_pnl": 3.0,
            "total_fees": 0.25,
            "funding_pnl": 0.05,
            "net_pnl": 2.8,
        },
        "trade_metrics": {
            "metric_source": "trading.fills_close_realized",
            "metric_unit": "usdt",
            "total_round_trips": 4,
            "win_rate": 0.5,
            "win_loss_ratio": 1.25,
            "largest_win": 4.0,
            "largest_loss": -3.0,
            "avg_loss": 1.5,
        },
        "edge_metrics": {
            "metric_source": "learning.mlde_edge_training_rows",
            "metric_unit": "bps",
            "total_round_trips": 3,
            "win_rate": 0.667,
            "win_loss_ratio": 1.5,
            "largest_win": 18.0,
            "largest_loss": -9.0,
            "avg_loss": 4.5,
            "avg_net_bps": 2.25,
        },
        "risk_metrics": {
            "metric_source": "trading.fills_close_realized",
            "max_drawdown_pct": 1.75,
            "sharpe_ratio": 0.62,
            "avg_holding_period_sec": 180.0,
        },
    }


def test_build_performance_metrics_has_canonical_order_tooltips_and_no_today_duplicate() -> None:
    metrics = build_performance_metrics(_db_metrics(["demo"]), total_ai_cost=0.42)

    assert [m["key"] for m in metrics] == EXPECTED_KEYS
    assert all(m["label"] for m in metrics)
    assert all(m["tooltip_zh"] for m in metrics)
    assert all("source" in m for m in metrics)

    by_key = {m["key"]: m for m in metrics}
    assert "net_pnl_today" not in by_key
    assert by_key["net_pnl_24h"]["value"] == 2.8
    assert by_key["net_pnl_24h"]["unit"] == "money"
    assert by_key["net_pnl_24h"]["polarity"] == "pnl"
    assert by_key["total_ai_cost"]["value"] == 0.42
    assert by_key["avg_net_edge"]["value"] == 2.25
    assert by_key["largest_win"]["unit"] == "bps"


def test_paper_metrics_route_reads_paper_db_only(monkeypatch) -> None:
    from app import paper_trading_routes as routes

    captured: list[tuple[list[str], list[str] | None, int]] = []

    class Reader:
        def is_engine_available(self, engine: str) -> bool:
            assert engine == "paper"
            return False

    def fake_fetch(modes, *, edge_engine_modes=None, window_days=7):
        captured.append((list(modes), list(edge_engine_modes or []), window_days))
        return _db_metrics(list(modes))

    monkeypatch.setattr(routes, "get_rust_reader", lambda: Reader())
    monkeypatch.setattr(routes, "fetch_db_true_metrics", fake_fetch)
    monkeypatch.setattr(routes, "_fetch_total_ai_cost_30d_safe", lambda: None)

    out = routes.get_metrics(actor=None)

    assert captured == [(["paper"], ["paper"], 7)]
    assert out["data"]["db_true_metrics"]["engine_modes"] == ["paper"]
    assert out["data"]["db_true_metrics"]["account_metrics_today"]["net_pnl"] == 1.7
    assert out["data"]["performance_metrics"][3]["key"] == "net_pnl_24h"


@pytest.mark.asyncio
async def test_demo_metrics_route_reads_demo_db_only(monkeypatch) -> None:
    from app import paper_trading_routes
    from app import strategy_ai_routes as routes
    from app import trading_true_metrics

    captured: list[tuple[list[str], list[str] | None, int]] = []

    class Reader:
        def is_engine_available(self, engine: str) -> bool:
            assert engine == "demo"
            return False

    def fake_fetch(modes, *, edge_engine_modes=None, window_days=7):
        captured.append((list(modes), list(edge_engine_modes or []), window_days))
        return _db_metrics(list(modes))

    monkeypatch.setattr(paper_trading_routes, "get_rust_reader", lambda: Reader())
    monkeypatch.setattr(trading_true_metrics, "fetch_db_true_metrics", fake_fetch)
    monkeypatch.setattr(routes, "_fetch_total_ai_cost_30d_safe", lambda: None)

    out = await routes.get_demo_metrics(actor=None)

    assert captured == [(["demo"], ["demo"], 7)]
    assert out["data"]["db_true_metrics"]["engine_modes"] == ["demo"]
    assert out["data"]["db_true_metrics"]["account_metrics_today"]["net_pnl"] == 1.7
    assert out["data"]["performance_metrics"][3]["key"] == "net_pnl_24h"


@pytest.mark.parametrize(
    ("engine_kind", "actual_endpoint", "expected_modes"),
    [
        ("live", "live_demo", ["live_demo"]),
        ("live", "mainnet", ["live"]),
        ("live", "unconfigured", ["live"]),
        ("demo", "live_demo", ["live_demo"]),
        ("paper", "mainnet", ["live"]),
    ],
)
def test_live_metrics_route_uses_endpoint_specific_db_modes(
    monkeypatch,
    engine_kind: str,
    actual_endpoint: str,
    expected_modes: list[str],
) -> None:
    from app import live_session_account_routes as routes
    from app import live_session_routes as core
    from app import trading_true_metrics

    captured: list[tuple[list[str], list[str] | None, int]] = []

    class Reader:
        def is_available(self) -> bool:
            return False

    def fake_fetch(modes, *, edge_engine_modes=None, window_days=7):
        captured.append((list(modes), list(edge_engine_modes or []), window_days))
        return _db_metrics(list(modes))

    monkeypatch.setattr(routes, "_phantom_view_guard", lambda: None)
    monkeypatch.setattr(routes, "get_rust_reader", lambda: Reader())
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: engine_kind)
    monkeypatch.setattr(core, "_resolve_live_endpoint_label", lambda: actual_endpoint)
    monkeypatch.setattr(trading_true_metrics, "fetch_db_true_metrics", fake_fetch)
    monkeypatch.setattr(routes, "_fetch_total_ai_cost_30d_safe", lambda: None)

    out = routes.get_live_metrics(actor=None)

    assert captured == [(expected_modes, expected_modes, 7)]
    assert out["data"]["db_true_metrics"]["engine_modes"] == expected_modes
    assert out["data"]["db_true_metrics"]["account_metrics_today"]["net_pnl"] == 1.7
    assert out["data"]["performance_metrics"][3]["key"] == "net_pnl_24h"
