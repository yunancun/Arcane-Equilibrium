#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：gate_b_auto_capture 單元 + gate_b_watch 整合測試（AMD-2026-07-10-01）。
  覆蓋：cap=5 釘死、預設 OFF 零副作用、探針自啟 / 附掛運行中探針、symbol 去重、
  cap 滿自動停 + 一次性 audit 行、spawn 失敗不耗名額、dry-run 不落地、
  公告標題 symbol 防誤耗、R-0 隔離紅線靜態 grep、run_once 整合。
"""

import datetime as dt
import inspect
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_b_auto_capture as gba  # noqa: E402
import gate_b_watch as gbw  # noqa: E402

NOW = dt.datetime(2026, 7, 10, 10, 0, tzinfo=dt.timezone.utc).timestamp()


def _candidate(
    symbol="NEWUSDT",
    *,
    action=gba.ACTION_START_NOW,
    trigger=gba.TRIGGER_PRELAUNCH_ACTIVE,
    title=None,
):
    c = {
        "candidate_key": f"test:{symbol}:{trigger}",
        "symbol": symbol,
        "recommended_action": action,
        "trigger_type": trigger,
    }
    if title is not None:
        c["title"] = title
    return c


class SpawnRecorder:
    def __init__(self, *, exc=None):
        self.calls = []
        self.exc = exc

    def __call__(self, data_dir, run_id):
        self.calls.append({"data_dir": data_dir, "run_id": run_id})
        if self.exc is not None:
            raise self.exc
        return 4242 + len(self.calls), f"{data_dir}/logs/{run_id}.log"


class AlertRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, subject, body, severity, data_dir):
        self.calls.append({"subject": subject, "body": body, "severity": severity})


def _no_sleep(_seconds):
    return None


def _audit_lines(data_dir):
    path = Path(data_dir) / gba.ARTIFACT_DIR / gba.AUDIT_FILE
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _run(tmp_path, state, candidates, *, now=NOW, dry_run=False, spawn=None,
         alert=None, pid_alive=None):
    return gba.maybe_auto_capture(
        str(tmp_path),
        state,
        candidates,
        now=now,
        dry_run=dry_run,
        alert_fn=alert or AlertRecorder(),
        spawn_fn=spawn,
        pid_alive_fn=pid_alive or (lambda _pid: False),
        sleep_fn=_no_sleep,
    )


def test_cap_constant_is_five_per_amd():
    # 釘死 operator 授權上限：改 cap 必紅，逼新 AMD（AMD-2026-07-10-01-2）。
    assert gba.AUTO_CAPTURE_CAP == 5


def test_disabled_by_default_zero_side_effects(tmp_path, monkeypatch):
    monkeypatch.delenv(gba.ENV_FLAG, raising=False)
    spawn = SpawnRecorder()
    state = {}
    summary = _run(tmp_path, state, [_candidate()], spawn=spawn)

    assert summary["status"] == gba.STATUS_DISABLED
    assert summary["enabled"] is False
    assert spawn.calls == []
    assert state == {}
    assert _audit_lines(tmp_path) == []


def test_enabled_starts_probe_and_persists_counter(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    alert = AlertRecorder()
    state = {}
    summary = _run(tmp_path, state, [_candidate("AAAUSDT")], spawn=spawn, alert=alert)

    assert summary["status"] == gba.STATUS_STARTED
    assert summary["used"] == 1
    assert summary["remaining"] == 4
    assert summary["attributed_symbols"] == ["AAAUSDT"]
    assert len(spawn.calls) == 1
    assert spawn.calls[0]["run_id"].startswith("gate_b_auto_")

    captured = state[gba.STATE_KEY]["captured_symbols"]
    assert captured["AAAUSDT"]["slot"] == 1
    assert captured["AAAUSDT"]["run_id"] == summary["started_run_id"]

    events = [row["event"] for row in _audit_lines(tmp_path)]
    assert events == ["probe_started", "listing_capture_attributed"]
    for row in _audit_lines(tmp_path):
        assert row["authorization"] == gba.AUTHORIZATION_REF
    assert any("[GATE-B-AUTO-CAPTURE][P1]" in c["subject"] for c in alert.calls)


def test_same_symbol_across_rounds_consumes_one_slot(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    state = {}
    _run(tmp_path, state, [_candidate("AAAUSDT")], spawn=spawn)
    summary2 = _run(tmp_path, state, [_candidate("AAAUSDT")], spawn=spawn)

    assert summary2["status"] == gba.STATUS_IDLE
    assert summary2["used"] == 1
    assert len(spawn.calls) == 1


def test_running_probe_attributes_new_symbol_without_second_spawn(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    state = {}
    _run(tmp_path, state, [_candidate("AAAUSDT")], spawn=spawn)
    run_id = state[gba.STATE_KEY]["active_probe"]["run_id"]

    # 探針仍存活（pid alive + 未過期）：新 symbol 附掛同一 run，不二次 spawn。
    summary2 = _run(
        tmp_path,
        state,
        [_candidate("BBBUSDT")],
        now=NOW + 600,
        spawn=spawn,
        pid_alive=lambda _pid: True,
    )

    assert summary2["status"] == gba.STATUS_ATTRIBUTED
    assert summary2["started_run_id"] is None
    assert summary2["attributed_symbols"] == ["BBBUSDT"]
    assert len(spawn.calls) == 1
    assert state[gba.STATE_KEY]["captured_symbols"]["BBBUSDT"]["run_id"] == run_id
    assert state[gba.STATE_KEY]["captured_symbols"]["BBBUSDT"]["slot"] == 2


def test_dead_probe_triggers_new_spawn(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    state = {}
    _run(tmp_path, state, [_candidate("AAAUSDT")], spawn=spawn)
    summary2 = _run(
        tmp_path,
        state,
        [_candidate("BBBUSDT")],
        now=NOW + 600,
        spawn=spawn,
        pid_alive=lambda _pid: False,
    )

    assert summary2["status"] == gba.STATUS_STARTED
    assert len(spawn.calls) == 2


def test_cap_reached_stops_with_single_audit_line(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    alert = AlertRecorder()
    state = {
        gba.STATE_KEY: {
            "captured_symbols": {
                f"S{i}USDT": {"slot": i + 1, "run_id": "gate_b_auto_x"}
                for i in range(4)
            }
        }
    }
    # 剩 1 名額，一輪來 2 個新上市：只消耗 1 個（裁剪到剩額），並觸發 cap_reached。
    summary = _run(
        tmp_path,
        state,
        [_candidate("AAAUSDT"), _candidate("BBBUSDT")],
        spawn=spawn,
        alert=alert,
    )

    assert summary["used"] == 5
    assert summary["remaining"] == 0
    assert summary["attributed_symbols"] == ["AAAUSDT"]
    assert "BBBUSDT" not in state[gba.STATE_KEY]["captured_symbols"]

    events = [row["event"] for row in _audit_lines(tmp_path)]
    assert events.count("cap_reached") == 1
    assert any("[GATE-B-AUTO-CAPTURE][CAP]" in c["subject"] for c in alert.calls)

    # cap 滿後：新上市零 spawn、零新名額、cap_reached audit 不重複。
    spawn_count_before = len(spawn.calls)
    summary2 = _run(tmp_path, state, [_candidate("CCCUSDT")], spawn=spawn, alert=alert)
    assert summary2["status"] == gba.STATUS_CAP_REACHED
    assert len(spawn.calls) == spawn_count_before
    events2 = [row["event"] for row in _audit_lines(tmp_path)]
    assert events2.count("cap_reached") == 1


def test_spawn_failure_does_not_consume_cap(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder(exc=OSError("boom"))
    state = {}
    summary = _run(tmp_path, state, [_candidate("AAAUSDT")], spawn=spawn)

    assert summary["status"] == gba.STATUS_LAUNCH_FAILED
    assert summary["used"] == 0
    assert state[gba.STATE_KEY].get("captured_symbols") == {}
    events = [row["event"] for row in _audit_lines(tmp_path)]
    assert events == ["probe_launch_failed"]


def test_dry_run_reports_without_spawn_or_state_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    state = {}
    summary = _run(tmp_path, state, [_candidate("AAAUSDT")], dry_run=True, spawn=spawn)

    assert summary["status"] == gba.STATUS_DRY_RUN
    assert summary["attributed_symbols"] == ["AAAUSDT"]
    assert spawn.calls == []
    assert state[gba.STATE_KEY].get("captured_symbols") == {}
    assert _audit_lines(tmp_path) == []


def test_ineligible_candidates_do_not_burn_cap(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    state = {}
    candidates = [
        # symbol 解析失敗的公告候選。
        _candidate("UNKNOWN", trigger=gba.TRIGGER_PREMARKET_LISTING, title="Bybit lists"),
        # 轉標準合約非新上市。
        _candidate("CONVUSDT", trigger="announcement_standard_conversion"),
        # 未到啟動窗口。
        _candidate("SCHEDUSDT", action="SCHEDULE_GATE_B_WINDOW"),
        # 公告 START_NOW 但 symbol 不在標題內（description 正文 regex 誤匹配防線）。
        _candidate(
            "OTHERUSDT",
            trigger=gba.TRIGGER_PREMARKET_LISTING,
            title="Bybit to List Pre-Market Perpetuals for REALUSDT",
        ),
    ]
    summary = _run(tmp_path, state, candidates, spawn=spawn)

    assert summary["status"] == gba.STATUS_IDLE
    assert spawn.calls == []
    assert state[gba.STATE_KEY].get("captured_symbols") == {}


def test_announcement_symbol_in_title_is_eligible(tmp_path, monkeypatch):
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    state = {}
    summary = _run(
        tmp_path,
        state,
        [
            _candidate(
                "REALUSDT",
                trigger=gba.TRIGGER_PREMARKET_LISTING,
                title="Bybit to List Pre-Market Perpetuals for REALUSDT",
            )
        ],
        spawn=spawn,
    )

    assert summary["status"] == gba.STATUS_STARTED
    assert summary["attributed_symbols"] == ["REALUSDT"]


def test_run_once_integration_flag_on(tmp_path, monkeypatch):
    """gbw.run_once 整合：flag ON + fresh CallAuction PreLaunch → 探針自啟 + artifact 記錄。"""
    monkeypatch.setenv(gba.ENV_FLAG, "1")
    spawn = SpawnRecorder()
    monkeypatch.setattr(gba, "_spawn_probe", spawn)
    monkeypatch.setattr(gba, "_pid_alive", lambda _pid: False)

    launch_ms = int((NOW + 3600) * 1000)
    prelaunch_row = {
        "symbol": "NEWUSDT",
        "status": "PreLaunch",
        "launchTime": str(launch_ms),
        "preListingInfo": {"curAuctionPhase": "CallAuction", "phases": []},
    }

    class Opener:
        def __call__(self, req, timeout=None):
            import test_gate_b_watch as helpers  # sibling 測試的 fake response 復用

            if "/v5/announcements/index" in req.full_url:
                return helpers.FakeHTTPResponse(helpers._v5_list([]))
            return helpers.FakeHTTPResponse(helpers._v5_list([prelaunch_row]))

    alert = AlertRecorder()
    rc = gbw.run_once(
        str(tmp_path),
        opener=Opener(),
        alert_fn=alert,
        now=NOW,
        announcement_pages=1,
        sleep_fn=_no_sleep,
    )
    assert rc == 0

    latest = json.loads(
        (Path(tmp_path) / gbw.ARTIFACT_DIR / gbw.LATEST_FILE).read_text(encoding="utf-8")
    )
    assert latest["auto_capture"]["enabled"] is True
    assert latest["auto_capture"]["used"] == 1
    assert latest["auto_capture"]["attributed_symbols"] == ["NEWUSDT"]
    assert "AMD-2026-07-10-01" in latest["boundary"]
    assert len(spawn.calls) == 1

    # 計數器持久化：state 檔內 slot 落地，下一輪 load_state 可續。
    state = json.loads((Path(tmp_path) / gbw.STATE_FILE).read_text(encoding="utf-8"))
    assert state[gba.STATE_KEY]["captured_symbols"]["NEWUSDT"]["slot"] == 1


def test_run_once_integration_flag_off_boundary_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv(gba.ENV_FLAG, raising=False)
    spawn = SpawnRecorder()
    monkeypatch.setattr(gba, "_spawn_probe", spawn)

    class Opener:
        def __call__(self, req, timeout=None):
            import test_gate_b_watch as helpers

            return helpers.FakeHTTPResponse(helpers._v5_list([]))

    rc = gbw.run_once(
        str(tmp_path),
        opener=Opener(),
        alert_fn=AlertRecorder(),
        now=NOW,
        announcement_pages=1,
        sleep_fn=_no_sleep,
    )
    assert rc == 0
    latest = json.loads(
        (Path(tmp_path) / gbw.ARTIFACT_DIR / gbw.LATEST_FILE).read_text(encoding="utf-8")
    )
    assert latest["auto_capture"]["status"] == gba.STATUS_DISABLED
    assert "auto-capture disabled" in latest["boundary"]
    assert spawn.calls == []


def test_static_isolation_no_runtime_or_db_routes():
    """R-0 紅線：本模塊禁任何生產 / DB / 交易路徑 token；唯一 spawn 目標 = 隔離探針。"""
    src = inspect.getsource(gba)
    forbidden = (
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "place_order",
        "cancel_order",
        "X-BAPI-SIGN",
        "OPENCLAW_ALLOW_MAINNET",
        "control_api_v1",
        "program_code",
        "rust/",
        "openclaw_engine",
        "decision_lease",
    )
    for needle in forbidden:
        assert needle not in src, f"forbidden route token found: {needle}"
    assert gba.probe_script_path().name == "aeg_gate_b_probe.py"
    # 探針檔案真實存在於 repo（防 rename 後 spawn 永遠 fail-soft 的靜默腐化）。
    assert gba.probe_script_path().is_file()
