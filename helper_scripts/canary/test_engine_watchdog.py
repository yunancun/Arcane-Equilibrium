#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：P0-ENGINE-HALTSESSION-STUCK-FIX Layer B（spec v0.2 §4）
TRADING_INERT_PROLONGED watchdog 業務心跳探測單元測試。
主要類/函數：TestInertProbe* 測試覆蓋 detect_paper_paused_stuck、
detect_intents_zero_delta、evaluate_inert_probe、TOML config load、
state persistence、multi-engine 獨立性。
依賴：engine_watchdog.py (Layer B 新增 fn)、unittest.mock（無）、tempfile。
硬邊界：所有測試都在 tmpdir 下；不寫 prod /tmp/openclaw；不影響 watchdog 主循環。

驗收條件對應（spec §10.2）：
- B-1 / B-1a：paper_paused 持續 > threshold → alarm
- B-2：intents 0-delta > window → alarm（含 per-env threshold）
- B-3：cooldown，incident 內不重發
- B-4：clear 後寫 TRADING_INERT_CLEARED
- B-5：watchdog restart 不重置 incident state
- B-7：multi-engine 獨立 state
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_watchdog import (
    INERT_PROBE_DEFAULTS,
    INERT_STATE_FILE,
    InertState,
    detect_intents_zero_delta,
    detect_paper_paused_stuck,
    evaluate_inert_probe,
    load_inert_probe_config,
    load_inert_state,
    resolve_engine_label_for_snapshot,
    run_inert_probe_once,
    save_inert_state,
)


# 為什麼用 fixture 構 snapshot：與 Rust pipeline_types.rs PipelineSnapshot
# 序列化結構對齊（pipeline_kind rename=trading_mode）。
def make_snapshot(
    paper_paused: bool = False,
    trading_mode: str = "demo",
    halt_kind: Optional[str] = None,
    halt_set_ts_ms: int = 0,
    halt_ttl_remaining_ms: Optional[int] = None,
    recent_intents: Optional[list] = None,
    use_mode_snapshots: bool = False,
    mode_key: str = "demo",
) -> dict:
    """構造一份 PipelineSnapshot-like dict 用於 inert probe 測試。"""
    snap = {
        "schema_version": "2.0.0",
        "trading_mode": trading_mode,
        "paper_paused": paper_paused,
        "halt_set_ts_ms": halt_set_ts_ms,
        "recent_intents": recent_intents if recent_intents is not None else [],
    }
    if halt_kind is not None:
        snap["halt_kind"] = halt_kind
    if halt_ttl_remaining_ms is not None:
        snap["halt_ttl_remaining_ms"] = halt_ttl_remaining_ms
    if use_mode_snapshots:
        snap["mode_snapshots"] = {
            mode_key: {
                "paper_paused": paper_paused,
                "halt_kind": halt_kind,
                "halt_set_ts_ms": halt_set_ts_ms,
            }
        }
    return snap


class TestResolveEngineLabel(unittest.TestCase):
    """File-basename + snapshot fallback engine 標識解析。"""

    def test_per_engine_paths(self):
        """pipeline_snapshot_<engine>.json 直接對應 engine label。"""
        for engine in ("paper", "demo", "live"):
            label = resolve_engine_label_for_snapshot(
                Path(f"/tmp/openclaw/pipeline_snapshot_{engine}.json"),
                None,
            )
            self.assertEqual(label, engine)

    def test_compat_snapshot_reads_trading_mode(self):
        """compat pipeline_snapshot.json 讀 snapshot 內 trading_mode 字段。"""
        snap = make_snapshot(trading_mode="live")
        label = resolve_engine_label_for_snapshot(
            Path("/tmp/openclaw/pipeline_snapshot.json"), snap,
        )
        self.assertEqual(label, "live")

    def test_unknown_path_fallback_default(self):
        """未知檔名 + 無 snapshot data → default 標籤（保守 demo）。"""
        label = resolve_engine_label_for_snapshot(
            Path("/tmp/openclaw/random.json"), None,
        )
        self.assertEqual(label, "default")

    def test_compat_invalid_trading_mode_fallback(self):
        """compat snapshot 內 trading_mode 非 paper/demo/live → fallback default。"""
        snap = {"trading_mode": "weird_mode"}
        label = resolve_engine_label_for_snapshot(
            Path("/tmp/openclaw/pipeline_snapshot.json"), snap,
        )
        self.assertEqual(label, "default")


class TestLoadInertProbeConfig(unittest.TestCase):
    """TOML config 載入 + fallback 行為。"""

    def test_load_default_when_file_missing(self):
        """缺檔 → 預設值字典。"""
        cfg = load_inert_probe_config(Path("/no/such/file/inert.toml"))
        self.assertEqual(cfg["demo"]["paper_paused_threshold_seconds"], 3600.0)
        self.assertEqual(cfg["live"]["paper_paused_threshold_seconds"], 900.0)
        self.assertEqual(cfg["live"]["intents_zero_delta_window_seconds"], 600.0)

    def test_load_with_override(self):
        """TOML override 覆寫預設值。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8",
        ) as f:
            f.write(
                "[demo]\n"
                "paper_paused_threshold_seconds = 999\n"
                "intents_zero_delta_window_seconds = 333\n"
            )
            tmp_path = Path(f.name)
        try:
            cfg = load_inert_probe_config(tmp_path)
            self.assertEqual(cfg["demo"]["paper_paused_threshold_seconds"], 999.0)
            self.assertEqual(cfg["demo"]["intents_zero_delta_window_seconds"], 333.0)
            # 其他 env 仍走預設
            self.assertEqual(cfg["live"]["paper_paused_threshold_seconds"], 900.0)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_invalid_value_fallback_default(self):
        """非數值 → 該 key fallback default + warning（不 RAISE）。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8",
        ) as f:
            f.write(
                "[demo]\n"
                'paper_paused_threshold_seconds = "not_a_number"\n'
            )
            tmp_path = Path(f.name)
        try:
            # tomllib 會將 string 解析為 string，下游 float() 轉換失敗 → fallback
            cfg = load_inert_probe_config(tmp_path)
            self.assertEqual(cfg["demo"]["paper_paused_threshold_seconds"], 3600.0)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_parse_error_raises(self):
        """壞 TOML（syntax error）→ RAISE per spec §4.3 fail-loud。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8",
        ) as f:
            f.write("not valid toml = = = ")
            tmp_path = Path(f.name)
        try:
            with self.assertRaises(Exception):
                load_inert_probe_config(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_repo_canonical_toml_loads(self):
        """確認 repo 內 watchdog_inert_probe.toml 可正確解析。"""
        repo_toml = Path(__file__).resolve().parent / "watchdog_inert_probe.toml"
        if not repo_toml.exists():
            self.skipTest("canonical watchdog_inert_probe.toml not present")
        cfg = load_inert_probe_config(repo_toml)
        self.assertEqual(cfg["live"]["paper_paused_threshold_seconds"], 900.0)
        self.assertEqual(cfg["live"]["intents_zero_delta_window_seconds"], 600.0)
        self.assertEqual(cfg["demo"]["paper_paused_threshold_seconds"], 3600.0)
        self.assertEqual(cfg["live_demo"]["paper_paused_threshold_seconds"], 1800.0)


class TestDetectPaperPausedStuck(unittest.TestCase):
    """spec §4.3 condition 1 — paper_paused 持續超 threshold。"""

    def test_not_paused_returns_false(self):
        """paper_paused=false → state 重置，回傳 False。"""
        state = InertState(paper_paused_since=time.time())
        snap = make_snapshot(paper_paused=False)
        self.assertFalse(detect_paper_paused_stuck(snap, state, 60.0, time.time()))
        self.assertIsNone(state.paper_paused_since)

    def test_just_paused_within_threshold(self):
        """剛 paused < threshold → False，state 設起點。"""
        state = InertState()
        now = time.time()
        snap = make_snapshot(paper_paused=True)
        self.assertFalse(detect_paper_paused_stuck(snap, state, 3600.0, now))
        self.assertEqual(state.paper_paused_since, now)

    def test_paused_exceeds_threshold(self):
        """paper_paused 超過 threshold → True。"""
        now = time.time()
        # paused_since 3700s 前
        state = InertState(paper_paused_since=now - 3700.0)
        snap = make_snapshot(paper_paused=True)
        self.assertTrue(detect_paper_paused_stuck(snap, state, 3600.0, now))

    def test_uses_halt_set_ts_ms_as_anchor(self):
        """halt_set_ts_ms 存在 → 用 engine 端 wall-clock 起點，spec B-5。"""
        state = InertState()
        now = time.time()
        # halt 起點 3700s 前
        halt_ts_ms = int((now - 3700.0) * 1000)
        snap = make_snapshot(paper_paused=True, halt_set_ts_ms=halt_ts_ms)
        self.assertTrue(detect_paper_paused_stuck(snap, state, 3600.0, now))
        # state 起點應用 halt_ts，非 now
        self.assertAlmostEqual(state.paper_paused_since, halt_ts_ms / 1000.0, places=3)

    def test_mode_snapshots_takes_priority(self):
        """mode_snapshots 內 paper_paused 優先於頂層（per-engine snapshot）。"""
        state = InertState()
        now = time.time()
        snap = make_snapshot(
            paper_paused=False,
            use_mode_snapshots=True,
            mode_key="demo",
        )
        # mode_snapshots.demo.paper_paused = False（與頂層一致），驗 read path
        snap["mode_snapshots"]["demo"]["paper_paused"] = True
        self.assertFalse(detect_paper_paused_stuck(snap, state, 3600.0, now))
        # 上面只是探一次 — paused_since 應該被 set
        self.assertEqual(state.paper_paused_since, now)


class TestDetectIntentsZeroDelta(unittest.TestCase):
    """spec §4.3 condition 2 — recent_intents 滾動窗口無增長。"""

    def test_empty_intents_returns_false(self):
        """boot 期無 intent → False（避免冷啟動 false-positive）。"""
        state = InertState()
        snap = make_snapshot(recent_intents=[])
        self.assertFalse(detect_intents_zero_delta(snap, state, 1200.0, time.time()))

    def test_recent_intent_within_window(self):
        """最近 intent < window → False。"""
        state = InertState()
        now = time.time()
        recent_ts_ms = int((now - 10.0) * 1000)  # 10s 前
        snap = make_snapshot(recent_intents=[{"timestamp_ms": recent_ts_ms}])
        self.assertFalse(detect_intents_zero_delta(snap, state, 1200.0, now))

    def test_intent_stale_exceeds_window(self):
        """最近 intent > window → True。"""
        state = InertState()
        now = time.time()
        stale_ts_ms = int((now - 1300.0) * 1000)  # 1300s 前
        snap = make_snapshot(recent_intents=[{"timestamp_ms": stale_ts_ms}])
        self.assertTrue(detect_intents_zero_delta(snap, state, 1200.0, now))

    def test_uses_max_timestamp(self):
        """ring buffer 多筆 intent → 用 max(timestamp_ms)。"""
        state = InertState()
        now = time.time()
        snap = make_snapshot(recent_intents=[
            {"timestamp_ms": int((now - 2000.0) * 1000)},  # old
            {"timestamp_ms": int((now - 500.0) * 1000)},   # newer
            {"timestamp_ms": int((now - 1000.0) * 1000)},  # middle
        ])
        # max = now-500 < 1200s window → 不算 stale
        self.assertFalse(detect_intents_zero_delta(snap, state, 1200.0, now))

    def test_invalid_timestamp_ms_skipped(self):
        """壞 timestamp_ms (None / str) → skipped。"""
        state = InertState()
        now = time.time()
        valid_ts = int((now - 100.0) * 1000)
        snap = make_snapshot(recent_intents=[
            {"timestamp_ms": "bad"},
            {"timestamp_ms": None},
            {"timestamp_ms": valid_ts},
        ])
        self.assertFalse(detect_intents_zero_delta(snap, state, 1200.0, now))


class TestEvaluateInertProbe(unittest.TestCase):
    """主 probe 評估：condition combine + cooldown + cleared transition。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name
        self.config = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}

    def tearDown(self):
        self.tmp.cleanup()

    def _events_jsonl_lines(self) -> list[dict]:
        path = Path(self.data_dir) / "canary_events.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def test_fires_alarm_paper_paused_stuck(self):
        """B-1：paper_paused > threshold → alarm + jsonl write。"""
        state = InertState()
        now = time.time()
        # 預先把 paused_since 設成 3700s 前（>3600 demo threshold）
        state.paper_paused_since = now - 3700.0
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        snap = make_snapshot(paper_paused=True, halt_kind="daily_loss")
        result = evaluate_inert_probe(
            snap_path, snap, state, self.config, now, self.data_dir,
        )
        self.assertEqual(result, "paper_paused_stuck")
        self.assertTrue(state.incident_active)
        events = self._events_jsonl_lines()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "TRADING_INERT_PROLONGED")
        self.assertEqual(events[0]["trigger"], "paper_paused_stuck")
        self.assertEqual(events[0]["engine"], "demo")
        self.assertEqual(events[0]["halt_kind"], "daily_loss")

    def test_fires_alarm_intents_zero_delta(self):
        """B-2：intents zero delta > window → alarm。"""
        state = InertState()
        now = time.time()
        # paper_paused=false 但 intents 都很舊
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        stale_ts_ms = int((now - 1300.0) * 1000)
        snap = make_snapshot(
            paper_paused=False,
            recent_intents=[{"timestamp_ms": stale_ts_ms}],
        )
        result = evaluate_inert_probe(
            snap_path, snap, state, self.config, now, self.data_dir,
        )
        self.assertEqual(result, "intents_zero_delta")
        self.assertTrue(state.incident_active)

    def test_cooldown_no_duplicate_alarms(self):
        """B-3：同 incident 內第二次評估不重發 alarm。"""
        state = InertState()
        now = time.time()
        state.paper_paused_since = now - 3700.0
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        snap = make_snapshot(paper_paused=True, halt_kind="daily_loss")
        # 第一次：alarm
        evaluate_inert_probe(snap_path, snap, state, self.config, now, self.data_dir)
        # 第二次同一個 incident_active
        result = evaluate_inert_probe(
            snap_path, snap, state, self.config, now + 1.0, self.data_dir,
        )
        self.assertIsNone(result)  # cooldown 不重發
        events = self._events_jsonl_lines()
        # 仍只有 1 條 alarm
        alarms = [e for e in events if e["event"] == "TRADING_INERT_PROLONGED"]
        self.assertEqual(len(alarms), 1)

    def test_paper_paused_clears_state(self):
        """B-4：clear transition → 寫 TRADING_INERT_CLEARED + reset cooldown。"""
        state = InertState()
        now = time.time()
        state.paper_paused_since = now - 3700.0
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        # 先 fire alarm
        snap_paused = make_snapshot(paper_paused=True, halt_kind="daily_loss")
        evaluate_inert_probe(snap_path, snap_paused, state, self.config, now, self.data_dir)
        self.assertTrue(state.incident_active)
        # 再次評估：paused=false + intents 新鮮 → cleared
        snap_clear = make_snapshot(
            paper_paused=False,
            recent_intents=[{"timestamp_ms": int(now * 1000)}],
        )
        result = evaluate_inert_probe(
            snap_path, snap_clear, state, self.config, now + 60.0, self.data_dir,
        )
        self.assertEqual(result, "cleared")
        self.assertFalse(state.incident_active)
        self.assertIsNone(state.last_alarm_ts)
        events = self._events_jsonl_lines()
        cleared = [e for e in events if e["event"] == "TRADING_INERT_CLEARED"]
        self.assertEqual(len(cleared), 1)
        self.assertEqual(cleared[0]["engine"], "demo")
        self.assertEqual(cleared[0]["previous_trigger"], "paper_paused_stuck")

    def test_per_env_threshold_live_stricter(self):
        """B-1a：live env paper_paused 15min+ alarm（vs demo 60min）。"""
        state = InertState()
        now = time.time()
        # 16min 前
        state.paper_paused_since = now - 960.0
        snap_path = Path(self.data_dir) / "pipeline_snapshot_live.json"
        snap = make_snapshot(paper_paused=True, trading_mode="live")
        result = evaluate_inert_probe(
            snap_path, snap, state, self.config, now, self.data_dir,
        )
        # live threshold = 900s → 960 > 900 → fire
        self.assertEqual(result, "paper_paused_stuck")
        events = self._events_jsonl_lines()
        self.assertEqual(events[0]["engine"], "live")
        self.assertEqual(events[0]["threshold_seconds"], 900.0)

    def test_per_env_threshold_demo_not_fire_at_live_threshold(self):
        """B-1a 對照：同 16min 場景，demo engine 不 alarm（threshold 60min）。"""
        state = InertState()
        now = time.time()
        state.paper_paused_since = now - 960.0  # 16min
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        snap = make_snapshot(paper_paused=True, trading_mode="demo")
        result = evaluate_inert_probe(
            snap_path, snap, state, self.config, now, self.data_dir,
        )
        self.assertIsNone(result)  # demo 60min 還沒到
        self.assertFalse(state.incident_active)


class TestInertStatePersistence(unittest.TestCase):
    """B-5：watchdog restart 不重置 incident state。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_load_roundtrip(self):
        """save → load 對齊所有字段。"""
        now = time.time()
        states = {
            "demo": InertState(
                paper_paused_since=now - 100.0,
                last_intent_ts_ms=int((now - 50) * 1000),
                last_alarm_ts=now - 30.0,
                last_alarm_trigger="paper_paused_stuck",
                incident_active=True,
            ),
            "live": InertState(),
        }
        save_inert_state(self.data_dir, states)
        loaded = load_inert_state(self.data_dir)
        self.assertIn("demo", loaded)
        self.assertIn("live", loaded)
        self.assertTrue(loaded["demo"].incident_active)
        self.assertAlmostEqual(loaded["demo"].paper_paused_since, now - 100.0, places=3)
        self.assertEqual(loaded["demo"].last_alarm_trigger, "paper_paused_stuck")
        self.assertFalse(loaded["live"].incident_active)

    def test_missing_state_file_returns_empty(self):
        """缺檔 → 空 dict（冷啟動）。"""
        loaded = load_inert_state(self.data_dir)
        self.assertEqual(loaded, {})

    def test_corrupted_state_file_returns_empty(self):
        """壞 JSON → 空 dict（fail-soft）。"""
        path = Path(self.data_dir) / INERT_STATE_FILE
        path.write_text("not valid json", encoding="utf-8")
        loaded = load_inert_state(self.data_dir)
        self.assertEqual(loaded, {})

    def test_state_persistence_across_restart(self):
        """端對端：incident_active 寫盤 → 重載 → cooldown 仍生效不重發 alarm。"""
        now = time.time()
        states_session1 = {
            "demo": InertState(
                paper_paused_since=now - 3700.0,
                incident_active=True,
                last_alarm_ts=now - 60.0,
                last_alarm_trigger="paper_paused_stuck",
            ),
        }
        save_inert_state(self.data_dir, states_session1)

        # 模擬 watchdog restart：重新 load_inert_state
        states_session2 = load_inert_state(self.data_dir)
        config = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        snap = make_snapshot(paper_paused=True, halt_kind="daily_loss")
        state = states_session2["demo"]
        # cooldown 期間再評估：返 None，不重發 alarm
        result = evaluate_inert_probe(
            snap_path, snap, state, config, now, self.data_dir,
        )
        self.assertIsNone(result)
        # 仍 incident_active
        self.assertTrue(state.incident_active)


class TestRunInertProbeOnce(unittest.TestCase):
    """B-7：multi-engine 獨立 state；stale snapshot 不參與 inert probe。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_snap(self, name: str, snap: dict) -> Path:
        path = Path(self.data_dir) / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        # 確保 mtime 是 now（fresh）
        os.utime(path, None)
        return path

    def test_multi_engine_independent_state(self):
        """B-7：demo halt 不影響 live alarm 狀態。"""
        now = time.time()
        # demo 已 paused 3700s
        demo_snap = make_snapshot(
            paper_paused=True, trading_mode="demo", halt_kind="daily_loss",
            halt_set_ts_ms=int((now - 3700.0) * 1000),
        )
        # live 正常運行（有最近 intent）
        live_snap = make_snapshot(
            paper_paused=False, trading_mode="live",
            recent_intents=[{"timestamp_ms": int(now * 1000)}],
        )
        self._write_snap("pipeline_snapshot_demo.json", demo_snap)
        self._write_snap("pipeline_snapshot_live.json", live_snap)

        config = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}
        snapshot_paths = [
            Path(self.data_dir) / "pipeline_snapshot_demo.json",
            Path(self.data_dir) / "pipeline_snapshot_live.json",
        ]
        inert_states: dict[str, InertState] = {}
        events = run_inert_probe_once(
            snapshot_paths, inert_states, config, self.data_dir, now,
        )
        # demo 應 fire alarm，live 不應
        self.assertEqual(events[snapshot_paths[0]], "paper_paused_stuck")
        self.assertNotEqual(events.get(snapshot_paths[1]), "paper_paused_stuck")
        self.assertTrue(inert_states["demo"].incident_active)
        self.assertFalse(inert_states.get("live", InertState()).incident_active)

    def test_stale_snapshot_skipped(self):
        """spec §4.8：stale snapshot 走 crash 路徑優先，inert probe 跳過。"""
        now = time.time()
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(make_snapshot(paper_paused=True), f)
        # 設成 200s 前（超過 STALE_THRESHOLD_SECONDS 預設 45s）
        old = time.time() - 200.0
        os.utime(snap_path, (old, old))
        config = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}
        inert_states: dict[str, InertState] = {}
        events = run_inert_probe_once(
            [snap_path], inert_states, config, self.data_dir, now,
        )
        # stale 應被 skip，無 event
        self.assertEqual(events, {})

    def test_corrupted_snapshot_skipped(self):
        """JSON parse error → 跳過此次 poll，不 alarm。"""
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        snap_path.write_text("not valid json", encoding="utf-8")
        config = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}
        inert_states: dict[str, InertState] = {}
        events = run_inert_probe_once(
            [snap_path], inert_states, config, self.data_dir, time.time(),
        )
        self.assertEqual(events, {})


# ---------------------------------------------------------------------------
# Round 2 修補測試（HIGH-1 + MEDIUM-1 + LOW-1 + LOW-2）
# ---------------------------------------------------------------------------


class TestRound2HighStateCorruption(unittest.TestCase):
    """Round 2 HIGH-1：load_inert_state 對 type-mismatch JSON 防呆。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_inert_state_corrupted_payload_does_not_crash(self):
        """type-mismatch JSON：壞 engine 條目被 skip，其餘條目保留，不 raise。

        E2 reproduce 用 case：`{"demo": {"last_intent_ts_ms": "not_int"}, "live":
        {...有效...}}` 必須不 crash 且 live 條目保留 — 證明 partial recovery。
        """
        path = Path(self.data_dir) / INERT_STATE_FILE
        # demo 條目 last_intent_ts_ms 是 string；live 條目正常
        bad_state = {
            "demo": {
                "paper_paused_since": "bad_string",
                "last_intent_ts_ms": "not_int",
                "last_alarm_ts": None,
                "last_alarm_trigger": "paper_paused_stuck",
                "incident_active": True,
            },
            "live": {
                "paper_paused_since": None,
                "last_intent_ts_ms": 12345,
                "last_alarm_ts": None,
                "last_alarm_trigger": None,
                "incident_active": False,
            },
        }
        path.write_text(json.dumps(bad_state), encoding="utf-8")

        # 不應 raise — 是 HIGH finding 核心：watchdog 啟動不可 crash
        loaded = load_inert_state(self.data_dir)

        # demo 條目壞 type，必須被 skip
        self.assertNotIn("demo", loaded)
        # live 條目保留（partial recovery 設計）
        self.assertIn("live", loaded)
        self.assertEqual(loaded["live"].last_intent_ts_ms, 12345)
        self.assertFalse(loaded["live"].incident_active)

    def test_load_inert_state_all_bad_engines_returns_empty(self):
        """全 engine 條目都壞 type → 返空 dict，不 raise。"""
        path = Path(self.data_dir) / INERT_STATE_FILE
        bad_state = {
            "demo": {"last_intent_ts_ms": "not_int"},
            "live": {"last_intent_ts_ms": [1, 2, 3]},  # list 不可 int()
        }
        path.write_text(json.dumps(bad_state), encoding="utf-8")
        loaded = load_inert_state(self.data_dir)
        self.assertEqual(loaded, {})


class TestRound2MediumTransitionOnlyWrite(unittest.TestCase):
    """Round 2 MEDIUM-1：save_inert_state 僅在 state 變化時寫盤。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _state_file_mtime(self) -> Optional[float]:
        """讀取 inert_state.json mtime；不存在返 None。"""
        path = Path(self.data_dir) / INERT_STATE_FILE
        if not path.exists():
            return None
        return path.stat().st_mtime_ns

    def test_inert_state_write_skipped_when_unchanged(self):
        """跑 10 次相同 state save，僅 1 次實際寫盤；隨後 state 變化再寫第 2 次。"""
        states = {
            "demo": InertState(
                paper_paused_since=time.time() - 100.0,
                last_intent_ts_ms=12345,
                incident_active=False,
            ),
        }

        # 第一次 save：first write 應寫盤
        last_written = save_inert_state(self.data_dir, states, last_written=None)
        first_mtime = self._state_file_mtime()
        self.assertIsNotNone(first_mtime)
        self.assertIsNotNone(last_written)

        # 連續 9 次 save 相同 state：mtime 不變（無寫盤）
        # 為什麼直接比 mtime_ns：os.replace 原子 rename 必 bump mtime；mtime
        # 不變即可確認沒走實際寫盤路徑。
        for _ in range(9):
            last_written = save_inert_state(self.data_dir, states, last_written)
        self.assertEqual(self._state_file_mtime(), first_mtime)

        # 變更 state：mtime 必須改變（觸 transition write）
        # 為什麼 sleep 1ms：HFS+/APFS mtime 解析度可能 sub-ms；確保新 mtime 與舊不同
        time.sleep(0.01)
        states["demo"].incident_active = True
        last_written = save_inert_state(self.data_dir, states, last_written)
        new_mtime = self._state_file_mtime()
        self.assertNotEqual(new_mtime, first_mtime)

        # 驗 disk 內容正確反映新 state
        reloaded = load_inert_state(self.data_dir)
        self.assertTrue(reloaded["demo"].incident_active)

    def test_inert_state_first_write_with_no_baseline(self):
        """last_written=None → first write 必寫盤（cold start fallback）。"""
        states = {"demo": InertState(last_intent_ts_ms=1)}
        result = save_inert_state(self.data_dir, states, last_written=None)
        self.assertIsNotNone(result)
        self.assertIsNotNone(self._state_file_mtime())
        # result 反映剛寫的 serializable snapshot
        self.assertEqual(result["demo"]["last_intent_ts_ms"], 1)


class TestRound2LowNegativeThreshold(unittest.TestCase):
    """Round 2 LOW-1：負/0 threshold 在 load_inert_probe_config 被拒收。"""

    def test_load_inert_probe_config_negative_threshold_rejected(self):
        """負 threshold → warning + fallback default，不污染 config slot。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8",
        ) as f:
            f.write(
                "[demo]\n"
                "paper_paused_threshold_seconds = -1\n"
                "intents_zero_delta_window_seconds = 0\n"
            )
            tmp_path = Path(f.name)
        try:
            cfg = load_inert_probe_config(tmp_path)
            # 兩個都該 fallback default（3600 / 1200）
            self.assertEqual(cfg["demo"]["paper_paused_threshold_seconds"], 3600.0)
            self.assertEqual(cfg["demo"]["intents_zero_delta_window_seconds"], 1200.0)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_load_inert_probe_config_positive_threshold_accepted(self):
        """正常 threshold 仍正確載入（驗 LOW-1 patch 不誤殺）。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False, encoding="utf-8",
        ) as f:
            f.write(
                "[live]\n"
                "paper_paused_threshold_seconds = 600\n"
            )
            tmp_path = Path(f.name)
        try:
            cfg = load_inert_probe_config(tmp_path)
            self.assertEqual(cfg["live"]["paper_paused_threshold_seconds"], 600.0)
        finally:
            tmp_path.unlink(missing_ok=True)


class TestRound2LowClearedFallback(unittest.TestCase):
    """Round 2 LOW-2：_emit_inert_cleared 對 None trigger fallback marker。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_cleared_event_uses_no_trigger_recorded_fallback(self):
        """state.last_alarm_trigger=None 時 jsonl 寫 `no_trigger_recorded`
        非 null（audit 完整度）。"""
        now = time.time()
        # 模擬 state 載入時 incident_active=True 但 last_alarm_trigger 缺失
        state = InertState(
            paper_paused_since=now - 3700.0,
            incident_active=True,
            last_alarm_ts=now - 60.0,
            last_alarm_trigger=None,  # corruption / partial load case
        )
        config = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        # snapshot 已清掉 paper_paused 且無 intent → cleared 路徑
        snap = make_snapshot(paper_paused=False)
        result = evaluate_inert_probe(
            snap_path, snap, state, config, now, self.data_dir,
        )
        self.assertEqual(result, "cleared")

        # 讀 canary_events.jsonl 驗 fallback 字串
        jsonl_path = Path(self.data_dir) / "canary_events.jsonl"
        self.assertTrue(jsonl_path.exists())
        events = [json.loads(line) for line in jsonl_path.read_text().strip().split("\n")]
        cleared_events = [e for e in events if e.get("event") == "TRADING_INERT_CLEARED"]
        self.assertEqual(len(cleared_events), 1)
        self.assertEqual(cleared_events[0]["previous_trigger"], "no_trigger_recorded")

    def test_cleared_event_keeps_real_trigger_when_present(self):
        """state.last_alarm_trigger 有值時 jsonl 寫實際值，不被 fallback 誤蓋。"""
        now = time.time()
        state = InertState(
            paper_paused_since=now - 3700.0,
            incident_active=True,
            last_alarm_ts=now - 60.0,
            last_alarm_trigger="paper_paused_stuck",
        )
        config = {k: dict(v) for k, v in INERT_PROBE_DEFAULTS.items()}
        snap_path = Path(self.data_dir) / "pipeline_snapshot_demo.json"
        snap = make_snapshot(paper_paused=False)
        evaluate_inert_probe(snap_path, snap, state, config, now, self.data_dir)
        jsonl_path = Path(self.data_dir) / "canary_events.jsonl"
        events = [json.loads(line) for line in jsonl_path.read_text().strip().split("\n")]
        cleared_events = [e for e in events if e.get("event") == "TRADING_INERT_CLEARED"]
        self.assertEqual(cleared_events[0]["previous_trigger"], "paper_paused_stuck")


if __name__ == "__main__":
    unittest.main(verbosity=2)
