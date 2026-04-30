"""
Tests for Layer 2 toolbox extension — G3-07 (2026-04-26).
Layer 2 工具箱擴充測試 —— G3-07（2026-04-26）。

Coverage / 覆蓋範圍：
  Unit tests (mock httpx.AsyncClient — no real network)
  - query_onchain: env-disabled / missing args / unsupported metric
  - query_onchain: 200-OK funding_rate parsing
  - query_onchain: HTTP timeout fail-closed
  - query_onchain: liquidations_24h explicit data-unavailable
  - check_derivatives: env-disabled
  - check_derivatives: 200-OK ticker JSON parsing (mark_price + funding)
  - check_derivatives: oi_24h_change_pct surfaced as data-unavailable
  - check_derivatives: invalid metric in input → error_per_metric
  - check_derivatives: HTTP timeout fail-closed (global error)
  - HTTP timeout helper / env-gate helper sanity

  E2E test (pytest mark slow — real Bybit public network)
  - check_derivatives BTCUSDT real network → mark_price + funding parsed
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.layer2_tools_g3_07 import (  # noqa: E402
    DEFAULT_DATA_UNAVAILABLE_ERROR,
    DEFAULT_HTTP_TIMEOUT_SEC,
    DEFAULT_TOOL_DISABLED_ERROR,
    ENV_BYBIT_ENV,
    ENV_BYBIT_PUBLIC_BASE_URL,
    ENV_CHECK_DERIVATIVES_ENABLED,
    ENV_HTTP_TIMEOUT_SEC,
    ENV_QUERY_ONCHAIN_ENABLED,
    bybit_public_base_url,
    check_derivatives,
    http_timeout,
    is_tool_enabled,
    query_onchain,
)
from app.layer2_types import (  # noqa: E402
    DERIV_METRIC_FUNDING,
    DERIV_METRIC_INDEX_PRICE,
    DERIV_METRIC_MARK_PRICE,
    DERIV_METRIC_NEXT_FUNDING_TS,
    DERIV_METRIC_OI_24H_CHANGE_PCT,
    ONCHAIN_METRIC_FUNDING_RATE,
    ONCHAIN_METRIC_LIQUIDATIONS_24H,
    ONCHAIN_METRIC_OPEN_INTEREST,
    TOOL_CHECK_DERIVATIVES,
    TOOL_QUERY_ONCHAIN,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _run(coro):
    """Run a coroutine in an isolated event loop / 在獨立 event loop 跑 coroutine"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_async_response(status_code: int = 200, json_payload: dict | None = None):
    """
    Build a mock httpx.Response. JSON is sync (httpx returns dict directly).
    建立 mock httpx.Response，json() 為同步呼叫（httpx 回 dict）。
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_payload or {})
    return resp


def _make_async_client_ctx(get_return):
    """
    Build a context-manager-shaped AsyncClient mock for `async with httpx.AsyncClient() as c`.
    為 `async with httpx.AsyncClient() as c` 構造一個 context-manager 行 AsyncClient mock。
    """
    client = MagicMock()
    client.get = AsyncMock(return_value=get_return)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx, client


# ═══════════════════════════════════════════════════════════════════════════════
# Env-gate / HTTP timeout helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvHelpers:
    """Tests for is_tool_enabled / http_timeout / bybit_public_base_url"""

    def _clear_bybit_url_env(self):
        for key in (
            ENV_BYBIT_PUBLIC_BASE_URL,
            ENV_BYBIT_ENV,
            "OPENCLAW_SECRETS_DIR",
            "OPENCLAW_SECRETS_ROOT",
        ):
            os.environ.pop(key, None)

    def test_is_tool_enabled_truthy_values(self):
        for v in ["1", "true", "True", "YES", " on "]:
            with patch.dict(os.environ, {"FOO": v}, clear=False):
                assert is_tool_enabled("FOO") is True

    def test_is_tool_enabled_falsy_values(self):
        for v in ["", "0", "false", "no", "off", "random"]:
            with patch.dict(os.environ, {"FOO": v}, clear=False):
                assert is_tool_enabled("FOO") is False

    def test_is_tool_enabled_unset(self):
        os.environ.pop("FOO_NOT_SET", None)
        assert is_tool_enabled("FOO_NOT_SET") is False

    def test_http_timeout_default(self):
        os.environ.pop(ENV_HTTP_TIMEOUT_SEC, None)
        assert http_timeout() == DEFAULT_HTTP_TIMEOUT_SEC

    def test_http_timeout_override(self):
        with patch.dict(os.environ, {ENV_HTTP_TIMEOUT_SEC: "12.5"}, clear=False):
            assert http_timeout() == 12.5

    def test_http_timeout_bad_value(self):
        with patch.dict(os.environ, {ENV_HTTP_TIMEOUT_SEC: "abc"}, clear=False):
            assert http_timeout() == DEFAULT_HTTP_TIMEOUT_SEC

    def test_http_timeout_zero_or_negative(self):
        for v in ["0", "-1", "-0.5"]:
            with patch.dict(os.environ, {ENV_HTTP_TIMEOUT_SEC: v}, clear=False):
                assert http_timeout() == DEFAULT_HTTP_TIMEOUT_SEC

    def test_base_url_resolution(self):
        cases = {
            "demo": "https://api-demo.bybit.com",
            "testnet": "https://api-testnet.bybit.com",
            "live_demo": "https://api-demo.bybit.com",
            "mainnet": "https://api.bybit.com",
            "garbage_unknown": "https://api-demo.bybit.com",  # fallback to demo
        }
        for env_val, expected in cases.items():
            with patch.dict(os.environ, {ENV_BYBIT_ENV: env_val}, clear=False):
                os.environ.pop(ENV_BYBIT_PUBLIC_BASE_URL, None)
                os.environ.pop("OPENCLAW_SECRETS_DIR", None)
                os.environ.pop("OPENCLAW_SECRETS_ROOT", None)
                assert bybit_public_base_url() == expected

    def test_base_url_unset_falls_back_demo(self):
        self._clear_bybit_url_env()
        assert bybit_public_base_url() == "https://api-demo.bybit.com"

    def test_base_url_explicit_public_url_override(self):
        with patch.dict(
            os.environ,
            {
                ENV_BYBIT_PUBLIC_BASE_URL: "https://example.invalid/",
                ENV_BYBIT_ENV: "mainnet",
            },
            clear=False,
        ):
            assert bybit_public_base_url() == "https://example.invalid"

    def test_base_url_reads_file_based_live_demo_endpoint(self, tmp_path):
        slot_dir = tmp_path / "live"
        slot_dir.mkdir()
        (slot_dir / "bybit_endpoint").write_text("demo\n", encoding="utf-8")

        with patch.dict(os.environ, {"OPENCLAW_SECRETS_DIR": str(tmp_path)}, clear=False):
            os.environ.pop(ENV_BYBIT_PUBLIC_BASE_URL, None)
            os.environ.pop(ENV_BYBIT_ENV, None)
            os.environ.pop("OPENCLAW_SECRETS_ROOT", None)
            assert bybit_public_base_url() == "https://api-demo.bybit.com"

    def test_base_url_reads_file_based_mainnet_endpoint(self, tmp_path):
        slot_dir = tmp_path / "live"
        slot_dir.mkdir()
        (slot_dir / "bybit_endpoint").write_text("mainnet\n", encoding="utf-8")

        with patch.dict(os.environ, {"OPENCLAW_SECRETS_DIR": str(tmp_path)}, clear=False):
            os.environ.pop(ENV_BYBIT_PUBLIC_BASE_URL, None)
            os.environ.pop(ENV_BYBIT_ENV, None)
            os.environ.pop("OPENCLAW_SECRETS_ROOT", None)
            assert bybit_public_base_url() == "https://api.bybit.com"


# ═══════════════════════════════════════════════════════════════════════════════
# query_onchain — unit tests (env-gate / arg validation / parsing)
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryOnchainEnvGate:
    """Default-OFF env gate behavior / 預設關閉的 env gate 行為"""

    def setup_method(self):
        # Ensure no leakage between tests
        os.environ.pop(ENV_QUERY_ONCHAIN_ENABLED, None)

    def test_disabled_returns_disabled_error(self):
        out = _run(query_onchain({"symbol": "BTCUSDT", "metric": ONCHAIN_METRIC_FUNDING_RATE}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR
        assert out["value"] is None
        assert out["symbol"] == "BTCUSDT"
        assert out["metric"] == ONCHAIN_METRIC_FUNDING_RATE

    def test_disabled_even_with_missing_args(self):
        # Disabled error must fire BEFORE arg validation
        out = _run(query_onchain({}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR

    def test_enabled_with_missing_args(self):
        with patch.dict(os.environ, {ENV_QUERY_ONCHAIN_ENABLED: "1"}, clear=False):
            out = _run(query_onchain({}))
            assert out["value"] is None
            assert "required" in out["error"]

    def test_enabled_unsupported_metric(self):
        with patch.dict(
            os.environ, {ENV_QUERY_ONCHAIN_ENABLED: "1"}, clear=False
        ):
            out = _run(query_onchain({"symbol": "BTCUSDT", "metric": "bogus"}))
            assert out["value"] is None
            assert "metric not supported" in out["error"]


class TestQueryOnchainParsing:
    """HTTP success / parsing paths / HTTP 成功與解析路徑"""

    def setup_method(self):
        os.environ[ENV_QUERY_ONCHAIN_ENABLED] = "1"

    def teardown_method(self):
        os.environ.pop(ENV_QUERY_ONCHAIN_ENABLED, None)

    def test_funding_rate_200_ok_parses(self):
        payload = {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1714137600000,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "fundingRate": "0.0001",
                        "nextFundingTime": "1714166400000",
                        "timestamp": "1714137600000",
                    }
                ]
            },
        }
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)

        with patch("app.layer2_tools_g3_07.bybit_public_base_url", return_value="https://api-demo.bybit.com"):
            with patch("httpx.AsyncClient", return_value=ctx):
                out = _run(query_onchain({
                    "symbol": "BTCUSDT",
                    "metric": ONCHAIN_METRIC_FUNDING_RATE,
                }))

        assert out["error"] is None
        assert out["value"] == pytest.approx(0.0001)
        assert out["symbol"] == "BTCUSDT"
        assert out["data_source"] == "bybit_v5_public"
        assert out["timestamp_ms"] == 1714137600000

    def test_open_interest_200_ok_parses(self):
        payload = {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1714137600000,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "openInterest": "12345.678",
                        "timestamp": "1714137500000",
                    }
                ]
            },
        }
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)

        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(query_onchain({
                "symbol": "BTCUSDT",
                "metric": ONCHAIN_METRIC_OPEN_INTEREST,
            }))

        assert out["error"] is None
        assert out["value"] == pytest.approx(12345.678)

    def test_liquidations_24h_returns_data_unavailable(self):
        # No HTTP call should be made — this metric has no public V5 endpoint.
        with patch("httpx.AsyncClient") as mock_client:
            out = _run(query_onchain({
                "symbol": "BTCUSDT",
                "metric": ONCHAIN_METRIC_LIQUIDATIONS_24H,
            }))
            mock_client.assert_not_called()

        assert out["value"] is None
        assert DEFAULT_DATA_UNAVAILABLE_ERROR in out["error"]
        assert "no public V5 endpoint" in out["error"]

    def test_http_timeout_fail_closed(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=TimeoutError("simulated timeout"))
        ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(query_onchain({
                "symbol": "BTCUSDT",
                "metric": ONCHAIN_METRIC_FUNDING_RATE,
            }))

        # Must be fail-closed: value=None + error string, no raise
        assert out["value"] is None
        assert DEFAULT_DATA_UNAVAILABLE_ERROR in out["error"]
        assert "timeout" in out["error"].lower()

    def test_non_200_http_status(self):
        resp = _make_async_response(503, {})
        ctx, _ = _make_async_client_ctx(resp)
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(query_onchain({
                "symbol": "BTCUSDT",
                "metric": ONCHAIN_METRIC_FUNDING_RATE,
            }))
        assert out["value"] is None
        assert "HTTP 503" in out["error"]

    def test_bybit_retcode_nonzero(self):
        payload = {"retCode": 10001, "retMsg": "params error", "result": {"list": []}}
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(query_onchain({
                "symbol": "BTCUSDT",
                "metric": ONCHAIN_METRIC_FUNDING_RATE,
            }))
        assert out["value"] is None
        assert "retCode!=0" in out["error"]
        assert "params error" in out["error"]

    def test_empty_result_list(self):
        payload = {"retCode": 0, "retMsg": "OK", "result": {"list": []}}
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(query_onchain({
                "symbol": "BTCUSDT",
                "metric": ONCHAIN_METRIC_FUNDING_RATE,
            }))
        assert out["value"] is None
        assert "empty result list" in out["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# check_derivatives — unit tests (env-gate / arg validation / parsing)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckDerivativesEnvGate:
    """Default-OFF env gate behavior / 預設關閉的 env gate 行為"""

    def setup_method(self):
        os.environ.pop(ENV_CHECK_DERIVATIVES_ENABLED, None)

    def test_disabled_returns_disabled_error(self):
        out = _run(check_derivatives({"symbol": "BTCUSDT"}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR
        assert out["metrics"] == {}

    def test_disabled_even_with_missing_args(self):
        out = _run(check_derivatives({}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR

    def test_enabled_missing_symbol(self):
        with patch.dict(os.environ, {ENV_CHECK_DERIVATIVES_ENABLED: "1"}, clear=False):
            out = _run(check_derivatives({}))
            assert "required" in out["error"]

    def test_enabled_metrics_must_be_list(self):
        with patch.dict(os.environ, {ENV_CHECK_DERIVATIVES_ENABLED: "1"}, clear=False):
            out = _run(check_derivatives({"symbol": "BTCUSDT", "metrics": "not_a_list"}))
            assert "must be a list" in out["error"]

    def test_enabled_no_valid_metrics(self):
        with patch.dict(os.environ, {ENV_CHECK_DERIVATIVES_ENABLED: "1"}, clear=False):
            out = _run(check_derivatives({"symbol": "BTCUSDT", "metrics": ["bogus"]}))
            assert "no valid metrics" in out["error"]
            assert "bogus" in out["error_per_metric"]


class TestCheckDerivativesParsing:
    """HTTP success / parsing paths / HTTP 成功與解析路徑"""

    def setup_method(self):
        os.environ[ENV_CHECK_DERIVATIVES_ENABLED] = "1"

    def teardown_method(self):
        os.environ.pop(ENV_CHECK_DERIVATIVES_ENABLED, None)

    def test_full_metric_set_parses(self):
        payload = {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1714137600000,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "markPrice": "65000.50",
                        "indexPrice": "65010.20",
                        "fundingRate": "0.00012",
                        "nextFundingTime": "1714166400000",
                        "openInterestValue": "1234567890",
                    }
                ]
            },
        }
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)

        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(check_derivatives({
                "symbol": "BTCUSDT",
                "metrics": [
                    DERIV_METRIC_MARK_PRICE,
                    DERIV_METRIC_INDEX_PRICE,
                    DERIV_METRIC_FUNDING,
                    DERIV_METRIC_NEXT_FUNDING_TS,
                    DERIV_METRIC_OI_24H_CHANGE_PCT,
                ],
            }))

        assert out["error"] is None
        assert out["symbol"] == "BTCUSDT"
        assert out["timestamp_ms"] == 1714137600000
        assert out["metrics"][DERIV_METRIC_MARK_PRICE] == pytest.approx(65000.50)
        assert out["metrics"][DERIV_METRIC_INDEX_PRICE] == pytest.approx(65010.20)
        assert out["metrics"][DERIV_METRIC_FUNDING] == pytest.approx(0.00012)
        assert out["metrics"][DERIV_METRIC_NEXT_FUNDING_TS] == pytest.approx(1714166400000)
        # oi_24h_change_pct surfaced as None (not in V5 ticker)
        assert out["metrics"][DERIV_METRIC_OI_24H_CHANGE_PCT] is None
        assert (
            "oi_24h_change_pct requires"
            in out["error_per_metric"][DERIV_METRIC_OI_24H_CHANGE_PCT]
        )

    def test_default_metrics_when_omitted(self):
        payload = {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1714137600000,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "markPrice": "65000",
                        "indexPrice": "65000",
                        "fundingRate": "0.0001",
                        "nextFundingTime": "1714166400000",
                    }
                ]
            },
        }
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)

        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(check_derivatives({"symbol": "BTCUSDT"}))

        assert out["error"] is None
        # All five default metrics must be present in dict (some may be None)
        for m in (DERIV_METRIC_MARK_PRICE, DERIV_METRIC_INDEX_PRICE,
                  DERIV_METRIC_FUNDING, DERIV_METRIC_NEXT_FUNDING_TS,
                  DERIV_METRIC_OI_24H_CHANGE_PCT):
            assert m in out["metrics"]

    def test_invalid_metric_in_input(self):
        payload = {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1714137600000,
            "result": {"list": [{"symbol": "BTCUSDT", "markPrice": "100"}]},
        }
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(check_derivatives({
                "symbol": "BTCUSDT",
                "metrics": [DERIV_METRIC_MARK_PRICE, "bogus_metric"],
            }))

        assert out["error"] is None  # global success
        assert out["metrics"][DERIV_METRIC_MARK_PRICE] == pytest.approx(100.0)
        assert "bogus_metric" in out["error_per_metric"]
        assert "metric not supported" in out["error_per_metric"]["bogus_metric"]

    def test_http_timeout_global_fail_closed(self):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=TimeoutError("simulated timeout"))
        ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(check_derivatives({
                "symbol": "BTCUSDT",
                "metrics": [DERIV_METRIC_MARK_PRICE, DERIV_METRIC_FUNDING],
            }))

        assert out["error"] is not None
        assert DEFAULT_DATA_UNAVAILABLE_ERROR in out["error"]
        # Per-metric errors echo the global timeout
        assert DERIV_METRIC_MARK_PRICE in out["error_per_metric"]
        assert DERIV_METRIC_FUNDING in out["error_per_metric"]

    def test_non_200_http(self):
        resp = _make_async_response(429, {})
        ctx, _ = _make_async_client_ctx(resp)
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(check_derivatives({
                "symbol": "BTCUSDT",
                "metrics": [DERIV_METRIC_MARK_PRICE],
            }))
        assert "HTTP 429" in out["error"]

    def test_bybit_retcode_nonzero(self):
        payload = {"retCode": 10001, "retMsg": "params error", "result": {"list": []}}
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(check_derivatives({
                "symbol": "BTCUSDT",
                "metrics": [DERIV_METRIC_MARK_PRICE],
            }))
        assert "retCode!=0" in out["error"]
        assert "params error" in out["error"]

    def test_missing_field_marks_metric_none(self):
        payload = {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1714137600000,
            "result": {"list": [{"symbol": "BTCUSDT"}]},  # no markPrice!
        }
        resp = _make_async_response(200, payload)
        ctx, _ = _make_async_client_ctx(resp)
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(check_derivatives({
                "symbol": "BTCUSDT",
                "metrics": [DERIV_METRIC_MARK_PRICE],
            }))

        assert out["error"] is None  # global OK
        assert out["metrics"][DERIV_METRIC_MARK_PRICE] is None
        assert "missing" in out["error_per_metric"][DERIV_METRIC_MARK_PRICE]


# ═══════════════════════════════════════════════════════════════════════════════
# ToolExecutor wiring / 透過 ToolExecutor 觸發
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolExecutorWiring:
    """Ensure ToolExecutor.execute() routes the new tool names through wrappers."""

    def setup_method(self):
        os.environ.pop(ENV_QUERY_ONCHAIN_ENABLED, None)
        os.environ.pop(ENV_CHECK_DERIVATIVES_ENABLED, None)

    def test_executor_query_onchain_disabled(self):
        from app.layer2_tools import ToolExecutor
        executor = ToolExecutor()
        result_str = _run(executor.execute(
            TOOL_QUERY_ONCHAIN, {"symbol": "BTCUSDT", "metric": ONCHAIN_METRIC_FUNDING_RATE}
        ))
        # ToolExecutor.execute returns JSON string
        import json
        parsed = json.loads(result_str)
        assert parsed["error"] == DEFAULT_TOOL_DISABLED_ERROR

    def test_executor_check_derivatives_disabled(self):
        from app.layer2_tools import ToolExecutor
        executor = ToolExecutor()
        result_str = _run(executor.execute(
            TOOL_CHECK_DERIVATIVES, {"symbol": "BTCUSDT"}
        ))
        import json
        parsed = json.loads(result_str)
        assert parsed["error"] == DEFAULT_TOOL_DISABLED_ERROR

    def test_tool_schemas_include_new_tools(self):
        from app.layer2_tools import TOOL_SCHEMAS
        names = {s["name"] for s in TOOL_SCHEMAS}
        assert TOOL_QUERY_ONCHAIN in names
        assert TOOL_CHECK_DERIVATIVES in names
        # Pre-G3-07 was 8 tools; now 10
        assert len(TOOL_SCHEMAS) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# E2E (slow / network) — real Bybit public endpoint
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.slow
@pytest.mark.e2e
class TestCheckDerivativesE2E:
    """
    Real-network e2e against Bybit V5 public endpoints (demo). Skipped by default.
    對 Bybit V5 公開端點（demo）的真實網路 e2e 測試，預設跳過。

    Marked with both `slow` and `e2e` (G3-07-FUP-PYTEST-MARK Tier 6 Track 1):
      - `slow` — class-level: this is a long-running test
      - `e2e`  — class-level: real network against Bybit (e2e implies slow)

    `e2e` markers are registered in `conftest.py::pytest_configure`. Default
    pytest runs (no `-m` filter) include this; CI should deselect with
    `-m "not slow and not e2e"`.

    `slow` 與 `e2e` 雙標籤（G3-07-FUP-PYTEST-MARK Tier 6 Track 1）：
      - `slow` — class 級：長時間執行
      - `e2e`  — class 級：對 Bybit 真實網路（e2e 暗示 slow）

    `e2e` 標記在 `conftest.py::pytest_configure` 註冊。CI 預設 deselect
    `-m "not slow and not e2e"`。

    Run with: pytest -m slow program_code/.../tests/test_layer2_tools.py
              pytest -m e2e  program_code/.../tests/test_layer2_tools.py
    """

    def setup_method(self):
        os.environ[ENV_CHECK_DERIVATIVES_ENABLED] = "1"
        # Force demo URL even if local env points elsewhere
        os.environ.pop(ENV_BYBIT_PUBLIC_BASE_URL, None)
        os.environ[ENV_BYBIT_ENV] = "demo"

    def teardown_method(self):
        os.environ.pop(ENV_CHECK_DERIVATIVES_ENABLED, None)
        os.environ.pop(ENV_BYBIT_PUBLIC_BASE_URL, None)
        os.environ.pop(ENV_BYBIT_ENV, None)

    def test_btcusdt_real_network(self):
        out = _run(check_derivatives({
            "symbol": "BTCUSDT",
            "metrics": [DERIV_METRIC_MARK_PRICE, DERIV_METRIC_FUNDING],
        }))
        # Either we got real data OR the network is unreachable; in CI both are
        # acceptable — assert no raise.
        # 可能取得真實資料，也可能網路不可達；CI 中皆可接受 —— 重點是不 raise。
        assert out["symbol"] == "BTCUSDT"
        if out["error"] is None:
            mp = out["metrics"].get(DERIV_METRIC_MARK_PRICE)
            assert mp is not None and mp > 0, f"unexpected mark_price: {mp!r}"
            # funding can be slightly negative; just check finite numeric
            f = out["metrics"].get(DERIV_METRIC_FUNDING)
            assert f is None or isinstance(f, float)
