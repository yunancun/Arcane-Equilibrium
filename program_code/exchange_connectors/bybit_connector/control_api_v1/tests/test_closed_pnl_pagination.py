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
        "openFee": "0.02",
        "closeFee": "0.01",
        "closedSize": "10",
        "fillCount": "2",
        "updatedTime": "1700000000000",
        "orderId": "OID1",
    }
    out = cp._closed_pnl_snake_row(row)
    assert out["closed_pnl"] == 1.0
    assert out["bybit_closed_pnl"] == 1.0
    assert out["bybit_fee_total"] == pytest.approx(0.03)
    assert out["bybit_gross_pnl"] == pytest.approx(1.03)
    assert out["authoritative_pnl"] == 1.0
    assert out["learning_pnl"] == 1.0
    assert out["avg_entry_price"] == 1.5
    assert out["fill_count"] == 2
    assert out["order_id"] == "OID1"
    # 原始 camelCase 鍵保留
    assert out["closedPnl"] == "1.0"


def test_snake_row_handles_missing_fill_count():
    out = cp._closed_pnl_snake_row({"symbol": "X"})
    assert out["fill_count"] == 0
    # 展示欄 closed_pnl 缺漏補 0.0（僅影響 UI）
    assert out["closed_pnl"] == 0.0


def test_snake_row_missing_closed_pnl_fail_closes_learning_pnl():
    """closedPnl 缺漏 → authoritative/learning_pnl 必 None + fail_closed source（DIRTY-FIX LOW-3）。

    為什麼：closed_pnl / bybit_closed_pnl 是展示欄，缺漏補 0.0 僅影響 UI；但
    authoritative_pnl / learning_pnl 是對帳與學習口徑欄，捏造 0.0 並標
    authoritative='bybit_closed_pnl' = 把「交易所沒給淨值」偽裝成「淨值=0 且權威」，
    與 PG 備援路徑（learning_pnl=None + fail_closed source）矛盾。兩路徑須對稱。
    """
    out = cp._closed_pnl_snake_row({"symbol": "X"})
    # 學習/對帳口徑欄 fail-closed None
    assert out["learning_pnl"] is None
    assert out["learning_pnl_source"] == "bybit_pnl_missing_fail_closed"
    assert out["authoritative_pnl"] is None
    assert out["authoritative_pnl_source"] == "bybit_pnl_missing_fail_closed"


def test_snake_row_present_closed_pnl_keeps_authoritative(monkeypatch):
    """closedPnl 存在（含真實 0.0）→ authoritative/learning_pnl 走交易所權威值，不被誤 fail-close。"""
    # 真實 closedPnl=0.0（交易所確實給了 0）≠ 缺漏，必標 authoritative
    out = cp._closed_pnl_snake_row({"symbol": "X", "closedPnl": "0.0"})
    assert out["learning_pnl"] == 0.0
    assert out["learning_pnl_source"] == "bybit_closed_pnl"
    assert out["authoritative_pnl"] == 0.0
    assert out["authoritative_pnl_source"] == "bybit_closed_pnl"


def test_attach_missing_closed_pnl_does_not_override_fail_closed(monkeypatch):
    """_attach_closed_pnl_strategy 對 closedPnl 缺漏行不得覆寫成捏造 0.0（DIRTY-FIX LOW-3）。

    為什麼：override 區塊舊用 enriched["closed_pnl"]（展示欄，缺漏已補 0.0）判存在 →
    把缺漏誤判為「淨值=0」覆寫 learning_pnl=0.0。改用原始 row["closedPnl"] 判存在，
    缺漏時不覆寫 snake_row 設好的 fail-closed None（與 PG 備援路徑對稱）。
    """
    monkeypatch.setattr(cp, "_fetch_strategy_by_order_id", lambda ids, **kw: {})
    monkeypatch.setattr(cp, "_fetch_strategy_by_symbol_time", lambda rows, **kw: {})
    # closedPnl 缺漏（無 key）的 Bybit row
    rows = [{"symbol": "DOGEUSDT", "side": "Buy", "orderId": "OID9", "orderLinkId": ""}]
    out = cp._attach_closed_pnl_strategy(rows, engine_owner_lookup=lambda e: {})
    assert len(out) == 1
    item = out[0]
    assert item["learning_pnl"] is None
    assert item["learning_pnl_source"] == "bybit_pnl_missing_fail_closed"
    assert item["authoritative_pnl"] is None
    assert item["authoritative_pnl_source"] == "bybit_pnl_missing_fail_closed"


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


# ── gross PnL / fee 還原 helper ───────────────────────────────────────────────


def test_bybit_fee_total_sums_open_and_close_fee():
    assert cp._bybit_fee_total({"openFee": "0.02", "closeFee": "0.01"}) == pytest.approx(0.03)
    # snake_case fallback + 缺漏視為 0
    assert cp._bybit_fee_total({"open_fee": "0.05"}) == pytest.approx(0.05)
    assert cp._bybit_fee_total({}) == 0.0


def test_bybit_gross_pnl_adds_back_fees():
    """gross = net closedPnl + open/close fee（同口徑對帳，避免費用差假性放大 drift）。"""
    assert cp._bybit_gross_pnl(
        {"closedPnl": "1.0", "openFee": "0.02", "closeFee": "0.01"}
    ) == pytest.approx(1.03)


def test_bybit_gross_pnl_none_when_closed_pnl_missing():
    """closedPnl 缺漏 → gross 回 None（caller fail-closed）。"""
    assert cp._bybit_gross_pnl({"openFee": "0.02"}) is None


# ── PG 備援 fail-closed learning_pnl 分支 ──────────────────────────────────────


class _FakeCursor:
    """最小 cursor stub：SET LOCAL statement_timeout no-op，SELECT 回注入 rows。"""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=None):  # noqa: D401 - stub
        # SET LOCAL statement_timeout 是 no-op；真正取數走 fetchall。
        return None

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)


def _patch_db(monkeypatch, rows):
    """注入假 db_pool.get_conn/put_conn，回傳吐 rows 的 _FakeConn。"""
    fake_conn = _FakeConn(rows)
    from app import db_pool  # noqa: PLC0415

    monkeypatch.setattr(db_pool, "get_conn", lambda: fake_conn)
    monkeypatch.setattr(db_pool, "put_conn", lambda conn: None)
    return fake_conn


def test_pg_fallback_learning_pnl_fail_closed_none(monkeypatch):
    """PG 備援分支 learning_pnl 必 fail-closed 為 None（缺權威淨 closedPnl，不得餵學習）。

    為什麼：備援只有 PG 毛 realized_pnl + close fee，缺交易所權威淨值 + open fee；
    估算淨值（authoritative_pnl）僅供展示，learning_pnl 必 None 否則污染 M4 學習口徑。
    """
    import datetime as _dt

    ts = _dt.datetime(2026, 6, 14, 0, 0, 0, tzinfo=_dt.timezone.utc)
    # (ts, order_id, symbol, side, qty, price, fee, realized_pnl, strategy_name)
    rows = [(ts, "OID1", "DOGEUSDT", "Buy", 10, 0.5, 0.01, 1.0, "grid_trading")]
    _patch_db(monkeypatch, rows)

    out = cp._fetch_pg_closed_pnl_fallback(
        limit=10, offset=0, symbol=None, start_ms=0, end_ms=99999999999999,
    )
    assert out["count"] == 1
    item = out["list"][0]
    # learning_pnl fail-closed
    assert item["learning_pnl"] is None
    assert item["learning_pnl_source"] == "bybit_unavailable_fail_closed"
    # authoritative_pnl = 估算淨值 = pg_gross - close_fee = 1.0 - 0.01
    assert item["authoritative_pnl"] == pytest.approx(0.99)
    assert item["authoritative_pnl_source"] == "pg_fallback_estimated_net"
    assert item["pg_engine_gross_pnl"] == pytest.approx(1.0)
    assert item["pg_engine_close_fee"] == pytest.approx(0.01)
    assert item["pnl_source_drift_basis"] == "pg_fallback_no_bybit"


def test_pg_fallback_pg_unavailable_raises(monkeypatch):
    """get_conn 回 None → fail-loud RuntimeError('pg_unavailable')，不靜默吐空。"""
    from app import db_pool  # noqa: PLC0415

    monkeypatch.setattr(db_pool, "get_conn", lambda: None)
    monkeypatch.setattr(db_pool, "put_conn", lambda conn: None)
    with pytest.raises(RuntimeError, match="pg_unavailable"):
        cp._fetch_pg_closed_pnl_fallback(
            limit=10, offset=0, symbol=None, start_ms=0, end_ms=1,
        )
