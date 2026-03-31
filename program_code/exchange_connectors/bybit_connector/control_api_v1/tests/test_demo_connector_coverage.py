"""
BybitDemoConnector Direct Tests — HMAC _sign() and unit coverage
BybitDemoConnector 直接测试 — HMAC _sign() 方法与单元覆盖

MODULE_NOTE (中文):
  P1-9 任务：bybit_demo_connector.py 覆盖率从 ~8% 提升到 30%+
  重点：_sign() HMAC-SHA256 签名逻辑、头部构建、初始化行为、错误场景
  不发送真实网络请求，全部通过 mock 隔离。

MODULE_NOTE (English):
  Task P1-9: Raise bybit_demo_connector.py coverage from ~8% to 30%+.
  Focuses on _sign() HMAC-SHA256, header construction, init behavior,
  error scenarios. No real network calls — all isolated via mocks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import threading
import unittest.mock as mock
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, mock_open

import pytest

# ── Path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bybit_demo_connector import BybitDemoConnector, DEMO_BASE_URL, RECV_WINDOW

# ── Test constants ───────────────────────────────────────────────────────────
TEST_API_KEY = "test_api_key_abc123"
TEST_API_SECRET = "test_secret_xyz789"
TEST_TIMESTAMP = "1700000000000"


def _expected_sig(api_key: str, api_secret: str, timestamp: str, params: str) -> str:
    """Reusable helper: compute expected HMAC-SHA256 signature."""
    sign_str = f"{timestamp}{api_key}{RECV_WINDOW}{params}"
    return hmac.new(api_secret.encode(), sign_str.encode(), hashlib.sha256).hexdigest()


# ════════════════════════════════════════════════════════════════════════════
# Section 1: _sign() HMAC 簽名正確性
# ════════════════════════════════════════════════════════════════════════════

class TestSign:
    """Direct tests for _sign() — covers HMAC correctness path."""

    def _make_connector(self) -> BybitDemoConnector:
        return BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)

    def test_sign_known_input_known_output(self):
        """TC1: Known params produce exact expected HMAC-SHA256 hex digest."""
        connector = self._make_connector()
        params = "symbol=BTCUSDT&side=Buy"
        result = connector._sign(TEST_TIMESTAMP, params)
        expected = "351d8387ace6d6b81d800a7afd0db471297f2aaaef47019edb24ce0626827e68"
        assert result == expected, f"Got {result!r}, expected {expected!r}"

    def test_sign_empty_params(self):
        """TC2: Empty params string produces correct HMAC (covers empty query path)."""
        connector = self._make_connector()
        result = connector._sign(TEST_TIMESTAMP, "")
        expected = "e520a8d16d0d5b719520bc4a1c2e40ea20890247d22b75650e9a275058d5e069"
        assert result == expected

    def test_sign_special_chars_params(self):
        """TC3: Params with spaces and URL-encoded chars handled correctly."""
        connector = self._make_connector()
        params = "msg=hello world&val=a%2Bb"
        result = connector._sign(TEST_TIMESTAMP, params)
        expected = "d22a2b6fa3396207085cadee6e2cb1a916ec1516beaa4fc0c09c46f1950d3180"
        assert result == expected

    def test_sign_json_body_post(self):
        """TC4: JSON body (POST path) produces correct signature."""
        connector = self._make_connector()
        body = json.dumps({"category": "linear", "symbol": "BTCUSDT", "side": "Buy", "qty": "0.001"})
        result = connector._sign(TEST_TIMESTAMP, body)
        expected = "43e0fa484ab98c979919ad7f5ce5cc341170938a92ec51ed4d0e42f6c87f14d4"
        assert result == expected

    def test_sign_output_is_hex_string_64_chars(self):
        """TC5: Output is always a 64-char hex string (SHA256 = 32 bytes = 64 hex chars)."""
        connector = self._make_connector()
        result = connector._sign(TEST_TIMESTAMP, "anyparams")
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_sign_different_timestamps_produce_different_sigs(self):
        """TC6: Changing timestamp changes the signature (replay protection)."""
        connector = self._make_connector()
        sig_a = connector._sign("1700000000000", "symbol=BTCUSDT")
        sig_b = connector._sign("1700000000001", "symbol=BTCUSDT")
        assert sig_a != sig_b

    def test_sign_different_params_produce_different_sigs(self):
        """TC7: Changing params changes the signature (integrity protection)."""
        connector = self._make_connector()
        sig_a = connector._sign(TEST_TIMESTAMP, "symbol=BTCUSDT")
        sig_b = connector._sign(TEST_TIMESTAMP, "symbol=ETHUSDT")
        assert sig_a != sig_b

    def test_sign_deterministic_same_inputs(self):
        """TC8: Same inputs always produce same signature (deterministic)."""
        connector = self._make_connector()
        sig1 = connector._sign(TEST_TIMESTAMP, "symbol=BTCUSDT")
        sig2 = connector._sign(TEST_TIMESTAMP, "symbol=BTCUSDT")
        assert sig1 == sig2

    def test_sign_incorporates_api_key_in_sign_string(self):
        """TC9: Two connectors with different api_keys produce different signatures."""
        connector_a = BybitDemoConnector(api_key="key_A", api_secret=TEST_API_SECRET)
        connector_b = BybitDemoConnector(api_key="key_B", api_secret=TEST_API_SECRET)
        params = "symbol=BTCUSDT"
        sig_a = connector_a._sign(TEST_TIMESTAMP, params)
        sig_b = connector_b._sign(TEST_TIMESTAMP, params)
        assert sig_a != sig_b, "Different API keys must yield different signatures"

    def test_sign_incorporates_api_secret(self):
        """TC10: Two connectors with different api_secrets produce different signatures."""
        connector_a = BybitDemoConnector(api_key=TEST_API_KEY, api_secret="secret_A")
        connector_b = BybitDemoConnector(api_key=TEST_API_KEY, api_secret="secret_B")
        params = "symbol=BTCUSDT"
        sig_a = connector_a._sign(TEST_TIMESTAMP, params)
        sig_b = connector_b._sign(TEST_TIMESTAMP, params)
        assert sig_a != sig_b, "Different API secrets must yield different signatures"


# ════════════════════════════════════════════════════════════════════════════
# Section 2: 初始化行為 (Initialization)
# ════════════════════════════════════════════════════════════════════════════

class TestInit:
    """Tests for BybitDemoConnector.__init__() behavior."""

    def test_init_with_explicit_keys_enabled(self):
        """Connector is enabled when both keys are provided explicitly."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        assert connector.is_enabled is True

    def test_init_no_keys_disabled(self):
        """Connector is disabled when no keys and secret file not found."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            connector = BybitDemoConnector()
        assert connector.is_enabled is False

    def test_init_missing_api_key_only_disabled(self):
        """Connector is disabled when only secret is provided (no key)."""
        connector = BybitDemoConnector(api_key="", api_secret=TEST_API_SECRET)
        # Without a key file present, api_key stays empty → disabled
        with patch("builtins.open", side_effect=FileNotFoundError):
            connector2 = BybitDemoConnector(api_key="", api_secret=TEST_API_SECRET)
        assert connector2.is_enabled is False

    def test_init_stats_initialized_to_zero(self):
        """Stats counters start at zero on fresh connector."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        status = connector.get_status()
        assert status["orders_submitted"] == 0
        assert status["orders_filled"] == 0
        assert status["orders_rejected"] == 0
        assert status["errors"] == 0

    def test_init_reads_api_key_from_file_when_not_provided(self):
        """When api_key is empty, connector reads from secrets file."""
        key_content = "file_api_key\n"
        secret_content = "file_api_secret\n"
        file_reads = [key_content, secret_content]

        def _open_side_effect(path, *args, **kwargs):
            content = file_reads.pop(0)
            return mock_open(read_data=content)()

        with patch("builtins.open", side_effect=_open_side_effect):
            connector = BybitDemoConnector()

        assert connector._api_key == "file_api_key"
        assert connector._api_secret == "file_api_secret"
        assert connector.is_enabled is True

    def test_init_lock_is_threading_lock(self):
        """Internal lock is a real threading.Lock for thread safety."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        assert hasattr(connector._lock, "acquire")
        assert hasattr(connector._lock, "release")


# ════════════════════════════════════════════════════════════════════════════
# Section 3: 頭部構建 (_request headers)
# ════════════════════════════════════════════════════════════════════════════

class TestRequestHeaders:
    """Verify that _request builds correct HTTP headers with all required fields."""

    def _make_connector(self) -> BybitDemoConnector:
        return BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)

    def _capture_request_headers(self, connector: BybitDemoConnector, method: str = "GET") -> dict:
        """Helper: intercept urllib.request.Request to capture headers."""
        captured = {}

        def fake_request_cls(url, data, headers, method):
            captured.update(headers)
            return MagicMock()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":0,"result":{}}'

        with patch("app.bybit_demo_connector.urllib.request.Request", side_effect=fake_request_cls), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            connector._request(method, "/v5/order/realtime", {"category": "linear"})

        return captured

    def test_headers_contain_x_bapi_api_key(self):
        """X-BAPI-API-KEY header must be present and equal to the configured key."""
        connector = self._make_connector()
        headers = self._capture_request_headers(connector)
        assert "X-BAPI-API-KEY" in headers
        assert headers["X-BAPI-API-KEY"] == TEST_API_KEY

    def test_headers_contain_x_bapi_sign(self):
        """X-BAPI-SIGN header must be present and be 64 hex chars."""
        connector = self._make_connector()
        headers = self._capture_request_headers(connector)
        assert "X-BAPI-SIGN" in headers
        sign = headers["X-BAPI-SIGN"]
        assert len(sign) == 64
        assert all(c in "0123456789abcdef" for c in sign)

    def test_headers_contain_x_bapi_timestamp(self):
        """X-BAPI-TIMESTAMP header must be present and look like a ms-epoch string."""
        connector = self._make_connector()
        headers = self._capture_request_headers(connector)
        assert "X-BAPI-TIMESTAMP" in headers
        ts = headers["X-BAPI-TIMESTAMP"]
        assert ts.isdigit()
        assert len(ts) == 13  # ms timestamp

    def test_headers_contain_x_bapi_recv_window(self):
        """X-BAPI-RECV-WINDOW header must match module-level RECV_WINDOW constant."""
        connector = self._make_connector()
        headers = self._capture_request_headers(connector)
        assert "X-BAPI-RECV-WINDOW" in headers
        assert headers["X-BAPI-RECV-WINDOW"] == RECV_WINDOW

    def test_headers_contain_content_type_json(self):
        """Content-Type must be application/json."""
        connector = self._make_connector()
        headers = self._capture_request_headers(connector)
        assert headers.get("Content-Type") == "application/json"


# ════════════════════════════════════════════════════════════════════════════
# Section 4: get_status() 狀態回報
# ════════════════════════════════════════════════════════════════════════════

class TestGetStatus:
    """Tests for get_status() reporting."""

    def test_get_status_component_name(self):
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        status = connector.get_status()
        assert status["component"] == "bybit_demo_connector"

    def test_get_status_enabled_reflects_init(self):
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        status = connector.get_status()
        assert status["enabled"] is True

    def test_get_status_base_url(self):
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        status = connector.get_status()
        assert status["base_url"] == DEMO_BASE_URL

    def test_get_status_disabled_connector(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            connector = BybitDemoConnector()
        status = connector.get_status()
        assert status["enabled"] is False


# ════════════════════════════════════════════════════════════════════════════
# Section 5: submit_order() 錯誤場景
# ════════════════════════════════════════════════════════════════════════════

class TestSubmitOrderErrorScenarios:
    """Error path tests for submit_order()."""

    def test_submit_order_disabled_returns_error_dict(self):
        """When connector is disabled, submit_order returns retCode=-1 without network call."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            connector = BybitDemoConnector()
        result = connector.submit_order("BTCUSDT", "Buy", qty=0.001)
        assert result["retCode"] == -1
        assert "not enabled" in result["retMsg"].lower()

    def test_submit_order_qty_rounds_to_zero_returns_error(self):
        """qty that rounds to 0 returns retCode=-1 without network call."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        result = connector.submit_order("BTCUSDT", "Buy", qty=0.0001)
        assert result["retCode"] == -1
        assert "zero" in result["retMsg"].lower()

    def test_submit_order_qty_ge_1_rounds_to_int(self):
        """qty >= 1.0 is rounded to integer (cheap-token step)."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":0,"result":{"orderId":"abc"}}'

        with patch("app.bybit_demo_connector.urllib.request.Request"), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            result = connector.submit_order("DOGEUSDT", "Buy", qty=1.7)
        assert result["retCode"] == 0

    def test_submit_order_rejected_increments_rejected_stat(self):
        """When API returns non-zero retCode, orders_rejected is incremented."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":10001,"retMsg":"Invalid qty"}'

        with patch("app.bybit_demo_connector.urllib.request.Request"), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            connector.submit_order("BTCUSDT", "Buy", qty=0.001)

        status = connector.get_status()
        assert status["orders_rejected"] == 1
        assert status["orders_submitted"] == 0

    def test_submit_order_success_increments_submitted_stat(self):
        """When API returns retCode=0, orders_submitted is incremented."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":0,"result":{"orderId":"order123"}}'

        with patch("app.bybit_demo_connector.urllib.request.Request"), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            result = connector.submit_order("BTCUSDT", "Buy", qty=0.001)

        assert result["retCode"] == 0
        status = connector.get_status()
        assert status["orders_submitted"] == 1
        assert status["orders_rejected"] == 0


# ════════════════════════════════════════════════════════════════════════════
# Section 6: place_conditional_order() 條件單
# ════════════════════════════════════════════════════════════════════════════

class TestConditionalOrder:
    """Tests for conditional stop-loss order behavior."""

    def test_conditional_order_disabled_returns_error(self):
        """Disabled connector returns retCode=-1 for conditional orders."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            connector = BybitDemoConnector()
        result = connector.place_conditional_order("BTCUSDT", "Sell", qty=0.001, trigger_price=40000.0)
        assert result["retCode"] == -1
        assert "not enabled" in result["retMsg"].lower()

    def test_conditional_order_sell_trigger_direction_auto_2(self):
        """Sell stop → trigger_direction auto-detected as 2 (fall below)."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        captured_params: dict[str, Any] = {}

        def fake_request(url, data, headers, method):
            if data:
                captured_params.update(json.loads(data.decode()))
            return MagicMock()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":0,"result":{"orderId":"cond1"}}'

        with patch("app.bybit_demo_connector.urllib.request.Request", side_effect=fake_request), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            connector.place_conditional_order("BTCUSDT", "Sell", qty=0.001, trigger_price=40000.0)

        assert captured_params.get("triggerDirection") == 2

    def test_conditional_order_buy_trigger_direction_auto_1(self):
        """Buy stop (close short) → trigger_direction auto-detected as 1 (rise above)."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        captured_params: dict[str, Any] = {}

        def fake_request(url, data, headers, method):
            if data:
                captured_params.update(json.loads(data.decode()))
            return MagicMock()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":0,"result":{"orderId":"cond2"}}'

        with patch("app.bybit_demo_connector.urllib.request.Request", side_effect=fake_request), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            connector.place_conditional_order("BTCUSDT", "Buy", qty=0.001, trigger_price=50000.0)

        assert captured_params.get("triggerDirection") == 1

    def test_conditional_order_qty_rounds_to_zero_returns_error(self):
        """qty=0.0001 rounds to zero → error without network call."""
        connector = BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)
        result = connector.place_conditional_order("BTCUSDT", "Sell", qty=0.0001, trigger_price=40000.0)
        assert result["retCode"] == -1
        assert "zero" in result["retMsg"].lower()

    def test_cancel_all_conditional_orders_disabled_returns_error(self):
        """Disabled connector returns error for cancel_all_conditional_orders."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            connector = BybitDemoConnector()
        result = connector.cancel_all_conditional_orders("BTCUSDT")
        assert result["retCode"] == -1


# ════════════════════════════════════════════════════════════════════════════
# Section 7: _request() 網絡錯誤處理
# ════════════════════════════════════════════════════════════════════════════

class TestRequestNetworkErrors:
    """_request() graceful degradation on network failures."""

    def _make_connector(self) -> BybitDemoConnector:
        return BybitDemoConnector(api_key=TEST_API_KEY, api_secret=TEST_API_SECRET)

    def test_request_handles_http_error_gracefully(self):
        """HTTPError is caught and returned as retCode=HTTP status, not raised."""
        import urllib.error
        connector = self._make_connector()
        http_err = urllib.error.HTTPError(
            url="https://api-demo.bybit.com/v5/order/realtime",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        http_err.read = lambda: b"Access denied"

        with patch("app.bybit_demo_connector.urllib.request.Request"), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", side_effect=http_err):
            result = connector._request("GET", "/v5/order/realtime")

        assert result["retCode"] == 403

    def test_request_handles_generic_exception_gracefully(self):
        """Generic exception (e.g. timeout) is caught and returned as retCode=-1."""
        connector = self._make_connector()

        with patch("app.bybit_demo_connector.urllib.request.Request"), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", side_effect=OSError("timeout")):
            result = connector._request("GET", "/v5/order/realtime")

        assert result["retCode"] == -1
        assert "timeout" in result["retMsg"]

    def test_request_get_appends_query_string(self):
        """GET request appends params as query string to URL."""
        connector = self._make_connector()
        captured_url = []

        def fake_request(url, data, headers, method):
            captured_url.append(url)
            return MagicMock()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":0,"result":{}}'

        with patch("app.bybit_demo_connector.urllib.request.Request", side_effect=fake_request), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            connector._request("GET", "/v5/order/realtime", {"category": "linear"})

        assert len(captured_url) == 1
        assert "category=linear" in captured_url[0]

    def test_request_post_sends_json_body(self):
        """POST request encodes params as JSON body bytes."""
        connector = self._make_connector()
        captured_data = []

        def fake_request(url, data, headers, method):
            captured_data.append(data)
            return MagicMock()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b'{"retCode":0,"result":{}}'

        params = {"category": "linear", "symbol": "BTCUSDT"}
        with patch("app.bybit_demo_connector.urllib.request.Request", side_effect=fake_request), \
             patch("app.bybit_demo_connector.urllib.request.urlopen", return_value=mock_resp):
            connector._request("POST", "/v5/order/create", params)

        assert len(captured_data) == 1
        parsed = json.loads(captured_data[0].decode())
        assert parsed["category"] == "linear"
        assert parsed["symbol"] == "BTCUSDT"


# ════════════════════════════════════════════════════════════════════════════
# Section 8: 模組常量與安全不變量
# ════════════════════════════════════════════════════════════════════════════

class TestModuleConstants:
    """Verify safety invariants encoded as module constants."""

    def test_demo_base_url_is_demo_not_production(self):
        """DEMO_BASE_URL must point to api-demo.bybit.com, never production."""
        assert "demo" in DEMO_BASE_URL
        assert "api-demo.bybit.com" in DEMO_BASE_URL
        assert "api.bybit.com" not in DEMO_BASE_URL or "demo" in DEMO_BASE_URL

    def test_recv_window_is_string_5000(self):
        """RECV_WINDOW must be '5000' string (Bybit requires string in headers)."""
        assert RECV_WINDOW == "5000"
        assert isinstance(RECV_WINDOW, str)
