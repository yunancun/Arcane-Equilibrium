"""
Bybit Demo Sync — Unit Tests
Bybit Demo 数据同步器 — 单元测试

MODULE_NOTE (中文):
  测试 BybitDemoSync 的核心逻辑：
  1. 同步执行记录、持仓快照、钱包余额到 PostgreSQL
  2. 连接失败时的静默降级
  3. 重试与错误计数
  4. get_current_snapshot() 对账快照构建
  5. start/stop 生命周期

MODULE_NOTE (English):
  Tests for BybitDemoSync core logic:
  1. Sync executions, positions, wallet balance to PostgreSQL
  2. Graceful degradation on connection failure
  3. Retry and error counting
  4. get_current_snapshot() reconciliation snapshot building
  5. start/stop lifecycle
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bybit_demo_sync import BybitDemoSync


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — mock objects for Bybit Demo connector and PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════════

def _make_demo_connector(*, is_enabled=True):
    """Create a mock Bybit Demo connector with reasonable defaults."""
    connector = MagicMock()
    connector.is_enabled = is_enabled
    connector.get_executions.return_value = {
        "retCode": 0,
        "result": {"list": []},
    }
    connector.get_positions.return_value = {
        "retCode": 0,
        "result": {"list": []},
    }
    connector.get_wallet_balance.return_value = {
        "retCode": 0,
        "result": {"list": [{"coin": []}]},
    }
    return connector


def _make_mock_cursor():
    """Create a mock PostgreSQL cursor."""
    return MagicMock()


def _make_mock_conn(cursor=None):
    """Create a mock PostgreSQL connection."""
    conn = MagicMock()
    conn.cursor.return_value = cursor or _make_mock_cursor()
    return conn


def _make_sync(connector=None, **kwargs):
    """Create a BybitDemoSync instance with mocked PG connection."""
    if connector is None:
        connector = _make_demo_connector()
    return BybitDemoSync(
        connector,
        pg_host="127.0.0.1",
        pg_port=5432,
        pg_user="test",
        pg_pass="test",
        pg_db="test_db",
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 1: Constructor and Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestBybitDemoSyncLifecycle:
    """Test constructor, start, stop lifecycle.
    测试构造器、启动、停止生命周期。"""

    def test_init_defaults(self):
        """Constructor sets correct defaults. 构造器设置正确默认值。"""
        connector = _make_demo_connector()
        sync = BybitDemoSync(connector, interval_sec=120.0, pg_pass="secret")
        assert sync._interval == 120.0
        assert sync._running is False
        assert sync._thread is None
        assert sync._stats["syncs"] == 0
        assert sync._stats["errors"] == 0
        assert sync._pg_config["password"] == "secret"

    def test_init_with_empty_pg_pass_falls_back(self):
        """Empty pg_pass triggers fallback to env/secrets.
        空密码触发环境变量/secrets 回退。"""
        connector = _make_demo_connector()
        with patch.dict(os.environ, {"PG_PASS": "env_pass"}):
            sync = BybitDemoSync(connector, pg_pass="")
            assert sync._pg_config["password"] == "env_pass"

    def test_start_with_disabled_connector_does_nothing(self):
        """start() is no-op when connector is disabled.
        连接器禁用时 start() 不做任何事。"""
        connector = _make_demo_connector(is_enabled=False)
        sync = BybitDemoSync(connector)
        sync.start()
        assert sync._running is False
        assert sync._thread is None

    def test_start_with_none_connector_does_nothing(self):
        """start() is no-op when connector is None.
        连接器为 None 时 start() 不做任何事。"""
        sync = BybitDemoSync(None)
        sync.start()
        assert sync._running is False

    def test_stop_sets_running_false(self):
        """stop() sets _running to False. stop() 设置 _running 为 False。"""
        sync = _make_sync()
        sync._running = True
        sync.stop()
        assert sync._running is False

    def test_get_stats_returns_expected_keys(self):
        """get_stats() returns component name and all stat keys.
        get_stats() 返回组件名和所有统计键。"""
        sync = _make_sync()
        stats = sync.get_stats()
        assert stats["component"] == "bybit_demo_sync"
        assert "running" in stats
        assert "syncs" in stats
        assert "executions_synced" in stats
        assert "positions_synced" in stats
        assert "errors" in stats


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 2: _sync() method — main sync orchestration
# ═══════════════════════════════════════════════════════════════════════════════

class TestBybitDemoSyncMainSync:
    """Test the _sync() method that orchestrates all sub-syncs.
    测试 _sync() 方法（编排所有子同步操作）。"""

    def test_sync_returns_early_when_pg_unavailable(self):
        """_sync() returns immediately if PG connection fails.
        PG 连接失败时 _sync() 立即返回。"""
        sync = _make_sync()
        with patch.object(sync, "_get_conn", return_value=None):
            sync._sync()  # Should not raise
        assert sync._stats["syncs"] == 0

    def test_sync_commits_on_success(self):
        """_sync() commits transaction and releases connection on success.
        成功时 _sync() 提交事务并释放连接。"""
        sync = _make_sync()
        mock_conn = _make_mock_conn()
        with patch.object(sync, "_get_conn", return_value=mock_conn), \
             patch.object(sync, "_release_conn") as mock_release:
            sync._sync()
        mock_conn.commit.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)
        assert sync._stats["syncs"] == 1

    def test_sync_rollback_on_exception(self):
        """_sync() rolls back and releases connection on error.
        出错时 _sync() 回滚并释放连接。"""
        sync = _make_sync()
        mock_conn = _make_mock_conn()
        with patch.object(sync, "_sync_executions", side_effect=RuntimeError("db error")):
            with patch.object(sync, "_get_conn", return_value=mock_conn), \
                 patch.object(sync, "_release_conn") as mock_release:
                with pytest.raises(RuntimeError, match="db error"):
                    sync._sync()
        mock_conn.rollback.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    def test_sync_calls_all_sub_syncs(self):
        """_sync() calls executions, positions, and wallet sub-syncs.
        _sync() 调用执行记录、持仓和钱包子同步。"""
        sync = _make_sync()
        mock_conn = _make_mock_conn()
        with patch.object(sync, "_get_conn", return_value=mock_conn), \
             patch.object(sync, "_sync_executions") as m_exec, \
             patch.object(sync, "_sync_positions") as m_pos, \
             patch.object(sync, "_sync_wallet") as m_wal:
            sync._sync()
        m_exec.assert_called_once()
        m_pos.assert_called_once()
        m_wal.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 3: _sync_executions()
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncExecutions:
    """Test execution sync logic. 测试执行记录同步逻辑。"""

    def test_sync_executions_inserts_records(self):
        """Executions from API are inserted into PG.
        API 返回的执行记录被插入到 PG。"""
        connector = _make_demo_connector()
        connector.get_executions.return_value = {
            "retCode": 0,
            "result": {"list": [
                {
                    "execTime": "1700000000000",
                    "execId": "ex_001",
                    "orderId": "ord_001",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "execType": "Trade",
                    "execQty": "0.01",
                    "execPrice": "60000",
                    "execFee": "0.36",
                    "feeCurrency": "USDT",
                },
            ]},
        }
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_executions(cur, 1700000000000)
        cur.execute.assert_called_once()
        assert sync._stats["executions_synced"] == 1

    def test_sync_executions_skips_on_nonzero_retcode(self):
        """Non-zero retCode means API error — skip.
        非零 retCode 表示 API 错误 — 跳过。"""
        connector = _make_demo_connector()
        connector.get_executions.return_value = {"retCode": 10001, "retMsg": "error"}
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_executions(cur, 1700000000000)
        cur.execute.assert_not_called()
        assert sync._stats["executions_synced"] == 0

    def test_sync_executions_handles_api_exception(self):
        """API call exception is caught gracefully.
        API 调用异常被优雅捕获。"""
        connector = _make_demo_connector()
        connector.get_executions.side_effect = ConnectionError("timeout")
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_executions(cur, 1700000000000)  # Should not raise
        assert sync._stats["executions_synced"] == 0

    def test_sync_executions_multiple_records(self):
        """Multiple executions are all inserted.
        多条执行记录全部被插入。"""
        connector = _make_demo_connector()
        execs = [
            {"execId": f"ex_{i}", "orderId": f"ord_{i}", "symbol": "ETHUSDT",
             "side": "Sell", "execQty": "1.0", "execPrice": "3000", "execFee": "0.1"}
            for i in range(5)
        ]
        connector.get_executions.return_value = {"retCode": 0, "result": {"list": execs}}
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_executions(cur, 1700000000000)
        assert cur.execute.call_count == 5
        assert sync._stats["executions_synced"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 4: _sync_positions()
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncPositions:
    """Test position sync logic. 测试持仓同步逻辑。"""

    def test_sync_positions_both_categories(self):
        """Positions are queried for both linear and inverse.
        线性和反向品类都会被查询。"""
        connector = _make_demo_connector()
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_positions(cur, 1700000000000)
        # get_positions called twice: once for linear, once for inverse
        assert connector.get_positions.call_count == 2
        calls = [c.kwargs.get("category") for c in connector.get_positions.call_args_list]
        assert "linear" in calls
        assert "inverse" in calls

    def test_sync_positions_skips_zero_size(self):
        """Positions with size=0 are skipped.
        大小为 0 的持仓被跳过。"""
        connector = _make_demo_connector()
        connector.get_positions.return_value = {
            "retCode": 0,
            "result": {"list": [
                {"symbol": "BTCUSDT", "size": "0", "side": "Buy"},
            ]},
        }
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_positions(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_sync_positions_inserts_nonzero(self):
        """Non-zero positions are inserted. 非零持仓被插入。"""
        connector = _make_demo_connector()
        connector.get_positions.return_value = {
            "retCode": 0,
            "result": {"list": [
                {
                    "symbol": "BTCUSDT", "size": "0.5", "side": "Buy",
                    "avgPrice": "60000", "markPrice": "61000",
                    "unrealisedPnl": "500", "leverage": "10",
                    "positionValue": "30000",
                },
            ]},
        }
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_positions(cur, 1700000000000)
        # Called for both linear and inverse; both return the same mock
        assert cur.execute.call_count == 2
        assert sync._stats["positions_synced"] == 2

    def test_sync_positions_skips_on_nonzero_retcode(self):
        """Non-zero retCode skips that category.
        非零 retCode 跳过该品类。"""
        connector = _make_demo_connector()
        connector.get_positions.return_value = {"retCode": 10001, "retMsg": "fail"}
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_positions(cur, 1700000000000)
        cur.execute.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 5: _sync_wallet()
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncWallet:
    """Test wallet balance sync logic. 测试钱包余额同步逻辑。"""

    def test_sync_wallet_inserts_balance(self):
        """Wallet balance is aggregated and inserted.
        钱包余额被汇总并插入。"""
        connector = _make_demo_connector()
        connector.get_wallet_balance.return_value = {
            "retCode": 0,
            "result": {"list": [{"coin": [
                {"coin": "USDT", "equity": "10000", "walletBalance": "9500", "unrealisedPnl": "500"},
                {"coin": "BTC", "equity": "1.5", "walletBalance": "1.5", "unrealisedPnl": "0"},
            ]}]},
        }
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_wallet(cur, 1700000000000)
        cur.execute.assert_called_once()
        # Verify the SQL params include aggregated values
        call_args = cur.execute.call_args
        params = call_args[0][1]
        # total_equity = 10000 + 1.5 = 10001.5
        assert params[1] == 10001.5
        # total_balance = 9500 + 1.5 = 9501.5
        assert params[2] == 9501.5
        # unrealized = 500 + 0 = 500
        assert params[3] == 500.0
        # account_type
        assert params[4] == "bybit_demo"

    def test_sync_wallet_skips_on_nonzero_retcode(self):
        """Non-zero retCode skips wallet sync.
        非零 retCode 跳过钱包同步。"""
        connector = _make_demo_connector()
        connector.get_wallet_balance.return_value = {"retCode": 10001}
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_wallet(cur, 1700000000000)
        cur.execute.assert_not_called()

    def test_sync_wallet_handles_exception(self):
        """Wallet API exception is caught gracefully.
        钱包 API 异常被优雅捕获。"""
        connector = _make_demo_connector()
        connector.get_wallet_balance.side_effect = RuntimeError("api down")
        sync = _make_sync(connector)
        cur = _make_mock_cursor()
        sync._sync_wallet(cur, 1700000000000)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 6: get_current_snapshot() — reconciliation format
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetCurrentSnapshot:
    """Test reconciliation snapshot building.
    测试对账快照构建。"""

    def test_snapshot_with_positions_and_balance(self):
        """Snapshot includes positions and balances.
        快照包含持仓和余额。"""
        connector = _make_demo_connector()
        connector.get_positions.return_value = {
            "retCode": 0,
            "result": {"list": [
                {"symbol": "BTCUSDT", "size": "0.5", "side": "Buy", "avgPrice": "60000"},
            ]},
        }
        connector.get_wallet_balance.return_value = {
            "retCode": 0,
            "result": {"list": [{"coin": [
                {"coin": "USDT", "walletBalance": "5000"},
            ]}]},
        }
        sync = _make_sync(connector)
        snap = sync.get_current_snapshot()

        assert snap is not None
        assert "snapshot_ts_ms" in snap
        assert isinstance(snap["snapshot_ts_ms"], int)
        assert snap["orders"] == []
        assert snap["fills"] == []
        assert snap["spot_positions_excluded"] is True

        # BTCUSDT appears in positions (queried for both linear and inverse)
        assert "BTCUSDT" in snap["positions"]
        pos = snap["positions"]["BTCUSDT"]
        assert pos["side"] == "Buy"
        assert pos["size"] == 0.5
        assert pos["avg_entry_price"] == 60000.0

        # Balance
        assert "USDT" in snap["balances"]
        assert snap["balances"]["USDT"] == 5000.0

    def test_snapshot_skips_zero_size_positions(self):
        """Zero-size positions excluded from snapshot.
        零大小持仓被排除。"""
        connector = _make_demo_connector()
        connector.get_positions.return_value = {
            "retCode": 0,
            "result": {"list": [
                {"symbol": "BTCUSDT", "size": "0", "side": "Buy"},
            ]},
        }
        sync = _make_sync(connector)
        snap = sync.get_current_snapshot()
        assert snap is not None
        assert len(snap["positions"]) == 0

    def test_snapshot_skips_zero_balance(self):
        """Zero-balance coins excluded from snapshot.
        零余额币种被排除。"""
        connector = _make_demo_connector()
        connector.get_wallet_balance.return_value = {
            "retCode": 0,
            "result": {"list": [{"coin": [
                {"coin": "BTC", "walletBalance": "0"},
            ]}]},
        }
        sync = _make_sync(connector)
        snap = sync.get_current_snapshot()
        assert snap is not None
        assert len(snap["balances"]) == 0

    def test_snapshot_returns_none_on_exception(self):
        """Exception in snapshot building returns None.
        构建快照时异常返回 None。"""
        connector = _make_demo_connector()
        connector.get_positions.side_effect = RuntimeError("api crash")
        sync = _make_sync(connector)
        snap = sync.get_current_snapshot()
        assert snap is None

    def test_snapshot_continues_when_one_category_fails(self):
        """If one category fails, other category still included.
        一个品类失败时，另一个品类仍被包含。"""
        connector = _make_demo_connector()
        call_count = [0]

        def mock_get_positions(category=None):
            call_count[0] += 1
            if category == "linear":
                return {"retCode": 10001, "retMsg": "fail"}
            return {
                "retCode": 0,
                "result": {"list": [
                    {"symbol": "BTCUSD", "size": "100", "side": "Buy", "avgPrice": "60000"},
                ]},
            }

        connector.get_positions = mock_get_positions
        sync = _make_sync(connector)
        snap = sync.get_current_snapshot()
        assert snap is not None
        assert "BTCUSD" in snap["positions"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class 7: _loop() error handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncLoop:
    """Test the background loop error handling.
    测试后台循环错误处理。"""

    def test_loop_increments_error_count_on_exception(self):
        """_loop() increments errors stat on exception.
        _loop() 在异常时递增错误计数。"""
        sync = _make_sync()
        sync._running = True
        call_count = [0]

        def mock_sync():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("sync failed")
            sync._running = False  # Stop after second call

        with patch.object(sync, "_sync", side_effect=mock_sync), \
             patch("time.sleep", return_value=None):
            sync._loop()

        assert sync._stats["errors"] == 1

    def test_pg_connection_failure_returns_none(self):
        """_get_conn returns None when both pool and direct connect fail.
        連接池和直連都失敗時 _get_conn 返回 None。"""
        sync = _make_sync()
        with patch("app.db_pool.get_conn", return_value=None), \
             patch.dict(sys.modules, {"psycopg2": MagicMock()}):
            mock_pg = sys.modules["psycopg2"]
            mock_pg.connect.side_effect = Exception("connection refused")
            result = sync._get_conn()
            assert result is None
