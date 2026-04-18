"""Unit tests for owner_strategy enrichment helpers in strategy_ai_routes.

Tests the thread that injects authoritative Rust `paper_state.PaperPosition.owner_strategy`
into Bybit REST position dicts so the GUI shows the correct strategy attribution for
non-grid / low-turnover strategies (see 2026-04-18 fix — root cause: fills-derived
map missed symbols whose latest fill fell outside the LIMIT 50 window).

測試將 Rust paper_state 的 owner_strategy 注入 Bybit REST 倉位 dict 的輔助函數。
（2026-04-18 修復；根因：fills 反推映射對低週轉策略失效）
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app import strategy_ai_routes


# ── _engine_owner_strategy_map ───────────────────────────────────────────────


def test_owner_map_from_list_snapshot():
    reader = MagicMock()
    reader.is_engine_available.return_value = True
    reader.get_paper_state.return_value = {
        "positions": [
            {"symbol": "BTCUSDT", "owner_strategy": "grid_trading", "qty": 0.1},
            {"symbol": "ETHUSDT", "owner_strategy": "ma_crossover", "qty": 0.01},
            {"symbol": "ADAUSDT", "owner_strategy": "orphan_frozen", "qty": 100.0},
        ]
    }
    with patch("app.paper_trading_routes.get_rust_reader", return_value=reader):
        result = strategy_ai_routes._engine_owner_strategy_map("demo")
    assert result == {
        "BTCUSDT": "grid_trading",
        "ETHUSDT": "ma_crossover",
        "ADAUSDT": "orphan_frozen",
    }
    reader.is_engine_available.assert_called_once_with("demo")


def test_owner_map_gated_on_staleness():
    """When snapshot is stale (is_engine_available=False), return {} so caller falls
    back to fills-derived map. Guards against attaching obsolete owner after handoff."""
    reader = MagicMock()
    reader.is_engine_available.return_value = False
    reader.get_paper_state.return_value = {
        "positions": [{"symbol": "BTCUSDT", "owner_strategy": "grid_trading"}]
    }
    with patch("app.paper_trading_routes.get_rust_reader", return_value=reader):
        result = strategy_ai_routes._engine_owner_strategy_map("live")
    assert result == {}
    reader.get_paper_state.assert_not_called()


def test_owner_map_empty_owner_skipped():
    """Empty-string owner_strategy (pre-Phase-2A snapshots) must not overwrite fills fallback."""
    reader = MagicMock()
    reader.is_engine_available.return_value = True
    reader.get_paper_state.return_value = {
        "positions": [
            {"symbol": "BTCUSDT", "owner_strategy": ""},
            {"symbol": "ETHUSDT", "owner_strategy": "ma_crossover"},
            {"symbol": "", "owner_strategy": "stray"},
        ]
    }
    with patch("app.paper_trading_routes.get_rust_reader", return_value=reader):
        result = strategy_ai_routes._engine_owner_strategy_map("demo")
    assert result == {"ETHUSDT": "ma_crossover"}


def test_owner_map_missing_snapshot_returns_empty():
    reader = MagicMock()
    reader.is_engine_available.return_value = True
    reader.get_paper_state.return_value = None
    with patch("app.paper_trading_routes.get_rust_reader", return_value=reader):
        result = strategy_ai_routes._engine_owner_strategy_map("demo")
    assert result == {}


def test_owner_map_reader_exception_swallowed():
    """Any exception in the reader path degrades gracefully to {} (caller falls back)."""
    with patch(
        "app.paper_trading_routes.get_rust_reader",
        side_effect=RuntimeError("broken"),
    ):
        result = strategy_ai_routes._engine_owner_strategy_map("demo")
    assert result == {}


def test_owner_map_dict_shape_supported():
    """Defensive: snapshot may evolve to dict shape; helper supports both."""
    reader = MagicMock()
    reader.is_engine_available.return_value = True
    reader.get_paper_state.return_value = {
        "positions": {
            "BTCUSDT": {"owner_strategy": "grid_trading"},
            "ETHUSDT": {"owner_strategy": "ma_crossover"},
        }
    }
    with patch("app.paper_trading_routes.get_rust_reader", return_value=reader):
        result = strategy_ai_routes._engine_owner_strategy_map("demo")
    assert result == {"BTCUSDT": "grid_trading", "ETHUSDT": "ma_crossover"}


# ── _attach_owner_strategy ───────────────────────────────────────────────────


def test_attach_enriches_matching_symbols():
    positions = [
        {"symbol": "BTCUSDT", "size": "0.1"},
        {"symbol": "ETHUSDT", "size": "0.01"},
    ]
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"BTCUSDT": "grid_trading", "ETHUSDT": "ma_crossover"},
    ):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    assert result[0]["owner_strategy"] == "grid_trading"
    assert result[1]["owner_strategy"] == "ma_crossover"


def test_attach_leaves_unmapped_symbols_untouched():
    """Symbols not in paper_state (e.g., orphan Bybit positions) must keep no owner_strategy
    key — GUI then falls through to the fills-derived map, which is the pre-fix behaviour."""
    positions = [{"symbol": "BTCUSDT", "size": "0.1"}]
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"ETHUSDT": "ma_crossover"},
    ):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    assert "owner_strategy" not in result[0]


def test_attach_empty_map_is_noop():
    positions = [{"symbol": "BTCUSDT", "size": "0.1"}]
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={},
    ):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    assert "owner_strategy" not in result[0]


def test_attach_handles_empty_and_non_list():
    assert strategy_ai_routes._attach_owner_strategy([], engine="demo") == []
    assert strategy_ai_routes._attach_owner_strategy(None, engine="demo") is None  # type: ignore[arg-type]


def test_attach_skips_non_dict_elements():
    positions = [{"symbol": "BTCUSDT"}, "not a dict", 42]
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"BTCUSDT": "grid_trading"},
    ):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")  # type: ignore[arg-type]
    assert result[0]["owner_strategy"] == "grid_trading"
    assert result[1] == "not a dict"
    assert result[2] == 42
