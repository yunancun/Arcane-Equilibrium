"""Tests for realized_edge_stats.compute_edge_stats engine_mode validator.
realized_edge_stats.compute_edge_stats 的 engine_mode 驗證器測試。

Covers the 2026-04-16 cutover where Live+LiveDemo endpoints write
engine_mode="live_demo" to trading.fills, which must be a valid input.
覆蓋 2026-04-16 切換：Live+LiveDemo 端點寫 engine_mode="live_demo"，
必須作為有效輸入被接受。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from program_code.ml_training import realized_edge_stats
from program_code.ml_training.realized_edge_stats import RoundTripRecord


def _make_empty_conn() -> MagicMock:
    """Return a mock connection whose cursor yields zero rows with minimal description."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.description = [("placeholder",)]
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def test_live_demo_mode_passes_validator():
    """engine_mode='live_demo' must not raise ValueError at validator step."""
    conn = _make_empty_conn()
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        result = realized_edge_stats.compute_edge_stats(
            days_back=1, min_samples=3, engine_mode="live_demo"
        )
    assert result == {}


def test_paper_mode_passes_validator():
    """Regression: engine_mode='paper' still accepted."""
    conn = _make_empty_conn()
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        result = realized_edge_stats.compute_edge_stats(
            days_back=1, min_samples=3, engine_mode="paper"
        )
    assert result == {}


def test_demo_mode_passes_validator():
    """Regression: engine_mode='demo' still accepted."""
    conn = _make_empty_conn()
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        result = realized_edge_stats.compute_edge_stats(
            days_back=1, min_samples=3, engine_mode="demo"
        )
    assert result == {}


def test_live_mode_passes_validator():
    """Regression: engine_mode='live' still accepted."""
    conn = _make_empty_conn()
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        result = realized_edge_stats.compute_edge_stats(
            days_back=1, min_samples=3, engine_mode="live"
        )
    assert result == {}


def test_invalid_mode_rejected():
    """Unknown mode must raise ValueError with helpful message listing allowed modes."""
    with pytest.raises(ValueError) as excinfo:
        realized_edge_stats.compute_edge_stats(
            days_back=1, min_samples=3, engine_mode="invalid_mode"
        )
    msg = str(excinfo.value)
    assert "invalid_mode" in msg
    assert "live_demo" in msg


def test_empty_string_mode_rejected():
    """Empty string must also be rejected."""
    with pytest.raises(ValueError):
        realized_edge_stats.compute_edge_stats(
            days_back=1, min_samples=3, engine_mode=""
        )


# ── EDGE-DIAG-2 (2026-04-28): min_observation_ts cutoff ──
# EDGE-DIAG-2（2026-04-28）：min_observation_ts 硬下限


def _capture_query_args(captured: dict) -> MagicMock:
    """Cursor mock that records the parameters psycopg2 was called with."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.description = [("placeholder",)]
    cur.fetchall.return_value = []

    def _exec(_sql, params):
        captured.update(params)
        return None

    cur.execute.side_effect = _exec
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def test_min_observation_ts_uses_later_of_rolling_and_cutoff():
    """When cutoff is more recent than rolling window, cutoff wins."""
    captured: dict = {}
    conn = _capture_query_args(captured)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=2)  # very recent
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        realized_edge_stats.compute_edge_stats(
            days_back=30, min_samples=3, engine_mode="demo",
            min_observation_ts=cutoff,
        )
    used = captured["since"]
    # Cutoff at -2h is more recent than rolling -30d → since must equal cutoff.
    assert used == cutoff, f"expected cutoff to dominate, got {used} (cutoff={cutoff})"


def test_min_observation_ts_yields_to_rolling_when_older():
    """When cutoff is older than rolling window, rolling window wins."""
    captured: dict = {}
    conn = _capture_query_args(captured)
    # Cutoff in the distant past must NOT loosen the rolling window.
    ancient_cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        realized_edge_stats.compute_edge_stats(
            days_back=7, min_samples=3, engine_mode="demo",
            min_observation_ts=ancient_cutoff,
        )
    used = captured["since"]
    expected_min_rolling = datetime.now(tz=timezone.utc) - timedelta(days=7, seconds=5)
    assert used >= expected_min_rolling, (
        f"ancient cutoff must not loosen rolling 7d window; got since={used}"
    )


def test_min_observation_ts_none_preserves_legacy_behavior():
    """No cutoff supplied → since == now - days_back (regression guard)."""
    captured: dict = {}
    conn = _capture_query_args(captured)
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        realized_edge_stats.compute_edge_stats(
            days_back=7, min_samples=3, engine_mode="demo",
            min_observation_ts=None,
        )
    used = captured["since"]
    expected_min_rolling = datetime.now(tz=timezone.utc) - timedelta(days=7, seconds=5)
    assert used >= expected_min_rolling


def test_min_observation_ts_naive_treated_as_utc():
    """Naive datetime cutoff must be normalized to UTC tz before comparison."""
    captured: dict = {}
    conn = _capture_query_args(captured)
    naive_cutoff = datetime.utcnow() - timedelta(hours=1)  # tz-naive on purpose
    with patch.object(realized_edge_stats, "_get_db_conn", return_value=conn):
        realized_edge_stats.compute_edge_stats(
            days_back=30, min_samples=3, engine_mode="demo",
            min_observation_ts=naive_cutoff,
        )
    used = captured["since"]
    assert used.tzinfo is not None, "since must be tz-aware after normalization"


def test_attach_funding_to_records_updates_net_bps_without_double_counting_splits():
    entry_ts = datetime(2026, 4, 28, 8, 0, tzinfo=timezone.utc)
    exit_ts = datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc)
    records = [
        RoundTripRecord(
            strategy_name="funding_arb",
            symbol="BTCUSDT",
            gross_pnl_bps=0.0,
            entry_fee_bps=1.0,
            exit_fee_bps=1.0,
            net_pnl_bps=-2.0,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            notional_usd=100.0,
            bps_denominator_usd=100.0,
            entry_context_id="ctx-1",
        ),
        RoundTripRecord(
            strategy_name="funding_arb",
            symbol="BTCUSDT",
            gross_pnl_bps=0.0,
            entry_fee_bps=1.0,
            exit_fee_bps=1.0,
            net_pnl_bps=-2.0,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            notional_usd=300.0,
            bps_denominator_usd=300.0,
            entry_context_id="ctx-1",
        ),
    ]

    realized_edge_stats._attach_funding_to_records(
        records,
        [
            {
                "ts": datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc),
                "symbol": "BTCUSDT",
                "strategy_name": "funding_arb",
                "amount": 4.0,
            }
        ],
    )

    assert sum(r.funding_pnl_usd for r in records) == 4.0
    assert records[0].funding_pnl_usd == 1.0
    assert records[1].funding_pnl_usd == 3.0
    assert records[0].net_pnl_bps == 98.0
    assert records[1].net_pnl_bps == 98.0


def test_attach_funding_to_records_excludes_split_closed_before_settlement():
    entry_ts = datetime(2026, 4, 28, 8, 0, tzinfo=timezone.utc)
    records = [
        RoundTripRecord(
            strategy_name="funding_arb",
            symbol="BTCUSDT",
            gross_pnl_bps=0.0,
            entry_fee_bps=0.0,
            exit_fee_bps=0.0,
            net_pnl_bps=0.0,
            entry_ts=entry_ts,
            exit_ts=datetime(2026, 4, 28, 8, 30, tzinfo=timezone.utc),
            notional_usd=100.0,
            bps_denominator_usd=100.0,
            entry_context_id="ctx-2",
        ),
        RoundTripRecord(
            strategy_name="funding_arb",
            symbol="BTCUSDT",
            gross_pnl_bps=0.0,
            entry_fee_bps=0.0,
            exit_fee_bps=0.0,
            net_pnl_bps=0.0,
            entry_ts=entry_ts,
            exit_ts=datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc),
            notional_usd=300.0,
            bps_denominator_usd=300.0,
            entry_context_id="ctx-2",
        ),
    ]

    realized_edge_stats._attach_funding_to_records(
        records,
        [
            {
                "ts": datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc),
                "symbol": "BTCUSDT",
                "strategy_name": "funding_arb",
                "amount": 3.0,
            }
        ],
    )

    assert records[0].funding_pnl_usd == 0.0
    assert records[1].funding_pnl_usd == 3.0
    assert records[1].net_pnl_bps == 100.0
