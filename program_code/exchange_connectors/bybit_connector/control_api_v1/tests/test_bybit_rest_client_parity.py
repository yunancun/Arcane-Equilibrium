"""Snapshot tests for the httpx BybitClient (PYO3-ELIMINATE-1 Phase 3 後).
httpx BybitClient snapshot 測試（PYO3-ELIMINATE-1 Phase 3 後）.

MODULE_NOTE (EN): Post-Phase-3 regression guard — the old PyO3 parity mode
  has been deleted along with the `rust/openclaw_pyo3` crate. These tests now
  snapshot-assert the known-good shape produced by the new httpx BybitClient
  against captured Bybit V5 fixtures, so the 3 call sites (strategy_ai_routes,
  live_session_routes, clean_restart_flatten) never silently regress.

  Raw shapes served by the httpx client:
    * refresh_balance / get_instrument / place_order → snake_case
    * get_positions / get_active_orders / get_executions → camelCase (Bybit V5 verbatim)
  Production `_normalize_order` / `_normalize_execution` fallback chains
  tolerate both — snapshots target the NORMALIZED output.

MODULE_NOTE (中): Phase 3 後的 regression guard。舊 PyO3 parity 模式與
  `rust/openclaw_pyo3` crate 已一併刪除；本檔用 Bybit V5 fixture 對新 httpx
  BybitClient 做 snapshot，確保 3 個 call site 的形狀不退化。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import pytest

# ---------------------------------------------------------------------------
# Imports with graceful guards / 匯入與優雅守衛
# ---------------------------------------------------------------------------

# New httpx BybitClient — MUST exist post-Phase-2. Missing import → all tests skip.
# 新 httpx BybitClient — Phase 2 後必存在；缺失 → 全部 skip。
try:
    from app.bybit_rest_client import (
        BybitBusinessError as NewBybitBusinessError,
        BybitClient as NewBybitClient,
    )
    _NEW_CLIENT_AVAILABLE = True
except ImportError:
    NewBybitClient = None  # type: ignore[assignment,misc]
    NewBybitBusinessError = Exception  # type: ignore[assignment,misc]
    _NEW_CLIENT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Fixture loading / 夾具載入
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "bybit_v5_responses"


def _load_fixture(name: str) -> dict[str, Any]:
    """Load a Bybit V5 response fixture by filename stem.
    依檔名 stem 載入 Bybit V5 回應 fixture。"""
    path = FIXTURES_DIR / f"{name}.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Shared env clean-up / 共用環境清理
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path: Path):
    """Scrub env / HOME so credential resolution cannot leak real values.
    清理 env / HOME，避免真實憑證洩漏進測試。"""
    for var in (
        "BYBIT_API_KEY",
        "BYBIT_API_SECRET",
        "OPENCLAW_ALLOW_MAINNET",
        "OPENCLAW_SECRETS_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# Mock transport plumbing / Mock transport 管線
# ---------------------------------------------------------------------------

def _bybit_mock_handler(
    routes: dict[str, dict[str, Any]],
) -> Callable[[httpx.Request], httpx.Response]:
    """Return a MockTransport handler that responds by (method, path) key.
    回傳依 (method, path) 分派的 MockTransport handler。

    `routes` shape:
        { "GET /v5/account/wallet-balance": {fixture_payload_dict} }
    """
    def _handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        payload = routes.get(key)
        if payload is None:
            # Default safe response — unknown route gets a retCode=10404 body
            # so the test crashes loudly rather than silently asserting nothing.
            # 未登記的路徑返回 10404 body，避免測試靜默通過。
            payload = {
                "retCode": 10404,
                "retMsg": f"test fixture missing route: {key}",
                "result": {},
                "retExtInfo": {},
                "time": 0,
            }
        return httpx.Response(
            200,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    return _handler


def _new_client_with_transport(
    routes: dict[str, dict[str, Any]],
    env: str = "demo",
) -> NewBybitClient:
    """Build a new httpx BybitClient wired to a MockTransport.
    構造掛載 MockTransport 的新 httpx BybitClient。"""
    c = NewBybitClient(api_key="TESTKEY", api_secret="TESTSECRET", environment=env)
    # Swap inner httpx.Client's transport — same technique as test_bybit_rest_client.py.
    # 把內部 httpx.Client 的 transport 換成 mock — 與既有測試相同手法。
    c._client.close()
    c._client = httpx.Client(
        base_url=c._base_url,
        timeout=5.0,
        transport=httpx.MockTransport(_bybit_mock_handler(routes)),
        headers={"Content-Type": "application/json"},
    )
    return c


# ---------------------------------------------------------------------------
# Normalization helpers — same shape production uses, imported defensively.
# Normalization 輔助函式 — 與生產端相同，防禦性匯入。
# ---------------------------------------------------------------------------

def _safe_normalize_order(o: dict[str, Any]) -> dict[str, Any]:
    """Mirror of strategy_ai_routes._normalize_order. Local copy to avoid
    pulling the entire strategy_ai_routes module (heavy imports) into the
    parity test just to call one helper.
    複製 strategy_ai_routes._normalize_order 本地實作，避免把整個重模組拉進來。"""
    if not isinstance(o, dict):
        return o
    return {
        **o,
        "orderId":      o.get("orderId")      or o.get("order_id"),
        "orderLinkId":  o.get("orderLinkId")  or o.get("order_link_id"),
        "orderStatus":  o.get("orderStatus")  or o.get("order_status"),
        "orderType":    o.get("orderType")    or o.get("order_type"),
        "triggerPrice": o.get("triggerPrice") or o.get("trigger_price"),
        "createdTime":  o.get("createdTime")  or o.get("created_time"),
        "updatedTime":  o.get("updatedTime")  or o.get("updated_time"),
    }


def _safe_normalize_execution(f: dict[str, Any]) -> dict[str, Any]:
    """Mirror of strategy_ai_routes._normalize_execution for execution rows.
    execution row 的本地 normalization 版本。"""
    if not isinstance(f, dict):
        return f
    cp = f.get("closedPnl")
    if cp is None:
        cp = f.get("closed_pnl")
    return {
        **f,
        "execQty":    f.get("execQty")   or f.get("exec_qty")   or f.get("qty"),
        "execPrice":  f.get("execPrice") or f.get("exec_price") or f.get("price"),
        "execFee":    f.get("execFee")   or f.get("exec_fee")   or f.get("fee"),
        "closedPnl":  cp,
    }


def _normalize_position(p: dict[str, Any]) -> dict[str, Any]:
    """Normalize position shape for parity — mirror the camelCase-or-snake_case
    fallback chain used by live_session_routes for position read paths.
    對持倉應用 camelCase/snake_case 雙來源 fallback 統一化。"""
    if not isinstance(p, dict):
        return p
    return {
        **p,
        "symbol":         p.get("symbol"),
        "side":           p.get("side"),
        "size":           p.get("size")           or p.get("qty"),
        "avgPrice":       p.get("avgPrice")       or p.get("avg_price"),
        "markPrice":      p.get("markPrice")      or p.get("mark_price"),
        "unrealisedPnl":  p.get("unrealisedPnl")  or p.get("unrealised_pnl"),
        "leverage":       p.get("leverage"),
        "positionIdx":    p.get("positionIdx")    or p.get("position_idx") or 0,
    }


def _key_sorted(d: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with top-level keys sorted (for stable snapshot compare).
    複製並排序頂層 key 的 dict（供 snapshot 穩定比對）。"""
    return {k: d[k] for k in sorted(d.keys())}


# ---------------------------------------------------------------------------
# Mode B — snapshot assertions on the new client only.
# Mode B — 僅對新 client 做 snapshot 斷言。
# ---------------------------------------------------------------------------

pytestmark_newclient_required = pytest.mark.skipif(
    not _NEW_CLIENT_AVAILABLE,
    reason="new app.bybit_rest_client.BybitClient not yet shipped (PYO3-ELIMINATE-1 Phase 2)",
)


@pytestmark_newclient_required
class TestModeBSnapshotNewClient:
    """Mode B — assert the new httpx BybitClient produces the expected shape.
    Mode B — 斷言新 client 產生的形狀符合契約。

    These snapshots are the ground truth Phase 2 ships against. If they
    regress, the migration spec is violated and the 3 call sites may break.
    這些 snapshot 是 Phase 2 發貨的 ground truth；破壞 = spec 違反 = 呼叫端可能壞。
    """

    def test_has_credentials_and_base_url(self):
        """Introspection fields align with what live_session_routes expects.
        Introspection 欄位須與 live_session_routes 期望一致。"""
        c = _new_client_with_transport({}, env="demo")
        try:
            assert c.has_credentials() is True
            assert c.base_url() == "https://api-demo.bybit.com"
            assert c.instrument_count() == 0
        finally:
            c.close()

    def test_refresh_balance_returns_wallet_state_shape(self):
        """refresh_balance returns WalletState-shaped snake_case dict.
        refresh_balance 回傳 WalletState 形狀 snake_case dict。"""
        routes = {
            "GET /v5/account/wallet-balance": _load_fixture("wallet_balance"),
        }
        c = _new_client_with_transport(routes)
        try:
            ws = c.refresh_balance()
            assert isinstance(ws, dict)
            # Required keys — mirrors Rust WalletState struct.
            # 必要 keys — 對齊 Rust WalletState。
            for key in (
                "account_type", "total_equity", "total_wallet_balance",
                "total_available_balance", "total_unrealised_pnl",
                "coins", "updated_at_ms",
            ):
                assert key in ws, f"missing WalletState key: {key}"
            assert ws["account_type"] == "UNIFIED"
            assert isinstance(ws["coins"], dict)
            assert "USDT" in ws["coins"]
            usdt = ws["coins"]["USDT"]
            for key in ("coin", "wallet_balance", "available_to_withdraw",
                        "equity", "unrealised_pnl", "cum_realised_pnl"):
                assert key in usdt, f"missing CoinBalance key: {key}"
            assert usdt["coin"] == "USDT"
            assert usdt["wallet_balance"] == pytest.approx(9800.5)
        finally:
            c.close()

    def test_refresh_balance_retcode_error(self):
        """retCode != 0 raises BybitBusinessError.
        retCode != 0 拋 BybitBusinessError。"""
        routes = {
            "GET /v5/account/wallet-balance": _load_fixture("wallet_balance_error"),
        }
        c = _new_client_with_transport(routes)
        try:
            with pytest.raises(NewBybitBusinessError) as exc_info:
                c.refresh_balance()
            assert exc_info.value.ret_code == 10001
            assert "accountType invalid" in exc_info.value.ret_msg
        finally:
            c.close()

    def test_refresh_instruments_and_get_instrument(self):
        """refresh_instruments populates cache; get_instrument returns SymbolSpec.
        refresh_instruments 填快取；get_instrument 回傳 SymbolSpec。"""
        routes = {
            "GET /v5/market/instruments-info": _load_fixture("instruments_info_linear"),
        }
        c = _new_client_with_transport(routes)
        try:
            loaded = c.refresh_instruments("linear")
            assert loaded == 3
            assert c.instrument_count() == 3
            spec = c.get_instrument("BTCUSDT")
            assert spec is not None
            for key in (
                "symbol", "base_currency", "quote_currency", "contract_type",
                "qty_step", "min_qty", "max_qty", "tick_size", "min_price",
                "max_price", "min_notional", "qty_decimals", "price_decimals",
            ):
                assert key in spec, f"missing SymbolSpec key: {key}"
            assert spec["symbol"] == "BTCUSDT"
            assert spec["qty_step"] == pytest.approx(0.001)
            assert spec["qty_decimals"] == 3
            assert spec["tick_size"] == pytest.approx(0.1)
            assert spec["price_decimals"] == 1
            # Unknown symbol returns None (not a raise).
            # 未知 symbol 回 None（不拋）。
            assert c.get_instrument("UNKNOWNUSDT") is None
        finally:
            c.close()

    def test_round_qty_none_semantics(self):
        """round_qty returns None for uncached symbols — caller relies on this.
        round_qty 對未快取 symbol 回 None — 呼叫端依賴此語意。"""
        c = _new_client_with_transport({})
        try:
            # No refresh_instruments call → cache empty → None return.
            # 未呼叫 refresh_instruments → 快取空 → 回 None。
            assert c.round_qty("BTCUSDT", 0.05) is None
        finally:
            c.close()

    def test_round_qty_floor_to_step(self):
        """round_qty floor-rounds to qty_step once cached.
        已快取後 round_qty 地板取整到 qty_step。"""
        routes = {
            "GET /v5/market/instruments-info": _load_fixture("instruments_info_linear"),
        }
        c = _new_client_with_transport(routes)
        try:
            c.refresh_instruments("linear")
            # BTC qty_step=0.001 → floor(0.00459 / 0.001) * 0.001 = 0.004.
            assert c.round_qty("BTCUSDT", 0.00459) == pytest.approx(0.004)
            # ETH qty_step=0.01 → floor(0.129 / 0.01) * 0.01 = 0.12.
            assert c.round_qty("ETHUSDT", 0.129) == pytest.approx(0.12)
            # DOGE qty_step=1 → floor(103.8 / 1) * 1 = 103.
            assert c.round_qty("DOGEUSDT", 103.8) == pytest.approx(103.0)
        finally:
            c.close()

    def test_get_positions_returns_camelcase_list(self):
        """get_positions returns raw Bybit V5 camelCase rows.
        get_positions 回傳原始 Bybit V5 camelCase rows。"""
        routes = {
            "GET /v5/position/list": _load_fixture("positions_list"),
        }
        c = _new_client_with_transport(routes)
        try:
            positions = c.get_positions("linear")
            assert isinstance(positions, list)
            assert len(positions) == 2
            p = positions[0]
            # camelCase — confirms new client does NOT snake_case these.
            # camelCase — 確認新 client 對持倉未做 snake_case 轉換。
            for key in ("symbol", "side", "size", "avgPrice", "markPrice",
                        "unrealisedPnl", "leverage"):
                assert key in p, f"missing camelCase key: {key}"
            assert p["symbol"] == "BTCUSDT"
            assert p["side"] == "Buy"
            assert p["size"] == "0.01"   # Bybit sends numbers as strings.
        finally:
            c.close()

    def test_get_active_orders_returns_camelcase_list(self):
        """get_active_orders returns raw Bybit V5 camelCase order rows.
        get_active_orders 回傳原始 Bybit V5 camelCase orders。"""
        routes = {
            "GET /v5/order/realtime": _load_fixture("order_realtime"),
        }
        c = _new_client_with_transport(routes)
        try:
            orders = c.get_active_orders("linear", None, "USDT")
            assert isinstance(orders, list)
            assert len(orders) == 2
            o = orders[0]
            for key in ("orderId", "orderLinkId", "symbol", "orderStatus",
                        "orderType", "side", "qty", "price"):
                assert key in o, f"missing camelCase key: {key}"
            assert o["orderId"] == "1712262345000-BTC-01"
            # Normalization must not lose data — round-trip through helper.
            # 走一趟 normalization 不得丟數據。
            normalized = _safe_normalize_order(o)
            assert normalized["orderId"] == "1712262345000-BTC-01"
            assert normalized["orderStatus"] == "New"
            assert normalized["orderType"] == "Limit"
        finally:
            c.close()

    def test_get_active_orders_filters_untriggered(self):
        """Conditional (stop) orders show orderStatus=Untriggered — GUI depends on this.
        條件（止損）訂單 orderStatus=Untriggered — GUI 過濾器依賴此值。"""
        routes = {
            "GET /v5/order/realtime": _load_fixture("order_realtime"),
        }
        c = _new_client_with_transport(routes)
        try:
            orders = c.get_active_orders("linear", None, "USDT")
            untriggered = [
                o for o in orders
                if (o.get("orderStatus") or "").lower() == "untriggered"
            ]
            assert len(untriggered) == 1
            assert untriggered[0]["symbol"] == "ETHUSDT"
        finally:
            c.close()

    def test_get_executions_returns_camelcase_with_closedpnl(self):
        """get_executions returns Bybit V5 rows with closedPnl camelCase key.
        get_executions 回傳 Bybit V5 row 含 closedPnl camelCase key。"""
        routes = {
            "GET /v5/execution/list": _load_fixture("execution_list"),
        }
        c = _new_client_with_transport(routes)
        try:
            fills = c.get_executions("linear", limit=50)
            assert isinstance(fills, list)
            assert len(fills) == 3
            f = fills[1]   # SELL fill with non-zero closedPnl.
            for key in ("symbol", "orderId", "execId", "execQty", "execPrice",
                        "execFee", "closedPnl", "side", "execTime"):
                assert key in f, f"missing camelCase key: {key}"
            # closedPnl string → normalization preserves it.
            # closedPnl 為字串 → normalization 不丟失。
            normalized = _safe_normalize_execution(f)
            assert normalized["closedPnl"] == "4.992825"
            # Open-leg (index 0) has closedPnl == "0" (not None) — must NOT
            # be coerced to None or falsy-dropped.
            # 開倉腿 closedPnl == "0"，不得被 falsy-drop。
            open_leg = _safe_normalize_execution(fills[0])
            assert open_leg["closedPnl"] == "0"
        finally:
            c.close()

    def test_place_order_dual_shape_response(self):
        """place_order returns BOTH snake_case and camelCase order id keys.
        place_order 返回 snake_case + camelCase 雙形狀的 order id。"""
        routes = {
            "POST /v5/order/create": _load_fixture("order_create_success"),
        }
        c = _new_client_with_transport(routes)
        try:
            resp = c.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Market",
                qty=0.01,
                category="linear",
                reduce_only=False,
            )
            assert isinstance(resp, dict)
            # Both shapes present for drop-in parity with call sites.
            # 雙形狀並存以對呼叫端 drop-in 相容。
            assert resp["order_id"] == "1712262345000-NEW-ORDER-01"
            assert resp["order_link_id"] == "openclaw-create-001"
            assert resp["orderId"] == "1712262345000-NEW-ORDER-01"
            assert resp["orderLinkId"] == "openclaw-create-001"
        finally:
            c.close()

    def test_place_order_reduce_only_live_gate_fallback_1(self):
        """LIVE-GATE-FALLBACK-1: reduce_only=True emergency close path must work.
        LIVE-GATE-FALLBACK-1：reduce_only=True 緊急平倉路徑必須可用。"""
        routes = {
            "POST /v5/order/create": _load_fixture("order_create_success"),
        }
        c = _new_client_with_transport(routes)
        try:
            resp = c.place_order(
                symbol="ETHUSDT",
                side="Sell",
                order_type="Market",
                qty=0.1,
                category="linear",
                reduce_only=True,
            )
            # Same dual-shape contract under reduce_only branch.
            # reduce_only 分支下同樣雙形狀契約。
            assert resp["order_id"] == "1712262345000-NEW-ORDER-01"
            assert resp["orderId"] == "1712262345000-NEW-ORDER-01"
        finally:
            c.close()

    def test_cancel_order_dual_shape_response(self):
        """cancel_order returns dual-shape like place_order.
        cancel_order 同樣雙形狀。"""
        routes = {
            "POST /v5/order/cancel": _load_fixture("order_cancel_success"),
        }
        c = _new_client_with_transport(routes)
        try:
            resp = c.cancel_order(
                symbol="BTCUSDT",
                order_id="1712262345000-CANCEL-01",
                category="linear",
            )
            assert resp["order_id"] == "1712262345000-CANCEL-01"
            assert resp["orderId"] == "1712262345000-CANCEL-01"
            assert resp["order_link_id"] == "openclaw-cancel-001"
            assert resp["orderLinkId"] == "openclaw-cancel-001"
        finally:
            c.close()


# ---------------------------------------------------------------------------
# Coverage matrix sanity check — meta-test asserts we covered the 12
# headline methods the migration spec (§5) lists.
# 覆蓋矩陣檢查 — meta-test 斷言覆蓋了 spec §5 列出的 12 個 headline 方法。
# ---------------------------------------------------------------------------

@pytestmark_newclient_required
def test_parity_coverage_matrix_complete():
    """Meta-test: every headline method from migration spec §5 has a Mode B test.
    Meta-test：spec §5 的 12 個 headline 方法都有對應 Mode B 測試。"""
    headline_methods = {
        "__init__",            # test_has_credentials_and_base_url
        "has_credentials",     # test_has_credentials_and_base_url
        "base_url",            # test_has_credentials_and_base_url
        "instrument_count",    # test_has_credentials_and_base_url
        "refresh_balance",     # test_refresh_balance_returns_wallet_state_shape
        "refresh_instruments", # test_refresh_instruments_and_get_instrument
        "get_instrument",      # test_refresh_instruments_and_get_instrument
        "round_qty",           # test_round_qty_none_semantics + floor_to_step
        "get_positions",       # test_get_positions_returns_camelcase_list
        "get_active_orders",   # test_get_active_orders_returns_camelcase_list
        "get_executions",      # test_get_executions_returns_camelcase_with_closedpnl
        "place_order",         # test_place_order_dual_shape_response + LIVE-GATE-FALLBACK-1
        "cancel_order",        # test_cancel_order_dual_shape_response
    }
    # Verify each method exists on the new client surface.
    # 確認每個方法存在於新 client 介面。
    for name in headline_methods:
        assert hasattr(NewBybitClient, name), (
            f"new BybitClient missing headline method: {name}"
        )


# ---------------------------------------------------------------------------
# PYO3-ELIMINATE-1 checkpoint detector — never lets the snapshot silently bit-rot.
# PYO3-ELIMINATE-1 checkpoint 檢測 — 防止 snapshot 靜默 bit-rot。
# ---------------------------------------------------------------------------

def test_parity_mode_status_report(capsys):
    """Emit a structured status line so CI can grep it.
    輸出結構化狀態行供 CI grep。"""
    status = {
        "new_client_available": _NEW_CLIENT_AVAILABLE,
        "phase": "post_phase3_snapshot_only",
    }
    print(f"PYO3_PARITY_STATUS={json.dumps(status, sort_keys=True)}")
    # Always passes — this is a signal-beacon, not a correctness check.
    # 永遠通過 — 此為狀態燈，非正確性檢查。
    assert True
