from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "learning_stack_health_snapshot.py"


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    path.write_text(str(text), encoding="utf-8")


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
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "init"],
        check=True,
    )
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _active_crontab() -> str:
    return "\n".join(
        [
            "7,37 * * * * OPENCLAW_BASE_DIR=/srv /srv/helper_scripts/cron/demo_learning_evidence_audit_cron.sh",
            "22 * * * * OPENCLAW_BASE_DIR=/srv /srv/helper_scripts/cron/sealed_horizon_probe_preflight_cron.sh",
            "27 * * * * OPENCLAW_BASE_DIR=/srv /srv/helper_scripts/cron/cost_gate_learning_lane_cron.sh",
            "32 * * * * OPENCLAW_BASE_DIR=/srv /srv/helper_scripts/cron/demo_learning_stack_healthcheck_cron.sh",
            "17 3 * * * OPENCLAW_BASE_DIR=/srv /srv/helper_scripts/cron/ml_training_maintenance_cron.sh",
        ]
    )


def _run(
    tmp_path: Path,
    data_dir: Path,
    repo_root: Path,
    crontab: str,
    head: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    cron_file = tmp_path / "crontab.txt"
    _write(cron_file, crontab)
    return subprocess.run(
        [
            sys.executable,
            str(SNAPSHOT),
            "--data-dir",
            str(data_dir),
            "--repo-root",
            str(repo_root),
            "--expected-head",
            head[:12],
            "--crontab-text-file",
            str(cron_file),
            "--model-artifact-dir",
            str(data_dir / "models"),
            "--now-utc",
            "2026-06-29T12:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=check,
    )


def _populate_ready_data(data: Path) -> None:
    _write(
        data
        / "demo_learning_stack_healthcheck"
        / "demo_learning_stack_healthcheck_latest.json",
        {
            "schema_version": "demo_learning_stack_healthcheck_v1",
            "ts_utc": "2026-06-29T11:40:00Z",
            "status": "EVIDENCE_STACK_ACTIVE",
            "reason": "demo_learning_stack_recent_and_evidence_available",
            "answers": {"stack_installed": True, "heartbeats_recent": True},
        },
    )
    status_payload = {
        "ts_utc": "2026-06-29T11:42:00Z",
        "status": "ok",
        "results": [
            {"job": "linucb_trainer", "status": "ok"},
            {"job": "mlde_shadow_advisor", "status": "ok"},
            {"job": "mlde_demo_applier", "status": "ok"},
            {"job": "scorer_trainer", "status": "skipped"},
            {"job": "quantile_trainer", "status": "ok"},
        ],
    }
    _write(data / "status/ml_training_maintenance_status.json", status_payload)
    _write(
        data / "logs/ml_training_maintenance_status.log",
        json.dumps({"ts_utc": "2026-06-29T08:42:00Z", "status": "ok"})
        + "\n"
        + json.dumps({"ts_utc": "2026-06-29T11:42:00Z", "status": "ok"})
        + "\n",
    )
    model_path = data / "models/q50/model.onnx"
    _write(model_path, "fake-onnx")
    _touch(model_path, 1782731700)  # 2026-06-29T11:15:00Z
    _write(
        data / "learning/model_registry_summary_latest.json",
        {
            "schema_version": "learning_model_registry_summary_v1",
            "generated_at_utc": "2026-06-29T11:50:00Z",
            "status": "ok",
            "latest_registry_row_utc": "2026-06-29T11:30:00Z",
            "registry_row_count": 3,
            "shadow_or_canary_row_count": 3,
            "q10_q50_q90_trio_complete": True,
            "artifact_hash_parity_ok": True,
            "feature_schema_hash": "feature-schema-sha",
        },
    )
    _write(
        data / "learning/artifact_pg_parity_latest.json",
        {
            "schema_version": "learning_artifact_pg_parity_v1",
            "generated_at_utc": "2026-06-29T11:45:00Z",
            "status": "ARTIFACT_PG_PARITY_OK",
            "parity_ok": True,
            "mismatch_count": 0,
        },
    )
    _write(
        data / "learning/proof_summary_latest.json",
        {
            "schema_version": "learning_proof_summary_v1",
            "generated_at_utc": "2026-06-29T11:44:00Z",
            "status": "FILL_BACKED_EVIDENCE_PRESENT",
            "candidate_matched_fill_count": 3,
            "proof_exclusions_clear": True,
        },
    )
    _write(
        data / "cost_gate_learning_lane/probe_ledger.jsonl",
        json.dumps(
            {
                "ts_utc": "2026-06-29T11:43:00Z",
                "candidate": "grid_trading|ETHUSDT|Buy",
                "proof_tier": "fill_backed",
                "candidate_matched_fill_count": 3,
                "allowed_to_submit_order": False,
                "promotion_evidence": False,
            },
            sort_keys=True,
        )
        + "\n",
    )
    _touch(data / "cost_gate_learning_lane/probe_ledger.jsonl", 1782733380)


def test_empty_crontab_and_missing_inputs_degrade_and_disable_mutation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    proc = _run(tmp_path, tmp_path / "data", repo, "", head)
    payload = json.loads(proc.stdout)

    assert payload["status"] == "LEARNING_STACK_DEGRADED"
    assert payload["answers"]["unique_scheduler_authority"] is False
    assert payload["answers"]["mutation_enabled"] is False
    assert payload["answers"]["order_authority_granted"] is False
    assert payload["answers"]["bybit_call_performed"] is False
    assert "scheduler_authority_not_unique_or_missing" in payload["blockers"]
    assert "fill_backed_candidate_evidence_missing" in payload["blockers"]


def test_ready_fixture_builds_single_source_health_gate_without_authority(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    data = tmp_path / "data"
    _populate_ready_data(data)

    proc = _run(tmp_path, data, repo, _active_crontab(), head)
    payload = json.loads(proc.stdout)

    assert payload["status"] == "LEARNING_STACK_READY_FOR_SOURCE_ONLY_REVIEW"
    assert payload["blockers"] == []
    assert payload["answers"]["health_gate_valid_for_demo_mutation"] is True
    assert payload["answers"]["mutation_enabled"] is False
    assert payload["answers"]["demo_mutation_authority_granted"] is False
    assert payload["answers"]["cost_gate_lowering_allowed"] is False
    assert payload["answers"]["pg_write_performed"] is False
    assert payload["components"]["model_registry"]["artifact_newer_than_registry"] is False


def test_ml_maintenance_error_blocks_ready_even_with_active_demo_stack(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    data = tmp_path / "data"
    _populate_ready_data(data)
    _write(
        data / "status/ml_training_maintenance_status.json",
        {
            "ts_utc": "2026-06-29T11:42:00Z",
            "status": "error",
            "results": [{"job": "quantile_trainer", "status": "error"}],
        },
    )

    proc = _run(tmp_path, data, repo, _active_crontab(), head)
    payload = json.loads(proc.stdout)

    assert payload["status"] == "LEARNING_STACK_DEGRADED"
    assert payload["answers"]["ml_training_maintenance_latest_ok"] is False
    assert "ml_training_maintenance_latest_not_ok" in payload["blockers"]


def test_onnx_newer_than_registry_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    data = tmp_path / "data"
    _populate_ready_data(data)
    model_path = data / "models/q50/model.onnx"
    _touch(model_path, 1782734100)  # 2026-06-29T11:55:00Z

    proc = _run(tmp_path, data, repo, _active_crontab(), head)
    payload = json.loads(proc.stdout)

    assert payload["status"] == "LEARNING_STACK_DEGRADED"
    assert payload["answers"]["onnx_newer_than_registry"] is True
    assert "model_registry_not_fresh_or_artifact_parity_failed" in payload["blockers"]


def test_duplicate_scheduler_entries_fail_unique_scheduler(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    data = tmp_path / "data"
    _populate_ready_data(data)
    crontab = _active_crontab() + "\n" + (
        "47 * * * * OPENCLAW_BASE_DIR=/srv "
        "/srv/helper_scripts/cron/cost_gate_learning_lane_cron.sh"
    )

    proc = _run(tmp_path, data, repo, crontab, head)
    payload = json.loads(proc.stdout)

    assert payload["status"] == "LEARNING_STACK_DEGRADED"
    assert payload["cron"]["expected_marker_counts"]["cost_gate_learning_lane"] == 2
    assert payload["answers"]["unique_scheduler_authority"] is False
    assert "scheduler_authority_not_unique_or_missing" in payload["blockers"]


def test_json_output_and_fail_on_degraded_contract(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    output = tmp_path / "snapshot.json"
    cron_file = tmp_path / "crontab.txt"
    _write(cron_file, "")

    proc = subprocess.run(
        [
            sys.executable,
            str(SNAPSHOT),
            "--data-dir",
            str(tmp_path / "data"),
            "--repo-root",
            str(repo),
            "--expected-head",
            head[:12],
            "--crontab-text-file",
            str(cron_file),
            "--json-output",
            str(output),
            "--fail-on-degraded",
            "--now-utc",
            "2026-06-29T12:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    stdout_payload = json.loads(proc.stdout)
    artifact_payload = json.loads(output.read_text(encoding="utf-8"))
    assert artifact_payload == stdout_payload
    assert artifact_payload["status"] == "LEARNING_STACK_DEGRADED"


def test_source_contains_no_effect_capable_io_strings() -> None:
    src = SNAPSHOT.read_text(encoding="utf-8")
    forbidden = [
        "requests.",
        "httpx.",
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE learning",
        "DELETE FROM",
        "place_order",
        "cancel_order",
        "create_order",
        "OPENCLAW_ALLOW_MAINNET=1",
    ]
    for token in forbidden:
        assert token not in src
