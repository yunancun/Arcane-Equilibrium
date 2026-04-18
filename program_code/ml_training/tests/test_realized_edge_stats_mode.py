"""Tests for realized_edge_stats.compute_edge_stats engine_mode validator.
realized_edge_stats.compute_edge_stats 的 engine_mode 驗證器測試。

Covers the 2026-04-16 cutover where Live+LiveDemo endpoints write
engine_mode="live_demo" to trading.fills, which must be a valid input.
覆蓋 2026-04-16 切換：Live+LiveDemo 端點寫 engine_mode="live_demo"，
必須作為有效輸入被接受。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from program_code.ml_training import realized_edge_stats


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
