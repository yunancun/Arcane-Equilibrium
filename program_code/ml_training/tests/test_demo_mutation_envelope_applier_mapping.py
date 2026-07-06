from __future__ import annotations

import json
from pathlib import Path

from psycopg2.extras import Json  # type: ignore

from ml_training.demo_mutation_envelope import (
    DEMO_MUTATION_ENVELOPE_FIELD,
    STATUS_AUDIT_ONLY,
    STATUS_COUNTABLE,
    STATUS_INVALID,
    stable_sha256_json,
    validate_demo_mutation_envelope,
)
from ml_training.demo_mutation_envelope_applier_mapping import (
    attach_demo_mutation_envelope_to_payload,
    map_record_application_to_demo_mutation_envelope,
)
from ml_training.mlde_demo_applier import _record_application


def _applied_envelope(**overrides):
    args = {
        "row": {
            "id": 17,
            "engine_mode": "demo",
            "source": "ml_shadow",
            "recommendation_type": "rank",
            "strategy_name": "grid_trading",
        },
        "application_type": "strategy_params",
        "target_name": "grid_trading",
        "patch": {"conf_scale": 1.05},
        "prev_snapshot": {"conf_scale": 1.0, "cooldown_ms": 120_000},
        "ipc_response": {
            "status": "applied",
            "request_id": "ipc-1",
            "private_detail": "raw-sensitive-marker",
        },
        "status": "applied",
        "reason": "mlde:ml_shadow:rank",
        "requires_governance": False,
        "payload": {
            "fingerprint": "fp-1",
            "source_payload": {
                "recommendation_id": 17,
                "strategy_name": "grid_trading",
                "symbol": "ETHUSDT",
            },
        },
    }
    args.update(overrides)
    return map_record_application_to_demo_mutation_envelope(**args)


def _explicit_countability_evidence_payload(**overrides):
    payload = {
        "fingerprint": "fp-countability",
        "source_payload": {
            "recommendation_id": 17,
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
        },
        "governance_verdict": {
            "verdict": "approved_for_review",
            "review_allowed": True,
        },
        "rollback_handle": {
            "rollback_id": "rollback-demo-17",
            "available": True,
        },
        "post_change_review": {
            "status": "passed",
            "review_hash": "c" * 64,
        },
        "proof_linkage": {
            "valid": True,
            "proof_packet_hash": "d" * 64,
        },
    }
    payload.update(overrides)
    return payload


def test_applied_demo_row_maps_to_valid_audit_only_envelope_without_review_or_proof():
    envelope = _applied_envelope()

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert validation.effective_learning_countable is False
    assert envelope["application"]["status"] == "applied"
    assert envelope["effective_learning_countable"] is False
    assert envelope["governance_verdict"]["requires_governance"] is False
    assert envelope["governance_verdict"]["review_satisfied"] is False
    assert envelope["rollback_handle"]["source_only_mapping"] is True
    assert envelope["rollback_handle"]["rollback_not_implemented"] is True
    assert envelope["rollback_handle"]["snapshot_hash"] == stable_sha256_json(
        {"conf_scale": 1.0, "cooldown_ms": 120_000}
    )
    assert envelope["ipc_response_hash"] == stable_sha256_json(
        {
            "status": "applied",
            "request_id": "ipc-1",
            "private_detail": "raw-sensitive-marker",
        }
    )
    assert "ipc_response" not in envelope
    assert "raw-sensitive-marker" not in json.dumps(envelope, sort_keys=True)
    assert "post_change_review_not_passed" in validation.reasons
    assert "proof_linkage_not_valid" in validation.reasons


def test_mapping_default_none_bound_requires_explicit_countability_bound():
    envelope = _applied_envelope(payload=_explicit_countability_evidence_payload())

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert validation.effective_learning_countable is False
    assert envelope["max_delta_policy"]["max_delta_pct"] is None
    assert "bounded_delta[0]_max_delta_policy_not_concrete" in validation.reasons


def test_mapping_with_explicit_concrete_bound_and_evidence_can_count():
    envelope = _applied_envelope(
        payload=_explicit_countability_evidence_payload(
            max_delta_policy={
                "policy_id": "demo_mutation_max_delta_policy_v1",
                "max_delta_pct": 0.10,
            }
        )
    )

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_COUNTABLE
    assert validation.effective_learning_countable is True


def test_dry_run_and_dedupe_rows_map_to_valid_audit_only_envelopes():
    dry_run = _applied_envelope(
        ipc_response={"dry_run": True},
        status="dry_run",
        reason="dry_run",
    )
    dedupe = _applied_envelope(
        patch={"conf_scale": 1.05},
        ipc_response={},
        status="skipped",
        reason="dedupe",
        payload={"fingerprint": "fp-dedupe"},
    )

    for envelope in (dry_run, dedupe):
        validation = validate_demo_mutation_envelope(envelope)
        assert validation.valid is True
        assert validation.status == STATUS_AUDIT_ONLY
        assert validation.effective_learning_countable is False

    assert dry_run["application"]["dry_run"] is True
    assert dedupe["application"]["dedupe"] is True


def test_skipped_noop_row_maps_to_valid_audit_only_envelope():
    envelope = map_record_application_to_demo_mutation_envelope(
        row={"engine_mode": "demo", "id": None},
        application_type="strategy_params",
        target_name="mlde_demo_applier",
        patch={},
        prev_snapshot={},
        ipc_response={},
        status="skipped",
        reason="no_eligible_recommendations",
        requires_governance=False,
        payload={"reason": "no_eligible_recommendations", "fingerprint": "fp-noop"},
    )

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert validation.effective_learning_countable is False
    assert envelope["source_proposal_or_recommendation_id"].startswith("audit:")


def test_non_demo_and_live_candidate_rows_cannot_count_or_create_false_authority():
    live_candidate = _applied_envelope(
        row={"id": 17, "engine_mode": "live", "strategy_name": "grid_trading"},
        application_type="live_promotion_candidate",
        status="candidate",
        reason="positive_demo_evidence_governed_live_candidate",
        requires_governance=True,
        payload={"policy": "live_governed_promotion_candidate"},
    )
    live_demo = _applied_envelope(row={"id": 18, "engine_mode": "live_demo"})
    paper = _applied_envelope(row={"id": 19, "engine_mode": "paper"})

    for envelope in (live_candidate, live_demo, paper):
        validation = validate_demo_mutation_envelope(envelope)
        assert validation.valid is False
        assert validation.status == STATUS_INVALID
        assert validation.effective_learning_countable is False
        assert validation.reason.startswith("non_demo_scope:")
        assert envelope["answers"]["order_authority_granted"] is False
        assert envelope["answers"]["live_authority_granted"] is False
        assert envelope["answers"]["runtime_mutation_allowed"] is False


def test_attach_helper_preserves_caller_payload_fields():
    payload = {"fingerprint": "fp-2", "caller_field": {"keep": True}}

    out = attach_demo_mutation_envelope_to_payload(
        row={"id": 22, "engine_mode": "demo"},
        application_type="strategy_params",
        target_name="grid_trading",
        patch={"conf_scale": 1.02},
        prev_snapshot={"conf_scale": 1.0},
        ipc_response={"ok": True},
        status="applied",
        reason="mlde:ml_shadow:rank",
        requires_governance=False,
        payload=payload,
    )

    assert out is not payload
    assert out["fingerprint"] == "fp-2"
    assert out["caller_field"] == {"keep": True}
    validation = validate_demo_mutation_envelope(out[DEMO_MUTATION_ENVELOPE_FIELD])
    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY


def test_record_application_attaches_envelope_without_changing_sql_params_shape():
    captured: dict[str, object] = {}

    class _CaptureCursor:
        def execute(self, sql, params=()):
            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self):
            return (4242,)

    patch = {"conf_scale": 1.05}
    prev_snapshot = {"conf_scale": 1.0}
    ipc_response = {"status": "applied", "private_detail": "raw-sensitive-marker"}
    caller_payload = {"fingerprint": "fp-3", "source_payload": {"symbol": "ETHUSDT"}}

    new_id = _record_application(
        _CaptureCursor(),
        row={"id": 33, "engine_mode": "demo", "strategy_name": "grid_trading"},
        application_type="strategy_params",
        target_name="grid_trading",
        patch=patch,
        prev_snapshot=prev_snapshot,
        ipc_response=ipc_response,
        status="applied",
        reason="mlde:ml_shadow:rank",
        requires_governance=False,
        payload=caller_payload,
    )

    assert new_id == 4242
    sql = str(captured["sql"])
    params = captured["params"]
    assert "INSERT INTO learning.mlde_param_applications" in sql
    assert len(params) == 11
    assert params[:4] == (
        "demo",
        33,
        "strategy_params",
        "grid_trading",
    )
    assert params[7:10] == ("applied", "mlde:ml_shadow:rank", False)
    assert isinstance(params[4], Json)
    assert isinstance(params[5], Json)
    assert isinstance(params[6], Json)
    assert isinstance(params[10], Json)
    assert params[4].adapted == patch
    assert params[5].adapted == prev_snapshot
    assert params[6].adapted == ipc_response

    written_payload = params[10].adapted
    assert written_payload["fingerprint"] == "fp-3"
    assert written_payload["source_payload"] == {"symbol": "ETHUSDT"}
    envelope = written_payload[DEMO_MUTATION_ENVELOPE_FIELD]
    validation = validate_demo_mutation_envelope(envelope)
    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert envelope["source_proposal_or_recommendation_id"] == "33"
    assert envelope["ipc_response_hash"] == stable_sha256_json(ipc_response)
    assert "raw-sensitive-marker" not in json.dumps(envelope, sort_keys=True)


def test_mapping_helper_has_no_runtime_or_persistence_side_effect_surface():
    source = Path(
        "program_code/ml_training/demo_mutation_envelope_applier_mapping.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg2",
        "asyncpg",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "one_shot_ipc_call",
        "ipc_dispatch",
        "place_order",
        "create_order",
        "cancel_order",
        "submit_order",
        "INSERT INTO",
        "UPDATE learning",
        "DELETE FROM",
        "os.environ",
        "getenv",
    ]
    for needle in forbidden:
        assert needle not in source
