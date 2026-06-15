#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：B1 watchdog 破壞性重啟前 IPC 存活交叉檢查（2026-06-15）的單元測試。
  覆蓋 PA/E5 spec 五情境 + probe 層 fail-toward-restart 證明 + max-hold 上限。
主要類/函數：
  - TestProbeEngineIPC：對 AF_UNIX socket 的探測——alive / socket 不存在 / 逾時 /
    認證失敗 / RPC error / id 不符 / 亂碼，全用 mock socket，不開真引擎。
  - TestDecideRestartSuppression：決策表——alive→suppress、not-alive→restart、
    達 N 連續週期上限→restart、達硬性 wall-clock 上限→restart。
  - TestEnvToggles：CROSSCHECK_ENABLED env 開關 + STALE_THRESHOLD_MS 覆寫 fail-safe。
  - TestOnEngineCrashWiring：on_engine_crash 端到端——stale+alive 抑制（不重啟、不計
    crash、發 SNAPSHOT_STALL_ENGINE_ALIVE）/ stale+dead 重啟 / probe 拋例外→重啟 /
    max-hold 達上限→升級重啟 / env 關閉→原行為（always restart on stale）。
依賴：engine_watchdog.py、watchdog_liveness_crosscheck.py、canary_audit_common.py、
  unittest.mock、tempfile。
硬邊界：全在 tmpdir；mock 掉 IPC（socket）+ DB（audit write）+ trigger_restart，
  絕不開真引擎 / 真 SIGTERM / 真 PG。
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import engine_watchdog  # noqa: E402
import watchdog_liveness_crosscheck as lcc  # noqa: E402
from engine_watchdog import WatchdogState, on_engine_crash  # noqa: E402
from watchdog_liveness_crosscheck import (  # noqa: E402
    ProbeResult,
    decide_restart_suppression,
    liveness_crosscheck_enabled,
    probe_engine_ipc,
    resolve_stale_threshold_ms,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock socket helpers / 假 socket 輔助
# ─────────────────────────────────────────────────────────────────────────────


class _FakeSocket:
    """模擬 AF_UNIX socket：可注入逐行回應 + connect 行為 + recv 行為。

    為什麼自寫而非 mock.MagicMock：probe_engine_ipc 用 sock.recv(1) 逐 byte 讀到 \\n，
    需要真實 byte 串流語義；MagicMock 難精準模擬。
    """

    def __init__(self, *, lines=None, connect_exc=None, recv_exc=None, timeout_on_recv=False):
        # lines：依序回給每次 _recv_line 的整行字串（不含換行）。
        self._lines = list(lines or [])
        self._connect_exc = connect_exc
        self._recv_exc = recv_exc
        self._timeout_on_recv = timeout_on_recv
        self._cur = b""  # 當前行剩餘 bytes（含尾端 \n）
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, _t):
        pass

    def connect(self, _path):
        if self._connect_exc is not None:
            raise self._connect_exc

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, _n):
        import socket as _s
        if self._timeout_on_recv:
            raise _s.timeout("simulated recv timeout")
        if self._recv_exc is not None:
            raise self._recv_exc
        if not self._cur:
            if not self._lines:
                return b""  # 連線被關閉（空回應）
            self._cur = (self._lines.pop(0) + "\n").encode("utf-8")
        ch = self._cur[:1]
        self._cur = self._cur[1:]
        return ch


def _patch_socket(fake):
    """讓 watchdog_liveness_crosscheck 內的 _socket.socket(...) 回我們的 fake。"""
    return mock.patch.object(lcc._socket, "socket", return_value=fake)


# ─────────────────────────────────────────────────────────────────────────────
# Probe layer / 探測層
# ─────────────────────────────────────────────────────────────────────────────


class TestProbeEngineIPC(unittest.TestCase):
    def setUp(self):
        # 無 secret = dev 模式跳過認證握手（探測只送 get_risk_runtime_status）。
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("OPENCLAW_IPC_SECRET", None)

    def tearDown(self):
        self._env.stop()

    def test_alive_when_engine_responds_with_dict_result(self):
        """引擎在 timeout 內明確回正確 result dict → alive=True。"""
        fake = _FakeSocket(lines=['{"jsonrpc":"2.0","result":{"governor_tier":"NORMAL"},"id":1}'])
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertTrue(res.alive)
        self.assertEqual(res.reason, "ipc_responsive")
        # 探測必須是唯讀 method（白名單）。
        self.assertIn(b"get_risk_runtime_status", fake.sent[-1])

    def test_socket_missing_is_not_alive(self):
        """socket 不存在（引擎進程未跑）→ alive=False（真死，重啟）。"""
        fake = _FakeSocket(connect_exc=FileNotFoundError("no socket"))
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertFalse(res.alive)
        self.assertEqual(res.reason, "ipc_socket_missing")

    def test_timeout_is_not_alive(self):
        """recv 逾時（引擎掛死不回）→ alive=False（fail-safe，重啟）。"""
        fake = _FakeSocket(timeout_on_recv=True)
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertFalse(res.alive)
        self.assertEqual(res.reason, "ipc_timeout")

    def test_rpc_error_is_not_alive(self):
        """引擎回 JSON-RPC error → alive=False（非明確健康 reply，保守）。"""
        fake = _FakeSocket(lines=['{"jsonrpc":"2.0","error":{"code":-32601,"message":"x"},"id":1}'])
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertFalse(res.alive)
        self.assertEqual(res.reason, "ipc_rpc_error")

    def test_garbled_reply_is_not_alive(self):
        """亂碼（非合法 JSON）→ alive=False。"""
        fake = _FakeSocket(lines=["this is not json"])
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertFalse(res.alive)
        self.assertEqual(res.reason, "ipc_garbled_reply")

    def test_id_mismatch_is_not_alive(self):
        """回應 id 不符 → alive=False（保守）。"""
        fake = _FakeSocket(lines=['{"jsonrpc":"2.0","result":{"a":1},"id":99}'])
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertFalse(res.alive)
        self.assertEqual(res.reason, "ipc_id_mismatch")

    def test_non_dict_result_is_not_alive(self):
        """result 非 dict（非預期形狀）→ alive=False。"""
        fake = _FakeSocket(lines=['{"jsonrpc":"2.0","result":"pong","id":1}'])
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertFalse(res.alive)
        self.assertEqual(res.reason, "ipc_unexpected_result")

    def test_auth_failure_is_not_alive(self):
        """設了 secret 但認證被拒 → alive=False（fail-safe）。"""
        os.environ["OPENCLAW_IPC_SECRET"] = "deadbeef"
        # 第一行是 __auth 回應（error）；探測在 auth 失敗即 return，不會送 probe。
        fake = _FakeSocket(lines=['{"jsonrpc":"2.0","error":{"message":"auth failed"},"id":0}'])
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertFalse(res.alive)
        self.assertEqual(res.reason, "ipc_auth_failed")

    def test_auth_then_alive_when_secret_set(self):
        """設了 secret，認證成功後 probe 回正確 result → alive=True。"""
        os.environ["OPENCLAW_IPC_SECRET"] = "deadbeef"
        fake = _FakeSocket(lines=[
            '{"jsonrpc":"2.0","result":{"authenticated":true},"id":0}',
            '{"jsonrpc":"2.0","result":{"governor_tier":"NORMAL"},"id":1}',
        ])
        with _patch_socket(fake):
            res = probe_engine_ipc(socket_path="/tmp/fake.sock")
        self.assertTrue(res.alive)
        # 必須先送 __auth 再送 probe。
        self.assertIn(b"__auth", fake.sent[0])
        self.assertIn(b"get_risk_runtime_status", fake.sent[1])


# ─────────────────────────────────────────────────────────────────────────────
# Decision layer / 決策層
# ─────────────────────────────────────────────────────────────────────────────


class TestDecideRestartSuppression(unittest.TestCase):
    def test_alive_first_cycle_suppresses(self):
        """alive + 尚未抑制 → suppress=True，hold_cycles=1。"""
        d = decide_restart_suppression(
            ProbeResult(alive=True, reason="ipc_responsive"),
            prior_hold_cycles=0, first_suppress_ts=None, now=1000.0,
        )
        self.assertTrue(d.suppress)
        self.assertEqual(d.reason, "engine_alive_snapshot_stalled")
        self.assertEqual(d.hold_cycles, 1)

    def test_not_alive_does_not_suppress(self):
        """not-alive → suppress=False（重啟），reason 透傳 probe.reason。"""
        d = decide_restart_suppression(
            ProbeResult(alive=False, reason="ipc_timeout"),
            prior_hold_cycles=0, first_suppress_ts=None, now=1000.0,
        )
        self.assertFalse(d.suppress)
        self.assertEqual(d.reason, "ipc_timeout")

    def test_max_hold_cycles_escalates_to_restart(self):
        """alive 但連續抑制達 N 週期上限 → suppress=False（升級重啟）。"""
        d = decide_restart_suppression(
            ProbeResult(alive=True, reason="ipc_responsive"),
            prior_hold_cycles=lcc.MAX_HOLD_CONSECUTIVE_CYCLES,  # +1 即超過
            first_suppress_ts=1000.0, now=1000.5,
        )
        self.assertFalse(d.suppress)
        self.assertEqual(d.reason, "max_hold_cycles_exceeded")

    def test_max_hold_seconds_escalates_to_restart(self):
        """alive 但 wall-clock 抑制達硬性上限 → suppress=False（升級重啟）。"""
        d = decide_restart_suppression(
            ProbeResult(alive=True, reason="ipc_responsive"),
            prior_hold_cycles=1,
            first_suppress_ts=1000.0,
            now=1000.0 + lcc.MAX_HOLD_SECONDS + 1.0,
        )
        self.assertFalse(d.suppress)
        self.assertEqual(d.reason, "max_hold_seconds_exceeded")

    def test_alive_within_limits_keeps_suppressing(self):
        """alive 且兩道上限皆未達 → 持續 suppress。"""
        d = decide_restart_suppression(
            ProbeResult(alive=True, reason="ipc_responsive"),
            prior_hold_cycles=5, first_suppress_ts=1000.0, now=1010.0,
        )
        self.assertTrue(d.suppress)
        self.assertEqual(d.hold_cycles, 6)


# ─────────────────────────────────────────────────────────────────────────────
# Env toggles (B3-lite) / env 旗標
# ─────────────────────────────────────────────────────────────────────────────


class TestEnvToggles(unittest.TestCase):
    def test_enabled_default_on(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(lcc.CROSSCHECK_ENABLED_ENV_VAR, None)
            self.assertTrue(liveness_crosscheck_enabled())

    def test_disabled_by_zero(self):
        for val in ("0", "false", "no", "off", ""):
            with mock.patch.dict(os.environ, {lcc.CROSSCHECK_ENABLED_ENV_VAR: val}):
                self.assertFalse(liveness_crosscheck_enabled(), f"val={val!r}")

    def test_enabled_by_one(self):
        with mock.patch.dict(os.environ, {lcc.CROSSCHECK_ENABLED_ENV_VAR: "1"}):
            self.assertTrue(liveness_crosscheck_enabled())

    def test_stale_threshold_default_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(lcc.STALE_THRESHOLD_MS_ENV_VAR, None)
            self.assertEqual(resolve_stale_threshold_ms(45000.0), 45000.0)

    def test_stale_threshold_override(self):
        with mock.patch.dict(os.environ, {lcc.STALE_THRESHOLD_MS_ENV_VAR: "60000"}):
            self.assertEqual(resolve_stale_threshold_ms(45000.0), 60000.0)

    def test_stale_threshold_invalid_falls_back(self):
        """非數字 / 非正數 → fail-safe 退回 default（不放寬不報錯）。"""
        for bad in ("notanumber", "-5", "0"):
            with mock.patch.dict(os.environ, {lcc.STALE_THRESHOLD_MS_ENV_VAR: bad}):
                self.assertEqual(resolve_stale_threshold_ms(45000.0), 45000.0, f"bad={bad!r}")


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end wiring in on_engine_crash / 端到端接線
# ─────────────────────────────────────────────────────────────────────────────


class TestOnEngineCrashWiring(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name
        # 預設啟用交叉檢查 + 無 secret（dev）。各 test 自行 patch probe。
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(lcc.CROSSCHECK_ENABLED_ENV_VAR, None)
        os.environ.pop("OPENCLAW_IPC_SECRET", None)
        # 一律 mock 掉 DB audit 寫入（Mac 無 PG），避免真連線。
        self._audit = mock.patch.object(
            engine_watchdog.canary_audit_common, "write_audit_event_best_effort",
            return_value=False,
        )
        self._audit.start()
        # 一律 mock 掉真告警外發（fire-and-forget thread / 憑證讀取）。
        self._alert = mock.patch.object(
            engine_watchdog, "_send_alert_best_effort", return_value=None,
        )
        self._alert.start()

    def tearDown(self):
        self._alert.stop()
        self._audit.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _canary_events(self):
        path = Path(self.data_dir) / engine_watchdog.CANARY_EVENTS_FILE
        if not path.exists():
            return []
        import json
        return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]

    def test_stale_but_ipc_alive_suppresses_restart(self):
        """情境1：stale + IPC alive → 不重啟、SNAPSHOT_STALL_ENGINE_ALIVE、不計 crash。"""
        state = WatchdogState()
        with mock.patch.object(
            engine_watchdog.watchdog_liveness_crosscheck, "probe_engine_ipc",
            return_value=ProbeResult(alive=True, reason="ipc_responsive"),
        ), mock.patch.object(engine_watchdog, "trigger_restart") as trig:
            action = on_engine_crash(state, 50.0, data_dir=self.data_dir, log_path=None)
        self.assertEqual(action, "fallback")
        trig.assert_not_called()  # 關鍵：未觸發重啟 = 未 SIGTERM = 未平倉
        self.assertEqual(state.total_crashes, 0)  # 不污染 crash 計數
        self.assertTrue(state.engine_alive)       # 引擎活著，不翻 False
        self.assertEqual(state.liveness_suppress_cycles, 1)
        events = [e for e in self._canary_events() if e.get("event") == "SNAPSHOT_STALL_ENGINE_ALIVE"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["probe_reason"], "ipc_responsive")
        # audit row 走 SNAPSHOT_STALL_ENGINE_ALIVE 映射（warning）。
        self.assertEqual(
            engine_watchdog.canary_audit_common.map_canary_to_audit("SNAPSHOT_STALL_ENGINE_ALIVE"),
            ("snapshot_stall_engine_alive", "warning"),
        )

    def test_stale_and_ipc_dead_triggers_restart(self):
        """情境2：stale + IPC dead → 走既有重啟路徑（行為不變）。"""
        state = WatchdogState()
        with mock.patch.object(
            engine_watchdog.watchdog_liveness_crosscheck, "probe_engine_ipc",
            return_value=ProbeResult(alive=False, reason="ipc_socket_missing"),
        ), mock.patch.object(engine_watchdog, "trigger_restart", return_value=True) as trig:
            action = on_engine_crash(state, 50.0, data_dir=self.data_dir, log_path=None)
        self.assertEqual(action, "fallback")
        trig.assert_called_once()  # 真死 → 重啟照舊
        self.assertEqual(state.total_crashes, 1)  # crash 計數正常
        self.assertFalse(state.engine_alive)
        # 無 SNAPSHOT_STALL_ENGINE_ALIVE；有 ENGINE_CRASH canary。
        self.assertEqual(
            [e for e in self._canary_events() if e.get("event") == "SNAPSHOT_STALL_ENGINE_ALIVE"],
            [],
        )
        self.assertTrue(any(e.get("event") == "ENGINE_CRASH" for e in self._canary_events()))

    def test_probe_raises_fails_toward_restart(self):
        """情境3：probe 拋例外 → fail-safe 倒向重啟。"""
        state = WatchdogState()
        with mock.patch.object(
            engine_watchdog.watchdog_liveness_crosscheck, "probe_engine_ipc",
            side_effect=RuntimeError("boom"),
        ), mock.patch.object(engine_watchdog, "trigger_restart", return_value=True) as trig:
            action = on_engine_crash(state, 50.0, data_dir=self.data_dir, log_path=None)
        self.assertEqual(action, "fallback")
        trig.assert_called_once()  # 例外 → 重啟（survival > avoiding market-close）
        self.assertEqual(state.total_crashes, 1)

    def test_max_hold_cap_escalates_to_restart(self):
        """情境4：max-hold 達上限（IPC 仍 alive）→ 升級重啟。"""
        state = WatchdogState()
        # 預置已抑制到上限：下一次 alive poll 應升級重啟。
        state.liveness_suppress_cycles = lcc.MAX_HOLD_CONSECUTIVE_CYCLES
        state.liveness_first_suppress_ts = engine_watchdog.time.time() - 5.0
        with mock.patch.object(
            engine_watchdog.watchdog_liveness_crosscheck, "probe_engine_ipc",
            return_value=ProbeResult(alive=True, reason="ipc_responsive"),
        ), mock.patch.object(engine_watchdog, "trigger_restart", return_value=True) as trig:
            action = on_engine_crash(state, 50.0, data_dir=self.data_dir, log_path=None)
        self.assertEqual(action, "fallback")
        trig.assert_called_once()  # 達上限 → 不再抑制，重啟
        self.assertEqual(state.total_crashes, 1)
        # 升級重啟後 streak 歸零。
        self.assertEqual(state.liveness_suppress_cycles, 0)
        self.assertIsNone(state.liveness_first_suppress_ts)

    def test_crosscheck_disabled_always_restarts_on_stale(self):
        """情境5：env 關閉交叉檢查 → 原行為（stale 即重啟，不探測 IPC）。"""
        state = WatchdogState()
        os.environ[lcc.CROSSCHECK_ENABLED_ENV_VAR] = "0"
        with mock.patch.object(
            engine_watchdog.watchdog_liveness_crosscheck, "probe_engine_ipc",
        ) as probe, mock.patch.object(engine_watchdog, "trigger_restart", return_value=True) as trig:
            action = on_engine_crash(state, 50.0, data_dir=self.data_dir, log_path=None)
        self.assertEqual(action, "fallback")
        probe.assert_not_called()  # 關閉時根本不探測
        trig.assert_called_once()  # stale 即重啟（舊行為）
        self.assertEqual(state.total_crashes, 1)

    def test_suppress_then_recovery_resets_streak(self):
        """抑制後 snapshot 恢復新鮮 → on_engine_recovery reset 連續抑制計數。"""
        state = WatchdogState()
        with mock.patch.object(
            engine_watchdog.watchdog_liveness_crosscheck, "probe_engine_ipc",
            return_value=ProbeResult(alive=True, reason="ipc_responsive"),
        ), mock.patch.object(engine_watchdog, "trigger_restart"):
            on_engine_crash(state, 50.0, data_dir=self.data_dir, log_path=None)
        self.assertEqual(state.liveness_suppress_cycles, 1)
        self.assertIsNotNone(state.liveness_first_suppress_ts)
        # snapshot 恢復新鮮 → recovery 路徑歸零 streak（即便 engine_alive 一直是 True）。
        engine_watchdog.on_engine_recovery(state, data_dir=self.data_dir)
        self.assertEqual(state.liveness_suppress_cycles, 0)
        self.assertIsNone(state.liveness_first_suppress_ts)

    def test_repeated_suppress_polls_emit_event_only_once(self):
        """連續多次 stale-but-alive poll：只在首次抑制發一次 SNAPSHOT_STALL_ENGINE_ALIVE。"""
        state = WatchdogState()
        with mock.patch.object(
            engine_watchdog.watchdog_liveness_crosscheck, "probe_engine_ipc",
            return_value=ProbeResult(alive=True, reason="ipc_responsive"),
        ), mock.patch.object(engine_watchdog, "trigger_restart"):
            for _ in range(4):
                on_engine_crash(state, 50.0, data_dir=self.data_dir, log_path=None)
        events = [e for e in self._canary_events() if e.get("event") == "SNAPSHOT_STALL_ENGINE_ALIVE"]
        self.assertEqual(len(events), 1)  # 不每 poll 灌爆
        self.assertEqual(state.liveness_suppress_cycles, 4)


if __name__ == "__main__":
    unittest.main()
