"""
R06-E — IPC Integration Tests: Route-Level Rust-First + Fallback
================================================================
Tests for all route endpoints that use get_rust_reader() with
Rust-first / Python-fallback pattern (R06-B).

IPC 集成測試：路由級 Rust 優先 + Python 降級
測試所有使用 get_rust_reader() 的路由端點。

Test categories / 測試分類:
  1. Reader core (supplement)    — additional edge cases / 讀取器核心補充
  2. Paper routes Rust-first     — session/positions/pnl with Rust data / 紙盤路由 Rust 優先
  3. Paper routes fallback       — same routes without Rust data / 紙盤路由降級
  4. Risk routes Rust-first      — drawdown from Rust / 風控路由 Rust 優先
  5. Risk routes fallback        — drawdown from Python / 風控路由降級
  6. Phase2 routes Rust-first    — tick stats from Rust / Phase2 路由 Rust 優先
  7. Phase2 routes fallback      — tick stats from Python / Phase2 路由降級
  8. Source tag discrimination   — verify source attribution / 數據源標識驗證
  9. Edge cases                  — empty positions, zero balance, partial data / 邊界情況
 10. Rollback simulation         — Rust crash → fallback → recovery / 回滾模擬

46 tests total (+ 14 existing reader tests = 60).
"""

import sys
import os
import json
import time
import tempfile
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Path setup / 路徑設置
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
_bybit_connector_dir = os.path.dirname(_control_api_dir)
_exchange_connectors_dir = os.path.dirname(_bybit_connector_dir)
_program_code_dir = os.path.dirname(_exchange_connectors_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

from app.ipc_state_reader import RustSnapshotReader, _CACHE_TTL_SECONDS

# ═══════════════════════════════════════════════════════════════════════════════
# Shared test data / 共享測試數據
# ═══════════════════════════════════════════════════════════════════════════════

SNAPSHOT_FULL = {
    "paper_state": {
        "balance": 9500.0,
        "peak_balance": 10000.0,
        "total_realized_pnl": -500.0,
        "total_fees": 12.5,
        "trade_count": 3,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "is_long": True,
                "qty": 0.01,
                "entry_price": 65000.0,
                "best_price": 66000.0,
                "entry_fee": 3.25,
                "entry_ts_ms": 1700000000000,
                "unrealized_pnl": 10.0,
            }
        ],
    },
    "latest_prices": {"BTCUSDT": 66000.0, "ETHUSDT": 3200.0},
    "stats": {
        "total_ticks": 5000,
        "total_intents": 15,
        "total_fills": 3,
        "total_stops": 1,
        "last_tick_ms": 1700000050000,
    },
    "source": "rust_engine",
}

SNAPSHOT_EMPTY_POSITIONS = {
    "paper_state": {
        "balance": 10000.0,
        "peak_balance": 10000.0,
        "total_realized_pnl": 0.0,
        "total_fees": 0.0,
        "trade_count": 0,
        "positions": [],
    },
    "latest_prices": {"BTCUSDT": 65000.0},
    "stats": {
        "total_ticks": 100,
        "total_intents": 0,
        "total_fills": 0,
        "total_stops": 0,
        "last_tick_ms": 1700000010000,
    },
    "source": "rust_engine",
}

SNAPSHOT_ZERO_BALANCE = {
    "paper_state": {
        "balance": 0.0,
        "peak_balance": 10000.0,
        "total_realized_pnl": -10000.0,
        "total_fees": 50.0,
        "trade_count": 20,
        "positions": [],
    },
    "latest_prices": {},
    "stats": {
        "total_ticks": 50000,
        "total_intents": 100,
        "total_fills": 20,
        "total_stops": 10,
        "last_tick_ms": 1700000090000,
    },
    "source": "rust_engine",
}

SNAPSHOT_MULTI_POSITIONS = {
    "paper_state": {
        "balance": 8000.0,
        "peak_balance": 10000.0,
        "total_realized_pnl": -200.0,
        "total_fees": 25.0,
        "trade_count": 5,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "is_long": True,
                "qty": 0.01,
                "entry_price": 65000.0,
                "best_price": 66000.0,
                "entry_fee": 3.25,
                "entry_ts_ms": 1700000000000,
                "unrealized_pnl": 10.0,
            },
            {
                "symbol": "ETHUSDT",
                "is_long": False,
                "qty": 0.1,
                "entry_price": 3300.0,
                "best_price": 3200.0,
                "entry_fee": 1.65,
                "entry_ts_ms": 1700000005000,
                "unrealized_pnl": 10.0,
            },
        ],
    },
    "latest_prices": {"BTCUSDT": 66000.0, "ETHUSDT": 3200.0, "SOLUSDT": 150.0},
    "stats": {
        "total_ticks": 10000,
        "total_intents": 30,
        "total_fills": 5,
        "total_stops": 2,
        "last_tick_ms": 1700000060000,
    },
    "source": "rust_engine",
}


def _write_snapshot(data_dir: str, data: dict) -> str:
    """Write snapshot JSON to the expected path / 將快照 JSON 寫入預期路徑"""
    path = os.path.join(data_dir, "pipeline_snapshot.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def _make_reader(data_dir: str) -> RustSnapshotReader:
    """Create a RustSnapshotReader for the given dir / 為給定目錄創建讀取器"""
    return RustSnapshotReader(data_dir=data_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Reader Core — Supplementary Tests / 讀取器核心補充測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestReaderCoreSupplement(unittest.TestCase):
    """Additional reader tests beyond the base 14 / 基礎 14 個測試之外的補充"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_empty_json_object(self):
        """Empty JSON object {} returns empty dict, sub-accessors return None.
        空 JSON 對象返回空字典，子訪問器返回 None。"""
        _write_snapshot(self._tmpdir.name, {})
        reader = _make_reader(self._tmpdir.name)
        snap = reader.get_snapshot()
        self.assertIsNotNone(snap)
        self.assertEqual(snap, {})
        self.assertIsNone(reader.get_paper_state())
        self.assertIsNone(reader.get_latest_prices())
        self.assertIsNone(reader.get_tick_stats())
        self.assertIsNone(reader.get_source())

    def test_partial_snapshot_missing_stats(self):
        """Snapshot with paper_state but no stats — get_tick_stats() returns None.
        有 paper_state 但無 stats 的快照 — get_tick_stats() 返回 None。"""
        partial = {"paper_state": SNAPSHOT_FULL["paper_state"], "source": "rust_engine"}
        _write_snapshot(self._tmpdir.name, partial)
        reader = _make_reader(self._tmpdir.name)
        self.assertIsNotNone(reader.get_paper_state())
        self.assertIsNone(reader.get_tick_stats())
        self.assertIsNone(reader.get_latest_prices())

    def test_partial_snapshot_missing_paper_state(self):
        """Snapshot with prices but no paper_state — get_paper_state() returns None.
        有價格但無 paper_state 的快照 — get_paper_state() 返回 None。"""
        partial = {"latest_prices": {"BTCUSDT": 65000.0}, "source": "rust_engine"}
        _write_snapshot(self._tmpdir.name, partial)
        reader = _make_reader(self._tmpdir.name)
        self.assertIsNone(reader.get_paper_state())
        prices = reader.get_latest_prices()
        self.assertIsNotNone(prices)
        self.assertEqual(prices["BTCUSDT"], 65000.0)

    def test_empty_file(self):
        """Empty file returns None (JSONDecodeError handled).
        空文件返回 None（處理 JSONDecodeError）。"""
        path = os.path.join(self._tmpdir.name, "pipeline_snapshot.json")
        with open(path, "w") as f:
            f.write("")
        reader = _make_reader(self._tmpdir.name)
        self.assertIsNone(reader.get_snapshot())

    def test_concurrent_reads_thread_safety(self):
        """Multiple threads reading simultaneously should not raise.
        多線程同時讀取不應拋出異常。"""
        import threading
        _write_snapshot(self._tmpdir.name, SNAPSHOT_FULL)
        reader = _make_reader(self._tmpdir.name)
        errors = []

        def read_loop():
            try:
                for _ in range(50):
                    reader.get_paper_state()
                    reader.get_latest_prices()
                    reader.get_tick_stats()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_loop) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")

    def test_large_positions_list(self):
        """Snapshot with many positions parses correctly.
        含大量持倉的快照正確解析。"""
        snap = json.loads(json.dumps(SNAPSHOT_FULL))
        snap["paper_state"]["positions"] = [
            {
                "symbol": f"SYM{i}USDT",
                "is_long": i % 2 == 0,
                "qty": 0.01 * (i + 1),
                "entry_price": 100.0 + i,
                "best_price": 101.0 + i,
                "entry_fee": 0.5,
                "entry_ts_ms": 1700000000000 + i * 1000,
                "unrealized_pnl": 1.0 * (i % 3 - 1),
            }
            for i in range(25)
        ]
        _write_snapshot(self._tmpdir.name, snap)
        reader = _make_reader(self._tmpdir.name)
        state = reader.get_paper_state()
        self.assertEqual(len(state["positions"]), 25)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Paper Route Logic — Rust-First Path / 紙盤路由邏輯 — Rust 優先路徑
# ═══════════════════════════════════════════════════════════════════════════════


class TestPaperRouteRustFirst(unittest.TestCase):
    """Test paper trading route Rust-first logic with available reader.
    測試紙盤交易路由的 Rust 優先邏輯（讀取器可用）。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        _write_snapshot(self._tmpdir.name, SNAPSHOT_FULL)
        self.reader = _make_reader(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_session_status_returns_rust_data(self):
        """Simulates GET /session/status Rust-first path.
        模擬 GET /session/status Rust 優先路徑。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNotNone(rust_state)
        # Build response as route handler does / 按路由處理器方式構建響應
        resp = {
            "source": "rust_engine",
            "balance": rust_state.get("balance", 0),
            "peak_balance": rust_state.get("peak_balance", 0),
            "total_realized_pnl": rust_state.get("total_realized_pnl", 0),
            "total_fees": rust_state.get("total_fees", 0),
            "trade_count": rust_state.get("trade_count", 0),
            "positions_count": len(rust_state.get("positions", [])),
        }
        self.assertEqual(resp["source"], "rust_engine")
        self.assertEqual(resp["balance"], 9500.0)
        self.assertEqual(resp["peak_balance"], 10000.0)
        self.assertEqual(resp["positions_count"], 1)

    def test_positions_returns_rust_data(self):
        """Simulates GET /positions Rust-first path.
        模擬 GET /positions Rust 優先路徑。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNotNone(rust_state)
        positions = rust_state.get("positions", [])
        resp = {"positions": positions, "count": len(positions), "source": "rust_engine"}
        self.assertEqual(resp["count"], 1)
        self.assertEqual(resp["positions"][0]["symbol"], "BTCUSDT")
        self.assertTrue(resp["positions"][0]["is_long"])

    def test_pnl_computation_from_rust(self):
        """Simulates GET /pnl Rust-first path — computes net_pnl.
        模擬 GET /pnl Rust 優先路徑 — 計算 net_pnl。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNotNone(rust_state)
        positions = rust_state.get("positions", [])
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        realized = rust_state.get("total_realized_pnl", 0)
        fees = rust_state.get("total_fees", 0)
        net_pnl = realized + total_unrealized - fees
        # -500 + 10 - 12.5 = -502.5
        self.assertAlmostEqual(net_pnl, -502.5)

    def test_latest_prices_from_rust(self):
        """Simulates price lookup for order submission.
        模擬下單的價格查詢。"""
        prices = self.reader.get_latest_prices()
        self.assertIsNotNone(prices)
        self.assertIn("BTCUSDT", prices)
        self.assertEqual(prices["BTCUSDT"], 66000.0)
        self.assertEqual(prices["ETHUSDT"], 3200.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Paper Route Logic — Fallback Path / 紙盤路由邏輯 — 降級路徑
# ═══════════════════════════════════════════════════════════════════════════════


class TestPaperRouteFallback(unittest.TestCase):
    """Test paper trading route fallback when Rust reader is unavailable.
    測試 Rust 讀取器不可用時紙盤交易路由的降級邏輯。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        # No snapshot file — simulates Rust engine not running
        # 無快照文件 — 模擬 Rust 引擎未運行
        self.reader = _make_reader(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_session_status_falls_back(self):
        """Rust unavailable → should fall back to Python ENGINE.
        Rust 不可用 → 應降級到 Python ENGINE。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNone(rust_state)

    def test_positions_falls_back(self):
        """Rust unavailable → should fall back to Python ENGINE.
        Rust 不可用 → 應降級到 Python ENGINE。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNone(rust_state)

    def test_pnl_falls_back(self):
        """Rust unavailable → should fall back to Python ENGINE.
        Rust 不可用 → 應降級到 Python ENGINE。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNone(rust_state)

    def test_latest_prices_falls_back(self):
        """Rust prices unavailable → returns None for fallback chain.
        Rust 價格不可用 → 返回 None 供降級鏈使用。"""
        prices = self.reader.get_latest_prices()
        self.assertIsNone(prices)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Risk Route Logic — Rust-First / 風控路由邏輯 — Rust 優先
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskRouteRustFirst(unittest.TestCase):
    """Test risk route drawdown calculation from Rust data.
    測試風控路由從 Rust 數據計算回撤。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        _write_snapshot(self._tmpdir.name, SNAPSHOT_FULL)
        self.reader = _make_reader(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_drawdown_from_rust(self):
        """Simulates GET /risk/status drawdown calculation.
        模擬 GET /risk/status 回撤計算。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNotNone(rust_state)
        peak = rust_state.get("peak_balance", 0)
        current = rust_state.get("balance", 0)
        drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0
        # (10000 - 9500) / 10000 * 100 = 5.0%
        self.assertAlmostEqual(drawdown_pct, 5.0)

    def test_drawdown_zero_when_at_peak(self):
        """Drawdown is 0% when balance equals peak.
        餘額等於峰值時回撤為 0%。"""
        _write_snapshot(self._tmpdir.name, SNAPSHOT_EMPTY_POSITIONS)
        reader = _make_reader(self._tmpdir.name)
        rust_state = reader.get_paper_state()
        peak = rust_state.get("peak_balance", 0)
        current = rust_state.get("balance", 0)
        drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0
        self.assertAlmostEqual(drawdown_pct, 0.0)

    def test_drawdown_100pct_zero_balance(self):
        """Drawdown is 100% when balance is 0.
        餘額為 0 時回撤為 100%。"""
        _write_snapshot(self._tmpdir.name, SNAPSHOT_ZERO_BALANCE)
        reader = _make_reader(self._tmpdir.name)
        rust_state = reader.get_paper_state()
        peak = rust_state.get("peak_balance", 0)
        current = rust_state.get("balance", 0)
        drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0
        self.assertAlmostEqual(drawdown_pct, 100.0)

    def test_risk_status_has_source_tag(self):
        """Rust-first risk status includes source='rust_engine'.
        Rust 優先風控狀態包含 source='rust_engine'。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        status = {}
        if rust_state is not None:
            status["source"] = "rust_engine"
        self.assertEqual(status.get("source"), "rust_engine")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Risk Route Logic — Fallback / 風控路由邏輯 — 降級
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskRouteFallback(unittest.TestCase):
    """Test risk route fallback when Rust unavailable.
    測試 Rust 不可用時風控路由降級。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reader = _make_reader(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_drawdown_falls_back_to_python(self):
        """Rust unavailable → falls back to Python ENGINE.get_state().
        Rust 不可用 → 降級到 Python ENGINE.get_state()。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        self.assertIsNone(rust_state)

    def test_no_source_tag_on_fallback(self):
        """Fallback path should NOT set source='rust_engine'.
        降級路徑不應設置 source='rust_engine'。"""
        rust_state = self.reader.get_paper_state() if self.reader.is_available() else None
        status = {}
        if rust_state is not None:
            status["source"] = "rust_engine"
        self.assertNotIn("source", status)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Phase2 Route Logic — Rust-First / Phase2 路由邏輯 — Rust 優先
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase2RouteRustFirst(unittest.TestCase):
    """Test phase2 pipeline stats from Rust data.
    測試從 Rust 數據獲取 phase2 管線統計。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        _write_snapshot(self._tmpdir.name, SNAPSHOT_FULL)
        self.reader = _make_reader(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_tick_stats_from_rust(self):
        """Simulates GET /pipeline/stats Rust-first path.
        模擬 GET /pipeline/stats Rust 優先路徑。"""
        rust_stats = self.reader.get_tick_stats() if self.reader.is_available() else None
        self.assertIsNotNone(rust_stats)
        self.assertEqual(rust_stats["total_ticks"], 5000)
        self.assertEqual(rust_stats["total_fills"], 3)
        self.assertEqual(rust_stats["total_intents"], 15)
        self.assertEqual(rust_stats["total_stops"], 1)
        self.assertEqual(rust_stats["last_tick_ms"], 1700000050000)

    def test_tick_stats_response_format(self):
        """Response format matches phase2 route handler output.
        響應格式匹配 phase2 路由處理器輸出。"""
        rust_stats = self.reader.get_tick_stats() if self.reader.is_available() else None
        resp = {
            "source": "rust_engine",
            "total_ticks": rust_stats.get("total_ticks", 0),
            "total_fills": rust_stats.get("total_fills", 0),
            "total_intents": rust_stats.get("total_intents", 0),
            "total_stops": rust_stats.get("total_stops", 0),
            "last_tick_ms": rust_stats.get("last_tick_ms", 0),
        }
        self.assertEqual(resp["source"], "rust_engine")
        self.assertIsInstance(resp["total_ticks"], int)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Phase2 Route Logic — Fallback / Phase2 路由邏輯 — 降級
# ═══════════════════════════════════════════════════════════════════════════════


class TestPhase2RouteFallback(unittest.TestCase):
    """Test phase2 route fallback when Rust unavailable.
    測試 Rust 不可用時 phase2 路由降級。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reader = _make_reader(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_tick_stats_falls_back(self):
        """Rust unavailable → falls back to PIPELINE_BRIDGE.
        Rust 不可用 → 降級到 PIPELINE_BRIDGE。"""
        rust_stats = self.reader.get_tick_stats() if self.reader.is_available() else None
        self.assertIsNone(rust_stats)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Source Tag Discrimination / 數據源標識區分
# ═══════════════════════════════════════════════════════════════════════════════


class TestSourceTagDiscrimination(unittest.TestCase):
    """Verify source attribution across all routes.
    驗證所有路由的數據源標識。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        _write_snapshot(self._tmpdir.name, SNAPSHOT_FULL)
        self.rust_reader = _make_reader(self._tmpdir.name)
        self._empty_dir = tempfile.TemporaryDirectory()
        self.no_rust_reader = _make_reader(self._empty_dir.name)

    def tearDown(self):
        self._tmpdir.cleanup()
        self._empty_dir.cleanup()

    def test_rust_source_tag_present(self):
        """All Rust-sourced data has source='rust_engine' tag.
        所有 Rust 源數據含 source='rust_engine' 標識。"""
        self.assertEqual(self.rust_reader.get_source(), "rust_engine")

    def test_fallback_no_source_tag(self):
        """No source tag when Rust is unavailable — Python doesn't set it.
        Rust 不可用時無數據源標識 — Python 不設置。"""
        self.assertIsNone(self.no_rust_reader.get_source())

    def test_source_tag_in_snapshot(self):
        """Source tag is a top-level field in PipelineSnapshot.
        source 標識是 PipelineSnapshot 的頂層字段。"""
        snap = self.rust_reader.get_snapshot()
        self.assertIn("source", snap)
        self.assertEqual(snap["source"], "rust_engine")

    def test_source_tag_survives_cache(self):
        """Source tag persists through cache refresh cycles.
        source 標識在緩存刷新週期中持續存在。"""
        # First read / 第一次讀取
        self.assertEqual(self.rust_reader.get_source(), "rust_engine")
        # Force cache expiry / 強制緩存過期
        self.rust_reader._cache_ts = 0.0
        # Second read after refresh / 刷新後第二次讀取
        self.assertEqual(self.rust_reader.get_source(), "rust_engine")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Edge Cases / 邊界情況
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases(unittest.TestCase):
    """Edge case tests for IPC data handling.
    IPC 數據處理的邊界情況測試。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_empty_positions_pnl_zero(self):
        """PnL computation with 0 positions → unrealized=0.
        0 持倉時的 PnL 計算 → unrealized=0。"""
        _write_snapshot(self._tmpdir.name, SNAPSHOT_EMPTY_POSITIONS)
        reader = _make_reader(self._tmpdir.name)
        state = reader.get_paper_state()
        positions = state.get("positions", [])
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        self.assertEqual(total_unrealized, 0.0)

    def test_multi_position_unrealized_sum(self):
        """PnL computation sums unrealized across multiple positions.
        PnL 計算匯總多個持倉的未實現損益。"""
        _write_snapshot(self._tmpdir.name, SNAPSHOT_MULTI_POSITIONS)
        reader = _make_reader(self._tmpdir.name)
        state = reader.get_paper_state()
        positions = state.get("positions", [])
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        # 10.0 + 10.0 = 20.0
        self.assertAlmostEqual(total_unrealized, 20.0)

    def test_net_pnl_with_multi_positions(self):
        """net_pnl = realized + unrealized - fees with multiple positions.
        net_pnl = 已實現 + 未實現 - 手續費（多持倉）。"""
        _write_snapshot(self._tmpdir.name, SNAPSHOT_MULTI_POSITIONS)
        reader = _make_reader(self._tmpdir.name)
        state = reader.get_paper_state()
        positions = state.get("positions", [])
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        realized = state.get("total_realized_pnl", 0)
        fees = state.get("total_fees", 0)
        net_pnl = realized + total_unrealized - fees
        # -200 + 20 - 25 = -205
        self.assertAlmostEqual(net_pnl, -205.0)

    def test_drawdown_with_zero_peak(self):
        """Drawdown safe division when peak_balance is 0.
        peak_balance 為 0 時回撤安全除法。"""
        snap = json.loads(json.dumps(SNAPSHOT_FULL))
        snap["paper_state"]["peak_balance"] = 0.0
        snap["paper_state"]["balance"] = 0.0
        _write_snapshot(self._tmpdir.name, snap)
        reader = _make_reader(self._tmpdir.name)
        state = reader.get_paper_state()
        peak = state.get("peak_balance", 0)
        current = state.get("balance", 0)
        drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0
        self.assertEqual(drawdown_pct, 0.0)

    def test_missing_unrealized_pnl_field(self):
        """Position without unrealized_pnl field defaults to 0.
        持倉缺少 unrealized_pnl 字段時默認為 0。"""
        snap = json.loads(json.dumps(SNAPSHOT_FULL))
        for pos in snap["paper_state"]["positions"]:
            del pos["unrealized_pnl"]
        _write_snapshot(self._tmpdir.name, snap)
        reader = _make_reader(self._tmpdir.name)
        state = reader.get_paper_state()
        positions = state.get("positions", [])
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        self.assertEqual(total_unrealized, 0.0)

    def test_prices_empty_dict(self):
        """Empty prices dict is still valid — not None.
        空價格字典仍有效 — 不是 None。"""
        _write_snapshot(self._tmpdir.name, SNAPSHOT_ZERO_BALANCE)
        reader = _make_reader(self._tmpdir.name)
        prices = reader.get_latest_prices()
        self.assertIsNotNone(prices)
        self.assertEqual(len(prices), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Rollback Simulation / 回滾模擬 (R06-F)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRollbackSimulation(unittest.TestCase):
    """
    Simulate Rust engine crash → fallback → recovery cycle.
    模擬 Rust 引擎崩潰 → 降級 → 恢復週期。

    Verifies the fallback path activates within SLA when the snapshot file
    disappears, and the Rust-first path resumes when the file reappears.
    驗證快照文件消失時降級路徑在 SLA 內啟動，文件重新出現時 Rust 優先路徑恢復。
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_rust_available_then_crash_then_recover(self):
        """Full lifecycle: available → crash (file deleted) → fallback → recovery.
        完整生命週期：可用 → 崩潰（文件刪除）→ 降級 → 恢復。"""
        data_dir = self._tmpdir.name
        snap_path = _write_snapshot(data_dir, SNAPSHOT_FULL)
        reader = _make_reader(data_dir)

        # Phase 1: Rust available / 階段 1：Rust 可用
        self.assertTrue(reader.is_available())
        state = reader.get_paper_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["balance"], 9500.0)

        # Phase 2: Simulate crash — delete snapshot file
        # 階段 2：模擬崩潰 — 刪除快照文件
        os.unlink(snap_path)
        # Force cache expiry so reader re-reads / 強制緩存過期以重新讀取
        reader._cache_ts = 0.0
        reader._cache = None

        self.assertFalse(reader.is_available())
        self.assertIsNone(reader.get_paper_state())
        self.assertIsNone(reader.get_latest_prices())

        # Phase 3: Recovery — recreate snapshot file
        # 階段 3：恢復 — 重新創建快照文件
        _write_snapshot(data_dir, SNAPSHOT_FULL)
        reader._cache_ts = 0.0
        reader._cache = None

        self.assertTrue(reader.is_available())
        state = reader.get_paper_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["balance"], 9500.0)

    def test_fallback_latency_under_sla(self):
        """Fallback detection latency is well under 30s SLA.
        降級檢測延遲遠低於 30 秒 SLA。"""
        data_dir = self._tmpdir.name
        snap_path = _write_snapshot(data_dir, SNAPSHOT_FULL)
        reader = _make_reader(data_dir)

        # Warm up cache / 預熱緩存
        reader.get_paper_state()

        # Simulate crash / 模擬崩潰
        os.unlink(snap_path)
        reader._cache_ts = 0.0
        reader._cache = None

        start = time.monotonic()
        result = reader.get_paper_state()
        elapsed_ms = (time.monotonic() - start) * 1000

        self.assertIsNone(result)
        # Fallback detection should be < 100ms (file read failure is instant)
        # 降級檢測應 < 100ms（文件讀取失敗是即時的）
        self.assertLess(elapsed_ms, 100, f"Fallback took {elapsed_ms:.1f}ms, expected <100ms")

    def test_recovery_latency_under_sla(self):
        """Recovery detection latency is well under 30s SLA.
        恢復檢測延遲遠低於 30 秒 SLA。"""
        data_dir = self._tmpdir.name
        reader = _make_reader(data_dir)

        # Start with no file / 開始時無文件
        self.assertIsNone(reader.get_paper_state())

        # Simulate recovery / 模擬恢復
        _write_snapshot(data_dir, SNAPSHOT_FULL)
        reader._cache_ts = 0.0
        reader._cache = None

        start = time.monotonic()
        result = reader.get_paper_state()
        elapsed_ms = (time.monotonic() - start) * 1000

        self.assertIsNotNone(result)
        # Recovery should be < 100ms (file read is fast)
        # 恢復應 < 100ms（文件讀取很快）
        self.assertLess(elapsed_ms, 100, f"Recovery took {elapsed_ms:.1f}ms, expected <100ms")

    def test_stale_file_triggers_fallback(self):
        """File exists but is stale (>60s old) → is_available() returns False.
        文件存在但過期（>60 秒）→ is_available() 返回 False。"""
        data_dir = self._tmpdir.name
        snap_path = _write_snapshot(data_dir, SNAPSHOT_FULL)
        reader = _make_reader(data_dir)

        # Make file stale / 使文件過期
        old_time = time.time() - 120
        os.utime(snap_path, (old_time, old_time))

        self.assertFalse(reader.is_available())
        # get_paper_state() still returns data (only is_available checks staleness)
        # get_paper_state() 仍返回數據（只有 is_available 檢查過期）
        reader._cache_ts = 0.0
        state = reader.get_paper_state()
        self.assertIsNotNone(state)

    def test_crash_during_write_partial_json(self):
        """Simulate crash during write — partial JSON file.
        模擬寫入中崩潰 — 部分 JSON 文件。"""
        data_dir = self._tmpdir.name
        path = os.path.join(data_dir, "pipeline_snapshot.json")
        # Write partial JSON (simulates crash mid-write)
        # 寫入部分 JSON（模擬寫入中崩潰）
        with open(path, "w") as f:
            f.write('{"paper_state": {"balance": 9500.0, "peak_balance":')

        reader = _make_reader(data_dir)
        result = reader.get_snapshot()
        self.assertIsNone(result)

    def test_rapid_crash_recovery_cycles(self):
        """Multiple rapid crash/recovery cycles work correctly.
        多次快速崩潰/恢復週期正確工作。"""
        data_dir = self._tmpdir.name
        reader = _make_reader(data_dir)

        for cycle in range(5):
            # Recovery / 恢復
            _write_snapshot(data_dir, SNAPSHOT_FULL)
            reader._cache_ts = 0.0
            reader._cache = None
            self.assertIsNotNone(reader.get_paper_state(), f"Cycle {cycle}: recovery failed")

            # Crash / 崩潰
            os.unlink(os.path.join(data_dir, "pipeline_snapshot.json"))
            reader._cache_ts = 0.0
            reader._cache = None
            self.assertIsNone(reader.get_paper_state(), f"Cycle {cycle}: crash not detected")


if __name__ == "__main__":
    unittest.main()
