"""closed_pnl_pagination 純邏輯單元測試（P2b 抽取後模塊匹配測試）。

涵蓋：游標 base64/JSON 編解碼往返與版本守衛、7 天視窗邊界推導、
視窗狀態機推進（initial / previous / with_cursor）、跨視窗 Bybit 分頁抓取、
Bybit 行 → snake_case 正規化、orderLinkId 策略推斷（注入 engine_owner_lookup）、
_safe_float NaN/字串守衛。route 層整合測試見 test_bybit_closed_pnl_route.py。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import closed_pnl_pagination as cp


# ── _safe_float ──────────────────────────────────────────────────────────────


def test_safe_float_parses_stringified_number():
    assert cp._safe_float("1.5") == 1.5
    assert cp._safe_float(2) == 2.0


def test_safe_float_none_and_garbage_return_none():
    assert cp._safe_float(None) is None
    assert cp._safe_float("abc") is None
    assert cp._safe_float("") is None


def test_safe_float_nan_returns_none():
    assert cp._safe_float(float("nan")) is None


# ── 游標編解碼 ─────────────────────────────────────────────────────────────────


def test_cursor_encode_decode_roundtrip():
    payload = {"source": "pg", "offset": 100, "symbol": "OPUSDT"}
    token = cp._closed_pnl_encode_cursor(payload)
    decoded = cp._closed_pnl_decode_cursor(token)
    assert decoded["source"] == "pg"
    assert decoded["offset"] == 100
    assert decoded["symbol"] == "OPUSDT"
    # 編碼器強制注入版本號
    assert decoded["v"] == cp._CLOSED_PNL_CURSOR_VERSION


def test_cursor_decode_empty_returns_empty_dict():
    assert cp._closed_pnl_decode_cursor(None) == {}
    assert cp._closed_pnl_decode_cursor("") == {}


def test_cursor_decode_malformed_raises_400():
    with pytest.raises(HTTPException) as exc:
        cp._closed_pnl_decode_cursor("@@@not-base64@@@")
    assert exc.value.status_code == 400


def test_cursor_decode_version_mismatch_raises_400():
    bad = cp._closed_pnl_encode_cursor({"source": "pg"})
    # 篡改 1 byte 破壞版本/結構
    import base64
    import json

    raw = json.loads(base64.urlsafe_b64decode(bad + "===").decode())
    raw["v"] = 999
    import json as _j

    forged = base64.urlsafe_b64encode(
        _j.dumps(raw, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    with pytest.raises(HTTPException) as exc:
        cp._closed_pnl_decode_cursor(forged)
    assert exc.value.status_code == 400


# ── 視窗邊界 ───────────────────────────────────────────────────────────────────


def test_history_bounds_defaults_to_lookback_days():
    start_ms, end_ms = cp._closed_pnl_history_bounds(
        start_time=None, end_time=1_000_000_000_000, lookback_days=7
    )
    assert end_ms == 1_000_000_000_000
    assert end_ms - start_ms == 7 * cp._CLOSED_PNL_DAY_MS


def test_history_bounds_clamps_excessive_lookback():
    start_ms, end_ms = cp._closed_pnl_history_bounds(
        start_time=None, end_time=2_000_000_000_000, lookback_days=99999
    )
    # safe_days 上限為 _CLOSED_PNL_ALL_HISTORY_DAYS
    assert end_ms - start_ms == cp._CLOSED_PNL_ALL_HISTORY_DAYS * cp._CLOSED_PNL_DAY_MS


def test_history_bounds_end_before_start_raises_400():
    with pytest.raises(HTTPException) as exc:
        cp._closed_pnl_history_bounds(start_time=2000, end_time=1000, lookback_days=1)
    assert exc.value.status_code == 400


# ── 視窗狀態機 ─────────────────────────────────────────────────────────────────


def test_initial_state_caps_window_to_max_window():
    start_ms = 0
    end_ms = 30 * cp._CLOSED_PNL_DAY_MS
    state = cp._closed_pnl_initial_bybit_state(start_ms=start_ms, end_ms=end_ms, symbol="X")
    assert state["window_end_ms"] == end_ms
    assert state["window_start_ms"] == end_ms - cp._CLOSED_PNL_MAX_WINDOW_MS
    assert state["symbol"] == "X"


def test_previous_window_steps_back_one_ms():
    end_ms = 30 * cp._CLOSED_PNL_DAY_MS
    state = cp._closed_pnl_initial_bybit_state(start_ms=0, end_ms=end_ms, symbol=None)
    prev = cp._closed_pnl_previous_window_state(state)
    assert prev is not None
    assert prev["window_end_ms"] == state["window_start_ms"] - 1


def test_previous_window_returns_none_at_range_floor():
    # window 已覆蓋到 start_ms → 無上一視窗
    state = cp._closed_pnl_initial_bybit_state(start_ms=0, end_ms=cp._CLOSED_PNL_DAY_MS, symbol=None)
    assert cp._closed_pnl_previous_window_state(state) is None


def test_state_with_cursor_falls_back_to_initial_on_non_bybit_source():
    state = cp._closed_pnl_bybit_state_with_cursor(
        cursor=None, start_ms=0, end_ms=100, symbol="Y"
    )
    assert state["source"] == "bybit"
    assert state["symbol"] == "Y"


# ── 跨視窗 Bybit 分頁抓取 ──────────────────────────────────────────────────────


class _PagedRC:
    """假 BybitClient：依 cursor 回傳分頁，記錄每次呼叫。"""

    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get_closed_pnl(self, category, *, symbol, start_time, end_time, limit, cursor):
        self.calls.append({"cursor": cursor, "limit": limit})
        rows, nxt = self._pages.get(cursor or "", ([], None))
        return {"list": rows, "nextPageCursor": nxt}


def test_fetch_history_page_follows_cursor_chain():
    pages = {
        "": ([{"orderId": f"A{i}"} for i in range(3)], "C1"),
        "C1": ([{"orderId": f"B{i}"} for i in range(3)], None),
    }
    rc = _PagedRC(pages)
    rows, next_cursor = cp._fetch_closed_pnl_bybit_history_page(
        rc, limit=6, cursor=None, symbol="OPUSDT", start_ms=0, end_ms=cp._CLOSED_PNL_DAY_MS
    )
    assert [r["orderId"] for r in rows] == ["A0", "A1", "A2", "B0", "B1", "B2"]
    # 第二頁無 nextPageCursor 且回到範圍底 → next_cursor None
    assert next_cursor is None


def test_fetch_history_page_stops_on_repeated_cursor():
    # nextPageCursor 自我循環 → 必須停止，不可無限迴圈
    pages = {"": ([{"orderId": "A0"}], "LOOP"), "LOOP": ([{"orderId": "A1"}], "LOOP")}
    rc = _PagedRC(pages)
    rows, _ = cp._fetch_closed_pnl_bybit_history_page(
        rc, limit=50, cursor=None, symbol=None, start_ms=0, end_ms=cp._CLOSED_PNL_DAY_MS
    )
    # 抓到 A0、A1 後偵測重複 cursor 停止
    assert [r["orderId"] for r in rows] == ["A0", "A1"]


# ── 行正規化 ───────────────────────────────────────────────────────────────────


def test_snake_row_exposes_aliases_and_preserves_camel():
    row = {
        "symbol": "OPUSDT",
        "side": "Buy",
        "qty": "10",
        "avgEntryPrice": "1.5",
        "avgExitPrice": "1.6",
        "closedPnl": "1.0",
        "closeFee": "0.01",
        "closedSize": "10",
        "fillCount": "2",
        "updatedTime": "1700000000000",
        "orderId": "OID1",
    }
    out = cp._closed_pnl_snake_row(row)
    assert out["closed_pnl"] == 1.0
    assert out["bybit_closed_pnl"] == 1.0
    assert out["avg_entry_price"] == 1.5
    assert out["fill_count"] == 2
    assert out["order_id"] == "OID1"
    # 原始 camelCase 鍵保留
    assert out["closedPnl"] == "1.0"


def test_snake_row_handles_missing_fill_count():
    out = cp._closed_pnl_snake_row({"symbol": "X"})
    assert out["fill_count"] == 0
    assert out["closed_pnl"] == 0.0


# ── orderLinkId 策略推斷（注入 engine_owner_lookup）──────────────────────────────


def test_strategy_from_link_external_when_no_match():
    name, source = cp._strategy_from_order_link_id(
        "external-link", symbol="OPUSDT", engine_owner_lookup=lambda e: {}
    )
    assert (name, source) == ("external_manual", "bybit_unknown")


def test_strategy_from_link_uses_owner_map_for_demo_prefix():
    name, source = cp._strategy_from_order_link_id(
        "oc_dm_1", symbol="DOGEUSDT", engine_owner_lookup=lambda e: {"DOGEUSDT": "grid_trading"}
    )
    assert (name, source) == ("grid_trading", "pg_link_id")


def test_strategy_from_link_live_demo_prefix_routes_to_live_demo_engine():
    seen = {}

    def lookup(engine):
        seen["engine"] = engine
        return {"ETHUSDT": "funding_arb"} if engine == "live_demo" else {}

    name, source = cp._strategy_from_order_link_id(
        "oc_ld_1", symbol="ETHUSDT", engine_owner_lookup=lookup
    )
    assert seen["engine"] == "live_demo"
    assert (name, source) == ("funding_arb", "pg_link_id")


def test_strategy_from_link_openclaw_without_owner_is_unknown_pending():
    name, source = cp._strategy_from_order_link_id(
        "oc_dm_9", symbol="DOGEUSDT", engine_owner_lookup=lambda e: {}
    )
    assert (name, source) == ("unknown_pending", "pg_missing_unknown_external")


# ── P2 #6-T2：對齊 Rust 真實前綴 grammar（lv + 全 close 前綴）─────────────────────
# Rust 鑄造點（已 grep 核對）：
#   開倉  oc_{em}_...            （step_4_5_dispatch.rs:662）
#   風控平 oc_risk_{em}_...      （commands.rs:931+988）
#   IPC 平 oc_ipc_close_{em}_... （commands.rs:1350/1547）
#   maker fb oc_close_mf_fb_{em}_...（commands.rs:1112）
# em ∈ {dm=demo, ld=live_demo, lv=live}。


def test_strategy_from_link_lv_routes_to_live_engine():
    """lv（live mainnet）必須映射為 engine='live'，不可 fall-through 誤判成 demo。"""
    seen = {}

    def lookup(engine):
        seen["engine"] = engine
        return {"BTCUSDT": "ma_crossover"} if engine == "live" else {}

    name, source = cp._strategy_from_order_link_id(
        "oc_lv_1", symbol="BTCUSDT", engine_owner_lookup=lookup
    )
    assert seen["engine"] == "live"
    assert (name, source) == ("ma_crossover", "pg_link_id")


def test_strategy_from_link_lv_without_owner_does_not_misclassify_as_demo():
    """回歸守衛：lv 無 owner 時應 unknown_pending，且查詢的 engine 不得是 demo。"""
    engines_seen = []

    def lookup(engine):
        engines_seen.append(engine)
        return {}

    name, source = cp._strategy_from_order_link_id(
        "oc_lv_42", symbol="BTCUSDT", engine_owner_lookup=lookup
    )
    assert engines_seen == ["live"]
    assert "demo" not in engines_seen
    assert (name, source) == ("unknown_pending", "pg_missing_unknown_external")


def test_strategy_from_link_risk_close_prefix_demo():
    """oc_risk_{em} 風控平倉前綴 → 正確抽出 em=dm。"""
    name, source = cp._strategy_from_order_link_id(
        "oc_risk_dm_1700000000000_5",
        symbol="DOGEUSDT",
        engine_owner_lookup=lambda e: {"DOGEUSDT": "grid_trading"} if e == "demo" else {},
    )
    assert (name, source) == ("grid_trading", "pg_link_id")


def test_strategy_from_link_ipc_close_prefix_live_demo():
    """oc_ipc_close_{em} 不可被泛 close_[a-z0-9_]+_ 先吃掉 'ipc' 導致 em 錯位。"""
    seen = {}

    def lookup(engine):
        seen["engine"] = engine
        return {"ETHUSDT": "funding_arb"} if engine == "live_demo" else {}

    name, source = cp._strategy_from_order_link_id(
        "oc_ipc_close_ld_1700000000000_9", symbol="ETHUSDT", engine_owner_lookup=lookup
    )
    assert seen["engine"] == "live_demo"
    assert (name, source) == ("funding_arb", "pg_link_id")


def test_strategy_from_link_maker_fallback_close_prefix_demo():
    """oc_close_mf_fb_{em} maker fallback 平倉前綴 → 正確抽出 em=dm。"""
    name, source = cp._strategy_from_order_link_id(
        "oc_close_mf_fb_dm_1700000000000_3",
        symbol="DOGEUSDT",
        engine_owner_lookup=lambda e: {"DOGEUSDT": "grid_trading"} if e == "demo" else {},
    )
    assert (name, source) == ("grid_trading", "pg_link_id")


def test_strategy_from_link_legacy_generic_close_prefix_still_matches():
    """向後相容：舊測試覆蓋的泛 oc_close_<...>_{em} 中綴仍須抽出 em。"""
    name, source = cp._strategy_from_order_link_id(
        "oc_close_maker_dm_1",
        symbol="DOGEUSDT",
        engine_owner_lookup=lambda e: {"DOGEUSDT": "grid_trading"} if e == "demo" else {},
    )
    assert (name, source) == ("grid_trading", "pg_link_id")


def test_strategy_from_link_shadow_rail_prefix_is_external():
    """sh_risk_ 為影子軌（非 Bybit-facing），不入此讀模型 → external_manual。"""
    name, source = cp._strategy_from_order_link_id(
        "sh_risk_dm_1", symbol="DOGEUSDT", engine_owner_lookup=lambda e: {"DOGEUSDT": "grid_trading"}
    )
    assert (name, source) == ("external_manual", "bybit_unknown")


@pytest.mark.parametrize("garbage", ["sh_xyz", "pop_123", "manual-entry", "", "oc_xx_1", "oc_zz_1"])
def test_strategy_from_link_non_openclaw_or_unknown_tag_is_external(garbage):
    """非 oc_ 前綴、或 em∉{dm,ld,lv}（含 paper-defensive xx）→ 既有 external fallback 不變。"""
    name, source = cp._strategy_from_order_link_id(
        garbage, symbol="DOGEUSDT", engine_owner_lookup=lambda e: {"DOGEUSDT": "grid_trading"}
    )
    assert (name, source) == ("external_manual", "bybit_unknown")
