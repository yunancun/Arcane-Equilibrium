from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "helper_scripts/maintenance_scripts/agent_governance.py"
CONSUMPTION = ROOT / "helper_scripts/maintenance_scripts/agent_governance_consumption.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _baseline() -> dict:
    return {
        "source_head": "a" * 40,
        "dirty_diff_hash": "sha256:" + "b" * 64,
        "untracked_relevant_hash": "sha256:" + "c" * 64,
        "runtime_head": "d" * 40,
        "runtime_observed_at": "2026-07-10T12:00:00Z",
    }


def test_authority_claims_are_self_bound_fresh_and_conflict_aware() -> None:
    governance = _load(FACADE, "agent_governance_truth_authority")
    normative = governance.build_authority_claim(
        authority_class="normative_policy",
        subject="deploy.mainnet_allowed",
        value=False,
        source="CLAUDE.md#Hard Boundaries",
        source_ref="ev-normative-source",
        source_digest="sha256:" + "1" * 64,
        observed_at="2026-07-10T10:00:00Z",
        scope="deploy:trade-core",
        strength="direct",
        expiry=None,
    )
    assert governance.resolve_authority_claims(
        [normative], adjudicated_at="2026-07-10T12:00:00Z"
    )["gate_verdict"] == "PASS"

    runtime = governance.build_authority_claim(
        authority_class="runtime_observation",
        subject="deploy.mainnet_allowed",
        value=True,
        source="runtime-attestation",
        source_ref="ev-runtime-attestation",
        source_digest="sha256:" + "2" * 64,
        observed_at="2026-07-10T11:55:00Z",
        scope="deploy:trade-core",
        strength="direct",
        expiry="2026-07-10T12:10:00Z",
    )
    decision = governance.resolve_authority_claims(
        [normative, runtime], adjudicated_at="2026-07-10T12:00:00Z"
    )
    assert decision["status"] == "CONFLICT"
    assert decision["gate_verdict"] == "BLOCKED"

    tampered = deepcopy(normative)
    tampered["value"] = True
    assert governance.resolve_authority_claims(
        [tampered], adjudicated_at="2026-07-10T12:00:00Z"
    )["status"] == "INVALID"

    expired = deepcopy(runtime)
    expired["expiry"] = "2026-07-10T11:30:00Z"
    expired["claim_digest"] = governance.authority_claim_digest(expired)
    assert governance.resolve_authority_claims(
        [expired], adjudicated_at="2026-07-10T12:00:00Z"
    )["status"] == "INVALID"


def test_typed_observation_receipts_bind_baseline_result_and_wrapper() -> None:
    governance = _load(FACADE, "agent_governance_truth_observations")
    baseline = _baseline()
    source = governance.build_source_review_receipt(
        producer_role="E2",
        command="git diff -- helper_scripts",
        baseline=baseline,
        criteria=["governance remains fail-closed"],
        observed_at="2026-07-10T12:02:00Z",
        exit_code=0,
        stdout=b"reviewed",
        stderr=b"",
    )
    evidence = {
        "id": "ev-source",
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": source["receipt_digest"],
        "observed_at": source["observed_at"],
        "artifact": source,
    }
    errors, artifact = governance.validate_observation_evidence(
        evidence,
        expected_baseline=baseline,
        adjudicated_at="2026-07-10T12:05:00Z",
        task_baseline=baseline,
    )
    assert errors == []
    assert artifact == source

    fake_success = deepcopy(evidence)
    fake_success["artifact"]["exit_code"] = 7
    fake_success["artifact"]["status"] = "PASS"
    assert governance.validate_observation_evidence(
        fake_success,
        expected_baseline=baseline,
        adjudicated_at="2026-07-10T12:05:00Z",
        task_baseline=baseline,
    )[0]

    runtime = governance.build_runtime_observation_receipt(
        producer_role="OPS",
        probe_kind="service_health",
        command="ssh trade-core systemctl --user is-active openclaw-engine.service",
        baseline=baseline,
        runtime_head=baseline["runtime_head"],
        host="trade-core",
        environment="demo",
        observed_at="2026-07-10T12:02:00Z",
        expiry="2026-07-10T12:17:00Z",
        exit_code=0,
        facts={"active": True},
        stdout=b"active\n",
        stderr=b"",
    )
    runtime_evidence = {
        "id": "ev-runtime",
        "scope": "runtime",
        "kind": "runtime_observation_receipt_v1",
        "digest": runtime["receipt_digest"],
        "host": runtime["host"],
        "environment": runtime["environment"],
        "observed_at": runtime["observed_at"],
        "expiry": runtime["expiry"],
        "artifact": runtime,
    }
    assert governance.validate_observation_evidence(
        runtime_evidence,
        expected_baseline=baseline,
        adjudicated_at="2026-07-10T12:05:00Z",
        task_baseline=baseline,
    )[0] == []


def test_consumption_status_requires_telemetry_and_reconciles_fragments() -> None:
    governance = _load(FACADE, "agent_governance_truth_consumption_facade")
    consumption = _load(CONSUMPTION, "agent_governance_truth_consumption")
    route = governance.route_task(
        {
            "task_shape": "review",
                "surfaces": ["hard_boundary"],
                "risk": "low",
                "uncertainty": "low",
                "side_effect_class": "none",
                "task_prompt": "verify consumption receipt reconciliation",
            }
    )
    fragment_metrics = {
        "measurement_status": "measured",
        "measurement_source": "platform_telemetry",
        "telemetry_digest": "sha256:" + "4" * 64,
        "telemetry_ref": "telemetry-measured",
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 2,
        "tool_calls": 1,
        "retry_count": 0,
        "wall_time_ms": 50,
        "rework_count": 0,
    }
    packet = {
        "consumption": {
            "measurement_status": "measured",
            "measurement_source": "platform_telemetry",
            "telemetry_digest": "sha256:" + "4" * 64,
            "telemetry_ref": "telemetry-measured",
            "planned_tokens": 3000,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 2,
            "tool_calls": 1,
            "retry_count": 0,
            "fan_out": 1,
            "wall_time_ms": 50,
            "accepted_findings": 0,
            "rework_count": 0,
            "quality_reserve_used": False,
        }
    }
    fragments = [{"consumption": fragment_metrics}]
    capture_index = {
        "platform_attested": {"telemetry-measured"},
        "telemetry": {
            "telemetry-measured": {
                "record_digest": "sha256:" + "4" * 64,
                "body": {
                    "subject_call_ids": ["call-measured"],
                    "metrics": {
                        field: fragment_metrics[field]
                        for field in (
                            "input_tokens", "output_tokens", "cache_read_tokens",
                            "tool_calls", "retry_count", "wall_time_ms", "rework_count",
                        )
                    }
                },
            }
        },
    }
    assert consumption.validate_consumption_binding(
        packet, fragments, route, capture_index
    ) == []

    empty_measured = deepcopy(packet)
    empty_measured["consumption"] = {"measurement_status": "measured"}
    assert consumption.validate_consumption_binding(
        empty_measured, fragments, route, capture_index
    )

    hidden_fragment_tokens = deepcopy(packet)
    hidden_fragment_tokens["consumption"]["input_tokens"] = 0
    assert any(
        "does not equal fragment sum" in error
        for error in consumption.validate_consumption_binding(
            hidden_fragment_tokens, fragments, route, capture_index
        )
    )
