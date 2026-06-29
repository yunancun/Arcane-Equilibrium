from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.learning_serving_snapshot import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    BLOCKED_BY_REGISTRY_STATUS,
    BLOCKED_BY_REPAIR_STATUS,
    BLOCKED_BY_RUNTIME_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_learning_serving_snapshot,
    main,
    render_markdown,
)
from cost_gate_learning_lane.learning_training_registry_repair import (
    NO_REPAIR_REQUIRED_STATUS,
    READY_STATUS as REPAIR_READY_STATUS,
)


NOW = dt.datetime(2026, 6, 29, 14, 30, tzinfo=dt.timezone.utc)


def _repair(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_learning_training_registry_repair_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": NO_REPAIR_REQUIRED_STATUS,
        "repair_items": [],
        "answers": {
            "training_run_performed": False,
            "registry_write_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "serving_snapshot_ready": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _repair_required() -> dict:
    return _repair(
        status=REPAIR_READY_STATUS,
        repair_items=[
            {
                "repair_id": "learning_repair:abc",
                "repair_kind": "MODEL_REGISTRY_REPAIR_REQUIRED",
            }
        ],
    )


def _health(**overrides) -> dict:
    payload = {
        "schema_version": "learning_stack_health_snapshot_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "LEARNING_STACK_READY_FOR_SOURCE_ONLY_REVIEW",
        "snapshot_sha256": "a" * 64,
        "blockers": [],
        "answers": {
            "mutation_enabled": False,
            "order_authority_granted": False,
            "bybit_call_performed": False,
            "pg_write_performed": False,
        },
        "components": {
            "model_registry": {
                "status": "ok",
                "fresh": True,
                "registry_status_ok": True,
                "registry_row_count": 3,
                "shadow_or_canary_row_count": 3,
                "q10_q50_q90_trio_complete": True,
                "artifact_hash_parity_ok": True,
                "feature_schema_hash_present": True,
                "artifact_newer_than_registry": False,
            }
        },
    }
    payload.update(overrides)
    return payload


def _registry(**overrides) -> dict:
    payload = {
        "schema_version": "learning_model_registry_summary_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "ok",
        "latest_registry_row_utc": "2026-06-29T14:00:00Z",
        "registry_row_count": 3,
        "shadow_or_canary_row_count": 3,
        "q10_q50_q90_trio_complete": True,
        "artifact_hash_parity_ok": True,
        "feature_schema_hash": "feature-schema-v1",
        "intended_model_version": "qtrio-20260629T1400Z",
        "artifact_hashes": {
            "q10": "1" * 64,
            "q50": "2" * 64,
            "q90": "3" * 64,
        },
        "serving_intent": {
            "shadow": "qtrio-20260629T1400Z",
            "canary": None,
            "production": None,
        },
        "legacy_artifacts": [
            {
                "path": "/tmp/openclaw/models/old-q50.onnx",
                "sha256": "4" * 64,
                "status": "excluded_from_serving",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _runtime(**overrides) -> dict:
    payload = {
        "schema_version": "learning_runtime_serving_state_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "RUNTIME_SERVING_STATE_READY",
        "loaded_model_version": "qtrio-20260629T1400Z",
        "runtime_feature_schema_hash": "feature-schema-v1",
        "loaded_artifact_hashes": {
            "q10": "1" * 64,
            "q50": "2" * 64,
            "q90": "3" * 64,
        },
        "fallback_mode_active": False,
        "fallback_reason": None,
        "fallback_rule_based_visible": False,
        "ml_inference_active": True,
        "answers": {
            "model_load_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
        },
    }
    payload.update(overrides)
    return payload


def test_blocks_serving_snapshot_when_training_registry_repairs_remain() -> None:
    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair_required(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=_registry(),
        runtime_serving_state=_runtime(),
        now_utc=NOW,
    )

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == BLOCKED_BY_REPAIR_STATUS
    assert packet["serving_snapshot_candidate"] is None
    assert packet["blocked_snapshot"]["repair_blockers"] == [
        "MODEL_REGISTRY_REPAIR_REQUIRED"
    ]
    assert packet["answers"]["model_load_performed"] is False
    assert packet["answers"]["registry_write_performed"] is False


def test_builds_ready_serving_snapshot_candidate_without_authority() -> None:
    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=_registry(),
        runtime_serving_state=_runtime(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == READY_STATUS
    candidate = packet["serving_snapshot_candidate"]
    assert candidate["snapshot_id"].startswith("learning_serving_snapshot:")
    assert candidate["runtime_agreement"] == "runtime_loaded_registry_intent"
    assert candidate["serving_slot_constraints"][
        "production_requires_separate_promotion_gate"
    ] is True
    assert candidate["legacy_artifact_exclusion"][
        "stale_or_legacy_artifacts_excluded_from_serving"
    ] is True
    assert candidate["allowed_actions"]["model_load_allowed_by_this_packet"] is False
    assert packet["answers"]["serving_snapshot_candidate_emitted"] is True
    assert packet["answers"]["serving_snapshot_authority_granted"] is False
    assert "Serving Snapshot" in markdown


def test_visible_runtime_fallback_is_reviewable_without_hidden_ml_inference() -> None:
    runtime = _runtime(
        status="RUNTIME_SERVING_STATE_FALLBACK_VISIBLE",
        loaded_model_version=None,
        loaded_artifact_hashes={},
        runtime_feature_schema_hash=None,
        fallback_mode_active=True,
        fallback_reason="registry_intent_not_loaded_fail_closed",
        fallback_rule_based_visible=True,
        ml_inference_active=False,
    )

    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=_registry(),
        runtime_serving_state=runtime,
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert packet["runtime_gate"]["agreement"] == "explicit_fallback_visible"
    assert packet["serving_snapshot_candidate"]["fallback_mode_active"] is True
    assert packet["answers"]["model_load_allowed_by_this_packet"] is False


def test_registry_or_legacy_artifact_gap_blocks_snapshot() -> None:
    registry = _registry(
        q10_q50_q90_trio_complete=False,
        legacy_artifacts=[
            {
                "path": "/tmp/openclaw/models/orphan-q90.onnx",
                "sha256": "5" * 64,
                "status": "orphan",
            }
        ],
    )

    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=registry,
        runtime_serving_state=_runtime(),
        now_utc=NOW,
    )

    assert packet["status"] == BLOCKED_BY_REGISTRY_STATUS
    assert packet["serving_snapshot_candidate"] is None
    assert "q10_q50_q90_trio_incomplete" in packet["registry_gate"]["blockers"]
    assert any(
        blocker.startswith("legacy_artifact_not_explicitly_excluded_or_current")
        for blocker in packet["registry_gate"]["blockers"]
    )
    assert packet["answers"]["model_load_performed"] is False


def test_visible_fallback_with_active_ml_inference_still_blocks_snapshot() -> None:
    runtime = _runtime(
        status="RUNTIME_SERVING_STATE_FALLBACK_VISIBLE",
        loaded_model_version=None,
        loaded_artifact_hashes={},
        runtime_feature_schema_hash=None,
        fallback_mode_active=True,
        fallback_reason="registry_intent_not_loaded_fail_closed",
        fallback_rule_based_visible=True,
        ml_inference_active=True,
    )

    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=_registry(),
        runtime_serving_state=runtime,
        now_utc=NOW,
    )

    assert packet["status"] == BLOCKED_BY_RUNTIME_STATUS
    assert "runtime_fallback_hides_active_ml_inference" in packet["runtime_gate"][
        "blockers"
    ]
    assert packet["serving_snapshot_candidate"] is None
    assert packet["answers"]["serving_authority_granted"] is False


def test_missing_runtime_state_blocks_but_does_not_load_model() -> None:
    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=_registry(),
        runtime_serving_state=None,
        runtime_serving_state_error="missing_path",
        now_utc=NOW,
    )

    assert packet["status"] == BLOCKED_BY_RUNTIME_STATUS
    assert "runtime_serving_state:missing_path" in packet["runtime_gate"]["blockers"]
    assert packet["answers"]["model_load_performed"] is False
    assert packet["answers"]["runtime_mutation_performed"] is False


def test_fallback_with_hidden_ml_inference_blocks() -> None:
    runtime = _runtime(
        status="RUNTIME_SERVING_STATE_FALLBACK_VISIBLE",
        loaded_model_version=None,
        loaded_artifact_hashes={},
        fallback_mode_active=True,
        fallback_reason="fallback_claimed_but_ml_still_active",
        fallback_rule_based_visible=True,
        ml_inference_active=True,
    )

    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=_registry(),
        runtime_serving_state=runtime,
        now_utc=NOW,
    )

    assert packet["status"] == BLOCKED_BY_RUNTIME_STATUS
    assert "runtime_fallback_hides_active_ml_inference" in packet["runtime_gate"]["blockers"]
    assert packet["serving_snapshot_candidate"] is None


def test_authority_bearing_input_fails_closed() -> None:
    registry = _registry()
    registry["answers"] = {"registry_write_performed": True}

    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=registry,
        runtime_serving_state=_runtime(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["serving_snapshot_candidate"] is None
    assert packet["summary"]["authority_violation_count"] >= 1
    assert packet["answers"]["serving_snapshot_authority_granted"] is False
    assert packet["answers"]["promotion_proof"] is False


def test_allowed_by_this_packet_alias_authority_fails_closed() -> None:
    runtime = _runtime()
    runtime["allowed_actions"] = {"production_slot_write_allowed_by_this_packet": True}

    packet = build_learning_serving_snapshot(
        training_registry_repair_packet=_repair(),
        learning_stack_health_snapshot=_health(),
        model_registry_summary=_registry(),
        runtime_serving_state=runtime,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["serving_snapshot_candidate"] is None
    assert any(
        item["key"] == "production_slot_write_allowed_by_this_packet"
        for item in packet["authority_violations"]
    )


def test_cli_writes_json_output(tmp_path: Path, monkeypatch) -> None:
    repair = tmp_path / "training_registry_repair.json"
    health = tmp_path / "learning_stack_health_snapshot.json"
    registry = tmp_path / "model_registry_summary.json"
    runtime = tmp_path / "runtime_serving_state.json"
    out = tmp_path / "serving_snapshot.json"
    repair.write_text(json.dumps(_repair(), sort_keys=True), encoding="utf-8")
    health.write_text(json.dumps(_health(), sort_keys=True), encoding="utf-8")
    registry.write_text(json.dumps(_registry(), sort_keys=True), encoding="utf-8")
    runtime.write_text(json.dumps(_runtime(), sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "learning_serving_snapshot",
            "--training-registry-repair-json",
            str(repair),
            "--learning-stack-health-snapshot-json",
            str(health),
            "--model-registry-summary-json",
            str(registry),
            "--runtime-serving-state-json",
            str(runtime),
            "--json-output",
            str(out),
            "--print-json",
        ],
    )

    assert main() == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["candidate_emitted"] is True


def test_static_no_network_db_model_load_or_runtime_side_effects() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/learning_serving_snapshot.py"
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
        "onnxruntime",
        "InferenceSession",
        "load_model(",
        "place_order",
        "cancel_order",
        "create_order",
        "crontab -",
        "os.system",
        "systemctl",
    ]
    for needle in forbidden:
        assert needle not in source
