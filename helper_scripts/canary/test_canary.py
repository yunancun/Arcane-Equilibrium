#!/usr/bin/env python3
"""
Tests for canary validation tools (R07-3/R07-6).
灰度驗證工具的測試。

Covers:
  - canary_schema: record building, validation, tolerances
  - canary_comparator: tick comparison, divergence detection, escalation
  - engine_watchdog: crash detection, recovery, 3-strike rule
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canary_schema import (
    CanaryRecord,
    build_record,
    validate_record,
    SCHEMA_VERSION,
    TOLERANCE_SIMPLE,
    TOLERANCE_RECURSIVE,
    TOLERANCE_COMPLEX,
)
from canary_comparator import (
    compare_numeric,
    compare_signal_direction,
    compare_tick,
    check_boundary_escalation,
    run_comparison,
    ComparisonReport,
    Divergence,
    PASS,
    WARNING,
    CRITICAL,
    MISSING,
    BOUNDARY_DIVERGENCE,
)
import engine_watchdog
from engine_watchdog import (
    check_snapshot_freshness,
    classify_engine_failure,
    get_watchdog_status,
    on_engine_crash,
    on_engine_recovery,
    trigger_restart,
    WatchdogState,
    run_watchdog,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Schema Tests / 模式測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestCanarySchema(unittest.TestCase):

    def test_build_record_defaults(self):
        """build_record() creates valid record with defaults / 默認構建有效記錄"""
        r = build_record("rust_engine", 1, 1700000000000, "BTCUSDT", 65000.0)
        self.assertEqual(r.schema_version, SCHEMA_VERSION)
        self.assertEqual(r.source, "rust_engine")
        self.assertEqual(r.tick_number, 1)
        self.assertEqual(r.indicators, {})
        self.assertEqual(r.signals, [])

    def test_record_json_roundtrip(self):
        """Record serializes and deserializes correctly / 記錄正確序列化和反序列化"""
        r = build_record("python_shadow", 42, 1700000001000, "ETHUSDT", 3200.0,
                         indicators={"sma_20": 3180.0},
                         signals=[{"direction": "Long", "confidence": 0.8, "source": "rsi"}])
        json_str = r.to_json()
        r2 = CanaryRecord.from_json(json_str)
        self.assertEqual(r2.tick_number, 42)
        self.assertEqual(r2.indicators["sma_20"], 3180.0)
        self.assertEqual(len(r2.signals), 1)

    def test_validate_record_valid(self):
        """Valid record passes validation / 有效記錄通過驗證"""
        d = json.loads(build_record("rust_engine", 1, 1700000000000, "BTC", 65000.0).to_json())
        errors = validate_record(d)
        self.assertEqual(errors, [])

    def test_validate_record_missing_fields(self):
        """Missing fields detected / 檢測缺失字段"""
        errors = validate_record({"source": "rust_engine"})
        self.assertTrue(any("missing" in e for e in errors))

    def test_validate_record_bad_source(self):
        """Invalid source detected / 檢測無效源"""
        d = json.loads(build_record("bad_source", 1, 0, "X", 0).to_json())
        errors = validate_record(d)
        self.assertTrue(any("invalid source" in e for e in errors))


# ═══════════════════════════════════════════════════════════════════════════════
# Comparator Tests / 比較器測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompareNumeric(unittest.TestCase):

    def test_identical_values_no_divergence(self):
        """Identical values → no divergence / 相同值 → 無偏差"""
        d = compare_numeric("sma_20", 100.0, 100.0, 1, 0, "BTC")
        self.assertIsNone(d)

    def test_within_tolerance_no_divergence(self):
        """Values within tolerance → no divergence / 容差內 → 無偏差"""
        d = compare_numeric("sma_20", 100.0, 100.0 + 1e-12, 1, 0, "BTC")
        self.assertIsNone(d)

    def test_beyond_simple_tolerance(self):
        """Values beyond simple tolerance → divergence / 超出簡單容差 → 偏差"""
        d = compare_numeric("sma_20", 100.0, 100.001, 1, 0, "BTC")
        self.assertIsNotNone(d)
        self.assertEqual(d.field, "sma_20")

    def test_recursive_tolerance_pass(self):
        """RSI within recursive tolerance → pass / RSI 在遞歸容差內 → 通過"""
        d = compare_numeric("rsi_14", 65.0, 65.0 + 1e-10, 1, 0, "BTC")
        self.assertIsNone(d)

    def test_hurst_complex_tolerance(self):
        """Hurst within complex tolerance → pass / Hurst 在複雜容差內 → 通過"""
        # Use canonical key; TOLERANCE_COMPLEX is 5e-2, so 1e-3 is within
        # 使用規範鍵名；TOLERANCE_COMPLEX 為 5e-2，因此 1e-3 在容差內
        d = compare_numeric("hurst", 0.55, 0.55 + 1e-3, 1, 0, "BTC")
        self.assertIsNone(d)

    def test_hurst_beyond_complex_tolerance(self):
        """Hurst beyond complex tolerance → divergence / Hurst 超出複雜容差 → 偏差"""
        # TOLERANCE_COMPLEX is 5e-2, so 0.1 diff is beyond
        # TOLERANCE_COMPLEX 為 5e-2，因此 0.1 的差異超出容差
        d = compare_numeric("hurst", 0.55, 0.55 + 0.1, 1, 0, "BTC")
        self.assertIsNotNone(d)

    def test_one_none_value(self):
        """One value None → WARNING / 一個值為 None → WARNING"""
        d = compare_numeric("sma_20", 100.0, None, 1, 0, "BTC")
        self.assertIsNotNone(d)
        self.assertEqual(d.severity, WARNING)

    def test_both_none_no_divergence(self):
        """Both None → no divergence / 兩者都是 None → 無偏差"""
        d = compare_numeric("sma_20", None, None, 1, 0, "BTC")
        self.assertIsNone(d)

    def test_known_missing_indicator_returns_missing(self):
        """Known-missing indicator (one side None) → MISSING severity, not WARNING
        已知缺失指標（一側為 None）→ MISSING 嚴重度，非 WARNING"""
        d = compare_numeric("sma_50", None, 64800.0, 1, 0, "BTC")
        self.assertIsNotNone(d)
        self.assertEqual(d.severity, MISSING)

    def test_unknown_missing_indicator_returns_warning(self):
        """Unknown indicator (one side None) → WARNING severity
        未知缺失指標（一側為 None）→ WARNING 嚴重度"""
        d = compare_numeric("sma_20", None, 64800.0, 1, 0, "BTC")
        self.assertIsNotNone(d)
        self.assertEqual(d.severity, WARNING)


class TestCompareSignals(unittest.TestCase):

    def test_matching_signals(self):
        """Same direction → no divergence / 方向相同 → 無偏差"""
        r = [{"direction": "Long", "confidence": 0.8, "source": "rsi"}]
        p = [{"direction": "Long", "confidence": 0.8, "source": "rsi"}]
        divs = compare_signal_direction(r, p, 1, 0, "BTC")
        self.assertEqual(len(divs), 0)

    def test_direction_mismatch_critical(self):
        """Direction mismatch with high confidence → CRITICAL / 高置信度方向不匹配 → CRITICAL"""
        r = [{"direction": "Long", "confidence": 0.8, "source": "rsi"}]
        p = [{"direction": "Short", "confidence": 0.8, "source": "rsi"}]
        divs = compare_signal_direction(r, p, 1, 0, "BTC")
        self.assertEqual(len(divs), 1)
        self.assertEqual(divs[0].severity, CRITICAL)

    def test_direction_mismatch_boundary(self):
        """Direction mismatch near boundary → BOUNDARY_DIVERGENCE / 邊界附近方向不匹配"""
        r = [{"direction": "Long", "confidence": 0.502, "source": "rsi"}]
        p = [{"direction": "Neutral", "confidence": 0.498, "source": "rsi"}]
        divs = compare_signal_direction(r, p, 1, 0, "BTC")
        self.assertEqual(len(divs), 1)
        self.assertEqual(divs[0].severity, BOUNDARY_DIVERGENCE)

    def test_signal_presence_mismatch(self):
        """Signal in one side only → WARNING / 信號只在一側 → WARNING"""
        r = [{"direction": "Long", "confidence": 0.8, "source": "rsi"}]
        p = []
        divs = compare_signal_direction(r, p, 1, 0, "BTC")
        self.assertEqual(len(divs), 1)
        self.assertEqual(divs[0].severity, WARNING)


class TestCompareTick(unittest.TestCase):

    def _make_tick(self, source, **overrides):
        base = {
            "tick_number": 1,
            "timestamp_ms": 1700000000000,
            "symbol": "BTCUSDT",
            "price": 65000.0,
            "indicators": {"sma_20": 64800.0, "rsi_14": 55.0},
            "signals": [{"direction": "Long", "confidence": 0.7, "source": "rsi"}],
            "paper_state": {"balance": 9500.0, "total_realized_pnl": -500.0, "total_fees": 12.5},
            "order_intents": [],
            "source": source,
        }
        base.update(overrides)
        return base

    def test_identical_ticks_no_divergences(self):
        """Identical ticks → 0 divergences / 相同 tick → 0 偏差"""
        r = self._make_tick("rust_engine")
        p = self._make_tick("python_shadow")
        divs, _ps_skipped, _sig_skipped = compare_tick(r, p)
        self.assertEqual(len(divs), 0)

    def test_indicator_divergence(self):
        """SMA mismatch → divergence / SMA 不匹配 → 偏差"""
        r = self._make_tick("rust_engine")
        p = self._make_tick("python_shadow", indicators={"sma_20": 64800.1, "rsi_14": 55.0})
        divs, _ps_skipped, _sig_skipped = compare_tick(r, p)
        self.assertTrue(any(d.field == "sma_20" for d in divs))

    def test_intent_count_mismatch_on_bar_close(self):
        """Different intent counts on bar-close tick → WARNING / bar-close tick 意圖數量不同 → WARNING"""
        # Both sides have signals → bar-close tick, intent comparison happens
        # 雙方都有信號 → bar-close tick，意圖比較會執行
        r = self._make_tick("rust_engine", order_intents=[{"symbol": "BTC"}])
        p = self._make_tick("python_shadow", order_intents=[])
        divs, _ps_skipped, sig_skipped = compare_tick(r, p)
        self.assertFalse(sig_skipped)
        self.assertTrue(any(d.field == "order_intents.count" for d in divs))

    def test_signal_skipped_on_non_bar_close(self):
        """Rust has signals but Python doesn't → skip signal compare (non bar-close)
        Rust 有信號但 Python 沒有 → 跳過信號比較（非 bar-close tick）"""
        r = self._make_tick("rust_engine",
                            signals=[{"direction": "Long", "confidence": 0.7, "source": "rsi"}],
                            order_intents=[{"symbol": "BTC"}])
        p = self._make_tick("python_shadow", signals=[], order_intents=[])
        divs, _ps_skipped, sig_skipped = compare_tick(r, p)
        self.assertTrue(sig_skipped)
        # No signal or intent divergences should be reported / 不應報告信號或意圖偏差
        self.assertFalse(any(d.field.startswith("signal.") for d in divs))
        self.assertFalse(any(d.field == "order_intents.count" for d in divs))


class TestBoundaryEscalation(unittest.TestCase):

    def test_no_escalation_few_boundaries(self):
        """Few boundary divergences → no escalation / 少量邊界偏差 → 不升級"""
        divs = [Divergence(0, 0, "BTC", "f", 0, 0, 0, 0, BOUNDARY_DIVERGENCE, "test")] * 5
        escalated, _ = check_boundary_escalation(divs)
        self.assertFalse(escalated)

    def test_escalation_over_50(self):
        """Over 50 boundary divergences → escalation / 超過 50 個邊界偏差 → 升級"""
        divs = [Divergence(0, 0, "BTC", "f", 0, 0, 0, 0, BOUNDARY_DIVERGENCE, "test")] * 51
        escalated, reason = check_boundary_escalation(divs)
        self.assertTrue(escalated)
        self.assertIn("50", reason)


class TestRunComparison(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_jsonl(self, filename, records):
        path = os.path.join(self._tmpdir.name, filename)
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return path

    def test_identical_files_pass(self):
        """Identical JSONL files → PASS verdict / 相同 JSONL 文件 → PASS 判定"""
        tick = {
            "tick_number": 1, "timestamp_ms": 1000, "symbol": "BTC",
            "price": 65000.0, "indicators": {"sma_20": 64800.0},
            "signals": [], "paper_state": {"balance": 10000.0}, "order_intents": [],
        }
        ep = self._write_jsonl("engine.jsonl", [tick])
        sp = self._write_jsonl("shadow.jsonl", [tick])
        report = run_comparison(ep, sp)
        self.assertEqual(report.verdict, PASS)
        self.assertEqual(report.matched_ticks, 1)
        self.assertEqual(report.critical_count, 0)

    def test_divergent_files_critical(self):
        """Divergent signals → CRITICAL verdict / 信號偏差 → CRITICAL 判定"""
        r_tick = {
            "tick_number": 1, "timestamp_ms": 1000, "symbol": "BTC",
            "price": 65000.0, "indicators": {},
            "signals": [{"direction": "Long", "confidence": 0.9, "source": "rsi"}],
            "paper_state": {}, "order_intents": [],
        }
        p_tick = {
            "tick_number": 1, "timestamp_ms": 1000, "symbol": "BTC",
            "price": 65000.0, "indicators": {},
            "signals": [{"direction": "Short", "confidence": 0.9, "source": "rsi"}],
            "paper_state": {}, "order_intents": [],
        }
        ep = self._write_jsonl("engine.jsonl", [r_tick])
        sp = self._write_jsonl("shadow.jsonl", [p_tick])
        report = run_comparison(ep, sp)
        self.assertEqual(report.verdict, CRITICAL)
        self.assertGreater(report.critical_count, 0)

    def test_empty_files_pass(self):
        """Empty files → PASS (no ticks to compare) / 空文件 → PASS"""
        ep = self._write_jsonl("engine.jsonl", [])
        sp = self._write_jsonl("shadow.jsonl", [])
        report = run_comparison(ep, sp)
        self.assertEqual(report.verdict, PASS)


# ═══════════════════════════════════════════════════════════════════════════════
# Watchdog Tests / 看門狗測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchdogSnapshot(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_fresh_snapshot(self):
        """Recently written snapshot is fresh / 最近寫入的快照是新鮮的"""
        path = os.path.join(self._tmpdir.name, "pipeline_snapshot.json")
        with open(path, "w") as f:
            f.write("{}")
        is_fresh, age = check_snapshot_freshness(
            __import__("pathlib").Path(path), 10.0
        )
        self.assertTrue(is_fresh)
        self.assertLess(age, 2.0)

    def test_stale_snapshot(self):
        """Old snapshot is not fresh / 舊快照不新鮮"""
        path = os.path.join(self._tmpdir.name, "pipeline_snapshot.json")
        with open(path, "w") as f:
            f.write("{}")
        old_time = time.time() - 30
        os.utime(path, (old_time, old_time))
        is_fresh, age = check_snapshot_freshness(
            __import__("pathlib").Path(path), 10.0
        )
        self.assertFalse(is_fresh)
        self.assertGreater(age, 25)

    def test_missing_snapshot(self):
        """Missing file is not fresh / 缺失文件不新鮮"""
        path = os.path.join(self._tmpdir.name, "nonexistent.json")
        is_fresh, age = check_snapshot_freshness(
            __import__("pathlib").Path(path), 10.0
        )
        self.assertFalse(is_fresh)
        self.assertEqual(age, float("inf"))

    def test_status_alive_when_per_engine_snapshot_is_fresh(self):
        """Per-engine fresh snapshot keeps status alive when compat is stale.
        每引擎快照新鮮時，即使兼容快照過期也不應判 dead。"""
        compat_path = os.path.join(self._tmpdir.name, "pipeline_snapshot.json")
        demo_path = os.path.join(self._tmpdir.name, "pipeline_snapshot_demo.json")
        with open(compat_path, "w", encoding="utf-8") as f:
            f.write("{}")
        with open(demo_path, "w", encoding="utf-8") as f:
            f.write("{}")
        old_time = time.time() - 30
        os.utime(compat_path, (old_time, old_time))

        status = get_watchdog_status(self._tmpdir.name, stale_threshold=10.0)

        self.assertTrue(status["engine_alive"])
        self.assertFalse(status["engines"]["paper"]["alive"])
        self.assertTrue(status["engines"]["demo"]["alive"])
        self.assertFalse(status["engines"]["live"]["alive"])
        self.assertIsNone(status["paper_age_seconds"])
        self.assertIsNotNone(status["demo_age_seconds"])
        self.assertIsNone(status["live_age_seconds"])


class TestWatchdogCrashRecovery(unittest.TestCase):

    def test_first_crash_triggers_fallback(self):
        """First crash → fallback (not rollback) / 首次崩潰 → 降級"""
        state = WatchdogState()
        action = on_engine_crash(state, 15.0)
        self.assertEqual(action, "fallback")
        self.assertFalse(state.engine_alive)
        self.assertEqual(state.total_crashes, 1)

    def test_duplicate_crash_does_not_recount(self):
        """WATCHDOG-RETRY-LEVELTRIGGER-1：已在崩潰狀態再 poll → 不重複計 strike。

        修正後語義：計數是 edge-triggered，已 down（engine_alive=False）的重複
        poll 不再 append crash_timestamps、不再 increment total_crashes；但不再
        早退「none」（那是死鎖成因）。無 data_dir 時不跑重試、不算轉移 → 回 fallback。"""
        state = WatchdogState(engine_alive=False)
        action = on_engine_crash(state, 15.0)
        self.assertEqual(action, "fallback")
        # 關鍵不變量：重複 poll 不重複計數
        self.assertEqual(state.total_crashes, 0)
        self.assertEqual(len(state.crash_timestamps), 0)

    def test_three_strikes_triggers_rollback(self):
        """3 crashes in window → rollback / 窗口內 3 次崩潰 → 回滾"""
        state = WatchdogState()
        on_engine_crash(state, 15.0)  # Strike 1
        state.engine_alive = True     # Simulate recovery
        on_engine_crash(state, 15.0)  # Strike 2
        state.engine_alive = True
        action = on_engine_crash(state, 15.0)  # Strike 3
        self.assertEqual(action, "rollback")
        self.assertTrue(state.rollback_triggered)

    def test_recovery(self):
        """Recovery after crash / 崩潰後恢復"""
        state = WatchdogState(engine_alive=False)
        on_engine_recovery(state)
        self.assertTrue(state.engine_alive)
        self.assertGreater(state.last_recovery_ts, 0)

    def test_recovery_when_already_alive(self):
        """Recovery when already alive is no-op / 已恢復時再恢復無操作"""
        state = WatchdogState(engine_alive=True, last_recovery_ts=0)
        on_engine_recovery(state)
        self.assertEqual(state.last_recovery_ts, 0)  # Not updated


class TestWatchdogLoop(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_healthy_engine_no_crash(self):
        """Fresh snapshot → engine stays alive / 新鮮快照 → 引擎保持存活"""
        path = os.path.join(self._tmpdir.name, "pipeline_snapshot.json")
        with open(path, "w") as f:
            f.write("{}")
        state = run_watchdog(self._tmpdir.name, stale_threshold=60, poll_interval=0.01, max_iterations=3)
        self.assertTrue(state.engine_alive)
        self.assertEqual(state.total_crashes, 0)

    def test_missing_file_triggers_crash(self):
        """No snapshot file → crash detected / 無快照文件 → 檢測到崩潰"""
        # grace_period=0: disable grace period so missing file is immediately detected as crash
        # grace_period=0：禁用寬限期，使缺失文件立即被檢測為崩潰
        state = run_watchdog(self._tmpdir.name, stale_threshold=5, poll_interval=0.01, max_iterations=3, grace_period=0)
        self.assertFalse(state.engine_alive)
        self.assertEqual(state.total_crashes, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# WATCHDOG-DNS-CLASSIFY-1 tests (2026-04-20) — DNS outage vs real crash
# 區分 DNS 斷線與真 crash（P0-9 停電 RCA 後補上的分類器）
# ═══════════════════════════════════════════════════════════════════════════════


class TestEngineFailureClassifier(unittest.TestCase):
    """classify_engine_failure(): tail-inspection routing."""

    def setUp(self):
        import pathlib
        self._pathlib = pathlib
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_log(self, lines):
        path = os.path.join(self._tmpdir.name, "engine.log")
        with open(path, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines) + "\n")
        return self._pathlib.Path(path)

    def _write_rotated_log(self, lines, name="engine-1700000000.log", age_seconds=0):
        logs_dir = os.path.join(self._tmpdir.name, "engine_logs")
        os.makedirs(logs_dir, exist_ok=True)
        path = os.path.join(logs_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines) + "\n")
        if age_seconds:
            old = time.time() - age_seconds
            os.utime(path, (old, old))
        return self._pathlib.Path(path)

    def test_missing_log_defaults_to_engine_crash(self):
        """No engine.log → conservative default / 缺日誌 → 保守 engine_crash"""
        path = self._pathlib.Path(self._tmpdir.name) / "absent.log"
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_empty_log_defaults_to_engine_crash(self):
        """Empty file → engine_crash / 空檔 → engine_crash"""
        path = self._write_log([])
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_five_consecutive_dns_classified_as_network_outage(self):
        """≥5 consecutive DNS lines at tail → network_outage / 連續 ≥5 DNS → 網路中斷"""
        lines = [
            "INFO startup ok",
            "INFO some other message",
        ] + [
            f"ERROR Temporary failure in name resolution attempt {i}"
            for i in range(5)
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_four_consecutive_dns_below_threshold(self):
        """<5 consecutive DNS → engine_crash / <5 連續 → engine_crash"""
        lines = ["info"] + [
            f"ERROR HTTP transport error {i}" for i in range(4)
        ] + ["info tail"]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_mixed_patterns_count_together(self):
        """Mixed DNS/transport/refused lines count as consecutive matches.
        DNS/transport/connection-refused 跨模式視為同組匹配"""
        lines = [
            "INFO ok",
            "ERROR Temporary failure in name resolution 1",
            "ERROR HTTP transport error 2",
            "ERROR connection refused 3",
            "ERROR failed to lookup address information 4",
            "ERROR DNS error 5",
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_panic_overrides_dns_flood(self):
        """Panic in tail → engine_crash even with plenty of DNS lines.
        tail 出現 panic 時即使 DNS 成堆也判為 engine_crash"""
        lines = [
            "thread 'main' panicked at 'boom' at src/foo.rs:42",
        ] + [
            f"ERROR Temporary failure in name resolution {i}"
            for i in range(10)
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_assertion_override(self):
        """Assertion in tail overrides DNS classification.
        assertion failed 也強制 engine_crash"""
        lines = [
            f"ERROR Temporary failure in name resolution {i}" for i in range(6)
        ] + ["ERROR assertion failed: left == right"]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_non_consecutive_dns_above_interleaved_threshold(self):
        """DNS 被打斷但比例 ≥ MIN_RATIO → NETOUTAGE-CLASSIFIER-FIX gate (c) 判 network_outage。

        為什麼這個 test 改了意圖：DNS-CLASSIFY-1 原設計只有「連續 ≥5」gate，
        interleaved 場景被誤判 engine_crash 會觸發 restart storm。
        NETOUTAGE-CLASSIFIER-FIX (2026-05-21) 新增 gate (c) interleaved。8 DNS /
        16 行 = 50% ≥ 25% ratio AND 8 ≥ MIN_INTERLEAVED=5 → network_outage。
        """
        lines = []
        for i in range(8):
            lines.append(f"ERROR Temporary failure in name resolution {i}")
            lines.append(f"INFO unrelated heartbeat {i}")
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_case_insensitive_matching(self):
        """Patterns match regardless of case / 不分大小寫"""
        lines = [
            "ERROR TEMPORARY FAILURE IN NAME RESOLUTION 1",
            "ERROR Http Transport Error 2",
            "ERROR Connection Refused 3",
            "ERROR failed to lookup address information 4",
            "ERROR DNS ERROR 5",
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_only_tail_window_counts(self):
        """Only the last tail_lines are inspected / 只看 tail 窗口內的行"""
        # Put 5 DNS lines far from the tail, then fill with non-matching lines
        lines = [f"ERROR Temporary failure in name resolution {i}" for i in range(5)]
        lines += [f"INFO unrelated heartbeat {i}" for i in range(25)]
        path = self._write_log(lines)
        # tail_lines=20 sees only the trailing heartbeats, no DNS
        self.assertEqual(
            classify_engine_failure(path, tail_lines=20),
            "engine_crash",
        )

    def test_recent_rotated_log_classifies_after_restart(self):
        """Recent rotated death log still classifies restart-triggering outage."""
        path = self._write_log(["INFO restarted cleanly"])
        self._write_rotated_log([
            "INFO pre-restart",
            *[
                f"ERROR Temporary failure in name resolution attempt {i}"
                for i in range(5)
            ],
        ])
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_active_panic_overrides_rotated_network_outage(self):
        """Active panic remains engine_crash even if recent rotated log has DNS flood."""
        path = self._write_log(["thread 'main' panicked at src/foo.rs:42"])
        self._write_rotated_log([
            f"ERROR Temporary failure in name resolution attempt {i}"
            for i in range(5)
        ])
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_old_rotated_log_ignored(self):
        """Historical rotated DNS logs must not classify a new unrelated crash."""
        path = self._write_log(["INFO fresh active log without outage"])
        self._write_rotated_log(
            [f"ERROR DNS error old outage {i}" for i in range(5)],
            age_seconds=20 * 60,
        )
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    # ──────────────────────────────────────────────────────────────────────────
    # WATCHDOG-NETOUTAGE-CLASSIFIER-FIX (2026-05-21) regression tests
    # 強化：interleaved + cross-rotation evidence 場景；false-positive guard。
    # ──────────────────────────────────────────────────────────────────────────

    def test_net_outage_classified_when_5_consecutive_dns_errors(self):
        """Baseline：≥5 連續 DNS error 在新分類器下仍判 network_outage（不破舊行為）。"""
        lines = [
            "INFO startup ok",
            "INFO heartbeat",
        ] + [
            f"ERROR Temporary failure in name resolution attempt {i}"
            for i in range(5)
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_net_outage_classified_when_5_interleaved_dns_errors_within_5min(self):
        """5 條 DNS error 散落於 tail 內被 heartbeat 打斷 → 新 gate (c) 判 network_outage。

        舊行為（DNS-CLASSIFY-1）：longest_run=1 < 5 → engine_crash（false negative）。
        新行為：tail 內總 match 數 5 / 總行數 17 ≈ 29% ≥ 25% ratio → network_outage。
        為什麼這個情境真實：DNS lookup 失敗時引擎可能仍輸出 metric/lifecycle 行，
        導致 error 連續性被破壞，但 DNS 確實是真實外部故障源。
        """
        # tail_lines=20，預期讀全部 17 行；5 條 DNS match / 17 ≈ 29% ≥ 25%
        lines = [
            "INFO startup ok",
            "INFO metric heartbeat 1",
            "ERROR Temporary failure in name resolution 1",
            "INFO metric heartbeat 2",
            "INFO some lifecycle event",
            "ERROR Temporary failure in name resolution 2",
            "INFO metric heartbeat 3",
            "ERROR HTTP transport error 3",
            "INFO metric heartbeat 4",
            "INFO unrelated debug",
            "ERROR DNS error 4",
            "INFO metric heartbeat 5",
            "ERROR connection refused 5",
            "INFO metric heartbeat 6",
            "INFO another lifecycle",
            "INFO metric heartbeat 7",
            "INFO last heartbeat",
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_net_outage_classified_when_dns_errors_span_log_rotation(self):
        """DNS errors 散落跨 active + rotated log → cross-rotation aggregate gate (d) 判 outage。

        場景：3 條 DNS 在 active log（不滿單檔 ≥5 連續/interleaved 門檻），2 條
        DNS 在 rotated death log；單檔均 fail，但合併 tail 內共 5 條 match 達
        aggregate gate（5 matches，total ~22-25，ratio ≥10%）→ network_outage。
        舊行為：每個檔獨立評估，均 fail → engine_crash（false negative，會觸發
        restart storm，與 v55 #5 watchdog RCA 同類更廣）。
        """
        # active log：3 DNS + heartbeats（不滿連續 ≥5 也不滿單檔 interleaved 5）
        active_lines = [
            "INFO restart heartbeat",
            "ERROR Temporary failure in name resolution active-1",
            "INFO startup heartbeat 1",
            "INFO startup heartbeat 2",
            "ERROR HTTP transport error active-2",
            "INFO startup heartbeat 3",
            "INFO startup heartbeat 4",
            "ERROR DNS error active-3",
            "INFO startup heartbeat 5",
            "INFO startup heartbeat 6",
        ]
        path = self._write_log(active_lines)
        # rotated death log：2 DNS + heartbeats（單檔也 fail）
        rotated_lines = [
            "INFO pre-restart heartbeat",
            "ERROR Temporary failure in name resolution rotated-1",
            "INFO pre-restart heartbeat 2",
            "INFO pre-restart heartbeat 3",
            "INFO pre-restart heartbeat 4",
            "INFO pre-restart heartbeat 5",
            "INFO pre-restart heartbeat 6",
            "INFO pre-restart heartbeat 7",
            "ERROR connection refused rotated-2",
            "INFO pre-restart heartbeat 8",
        ]
        self._write_rotated_log(rotated_lines)
        self.assertEqual(classify_engine_failure(path), "network_outage")

    def test_pg_connection_error_not_classified_as_net_outage(self):
        """tail 含 PG/sqlx 等 ambiguous-source token → 降級回 engine_crash（false-positive guard）。

        場景：tail 裡同時有 5+ 條 "connection refused"（NETWORK_OUTAGE_PATTERN
        命中）和 1 條 "ERROR sqlx pgconnection ..."（ambiguous source）。雖然
        connection refused 在 substring 上跟 Bybit transport 不可分，但 PG
        connection 異常 ≠ network outage 必走 engine_crash 計 strike（保守原則）。
        """
        lines = [
            "ERROR connection refused 1",
            "ERROR connection refused 2",
            "ERROR connection refused 3",
            "ERROR connection refused 4",
            "ERROR connection refused 5",
            "ERROR sqlx pgconnection unable to query database",
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_unrelated_log_lines_dont_trigger(self):
        """純 metric/lifecycle/heartbeat 行不應命中任何 gate → engine_crash（default）。

        場景：tail 全部 unrelated INFO/DEBUG 行，無 network error 子串、無
        panic、無 PG token。應走最終 default engine_crash（snapshot 過期但
        log 證據不足以推論為 net outage）。為什麼這個 test 重要：證明分類器
        不會把無證據場景錯判為 net-outage（最危險的 false positive：吞掉真
        engine 死鎖）。
        """
        lines = [
            "INFO startup ok",
            "INFO pipeline tick 1",
            "INFO pipeline tick 2",
            "INFO heartbeat",
            "DEBUG some debug output",
            "INFO metric submission ok",
            "INFO pipeline tick 3",
            "INFO pipeline tick 4",
            "INFO heartbeat",
            "INFO pipeline tick 5",
        ]
        path = self._write_log(lines)
        self.assertEqual(classify_engine_failure(path), "engine_crash")

    def test_pg_pool_exhaustion_with_concurrent_dns_errors_not_classified_as_net_outage(self):
        """HIGH-1 R2 production-empirical guard：真實 PG pool 失敗格式被正確識別為 ambiguous。

        E2 R1 用 production `<OPENCLAW_DATA_DIR>/engine.log` 第 4 行 reproduce
        false-positive：tail 內 5 條 connection refused + 1 條真實 ANSI-wrapped PG pool
        timed out 行，原 R1 ambiguous patterns 只列 postgres / pgconnection / sqlx /
        disk full / oom 等 token，**未涵蓋** `pg pool` / `pool timed out` / `db_pool`
        三個 production engine 真實格式 → guard 在最常見 PG 失敗場景設計目標達成度 = 0%。

        R2 補 3 個 token 後本 test 應命中 ambiguous guard → 降級回 engine_crash。

        production 真實字串（含 Rust tracing ANSI escape）對齊：
          - 第 4 行 `error=pool timed out while waiting for an open connection`
          - 「PG pool connect failed — DB writes disabled / PG 連接失敗，DB 寫入已禁用」
          - `db_pool unavailable, BudgetTracker not started`
        三條任一行被讀到時 ambiguous guard 即應啟動（整體降級不依賴連續行數）。
        """
        # Rust tracing 預設格式：\x1b[2m...timestamp...\x1b[0m \x1b[33m WARN\x1b[0m ThreadId(NN) \x1b[2m<module>\x1b[0m\x1b[2m:\x1b[0m <message>
        # 構造 5 條 connection refused（NETWORK_OUTAGE_PATTERN 命中）+ 1 條真實 ANSI-wrapped PG pool timed out
        # 任一 ambiguous token 命中應整體降級回 engine_crash（保守原則）。
        lines = [
            "\x1b[2m2026-05-21T10:14:23.190848Z\x1b[0m \x1b[31mERROR\x1b[0m ThreadId(01) \x1b[2mopenclaw_engine::ws::bybit\x1b[0m\x1b[2m:\x1b[0m connection refused attempt 1",
            "\x1b[2m2026-05-21T10:14:23.291848Z\x1b[0m \x1b[31mERROR\x1b[0m ThreadId(01) \x1b[2mopenclaw_engine::ws::bybit\x1b[0m\x1b[2m:\x1b[0m connection refused attempt 2",
            "\x1b[2m2026-05-21T10:14:23.392848Z\x1b[0m \x1b[31mERROR\x1b[0m ThreadId(01) \x1b[2mopenclaw_engine::ws::bybit\x1b[0m\x1b[2m:\x1b[0m connection refused attempt 3",
            "\x1b[2m2026-05-21T10:14:23.493848Z\x1b[0m \x1b[31mERROR\x1b[0m ThreadId(01) \x1b[2mopenclaw_engine::ws::bybit\x1b[0m\x1b[2m:\x1b[0m connection refused attempt 4",
            "\x1b[2m2026-05-21T10:14:23.594848Z\x1b[0m \x1b[31mERROR\x1b[0m ThreadId(01) \x1b[2mopenclaw_engine::ws::bybit\x1b[0m\x1b[2m:\x1b[0m connection refused attempt 5",
            # 真實 production line 4 字串（lowercase 後含 "pg pool" + "pool timed out"）
            "\x1b[2m2026-05-21T10:14:28.480901Z\x1b[0m \x1b[33m WARN\x1b[0m ThreadId(01) \x1b[2mopenclaw_engine::database::pool\x1b[0m\x1b[2m:\x1b[0m PG pool connect failed — DB writes disabled / PG 連接失敗，DB 寫入已禁用 \x1b[3merror\x1b[0m\x1b[2m=\x1b[0mpool timed out while waiting for an open connection",
        ]
        path = self._write_log(lines)
        # 預期：ambiguous guard 命中 ("pg pool" + "pool timed out" 雙重) → engine_crash
        self.assertEqual(classify_engine_failure(path), "engine_crash")


class TestOnEngineCrashClassification(unittest.TestCase):
    """on_engine_crash() honors classification (strike accounting + canary events)."""

    def setUp(self):
        import pathlib
        self._pathlib = pathlib
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_log(self, lines):
        path = os.path.join(self._tmpdir.name, "engine.log")
        with open(path, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines) + "\n")
        return self._pathlib.Path(path)

    def test_network_outage_does_not_count_strike(self):
        """network_outage classification → no strike, no total_crashes increment.
        網路中斷不計入 strike / total_crashes"""
        state = WatchdogState()
        log_path = self._write_log([
            f"ERROR Temporary failure in name resolution {i}" for i in range(8)
        ])
        action = on_engine_crash(state, 30.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(action, "network_outage")
        self.assertFalse(state.engine_alive)  # still flipped so recovery can re-fire
        self.assertEqual(state.total_crashes, 0)
        self.assertEqual(len(state.crash_timestamps), 0)
        self.assertEqual(state.total_network_outages, 1)
        self.assertEqual(len(state.network_outage_timestamps), 1)

    def test_network_outage_emits_canary_event(self):
        """NETWORK_OUTAGE event written to canary_events.jsonl"""
        state = WatchdogState()
        log_path = self._write_log([
            f"ERROR connection refused {i}" for i in range(6)
        ])
        on_engine_crash(state, 60.0, data_dir=self._tmpdir.name, log_path=log_path)
        events_path = os.path.join(self._tmpdir.name, "canary_events.jsonl")
        self.assertTrue(os.path.exists(events_path))
        with open(events_path, "r", encoding="utf-8") as f:
            events = [json.loads(line) for line in f if line.strip()]
        self.assertTrue(any(e.get("event") == "NETWORK_OUTAGE" for e in events))

    def test_panic_in_tail_still_counts_strike(self):
        """Panic amid DNS flood → engine_crash path; strike counted.
        panic 強制走 engine_crash，即使 tail 有 DNS"""
        state = WatchdogState()
        log_path = self._write_log(
            [f"ERROR Temporary failure in name resolution {i}" for i in range(8)]
            + ["thread 'main' panicked at 'boom'"]
        )
        action = on_engine_crash(state, 30.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(action, "fallback")
        self.assertEqual(state.total_crashes, 1)
        self.assertEqual(state.total_network_outages, 0)

    def test_no_log_path_preserves_legacy_behavior(self):
        """log_path=None → always engine_crash (pre-DNS-CLASSIFY-1 behavior).
        未傳 log_path 時保持既有行為"""
        state = WatchdogState()
        action = on_engine_crash(state, 30.0)
        self.assertEqual(action, "fallback")
        self.assertEqual(state.total_crashes, 1)

    def test_missing_log_file_defaults_to_engine_crash(self):
        """Missing engine.log + log_path param → classifier defaults to engine_crash.
        log_path 指向不存在檔案 → 分類器回退 engine_crash → 正常計 strike"""
        state = WatchdogState()
        missing = self._pathlib.Path(self._tmpdir.name) / "no_such_log.log"
        action = on_engine_crash(state, 30.0, data_dir=self._tmpdir.name, log_path=missing)
        self.assertEqual(action, "fallback")
        self.assertEqual(state.total_crashes, 1)
        self.assertEqual(state.total_network_outages, 0)

    def test_repeat_outage_while_in_outage_state_does_not_recount(self):
        """WATCHDOG-RETRY-LEVELTRIGGER-1：已在中斷狀態時再 poll → 重分類為
        network_outage 但不重複計數，且永不重啟。

        修正後語義：network_outage 每次 poll 重分類（level），但 total_network_outages
        只在下行轉移時 +1（edge）。已 down（engine_alive=False）的重複 poll 回
        network_outage、計數不變、不觸 trigger_restart。"""
        state = WatchdogState(engine_alive=False)
        log_path = self._write_log([
            f"ERROR Temporary failure in name resolution {i}" for i in range(8)
        ])
        action = on_engine_crash(state, 30.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(action, "network_outage")
        # 關鍵不變量：重複 poll 不重複計數
        self.assertEqual(state.total_network_outages, 0)
        self.assertEqual(len(state.network_outage_timestamps), 0)

    # ─── WATCHDOG-RETRY-LEVELTRIGGER-1 (2026-06-05) 死鎖修復回歸 ───

    def test_already_down_crash_retries_restart_when_allowed(self):
        """REGRESSION（死鎖核心）：engine_alive=False（已從 crash down）+ stale +
        should_restart→True ⇒ trigger_restart 必被呼叫。

        修正前：早退「none」，trigger_restart 永不被呼叫 → 引擎卡在第一次失敗，
        熔斷計數永遠到不了 5。修正後：retry 是 level-triggered，已 down 的重複
        poll 仍跑 should_restart→trigger_restart。"""
        state = WatchdogState(engine_alive=False)
        # engine_crash log（非 network_outage），確保走 retry 區塊
        log_path = self._write_log(["ERROR something broke", "thread 'main' panicked at 'boom'"])
        with mock.patch.object(engine_watchdog, "should_restart",
                               return_value=(True, "ok", "ok")) as m_should, \
                mock.patch.object(engine_watchdog, "trigger_restart", return_value=True) as m_trigger:
            action = on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
        # retry 必被觸發（這是修正前 NOT called 的關鍵差異）
        m_should.assert_called_once()
        m_trigger.assert_called_once_with(self._tmpdir.name)
        # 已 down 的重複 poll 不重複計數
        self.assertEqual(state.total_crashes, 0)
        self.assertEqual(action, "fallback")

    def test_already_down_crash_does_not_restart_when_circuit_broken(self):
        """level-triggered retry 仍受 should_restart 閘控：circuit_broken →
        trigger_restart 不被呼叫（證明不會 storm）。"""
        state = WatchdogState(engine_alive=False)
        log_path = self._write_log(["ERROR something broke"])
        with mock.patch.object(engine_watchdog, "should_restart",
                               return_value=(False, "circuit_broken", "circuit broken")) as m_should, \
                mock.patch.object(engine_watchdog, "trigger_restart") as m_trigger:
            on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
        m_should.assert_called_once()
        m_trigger.assert_not_called()

    def test_network_outage_never_restarts_even_on_repeated_polls(self):
        """network_outage 永不重啟（重啟治不了 DNS + 會燒熔斷），即使重複 poll。"""
        log_path = self._write_log([
            f"ERROR Temporary failure in name resolution {i}" for i in range(8)
        ])
        with mock.patch.object(engine_watchdog, "should_restart",
                               return_value=(True, "ok", "ok")) as m_should, \
                mock.patch.object(engine_watchdog, "trigger_restart") as m_trigger:
            # 第一次 poll（轉移）
            state = WatchdogState()
            self.assertEqual(
                on_engine_crash(state, 30.0, data_dir=self._tmpdir.name, log_path=log_path),
                "network_outage",
            )
            # 第二次 poll（已 down，level 重分類）
            self.assertEqual(
                on_engine_crash(state, 30.0, data_dir=self._tmpdir.name, log_path=log_path),
                "network_outage",
            )
        # network_outage 分支永不落到 retry 區塊
        m_should.assert_not_called()
        m_trigger.assert_not_called()
        # 轉移計數一次，重複 poll 不再 +1
        self.assertEqual(state.total_network_outages, 1)

    def test_two_consecutive_crash_polls_count_one_strike(self):
        """No double-count：兩次連續 engine_crash poll 只 +1 total_crashes（edge）。"""
        log_path = self._write_log(["ERROR something broke"])
        with mock.patch.object(engine_watchdog, "should_restart",
                               return_value=(False, "backoff", "backoff window active")), \
                mock.patch.object(engine_watchdog, "trigger_restart"):
            state = WatchdogState()
            on_engine_crash(state, 50.0, data_dir=self._tmpdir.name, log_path=log_path)
            on_engine_crash(state, 50.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(state.total_crashes, 1)
        self.assertEqual(len(state.crash_timestamps), 1)

    # ─── FINDING #2 (2026-06-05) RESTART_SKIPPED canary 去重節流回歸 ───

    def _count_canary_events(self, event_name: str) -> int:
        """數 canary_events.jsonl 中指定 event 的條數。"""
        events_path = os.path.join(self._tmpdir.name, "canary_events.jsonl")
        if not os.path.exists(events_path):
            return 0
        with open(events_path, "r", encoding="utf-8") as f:
            return sum(
                1 for line in f
                if line.strip() and json.loads(line).get("event") == event_name
            )

    def test_held_skip_state_emits_restart_skipped_at_most_once(self):
        """FINDING #2 核心：N 次連續 poll 處於同一 skip key（held circuit_broken）
        ⇒ 至多 1 條 RESTART_SKIPPED canary 事件（避免終態下每 2s 灌一條淹沒
        RESTART_CIRCUIT_BROKEN）。

        以 engine_alive=False 起始確保每次 poll 都跑 level-triggered retry → skip
        分支；should_restart 用 CONSTANT 3-tuple 模擬 held circuit_broken。此測試
        守的是「完全沒節流」這個 mutation；per-poll 字串變化的盲區由下面
        test_backoff_window_emits_restart_skipped_at_most_once 用真 should_restart
        驅動覆蓋。"""
        log_path = self._write_log(["ERROR something broke"])
        with mock.patch.object(
            engine_watchdog, "should_restart",
            return_value=(False, "circuit_broken",
                          "circuit broken after 5 consecutive failures"),
        ), mock.patch.object(engine_watchdog, "trigger_restart") as m_trigger:
            state = WatchdogState(engine_alive=False)
            for _ in range(10):
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
        # held circuit_broken 永不重啟
        m_trigger.assert_not_called()
        # 10 次 poll 同一 key → 只寫 1 條 RESTART_SKIPPED
        self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 1)

    def test_restart_skipped_reason_change_emits_again(self):
        """FINDING #2：reason_key CHANGE 仍要再發一次（不可被去重 marker 永久吞掉）。

        先 held backoff key 數 poll（1 條），再切到 circuit_broken key
        （第 2 條），證明 marker 是「key 改變才發」而非「發過就永遠不發」。"""
        log_path = self._write_log(["ERROR something broke"])
        state = WatchdogState(engine_alive=False)
        # 階段一：held backoff window key（detail 帶倒數秒，但去重看 key）
        with mock.patch.object(
            engine_watchdog, "should_restart",
            return_value=(False, "backoff", "backoff window active, 120s remaining"),
        ), mock.patch.object(engine_watchdog, "trigger_restart"):
            for _ in range(4):
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 1)
        # 階段二：key 切換為 circuit_broken → 必須再發一條
        with mock.patch.object(
            engine_watchdog, "should_restart",
            return_value=(False, "circuit_broken",
                          "circuit broken after 5 consecutive failures"),
        ), mock.patch.object(engine_watchdog, "trigger_restart"):
            for _ in range(4):
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 2)

    def test_recovery_resets_skip_marker_so_later_skip_re_emits(self):
        """FINDING #2：成功恢復清 marker → 之後同 key 再 skip 仍能再發一次。

        模擬：held skip（1 條）→ on_engine_recovery 清 marker → 再 held 同 key
        （因 marker 已清，再發第 2 條）。證明 reset-on-recovery 正確。"""
        log_path = self._write_log(["ERROR something broke"])
        with mock.patch.object(
            engine_watchdog, "should_restart",
            return_value=(False, "circuit_broken",
                          "circuit broken after 5 consecutive failures"),
        ), mock.patch.object(engine_watchdog, "trigger_restart"):
            state = WatchdogState(engine_alive=False)
            for _ in range(3):
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
            self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 1)
            # 引擎恢復（清 marker），再轉回 down
            on_engine_recovery(state, data_dir=self._tmpdir.name)
            state.engine_alive = False
            for _ in range(3):
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 2)

    # ─── FINDING #2-HIGH-1 (2026-06-05) 真 should_restart 驅動（per-poll 變字串盲區）───
    # E2 抓到：上面的去重測試 mock should_restart 回 CONSTANT 字串，看不到 backoff
    # 分支 detail 內倒數秒 per-poll 遞減的事實。下面兩個測試 NOT mock should_restart
    # 的 reason，直接擺好 state（next_allowed_restart_ts / consecutive_failures）讓
    # 真 backoff window 生效，證明 ≤1 條 RESTART_SKIPPED；並驗 key 變化會再發。

    def _poll_clock(self):
        """回傳 (advance, fake_time)：fake_time 在單一 poll 內回固定值，advance()
        把時鐘推進一個 POLL_INTERVAL（2s）。

        為什麼不直接用 side_effect 列表：on_engine_crash 的 engine_crash 路徑每 poll
        會多次呼叫 time.time()（classify_engine_failure 內 mtime / rotated-log 掃描也
        呼叫），call 次數依路徑而變，用固定長度 side_effect 會 StopIteration。本 clock
        讓「同一 poll 內所有 time.time() 回同值、poll 間才遞增」，與內部 call 次數解耦，
        從而真實逼出 backoff detail 的 per-poll 倒數秒變化。"""
        cur = {"t": 100000.0}

        def fake_time():
            return cur["t"]

        def advance():
            cur["t"] += 2.0  # POLL_INTERVAL=2s

        return advance, fake_time

    def test_backoff_window_emits_restart_skipped_at_most_once(self):
        """HIGH-1 核心：真 backoff window 整段只發 ≤1 條 RESTART_SKIPPED。

        擺一個遠在未來的 next_allowed_restart_ts，使 should_restart 真的走 backoff
        分支（detail 含 per-poll 遞減的 "Ns remaining"）。連續 N 次 poll（now 每 poll
        遞增 2s，故每 poll 的倒數字串都不同），should_restart NOT mock。修正前（用
        detail 字串去重）會每 poll 各寫一條；修正後（用 "backoff" key 去重）整段只 1 條。

        mutation-bite：把 emit_restart_skipped_if_new 的去重從 key 改回 detail 字串
        ⇒ N 條 RESTART_SKIPPED，本測試紅（已實機驗證，見 E1 報告）。"""
        log_path = self._write_log(["ERROR something broke"])
        advance, fake_time = self._poll_clock()
        # 擺好真 backoff state：未熔斷、退避窗口遠在未來（base+10000）。
        engine_watchdog.save_state(self._tmpdir.name, {
            "engine_alive": False,
            "consecutive_failures": 2,
            "circuit_broken": False,
            "next_allowed_restart_ts": 100000.0 + 10000.0,
        })
        poll_count = 8
        seen_details = set()
        # trigger_restart 仍 mock，避免萬一 allowed 時真的跑子進程；should_restart
        # 維持「真」（本測試重點）。time.time 用 poll-clock（同 poll 內固定、poll 間 +2s）。
        with mock.patch.object(engine_watchdog, "trigger_restart") as m_trigger, \
                mock.patch.object(engine_watchdog.time, "time", side_effect=fake_time):
            state = WatchdogState(engine_alive=False)
            for _ in range(poll_count):
                # 自證：每 poll 真 should_restart 的 detail 不同（否則退化成常字串、失去 bite）。
                allowed, key, detail = engine_watchdog.should_restart(
                    self._tmpdir.name, engine_watchdog.time.time())
                self.assertFalse(allowed)
                self.assertEqual(key, "backoff")
                seen_details.add(detail)
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
                advance()
        # backoff 期間永不重啟
        m_trigger.assert_not_called()
        # 倒數秒 detail 確實 per-poll 變化（否則本測試沒抓到 string-throttle 盲區）。
        self.assertGreater(len(seen_details), 1, "backoff detail 必須 per-poll 變化才有 bite")
        # 整段 backoff window 同一 "backoff" key → 只 1 條 RESTART_SKIPPED
        self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 1)

    def test_restart_skipped_reason_key_change_emits_again(self):
        """HIGH-1：真 backoff → circuit_broken 轉移時，key 變化必再發一條。

        先擺真 backoff（窗口在未來）跑數 poll（detail per-poll 變但 key 穩 → 1 條），
        再把 state 推成 circuit_broken（consecutive_failures 達 MAX + circuit_broken=
        True），should_restart 全程 NOT mock，驗第 2 條在 key 由 "backoff"→
        "circuit_broken" 時被寫出。"""
        log_path = self._write_log(["ERROR something broke"])
        advance, fake_time = self._poll_clock()
        engine_watchdog.save_state(self._tmpdir.name, {
            "engine_alive": False,
            "consecutive_failures": 2,
            "circuit_broken": False,
            "next_allowed_restart_ts": 100000.0 + 10000.0,
        })
        state = WatchdogState(engine_alive=False)
        # 階段一：真 backoff window，數 poll → 1 條（key 全程 "backoff"）。
        with mock.patch.object(engine_watchdog, "trigger_restart"), \
                mock.patch.object(engine_watchdog.time, "time", side_effect=fake_time):
            _, key_a, _ = engine_watchdog.should_restart(
                self._tmpdir.name, engine_watchdog.time.time())
            self.assertEqual(key_a, "backoff")
            for _ in range(4):
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
                advance()
        self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 1)
        # 推成 circuit_broken（保留剛被 emit 寫進的 last_restart_skipped_reason marker）。
        st = engine_watchdog.load_state(self._tmpdir.name)
        st["circuit_broken"] = True
        st["consecutive_failures"] = engine_watchdog.MAX_CONSECUTIVE_FAILURES
        engine_watchdog.save_state(self._tmpdir.name, st)
        _, key_b, _ = engine_watchdog.should_restart(self._tmpdir.name, 100000.0)
        self.assertEqual(key_b, "circuit_broken")
        # 階段二：key 變 circuit_broken → 必再發一條。
        with mock.patch.object(engine_watchdog, "trigger_restart"), \
                mock.patch.object(engine_watchdog.time, "time", side_effect=fake_time):
            for _ in range(4):
                on_engine_crash(state, 99.0, data_dir=self._tmpdir.name, log_path=log_path)
                advance()
        self.assertEqual(self._count_canary_events("RESTART_SKIPPED"), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# WATCHDOG-ALERT-WIRE (2026-06-05) HIGH-1：告警「接線」整合測試（驅動真狀態機）
#
# 為什麼這個 class 是 HIGH-1 的核心：emit_engine_down_alert_if_new /
# _send_alert_best_effort 的單元行為已在 test_watchdog_alert.py 證過，但「告警有沒有
# 真的被狀態機 trigger_restart / on_engine_crash / on_engine_recovery 在對的轉移點呼到」
# 沒被守。E2 證明兩個 seam mutation（刪掉 trigger_restart 的熔斷 emit 呼叫、把
# prolonged-down 的 key 釘死）都能讓整個既有測試套件 100% 全綠 —— 那正是這個功能要
# 防的「靜默宕機」失敗模式。以下三條直接驅動真狀態機（不 mock emit/標記函數，只 mock
# _send_alert_best_effort 與 subprocess/trigger_restart 以免發真 HTTP / 跑真子進程），
# 每條都附 seam-mutation 紅燈證明（見 E1 報告）。
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchdogAlertWiring(unittest.TestCase):
    """告警接線整合：熔斷 emit-once / 恢復清 marker 後可再 emit / 持續宕機每窗口一次。

    通則：mock _send_alert_best_effort（避免真 HTTP，且可斷言被呼次數/severity），
    但 emit_engine_down_alert_if_new / clear_engine_down_alert_marker / 去重 marker
    全走真路徑 —— 這樣才測得到「接線」而非孤立函數。canary ENGINE_DOWN_ALERT_SENT
    計數是 emit 真的發生過的稽核證據。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.dir = self._tmpdir.name
        self._pathlib = __import__("pathlib")

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_log(self, lines):
        path = os.path.join(self.dir, "engine.log")
        with open(path, "w", encoding="utf-8") as f:
            if lines:
                f.write("\n".join(lines) + "\n")
        return self._pathlib.Path(path)

    def _count_alert_sent(self, alert_key=None):
        """數 ENGINE_DOWN_ALERT_SENT canary 事件（可選按 alert_key 過濾）。"""
        path = os.path.join(self.dir, "canary_events.jsonl")
        if not os.path.exists(path):
            return 0
        n = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("event") != "ENGINE_DOWN_ALERT_SENT":
                    continue
                if alert_key is None or ev.get("alert_key") == alert_key:
                    n += 1
        return n

    def _alert_keys_sent(self):
        """回傳所有 ENGINE_DOWN_ALERT_SENT 的 alert_key 序列（按寫入順序）。"""
        path = os.path.join(self.dir, "canary_events.jsonl")
        keys = []
        if not os.path.exists(path):
            return keys
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("event") == "ENGINE_DOWN_ALERT_SENT":
                    keys.append(ev.get("alert_key"))
        return keys

    def _drive_to_circuit_broken(self):
        """用真 trigger_restart 連續失敗驅動到 circuit_broken（不 mock trigger_restart）。

        mock subprocess.run 回非零（真失敗路徑），故每次 trigger_restart 都遞增
        consecutive_failures；第 MAX_CONSECUTIVE_FAILURES 次翻 circuit_broken=True，
        熔斷分支的 emit_engine_down_alert_if_new("circuit_broken", ...) 才被觸發。
        trigger_restart 本身不檢 backoff（那是 should_restart 的事），故可直接連呼。"""
        fail = mock.Mock()
        fail.returncode = 1
        fail.stderr = "boom"
        with mock.patch.object(engine_watchdog.subprocess, "run", return_value=fail):
            for _ in range(engine_watchdog.MAX_CONSECUTIVE_FAILURES):
                trigger_restart(self.dir)

    # ─── 整合 1：熔斷 emit-once（再 poll 仍熔斷 → 不重發）───

    def test_circuit_break_emits_alert_exactly_once(self):
        """HIGH-1 整合①：連續重啟失敗到 circuit_broken ⇒ 恰好一條 circuit_broken
        告警；仍熔斷時再呼 trigger_restart ⇒ 不再發（去重）。

        驅動真 trigger_restart 狀態機（subprocess 失敗），只 mock _send_alert_best_effort。
        斷言：(a) _send_alert_best_effort 恰被呼一次、severity=CRITICAL；
        (b) ENGINE_DOWN_ALERT_SENT canary 恰一條、alert_key='circuit_broken'；
        (c) emit_engine_down_alert_if_new 在熔斷時被真的呼到一次（接線存在）。

        seam-mutation（E2 要求的 bite）：刪掉 trigger_restart 熔斷分支裡那行
        emit_engine_down_alert_if_new(...) ⇒ 本測試紅（0 條告警）。已實機驗證見 E1 報告。"""
        with mock.patch.object(engine_watchdog, "_send_alert_best_effort") as m_send, \
                mock.patch.object(
                    engine_watchdog, "emit_engine_down_alert_if_new",
                    wraps=engine_watchdog.emit_engine_down_alert_if_new) as m_emit:
            self._drive_to_circuit_broken()
            # 確認真的熔斷了（前置條件）。
            self.assertTrue(engine_watchdog.load_state(self.dir).get("circuit_broken"))
            # 接線：熔斷分支真的呼到 emit（key='circuit_broken'）。
            emit_calls = [c for c in m_emit.call_args_list if c.args[1] == "circuit_broken"]
            self.assertEqual(len(emit_calls), 1, "熔斷時 emit 必被呼且僅一次")
            # 仍熔斷時再 poll（再失敗）⇒ 同 key 去重，不再發第二條。
            again = mock.Mock()
            again.returncode = 1
            again.stderr = "boom"
            with mock.patch.object(engine_watchdog.subprocess, "run", return_value=again):
                trigger_restart(self.dir)
                trigger_restart(self.dir)
        # _send_alert_best_effort 恰一次、CRITICAL。
        self.assertEqual(m_send.call_count, 1)
        self.assertEqual(m_send.call_args.args[2], "CRITICAL")
        # canary 稽核：恰一條 circuit_broken。
        self.assertEqual(self._count_alert_sent("circuit_broken"), 1)
        self.assertEqual(self._count_alert_sent(), 1)

    # ─── 整合 2：恢復清 marker → all-clear 告警 + 新一輪宕機可再發 ───

    def test_recovery_clears_marker_and_new_episode_re_emits(self):
        """HIGH-1 整合②：熔斷發過告警後引擎恢復（新鮮快照）⇒ 發 RECOVERED all-clear
        告警且 clear_engine_down_alert_marker 真的執行（marker 清空）；隨後新一輪宕機
        ⇒ circuit_broken 告警再次發出（因 marker 已被清）。

        驅動真 trigger_restart→熔斷（第 1 條 down 告警）→on_engine_recovery（真路徑，
        清 marker + 發 INFO）→再 trigger_restart 失敗（仍熔斷）→第 2 條 down 告警。

        seam-mutation（E2 要求的 bite）：把 on_engine_recovery 裡的
        clear_engine_down_alert_marker(data_dir) 改成 no-op（marker 殘留）⇒ 新一輪
        宕機被永久去重吞掉 ⇒ 第 2 條告警不發 ⇒ 本測試紅。已實機驗證見 E1 報告。"""
        with mock.patch.object(engine_watchdog, "_send_alert_best_effort") as m_send:
            # 第一輪：驅動到熔斷 → 第 1 條 down 告警。
            self._drive_to_circuit_broken()
            self.assertEqual(self._count_alert_sent("circuit_broken"), 1)
            down_send_calls = m_send.call_count
            self.assertGreaterEqual(down_send_calls, 1)
            # marker 已落盤（down-alert 已發）。
            self.assertEqual(
                engine_watchdog.load_state(self.dir).get("last_engine_down_alert_key"),
                "circuit_broken",
            )

            # 引擎恢復（真路徑：on_engine_recovery 清 marker + 發 INFO all-clear）。
            state = WatchdogState(engine_alive=False)
            on_engine_recovery(state, data_dir=self.dir)
            self.assertTrue(state.engine_alive)
            # all-clear 告警有發（severity=INFO），且確實多了一通。
            self.assertEqual(m_send.call_count, down_send_calls + 1)
            self.assertEqual(m_send.call_args.args[2], "INFO")
            # clear_engine_down_alert_marker 真的執行：marker 被清空。
            cleared = engine_watchdog.load_state(self.dir)
            self.assertIsNone(cleared.get("last_engine_down_alert_key"))
            self.assertNotIn("engine_down_since_ts", cleared)

            # 新一輪宕機：仍熔斷（consecutive 已 >= MAX），但 marker 已清 → 再發第 2 條。
            again = mock.Mock()
            again.returncode = 1
            again.stderr = "boom"
            with mock.patch.object(engine_watchdog.subprocess, "run", return_value=again):
                trigger_restart(self.dir)
        # circuit_broken 告警共 2 條（marker-clear 讓再 down 能再發）。
        self.assertEqual(self._count_alert_sent("circuit_broken"), 2)

    # ─── 整合 3：持續宕機 re-alert 每 RE_ALERT_INTERVAL_SECONDS 窗口恰一次 ───

    def test_prolonged_down_re_alerts_once_per_window_not_per_poll(self):
        """HIGH-1 整合③：熔斷終態下，on_engine_crash 每 2s poll 不會每 poll 都重發；
        而是每 RE_ALERT_INTERVAL_SECONDS（4h）窗口恰發一條 re-ping（key 隨整數小時變化）。

        擺好真 circuit_broken state（含 engine_down_since_ts / last_engine_down_alert_ts），
        用 poll-clock 推進跨多個 4h 窗口，每窗口內也跑數個 2s poll。should_restart 走
        circuit_broken 分支（不重啟），trigger_restart mock，_send_alert_best_effort mock。

        斷言：總 re-ping 數 == 窗口數（非 poll 數）；key 形如 circuit_broken_reping_<h>
        且每窗口的整數小時各異（4/8/12...）。

        seam-mutation（E2 要求的 bite，也正是 E2 證過的那個）：把 on_engine_crash
        re-alert 的 key 從 f"circuit_broken_reping_{hours_down}" 釘死成常數
        （如 "circuit_broken_reping_0"）⇒ 第一窗口後 key 永不變 → 去重永久吞掉後續窗口
        ⇒ 只剩 1 條 ⇒ 本測試紅。已實機驗證見 E1 報告。"""
        log_path = self._write_log(["ERROR something broke"])
        interval = engine_watchdog.RE_ALERT_INTERVAL_SECONDS
        base = 100000.0
        # 起始：已熔斷、已發過初次告警（last_engine_down_alert_ts=base），down-since=base。
        engine_watchdog.save_state(self.dir, {
            "engine_alive": False,
            "circuit_broken": True,
            "consecutive_failures": engine_watchdog.MAX_CONSECUTIVE_FAILURES,
            "engine_down_since_ts": base,
            "last_engine_down_alert_ts": base,
            "last_engine_down_alert_key": "circuit_broken",
        })

        cur = {"t": base}

        def fake_time():
            return cur["t"]

        windows = 3  # 跨 3 個 4h 窗口
        polls_per_window = 4  # 每窗口內額外跑幾個 2s poll（證明不是每 poll 都發）
        # trigger_restart mock（避免真子進程；circuit_broken 下 should_restart 本也不會 allow，
        # 但保險起見 mock 掉，且確保它不會改 circuit_broken）。_send_alert_best_effort mock。
        with mock.patch.object(engine_watchdog, "trigger_restart") as m_trigger, \
                mock.patch.object(engine_watchdog, "_send_alert_best_effort") as m_send, \
                mock.patch.object(engine_watchdog.time, "time", side_effect=fake_time):
            state = WatchdogState(engine_alive=False)
            for w in range(windows):
                # 推進到下一個窗口邊界（+interval），觸發該窗口的 re-ping。
                cur["t"] = base + interval * (w + 1)
                on_engine_crash(state, 99.0, data_dir=self.dir, log_path=log_path)
                # 同窗口內再跑幾個 2s poll：距上次告警 < interval → 不應再發。
                for _ in range(polls_per_window):
                    cur["t"] += engine_watchdog.POLL_INTERVAL_SECONDS
                    on_engine_crash(state, 99.0, data_dir=self.dir, log_path=log_path)
        # circuit_broken 終態下絕不重啟。
        m_trigger.assert_not_called()
        # 每窗口恰一條 re-ping（共 windows 條），不是每 poll 一條。
        reping_keys = [k for k in self._alert_keys_sent() if k.startswith("circuit_broken_reping_")]
        self.assertEqual(
            len(reping_keys), windows,
            f"應每窗口恰一條 re-ping（共 {windows}），實得 {reping_keys}",
        )
        # key 隨整數小時變化（4/8/12...），各窗口互異 → 證明非釘死常數。
        self.assertEqual(len(set(reping_keys)), windows, f"各窗口 key 應互異：{reping_keys}")
        hours_step = int(interval // 3600)
        expected = [f"circuit_broken_reping_{hours_step * (w + 1)}" for w in range(windows)]
        self.assertEqual(reping_keys, expected)
        # _send_alert_best_effort 也恰被呼 windows 次（每窗口一條 CRITICAL）。
        self.assertEqual(m_send.call_count, windows)


class TestTriggerRestartBindHostSanitize(unittest.TestCase):
    """WATCHDOG-BINDHOST-SANITIZE-1 (2026-06-05)：trigger_restart 餵安全 bind-host。

    為什麼測 env= kwarg：被污染的父 env 帶 OPENCLAW_BIND_HOST=0.0.0.0 會被
    restart_all.sh 內 resolve_openclaw_api_bind_host exit=2 拒絕 → 自愈永久卡死。
    修復把危險值正規化成 auto（安全預設），合法值原樣放行。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _run_and_capture_env(self) -> dict:
        """跑 trigger_restart（mock subprocess.run），回傳傳給 subprocess 的 env=。"""
        fake_result = mock.Mock()
        fake_result.returncode = 0
        fake_result.stderr = ""
        with mock.patch.object(engine_watchdog.subprocess, "run",
                               return_value=fake_result) as m_run:
            trigger_restart(self._tmpdir.name)
        self.assertEqual(m_run.call_count, 1)
        env = m_run.call_args.kwargs.get("env")
        self.assertIsNotNone(env, "subprocess.run must receive an explicit env=")
        return env

    def test_dangerous_bind_host_normalized_to_auto(self):
        """OPENCLAW_BIND_HOST=0.0.0.0 → 子進程 env 變 auto。"""
        with mock.patch.dict(os.environ, {"OPENCLAW_BIND_HOST": "0.0.0.0"}, clear=False):
            env = self._run_and_capture_env()
        self.assertEqual(env.get("OPENCLAW_BIND_HOST"), "auto")

    def test_ipv6_any_and_empty_normalized_to_auto(self):
        """:: 與空字串同屬危險集，皆正規化 auto。"""
        for bad in ("::", "", "  "):
            with self.subTest(bad=bad):
                with mock.patch.dict(os.environ, {"OPENCLAW_BIND_HOST": bad}, clear=False):
                    env = self._run_and_capture_env()
                self.assertEqual(env.get("OPENCLAW_BIND_HOST"), "auto")

    def test_tailscale_unavailable_set_normalized_to_auto(self):
        """FINDING #1 (2026-06-05)：{tailscale, tailscale-ip, ts} 在 tailscale 不在
        PATH / 無 IPv4 時同樣被 resolver exit=2 拒絕，會像 0.0.0.0 一樣卡死自愈；
        故 watchdog 的 recovery 子進程把這些值也正規化成 never-fail 的 auto。

        為什麼納入這三個：對齊 api_bind_host.sh case 分支 "tailscale"|"tailscale-ip"|"ts"
        的 exit=2 路徑（tailscale 不可用時）。這只動自愈子進程的 recovery env，
        operator 手動發起的重啟仍照舊 fail-closed-and-loud（未碰 api_bind_host.sh）。"""
        for ts_val in ("tailscale", "tailscale-ip", "ts"):
            with self.subTest(ts_val=ts_val):
                with mock.patch.dict(os.environ, {"OPENCLAW_BIND_HOST": ts_val}, clear=False):
                    env = self._run_and_capture_env()
                self.assertEqual(env.get("OPENCLAW_BIND_HOST"), "auto")

    def test_legit_bind_host_passes_through(self):
        """合法值（具體 Tailscale IP / auto / 127.0.0.1）原樣放行。

        注意：'tailscale'/'tailscale-ip'/'ts' 已移入 exit=2 拒絕集（見
        test_tailscale_unavailable_set_normalized_to_auto），不再屬於 pass-through。"""
        for good in ("100.64.1.2", "auto", "127.0.0.1"):
            with self.subTest(good=good):
                with mock.patch.dict(os.environ, {"OPENCLAW_BIND_HOST": good}, clear=False):
                    env = self._run_and_capture_env()
                self.assertEqual(env.get("OPENCLAW_BIND_HOST"), good)

    def test_unset_bind_host_stays_unset(self):
        """未設置 OPENCLAW_BIND_HOST → 保持未設置（不強加 auto）。"""
        env_no_bind = {k: v for k, v in os.environ.items() if k != "OPENCLAW_BIND_HOST"}
        with mock.patch.dict(os.environ, env_no_bind, clear=True):
            env = self._run_and_capture_env()
        self.assertNotIn("OPENCLAW_BIND_HOST", env)


if __name__ == "__main__":
    unittest.main()
