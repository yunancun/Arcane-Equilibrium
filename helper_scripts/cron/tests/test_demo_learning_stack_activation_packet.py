from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

PACKET = (
    Path(__file__).resolve().parents[1] / "demo_learning_stack_activation_packet.py"
)

REQUIRED_SOURCE_RELATIVE_PATHS = (
    "helper_scripts/cron/cost_gate_learning_lane_cron.sh",
    "helper_scripts/cron/install_cost_gate_learning_lane_cron.sh",
    "helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py",
    "helper_scripts/research/cost_gate_learning_lane/reject_materializer.py",
    "helper_scripts/research/cost_gate_learning_lane/outcome_refresh.py",
    "helper_scripts/research/cost_gate_learning_lane/outcome_review.py",
    "helper_scripts/research/cost_gate_learning_lane/historical_review.py",
    "helper_scripts/research/cost_gate_learning_lane/status.py",
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
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "a@b.c"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "test"],
        check=True,
    )
    for rel in REQUIRED_SOURCE_RELATIVE_PATHS:
        full = path / rel
        if full.suffix == ".sh":
            _write(full, "#!/usr/bin/env bash\nexit 0\n")
            full.chmod(full.stat().st_mode | stat.S_IXUSR)
        else:
            _write(full, "# fixture\n")
    _write(path / "README.md", "fixture\n")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)
    origin = path.parent / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", str(origin)],
        check=True,
    )
    branch = subprocess.check_output(
        ["git", "-C", str(path), "branch", "--show-current"],
        text=True,
    ).strip()
    subprocess.run(
        ["git", "-C", str(path), "push", "-q", "-u", "origin", branch],
        check=True,
    )
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _active_crontab() -> str:
    return "\n".join(
        [
            "7,37 * * * * OPENCLAW_BASE_DIR=/srv "
            "/srv/helper_scripts/cron/demo_learning_evidence_audit_cron.sh",
            "22 * * * * OPENCLAW_BASE_DIR=/srv "
            "/srv/helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh",
            "27 * * * * OPENCLAW_BASE_DIR=/srv "
            "/srv/helper_scripts/cron/cost_gate_learning_lane_cron.sh",
            "32 * * * * OPENCLAW_BASE_DIR=/srv "
            "/srv/helper_scripts/cron/demo_learning_stack_healthcheck_cron.sh",
        ]
    )


def _populate_active_data(data_dir: Path) -> None:
    recent_epoch = 1782086100  # 2026-06-21T23:55:00Z
    _touch(
        data_dir / "cron_heartbeat/demo_learning_evidence_audit.last_fire",
        recent_epoch,
    )
    _touch(
        data_dir / "cron_heartbeat/sealed_horizon_probe_preflight.last_fire",
        recent_epoch,
    )
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
        data_dir / "logs/sealed_horizon_probe_preflight.log",
        json.dumps(
            {
                "ts_utc": "2026-06-21T23:56:30Z",
                "rc": 0,
                "status": "OPERATOR_REVIEW_REQUIRED",
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
                "bounded_probe_result_review_rc": 0,
                "bounded_probe_execution_realism_review_rc": 0,
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
    _write(
        data_dir / "cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json",
        json.dumps(
            {
                "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
                "generated_at_utc": "2026-06-21T23:57:00Z",
                "status": "OPERATOR_REVIEW_REQUIRED",
            }
        ),
    )
    _write(
        data_dir / "cost_gate_learning_lane/bounded_probe_result_review_latest.json",
        json.dumps(
            {
                "schema_version": "bounded_demo_probe_result_review_v1",
                "generated_at_utc": "2026-06-21T23:57:30Z",
                "status": "NO_PROBE_OUTCOMES_RECORDED",
            }
        ),
    )
    _write(
        data_dir
        / "cost_gate_learning_lane/bounded_probe_execution_realism_review_latest.json",
        json.dumps(
            {
                "schema_version": "bounded_demo_probe_execution_realism_review_v1",
                "generated_at_utc": "2026-06-21T23:57:45Z",
                "status": "NO_EXECUTION_REALISM_GAP_TO_REVIEW",
            }
        ),
    )


def _run(tmp_path: Path, data_dir: Path, repo_root: Path, crontab: str, head: str):
    cron_file = tmp_path / "crontab.txt"
    _write(cron_file, crontab)
    proc = subprocess.run(
        [
            sys.executable,
            str(PACKET),
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


def test_missing_stack_crons_emit_operator_dry_run_packet(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    payload = _run(tmp_path, tmp_path / "data", repo, "", head)

    assert payload["schema_version"] == "demo_learning_stack_activation_packet_v1"
    assert payload["status"] == "READY_FOR_OPERATOR_DRY_RUN"
    assert payload["install_review_ready"] is True
    assert payload["answers"]["missing_cron_count"] == 4
    assert payload["answers"]["global_cost_gate_lowering_recommended"] is False
    assert payload["answers"]["order_authority_granted"] is False
    assert payload["answers"]["probe_authority_granted"] is False
    assert (
        payload["operator_commands"]["dry_run_preview"]["mutates_crontab"] is False
    )
    assert payload["operator_commands"]["operator_only_apply"][
        "requires_operator_approval"
    ] is True


def test_dirty_source_fails_closed_before_install_review(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    _write(repo / "dirty.txt", "dirty\n")

    payload = _run(tmp_path, tmp_path / "data", repo, "", head)

    assert payload["status"] == "SOURCE_NOT_READY"
    assert payload["install_review_ready"] is False
    assert "runtime_source_clean_expected_head" in payload["missing_links"]


def test_active_stack_packet_does_not_recommend_reinstall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    data = tmp_path / "data"
    _populate_active_data(data)

    payload = _run(tmp_path, data, repo, _active_crontab(), head)

    assert payload["status"] == "STACK_ALREADY_ACTIVE"
    assert payload["install_review_ready"] is False
    assert payload["answers"]["stack_installed"] is True
    assert payload["answers"]["missing_cron_count"] == 0
    assert payload["planned_stack"]["cron_count"] == 4
