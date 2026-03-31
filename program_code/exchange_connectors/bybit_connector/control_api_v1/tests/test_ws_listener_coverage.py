"""
E4 Wave 2 P1-8: bybit_public_ws_listener.py 重連/on_close/on_error 覆蓋測試
Tests for reconnect, on_close, on_error, subscribe/unsubscribe, and message edge cases

覆蓋範圍 / Coverage:
  - on_close 回調：正常關閉 vs 異常關閉 / on_close: normal vs abnormal close
  - on_error 回調：不同錯誤類型 / on_error: various error types
  - 重連邏輯：connection_attempts 計數遞增 / Reconnect: connection_attempts increment
  - 重連後停止：stop_flag 設置後不重連 / After stop: no reconnect when stop_flag set
  - 消息解析邊界：無效 JSON / 缺少字段 / 負價格 / Message parsing edge cases
  - 訂閱管理：add_symbol / remove_symbol / Subscription management
  - 回調異常容忍：on_price 拋出異常不中斷監聽器 / Callback exception tolerance
  - 狀態追踪：subscribe_ok_count / connected flag / Status tracking
  - PriceEvent：to_dict 完整性 + receive_ts_ms 非零 / PriceEvent completeness
  - _safe_float：邊界值 / _safe_float edge values
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Project path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bybit_public_ws_listener import (
    BybitPublicWsListener,
    PriceEvent,
    RECONNECT_DELAY_SEC,
    _safe_float,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _ticker_msg(symbol: str, last_price: str, **extra) -> str:
    """Build a minimal Bybit V5 ticker JSON string / 構造最小 ticker JSON"""
    data: dict[str, Any] = {"symbol": symbol, "lastPrice": last_price}
    data.update(extra)
    return json.dumps({"topic": f"tickers.{symbol}", "type": "snapshot", "ts": 1711500000000, "data": data})


def _make_listener(**kwargs) -> BybitPublicWsListener:
    """Convenience factory / 快捷工廠"""
    return BybitPublicWsListener(symbols=["BTCUSDT"], **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# T01–T03: on_close callback behaviour
# ═══════════════════════════════════════════════════════════════════════════════

class TestOnClose:
    """on_close sets connected=False regardless of close code / on_close 無論關閉碼都設 connected=False"""

    def _extract_callbacks(self, listener: BybitPublicWsListener) -> dict[str, Any]:
        """
        Run one iteration of _run_loop with a mocked WebSocketApp that
        captures the callbacks passed as keyword arguments, then sets stop_flag.
        使用 kwargs 捕獲 on_close / on_error 回調，再設置 stop_flag 退出循環。
        """
        captured: dict[str, Any] = {}

        def fake_ws_app_constructor(url, **kwargs):
            captured.update(kwargs)
            # Set stop_flag after capture so the loop exits after one pass
            listener._stop_flag.set()
            mock_app = MagicMock()
            mock_app.run_forever.return_value = None
            return mock_app

        with patch("app.bybit_public_ws_listener.websocket.WebSocketApp",
                   side_effect=fake_ws_app_constructor):
            listener._run_loop()

        return captured

    def test_on_close_normal_sets_connected_false(self):
        """Normal close (code 1000) clears connected flag / 正常關閉清除 connected 標誌"""
        listener = _make_listener()
        with listener._lock:
            listener._status["connected"] = True

        captured = self._extract_callbacks(listener)
        on_close = captured["on_close"]
        on_close(MagicMock(), 1000, "Normal closure")

        assert listener._status["connected"] is False

    def test_on_close_abnormal_sets_connected_false(self):
        """Abnormal close (code 1006) also clears connected flag / 異常關閉也清除 connected"""
        listener = _make_listener()
        with listener._lock:
            listener._status["connected"] = True

        captured = self._extract_callbacks(listener)
        on_close = captured["on_close"]
        on_close(MagicMock(), 1006, "Connection reset")

        assert listener._status["connected"] is False

    def test_on_close_with_none_msg(self):
        """on_close handles None message without raising / on_close 處理 None msg 不拋出"""
        listener = _make_listener()
        captured = self._extract_callbacks(listener)
        on_close = captured["on_close"]
        on_close(MagicMock(), None, None)
        assert listener._status["connected"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# T04–T06: on_error callback behaviour
# ═══════════════════════════════════════════════════════════════════════════════

class TestOnError:
    """on_error records last_error in status / on_error 記錄 last_error"""

    def _extract_callbacks(self, listener: BybitPublicWsListener) -> dict[str, Any]:
        """Capture callbacks via kwargs, then set stop_flag / 通過 kwargs 捕獲回調後設 stop_flag"""
        captured: dict[str, Any] = {}

        def fake_ws_app_constructor(url, **kwargs):
            captured.update(kwargs)
            listener._stop_flag.set()
            mock_app = MagicMock()
            mock_app.run_forever.return_value = None
            return mock_app

        with patch("app.bybit_public_ws_listener.websocket.WebSocketApp",
                   side_effect=fake_ws_app_constructor):
            listener._run_loop()

        return captured

    def test_on_error_connection_refused(self):
        """Connection-refused error is stored in last_error / 連接拒絕錯誤記錄到 last_error"""
        listener = _make_listener()
        captured = self._extract_callbacks(listener)
        on_error = captured["on_error"]
        on_error(MagicMock(), ConnectionRefusedError("Connection refused"))
        assert listener._status["last_error"] is not None
        assert "Connection refused" in listener._status["last_error"]

    def test_on_error_timeout(self):
        """Timeout error string captured / 超時錯誤字符串被捕獲"""
        listener = _make_listener()
        captured = self._extract_callbacks(listener)
        on_error = captured["on_error"]
        on_error(MagicMock(), TimeoutError("timed out"))
        assert "timed out" in listener._status["last_error"]

    def test_on_error_generic_exception(self):
        """Generic exception string stored / 通用異常字符串存儲"""
        listener = _make_listener()
        captured = self._extract_callbacks(listener)
        on_error = captured["on_error"]
        on_error(MagicMock(), Exception("some ws error"))
        assert "some ws error" in listener._status["last_error"]

    def test_on_error_does_not_raise(self):
        """on_error itself should never raise / on_error 自身不拋出"""
        listener = _make_listener()
        captured = self._extract_callbacks(listener)
        on_error = captured["on_error"]
        on_error(MagicMock(), 42)
        assert listener._status["last_error"] == "42"


# ═══════════════════════════════════════════════════════════════════════════════
# T07–T10: Reconnect logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestReconnectLogic:
    """connection_attempts increments on each loop pass / 每次循環 connection_attempts 遞增"""

    def test_connection_attempts_increments_each_loop(self):
        """Two loop iterations → connection_attempts == 2 / 兩次迴圈 → attempts == 2"""
        listener = _make_listener()
        call_count = 0

        def fake_ws_app_constructor(url, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_app = MagicMock()
            if call_count >= 2:
                listener._stop_flag.set()
            mock_app.run_forever.return_value = None
            return mock_app

        with patch("app.bybit_public_ws_listener.websocket.WebSocketApp",
                   side_effect=fake_ws_app_constructor):
            with patch.object(listener._stop_flag, "wait", side_effect=lambda timeout=None: None):
                listener._run_loop()

        assert listener._status["connection_attempts"] == 2

    def test_stop_flag_prevents_reconnect(self):
        """Setting stop_flag before run_loop → only one attempt / stop_flag 設置後只有一次嘗試"""
        listener = _make_listener()

        def fake_ws_app_constructor(url, **kwargs):
            listener._stop_flag.set()
            mock_app = MagicMock()
            mock_app.run_forever.return_value = None
            return mock_app

        with patch("app.bybit_public_ws_listener.websocket.WebSocketApp",
                   side_effect=fake_ws_app_constructor):
            listener._run_loop()

        assert listener._status["connection_attempts"] == 1

    def test_run_forever_exception_stored_in_last_error(self):
        """run_forever exception captured in last_error / run_forever 異常存入 last_error"""
        listener = _make_listener()

        def fake_ws_app_constructor(url, **kwargs):
            listener._stop_flag.set()
            mock_app = MagicMock()
            mock_app.run_forever.side_effect = RuntimeError("network failure")
            return mock_app

        with patch("app.bybit_public_ws_listener.websocket.WebSocketApp",
                   side_effect=fake_ws_app_constructor):
            listener._run_loop()

        assert listener._status["last_error"] is not None
        assert "network failure" in listener._status["last_error"]

    def test_status_running_false_after_loop_exits(self):
        """After _run_loop exits, running=False, connected=False / 循環退出後狀態清零"""
        listener = _make_listener()
        with listener._lock:
            listener._status["running"] = True
            listener._status["connected"] = True

        def fake_ws_app_constructor(url, **kwargs):
            listener._stop_flag.set()
            mock_app = MagicMock()
            mock_app.run_forever.return_value = None
            return mock_app

        with patch("app.bybit_public_ws_listener.websocket.WebSocketApp",
                   side_effect=fake_ws_app_constructor):
            listener._run_loop()

        assert listener._status["running"] is False
        assert listener._status["connected"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# T11–T14: Message parsing edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestMessageParsingEdgeCases:
    """Edge cases for _handle_message / _handle_message 邊界情況"""

    def test_invalid_json_silently_dropped(self):
        """Invalid JSON does not raise / 無效 JSON 不拋出"""
        listener = _make_listener()
        listener._handle_message("{not valid json!!!")
        assert listener._status["message_count"] == 0  # not even counted

    def test_empty_string_silently_dropped(self):
        """Empty string does not raise / 空字符串不拋出"""
        listener = _make_listener()
        listener._handle_message("")
        assert listener._status["message_count"] == 0

    def test_missing_symbol_field_dropped(self):
        """Data without 'symbol' key is dropped / 缺少 symbol 字段被丟棄"""
        received: list = []
        listener = _make_listener(on_price=received.append)
        msg = json.dumps({
            "topic": "tickers.BTCUSDT",
            "data": {"lastPrice": "87000.00"},  # no "symbol" key
        })
        listener._handle_message(msg)
        assert len(received) == 0

    def test_missing_data_field_dropped(self):
        """Message without 'data' key is dropped / 缺少 data 字段被丟棄"""
        received: list = []
        listener = _make_listener(on_price=received.append)
        msg = json.dumps({"topic": "tickers.BTCUSDT", "type": "snapshot"})
        listener._handle_message(msg)
        assert len(received) == 0

    def test_negative_last_price_dropped(self):
        """Negative lastPrice is treated as invalid / 負數 lastPrice 視為無效"""
        received: list = []
        listener = _make_listener(on_price=received.append)
        listener._handle_message(_ticker_msg("BTCUSDT", "-1.0"))
        assert len(received) == 0

    def test_zero_last_price_dropped(self):
        """Zero lastPrice is treated as invalid / 零 lastPrice 視為無效"""
        received: list = []
        listener = _make_listener(on_price=received.append)
        listener._handle_message(_ticker_msg("BTCUSDT", "0"))
        assert len(received) == 0

    def test_non_ticker_topic_ignored(self):
        """Non-tickers topic is ignored / 非 tickers 主題被忽略"""
        received: list = []
        listener = _make_listener(on_price=received.append)
        msg = json.dumps({"topic": "orderbook.BTCUSDT", "data": {"symbol": "BTCUSDT", "lastPrice": "87000"}})
        listener._handle_message(msg)
        assert len(received) == 0

    def test_message_count_incremented_on_valid_parse(self):
        """message_count increments for every successfully JSON-parsed message / 成功解析的消息計數遞增"""
        listener = _make_listener()
        # Send a pong (valid JSON, not ticker, but still parsed)
        listener._handle_message(json.dumps({"op": "pong"}))
        assert listener._status["message_count"] == 1

    def test_subscribe_confirmation_increments_subscribe_ok_count(self):
        """subscribe confirmation with success=True increments subscribe_ok_count / 訂閱確認計數"""
        listener = _make_listener()
        msg = json.dumps({"op": "subscribe", "success": True, "req_id": "test"})
        listener._handle_message(msg)
        assert listener._status["subscribe_ok_count"] == 1

    def test_failed_subscribe_confirmation_does_not_increment(self):
        """subscribe confirmation with success=False does not increment / 失敗訂閱不計數"""
        listener = _make_listener()
        msg = json.dumps({"op": "subscribe", "success": False})
        listener._handle_message(msg)
        assert listener._status["subscribe_ok_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# T15–T18: Subscription management (add_symbol / remove_symbol)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubscriptionManagement:
    """add_symbol / remove_symbol behaviour / 訂閱管理行為"""

    def test_add_symbol_appends_to_list(self):
        """add_symbol adds symbol to internal list / add_symbol 加入內部列表"""
        listener = _make_listener()
        listener.add_symbol("ETHUSDT")
        assert "ETHUSDT" in listener._symbols
        assert "ETHUSDT" in listener._status["subscribed_symbols"]

    def test_add_symbol_duplicate_ignored(self):
        """Adding existing symbol is idempotent / 重複添加無效"""
        listener = _make_listener()
        listener.add_symbol("BTCUSDT")
        assert listener._symbols.count("BTCUSDT") == 1

    def test_remove_symbol_removes_from_list(self):
        """remove_symbol removes from internal list / remove_symbol 從內部列表移除"""
        listener = BybitPublicWsListener(symbols=["BTCUSDT", "ETHUSDT"])
        listener.remove_symbol("ETHUSDT")
        assert "ETHUSDT" not in listener._symbols
        assert "ETHUSDT" not in listener._status["subscribed_symbols"]

    def test_remove_symbol_not_present_ignored(self):
        """Removing non-existent symbol is safe / 移除不存在的交易對無副作用"""
        listener = _make_listener()
        listener.remove_symbol("SOLUSDT")  # Not in list, should not raise
        assert listener._symbols == ["BTCUSDT"]

    def test_add_symbol_sends_subscribe_when_ws_active(self):
        """add_symbol sends subscribe message when WS is active / 有 WS 時發送訂閱消息"""
        listener = _make_listener()
        mock_ws = MagicMock()
        listener._ws = mock_ws

        listener.add_symbol("SOLUSDT")

        mock_ws.send.assert_called_once()
        sent_payload = json.loads(mock_ws.send.call_args[0][0])
        assert sent_payload["op"] == "subscribe"
        assert "tickers.SOLUSDT" in sent_payload["args"]

    def test_remove_symbol_sends_unsubscribe_when_ws_active(self):
        """remove_symbol sends unsubscribe message when WS is active / 有 WS 時發送取消訂閱"""
        listener = BybitPublicWsListener(symbols=["BTCUSDT", "SOLUSDT"])
        mock_ws = MagicMock()
        listener._ws = mock_ws

        listener.remove_symbol("SOLUSDT")

        mock_ws.send.assert_called_once()
        sent_payload = json.loads(mock_ws.send.call_args[0][0])
        assert sent_payload["op"] == "unsubscribe"
        assert "tickers.SOLUSDT" in sent_payload["args"]

    def test_add_symbol_no_ws_no_send(self):
        """add_symbol does not crash when no active WS / 無 WS 時不崩潰"""
        listener = _make_listener()
        listener._ws = None
        listener.add_symbol("SOLUSDT")
        # No exception, symbol added
        assert "SOLUSDT" in listener._symbols


# ═══════════════════════════════════════════════════════════════════════════════
# T19–T21: Callback exception tolerance
# ═══════════════════════════════════════════════════════════════════════════════

class TestCallbackExceptionTolerance:
    """on_price callback exceptions should not crash the listener / 回調異常不崩潰監聽器"""

    def test_exception_in_callback_does_not_propagate(self):
        """Exception in on_price callback is swallowed / on_price 異常被吞噬"""
        def bad_callback(evt):
            raise RuntimeError("callback failure")

        listener = _make_listener(on_price=bad_callback)
        # Should not raise
        listener._handle_message(_ticker_msg("BTCUSDT", "87000.00"))
        # Verify price was still cached before callback
        assert listener.get_latest_price("BTCUSDT") is not None

    def test_multiple_messages_after_callback_error(self):
        """Listener continues processing after callback error / 回調錯誤後繼續處理"""
        call_count = 0

        def flaky_callback(evt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first call fails")

        listener = _make_listener(on_price=flaky_callback)
        listener._handle_message(_ticker_msg("BTCUSDT", "87000.00"))  # fails
        listener._handle_message(_ticker_msg("BTCUSDT", "87100.00"))  # should succeed

        assert call_count == 2  # Both calls were attempted
        assert listener._status["ticker_update_count"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# T22–T24: Status tracking completeness
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatusTracking:
    """Status dictionary completeness and correctness / 狀態字典完整性和正確性"""

    def test_initial_status_fields(self):
        """All expected status fields present at init / 初始化時所有狀態字段存在"""
        listener = _make_listener()
        status = listener.get_status()
        expected_keys = [
            "listener_type", "listener_version", "running", "connected",
            "subscribed_symbols", "connection_attempts", "connection_open_count",
            "subscribe_ok_count", "message_count", "ticker_update_count",
            "last_error", "last_ticker_ts_ms", "started_ts_ms", "ws_url",
        ]
        for key in expected_keys:
            assert key in status, f"Missing status key: {key}"

    def test_initial_status_defaults(self):
        """Initial status values are sane defaults / 初始狀態值為合理默認值"""
        listener = _make_listener()
        status = listener.get_status()
        assert status["running"] is False
        assert status["connected"] is False
        assert status["connection_attempts"] == 0
        assert status["ticker_update_count"] == 0
        assert status["last_error"] is None
        assert status["started_ts_ms"] is None

    def test_get_status_returns_copy(self):
        """get_status returns a copy, not the live dict / get_status 返回副本"""
        listener = _make_listener()
        status1 = listener.get_status()
        status1["running"] = True  # Mutate returned dict
        status2 = listener.get_status()
        assert status2["running"] is False  # Original unaffected

    def test_ticker_update_count_increments(self):
        """ticker_update_count increments for each valid ticker message / 有效 ticker 計數遞增"""
        listener = _make_listener()
        for price in ["87000.00", "87100.00", "87200.00"]:
            listener._handle_message(_ticker_msg("BTCUSDT", price))
        assert listener._status["ticker_update_count"] == 3

    def test_last_ticker_ts_ms_set_after_message(self):
        """last_ticker_ts_ms is set after processing a ticker / 處理 ticker 後設置時間戳"""
        listener = _make_listener()
        assert listener._status["last_ticker_ts_ms"] is None
        listener._handle_message(_ticker_msg("BTCUSDT", "87000.00"))
        assert listener._status["last_ticker_ts_ms"] is not None
        assert listener._status["last_ticker_ts_ms"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# T25–T27: PriceEvent completeness
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriceEventCompleteness:
    """PriceEvent construction and receive_ts_ms / 價格事件構建與接收時間戳"""

    def test_receive_ts_ms_set_on_handle_message(self):
        """receive_ts_ms is set to current time when message processed / 處理消息時設置接收時間戳"""
        listener = _make_listener()
        before = int(time.time() * 1000)
        listener._handle_message(_ticker_msg("BTCUSDT", "87000.00"))
        after = int(time.time() * 1000)

        evt = listener.get_latest_price("BTCUSDT")
        assert evt is not None
        assert before <= evt.receive_ts_ms <= after

    def test_ts_ms_from_message(self):
        """ts_ms is taken from message timestamp / ts_ms 從消息時間戳獲取"""
        listener = _make_listener()
        msg = json.dumps({
            "topic": "tickers.BTCUSDT",
            "type": "snapshot",
            "ts": 1711500123456,
            "data": {"symbol": "BTCUSDT", "lastPrice": "87000.00"},
        })
        listener._handle_message(msg)
        evt = listener.get_latest_price("BTCUSDT")
        assert evt.ts_ms == 1711500123456

    def test_optional_fields_none_when_absent(self):
        """Optional fields are None when not in message / 可選字段不存在時為 None"""
        listener = _make_listener()
        listener._handle_message(_ticker_msg("BTCUSDT", "87000.00"))
        evt = listener.get_latest_price("BTCUSDT")
        # Only lastPrice provided — all optional fields should be None
        assert evt.mark_price is None
        assert evt.index_price is None
        assert evt.best_bid is None
        assert evt.best_ask is None
        assert evt.volume_24h is None
        assert evt.high_24h is None
        assert evt.low_24h is None

    def test_full_ticker_all_optional_fields_parsed(self):
        """Full ticker message populates all optional fields / 完整 ticker 填充所有可選字段"""
        listener = _make_listener()
        msg = _ticker_msg(
            "BTCUSDT", "87000.00",
            markPrice="86995.00",
            indexPrice="86998.00",
            bid1Price="86999.00",
            ask1Price="87001.00",
            volume24h="50000.00",
            turnover24h="4350000000.00",
            price24hPcnt="0.0150",
            highPrice24h="88000.00",
            lowPrice24h="85000.00",
        )
        listener._handle_message(msg)
        evt = listener.get_latest_price("BTCUSDT")
        assert evt.mark_price == 86995.00
        assert evt.index_price == 86998.00
        assert evt.best_bid == 86999.00
        assert evt.best_ask == 87001.00
        assert evt.volume_24h == 50000.00
        assert evt.turnover_24h == 4350000000.00
        assert evt.price_change_pct_24h == 0.0150
        assert evt.high_24h == 88000.00
        assert evt.low_24h == 85000.00


# ═══════════════════════════════════════════════════════════════════════════════
# T28–T30: _safe_float edge values
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeFloatEdgeCases:
    """_safe_float boundary values / _safe_float 邊界值"""

    def test_very_small_positive(self):
        """Very small positive value returns that value / 極小正數返回該值"""
        result = _safe_float("0.000001")
        assert result == pytest.approx(0.000001)

    def test_large_value(self):
        """Large value (e.g. BTC price) handled correctly / 大數值正確處理"""
        assert _safe_float("87654321.12") == pytest.approx(87654321.12)

    def test_float_input_passthrough(self):
        """Float input (not string) also works / 浮點數輸入同樣可用"""
        assert _safe_float(3200.50) == pytest.approx(3200.50)

    def test_whitespace_string(self):
        """Whitespace-only string returns None / 僅空白字符串返回 None"""
        assert _safe_float("   ") is None

    def test_empty_string(self):
        """Empty string returns None / 空字符串返回 None"""
        assert _safe_float("") is None


# ═══════════════════════════════════════════════════════════════════════════════
# T31: Listener lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestListenerLifecycle:
    """start / stop / is_running basic lifecycle / 基本生命週期"""

    def test_is_running_false_before_start(self):
        """is_running is False before start() / start 前 is_running 為 False"""
        listener = _make_listener()
        assert listener.is_running() is False

    def test_get_all_latest_prices_empty_initially(self):
        """get_all_latest_prices returns empty dict initially / 初始狀態返回空字典"""
        listener = _make_listener()
        assert listener.get_all_latest_prices() == {}

    def test_get_latest_price_returns_none_for_unknown(self):
        """get_latest_price returns None for unknown symbol / 未知交易對返回 None"""
        listener = _make_listener()
        assert listener.get_latest_price("XYZUSDT") is None

    def test_multiple_symbols_cached_independently(self):
        """Each symbol caches independently / 每個交易對獨立緩存"""
        listener = BybitPublicWsListener(symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        listener._handle_message(_ticker_msg("BTCUSDT", "87000.00"))
        listener._handle_message(_ticker_msg("ETHUSDT", "3200.00"))
        listener._handle_message(_ticker_msg("SOLUSDT", "150.00"))

        assert listener.get_latest_price("BTCUSDT").last_price == 87000.00
        assert listener.get_latest_price("ETHUSDT").last_price == 3200.00
        assert listener.get_latest_price("SOLUSDT").last_price == 150.00

    def test_price_cache_updated_on_repeat_messages(self):
        """Repeated messages update cache to latest price / 重複消息更新緩存到最新價格"""
        listener = _make_listener()
        listener._handle_message(_ticker_msg("BTCUSDT", "87000.00"))
        listener._handle_message(_ticker_msg("BTCUSDT", "88000.00"))
        assert listener.get_latest_price("BTCUSDT").last_price == 88000.00

    def test_stop_sets_running_false_in_status(self):
        """stop() sets running=False in status / stop() 設置 running=False"""
        listener = _make_listener()
        with listener._lock:
            listener._status["running"] = True
        listener.stop()
        assert listener._status["running"] is False
