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
from engine_watchdog import (
    check_snapshot_freshness,
    classify_engine_failure,
    on_engine_crash,
    on_engine_recovery,
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


class TestWatchdogCrashRecovery(unittest.TestCase):

    def test_first_crash_triggers_fallback(self):
        """First crash → fallback (not rollback) / 首次崩潰 → 降級"""
        state = WatchdogState()
        action = on_engine_crash(state, 15.0)
        self.assertEqual(action, "fallback")
        self.assertFalse(state.engine_alive)
        self.assertEqual(state.total_crashes, 1)

    def test_duplicate_crash_ignored(self):
        """Crash while already in crash state → none / 已在崩潰狀態再崩潰 → 無動作"""
        state = WatchdogState(engine_alive=False)
        action = on_engine_crash(state, 15.0)
        self.assertEqual(action, "none")

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

    def test_non_consecutive_dns_below_threshold(self):
        """Interleaved DNS lines break the run / DNS 被非匹配行打斷 → 不夠連續"""
        lines = []
        for i in range(8):
            lines.append(f"ERROR Temporary failure in name resolution {i}")
            lines.append(f"INFO unrelated heartbeat {i}")
        path = self._write_log(lines)
        # Longest run = 1 (every DNS line is broken by a heartbeat)
        self.assertEqual(classify_engine_failure(path), "engine_crash")

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

    def test_repeat_outage_while_in_outage_state_returns_none(self):
        """Second outage while engine_alive=False is a no-op (dedup guard).
        已在中斷狀態時再次 on_engine_crash → none"""
        state = WatchdogState(engine_alive=False)
        log_path = self._write_log([
            f"ERROR Temporary failure in name resolution {i}" for i in range(8)
        ])
        action = on_engine_crash(state, 30.0, data_dir=self._tmpdir.name, log_path=log_path)
        self.assertEqual(action, "none")
        self.assertEqual(state.total_network_outages, 0)


if __name__ == "__main__":
    unittest.main()
