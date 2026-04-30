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


def test_attach_unmapped_below_min_notional_labels_orphan_frozen():
    """REST-only dust residues can be absent from paper_state after boot reaper.
    They should still render as orphan_frozen instead of a blank strategy cell."""
    positions = [{"symbol": "APEUSDT", "size": "0.1", "markPrice": "0.15347"}]
    client = _mock_rust_client_with_min({"APEUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["owner_strategy"] == "orphan_frozen"
    assert p["frozen_reason"] == "dust_below_min_notional"
    assert p["min_notional"] == 5.0
    assert abs(p["est_notional"] - 0.1 * 0.15347) < 1e-12


def test_attach_unmapped_above_min_notional_stays_unowned():
    positions = [{"symbol": "BTCUSDT", "size": "0.1", "markPrice": "50000.0"}]
    client = _mock_rust_client_with_min({"BTCUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
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


# ── _dust_status (unit) ──────────────────────────────────────────────────────


def test_dust_status_orphan_frozen_below_min():
    assert (
        strategy_ai_routes._dust_status("orphan_frozen", est_notional=0.2, min_notional=5.0)
        == "dust_below_min_notional"
    )


def test_dust_status_orphan_frozen_above_min_is_pending():
    # est >= min → retriage path will promote; snapshot still reads frozen.
    assert (
        strategy_ai_routes._dust_status("orphan_frozen", est_notional=10.0, min_notional=5.0)
        == "frozen_pending"
    )


def test_dust_status_orphan_frozen_equal_to_min_is_pending():
    # Boundary matches Rust event_consumer/dispatch.rs strict `<` — equal is NOT dust.
    assert (
        strategy_ai_routes._dust_status("orphan_frozen", est_notional=5.0, min_notional=5.0)
        == "frozen_pending"
    )


def test_dust_status_orphan_frozen_missing_notional_is_pending():
    assert (
        strategy_ai_routes._dust_status("orphan_frozen", est_notional=None, min_notional=5.0)
        == "frozen_pending"
    )
    assert (
        strategy_ai_routes._dust_status("orphan_frozen", est_notional=0.2, min_notional=None)
        == "frozen_pending"
    )
    assert (
        strategy_ai_routes._dust_status("orphan_frozen", est_notional=None, min_notional=None)
        == "frozen_pending"
    )


def test_dust_status_bybit_sync():
    # bybit_sync always maps to pending_triage regardless of notional values.
    assert (
        strategy_ai_routes._dust_status("bybit_sync", est_notional=0.1, min_notional=5.0)
        == "pending_triage"
    )
    assert (
        strategy_ai_routes._dust_status("bybit_sync", est_notional=None, min_notional=None)
        == "pending_triage"
    )


def test_dust_status_orphan_adopted():
    assert (
        strategy_ai_routes._dust_status("orphan_adopted", est_notional=100.0, min_notional=5.0)
        == "pending_edge"
    )


def test_dust_status_real_strategy_returns_empty():
    assert (
        strategy_ai_routes._dust_status("ma_crossover", est_notional=100.0, min_notional=5.0)
        == ""
    )
    assert strategy_ai_routes._dust_status("grid_trading", None, None) == ""


# ── _attach_owner_strategy dust enrichment (synthetic owners) ────────────────


def _mock_rust_client_with_min(min_notional_by_sym: dict):
    """Helper: build a mock Rust BybitClient whose get_instrument returns the
    given min_notional (or raises / returns None per key contents).
    """
    client = MagicMock()

    def _get_instrument(sym):
        entry = min_notional_by_sym.get(sym)
        if isinstance(entry, Exception):
            raise entry
        if entry is None:
            return None
        if entry == "bad_shape":
            # Simulate unexpected return type — helper must tolerate.
            return "not a dict"
        return {"symbol": sym, "min_notional": entry}

    client.get_instrument.side_effect = _get_instrument
    return client


def test_attach_orphan_frozen_dust_enriched():
    """orphan_frozen with computable notional below min → dust_below_min_notional
    + min_notional + est_notional attached."""
    positions = [{"symbol": "PNUTUSDT", "size": "3.0", "markPrice": "0.06644"}]
    client = _mock_rust_client_with_min({"PNUTUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"PNUTUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["owner_strategy"] == "orphan_frozen"
    assert p["frozen_reason"] == "dust_below_min_notional"
    assert p["min_notional"] == 5.0
    assert abs(p["est_notional"] - 3.0 * 0.06644) < 1e-9


def test_attach_orphan_frozen_instrument_lookup_fails_frozen_pending():
    """orphan_frozen + instrument lookup exception → frozen_pending, min_notional=None."""
    positions = [{"symbol": "FOOUSDT", "size": "1.0", "markPrice": "10.0"}]
    client = _mock_rust_client_with_min({"FOOUSDT": RuntimeError("rest down")})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"FOOUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["owner_strategy"] == "orphan_frozen"
    assert p["frozen_reason"] == "frozen_pending"
    assert p["min_notional"] is None
    # est_notional is still computable from markPrice × size.
    assert abs(p["est_notional"] - 10.0) < 1e-9


def test_attach_orphan_frozen_instrument_returns_none_frozen_pending():
    """orphan_frozen + instrument cache miss (returns None) → frozen_pending."""
    positions = [{"symbol": "NEWUSDT", "size": "1.0", "markPrice": "2.0"}]
    client = _mock_rust_client_with_min({"NEWUSDT": None})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"NEWUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["frozen_reason"] == "frozen_pending"
    assert p["min_notional"] is None


def test_attach_orphan_frozen_no_rust_client():
    """When _get_rust_client returns None, min_notional stays None (frozen_pending)."""
    positions = [{"symbol": "XUSDT", "size": "1.0", "markPrice": "1.0"}]
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"XUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=None):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["owner_strategy"] == "orphan_frozen"
    assert p["frozen_reason"] == "frozen_pending"
    assert p["min_notional"] is None


def test_attach_bybit_sync_pending_triage_regardless_of_notional():
    """bybit_sync always gets pending_triage regardless of computed notional."""
    positions = [
        {"symbol": "BTCUSDT", "size": "0.001", "markPrice": "100000.0"},
    ]
    client = _mock_rust_client_with_min({"BTCUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"BTCUSDT": "bybit_sync"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["owner_strategy"] == "bybit_sync"
    assert p["frozen_reason"] == "pending_triage"
    assert p["min_notional"] == 5.0
    assert abs(p["est_notional"] - 100.0) < 1e-9


def test_attach_orphan_adopted_pending_edge():
    """orphan_adopted → pending_edge with notional attached."""
    positions = [{"symbol": "ETHUSDT", "size": "0.5", "markPrice": "2000.0"}]
    client = _mock_rust_client_with_min({"ETHUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"ETHUSDT": "orphan_adopted"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["owner_strategy"] == "orphan_adopted"
    assert p["frozen_reason"] == "pending_edge"
    assert p["min_notional"] == 5.0
    assert abs(p["est_notional"] - 1000.0) < 1e-9


def test_attach_real_strategy_no_dust_fields():
    """Real strategy name (ma_crossover) → owner_strategy attached BUT
    no frozen_reason / min_notional / est_notional keys added (keeps payload lean)."""
    positions = [{"symbol": "BTCUSDT", "size": "0.1", "markPrice": "50000.0"}]
    client = _mock_rust_client_with_min({"BTCUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"BTCUSDT": "ma_crossover"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["owner_strategy"] == "ma_crossover"
    assert "frozen_reason" not in p
    assert "min_notional" not in p
    assert "est_notional" not in p
    # Confirms we did NOT call get_instrument for real strategies.
    client.get_instrument.assert_not_called()


def test_attach_real_strategy_passed_through_unchanged_when_mapped():
    """Symbols mapped to real strategy names pass through with only owner_strategy
    added — preserves existing behaviour for the common (lean) path."""
    positions = [
        {"symbol": "BTCUSDT", "size": "0.1"},
        {"symbol": "ETHUSDT", "size": "0.01"},
    ]
    client = _mock_rust_client_with_min({})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"BTCUSDT": "grid_trading", "ETHUSDT": "ma_crossover"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    for p in result:
        assert p["owner_strategy"] in {"grid_trading", "ma_crossover"}
        assert "frozen_reason" not in p
        assert "min_notional" not in p
        assert "est_notional" not in p


def test_attach_orphan_frozen_falls_back_to_avg_price():
    """When markPrice absent, fall back to avgPrice for est_notional."""
    positions = [{"symbol": "DOGEUSDT", "size": "100", "avgPrice": "0.10"}]
    client = _mock_rust_client_with_min({"DOGEUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"DOGEUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    # 100 * 0.10 = 10.0 ≥ 5.0 → frozen_pending (above min, retriage should promote)
    assert abs(p["est_notional"] - 10.0) < 1e-9
    assert p["frozen_reason"] == "frozen_pending"


def test_attach_orphan_frozen_no_usable_price_est_none():
    """No markPrice / avgPrice / entry_price → est_notional stays None → frozen_pending."""
    positions = [{"symbol": "NOPXUSDT", "size": "1.0"}]
    client = _mock_rust_client_with_min({"NOPXUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"NOPXUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["est_notional"] is None
    assert p["min_notional"] == 5.0
    # est unknown → frozen_pending (not dust_below_min_notional).
    assert p["frozen_reason"] == "frozen_pending"


def test_attach_orphan_frozen_instrument_returns_bad_shape():
    """_fetch_min_notional tolerates non-dict return from get_instrument (defensive)."""
    positions = [{"symbol": "WEIRDUSDT", "size": "1.0", "markPrice": "1.0"}]
    client = _mock_rust_client_with_min({"WEIRDUSDT": "bad_shape"})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"WEIRDUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert p["min_notional"] is None
    assert p["frozen_reason"] == "frozen_pending"


def test_attach_min_notional_cached_across_same_symbol():
    """Same symbol appearing twice (hedge mode long + short) → get_instrument called once."""
    positions = [
        {"symbol": "BTCUSDT", "size": "0.1", "markPrice": "50000.0", "side": "Buy"},
        {"symbol": "BTCUSDT", "size": "0.05", "markPrice": "50000.0", "side": "Sell"},
    ]
    client = _mock_rust_client_with_min({"BTCUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"BTCUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    # Both rows share the same symbol → single lookup.
    assert client.get_instrument.call_count == 1


def test_attach_qty_field_fallback():
    """Position using `qty` key (not `size`) still produces est_notional."""
    positions = [{"symbol": "ZUSDT", "qty": "2.0", "markPrice": "3.0"}]
    client = _mock_rust_client_with_min({"ZUSDT": 5.0})
    with patch(
        "app.strategy_ai_routes._engine_owner_strategy_map",
        return_value={"ZUSDT": "orphan_frozen"},
    ), patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        result = strategy_ai_routes._attach_owner_strategy(positions, engine="demo")
    p = result[0]
    assert abs(p["est_notional"] - 6.0) < 1e-9
    # 6.0 >= 5.0 → frozen_pending
    assert p["frozen_reason"] == "frozen_pending"


def test_fetch_min_notional_falls_back_to_one_symbol_lookup():
    """When the instrument cache is empty, fetch just the requested symbol."""
    client = MagicMock()
    client.get_instrument.return_value = None
    client._get.return_value = {
        "result": {
            "list": [
                {
                    "symbol": "APEUSDT",
                    "lotSizeFilter": {"minNotionalValue": "5"},
                }
            ]
        }
    }
    with patch("app.strategy_ai_routes._get_rust_client", return_value=client):
        assert strategy_ai_routes._fetch_min_notional("APEUSDT") == 5.0
    client._get.assert_called_once_with(
        "/v5/market/instruments-info",
        {"category": "linear", "symbol": "APEUSDT"},
    )
