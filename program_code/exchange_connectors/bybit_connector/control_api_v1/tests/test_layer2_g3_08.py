"""
Tests for Layer 2 microstructure toolbox — G3-08 (2026-06-05).
Layer 2 微結構工具箱測試 —— G3-08（2026-06-05）。

涵蓋（mock-only：patch httpx / db_pool.get_pg_conn，不碰真網路 / 真 PG）：
  get_orderbook    — env-gate OFF（預設關閉）/ missing symbol / depth clamp /
                     200-OK 解析（spread_bps + imbalance）/ HTTP 非 200 / retCode!=0 /
                     transport 例外 fail-closed / 空盤面。
  get_cvd          — DEFAULT-ON / 顯式關閉 / window_bars clamp / 空 rows 合法（零值）/
                     PG 不可用 fail-closed / SQL 聚合 shape。
  get_liquidations — DEFAULT-ON / 顯式關閉 / window_minutes clamp / 空 rows 合法 /
                     PG 不可用 fail-closed / 依 side 聚合 + 未知 side 不歸買賣。
  reachability     — 三工具皆可經 ToolExecutor.execute() 觸發、且在 TOOL_SCHEMAS 內
                     （直接守住 FIX 1 不回歸）；depth→limit 橋接生效。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import layer2_tools_g3_08 as g3_08  # noqa: E402
from app.layer2_tools_g3_08 import (  # noqa: E402
    DEFAULT_CVD_WINDOW_BARS,
    DEFAULT_LIQ_WINDOW_MINUTES,
    DEFAULT_ORDERBOOK_DEPTH,
    MAX_CVD_WINDOW_BARS,
    MAX_LIQ_WINDOW_MINUTES,
    MAX_ORDERBOOK_DEPTH,
    get_cvd,
    get_liquidations,
    get_orderbook,
)
from app.layer2_tools_g3_07 import DEFAULT_TOOL_DISABLED_ERROR  # noqa: E402
from app.layer2_types import (  # noqa: E402
    ENV_L2_TOOL_CVD_ENABLED,
    ENV_L2_TOOL_LIQUIDATIONS_ENABLED,
    ENV_L2_TOOL_ORDERBOOK_ENABLED,
    TOOL_GET_CVD,
    TOOL_GET_LIQUIDATIONS,
    TOOL_GET_ORDERBOOK,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_resp(status_code: int = 200, json_payload: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_payload or {})
    return resp


def _make_client_ctx(get_return=None, get_side_effect=None):
    """`async with httpx.AsyncClient() as c` 的 mock。"""
    client = MagicMock()
    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    else:
        client.get = AsyncMock(return_value=get_return)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx, client


def _mock_pg(rows, raise_on_execute: Exception | None = None, conn_is_none: bool = False):
    """
    Patch g3_08.db_pool.get_pg_conn → context manager 回 conn（或 None）。
    rows = fetchall() 結果；raise_on_execute 設定時 cursor.execute 拋例外。
    """
    cur = MagicMock()
    if raise_on_execute is not None:
        cur.execute = MagicMock(side_effect=raise_on_execute)
    else:
        cur.execute = MagicMock()
    cur.fetchall = MagicMock(return_value=rows)
    conn = MagicMock()
    conn.cursor.return_value = cur
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=None if conn_is_none else conn)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, cur


def _dt(epoch_offset_secs: float = 0.0) -> datetime:
    """構造 timezone-aware datetime（now + offset），供 freshness 計算。"""
    import time as _t
    return datetime.fromtimestamp(_t.time() + epoch_offset_secs, tz=timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# get_orderbook — 外部 Bybit 公開端點，預設關閉，fail-closed
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetOrderbookEnvGate:
    def setup_method(self):
        os.environ.pop(ENV_L2_TOOL_ORDERBOOK_ENABLED, None)

    def teardown_method(self):
        os.environ.pop(ENV_L2_TOOL_ORDERBOOK_ENABLED, None)

    def test_disabled_by_default(self):
        out = _run(get_orderbook({"symbol": "BTCUSDT"}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR
        assert out["bids"] == [] and out["asks"] == []

    def test_disabled_before_arg_validation(self):
        # 即使 symbol 缺失，關閉錯誤也應先觸發（不洩漏輸入回顯）。
        out = _run(get_orderbook({}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR

    def test_enabled_missing_symbol(self):
        with patch.dict(os.environ, {ENV_L2_TOOL_ORDERBOOK_ENABLED: "1"}, clear=False):
            out = _run(get_orderbook({}))
            assert "symbol is required" in out["error"]


class TestGetOrderbookParsing:
    def setup_method(self):
        os.environ[ENV_L2_TOOL_ORDERBOOK_ENABLED] = "1"

    def teardown_method(self):
        os.environ.pop(ENV_L2_TOOL_ORDERBOOK_ENABLED, None)

    def _ok_payload(self):
        return {
            "retCode": 0,
            "retMsg": "OK",
            "time": 1714137600000,
            "result": {
                "b": [["65000.0", "1.0"], ["64999.0", "2.0"]],
                "a": [["65001.0", "1.0"], ["65002.0", "3.0"]],
                "ts": 1714137600500,
            },
        }

    def test_200_ok_parses_spread_and_imbalance(self):
        ctx, client = _make_client_ctx(get_return=_make_resp(200, self._ok_payload()))
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(get_orderbook({"symbol": "BTCUSDT", "limit": 2}))
        assert out["error"] is None
        assert out["bids"][0] == [65000.0, 1.0]
        assert out["asks"][0] == [65001.0, 1.0]
        # spread = (65001-65000)/mid*1e4；mid≈65000.5
        assert out["bid_ask_spread_bps"] == pytest.approx(0.1538, abs=1e-3)
        # imbalance = sum_bid/(sum_bid+sum_ask) = 3/(3+4) = 0.428571
        assert out["bid_imbalance_ratio"] == pytest.approx(3.0 / 7.0, abs=1e-5)
        assert out["ts_ms"] == 1714137600500

    def test_depth_clamped_to_max(self):
        # 超界 depth（999）必須被收斂到 25；驗證傳給 HTTP 的 limit 參數。
        ctx, client = _make_client_ctx(get_return=_make_resp(200, self._ok_payload()))
        with patch("httpx.AsyncClient", return_value=ctx):
            _run(get_orderbook({"symbol": "BTCUSDT", "limit": 999}))
        _, kwargs = client.get.call_args
        assert kwargs["params"]["limit"] == MAX_ORDERBOOK_DEPTH

    def test_depth_default_when_absent(self):
        ctx, client = _make_client_ctx(get_return=_make_resp(200, self._ok_payload()))
        with patch("httpx.AsyncClient", return_value=ctx):
            _run(get_orderbook({"symbol": "BTCUSDT"}))
        _, kwargs = client.get.call_args
        assert kwargs["params"]["limit"] == DEFAULT_ORDERBOOK_DEPTH

    def test_non_200_fail_closed(self):
        ctx, _ = _make_client_ctx(get_return=_make_resp(503, {}))
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(get_orderbook({"symbol": "BTCUSDT"}))
        assert "HTTP 503" in out["error"]
        assert out["bids"] == []

    def test_retcode_nonzero_fail_closed(self):
        payload = {"retCode": 10001, "retMsg": "bad", "result": {}}
        ctx, _ = _make_client_ctx(get_return=_make_resp(200, payload))
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(get_orderbook({"symbol": "BTCUSDT"}))
        assert "retCode!=0" in out["error"]

    def test_transport_exception_fail_closed(self):
        ctx, _ = _make_client_ctx(get_side_effect=TimeoutError("net down"))
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(get_orderbook({"symbol": "BTCUSDT"}))
        # fail-closed：error string + 空盤面，不 raise。
        assert out["error"] is not None and "data unavailable" in out["error"]
        assert out["bids"] == [] and out["asks"] == []

    def test_empty_side_marks_unavailable(self):
        payload = {"retCode": 0, "result": {"b": [], "a": [["1", "1"]]}, "time": 1}
        ctx, _ = _make_client_ctx(get_return=_make_resp(200, payload))
        with patch("httpx.AsyncClient", return_value=ctx):
            out = _run(get_orderbook({"symbol": "BTCUSDT"}))
        assert "empty orderbook side" in out["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# get_cvd — 本地 PG，預設開啟，fail-closed
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetCvdEnvGate:
    def setup_method(self):
        os.environ.pop(ENV_L2_TOOL_CVD_ENABLED, None)

    def teardown_method(self):
        os.environ.pop(ENV_L2_TOOL_CVD_ENABLED, None)

    def test_default_on_when_unset(self):
        # 未設旗標 → 開啟 → 走 PG（這裡給空 rows，回零值合法）。
        cm, _ = _mock_pg(rows=[])
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_cvd({"symbol": "BTCUSDT"}))
        assert out["error"] is None
        assert out["cvd"] == 0.0

    def test_explicit_disable(self):
        with patch.dict(os.environ, {ENV_L2_TOOL_CVD_ENABLED: "0"}, clear=False):
            out = _run(get_cvd({"symbol": "BTCUSDT"}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR

    def test_enabled_missing_symbol(self):
        out = _run(get_cvd({}))
        assert "symbol is required" in out["error"]


class TestGetCvdQuery:
    def setup_method(self):
        os.environ.pop(ENV_L2_TOOL_CVD_ENABLED, None)

    def test_empty_rows_is_legal_zeros(self):
        cm, _ = _mock_pg(rows=[])
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_cvd({"symbol": "BTCUSDT"}))
        # 零筆 = 合法：error=None、cvd/buy/sell 皆 0、bars=0。
        assert out["error"] is None
        assert out["cvd"] == 0.0 and out["buy_volume"] == 0.0 and out["sell_volume"] == 0.0
        assert out["bars"] == 0

    def test_aggregates_buy_minus_sell(self):
        # rows 按 ts DESC：(ts, buy, sell)。cvd = sum(buy)-sum(sell)。
        rows = [
            (_dt(-30), 10.0, 4.0),
            (_dt(-90), 5.0, 6.0),
        ]
        cm, _ = _mock_pg(rows=rows)
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_cvd({"symbol": "BTCUSDT"}))
        assert out["error"] is None
        assert out["buy_volume"] == pytest.approx(15.0)
        assert out["sell_volume"] == pytest.approx(10.0)
        assert out["cvd"] == pytest.approx(5.0)
        assert out["bars"] == 2
        assert out["freshness_secs"] is not None and out["freshness_secs"] >= 0

    def test_window_bars_clamped(self):
        rows: list = []
        cm, cur = _mock_pg(rows=rows)
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            _run(get_cvd({"symbol": "BTCUSDT", "window_bars": 9999}))
        # 第二個 bind 參數（LIMIT）必須被夾到 MAX。
        args, _ = cur.execute.call_args
        params = args[1]
        assert params[1] == MAX_CVD_WINDOW_BARS

    def test_pg_unavailable_fail_closed(self):
        cm, _ = _mock_pg(rows=[], conn_is_none=True)
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_cvd({"symbol": "BTCUSDT"}))
        assert out["error"] is not None and "PG unavailable" in out["error"]
        assert out["cvd"] == 0.0

    def test_query_exception_fail_closed(self):
        cm, _ = _mock_pg(rows=[], raise_on_execute=RuntimeError("relation missing"))
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_cvd({"symbol": "BTCUSDT"}))
        assert out["error"] is not None and "data unavailable" in out["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# get_liquidations — 本地 PG，預設開啟，fail-closed
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetLiquidationsEnvGate:
    def setup_method(self):
        os.environ.pop(ENV_L2_TOOL_LIQUIDATIONS_ENABLED, None)

    def teardown_method(self):
        os.environ.pop(ENV_L2_TOOL_LIQUIDATIONS_ENABLED, None)

    def test_default_on_when_unset(self):
        cm, _ = _mock_pg(rows=[])
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_liquidations({"symbol": "BTCUSDT"}))
        assert out["error"] is None
        assert out["net_liq_qty"] == 0.0

    def test_explicit_disable(self):
        with patch.dict(os.environ, {ENV_L2_TOOL_LIQUIDATIONS_ENABLED: "off"}, clear=False):
            out = _run(get_liquidations({"symbol": "BTCUSDT"}))
        assert out["error"] == DEFAULT_TOOL_DISABLED_ERROR

    def test_enabled_missing_symbol(self):
        out = _run(get_liquidations({}))
        assert "symbol is required" in out["error"]


class TestGetLiquidationsQuery:
    def setup_method(self):
        os.environ.pop(ENV_L2_TOOL_LIQUIDATIONS_ENABLED, None)

    def test_empty_rows_is_legal_zeros(self):
        cm, _ = _mock_pg(rows=[])
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_liquidations({"symbol": "BTCUSDT"}))
        assert out["error"] is None
        assert out["buy_liq_qty"] == 0.0 and out["sell_liq_qty"] == 0.0
        assert out["buy_liq_count"] == 0 and out["sell_liq_count"] == 0
        assert out["net_liq_qty"] == 0.0

    def test_aggregates_by_side(self):
        # rows: (side, sum_qty, cnt, max_qty, oldest_ts, newest_ts)
        rows = [
            ("Buy", 12.0, 3, 8.0, _dt(-200), _dt(-30)),
            ("Sell", 5.0, 2, 4.0, _dt(-180), _dt(-60)),
        ]
        cm, _ = _mock_pg(rows=rows)
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_liquidations({"symbol": "BTCUSDT"}))
        assert out["error"] is None
        assert out["buy_liq_qty"] == pytest.approx(12.0)
        assert out["sell_liq_qty"] == pytest.approx(5.0)
        assert out["buy_liq_count"] == 3 and out["sell_liq_count"] == 2
        assert out["net_liq_qty"] == pytest.approx(7.0)
        assert out["largest_single_qty"] == pytest.approx(8.0)

    def test_unknown_side_not_counted_in_buy_sell(self):
        # 未知 side（如歷史髒資料 'liquidation'）不歸入買賣，但仍計 largest。
        rows = [
            ("Buy", 3.0, 1, 3.0, _dt(-100), _dt(-50)),
            ("weird", 99.0, 1, 99.0, _dt(-120), _dt(-40)),
        ]
        cm, _ = _mock_pg(rows=rows)
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_liquidations({"symbol": "BTCUSDT"}))
        assert out["buy_liq_qty"] == pytest.approx(3.0)
        assert out["sell_liq_qty"] == 0.0
        # 未知 side 不進買賣，但 largest 仍反映 99。
        assert out["largest_single_qty"] == pytest.approx(99.0)

    def test_window_minutes_clamped(self):
        cm, cur = _mock_pg(rows=[])
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            _run(get_liquidations({"symbol": "BTCUSDT", "window_minutes": 9999}))
        args, _ = cur.execute.call_args
        params = args[1]
        # 第二個 bind 參數 = window_minutes(clamped to 60) * 60 秒。
        assert params[1] == MAX_LIQ_WINDOW_MINUTES * 60

    def test_pg_unavailable_fail_closed(self):
        cm, _ = _mock_pg(rows=[], conn_is_none=True)
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_liquidations({"symbol": "BTCUSDT"}))
        assert out["error"] is not None and "PG unavailable" in out["error"]

    def test_query_exception_fail_closed(self):
        cm, _ = _mock_pg(rows=[], raise_on_execute=RuntimeError("relation missing"))
        with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
            out = _run(get_liquidations({"symbol": "BTCUSDT"}))
        assert out["error"] is not None and "data unavailable" in out["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# Reachability via public dispatch — 直接守住 FIX 1（dead-import 回歸防護）
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolDispatchReachability:
    """三個 C 工具必須：(a) 在 TOOL_SCHEMAS 內，(b) 可經 ToolExecutor.execute() 觸達。"""

    def setup_method(self):
        # orderbook 預設關閉、cvd/liq 預設開啟；統一清環境讓行為可預期。
        for k in (
            ENV_L2_TOOL_ORDERBOOK_ENABLED,
            ENV_L2_TOOL_CVD_ENABLED,
            ENV_L2_TOOL_LIQUIDATIONS_ENABLED,
        ):
            os.environ.pop(k, None)

    def teardown_method(self):
        for k in (
            ENV_L2_TOOL_ORDERBOOK_ENABLED,
            ENV_L2_TOOL_CVD_ENABLED,
            ENV_L2_TOOL_LIQUIDATIONS_ENABLED,
        ):
            os.environ.pop(k, None)

    def test_all_three_in_tool_schemas(self):
        from app.layer2_tools import TOOL_SCHEMAS
        names = {s["name"] for s in TOOL_SCHEMAS}
        assert TOOL_GET_ORDERBOOK in names
        assert TOOL_GET_CVD in names
        assert TOOL_GET_LIQUIDATIONS in names

    def test_all_three_in_handler_dispatch(self):
        # execute() 對未知工具回 {"error": "Unknown tool: ..."}；
        # 若三工具未註冊 handler，這裡會命中該分支 → 測試失敗。
        from app.layer2_tools import ToolExecutor
        ex = ToolExecutor()
        for tool in (TOOL_GET_ORDERBOOK, TOOL_GET_CVD, TOOL_GET_LIQUIDATIONS):
            # 用空 PG / 關閉的 orderbook，確保不依賴外部資源即可確認「已觸達」。
            cm, _ = _mock_pg(rows=[])
            with patch("app.layer2_tools_g3_08.db_pool.get_pg_conn", return_value=cm):
                result_str = _run(ex.execute(tool, {"symbol": "BTCUSDT"}))
            parsed = json.loads(result_str)
            # error 可能為 None（cvd/liq 空 rows 合法），用 or "" 防 None 不可迭代。
            assert "Unknown tool" not in (parsed.get("error") or "")
            # 回傳必含該工具的 symbol 欄位（證明走進了 g3_08，而非 unknown 分支）。
            assert parsed.get("symbol") == "BTCUSDT"

    def test_orderbook_depth_bridged_to_limit_via_executor(self):
        # schema 對外是 depth；sibling 讀 limit。經 executor 的 depth→limit 橋接，
        # depth 值必須真正抵達 HTTP params（否則靜默丟失）。
        from app.layer2_tools import ToolExecutor
        ex = ToolExecutor()
        payload = {
            "retCode": 0,
            "result": {"b": [["1", "1"]], "a": [["2", "1"]], "ts": 1},
            "time": 1,
        }
        ctx, client = _make_client_ctx(get_return=_make_resp(200, payload))
        with patch.dict(os.environ, {ENV_L2_TOOL_ORDERBOOK_ENABLED: "1"}, clear=False):
            with patch("httpx.AsyncClient", return_value=ctx):
                _run(ex.execute(TOOL_GET_ORDERBOOK, {"symbol": "BTCUSDT", "depth": 7}))
        _, kwargs = client.get.call_args
        assert kwargs["params"]["limit"] == 7
