#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：incident_sentinel 單元測試（設計 §8.4 全 9 條驗收）。
主要類/函數：六軸 fault-injection、dedup 全語義、per-axis 隔離、db_unreachable、
  A2 游標 rotate/首跑、never-remediate 結構斷言、_send_alert_best_effort 簽名 smoke、
  短命進程 drain、審計 jsonl。
依賴：incident_sentinel.py、engine_watchdog.py（sibling path-insert）、pytest。
硬邊界（測試隔離鐵則 §8.2，helper_scripts/canary 無 conftest guard 庇護）：
  - 0 真 DSN、0 psycopg2.connect（DB 軸全吃 FakeConn 注入）。
  - 0 真 urlopen / 0 真外發（A3 吃注入 opener；唯一 urlopen 路徑被 monkeypatch）。
  - 全部 tmp_path；不觸真 OPENCLAW_DATA_DIR。
"""

import inspect
import json
import os
import re
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import incident_sentinel as isentinel  # noqa: E402

NOW = 1_700_000_000.0


# ───────────────────────────────────────────────────────────────────────────
# 測試替身（FakeConn / opener / alert recorder）—— 連線與外發層唯一被隔離處，
# 業務邏輯全在純函數軸內被真測。
# ───────────────────────────────────────────────────────────────────────────


class FakeCursor:
    def __init__(self, handler):
        self._handler = handler
        self._row = None
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._row = self._handler(sql, params)

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, handler):
        self._handler = handler
        self.closed = False
        self.cursors = []

    def cursor(self):
        cur = FakeCursor(self._handler)
        self.cursors.append(cur)
        return cur

    def close(self):
        self.closed = True


def _db_handler(reject=0, rate=0, offlist=0, db_max=136, success=True):
    """以 SQL 內容路由查詢結果（一個 handler 服務三個 DB 軸）。"""
    def handler(sql, params):
        if "l2_gate_seam_log" in sql:
            return (reject,)
        if "agent.lessons" in sql and "NOT IN" in sql:
            return (offlist,)
        if "agent.lessons" in sql:
            return (rate,)
        if "_sqlx_migrations" in sql:
            return (db_max, success)
        raise AssertionError(f"unexpected sql: {sql}")
    return handler


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self.status


def _opener_with(status):
    def opener(url, timeout=None):
        return FakeResponse(status)
    return opener


def _opener_raises(url, timeout=None):
    raise ConnectionRefusedError("refused")


class AlertRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, subject, body, severity, data_dir):
        self.calls.append({
            "subject": subject, "body": body,
            "severity": severity, "data_dir": data_dir,
        })


def _fresh_snapshots(data_dir: Path, now: float) -> None:
    for name in isentinel.SNAPSHOT_FILES:
        p = data_dir / name
        p.write_text("{}", encoding="utf-8")
        os.utime(p, (now, now))


def _write_canary_events(data_dir: Path, events) -> None:
    with open(data_dir / "canary_events.jsonl", "a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def _read_audit(data_dir: Path) -> list:
    path = data_dir / isentinel.AUDIT_FILE
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class Env:
    """run_once 注入環境組裝器：默認全健康，按需注壞單軸。"""

    def __init__(self, tmp_path: Path, now: float = NOW, **overrides):
        self.now = now
        self.data_dir = tmp_path / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.base_dir = tmp_path / "base"
        mig = self.base_dir / "sql" / "migrations"
        mig.mkdir(parents=True, exist_ok=True)
        (mig / "V136__t.sql").write_text("-- t", encoding="utf-8")
        if overrides.pop("fresh_snapshots", True):
            _fresh_snapshots(self.data_dir, now)
        self.alerts = AlertRecorder()
        self.sleeps = []
        self.kwargs = dict(
            conn_factory=lambda: FakeConn(_db_handler()),
            alert_fn=self.alerts,
            opener=_opener_with(200),
            pgrep_runner=lambda: True,
            now=now,
            sleep_fn=self.sleeps.append,
        )
        self.kwargs.update(overrides)

    def run(self, **kw):
        merged = dict(self.kwargs)
        merged.update(kw)
        return isentinel.run_once(str(self.data_dir), str(self.base_dir), **merged)


# ───────────────────────────────────────────────────────────────────────────
# §8.4-1 六軸 fault-injection
# ───────────────────────────────────────────────────────────────────────────


class TestA1EngineHeartbeat:
    def test_all_stale_critical(self, tmp_path):
        _fresh_snapshots(tmp_path, NOW - 1000)
        r = isentinel.check_engine_heartbeat(str(tmp_path), NOW, 900.0)
        assert not r.ok and r.severity == "CRITICAL" and r.alert_key == "a1:engine_stale"

    def test_all_missing_critical(self, tmp_path):
        r = isentinel.check_engine_heartbeat(str(tmp_path), NOW, 900.0)
        assert not r.ok
        assert all(v == "missing" for v in r.evidence["snapshot_ages"].values())

    def test_one_fresh_ok(self, tmp_path):
        _fresh_snapshots(tmp_path, NOW - 1000)
        p = tmp_path / "pipeline_snapshot_demo.json"
        os.utime(p, (NOW - 10, NOW - 10))
        r = isentinel.check_engine_heartbeat(str(tmp_path), NOW, 900.0)
        assert r.ok and r.alert_key is None


class TestA1bWatchdog:
    def test_dead_with_engine_fresh_warns(self):
        r = isentinel.check_watchdog_alive(True, pgrep_runner=lambda: False)
        assert not r.ok and r.severity == "WARN" and r.alert_key == "a1b:watchdog_absent"

    def test_dead_with_engine_stale_folds_into_a1(self):
        # A1 已觸發時 A1b 不另發：資訊併入 A1 payload（run_once 層驗證見 TestRunOnce）。
        r = isentinel.check_watchdog_alive(False, pgrep_runner=lambda: False)
        assert r.ok and r.evidence["folded_into_a1"] is True

    def test_alive_ok(self):
        r = isentinel.check_watchdog_alive(True, pgrep_runner=lambda: True)
        assert r.ok


class TestA2CanaryEvents:
    ALERTABLE = ("RESTART_FAILED", "NETWORK_OUTAGE", "TRADING_INERT_PROLONGED", "RESTART_SKIPPED")
    EXCLUDED = (
        "RESTART_CIRCUIT_BROKEN", "INERT_CIRCUIT_BROKEN", "ENGINE_DOWN_ALERT_SENT",
        "RESTART_SUCCESS", "TRADING_INERT_CLEARED",
    )

    def test_four_alertable_kinds_aggregate_one_result(self, tmp_path):
        _write_canary_events(tmp_path, [
            {"ts": NOW - 100 + i, "event": name} for i, name in enumerate(self.ALERTABLE)
        ])
        r, cursor = isentinel.check_canary_events(str(tmp_path), NOW - 3600, NOW)
        assert not r.ok and r.severity == "WARN"
        assert sum(r.evidence["alertable_counts"].values()) == 4
        assert set(r.evidence["alertable_counts"]) == set(self.ALERTABLE)
        assert r.alert_key.startswith("a2:through_")

    def test_excluded_events_do_not_trigger(self, tmp_path):
        _write_canary_events(tmp_path, [
            {"ts": NOW - 100 + i, "event": name} for i, name in enumerate(self.EXCLUDED)
        ])
        r, cursor = isentinel.check_canary_events(str(tmp_path), NOW - 3600, NOW)
        assert r.ok
        # 游標仍推進過排除集事件（下輪不重掃）。
        assert cursor > NOW - 3600

    def test_events_at_or_before_cursor_ignored(self, tmp_path):
        _write_canary_events(tmp_path, [{"ts": NOW - 7200, "event": "RESTART_FAILED"}])
        r, _ = isentinel.check_canary_events(str(tmp_path), NOW - 3600, NOW)
        assert r.ok

    def test_missing_file_ok_cursor_unchanged(self, tmp_path):
        r, cursor = isentinel.check_canary_events(str(tmp_path), NOW - 3600, NOW)
        assert r.ok and cursor == NOW - 3600

    def test_malformed_lines_counted_not_fatal(self, tmp_path):
        (tmp_path / "canary_events.jsonl").write_text(
            'not-json\n{"event": "RESTART_FAILED"}\n'
            + json.dumps({"ts": NOW - 5, "event": "RESTART_FAILED"}) + "\n",
            encoding="utf-8",
        )
        r, _ = isentinel.check_canary_events(str(tmp_path), NOW - 3600, NOW)
        assert not r.ok
        assert r.evidence["malformed_lines"] == 2
        assert r.evidence["alertable_counts"]["RESTART_FAILED"] == 1

    def test_rotate_no_duplicate_no_miss(self, tmp_path):
        # §8.4-5：rotate 模擬（換 inode 新檔）後不重複消費、不漏新事件。
        t1 = NOW - 600
        _write_canary_events(tmp_path, [{"ts": t1, "event": "RESTART_FAILED"}])
        r1, c1 = isentinel.check_canary_events(str(tmp_path), NOW - 3600, NOW)
        assert not r1.ok and c1 == t1
        (tmp_path / "canary_events.jsonl").unlink()  # rotate：舊檔歸檔
        t2 = NOW - 60
        _write_canary_events(tmp_path, [{"ts": t2, "event": "NETWORK_OUTAGE"}])
        r2, c2 = isentinel.check_canary_events(str(tmp_path), c1, NOW)
        assert not r2.ok and c2 == t2
        assert r2.evidence["alertable_counts"] == {"NETWORK_OUTAGE": 1}  # 無舊批殘留
        assert r2.alert_key != r1.alert_key  # 新批 = 新 key（dedup 不吞新事件）


class TestA3ApiHealthz:
    def test_200_ok(self):
        r = isentinel.check_api_healthz("http://127.0.0.1:8000", opener=_opener_with(200))
        assert r.ok

    def test_non_200_critical(self):
        r = isentinel.check_api_healthz("http://127.0.0.1:8000", opener=_opener_with(500))
        assert not r.ok and r.severity == "CRITICAL" and r.alert_key == "a3:api_down"

    def test_connection_refused_critical(self):
        r = isentinel.check_api_healthz("http://127.0.0.1:8000", opener=_opener_raises)
        assert not r.ok and r.severity == "CRITICAL"
        assert "ConnectionRefusedError" in r.evidence["error"]


class TestA4SeamRejects:
    def test_above_threshold_warns(self):
        r = isentinel.check_l2_seam_rejects(FakeConn(_db_handler(reject=11)), NOW, 10)
        assert not r.ok and r.severity == "WARN" and r.alert_key == "a4:reject_surge"

    def test_at_threshold_ok(self):
        r = isentinel.check_l2_seam_rejects(FakeConn(_db_handler(reject=10)), NOW, 10)
        assert r.ok

    def test_sql_is_reject_verdict_select(self):
        conn = FakeConn(_db_handler())
        isentinel.check_l2_seam_rejects(conn, NOW, 10)
        sql = conn.cursors[0].executed[0][0]
        assert "verdict = 'reject'" in sql and sql.strip().upper().startswith("SELECT")


class TestA5LessonsAnomaly:
    def test_rate_seven_per_hour_warns(self):
        r = isentinel.check_lessons_anomaly(FakeConn(_db_handler(rate=7)), NOW)
        assert not r.ok and r.alert_key == "a5:rate"

    def test_rate_six_ok(self):
        r = isentinel.check_lessons_anomaly(FakeConn(_db_handler(rate=6)), NOW)
        assert r.ok

    def test_offlist_source_warns(self):
        r = isentinel.check_lessons_anomaly(FakeConn(_db_handler(offlist=1)), NOW)
        assert not r.ok and r.alert_key == "a5:whitelist"

    def test_both_layers_fingerprint(self):
        r = isentinel.check_lessons_anomaly(FakeConn(_db_handler(rate=9, offlist=2)), NOW)
        assert r.alert_key == "a5:rate+whitelist"

    def test_whitelist_param_passed(self):
        conn = FakeConn(_db_handler())
        isentinel.check_lessons_anomaly(conn, NOW)
        offlist_calls = [
            (sql, params) for cur in conn.cursors for sql, params in cur.executed
            if "NOT IN" in sql
        ]
        assert offlist_calls[0][1] == (("l2_session", "ml_advisory", "dead_mode_seed"),)


class TestA6MigrationsDrift:
    def _repo(self, tmp_path, *versions):
        d = tmp_path / "migrations"
        d.mkdir(exist_ok=True)
        for v in versions:
            (d / f"V{v}__t.sql").write_text("-- t", encoding="utf-8")
        return str(d)

    def test_match_and_success_ok(self, tmp_path):
        repo = self._repo(tmp_path, 135, 136)
        r = isentinel.check_migrations_drift(FakeConn(_db_handler(db_max=136)), repo)
        assert r.ok

    def test_db_behind_repo_warns(self, tmp_path):
        repo = self._repo(tmp_path, 135, 136)
        r = isentinel.check_migrations_drift(FakeConn(_db_handler(db_max=135)), repo)
        assert not r.ok and r.alert_key == "a6:db135_repo136_ok"

    def test_success_false_warns_even_when_equal(self, tmp_path):
        repo = self._repo(tmp_path, 136)
        r = isentinel.check_migrations_drift(
            FakeConn(_db_handler(db_max=136, success=False)), repo)
        assert not r.ok and r.alert_key.endswith("_fail")

    def test_repo_dir_missing_audits_without_alert(self, tmp_path):
        r = isentinel.check_migrations_drift(
            FakeConn(_db_handler()), str(tmp_path / "nope"))
        assert not r.ok and r.alert_key is None and "axis_error" in r.evidence


# ───────────────────────────────────────────────────────────────────────────
# §8.4-2 dedup 全語義（run_once 層）
# ───────────────────────────────────────────────────────────────────────────


class TestDedup:
    def test_same_state_two_rounds_exactly_one_alert(self, tmp_path):
        env = Env(tmp_path, fresh_snapshots=False)  # A1 stale → CRITICAL
        env.run()
        env.run(now=NOW + 300)
        a1_alerts = [c for c in env.alerts.calls if "a1_engine" in c["subject"]]
        assert len(a1_alerts) == 1

    def test_critical_recovery_emits_info_then_rebreak_realerts(self, tmp_path):
        env = Env(tmp_path, fresh_snapshots=False)
        env.run()
        _fresh_snapshots(env.data_dir, NOW + 300)  # 恢復
        env.run(now=NOW + 300)
        recovered = [c for c in env.alerts.calls if "RECOVERED" in c["subject"]]
        assert len(recovered) == 1 and recovered[0]["severity"] == "INFO"
        for name in isentinel.SNAPSHOT_FILES:  # 再壞
            (env.data_dir / name).unlink()
        env.run(now=NOW + 600)
        a1_alerts = [
            c for c in env.alerts.calls
            if "a1_engine" in c["subject"] and "RECOVERED" not in c["subject"]
        ]
        assert len(a1_alerts) == 2  # 恢復清 key 後再壞 → 重發

    def test_warn_recovery_silent(self, tmp_path):
        env = Env(tmp_path, pgrep_runner=lambda: False)  # A1b WARN（engine fresh）
        env.run()
        assert len(env.alerts.calls) == 1
        env.kwargs["pgrep_runner"] = lambda: True  # 恢復
        _fresh_snapshots(env.data_dir, NOW + 300)
        env.run(now=NOW + 300)
        assert len(env.alerts.calls) == 1  # WARN 恢復不發 INFO

    def test_realert_window_exactly_one_per_window(self, tmp_path):
        env = Env(tmp_path, fresh_snapshots=False)
        env.run(now=NOW)                      # 首發
        env.run(now=NOW + 3 * 3600)           # 窗內 → 無
        env.run(now=NOW + 4 * 3600 + 1)       # 過窗 → 重發一次
        env.run(now=NOW + 4 * 3600 + 300)     # 新窗內 → 無
        a1_alerts = [c for c in env.alerts.calls if "a1_engine" in c["subject"]]
        assert len(a1_alerts) == 2
        assert "(re-alert #2)" in a1_alerts[1]["subject"]


# ───────────────────────────────────────────────────────────────────────────
# §8.4-3 per-axis 隔離 / §8.4-4 db_unreachable
# ───────────────────────────────────────────────────────────────────────────


class TestIsolationAndDbUnreachable:
    def test_single_axis_raise_does_not_kill_round(self, tmp_path, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("axis bug")
        monkeypatch.setattr(isentinel, "check_api_healthz", boom)
        env = Env(tmp_path)
        code = env.run()
        assert code == isentinel.EXIT_FAIL  # exit code 反映
        audit = _read_audit(env.data_dir)[-1]
        by_axis = {a["axis"]: a for a in audit["axes"]}
        assert "axis_error" in by_axis["a3_api"]["evidence"]
        # 其餘軸照常完成且健康。
        for axis in ("a1_engine", "a1b_watchdog", "a2_canary", "a4_seam", "a5_lessons", "a6_migrations"):
            assert by_axis[axis]["ok"] is True
        assert env.alerts.calls == []  # axis-error 只審計不告警（防代碼 bug 變風暴）

    def test_conn_factory_none_aggregates_single_db_unreachable_warn(self, tmp_path):
        env = Env(tmp_path, conn_factory=lambda: None)
        code = env.run()
        assert code == isentinel.EXIT_CONNECT_ERROR
        assert len(env.alerts.calls) == 1
        assert "db_unreachable" in env.alerts.calls[0]["subject"]
        assert env.alerts.calls[0]["severity"] == "WARN"
        audit = _read_audit(env.data_dir)[-1]
        axes = {a["axis"] for a in audit["axes"]}
        assert "db_unreachable" in axes
        assert not axes & {"a4_seam", "a5_lessons", "a6_migrations"}  # 三軸本輪未評估

    def test_conn_factory_raise_same_semantics(self, tmp_path):
        def boom():
            raise OSError("connection refused")
        env = Env(tmp_path, conn_factory=boom)
        assert env.run() == isentinel.EXIT_CONNECT_ERROR
        assert len(env.alerts.calls) == 1

    def test_file_http_axes_unaffected_by_db_down(self, tmp_path):
        env = Env(tmp_path, conn_factory=lambda: None, fresh_snapshots=False)
        code = env.run()
        assert code == isentinel.EXIT_FAIL  # 軸 FAIL 優先於 connect error
        subjects = [c["subject"] for c in env.alerts.calls]
        assert any("a1_engine" in s for s in subjects)
        assert any("db_unreachable" in s for s in subjects)

    def test_dsn_unresolved_without_factory(self, tmp_path, monkeypatch):
        env = Env(tmp_path, conn_factory=None)
        code = env.run(dsn_resolver=lambda: None)
        assert code == isentinel.EXIT_CONNECT_ERROR
        audit = _read_audit(env.data_dir)[-1]
        db = [a for a in audit["axes"] if a["axis"] == "db_unreachable"][0]
        assert db["evidence"]["reason"] == "dsn_unresolved"


# ───────────────────────────────────────────────────────────────────────────
# §8.4-5 游標首跑 + run_once 整合 / 審計
# ───────────────────────────────────────────────────────────────────────────


class TestRunOnceIntegration:
    def test_all_healthy_exit_zero_no_alerts_audit_covers_all_axes(self, tmp_path):
        env = Env(tmp_path)
        assert env.run() == isentinel.EXIT_PASS
        assert env.alerts.calls == [] and env.sleeps == []
        audit = _read_audit(env.data_dir)[-1]
        assert {a["axis"] for a in audit["axes"]} == {
            "a1_engine", "a1b_watchdog", "a2_canary", "a3_api",
            "a4_seam", "a5_lessons", "a6_migrations",
        }  # 每輪 verdict 摘要含未告警軸

    def test_first_run_does_not_replay_events_older_than_1h(self, tmp_path):
        env = Env(tmp_path)
        _write_canary_events(env.data_dir, [
            {"ts": NOW - 7200, "event": "RESTART_FAILED"},   # 陳年：不回放
            {"ts": NOW - 100, "event": "NETWORK_OUTAGE"},    # 1h 內：要抓
        ])
        env.run()
        a2_alerts = [c for c in env.alerts.calls if "a2_canary" in c["subject"]]
        assert len(a2_alerts) == 1 and "1 unconsumed" in a2_alerts[0]["subject"]
        state = json.loads((env.data_dir / isentinel.STATE_FILE).read_text())
        assert state["canary_cursor_ts"] == NOW - 100

    def test_watchdog_absence_folded_into_a1_payload(self, tmp_path):
        env = Env(tmp_path, fresh_snapshots=False, pgrep_runner=lambda: False)
        env.run()
        a1_alerts = [c for c in env.alerts.calls if "a1_engine" in c["subject"]]
        a1b_alerts = [c for c in env.alerts.calls if "a1b_watchdog" in c["subject"]]
        assert len(a1_alerts) == 1 and "watchdog process absent" in a1_alerts[0]["body"]
        assert a1b_alerts == []  # A1 已觸發 → A1b 不另發

    def test_dry_run_suppresses_send_but_writes_state_and_audit(self, tmp_path, capsys):
        env = Env(tmp_path, fresh_snapshots=False)
        code = env.run(dry_run=True)
        assert code == isentinel.EXIT_FAIL
        assert env.alerts.calls == [] and env.sleeps == []  # 不發送也不 drain
        state = json.loads((env.data_dir / isentinel.STATE_FILE).read_text())
        assert state["alert_keys"]["a1_engine"]["key"] == "a1:engine_stale"  # dedup state 照寫
        audit = _read_audit(env.data_dir)[-1]
        assert audit["dry_run"] is True and audit["alerts_sent"][0]["dry_run"] is True
        assert "a1_engine" in capsys.readouterr().out  # verdict 印出


# ───────────────────────────────────────────────────────────────────────────
# §8.4-6 never-remediate 結構斷言（raw source；負面斷言查全文有效）
# ───────────────────────────────────────────────────────────────────────────


class TestNeverRemediateStructural:
    SRC = Path(isentinel.__file__).read_text(encoding="utf-8")

    def test_no_process_mutation_calls(self):
        assert re.search(r"os\.kill|send_signal|\.terminate\(|\.kill\(|systemctl|restart_all", self.SRC) is None

    def test_subprocess_only_used_for_pgrep_run(self):
        # subprocess 唯一用途 = pgrep 唯讀 list（A1b 例外條款）。
        assert re.findall(r"subprocess\.(\w+)", self.SRC) == ["run"]
        assert '"pgrep"' in self.SRC

    def test_no_sql_write_keywords(self):
        # 全 SQL 唯讀：raw source 0 寫入動詞（uppercase SQL 慣例詞邊界）。
        assert re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|GRANT|REVOKE)\b", self.SRC) is None

    def test_db_session_read_only_and_timeout_params_present(self):
        assert "default_transaction_read_only=on" in self.SRC
        assert "statement_timeout" in self.SRC

    def test_never_writes_watchdog_owned_files(self):
        # 不寫 watchdog_state.json：MODULE_NOTE 合法提及邊界宣告（裸 grep 會誤紅，
        # 承「grep 正反兩面」教訓），故斷言收窄到代碼區（模塊 docstring 之後）0 引用。
        _head, sep, code_area = self.SRC.partition("\nfrom __future__")
        assert sep, "模塊結構變動：找不到 from __future__ 分界"
        assert "watchdog_state.json" not in code_area
        # canary_events.jsonl 僅唯讀消費；append 模式全檔恰一處 = _append_audit（自身審計）。
        assert re.search(r'CANARY_EVENTS_FILE\s*=\s*"canary_events\.jsonl"', self.SRC)
        assert self.SRC.count('open(path, "a"') == 1
        assert 'open(path, "r"' in self.SRC


# ───────────────────────────────────────────────────────────────────────────
# §8.4-7 簽名 smoke（monkeypatch urlopen 下 4-arg 真調用）
# ───────────────────────────────────────────────────────────────────────────


class TestAlertEmitterContract:
    def test_resolves_watchdog_emitter(self):
        import engine_watchdog
        assert isentinel._resolve_alert_fn() is engine_watchdog._send_alert_best_effort

    def test_signature_is_four_args(self):
        import engine_watchdog
        params = list(inspect.signature(engine_watchdog._send_alert_best_effort).parameters)
        assert params == ["subject", "body", "severity", "data_dir"]

    def test_four_arg_call_reaches_urlopen_under_monkeypatch(self, tmp_path, monkeypatch):
        import engine_watchdog
        for key in (
            "OPENCLAW_TELEGRAM_BOT_TOKEN", "OPENCLAW_TELEGRAM_CHAT_ID",
            "OPENCLAW_WEBHOOK_URLS", "OPENCLAW_WEBHOOK_SECRET",
        ):
            monkeypatch.delenv(key, raising=False)
        (tmp_path / "alert_config.json").write_text(json.dumps({
            "version": 1,
            "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
            "webhook": {"enabled": True, "urls": ["https://example.invalid/hook"], "secret": ""},
        }), encoding="utf-8")
        captured = []
        done = threading.Event()

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            done.set()
            return _Resp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        engine_watchdog._send_alert_best_effort("subj", "body", "INFO", str(tmp_path))
        assert done.wait(2.0), "daemon thread 2s 內未呼叫（已 monkeypatch 的）urlopen"
        assert captured[0].full_url == "https://example.invalid/hook"


# ───────────────────────────────────────────────────────────────────────────
# §8.4-8 短命進程 drain
# ───────────────────────────────────────────────────────────────────────────


class TestDrain:
    def test_drain_sleep_after_alert_emitted(self, tmp_path):
        env = Env(tmp_path, fresh_snapshots=False)
        env.run()
        assert env.sleeps == [6.0]  # ALERT_DRAIN_SECONDS 默認 6（> 5s HTTP timeout）

    def test_no_drain_when_no_alert(self, tmp_path):
        env = Env(tmp_path)
        env.run()
        assert env.sleeps == []

    def test_drain_env_overridable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_SENTINEL_ALERT_DRAIN_SECONDS", "2.5")
        env = Env(tmp_path, fresh_snapshots=False)
        env.run()
        assert env.sleeps == [2.5]

    def test_slow_alert_fn_does_not_break_round(self, tmp_path):
        # monkeypatch 慢 send（同步部分慢）：run_once 仍完成且 drain 介入於其後。
        order = []

        def slow_alert(subject, body, severity, data_dir):
            order.append("send")

        env = Env(tmp_path, fresh_snapshots=False, alert_fn=slow_alert,
                  sleep_fn=lambda s: order.append(f"drain:{s}"))
        assert env.run() == isentinel.EXIT_FAIL
        assert order == ["send", "drain:6.0"]


# ───────────────────────────────────────────────────────────────────────────
# probe / CLI 細節
# ───────────────────────────────────────────────────────────────────────────


class TestProbeAndCli:
    def test_probe_alert_sends_info_and_audits(self, tmp_path):
        rec = AlertRecorder()
        sleeps = []
        code = isentinel._probe_alert(str(tmp_path), alert_fn=rec, sleep_fn=sleeps.append)
        assert code == 0
        assert rec.calls[0]["severity"] == "INFO" and "probe" in rec.calls[0]["subject"]
        assert _read_audit(tmp_path)[-1]["kind"] == "probe_alert"
        assert sleeps == [6.0]

    def test_env_threshold_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_SENTINEL_ENGINE_STALE_SECONDS", "30")
        env = Env(tmp_path)
        for name in isentinel.SNAPSHOT_FILES:
            os.utime(env.data_dir / name, (NOW - 60, NOW - 60))  # 60s > 30s override
        assert env.run() == isentinel.EXIT_FAIL

    def test_alertable_event_set_env_override(self, monkeypatch):
        monkeypatch.setenv("OPENCLAW_SENTINEL_CANARY_ALERTABLE", "RESTART_FAILED,NETWORK_OUTAGE")
        assert isentinel._alertable_event_set() == frozenset({"RESTART_FAILED", "NETWORK_OUTAGE"})

    def test_payload_never_contains_dsn_material(self, tmp_path, monkeypatch):
        # 絕不在 payload 放 creds/DSN：db_unreachable body 只含 reason 類別。
        monkeypatch.setenv("OPENCLAW_DATABASE_URL", "postgresql://user:supersecret@10.0.0.1:5432/db")
        env = Env(tmp_path, conn_factory=lambda: None)
        env.run()
        joined = json.dumps(env.alerts.calls)
        assert "supersecret" not in joined and "postgresql://" not in joined
