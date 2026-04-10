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
        with patch("app.grafana_data_writer._get_pg_conn", return_value=mock_conn), \
             patch("app.grafana_data_writer._put_pg_conn") as mock_put:
            writer._write_snapshot()
        mock_conn.commit.assert_called_once()
        mock_put.assert_called_once_with(mock_conn)
        assert writer._stats["writes"] == 1
        assert writer._stats["last_write_ts"] is not None

class TestGetPgConn:
    """Test PostgreSQL connection helper (now delegates to db_pool).
    测试 PostgreSQL 连接辅助函数（现委托给 db_pool）。"""

    def test_returns_none_when_pool_unavailable(self):
        """Pool returns None → _get_pg_conn returns None.
        連接池返回 None → _get_pg_conn 返回 None。"""
        with patch("app.db_pool.get_conn", return_value=None):
            result = _get_pg_conn()
            assert result is None

    def test_returns_conn_from_pool(self):
        """Pool returns connection → _get_pg_conn returns it.
        連接池返回連接 → _get_pg_conn 返回該連接。"""
        mock_conn = MagicMock()
        with patch("app.db_pool.get_conn", return_value=mock_conn):
            result = _get_pg_conn()
            assert result is mock_conn


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
