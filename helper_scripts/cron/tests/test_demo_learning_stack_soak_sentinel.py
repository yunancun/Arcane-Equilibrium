from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import demo_learning_stack_healthcheck as mod


NOW = dt.datetime(2026, 7, 4, 21, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|ETHUSDT|Buy"


def _write_soak_plan(path: Path, *, expires: str, status: str = "READY_FOR_DEMO_LEARNING_PROBE") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "cost_gate_demo_learning_lane_plan_v1",
                "status": status,
                "operator_authorization": {
                    "side_cell_key": SIDE_CELL,
                    "expires_at_utc": expires,
                },
            }
        ),
        encoding="utf-8",
    )


def _admission_record(*, decision: str, ts: dt.datetime, record_type: str = "probe_admission_decision") -> str:
    return json.dumps(
        {
            "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
            "record_type": record_type,
            "generated_at_utc": ts.isoformat(),
            "decision": decision,
            "reason": "x",
        }
    )


def _write_ledger(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_sentinel_no_warn_when_not_armed() -> None:
    env = {"envelope_active": True}
    dist = {"admission_decision_count": 0}
    out = mod._soak_sentinel(armed_adapter=False, envelope=env, distribution=dist, now_utc=NOW)
    assert out["armed"] is False
    assert out["warn"] is False


def test_sentinel_no_warn_when_armed_but_envelope_inactive() -> None:
    env = {"envelope_active": False}
    dist = {"admission_decision_count": 0}
    out = mod._soak_sentinel(armed_adapter=True, envelope=env, distribution=dist, now_utc=NOW)
    assert out["armed"] is False
    assert out["warn"] is False


def test_sentinel_warns_when_armed_active_and_zero_admissions() -> None:
    env = {"envelope_active": True}
    dist = {"admission_decision_count": 0}
    out = mod._soak_sentinel(armed_adapter=True, envelope=env, distribution=dist, now_utc=NOW)
    assert out["armed"] is True
    assert out["warn"] is True
    assert "soak_armed_but_zero_admission_decisions_in_window" in out["reasons"]


def test_sentinel_no_warn_when_admissions_present() -> None:
    env = {"envelope_active": True}
    dist = {"admission_decision_count": 5}
    out = mod._soak_sentinel(armed_adapter=True, envelope=env, distribution=dist, now_utc=NOW)
    assert out["armed"] is True
    assert out["warn"] is False


def test_distribution_ignores_non_admission_rows_not_row_count(tmp_path) -> None:
    # 核心不變量:哨兵判據=admission decision 分布,不是 ledger 行數。窗內塞滿 capture-error /
    # probe_outcome 雜 record 也不能餵飽哨兵——admission_decision_count 必須仍為 0。
    ledger = tmp_path / "probe_ledger.jsonl"
    fresh = NOW - dt.timedelta(hours=1)
    lines = [
        _admission_record(decision="X", ts=fresh, record_type="probe_outcome"),
        _admission_record(decision="Y", ts=fresh, record_type="blocked_signal_outcome"),
        _admission_record(decision="Z", ts=fresh, record_type="capture_error"),
    ]
    _write_ledger(ledger, lines)
    dist = mod._admission_decision_distribution(
        ledger, now_utc=NOW, window_seconds=6 * 3600
    )
    assert dist["present"] is True
    assert dist["admission_decision_count"] == 0  # 雜 record 不算 admission 活動
    # 但這些雜行本身數量非零 → 證明我們沒用 row-count 當判據。
    assert len(ledger.read_text().splitlines()) == 3


def test_distribution_windows_out_old_admissions(tmp_path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    old = NOW - dt.timedelta(hours=10)  # 落窗外(>6h)
    fresh = NOW - dt.timedelta(hours=2)
    _write_ledger(
        ledger,
        [
            _admission_record(decision="ADMIT_DEMO_LEARNING_PROBE", ts=old),
            _admission_record(decision="WITHHELD_PLAN_STALE", ts=fresh),
            _admission_record(decision="ADMIT_DEMO_LEARNING_PROBE", ts=fresh),
        ],
    )
    dist = mod._admission_decision_distribution(
        ledger, now_utc=NOW, window_seconds=6 * 3600
    )
    assert dist["admission_decision_count"] == 2  # 舊那筆被窗外剔除
    assert dist["admitted_count"] == 1
    assert dist["withheld_or_other_count"] == 1
    assert dist["decision_counts"]["ADMIT_DEMO_LEARNING_PROBE"] == 1


def test_missing_ledger_is_zero_admissions_not_crash(tmp_path) -> None:
    dist = mod._admission_decision_distribution(
        tmp_path / "nope.jsonl", now_utc=NOW, window_seconds=6 * 3600
    )
    assert dist["present"] is False
    assert dist["admission_decision_count"] == 0


def test_soak_envelope_active_expired_and_fresh(tmp_path) -> None:
    plan = tmp_path / "soak.json"
    _write_soak_plan(plan, expires="2099-01-01T00:00:00+00:00")
    env = mod._soak_envelope_status(plan, now_utc=NOW)
    assert env["envelope_active"] is True

    _write_soak_plan(plan, expires="2026-07-01T00:00:00+00:00")
    env2 = mod._soak_envelope_status(plan, now_utc=NOW)
    assert env2["envelope_active"] is False


def test_build_healthcheck_surfaces_soak_warn_only_when_stack_green(tmp_path) -> None:
    # 端到端:即使武裝+零 admission,若 stack 本身未 green(如 source 不 ready) 也不會被 soak
    # WARN 掩蓋——soak WARN 僅在 stack 否則會 EVIDENCE_STACK_ACTIVE 時升起。
    plan = tmp_path / "cost_gate_learning_lane" / "bounded_demo_probe_soak_plan.json"
    _write_soak_plan(plan, expires="2099-01-01T00:00:00+00:00")
    ledger = tmp_path / "cost_gate_learning_lane" / "probe_ledger.jsonl"
    _write_ledger(ledger, [_admission_record(decision="X", ts=NOW, record_type="probe_outcome")])
    # repo_root 不是 git repo → source head_error → source_not_ready(比 soak 嚴重),
    # 故 status 應為 SOURCE_NOT_READY 而非 SOAK_SENTINEL_WARN。
    out = mod.build_healthcheck(
        data_dir=tmp_path,
        repo_root=tmp_path / "not_a_repo",
        expected_head=None,
        crontab_text_file=None,
        max_heartbeat_age_minutes=90,
        max_status_age_minutes=180,
        soak_adapter_armed=True,
        soak_plan_json=plan,
        probe_ledger_jsonl=ledger,
        soak_sentinel_window_hours=6,
        now_utc=NOW,
    )
    assert out["soak_sentinel"]["armed"] is True
    assert out["soak_sentinel"]["warn"] is True
    # soak WARN 存在於 soak_sentinel 節,但頂層 status 被更嚴重 blocker 佔用(未被掩蓋)。
    assert out["status"] != "SOAK_SENTINEL_WARN"
    assert out["answers"]["soak_sentinel_warn"] is True
