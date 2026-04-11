"""
R06-E — IPC Integration Tests: RustSnapshotReader
==================================================
Tests for file-based IPC reading of Rust engine pipeline snapshots.
測試基於文件的 IPC 讀取 Rust 引擎管線快照。

Test categories / 測試分類:
  1. Snapshot not available — file missing / 快照不可用 — 文件缺失
  2. Snapshot available   — valid data returned / 快照可用 — 返回有效數據
  3. Cache behavior       — TTL & staleness / 緩存行為 — TTL 和過期
  4. Error handling       — malformed JSON, full dict / 錯誤處理 — 格式錯誤 JSON、完整字典
  5. Singleton            — get_rust_reader() identity / 單例 — get_rust_reader() 同一實例

15 tests total.
"""

import sys
import os
import json
import time
import tempfile
import unittest

# Path setup — same pattern as other test files in this directory
# 路徑設置 — 與本目錄其他測試文件相同的模式
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.ipc_state_reader import RustSnapshotReader, get_rust_reader, _CACHE_TTL_SECONDS

# ---------------------------------------------------------------------------
# Realistic snapshot fixture matching Rust PipelineSnapshot format
# 符合 Rust PipelineSnapshot 格式的真實快照測試數據
# ---------------------------------------------------------------------------
SAMPLE_SNAPSHOT = {
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


def _write_snapshot(data_dir: str, data: dict) -> str:
    """
    Write snapshot JSON to the expected path inside data_dir.
    將快照 JSON 寫入 data_dir 內的預期路徑。
    """
    path = os.path.join(data_dir, "pipeline_snapshot.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


# ===========================================================================
# 1. Snapshot not available / 快照不可用
# ===========================================================================


class TestSnapshotNotAvailable(unittest.TestCase):
    """Tests when the snapshot file does not exist / 快照文件不存在時的測試"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reader = RustSnapshotReader(data_dir=self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_paper_state_no_file(self):
        """Returns None when snapshot file doesn't exist / 文件不存在時返回 None"""
        result = self.reader.get_paper_state()
        self.assertIsNone(result)

    def test_get_latest_prices_no_file(self):
        """Returns None when snapshot file doesn't exist / 文件不存在時返回 None"""
        result = self.reader.get_latest_prices()
        self.assertIsNone(result)

    def test_is_available_no_file(self):
        """Returns False when snapshot file doesn't exist / 文件不存在時返回 False"""
        self.assertFalse(self.reader.is_available())


# ===========================================================================
# 2. Snapshot available / 快照可用
# ===========================================================================


class TestSnapshotAvailable(unittest.TestCase):
    """Tests when a valid snapshot file exists / 有效快照文件存在時的測試"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        _write_snapshot(self._tmpdir.name, SAMPLE_SNAPSHOT)
        self.reader = RustSnapshotReader(data_dir=self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_paper_state_valid(self):
        """
        Returns paper_state dict with balance and positions.
        返回包含餘額和持倉的 paper_state 字典。
        """
        state = self.reader.get_paper_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["balance"], 9500.0)
        self.assertEqual(state["peak_balance"], 10000.0)
        self.assertEqual(state["total_realized_pnl"], -500.0)
        self.assertEqual(state["total_fees"], 12.5)
        self.assertEqual(state["trade_count"], 3)
        # Verify positions list / 驗證持倉列表
        positions = state["positions"]
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "BTCUSDT")
        self.assertTrue(positions[0]["is_long"])
        self.assertAlmostEqual(positions[0]["qty"], 0.01)

    def test_get_latest_prices_valid(self):
        """
        Returns price dict keyed by symbol.
        返回以交易對為鍵的價格字典。
        """
        prices = self.reader.get_latest_prices()
        self.assertIsNotNone(prices)
        self.assertEqual(prices["BTCUSDT"], 66000.0)
        self.assertEqual(prices["ETHUSDT"], 3200.0)

    def test_get_tick_stats_valid(self):
        """
        Returns stats dict with tick/intent/fill/stop counters.
        返回包含 tick/intent/fill/stop 計數器的統計字典。
        """
        stats = self.reader.get_tick_stats()
        self.assertIsNotNone(stats)
        self.assertEqual(stats["total_ticks"], 5000)
        self.assertEqual(stats["total_intents"], 15)
        self.assertEqual(stats["total_fills"], 3)
        self.assertEqual(stats["total_stops"], 1)
        self.assertEqual(stats["last_tick_ms"], 1700000050000)

    def test_get_source_valid(self):
        """
        Returns 'rust_engine' as the source tag.
        返回 'rust_engine' 作為數據源標識。
        """
        source = self.reader.get_source()
        self.assertEqual(source, "rust_engine")

    def test_is_available_fresh_file(self):
        """
        Returns True for a recently written file (within staleness threshold).
        對於最近寫入的文件（在過期閾值內）返回 True。
        """
        self.assertTrue(self.reader.is_available())


# ===========================================================================
# 3. Cache behavior / 緩存行為
# ===========================================================================


class TestCacheBehavior(unittest.TestCase):
    """Tests for internal caching and TTL logic / 內部緩存和 TTL 邏輯的測試"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reader = RustSnapshotReader(data_dir=self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_cache_reuses_within_ttl(self):
        """
        Two rapid reads should hit cache (file read only once).
        兩次快速讀取應命中緩存（文件只讀取一次）。
        """
        _write_snapshot(self._tmpdir.name, SAMPLE_SNAPSHOT)

        # First read — populates cache / 第一次讀取 — 填充緩存
        snap1 = self.reader.get_snapshot()
        self.assertIsNotNone(snap1)

        # Overwrite file with different data / 用不同數據覆寫文件
        modified = {**SAMPLE_SNAPSHOT, "source": "modified"}
        _write_snapshot(self._tmpdir.name, modified)

        # Second read within TTL — should still return cached data
        # 在 TTL 內第二次讀取 — 應仍返回緩存數據
        snap2 = self.reader.get_snapshot()
        self.assertEqual(snap2["source"], "rust_engine")  # cached, not "modified"

    def test_cache_refreshes_after_ttl(self):
        """
        After TTL expires, file is re-read and new data returned.
        TTL 過期後，重新讀取文件並返回新數據。
        """
        _write_snapshot(self._tmpdir.name, SAMPLE_SNAPSHOT)
        snap1 = self.reader.get_snapshot()
        self.assertEqual(snap1["source"], "rust_engine")

        # Overwrite with new data / 用新數據覆寫
        modified = {**SAMPLE_SNAPSHOT, "source": "updated_engine"}
        _write_snapshot(self._tmpdir.name, modified)

        # Force cache expiry by resetting internal timestamp
        # 通過重置內部時間戳強制緩存過期
        self.reader._cache_ts = 0.0

        snap2 = self.reader.get_snapshot()
        self.assertEqual(snap2["source"], "updated_engine")

    def test_staleness_threshold(self):
        """
        File older than 60 seconds should make is_available() return False.
        超過 60 秒的文件應使 is_available() 返回 False。
        """
        path = _write_snapshot(self._tmpdir.name, SAMPLE_SNAPSHOT)

        # Set file mtime to 120 seconds ago (well past the 60s threshold)
        # 將文件修改時間設為 120 秒前（遠超 60 秒閾值）
        old_time = time.time() - 120
        os.utime(path, (old_time, old_time))

        self.assertFalse(self.reader.is_available())


# ===========================================================================
# 4. Error handling / 錯誤處理
# ===========================================================================


class TestErrorHandling(unittest.TestCase):
    """Tests for graceful degradation on bad data / 數據異常時優雅降級的測試"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reader = RustSnapshotReader(data_dir=self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_malformed_json(self):
        """
        Malformed JSON should return None without raising an exception.
        格式錯誤的 JSON 應返回 None 而不拋出異常。
        """
        path = os.path.join(self._tmpdir.name, "pipeline_snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{invalid json content!!!")

        result = self.reader.get_snapshot()
        self.assertIsNone(result)

        # Also verify sub-accessors return None gracefully
        # 同時驗證子訪問方法也優雅返回 None
        self.assertIsNone(self.reader.get_paper_state())
        self.assertIsNone(self.reader.get_latest_prices())

    def test_get_snapshot_returns_full_dict(self):
        """
        get_snapshot() returns the complete snapshot structure with all keys.
        get_snapshot() 返回包含所有鍵的完整快照結構。
        """
        _write_snapshot(self._tmpdir.name, SAMPLE_SNAPSHOT)

        snap = self.reader.get_snapshot()
        self.assertIsNotNone(snap)
        # Verify all top-level keys present / 驗證所有頂層鍵存在
        expected_keys = {"paper_state", "latest_prices", "stats", "source"}
        self.assertEqual(set(snap.keys()), expected_keys)
        # Verify types / 驗證類型
        self.assertIsInstance(snap["paper_state"], dict)
        self.assertIsInstance(snap["latest_prices"], dict)
        self.assertIsInstance(snap["stats"], dict)
        self.assertIsInstance(snap["source"], str)


# ===========================================================================
# 4b. 3E-ARCH per-engine routing (regression for paper-tab Live data bug)
# 4b. 3E-ARCH 每引擎路由（修復 paper tab 顯示 Live 數據的回歸測試）
# ===========================================================================


class TestPerEngineRouting(unittest.TestCase):
    """
    3E-ARCH regression: when all three per-engine snapshot files exist alongside
    the compat pipeline_snapshot.json (which under 3E-ARCH is written by whichever
    engine has is_primary=true — Live > Demo > Paper priority), the paper-tab
    callers MUST read pipeline_snapshot_paper.json, not the compat file.

    Before the 2026-04-11 fix, get_paper_state() and friends defaulted to the
    compat reader, so the Paper GUI tab showed Live engine balance + zero
    positions when all three engines were running.

    3E-ARCH 回歸：當三個 per-engine 檔與 compat 檔並存（compat 由 is_primary
    引擎寫入，Live > Demo > Paper 優先序），paper-tab 呼叫者必須讀
    pipeline_snapshot_paper.json，不能讀 compat。修復前 paper tab 會顯示 Live
    餘額 + 零持倉。

    Sentinel balances are deliberately obvious-fake values (11111 / 22222 / 33333)
    so it's clear at a glance these are test fixtures, not real engine state.
    哨兵餘額刻意用顯而易見的假數值（11111 / 22222 / 33333），一眼就知道是
    測試 fixture，不是真實引擎狀態。
    """

    # Sentinel balances — deliberately fake / 哨兵餘額——刻意用假值
    PAPER_SENTINEL_BALANCE = 11111.11
    DEMO_SENTINEL_BALANCE = 22222.22
    LIVE_SENTINEL_BALANCE = 33333.33

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        # Compat file written by Live engine (is_primary=true) — what the bug saw
        # Compat 檔由 Live 引擎寫入（is_primary=true）— 即 bug 觀察到的狀況
        live_data = {
            "trading_mode": "live",
            "paper_state": {
                "balance": self.LIVE_SENTINEL_BALANCE,
                "peak_balance": self.LIVE_SENTINEL_BALANCE,
                "total_realized_pnl": 0.0,
                "total_fees": 0.0,
                "trade_count": 0,
                "positions": [],
            },
            "latest_prices": {},
            "stats": {},
            "source": "rust_engine",
        }
        paper_data = {
            "trading_mode": "paper",
            "paper_state": {
                "balance": self.PAPER_SENTINEL_BALANCE,
                "peak_balance": 99999.99,
                "total_realized_pnl": -10.0,
                "total_fees": 5.0,
                "trade_count": 4,
                "positions": [
                    {
                        "symbol": "FAKEUSDT",
                        "is_long": True,
                        "qty": 0.01,
                        "entry_price": 12345.0,
                        "best_price": 12345.0,
                        "entry_fee": 1.0,
                        "entry_ts_ms": 1700000000000,
                        "unrealized_pnl": 0.0,
                    }
                ],
            },
            "latest_prices": {"FAKEUSDT": 12345.0},
            "stats": {"total_ticks": 100},
            "source": "rust_engine",
            "recent_intents": [{"id": "paper_intent_1"}],
            "recent_fills": [{"id": "paper_fill_1"}],
        }
        demo_data = {
            "trading_mode": "demo",
            "paper_state": {
                "balance": self.DEMO_SENTINEL_BALANCE,
                "peak_balance": self.DEMO_SENTINEL_BALANCE,
                "total_realized_pnl": 0.0,
                "total_fees": 0.0,
                "trade_count": 0,
                "positions": [],
            },
            "latest_prices": {},
            "stats": {},
            "source": "rust_engine",
        }
        with open(os.path.join(self._tmpdir.name, "pipeline_snapshot.json"), "w") as f:
            json.dump(live_data, f)
        with open(os.path.join(self._tmpdir.name, "pipeline_snapshot_live.json"), "w") as f:
            json.dump(live_data, f)
        with open(os.path.join(self._tmpdir.name, "pipeline_snapshot_paper.json"), "w") as f:
            json.dump(paper_data, f)
        with open(os.path.join(self._tmpdir.name, "pipeline_snapshot_demo.json"), "w") as f:
            json.dump(demo_data, f)
        self.reader = RustSnapshotReader(data_dir=self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_paper_state_default_routes_to_paper_engine(self):
        """get_paper_state() with no args MUST return paper engine data, not compat (Live)."""
        state = self.reader.get_paper_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["balance"], self.PAPER_SENTINEL_BALANCE)
        self.assertEqual(len(state["positions"]), 1)
        self.assertEqual(state["positions"][0]["symbol"], "FAKEUSDT")

    def test_get_paper_state_explicit_paper(self):
        """get_paper_state(engine='paper') returns paper data."""
        state = self.reader.get_paper_state(engine="paper")
        self.assertEqual(state["balance"], self.PAPER_SENTINEL_BALANCE)

    def test_get_paper_state_explicit_demo(self):
        """get_paper_state(engine='demo') returns demo data."""
        state = self.reader.get_paper_state(engine="demo")
        self.assertEqual(state["balance"], self.DEMO_SENTINEL_BALANCE)

    def test_get_paper_state_explicit_live(self):
        """get_paper_state(engine='live') returns live data."""
        state = self.reader.get_paper_state(engine="live")
        self.assertEqual(state["balance"], self.LIVE_SENTINEL_BALANCE)

    def test_get_paper_state_via_mode_param(self):
        """get_paper_state(mode='demo') routes through mode (engine alias)."""
        state = self.reader.get_paper_state(mode="demo")
        self.assertEqual(state["balance"], self.DEMO_SENTINEL_BALANCE)

    def test_get_snapshot_default_still_reads_compat(self):
        """get_snapshot() with no args reads compat (legacy callers untouched)."""
        snap = self.reader.get_snapshot()
        self.assertEqual(snap["trading_mode"], "live")  # compat = Live under 3E-ARCH

    def test_get_snapshot_with_engine_param_routes_per_engine(self):
        """get_snapshot(engine='paper') routes to per-engine file."""
        snap = self.reader.get_snapshot(engine="paper")
        self.assertEqual(snap["trading_mode"], "paper")
        self.assertEqual(snap["paper_state"]["balance"], self.PAPER_SENTINEL_BALANCE)


# ===========================================================================
# 5. Singleton / 單例
# ===========================================================================


class TestSingleton(unittest.TestCase):
    """Test module-level singleton behavior / 測試模組級單例行為"""

    def test_get_rust_reader_singleton(self):
        """
        Calling get_rust_reader() twice returns the same instance.
        調用 get_rust_reader() 兩次應返回同一實例。
        """
        import app.ipc_state_reader as mod

        # Reset module singleton to ensure clean test state
        # 重置模組單例以確保乾淨的測試狀態
        mod._READER = None

        reader1 = get_rust_reader()
        reader2 = get_rust_reader()
        self.assertIs(reader1, reader2)

        # Clean up — reset singleton so other tests are not affected
        # 清理 — 重置單例以免影響其他測試
        mod._READER = None


if __name__ == "__main__":
    unittest.main()
