"""Unit tests for the Python httpx BybitClient drop-in replacement.
Python httpx 版 BybitClient drop-in 取代的單元測試。

MODULE_NOTE (EN): Uses httpx.MockTransport to intercept requests — no real Bybit
  endpoint is hit. Covers constructor env mapping, credential loading, HMAC
  signing correctness (known vector), every public method's happy/edge paths,
  and the retCode != 0 error path.
MODULE_NOTE (中): 使用 httpx.MockTransport 攔截請求 — 不會打到真實 Bybit 端點。
  覆蓋 ctor 環境映射、憑證載入、HMAC 簽章正確性（已知向量）、所有公開方法
  的正常與邊界路徑，以及 retCode != 0 的錯誤路徑。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import pytest

from app.bybit_rest_client import (
    BybitBusinessError,
    BybitClient,
    BybitCredentialsMissing,
    BybitTransportError,
    _decimals_from_step,
    _format_number,
    _normalize_env,
    _parse_instrument_item,
    _resolve_credentials,
)


# ---------------------------------------------------------------------------
# Fixtures / 夾具
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path: Path):
    """Clean environment for every test — avoid real credentials leaking in.
    每個測試清理環境 — 避免真實憑證洩漏。"""
    # Strip anything that could affect credential resolution.
    for var in (
        "BYBIT_API_KEY",
        "BYBIT_API_SECRET",
        "OPENCLAW_ALLOW_MAINNET",
        "OPENCLAW_SECRETS_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    # Redirect HOME so _secrets_base_dir() cannot read real slot files.
    monkeypatch.setenv("HOME", str(tmp_path))
    yield


def _install_mock_transport(
    client: BybitClient,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Request]:
    """Swap the client's transport for a MockTransport and record requests.
    Returns the list that will be populated with each intercepted request.
    把 client 的 transport 換成 MockTransport，回傳一個會累積攔截請求的 list。
    """
    recorded: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return handler(request)

    mock = httpx.MockTransport(_wrapped)
    # Rebuild the inner httpx.Client with the MockTransport bound.
    # 用 MockTransport 重建 inner httpx.Client。
    client._client.close()
    client._client = httpx.Client(
        base_url=client._base_url,
        timeout=5.0,
        transport=mock,
        headers={"Content-Type": "application/json"},
    )
    return recorded


def _ok_envelope(result: Any = None) -> dict[str, Any]:
    """Build a standard Bybit V5 success envelope.
    組標準 Bybit V5 成功 envelope。"""
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": result if result is not None else {},
        "time": 1700000000000,
    }


def _make_client(env: str = "demo") -> BybitClient:
    """Construct a BybitClient with explicit dummy credentials.
    構造帶 dummy 憑證的 BybitClient。"""
    return BybitClient(api_key="TESTKEY", api_secret="TESTSECRET", environment=env)


# ---------------------------------------------------------------------------
# Env / URL mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "env_str, expected_url",
    [
        ("demo",      "https://api-demo.bybit.com"),
        ("testnet",   "https://api-testnet.bybit.com"),
        ("mainnet",   "https://api.bybit.com"),
        ("live_demo", "https://api-demo.bybit.com"),
    ],
)
def test_ctor_environment_maps_to_base_url(monkeypatch, env_str, expected_url):
    """Each supported environment string must map to the correct base URL.
    每個支援的環境字串必須映射到正確的 base URL。"""
    if env_str == "mainnet":
        monkeypatch.setenv("OPENCLAW_ALLOW_MAINNET", "1")
    c = BybitClient(api_key="k", api_secret="s", environment=env_str)
    assert c.base_url() == expected_url
    c.close()


def test_ctor_unknown_environment_defaults_to_demo():
    """Unknown environment strings default to demo (Rust parity — safe default).
    未知環境字串默認 demo（與 Rust 一致的安全默認值）。"""
    c = BybitClient(api_key="k", api_secret="s", environment="production")
    assert c.base_url() == "https://api-demo.bybit.com"
    c.close()


def test_ctor_normalize_env_is_case_insensitive():
    """Environment string is case-insensitive (matches Rust parse_environment).
    環境字串不區分大小寫。"""
    assert _normalize_env("DEMO") == "demo"
    assert _normalize_env("Mainnet") == "mainnet"
    assert _normalize_env("Live") == "mainnet"   # 'live' alias


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------

def test_has_credentials_explicit():
    """Explicit params → has_credentials True.
    顯式傳 param → has_credentials True。"""
    c = BybitClient(api_key="k", api_secret="s", environment="demo")
    assert c.has_credentials() is True
    c.close()


def test_has_credentials_env_var_for_demo(monkeypatch):
    """Demo env var fallback is allowed.
    Demo 允許 env var 回退。"""
    monkeypatch.setenv("BYBIT_API_KEY", "envkey")
    monkeypatch.setenv("BYBIT_API_SECRET", "envsecret")
    c = BybitClient(environment="demo")
    assert c.has_credentials() is True
    assert c._api_key == "envkey"
    assert c._api_secret == "envsecret"
    c.close()


def test_has_credentials_slot_file_fallback(tmp_path, monkeypatch):
    """Slot-file credentials load when no param / env var present.
    無 param / env var 時 slot 檔案憑證載入。"""
    # Set up slot file layout.
    slot_dir = tmp_path / "demo"
    slot_dir.mkdir()
    (slot_dir / "api_key").write_text("slot_key_value\n", encoding="utf-8")
    (slot_dir / "api_secret").write_text("slot_secret_value\n", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(tmp_path))
    c = BybitClient(environment="demo")
    assert c._api_key == "slot_key_value"
    assert c._api_secret == "slot_secret_value"
    c.close()


def test_mainnet_env_var_fallback_disabled(monkeypatch):
    """LIVE-GUARD-1 Gate #2: Mainnet must NOT read BYBIT_API_KEY/SECRET env vars.
    Mainnet 不得從 env var 讀憑證（LIVE-GUARD-1 Gate #2）。"""
    monkeypatch.setenv("OPENCLAW_ALLOW_MAINNET", "1")
    monkeypatch.setenv("BYBIT_API_KEY", "envkey")
    monkeypatch.setenv("BYBIT_API_SECRET", "envsecret")
    with pytest.raises(BybitBusinessError) as exc_info:
        BybitClient(environment="mainnet")
    assert "credentials missing" in str(exc_info.value).lower()


def test_mainnet_requires_openclaw_allow_mainnet_env():
    """LIVE-GUARD-1 Gate #1: Mainnet construction fails without opt-in env var.
    Mainnet 無 opt-in env var 時構造失敗（LIVE-GUARD-1 Gate #1）。"""
    with pytest.raises(BybitBusinessError) as exc_info:
        BybitClient(api_key="k", api_secret="s", environment="mainnet")
    assert "OPENCLAW_ALLOW_MAINNET" in str(exc_info.value)


def test_resolve_credentials_mainnet_prefers_param(monkeypatch):
    """Explicit param wins on Mainnet (env var is ignored, slot is fallback).
    Mainnet 顯式 param 優先（env var 忽略，slot 為回退）。"""
    monkeypatch.setenv("BYBIT_API_KEY", "envkey")
    monkeypatch.setenv("BYBIT_API_SECRET", "envsecret")
    k, s = _resolve_credentials("mainnet", "param_key", "param_secret")
    assert (k, s) == ("param_key", "param_secret")


# ---------------------------------------------------------------------------
# HMAC signing (known test vector)
# ---------------------------------------------------------------------------

def test_sign_known_vector_matches_rust_formula():
    """HMAC-SHA256 must match Rust common::bybit_signer::sign_rest_v5 byte-for-byte.
    HMAC-SHA256 必須與 Rust 端字節一致。"""
    c = BybitClient(api_key="TESTKEY123", api_secret="TESTSECRET456", environment="demo")
    timestamp = "1700000000000"
    params = "category=linear&symbol=BTCUSDT"

    # Manually compute the Rust formula.
    payload = f"{timestamp}{c._api_key}{c._recv_window}{params}"
    expected = hmac.new(
        b"TESTSECRET456", payload.encode("utf-8"), hashlib.sha256,
    ).hexdigest()

    actual = c._sign(timestamp, params)
    assert actual == expected
    assert len(actual) == 64
    assert actual.islower()
    c.close()


def test_sign_empty_params():
    """Empty params produce a valid 64-char hex signature.
    空 params 時簽章為 64 字元合法 hex。"""
    c = BybitClient(api_key="K", api_secret="S", environment="demo")
    sig = c._sign("1700000000000", "")
    assert len(sig) == 64
    assert all(ch in "0123456789abcdef" for ch in sig)
    c.close()


def test_sign_payload_bindings_includes_recv_window():
    """Signing must include recv_window — regression against drifting format.
    簽章須包含 recv_window — 防止格式漂移的回歸測試。"""
    c = BybitClient(api_key="K", api_secret="S", environment="demo")
    assert c._recv_window == "5000"
    # Flip recv_window → signature must change.
    sig1 = c._sign("1", "p=1")
    c._recv_window = "10000"
    sig2 = c._sign("1", "p=1")
    assert sig1 != sig2
    c.close()


# ---------------------------------------------------------------------------
# refresh_balance
# ---------------------------------------------------------------------------

def test_refresh_balance_success_shape():
    """refresh_balance returns a WalletState-shaped dict with snake_case keys.
    refresh_balance 返回 WalletState 形狀 dict（snake_case）。"""
    c = _make_client()
    result = {
        "list": [{
            "accountType": "UNIFIED",
            "totalEquity": "10500.5",
            "totalWalletBalance": "10000",
            "totalAvailableBalance": "9500.25",
            "coin": [
                {
                    "coin": "USDT",
                    "walletBalance": "10000",
                    "availableToWithdraw": "9500.25",
                    "equity": "10500.5",
                    "unrealisedPnl": "500.5",
                    "cumRealisedPnl": "123",
                },
            ],
        }]
    }
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope(result)),
    )

    snap = c.refresh_balance()
    assert snap["account_type"] == "UNIFIED"
    assert snap["total_equity"] == pytest.approx(10500.5)
    assert snap["total_wallet_balance"] == pytest.approx(10000.0)
    assert snap["total_available_balance"] == pytest.approx(9500.25)
    assert "USDT" in snap["coins"]
    usdt = snap["coins"]["USDT"]
    assert usdt["wallet_balance"] == pytest.approx(10000.0)
    assert usdt["equity"] == pytest.approx(10500.5)
    assert usdt["unrealised_pnl"] == pytest.approx(500.5)
    assert snap["total_unrealised_pnl"] == pytest.approx(500.5)
    assert snap["updated_at_ms"] > 0
    c.close()


def test_refresh_balance_ret_code_error():
    """retCode != 0 raises BybitBusinessError with code + msg.
    retCode != 0 raise BybitBusinessError 含 code + msg。"""
    c = _make_client()
    err_body = {
        "retCode": 10003,
        "retMsg": "Invalid api_key",
        "result": {},
        "time": 1700000000000,
    }
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=err_body),
    )
    with pytest.raises(BybitBusinessError) as exc_info:
        c.refresh_balance()
    assert exc_info.value.ret_code == 10003
    assert "Invalid api_key" in str(exc_info.value)
    c.close()


def test_refresh_balance_without_credentials_raises():
    """Private endpoint without credentials raises BybitCredentialsMissing.
    無憑證呼叫私有端點 raise BybitCredentialsMissing。"""
    c = BybitClient(environment="demo")   # no credentials, no env, no slot
    assert c.has_credentials() is False
    with pytest.raises(BybitCredentialsMissing):
        c.refresh_balance()
    c.close()


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------

def test_get_positions_empty_list():
    """Empty positions list returns [].
    空持倉列表返回 []。"""
    c = _make_client()
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": []})),
    )
    assert c.get_positions("linear") == []
    c.close()


def test_get_positions_linear_includes_settle_coin():
    """Linear positions query must add settleCoin=USDT.
    Linear 查詢必須帶 settleCoin=USDT。"""
    c = _make_client()
    recorded = _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": []})),
    )
    c.get_positions("linear")
    assert len(recorded) == 1
    req = recorded[0]
    params = dict(req.url.params)
    assert params.get("category") == "linear"
    assert params.get("settleCoin") == "USDT"
    c.close()


def test_get_positions_non_empty_preserves_camel_case_fields():
    """Positions are returned raw (camelCase preserved) so call sites can read
    markPrice / avgPrice / etc.
    持倉原樣返回（保留 camelCase），call sites 可讀 markPrice / avgPrice 等。"""
    c = _make_client()
    sample = [{
        "symbol": "BTCUSDT",
        "side": "Buy",
        "size": "0.01",
        "avgPrice": "50000",
        "markPrice": "50100",
        "unrealisedPnl": "1.0",
        "positionValue": "500",
    }]
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": sample})),
    )
    rows = c.get_positions("linear")
    assert len(rows) == 1
    row = rows[0]
    assert row["markPrice"] == "50100"
    assert row["avgPrice"] == "50000"
    c.close()


# ---------------------------------------------------------------------------
# get_active_orders
# ---------------------------------------------------------------------------

def test_get_active_orders_uses_settle_coin_when_symbol_none():
    """No symbol → settleCoin param is used.
    未傳 symbol → 使用 settleCoin 參數查詢。"""
    c = _make_client()
    recorded = _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": []})),
    )
    c.get_active_orders("linear", None, "USDT")
    params = dict(recorded[0].url.params)
    assert params.get("category") == "linear"
    assert params.get("settleCoin") == "USDT"
    assert "symbol" not in params
    c.close()


def test_get_active_orders_with_symbol_filters_by_symbol():
    """With symbol → symbol param used (no settleCoin).
    有 symbol → 按 symbol 過濾（不帶 settleCoin）。"""
    c = _make_client()
    recorded = _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": []})),
    )
    c.get_active_orders("linear", symbol="BTCUSDT")
    params = dict(recorded[0].url.params)
    assert params.get("symbol") == "BTCUSDT"
    assert "settleCoin" not in params
    c.close()


# ---------------------------------------------------------------------------
# refresh_instruments (paginated)
# ---------------------------------------------------------------------------

def test_refresh_instruments_single_page():
    """Single page response → all symbols loaded, instrument_count() matches.
    單頁回應 → 全部載入，instrument_count() 對齊。"""
    c = _make_client()
    items = [
        {
            "symbol": "BTCUSDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "contractType": "LinearPerpetual",
            "lotSizeFilter": {
                "qtyStep": "0.001",
                "minOrderQty": "0.001",
                "maxOrderQty": "100",
                "minNotionalValue": "5",
            },
            "priceFilter": {"tickSize": "0.1", "minPrice": "0.1", "maxPrice": "999999"},
        },
        {
            "symbol": "ETHUSDT",
            "baseCoin": "ETH",
            "quoteCoin": "USDT",
            "contractType": "LinearPerpetual",
            "lotSizeFilter": {"qtyStep": "0.01", "minOrderQty": "0.01", "maxOrderQty": "10000"},
            "priceFilter": {"tickSize": "0.01", "minPrice": "0.01", "maxPrice": "99999"},
        },
    ]
    _install_mock_transport(
        c,
        lambda req: httpx.Response(
            200,
            json=_ok_envelope({"list": items, "nextPageCursor": ""}),
        ),
    )
    loaded = c.refresh_instruments("linear")
    assert loaded == 2
    assert c.instrument_count() == 2
    c.close()


def test_refresh_instruments_paginated():
    """Paginated response → client follows cursor until empty.
    分頁回應 → client 跟隨 cursor 直到為空。"""
    c = _make_client()
    pages = [
        {
            "list": [{
                "symbol": "BTCUSDT",
                "baseCoin": "BTC",
                "quoteCoin": "USDT",
                "contractType": "LinearPerpetual",
                "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "maxOrderQty": "100"},
                "priceFilter": {"tickSize": "0.1", "minPrice": "0.1", "maxPrice": "999999"},
            }],
            "nextPageCursor": "page2",
        },
        {
            "list": [{
                "symbol": "ETHUSDT",
                "baseCoin": "ETH",
                "quoteCoin": "USDT",
                "contractType": "LinearPerpetual",
                "lotSizeFilter": {"qtyStep": "0.01", "minOrderQty": "0.01", "maxOrderQty": "10000"},
                "priceFilter": {"tickSize": "0.01", "minPrice": "0.01", "maxPrice": "99999"},
            }],
            "nextPageCursor": "",
        },
    ]
    page_iter = iter(pages)

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_envelope(next(page_iter)))

    recorded = _install_mock_transport(c, _handler)
    loaded = c.refresh_instruments("linear")
    assert loaded == 2
    assert c.instrument_count() == 2
    # Second request must carry cursor=page2.
    # 第二次請求必須帶 cursor=page2。
    second_params = dict(recorded[1].url.params)
    assert second_params.get("cursor") == "page2"
    c.close()


# ---------------------------------------------------------------------------
# get_instrument + round_qty
# ---------------------------------------------------------------------------

def test_get_instrument_cache_hit_and_miss():
    """Cache hit returns dict; cache miss returns None.
    快取命中返回 dict；未命中返回 None。"""
    c = _make_client()
    items = [{
        "symbol": "BTCUSDT",
        "baseCoin": "BTC",
        "quoteCoin": "USDT",
        "contractType": "LinearPerpetual",
        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "maxOrderQty": "100"},
        "priceFilter": {"tickSize": "0.1", "minPrice": "0.1", "maxPrice": "999999"},
    }]
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": items, "nextPageCursor": ""})),
    )
    c.refresh_instruments("linear")
    spec = c.get_instrument("BTCUSDT")
    assert spec is not None
    assert spec["symbol"] == "BTCUSDT"
    assert spec["qty_step"] == pytest.approx(0.001)
    assert c.get_instrument("XXXUSDT") is None
    c.close()


def test_round_qty_floor_and_miss():
    """round_qty floors to qty_step; cache miss → None.
    round_qty 地板取整；未快取 → None。"""
    c = _make_client()
    items = [{
        "symbol": "BTCUSDT",
        "baseCoin": "BTC",
        "quoteCoin": "USDT",
        "contractType": "LinearPerpetual",
        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "maxOrderQty": "100"},
        "priceFilter": {"tickSize": "0.1", "minPrice": "0.1", "maxPrice": "999999"},
    }]
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": items, "nextPageCursor": ""})),
    )
    c.refresh_instruments("linear")

    assert c.round_qty("BTCUSDT", 0.0056) == pytest.approx(0.005)
    assert c.round_qty("BTCUSDT", 1.9999) == pytest.approx(1.999)
    assert c.round_qty("BTCUSDT", 0.0) == pytest.approx(0.0)
    # Cache miss.
    assert c.round_qty("UNKNOWN", 1.23) is None
    c.close()


def test_decimals_from_step_helper():
    """Step → decimal-place derivation.
    Step → 小數位數推導。"""
    assert _decimals_from_step(0.001) == 3
    assert _decimals_from_step(0.01) == 2
    assert _decimals_from_step(0.5) == 1
    assert _decimals_from_step(1.0) == 0
    assert _decimals_from_step(0.0) == 0


# ---------------------------------------------------------------------------
# place_order
# ---------------------------------------------------------------------------

def test_place_order_market_reduce_only_dual_shape():
    """place_order Market + reduce_only must send correct camelCase body and
    return a dict carrying BOTH snake_case and camelCase order id keys.
    place_order Market + reduce_only 必須送正確 camelCase body 並返回
    雙形狀（snake_case + camelCase）的 order id。"""
    c = _make_client()

    captured_body: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(req.content))
        return httpx.Response(
            200,
            json=_ok_envelope({"orderId": "ORDER-123", "orderLinkId": "LINK-456"}),
        )

    _install_mock_transport(c, _handler)
    resp = c.place_order(
        symbol="BTCUSDT",
        side="Buy",
        order_type="Market",
        qty=0.001,
        category="linear",
        reduce_only=True,
    )

    # Body uses camelCase (Bybit V5 spec).
    assert captured_body["category"] == "linear"
    assert captured_body["symbol"] == "BTCUSDT"
    assert captured_body["side"] == "Buy"
    assert captured_body["orderType"] == "Market"
    assert captured_body["qty"] == "0.001"
    assert captured_body["reduceOnly"] is True
    # Market default should NOT set timeInForce (Rust only defaults GTC on Limit).
    assert "timeInForce" not in captured_body

    # Response exposes BOTH shapes.
    # 回應暴露雙形狀。
    assert resp["order_id"] == "ORDER-123"
    assert resp["order_link_id"] == "LINK-456"
    assert resp["orderId"] == "ORDER-123"
    assert resp["orderLinkId"] == "LINK-456"
    c.close()


def test_place_order_limit_defaults_gtc_and_formats_price():
    """Limit order auto-sets timeInForce=GTC and formats price/qty.
    Limit 單自動設 timeInForce=GTC，格式化 price/qty。"""
    c = _make_client()
    captured_body: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(req.content))
        return httpx.Response(
            200,
            json=_ok_envelope({"orderId": "X", "orderLinkId": "Y"}),
        )

    _install_mock_transport(c, _handler)
    c.place_order(
        symbol="BTCUSDT",
        side="Sell",
        order_type="Limit",
        qty=0.01000000,
        category="linear",
        price=50000.50,
    )

    assert captured_body["orderType"] == "Limit"
    assert captured_body["timeInForce"] == "GTC"
    assert captured_body["price"] == "50000.5"
    assert captured_body["qty"] == "0.01"
    c.close()


def test_place_order_retcode_error():
    """place_order retCode != 0 raises BybitBusinessError.
    place_order retCode != 0 raise BybitBusinessError。"""
    c = _make_client()
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json={
            "retCode": 110007,
            "retMsg": "Available balance insufficient",
            "result": {},
            "time": 1,
        }),
    )
    with pytest.raises(BybitBusinessError) as exc_info:
        c.place_order(
            symbol="BTCUSDT", side="Buy", order_type="Market",
            qty=0.001, category="linear",
        )
    assert exc_info.value.ret_code == 110007
    c.close()


# ---------------------------------------------------------------------------
# get_executions
# ---------------------------------------------------------------------------

def test_get_executions_sends_linear_params_and_limit():
    """get_executions sends category=linear, limit=N, settleCoin=USDT.
    get_executions 發送 category=linear, limit=N, settleCoin=USDT。"""
    c = _make_client()
    recorded = _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": []})),
    )
    c.get_executions("linear", limit=25)
    params = dict(recorded[0].url.params)
    assert params.get("category") == "linear"
    assert params.get("limit") == "25"
    assert params.get("settleCoin") == "USDT"
    c.close()


def test_get_executions_returns_raw_rows():
    """Executions returned raw so _normalize_execution() can remap keys.
    成交原樣返回，讓 _normalize_execution() 可處理 camelCase 欄位。"""
    c = _make_client()
    rows = [{
        "execId": "E1",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "execPrice": "50000",
        "execQty": "0.001",
        "execValue": "50",
        "execFee": "0.03",
        "orderId": "O1",
        "orderLinkId": "L1",
        "execType": "Trade",
        "execTime": "1700000000000",
        "closedPnl": "1.5",
    }]
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": rows})),
    )
    out = c.get_executions("linear", limit=50)
    assert len(out) == 1
    assert out[0]["execQty"] == "0.001"
    assert out[0]["closedPnl"] == "1.5"
    c.close()


# ---------------------------------------------------------------------------
# cancel_order (drop-in compat for clean_restart_flatten.py)
# ---------------------------------------------------------------------------

def test_cancel_order_sends_order_id():
    """cancel_order sends orderId (camelCase) in JSON body.
    cancel_order 在 JSON body 中帶 orderId（camelCase）。"""
    c = _make_client()
    captured_body: dict[str, Any] = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(req.content))
        return httpx.Response(
            200,
            json=_ok_envelope({"orderId": "O1", "orderLinkId": "L1"}),
        )

    _install_mock_transport(c, _handler)
    resp = c.cancel_order("BTCUSDT", "O1", "linear")
    assert captured_body == {"category": "linear", "symbol": "BTCUSDT", "orderId": "O1"}
    assert resp["order_id"] == "O1"
    assert resp["orderId"] == "O1"
    c.close()


# ---------------------------------------------------------------------------
# Transport / parsing error paths
# ---------------------------------------------------------------------------

def test_transport_error_on_network_failure():
    """httpx.HTTPError → BybitTransportError with original wrapped.
    httpx.HTTPError → BybitTransportError 包裝原始例外。"""
    c = _make_client()

    def _handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    _install_mock_transport(c, _handler)
    with pytest.raises(BybitTransportError):
        c.refresh_balance()
    c.close()


def test_bad_json_body_raises_transport_error():
    """Non-JSON response body → BybitTransportError.
    非 JSON response body → BybitTransportError。"""
    c = _make_client()
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, content=b"not json"),
    )
    with pytest.raises(BybitTransportError):
        c.refresh_balance()
    c.close()


def test_missing_ret_code_raises_transport_error():
    """Response missing retCode → BybitTransportError.
    回應缺 retCode → BybitTransportError。"""
    c = _make_client()
    _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json={"result": {}}),
    )
    with pytest.raises(BybitTransportError):
        c.refresh_balance()
    c.close()


# ---------------------------------------------------------------------------
# Sanity: auth headers on every signed request
# ---------------------------------------------------------------------------

def test_signed_requests_carry_required_headers():
    """Every signed request carries X-BAPI-* headers.
    每次簽名請求帶齊 X-BAPI-* headers。"""
    c = _make_client()
    recorded = _install_mock_transport(
        c,
        lambda req: httpx.Response(200, json=_ok_envelope({"list": []})),
    )
    c.get_positions("linear")
    req = recorded[0]
    assert req.headers["X-BAPI-API-KEY"] == "TESTKEY"
    assert len(req.headers["X-BAPI-SIGN"]) == 64   # HMAC-SHA256 hex
    assert req.headers["X-BAPI-TIMESTAMP"].isdigit()
    assert req.headers["X-BAPI-RECV-WINDOW"] == "5000"
    c.close()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def test_format_number_trims_zeros_and_handles_zero():
    """_format_number trims trailing zeros and handles 0.0.
    _format_number 去尾零並處理 0.0。"""
    assert _format_number(0.001) == "0.001"
    assert _format_number(1.0) == "1"
    assert _format_number(0.0) == "0"
    assert _format_number(50000.5) == "50000.5"


def test_parse_instrument_item_none_on_missing_symbol():
    """_parse_instrument_item returns None when symbol missing.
    缺 symbol 時 _parse_instrument_item 返回 None。"""
    assert _parse_instrument_item({"lotSizeFilter": {}, "priceFilter": {}}) is None
    assert _parse_instrument_item({"symbol": "X"}) is None
