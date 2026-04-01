"""
Grafana Data Writer — Unit Tests
Grafana 数据写入器 — 单元测试

MODULE_NOTE (中文):
  测试 GrafanaDataWriter 的核心逻辑：
  1. PnL 快照写入（session 状态、胜率计算）
  2. 市场行情写入（从 pipeline_bridge 获取价格）
  3. 系统健康写入（kline_manager、pipeline_bridge 健康状态）
  4. 成交记录增量写入（避免重复）
  5. PG 连接失败时的静默降级
  6. start/stop 生命周期

MODULE_NOTE (English):
  Tests for GrafanaDataWriter core logic:
  1. PnL snapshot writes (session state, win rate calculation)
  2. Market ticker writes (prices from pipeline_bridge)
  3. System health writes (kline_manager, pipeline_bridge health)
  4. Trade execution incremental writes (no duplicates)
  5. Graceful degradation on PG connection failure
  6. start/stop lifecycle
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.grafana_data_writer import GrafanaDataWriter, _get_pg_conn


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_mock_cursor():
    return MagicMock()


def _make_mock_conn(cursor=None):
    conn = MagicMock()
    conn.cursor.return_value = cursor or _make_mock_cursor()
    return conn


def _make_paper_engine(*, active=True, balance=10500, initial=10000, fills=None, positions=None):
    """Create a mock PaperTradingEngine with configurable state."""
    engine = MagicMock()
    state = {
        "session": {
            "session_state": "active" if active else "stopped",
            "current_paper_balance_usdt": str(balance),
            "initial_paper_balance_usdt": str(initial),
            "session_id": "test_session_001",
        },
        "fills": fills if fills is not None else [],
        "positions": positions if positions is not None else {},
    }
    engine.get_state.return_value = state
    return engine


def _make_bridge(prices=None):
    """Create a mock PipelineBridge with optional latest prices."""
    bridge = MagicMock()
    bridge._latest_prices = prices or {}
    bridge.get_stats.return_value = {
        "active": True,
        "ticks_received": 100,
        "intents_submitted": 5,
        "stops_triggered": 1,
    }
    return bridge


def _make_kline_manager(*, stale=False):
    """Create a mock KlineManager."""
    km = MagicMock()
    km.get_stats.return_value = {
        "total_ticks_processed": 500,
        "total_klines_closed": 20,
        "symbols": ["BTCUSDT", "ETHUSDT"],
    }
    km.get_staleness.return_value = {"is_stale": stale}
    return km


def _make_writer(paper_engine=None, kline_manager=None, bridge=None, **kwargs):
    """Create a GrafanaDataWriter with mocked dependencies."""
    return GrafanaDataWriter(
        paper_engine=paper_engine,
        kline_manager=kline_manager,
        pipeline_bridge=bridge,
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 1: Constructor and Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrafanaDataWriterLifecycle:
    """Test constructor, start, stop lifecycle.
    测试构造器、启动、停止生命周期。"""

    def test_init_defaults(self):
        """Constructor sets correct defaults. 构造器设置正确默认值。"""
        writer = GrafanaDataWriter(interval_sec=15.0)
        assert writer._interval == 15.0
        assert writer._running is False
        assert writer._thread is None
        assert writer._last_fill_count == 0
        assert writer._stats["writes"] == 0
        assert writer._stats["errors"] == 0

    def test_start_sets_running(self):
        """start() sets _running to True and creates thread.
        start() 设置 _running 为 True 并创建线程。"""
        writer = _make_writer()
        writer.start()
        assert writer._running is True
        assert writer._thread is not None
        assert writer._thread.daemon is True
        writer.stop()

    def test_start_idempotent(self):
        """Calling start() twice does not create second thread.
        连续两次 start() 不会创建第二个线程。"""
        writer = _make_writer()
        writer.start()
        thread1 = writer._thread
        writer.start()
        thread2 = writer._thread
        assert thread1 is thread2
        writer.stop()

    def test_stop_sets_running_false(self):
        """stop() sets _running to False. stop() 设置 _running 为 False。"""
        writer = _make_writer()
        writer._running = True
        writer._thread = MagicMock()
        writer.stop()
        assert writer._running is False

    def test_get_stats_returns_expected_keys(self):
        """get_stats() returns component name and all stat keys.
        get_stats() 返回组件名和所有统计键。"""
        writer = _make_writer(interval_sec=45.0)
        stats = writer.get_stats()
        assert stats["component"] == "grafana_data_writer"
        assert stats["interval_sec"] == 45.0
        assert "running" in stats
        assert "writes" in stats
        assert "errors" in stats
        assert "last_write_ts" in stats


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 2: _write_snapshot() orchestration
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteSnapshot:
    """Test _write_snapshot orchestration.
    测试 _write_snapshot 编排逻辑。"""

    def test_write_snapshot_returns_when_no_pg(self):
        """No PG connection → silent return. 无 PG 连接 → 静默返回。"""
        writer = _make_writer()
        with patch("app.grafana_data_writer._get_pg_conn", return_value=None):
            writer._write_snapshot()  # Should not raise
        assert writer._stats["writes"] == 0

    def test_write_snapshot_commits_on_success(self):
        """Successful write commits and increments stats.
        成功写入提交事务并递增统计。"""
        writer = _make_writer()
        mock_conn = _make_mock_conn()
        with patch("app.grafana_data_writer._get_pg_conn", return_value=mock_conn):
            writer._write_snapshot()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
        assert writer._stats["writes"] == 1
        assert writer._stats["last_write_ts"] is not None

    def test_write_snapshot_rollback_on_exception(self):
        """Exception during write → rollback + re-raise.
        写入异常 → 回滚 + 重新抛出。"""
        writer = _make_writer()
        mock_conn = _make_mock_conn()
        with patch("app.grafana_data_writer._get_pg_conn", return_value=mock_conn), \
             patch.object(writer, "_write_pnl", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                writer._write_snapshot()
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 3: _write_pnl()
# ═══════════════════════════════════════════════════════════════════════════════

class TestWritePnl:
    """Test PnL snapshot write logic. 测试 PnL 快照写入逻辑。"""

    def test_write_pnl_skips_without_engine(self):
        """No engine → skip. 无引擎 → 跳过。"""
        writer = _make_writer(paper_engine=None)
        cur = _make_mock_cursor()
        writer._write_pnl(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_write_pnl_skips_inactive_session(self):
        """Inactive session → skip. 非活跃会话 → 跳过。"""
        engine = _make_paper_engine(active=False)
        writer = _make_writer(paper_engine=engine)
        cur = _make_mock_cursor()
        writer._write_pnl(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_write_pnl_inserts_active_session(self):
        """Active session PnL is inserted.
        活跃会话的 PnL 被插入。"""
        fills = [
            {"fee_usdt": "1.5", "realized_pnl": "50"},
            {"fee_usdt": "0.5", "realized_pnl": "-10"},
            {"fee_usdt": "1.0", "realized_pnl": "30"},
        ]
        engine = _make_paper_engine(balance=10500, initial=10000, fills=fills,
                                    positions={"BTCUSDT": {}, "ETHUSDT": {}})
        writer = _make_writer(paper_engine=engine)
        cur = _make_mock_cursor()
        writer._write_pnl(cur, 1700000000000)
        cur.execute.assert_called_once()
        params = cur.execute.call_args[0][1]
        # realized_pnl = 10500 - 10000 = 500
        assert params[2] == 500.0
        # total_fees = 1.5 + 0.5 + 1.0 = 3.0
        assert params[4] == 3.0
        # open_positions = 2
        assert params[7] == 2
        # total_trades = 3
        assert params[8] == 3

    def test_write_pnl_win_rate_calculation(self):
        """Win rate is correctly calculated from fills.
        胜率从成交记录中正确计算。"""
        fills = [
            {"fee_usdt": "0", "realized_pnl": "100"},   # win
            {"fee_usdt": "0", "realized_pnl": "-50"},    # loss
            {"fee_usdt": "0", "realized_pnl": "0"},      # break-even (not a win)
            {"fee_usdt": "0", "realized_pnl": "200"},    # win
        ]
        engine = _make_paper_engine(fills=fills)
        writer = _make_writer(paper_engine=engine)
        cur = _make_mock_cursor()
        writer._write_pnl(cur, 1700000000000)
        params = cur.execute.call_args[0][1]
        # win_rate = 2/4 * 100 = 50.0
        assert params[9] == 50.0

    def test_write_pnl_zero_fills_win_rate_none(self):
        """Zero fills → win_rate is None.
        无成交 → 胜率为 None。"""
        engine = _make_paper_engine(fills=[])
        writer = _make_writer(paper_engine=engine)
        cur = _make_mock_cursor()
        writer._write_pnl(cur, 1700000000000)
        params = cur.execute.call_args[0][1]
        assert params[9] is None  # win_rate


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 4: _write_market_tickers()
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteMarketTickers:
    """Test market ticker write logic. 测试市场行情写入逻辑。"""

    def test_write_tickers_skips_without_bridge(self):
        """No bridge → skip. 无桥 → 跳过。"""
        writer = _make_writer(bridge=None)
        cur = _make_mock_cursor()
        writer._write_market_tickers(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_write_tickers_skips_empty_prices(self):
        """Empty prices → skip. 空价格 → 跳过。"""
        bridge = _make_bridge(prices={})
        writer = _make_writer(bridge=bridge)
        cur = _make_mock_cursor()
        writer._write_market_tickers(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_write_tickers_inserts_each_symbol(self):
        """Each symbol gets an INSERT. 每个符号都有一条 INSERT。"""
        bridge = _make_bridge(prices={"BTCUSDT": 60000.0, "ETHUSDT": 3000.0})
        writer = _make_writer(bridge=bridge)
        cur = _make_mock_cursor()
        writer._write_market_tickers(cur, 1700000000000)
        assert cur.execute.call_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 5: _write_system_health()
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteSystemHealth:
    """Test system health write logic. 测试系统健康写入逻辑。"""

    def test_health_writes_kline_manager_healthy(self):
        """KlineManager healthy → status='healthy'.
        KlineManager 健康 → status='healthy'。"""
        km = _make_kline_manager(stale=False)
        writer = _make_writer(kline_manager=km)
        cur = _make_mock_cursor()
        writer._write_system_health(cur, 1700000000000)
        cur.execute.assert_called_once()
        params = cur.execute.call_args[0][1]
        assert params[1] == "kline_manager"
        assert params[2] == "healthy"

    def test_health_writes_kline_manager_stale(self):
        """Stale KlineManager → status='stale'.
        过期 KlineManager → status='stale'。"""
        km = _make_kline_manager(stale=True)
        writer = _make_writer(kline_manager=km)
        cur = _make_mock_cursor()
        writer._write_system_health(cur, 1700000000000)
        params = cur.execute.call_args[0][1]
        assert params[2] == "stale"

    def test_health_writes_bridge_active(self):
        """Active bridge → status='active'.
        活跃桥 → status='active'。"""
        bridge = _make_bridge()
        writer = _make_writer(bridge=bridge)
        cur = _make_mock_cursor()
        writer._write_system_health(cur, 1700000000000)
        cur.execute.assert_called_once()
        params = cur.execute.call_args[0][1]
        assert params[1] == "pipeline_bridge"
        assert params[2] == "active"

    def test_health_writes_bridge_inactive(self):
        """Inactive bridge → status='inactive'.
        非活跃桥 → status='inactive'。"""
        bridge = _make_bridge()
        bridge.get_stats.return_value = {"active": False, "ticks_received": 0,
                                         "intents_submitted": 0, "stops_triggered": 0}
        writer = _make_writer(bridge=bridge)
        cur = _make_mock_cursor()
        writer._write_system_health(cur, 1700000000000)
        params = cur.execute.call_args[0][1]
        assert params[2] == "inactive"

    def test_health_writes_both_km_and_bridge(self):
        """Both KlineManager and bridge → two INSERTs.
        同时有 KlineManager 和 bridge → 两条 INSERT。"""
        km = _make_kline_manager()
        bridge = _make_bridge()
        writer = _make_writer(kline_manager=km, bridge=bridge)
        cur = _make_mock_cursor()
        writer._write_system_health(cur, 1700000000000)
        assert cur.execute.call_count == 2

    def test_health_no_deps_no_writes(self):
        """No km or bridge → no writes. 无依赖 → 无写入。"""
        writer = _make_writer()
        cur = _make_mock_cursor()
        writer._write_system_health(cur, 1700000000000)
        cur.execute.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 6: _write_trade_executions() — incremental fills
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteTradeExecutions:
    """Test incremental trade execution writes.
    测试增量成交记录写入。"""

    def test_skips_without_engine(self):
        """No engine → skip. 无引擎 → 跳过。"""
        writer = _make_writer(paper_engine=None)
        cur = _make_mock_cursor()
        writer._write_trade_executions(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_writes_new_fills_only(self):
        """Only new fills (after last cursor) are written.
        仅写入新的成交记录（游标之后的）。"""
        fills = [
            {"fill_id": "f1", "symbol": "BTCUSDT", "side": "Buy", "qty": 0.01,
             "fill_price": 60000, "fee_usdt": 0.36, "fill_ts_ms": 1700000000000},
            {"fill_id": "f2", "symbol": "ETHUSDT", "side": "Sell", "qty": 1.0,
             "fill_price": 3000, "fee_usdt": 0.18, "fill_ts_ms": 1700000001000},
        ]
        engine = _make_paper_engine(fills=fills)
        writer = _make_writer(paper_engine=engine)
        writer._last_fill_count = 0  # No fills seen yet

        cur = _make_mock_cursor()
        writer._write_trade_executions(cur, 1700000000000)
        assert cur.execute.call_count == 2
        assert writer._last_fill_count == 2

    def test_no_new_fills_does_nothing(self):
        """No new fills → no writes. 无新成交 → 不写入。"""
        fills = [{"fill_id": "f1"}]
        engine = _make_paper_engine(fills=fills)
        writer = _make_writer(paper_engine=engine)
        writer._last_fill_count = 1  # Already seen fill

        cur = _make_mock_cursor()
        writer._write_trade_executions(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_incremental_only_new_fills(self):
        """Second call only writes newly appended fills.
        第二次调用仅写入新追加的成交。"""
        fills = [
            {"fill_id": "f1", "symbol": "A", "side": "Buy", "qty": 1, "fill_price": 100, "fee_usdt": 0},
            {"fill_id": "f2", "symbol": "B", "side": "Sell", "qty": 2, "fill_price": 200, "fee_usdt": 0},
        ]
        engine = _make_paper_engine(fills=fills)
        writer = _make_writer(paper_engine=engine)
        writer._last_fill_count = 1  # f1 already written

        cur = _make_mock_cursor()
        writer._write_trade_executions(cur, 1700000000000)
        assert cur.execute.call_count == 1  # Only f2
        assert writer._last_fill_count == 2

    def test_fills_marked_is_paper_true(self):
        """All fills are marked is_paper=True.
        所有成交标记为 is_paper=True。"""
        fills = [{"fill_id": "f1", "symbol": "BTCUSDT", "side": "Buy",
                  "qty": 0.01, "fill_price": 60000, "fee_usdt": 0.36}]
        engine = _make_paper_engine(fills=fills)
        writer = _make_writer(paper_engine=engine)
        cur = _make_mock_cursor()
        writer._write_trade_executions(cur, 1700000000000)
        params = cur.execute.call_args[0][1]
        # is_paper is at index 11 in the params tuple
        assert params[11] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 7: _get_pg_conn() connection handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetPgConn:
    """Test PostgreSQL connection helper.
    测试 PostgreSQL 连接辅助函数。"""

    def test_returns_none_on_import_error(self):
        """psycopg2 not installed → None.
        psycopg2 未安装 → None。"""
        with patch.dict(sys.modules, {"psycopg2": None}):
            result = _get_pg_conn()
            assert result is None

    def test_returns_none_on_connection_error(self):
        """Connection failure → None. 连接失败 → None。"""
        mock_pg = MagicMock()
        mock_pg.connect.side_effect = Exception("connection refused")
        with patch.dict(sys.modules, {"psycopg2": mock_pg}):
            result = _get_pg_conn()
            assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 8: _loop() error handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriterLoop:
    """Test the background loop error handling.
    测试后台循环错误处理。"""

    def test_loop_increments_error_on_exception(self):
        """_loop() increments error count on exception.
        _loop() 在异常时递增错误计数。"""
        writer = _make_writer()
        writer._running = True
        call_count = [0]

        def mock_write():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("write failed")
            writer._running = False

        with patch.object(writer, "_write_snapshot", side_effect=mock_write), \
             patch("time.sleep", return_value=None):
            writer._loop()
        assert writer._stats["errors"] == 1
