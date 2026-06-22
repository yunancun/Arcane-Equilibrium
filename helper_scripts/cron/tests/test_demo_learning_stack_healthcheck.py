from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HEALTHCHECK = (
    Path(__file__).resolve().parents[1] / "demo_learning_stack_healthcheck.py"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _touch(path: Path, epoch: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    os.utime(path, (epoch, epoch))


def _git_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "a@b.c"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)
    _write(path / "README.md", "fixture\n")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _run(tmp_path: Path, data_dir: Path, repo_root: Path, crontab: str, head: str):
    cron_file = tmp_path / "crontab.txt"
    _write(cron_file, crontab)
    proc = subprocess.run(
        [
            sys.executable,
            str(HEALTHCHECK),
            "--data-dir",
            str(data_dir),
            "--repo-root",
            str(repo_root),
            "--expected-head",
            head[:12],
            "--crontab-text-file",
            str(cron_file),
            "--now-utc",
            "2026-06-22T00:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _active_crontab() -> str:
    return "\n".join(
        [
            "7,37 * * * * OPENCLAW_BASE_DIR=/srv /srv/helper_scripts/cron/demo_learning_evidence_audit_cron.sh",
            "27 * * * * OPENCLAW_BASE_DIR=/srv /srv/helper_scripts/cron/cost_gate_learning_lane_cron.sh",
        ]
    )


def _populate_active_data(data_dir: Path) -> None:
    recent_epoch = 1782086100  # 2026-06-21T23:55:00Z
    _touch(data_dir / "cron_heartbeat/demo_learning_evidence_audit.last_fire", recent_epoch)
    _touch(data_dir / "cron_heartbeat/cost_gate_learning_lane.last_fire", recent_epoch)
    _write(
        data_dir / "logs/demo_learning_evidence_audit.log",
        json.dumps(
            {
                "ts_utc": "2026-06-21T23:56:00Z",
                "classification_status": "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING",
                "audit_rc": 0,
            },
            sort_keys=True,
        )
        + "\n",
    )
    _write(
        data_dir / "logs/cost_gate_learning_lane.log",
        json.dumps(
            {
                "ts_utc": "2026-06-21T23:57:00Z",
                "scorecard_rc": 0,
                "plan_rc": 0,
                "materializer_rc": 0,
                "refresh_rc": 0,
                "review_rc": 0,
                "ledger_row_count": 9,
                "blocked_signal_outcome_count": 4,
                "review_status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
            },
            sort_keys=True,
        )
        + "\n",
    )
    _write(
        data_dir / "demo_learning_evidence/demo_learning_evidence_audit_latest.json",
        json.dumps({"schema_version": "demo_learning_evidence_audit_v1"}),
    )
    _write(
        data_dir / "cost_gate_learning_lane/blocked_outcome_review_latest.json",
        json.dumps(
            {
                "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v2",
                "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
                "blocked_signal_outcome_count": 4,
            }
        ),
    )


def test_missing_crons_are_not_installed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    payload = _run(tmp_path, tmp_path / "data", repo, "", head)

    assert payload["status"] == "NOT_INSTALLED"
    assert payload["answers"]["source_ready"] is True
    assert payload["answers"]["stack_installed"] is False
    assert payload["next_action"] == "install_stack_after_operator_source_reconcile"


def test_active_stack_reports_evidence_active(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    data = tmp_path / "data"
    _populate_active_data(data)

    payload = _run(tmp_path, data, repo, _active_crontab(), head)

    assert payload["status"] == "EVIDENCE_STACK_ACTIVE"
    assert payload["answers"]["stack_installed"] is True
    assert payload["answers"]["heartbeats_recent"] is True
    assert payload["answers"]["cost_gate_learning_ledger_rows_present"] is True
    assert payload["answers"]["blocked_signal_outcomes_present"] is True
    assert payload["components"]["cost_gate_learning_lane"]["latest_status"]["ledger_row_count"] == 9


def test_stale_heartbeat_blocks_active_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    data = tmp_path / "data"
    _populate_active_data(data)
    old_epoch = 1782075600  # 2026-06-21T21:00:00Z
    _touch(data / "cron_heartbeat/cost_gate_learning_lane.last_fire", old_epoch)

    payload = _run(tmp_path, data, repo, _active_crontab(), head)

    assert payload["status"] == "INSTALLED_NOT_FIRING"
    assert payload["answers"]["heartbeats_recent"] is False
    assert payload["components"]["cost_gate_learning_lane"]["heartbeat_recent"] is False


def test_dirty_source_blocks_validation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    _write(repo / "dirty.txt", "dirty\n")
    data = tmp_path / "data"
    _populate_active_data(data)

    payload = _run(tmp_path, data, repo, _active_crontab(), head)

    assert payload["status"] == "SOURCE_NOT_READY"
    assert payload["answers"]["source_ready"] is False
    assert payload["source"]["dirty_path_count"] == 1
