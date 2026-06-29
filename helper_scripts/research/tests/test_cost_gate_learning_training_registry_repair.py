from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.learning_training_registry_repair import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    NO_REPAIR_REQUIRED_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_learning_training_registry_repair,
    main,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 29, 13, 15, tzinfo=dt.timezone.utc)


def _snapshot(**overrides) -> dict:
    payload = {
        "schema_version": "learning_stack_health_snapshot_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "LEARNING_STACK_DEGRADED",
        "snapshot_sha256": "a" * 64,
        "blockers": [
            "ml_training_maintenance_latest_not_ok",
            "ml_training_maintenance_last_two_cycles_not_ok",
            "model_registry_not_fresh_or_artifact_parity_failed",
            "artifact_pg_parity_not_ok",
        ],
        "answers": {
            "mutation_enabled": False,
            "demo_mutation_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "cost_gate_lowering_allowed": False,
            "bybit_call_performed": False,
            "pg_write_performed": False,
        },
        "components": {
            "ml_training_maintenance": {
                "path": "/tmp/openclaw/status/ml_training_maintenance_status.json",
                "status": "error",
                "fresh": True,
                "latest_ok": False,
                "last_two_cycles_ok": False,
                "job_statuses": {"quantile_trainer": "error"},
                "history_error": None,
            },
            "model_registry": {
                "path": "/tmp/openclaw/status/model_registry_summary.json",
                "read_error": None,
                "status": "stale",
                "fresh": False,
                "registry_status_ok": False,
                "registry_row_count": 0,
                "shadow_or_canary_row_count": 0,
                "q10_q50_q90_trio_complete": False,
                "artifact_hash_parity_ok": False,
                "feature_schema_hash_present": False,
                "artifact_newer_than_registry": True,
                "latest_registry_row_utc": "2026-06-28T00:00:00Z",
                "artifact_inventory": {
                    "artifact_count": 3,
                    "newest_artifact_mtime_utc": "2026-06-29T12:00:00Z",
                },
            },
            "artifact_pg_parity": {
                "path": "/tmp/openclaw/status/artifact_pg_parity.json",
                "status": "mismatch",
                "fresh": True,
                "parity_ok": False,
                "mismatch_count": 2,
                "read_error": None,
            },
        },
    }
    payload.update(overrides)
    return payload


def test_builds_training_registry_repair_packet_from_degraded_snapshot() -> None:
    packet = build_learning_training_registry_repair(
        learning_stack_health_snapshot=_snapshot(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    kinds = {item["repair_kind"] for item in packet["repair_items"]}
    assert "ML_TRAINING_MAINTENANCE_REPAIR_REQUIRED" in kinds
    assert "MODEL_REGISTRY_REPAIR_REQUIRED" in kinds
    assert "ARTIFACT_PARITY_REPAIR_REQUIRED" in kinds
    assert "LEGACY_MODEL_ARTIFACT_RETIREMENT_REVIEW_REQUIRED" in kinds
    assert packet["answers"]["training_run_performed"] is False
    assert packet["answers"]["registry_write_performed"] is False
    assert packet["answers"]["pg_write_performed"] is False
    assert packet["repair_items"][0]["budget_backpressure_gates"][
        "separate_runtime_apply_gate_required"
    ] is True
    assert "Training/Registry Repair" in markdown


def test_ready_snapshot_has_no_repair_but_grants_no_authority() -> None:
    ready = _snapshot(
        status="LEARNING_STACK_READY_FOR_SOURCE_ONLY_REVIEW",
        blockers=[],
        components={
            "ml_training_maintenance": {
                "fresh": True,
                "latest_ok": True,
                "last_two_cycles_ok": True,
            },
            "model_registry": {
                "read_error": None,
                "registry_status_ok": True,
                "fresh": True,
                "registry_row_count": 3,
                "shadow_or_canary_row_count": 3,
                "q10_q50_q90_trio_complete": True,
                "artifact_hash_parity_ok": True,
                "feature_schema_hash_present": True,
                "artifact_newer_than_registry": False,
                "artifact_inventory": {"artifact_count": 3},
            },
            "artifact_pg_parity": {"fresh": True, "parity_ok": True},
        },
    )

    packet = build_learning_training_registry_repair(
        learning_stack_health_snapshot=ready,
        now_utc=NOW,
    )

    assert packet["status"] == NO_REPAIR_REQUIRED_STATUS
    assert packet["repair_items"] == []
    assert packet["answers"]["training_registry_repair_packet_ready"] is True
    assert packet["answers"]["serving_snapshot_ready"] is False
    assert packet["answers"]["promotion_proof"] is False


def test_authority_bearing_snapshot_fails_closed() -> None:
    snapshot = _snapshot()
    snapshot["answers"]["pg_write_performed"] = True

    packet = build_learning_training_registry_repair(
        learning_stack_health_snapshot=snapshot,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["repair_items"] == []
    assert packet["summary"]["authority_violation_count"] >= 1
    assert packet["answers"]["registry_write_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    snapshot_path = tmp_path / "learning_stack_health_snapshot.json"
    out = tmp_path / "training_registry_repair.json"
    snapshot_path.write_text(json.dumps(_snapshot(), sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_training_registry_repair",
            "--learning-stack-health-snapshot-json",
            str(snapshot_path),
            "--json-output",
            str(out),
            "--print-json",
        ],
    )

    assert main() == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["registry_repair_required"] is True


def test_static_no_network_db_training_or_runtime_side_effects() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/learning_training_registry_repair.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "requests.",
        "httpx.",
        "urllib.",
        "psycopg",
        "asyncpg",
        "INSERT INTO",
        "UPDATE learning",
        "DELETE FROM",
        "subprocess",
        "run_pipeline(",
        "register_model(",
        "export_quantile",
        "place_order",
        "cancel_order",
        "create_order",
        "crontab -",
        "os.system",
    ]
    for needle in forbidden:
        assert needle not in source
