#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────
# MODULE_NOTE
# 模組目的：W-AUDIT-8a C1 v2 probe 單元測試。
#          覆蓋：
#            - build_topics dedup
#            - parse_args 預設值
#            - classify_payload poison / topic counters / candidate samples
#            - _backoff_for_attempt 指數退避序列
#            - _interim_verdict 健康度評估
#            - assess() verdict mapping（5 條 PASS/FAIL 路徑）
#            - reconnect path（mock disconnect → simulate retry）
#            - restart cap（連續 3 sessions 觸發 RECONNECT_EXHAUSTED）
#            - checkpoint JSON 60min boundary write
#
# 跑法：
#   python3 -m unittest helper_scripts.bybit.test_liquidation_topic_probe_v2 -v
# 或：
#   cd helper_scripts/bybit && python3 -m unittest test_liquidation_topic_probe_v2 -v
# ─────────────────────────────────────────────────────────
"""Unit tests for liquidation_topic_probe_v2 — resilient harness."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 把本目錄加到 sys.path 才能直接 import 同目錄模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from liquidation_topic_probe_v2 import (  # noqa: E402
    CHECKPOINT_FILE_NAME,
    DEFAULT_PING_INTERVAL_SEC,
    DEFAULT_TOPIC,
    DEFAULT_URL,
    PASS_MIN_OBSERVED_SEC,
    PASS_MIN_UPTIME_RATIO,
    POISON_PATTERNS,
    RECONNECT_BACKOFF_CAP_SEC,
    RECONNECT_BACKOFF_SEC,
    RECONNECT_MAX_ATTEMPTS_PER_SESSION,
    ProbeV2Stats,
    ReconnectEvent,
    RestartEvent,
    _backoff_for_attempt,
    _interim_verdict,
    _write_checkpoint,
    assess,
    build_topics,
    classify_payload,
    parse_args,
)


# ── 基礎組件測試 ────────────────────────────────────────────────────────


class TestBuildTopics(unittest.TestCase):
    """`build_topics()` dedup + 預設 control 模板。"""

    def test_default_btcusdt_5_topics(self):
        topics = build_topics(DEFAULT_TOPIC, "BTCUSDT")
        self.assertEqual(topics[0], DEFAULT_TOPIC)
        self.assertEqual(len(topics), 5)
        self.assertIn("tickers.BTCUSDT", topics)
        self.assertIn("orderbook.50.BTCUSDT", topics)
        self.assertIn("publicTrade.BTCUSDT", topics)
        self.assertIn("kline.1.BTCUSDT", topics)

    def test_dedup_when_candidate_is_control_template(self):
        topics = build_topics("tickers.BTCUSDT", "BTCUSDT")
        self.assertEqual(topics[0], "tickers.BTCUSDT")
        # 4 control templates - 1 dup = 4 distinct topics total
        self.assertEqual(len(topics), 4)

    def test_custom_symbol(self):
        topics = build_topics("allLiquidation.ETHUSDT", "ETHUSDT")
        self.assertIn("tickers.ETHUSDT", topics)
        self.assertNotIn("tickers.BTCUSDT", topics)


class TestParseArgs(unittest.TestCase):
    """`parse_args()` 預設值 + v2 新旗標。"""

    def test_default_values(self):
        args = parse_args([])
        self.assertEqual(args.url, DEFAULT_URL)
        self.assertEqual(args.topic, DEFAULT_TOPIC)
        self.assertEqual(args.duration_sec, 86_400)
        self.assertEqual(args.ping_interval_sec, DEFAULT_PING_INTERVAL_SEC)
        self.assertEqual(args.proof_min_duration_sec, PASS_MIN_OBSERVED_SEC)
        self.assertEqual(args.proof_min_uptime_ratio, PASS_MIN_UPTIME_RATIO)
        self.assertEqual(args.max_restart, 3)
        self.assertEqual(args.checkpoint_interval_sec, 3600)
        self.assertFalse(args.enable_reconnect)
        self.assertFalse(args.start_utc_midnight)
        self.assertFalse(args.dry_run)

    def test_enable_reconnect_flag(self):
        args = parse_args(["--enable-reconnect"])
        self.assertTrue(args.enable_reconnect)

    def test_session_id_override(self):
        args = parse_args(["--session-id", "c1_v2_TEST_2026"])
        self.assertEqual(args.session_id, "c1_v2_TEST_2026")


class TestBackoffSequence(unittest.TestCase):
    """`_backoff_for_attempt()` 指數退避 + cap。"""

    def test_first_six_attempts_exponential(self):
        # design §3.2: 1, 2, 4, 8, 16, 32
        expected = [1, 2, 4, 8, 16, 32]
        for i, exp in enumerate(expected, start=1):
            self.assertEqual(_backoff_for_attempt(i), float(exp))

    def test_seventh_attempt_caps_at_60(self):
        # attempt 7+ all cap at 60s
        self.assertEqual(_backoff_for_attempt(7), float(RECONNECT_BACKOFF_CAP_SEC))
        self.assertEqual(_backoff_for_attempt(99), float(RECONNECT_BACKOFF_CAP_SEC))

    def test_zero_or_negative_returns_zero(self):
        self.assertEqual(_backoff_for_attempt(0), 0.0)
        self.assertEqual(_backoff_for_attempt(-1), 0.0)

    def test_backoff_seq_constant_matches_design(self):
        # 保護 RECONNECT_BACKOFF_SEC 不被無意修改
        self.assertEqual(RECONNECT_BACKOFF_SEC, (1, 2, 4, 8, 16, 32))
        self.assertEqual(RECONNECT_MAX_ATTEMPTS_PER_SESSION, 6)


# ── classify_payload 測試 ───────────────────────────────────────────────


class TestClassifyPayload(unittest.TestCase):
    """`classify_payload()` poison / subscribe / pong / topic counters。"""

    def setUp(self):
        self.stats = ProbeV2Stats(
            session_id="test",
            started_at_utc="2026-05-16T00:00:00+00:00",
            candidate_topic="allLiquidation.BTCUSDT",
        )

    def test_subscribe_success(self):
        classify_payload({"success": True, "op": "subscribe"}, self.stats, 20)
        self.assertEqual(self.stats.subscribe_success_count, 1)
        self.assertEqual(self.stats.subscribe_failure_count, 0)

    def test_subscribe_failure_with_poison(self):
        classify_payload(
            {"success": False, "ret_msg": "handler not found", "op": "subscribe"},
            self.stats,
            20,
        )
        self.assertEqual(self.stats.subscribe_failure_count, 1)
        self.assertEqual(len(self.stats.poison_events), 1)
        self.assertIn("handler not found", self.stats.poison_events[0])

    def test_pong_recognized(self):
        classify_payload({"op": "pong"}, self.stats, 20)
        self.assertEqual(self.stats.pongs_seen, 1)
        # ret_msg style
        classify_payload({"ret_msg": "pong"}, self.stats, 20)
        self.assertEqual(self.stats.pongs_seen, 2)

    def test_candidate_topic_message_collected(self):
        msg = {
            "topic": "allLiquidation.BTCUSDT",
            "type": "snapshot",
            "data": [{"T": 1745386800000, "s": "BTCUSDT", "S": "Sell", "v": "0.001", "p": "98765.5"}],
        }
        classify_payload(msg, self.stats, 20)
        self.assertEqual(self.stats.candidate_messages_seen, 1)
        self.assertEqual(self.stats.topic_message_counts["allLiquidation.BTCUSDT"], 1)
        self.assertEqual(len(self.stats.candidate_samples), 1)

    def test_candidate_samples_cap(self):
        # max=3 上限後不再 append
        for i in range(10):
            classify_payload(
                {"topic": "allLiquidation.BTCUSDT", "i": i},
                self.stats,
                3,
            )
        self.assertEqual(self.stats.candidate_messages_seen, 10)
        # 但只存了 3 個 sample
        self.assertEqual(len(self.stats.candidate_samples), 3)
        # 全部都計入 topic counter
        self.assertEqual(self.stats.topic_message_counts["allLiquidation.BTCUSDT"], 10)

    def test_poison_patterns_all_caught(self):
        for pattern in POISON_PATTERNS:
            stats = ProbeV2Stats(
                session_id="x",
                started_at_utc="2026-05-16T00:00:00+00:00",
                candidate_topic="topicx",
            )
            classify_payload({"ret_msg": pattern.upper(), "garbage": 1}, stats, 20)
            self.assertGreaterEqual(
                len(stats.poison_events),
                1,
                f"pattern '{pattern}' should be caught case-insensitively",
            )


# ── interim_verdict 測試 ────────────────────────────────────────────────


class TestInterimVerdict(unittest.TestCase):
    """`_interim_verdict()` 健康度評估。"""

    def _stats(self, **overrides):
        s = ProbeV2Stats(
            session_id="x",
            started_at_utc="2026-05-16T00:00:00+00:00",
            elapsed_sec=7200,
            uptime_sec=7100,
            uptime_ratio=0.98,
        )
        for k, v in overrides.items():
            setattr(s, k, v)
        return s

    def test_healthy(self):
        self.assertEqual(_interim_verdict(self._stats()), "IN_PROGRESS_HEALTHY")

    def test_poison_dominates(self):
        s = self._stats(poison_events=["handler not found"])
        self.assertEqual(_interim_verdict(s), "FAIL_TOPIC_POISON_DETECTED")

    def test_low_uptime_after_warmup(self):
        # elapsed > 1h + uptime_ratio < 0.5 → DEGRADED
        s = self._stats(uptime_ratio=0.3, elapsed_sec=7200)
        self.assertEqual(_interim_verdict(s), "DEGRADED_UPTIME_LOW")

    def test_low_uptime_within_warmup_still_healthy(self):
        # elapsed <= 1h → 不觸 DEGRADED
        s = self._stats(uptime_ratio=0.3, elapsed_sec=600)
        # 因為 reconnect_failures = 0 + elapsed < 3600 → healthy
        self.assertEqual(_interim_verdict(s), "IN_PROGRESS_HEALTHY")

    def test_reconnect_unstable(self):
        s = self._stats(reconnect_failures=3)
        self.assertEqual(_interim_verdict(s), "DEGRADED_RECONNECT_UNSTABLE")


# ── assess() verdict mapping ────────────────────────────────────────────


class TestAssess(unittest.TestCase):
    """`assess()` 5 條 verdict 路徑：
        1. FAIL_TOPIC_POISON       (poison_events 非空)
        2. FAIL_RESTART_BUDGET_EXHAUSTED (restart_count > max_restart)
        3. FAIL_RECONNECT_EXHAUSTED (enable_reconnect=True, elapsed < proof)
        4. FAIL_CONNECTION         (enable_reconnect=False, elapsed < proof, conn_err)
        5. PASS_C1_PROOF_CANDIDATE (elapsed≥23h + uptime≥0.95 + ≥3 control alive)
       還有 SMOKE_PASS_NOT_C1_PROOF + FAIL_SMOKE_CANARY_SILENT + FAIL_CANARY_SILENT
    """

    def _args(self, **overrides):
        # 模擬 argparse.Namespace
        defaults = dict(
            proof_min_duration_sec=PASS_MIN_OBSERVED_SEC,
            proof_min_uptime_ratio=PASS_MIN_UPTIME_RATIO,
            max_restart=3,
            enable_reconnect=True,
        )
        defaults.update(overrides)
        ns = MagicMock()
        for k, v in defaults.items():
            setattr(ns, k, v)
        return ns

    def _stats_with_full_window(self):
        # 一個 24h 級 stats baseline，control 全 alive
        s = ProbeV2Stats(
            session_id="x",
            started_at_utc="2026-05-16T00:00:00+00:00",
            target_sec=86400,
            elapsed_sec=85_000,
            uptime_sec=84_900,
            uptime_ratio=0.999,
            control_topics=[
                "tickers.BTCUSDT", "orderbook.50.BTCUSDT",
                "publicTrade.BTCUSDT", "kline.1.BTCUSDT",
            ],
            topic_message_counts={
                "allLiquidation.BTCUSDT": 50,
                "tickers.BTCUSDT": 8640,
                "orderbook.50.BTCUSDT": 86400,
                "publicTrade.BTCUSDT": 17280,
                "kline.1.BTCUSDT": 1440,
            },
        )
        return s

    def test_pass_c1_proof_full_window(self):
        s = self._stats_with_full_window()
        assess(s, self._args())
        self.assertEqual(s.verdict, "PASS_C1_PROOF_CANDIDATE")
        self.assertTrue(s.c1_proof_eligible)
        self.assertIsNone(s.c1_blocker)

    def test_fail_topic_poison_dominates(self):
        s = self._stats_with_full_window()
        s.poison_events.append("handler not found")
        assess(s, self._args())
        self.assertEqual(s.verdict, "FAIL_TOPIC_POISON")
        # poison 優先級高於 elapsed 條件

    def test_fail_restart_budget_exhausted(self):
        s = self._stats_with_full_window()
        s.restart_count = 4
        assess(s, self._args(max_restart=3))
        self.assertEqual(s.verdict, "FAIL_RESTART_BUDGET_EXHAUSTED")
        self.assertIn("restart budget exhausted", (s.c1_blocker or "").lower())

    def test_fail_reconnect_exhausted_when_enable_reconnect(self):
        # elapsed 不夠長 + conn_err 非空 + enable_reconnect=True
        s = ProbeV2Stats(
            session_id="x", started_at_utc="2026-05-16T00:00:00+00:00",
            elapsed_sec=3600, uptime_sec=3000, uptime_ratio=0.83,
            connection_errors=["recv_failed: ConnectionError"],
            control_topics=["tickers.BTCUSDT"],
            topic_message_counts={"tickers.BTCUSDT": 100},
        )
        assess(s, self._args(enable_reconnect=True))
        self.assertEqual(s.verdict, "FAIL_RECONNECT_EXHAUSTED")

    def test_fail_connection_when_no_reconnect_flag(self):
        # 相同條件但 enable_reconnect=False → FAIL_CONNECTION（v1 兼容路徑）
        s = ProbeV2Stats(
            session_id="x", started_at_utc="2026-05-16T00:00:00+00:00",
            elapsed_sec=3600, uptime_sec=3000, uptime_ratio=0.83,
            connection_errors=["recv_failed: ConnectionError"],
            control_topics=["tickers.BTCUSDT"],
            topic_message_counts={"tickers.BTCUSDT": 100},
        )
        assess(s, self._args(enable_reconnect=False))
        self.assertEqual(s.verdict, "FAIL_CONNECTION")

    def test_smoke_pass_short_window(self):
        s = ProbeV2Stats(
            session_id="x", started_at_utc="2026-05-16T00:00:00+00:00",
            elapsed_sec=60, uptime_sec=60, uptime_ratio=1.0,
            control_topics=["tickers.BTCUSDT"],
            topic_message_counts={"tickers.BTCUSDT": 50},
        )
        assess(s, self._args())
        self.assertEqual(s.verdict, "SMOKE_PASS_NOT_C1_PROOF")

    def test_smoke_canary_silent(self):
        s = ProbeV2Stats(
            session_id="x", started_at_utc="2026-05-16T00:00:00+00:00",
            elapsed_sec=60, uptime_sec=60, uptime_ratio=1.0,
            control_topics=["tickers.BTCUSDT"],
            topic_message_counts={"tickers.BTCUSDT": 0},
        )
        assess(s, self._args())
        self.assertEqual(s.verdict, "FAIL_SMOKE_CANARY_SILENT")

    def test_full_window_but_canary_silent(self):
        # 24h 級 elapsed 但只 1 個 control alive (< 3 threshold)
        s = self._stats_with_full_window()
        # Kill 3 control 留 1
        for k in ("tickers.BTCUSDT", "orderbook.50.BTCUSDT", "publicTrade.BTCUSDT"):
            s.topic_message_counts[k] = 0
        # kline.1.BTCUSDT 留 alive
        assess(s, self._args())
        self.assertEqual(s.verdict, "FAIL_CANARY_SILENT")

    def test_full_window_three_control_ok(self):
        # 3 alive control = PASS（v2 放寬，design §3.5）
        s = self._stats_with_full_window()
        s.topic_message_counts["kline.1.BTCUSDT"] = 0
        assess(s, self._args())
        self.assertEqual(s.verdict, "PASS_C1_PROOF_CANDIDATE")


# ── Checkpoint 寫入測試 ────────────────────────────────────────────────


class TestCheckpointWrite(unittest.TestCase):
    """`_write_checkpoint()` 60min boundary 寫入 + JSON schema 對齊 design §3.3。"""

    def test_writes_progress_json_with_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "audit" / "liquidation_topic_probe"
            stats = ProbeV2Stats(
                session_id="c1_v2_TEST",
                started_at_utc="2026-05-16T00:00:00+00:00",
                target_sec=86400,
                elapsed_sec=7200.5,
                uptime_sec=7195.2,
                uptime_ratio=0.999,
                reconnect_attempts=1,
                reconnect_successes=1,
                reconnect_failures=0,
                last_reconnect_reason="recv_failed: ConnectionClosedError",
                candidate_messages_seen=47,
                topic_message_counts={
                    "tickers.BTCUSDT": 2880,
                    "orderbook.50.BTCUSDT": 14400,
                },
                interim_verdict="IN_PROGRESS_HEALTHY",
                blocker_if_aborted_now="Duration shorter than 24h; SMOKE_PASS_NOT_C1_PROOF if abort",
            )
            path = _write_checkpoint(stats, output_dir)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, CHECKPOINT_FILE_NAME)
            # 驗 schema fields 與 design §3.3 對齊
            payload = json.loads(path.read_text(encoding="utf-8"))
            for field_name in (
                "session_id", "started_at_utc", "elapsed_sec", "target_sec",
                "uptime_sec", "uptime_ratio", "reconnect_attempts",
                "reconnect_successes", "reconnect_failures",
                "last_reconnect_reason", "candidate_messages_seen",
                "topic_message_counts", "interim_verdict", "blocker_if_aborted_now",
            ):
                self.assertIn(field_name, payload, f"missing field: {field_name}")
            self.assertEqual(payload["session_id"], "c1_v2_TEST")
            self.assertEqual(payload["target_sec"], 86400)

    def test_overwrites_same_path_no_dated_proliferation(self):
        # checkpoint 永遠寫 c1_proof_progress.json（不應產生 dated 副本）
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            stats = ProbeV2Stats(
                session_id="x",
                started_at_utc="2026-05-16T00:00:00+00:00",
            )
            stats.elapsed_sec = 100
            _write_checkpoint(stats, output_dir)
            stats.elapsed_sec = 200
            _write_checkpoint(stats, output_dir)
            files = list(output_dir.iterdir())
            # 只應該有 1 個 checkpoint file
            self.assertEqual(len([f for f in files if f.is_file()]), 1)
            # 內容是最後一次 write 的
            payload = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["elapsed_sec"], 200)


# ── Reconnect path 整合測試（mock websocket）──────────────────────────────


class FakeWebSocketModule:
    """Mock websocket module 對齊 `websocket-client` API 的 minimal subset。"""

    class WebSocketTimeoutException(Exception):
        pass

    def __init__(self):
        self.connections_created = []
        self.subscribe_sends = []

    def make_create_connection_factory(self, behavior_per_attempt):
        """behavior_per_attempt: list of callables；第 i 次呼叫用第 i 個 behavior。

        behavior 可以是：
          - 'OK' → 回一個 FakeWS instance 永遠收 timeout
          - 'OK_THEN_FAIL' → 第一次成功但 recv() 失敗
          - 'CONNECT_FAIL' → 連接 raise OSError
        """
        idx = {"i": 0}

        def factory(url, timeout=None):
            i = idx["i"]
            idx["i"] += 1
            behavior = behavior_per_attempt[min(i, len(behavior_per_attempt) - 1)]
            if behavior == "CONNECT_FAIL":
                raise OSError("simulated connect failure")
            return FakeWebSocket(behavior, self.WebSocketTimeoutException)
        return factory


class FakeWebSocket:
    """Mock WS connection。"""

    def __init__(self, behavior: str, timeout_exc_cls: type):
        self.behavior = behavior
        self.timeout_exc_cls = timeout_exc_cls
        self.closed = False
        self.sends = []
        self.recv_call_count = 0
        # mock socket for keepalive setsockopt
        self.sock = MagicMock()
        self.sock.setsockopt = MagicMock(return_value=None)

    def send(self, data):
        self.sends.append(data)

    def recv(self):
        self.recv_call_count += 1
        if self.behavior == "OK":
            raise self.timeout_exc_cls("timeout")
        if self.behavior == "OK_THEN_FAIL":
            # 第一次 recv 成功（回一個普通 message），第二次起 raise
            if self.recv_call_count == 1:
                return json.dumps({"success": True, "op": "subscribe"})
            raise ConnectionError("simulated mid-run disconnect")
        if self.behavior == "FAIL_IMMEDIATE":
            raise ConnectionError("simulated immediate disconnect")
        raise self.timeout_exc_cls("timeout default")

    def close(self):
        self.closed = True


class TestReconnectPath(unittest.TestCase):
    """模擬中斷 → exp backoff → 重連 → 成功 / 失敗 路徑。"""

    @patch("time.sleep", return_value=None)
    def test_reconnect_success_first_attempt(self, _mock_sleep):
        """第一次 reconnect attempt 即成功 → reconnect_attempts +1 / successes +1 / failures 0。"""
        from liquidation_topic_probe_v2 import _try_reconnect

        fake_module = FakeWebSocketModule()
        # 第一次 attempt 重連成功
        fake_module.create_connection = fake_module.make_create_connection_factory(["OK"])

        stats = ProbeV2Stats(
            session_id="t",
            started_at_utc="2026-05-16T00:00:00+00:00",
        )
        args = MagicMock()
        args.url = DEFAULT_URL
        args.recv_timeout_sec = 5.0
        args.ping_interval_sec = 10.0

        result = _try_reconnect(
            args, stats, fake_module, ["allLiquidation.BTCUSDT"],
            consecutive_attempt=0,
            reason="recv_failed: ConnectionError",
        )
        self.assertIsNotNone(result)
        ws, conn_on, next_ping, new_attempt_counter = result
        self.assertEqual(stats.reconnect_attempts, 1)
        self.assertEqual(stats.reconnect_successes, 1)
        self.assertEqual(stats.reconnect_failures, 0)
        self.assertEqual(new_attempt_counter, 0)
        self.assertEqual(len(stats.reconnect_events), 1)
        self.assertTrue(stats.reconnect_events[0].success)

    @patch("time.sleep", return_value=None)
    def test_reconnect_exhausted_after_six_attempts(self, _mock_sleep):
        """6 連續 attempt fail → 回 None（觸 restart）。"""
        from liquidation_topic_probe_v2 import _try_reconnect

        fake_module = FakeWebSocketModule()
        # 6 次 attempt 都 fail
        fake_module.create_connection = fake_module.make_create_connection_factory(
            ["CONNECT_FAIL"] * 10
        )

        stats = ProbeV2Stats(
            session_id="t",
            started_at_utc="2026-05-16T00:00:00+00:00",
        )
        args = MagicMock()
        args.url = DEFAULT_URL
        args.recv_timeout_sec = 5.0
        args.ping_interval_sec = 10.0

        result = _try_reconnect(
            args, stats, fake_module, ["allLiquidation.BTCUSDT"],
            consecutive_attempt=0,
            reason="recv_failed: ConnectionError",
        )
        self.assertIsNone(result)
        # 6 attempts × 全部 fail
        self.assertEqual(stats.reconnect_attempts, 6)
        self.assertEqual(stats.reconnect_failures, 6)
        self.assertEqual(stats.reconnect_successes, 0)
        # backoff 序列驗：1, 2, 4, 8, 16, 32（前 6 次走 exponential）
        for i, ev in enumerate(stats.reconnect_events, start=1):
            expected_backoff = float(RECONNECT_BACKOFF_SEC[i - 1])
            self.assertEqual(ev.backoff_sec, expected_backoff, f"attempt {i} backoff mismatch")


class TestRestartCap(unittest.TestCase):
    """連續 N 次 RECONNECT_EXHAUSTED 觸發 RestartEvent 累計；超過 max_restart=3 → FAIL。"""

    def test_restart_events_accumulate(self):
        """直接構造 stats 然後驗 assess() 對 restart_count > max_restart 的判定。"""
        stats = ProbeV2Stats(
            session_id="t",
            started_at_utc="2026-05-16T00:00:00+00:00",
            elapsed_sec=1000,
            uptime_sec=500,
            uptime_ratio=0.5,
            restart_count=4,
            max_restart_budget=3,
            restart_events=[
                RestartEvent(1, "2026-05-16T01:00:00+00:00", "RECONNECT_EXHAUSTED", 3600, 3500),
                RestartEvent(2, "2026-05-16T02:00:00+00:00", "RECONNECT_EXHAUSTED", 7200, 7000),
                RestartEvent(3, "2026-05-16T03:00:00+00:00", "RECONNECT_EXHAUSTED", 10800, 10500),
                RestartEvent(4, "2026-05-16T04:00:00+00:00", "RECONNECT_EXHAUSTED", 14400, 14000),
            ],
        )
        args = MagicMock()
        args.proof_min_duration_sec = PASS_MIN_OBSERVED_SEC
        args.proof_min_uptime_ratio = PASS_MIN_UPTIME_RATIO
        args.max_restart = 3
        args.enable_reconnect = True

        assess(stats, args)
        self.assertEqual(stats.verdict, "FAIL_RESTART_BUDGET_EXHAUSTED")
        self.assertEqual(stats.restart_count, 4)
        self.assertEqual(len(stats.restart_events), 4)

    def test_three_restart_within_budget_can_still_pass(self):
        """restart_count == max_restart 不算超標（> 是 fail）。"""
        stats = ProbeV2Stats(
            session_id="t",
            started_at_utc="2026-05-16T00:00:00+00:00",
            target_sec=86400,
            elapsed_sec=85_000,
            uptime_sec=84_000,
            uptime_ratio=0.988,
            restart_count=3,
            max_restart_budget=3,
            control_topics=[
                "tickers.BTCUSDT", "orderbook.50.BTCUSDT",
                "publicTrade.BTCUSDT", "kline.1.BTCUSDT",
            ],
            topic_message_counts={
                "allLiquidation.BTCUSDT": 30,
                "tickers.BTCUSDT": 8000,
                "orderbook.50.BTCUSDT": 80000,
                "publicTrade.BTCUSDT": 16000,
                "kline.1.BTCUSDT": 1400,
            },
        )
        args = MagicMock()
        args.proof_min_duration_sec = PASS_MIN_OBSERVED_SEC
        args.proof_min_uptime_ratio = PASS_MIN_UPTIME_RATIO
        args.max_restart = 3
        args.enable_reconnect = True

        assess(stats, args)
        # restart_count = max_restart = 3 (not >)，且其餘條件滿足
        self.assertEqual(stats.verdict, "PASS_C1_PROOF_CANDIDATE")


# ── 主入口：python3 -m unittest 直跑 ────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
