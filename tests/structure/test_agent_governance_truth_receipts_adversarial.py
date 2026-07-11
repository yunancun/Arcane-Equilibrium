from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_DIR = ROOT / "helper_scripts/maintenance_scripts"
if str(IMPLEMENTATION_DIR) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION_DIR))


def _load(name: str):
    path = IMPLEMENTATION_DIR / f"agent_governance_{name}.py"
    spec = importlib.util.spec_from_file_location(f"truth_receipt_{name}", path)
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
        "runtime_observed_at": "2026-07-11T10:00:00Z",
    }


def _measured_role_consumption(digest_char: str) -> dict:
    return {
        "measurement_status": "measured",
        "measurement_source": "platform_telemetry",
        "telemetry_digest": "sha256:" + digest_char * 64,
        "telemetry_ref": f"telemetry-{digest_char}",
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 10,
        "tool_calls": 2,
        "retry_count": 0,
        "wall_time_ms": 500,
        "rework_count": 0,
    }


def _measured_closure_consumption(digest_char: str, fan_out: int = 1) -> dict:
    return {
        "measurement_status": "measured",
        "measurement_source": "platform_telemetry",
        "telemetry_digest": "sha256:" + digest_char * 64,
        "telemetry_ref": f"telemetry-{digest_char}",
        "planned_tokens": 3000,
        "input_tokens": 100 * fan_out,
        "output_tokens": 20 * fan_out,
        "cache_read_tokens": 10 * fan_out,
        "tool_calls": 2 * fan_out,
        "retry_count": 0,
        "fan_out": fan_out,
        "wall_time_ms": 500,
        "accepted_findings": 0,
        "rework_count": 0,
        "quality_reserve_used": False,
    }


def test_cross_class_json_values_must_not_align_via_python_bool_integer_equality() -> None:
    authority = _load("authority")
    normative = authority.build_authority_claim(
        authority_class="normative_policy",
        subject="deploy.mainnet_allowed",
        value=False,
        source="CLAUDE.md#Hard Boundaries",
        source_ref="ev-normative-source",
        source_digest="sha256:" + "1" * 64,
        observed_at="2026-07-11T10:00:00Z",
        scope="deploy:trade-core",
        strength="direct",
        expiry=None,
    )
    runtime = authority.build_authority_claim(
        authority_class="runtime_observation",
        subject="deploy.mainnet_allowed",
        value=0,
        source="runtime-attestation",
        source_ref="ev-runtime-attestation",
        source_digest="sha256:" + "2" * 64,
        observed_at="2026-07-11T10:01:00Z",
        scope="deploy:trade-core",
        strength="direct",
        expiry="2026-07-11T10:10:00Z",
    )

    decision = authority.resolve_authority_claims(
        [normative, runtime], adjudicated_at="2026-07-11T10:02:00Z"
    )

    assert decision["status"] == "CONFLICT"
    assert decision["gate_verdict"] == "BLOCKED"


def test_ephemeral_authority_cannot_use_an_unbounded_freshness_window() -> None:
    authority = _load("authority")
    runtime = authority.build_authority_claim(
        authority_class="runtime_observation",
        subject="service.active",
        value=True,
        source="runtime-attestation",
        source_ref="ev-runtime-attestation",
        source_digest="sha256:" + "3" * 64,
        observed_at="2026-07-11T10:00:00Z",
        scope="runtime:trade-core",
        strength="direct",
        expiry="2026-07-11T11:00:00Z",
    )

    decision = authority.resolve_authority_claims(
        [runtime], adjudicated_at="2026-07-11T10:05:00Z"
    )

    assert decision["status"] == "INVALID"
    assert decision["gate_verdict"] == "BLOCKED"


def test_observation_validator_rejects_non_object_evidence_without_crashing() -> None:
    observations = _load("observations")

    errors, artifact = observations.validate_observation_evidence(
        None,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert errors == ["typed observation evidence must be an object"]
    assert artifact is None


def test_non_canonical_observation_payload_fails_closed_instead_of_crashing() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E2",
        command="review governed change",
        baseline=_baseline(),
        criteria=["change remains fail-closed"],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=0,
        stdout=b"reviewed",
        stderr=b"",
    )
    receipt["criteria"] = [float("nan")]
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert any("canonical JSON" in error for error in errors)
    assert artifact is None


def test_source_review_cannot_pass_without_a_bound_acceptance_criterion() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E2",
        command="review governed change",
        baseline=_baseline(),
        criteria=[],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=0,
        stdout=b"reviewed",
        stderr=b"",
    )
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "source review receipt criteria are invalid" in errors
    assert artifact is None


def test_runtime_observation_cannot_claim_an_hour_long_freshness_window() -> None:
    observations = _load("observations")
    receipt = observations.build_runtime_observation_receipt(
        producer_role="OPS",
        probe_kind="service_health",
        command="observe local runtime",
        baseline=_baseline(),
        runtime_head="d" * 40,
        host="trade-core",
        environment="demo",
        observed_at="2026-07-11T10:00:00Z",
        expiry="2026-07-11T11:00:00Z",
        exit_code=0,
        facts={"active": True},
        stdout=b"active\n",
        stderr=b"",
    )
    evidence = {
        "scope": "runtime",
        "kind": "runtime_observation_receipt_v1",
        "digest": receipt["receipt_digest"],
        "host": receipt["host"],
        "environment": receipt["environment"],
        "observed_at": receipt["observed_at"],
        "expiry": receipt["expiry"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "runtime observation freshness window exceeds fifteen minutes" in errors
    assert artifact is None


def test_write_capable_role_cannot_self_issue_an_independent_source_review() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E4",
        command="review the tests E4 just changed",
        baseline=_baseline(),
        criteria=["tests independently prove behavior"],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=0,
        stdout=b"looks good",
        stderr=b"",
    )
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "source review receipt producer must be read-only" in errors
    assert artifact is None


def test_orchestrator_cannot_self_issue_a_source_change_receipt() -> None:
    observations = _load("observations")
    after = {**_baseline(), "dirty_diff_hash": "sha256:" + "e" * 64}
    receipt = observations.build_source_change_receipt(
        producer_role="PM",
        before_baseline=_baseline(),
        after_baseline=after,
        changed_paths=["helper_scripts/example.py"],
        patch_digest="sha256:" + "f" * 64,
        observed_at="2026-07-11T10:02:00Z",
    )
    evidence = {
        "scope": "source",
        "kind": "source_change_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=after,
        task_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "source change receipt producer cannot own writes" in errors
    assert artifact is None


def test_non_hashable_partial_missing_metrics_fail_closed_without_crashing() -> None:
    consumption = _load("consumption")
    packet = {
        "consumption": {
            "measurement_status": "partial",
            "measurement_source": "orchestrator_receipt",
            "telemetry_digest": "sha256:" + "1" * 64,
            "input_tokens": 10,
            "missing_metrics": [["output_tokens"]],
            "unavailable_reason": "provider omitted fields",
        }
    }

    errors = consumption.validate_consumption_binding(packet, [], None)

    assert "closure partial consumption missing_metrics is inconsistent" in errors


def test_consumption_binding_rejects_non_object_packet_and_fragments() -> None:
    consumption = _load("consumption")

    errors = consumption.validate_consumption_binding(None, [None], None)

    assert "closure packet must be an object" in errors
    assert "role_fragments[0] must be an object" in errors


def test_partial_closure_cannot_hide_metrics_already_known_from_fragments() -> None:
    consumption = _load("consumption")
    fragment = {"consumption": _measured_role_consumption("2")}
    packet = {
        "consumption": {
            "measurement_status": "partial",
            "measurement_source": "orchestrator_receipt",
            "telemetry_digest": "sha256:" + "3" * 64,
            "planned_tokens": 3000,
            "fan_out": 1,
            "accepted_findings": 0,
            "quality_reserve_used": False,
            "missing_metrics": [
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "tool_calls",
                "retry_count",
                "wall_time_ms",
                "rework_count",
            ],
            "unavailable_reason": "orchestrator omitted role totals",
        }
    }

    errors = consumption.validate_consumption_binding(packet, [fragment], None)

    assert any("hides known fragment metrics" in error for error in errors)


def test_same_fragment_telemetry_receipt_cannot_be_counted_twice() -> None:
    consumption = _load("consumption")
    packet = {"consumption": _measured_closure_consumption("4", fan_out=2)}
    duplicate = _measured_role_consumption("5")
    fragments = [{"consumption": duplicate}, {"consumption": dict(duplicate)}]

    errors = consumption.validate_consumption_binding(packet, fragments, None)

    assert "fragment telemetry refs must be unique" in errors


def test_partial_planned_tokens_require_an_explicit_quality_reserve_decision() -> None:
    consumption = _load("consumption")
    packet = {
        "consumption": {
            "measurement_status": "partial",
            "measurement_source": "orchestrator_receipt",
            "telemetry_digest": "sha256:" + "6" * 64,
            "planned_tokens": 3000,
            "missing_metrics": [
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "tool_calls",
                "retry_count",
                "fan_out",
                "wall_time_ms",
                "accepted_findings",
                "rework_count",
            ],
            "unavailable_reason": "only planning telemetry was emitted",
        }
    }

    errors = consumption.validate_consumption_binding(packet, [], None)

    assert "closure consumption planned_tokens requires quality_reserve_used" in errors


def test_orchestrator_quality_metrics_must_be_recomputed_from_bound_fragments() -> None:
    consumption = _load("consumption")
    packet = {
        "consumption": {
            "measurement_status": "partial",
            "measurement_source": "orchestrator_receipt",
            "wave_record_refs": ["wave-quality"],
            "planned_tokens": 10,
            "retry_count": 0,
            "fan_out": 1,
            "accepted_findings": 9,
            "rework_count": 4,
            "quality_reserve_used": False,
            "missing_metrics": [
                "input_tokens", "output_tokens", "cache_read_tokens",
                "tool_calls", "wall_time_ms",
            ],
            "unavailable_reason": "only structural wave data is available",
        }
    }
    fragments = [
        {
            "work_status": "DONE",
            "gate_verdict": "PASS",
            "classification": "FACT",
            "confidence": "high",
            "concerns": [],
            "consumption": {
                "measurement_status": "unavailable",
                "unavailable_reason": "platform telemetry unavailable",
            },
        }
    ]
    capture_index = {
        "waves_by_id": {
            "wave-quality": {
                "scheduled_call_admitted_input_tokens_lower_bound": 10,
                "retry_call_count": 0,
                "admitted_tasks": [{"node_id": "review"}],
            }
        }
    }

    errors = consumption.validate_consumption_binding(
        packet, fragments, None, capture_index
    )

    assert "closure accepted_findings differs from accepted FACT fragments" in errors
    assert "closure orchestrator rework_count lacks complete attested fragment metrics" in errors

    packet["consumption"]["accepted_findings"] = 1
    packet["consumption"].pop("rework_count")
    packet["consumption"]["missing_metrics"].append("rework_count")
    assert consumption.validate_consumption_binding(
        packet, fragments, None, capture_index
    ) == []


def test_unavailable_consumption_cannot_claim_quality_reserve_usage() -> None:
    consumption = _load("consumption")
    packet = {
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform telemetry unavailable",
            "quality_reserve_used": False,
        }
    }

    errors = consumption.validate_consumption_binding(packet, [], None)

    assert "closure unavailable consumption cannot claim quality_reserve_used" in errors


def test_consumption_binding_rejects_non_object_route_without_crashing() -> None:
    consumption = _load("consumption")
    packet = {
        "consumption": {
            "measurement_status": "partial",
            "measurement_source": "orchestrator_receipt",
            "telemetry_digest": "sha256:" + "7" * 64,
            "planned_tokens": 100,
            "quality_reserve_used": False,
            "missing_metrics": [
                "input_tokens", "output_tokens", "cache_read_tokens", "tool_calls",
                "retry_count", "fan_out", "wall_time_ms", "accepted_findings",
                "rework_count",
            ],
            "unavailable_reason": "only planning telemetry was emitted",
        }
    }

    errors = consumption.validate_consumption_binding(packet, [], [])

    assert "expected route must be an object" in errors


def test_invalid_observation_adjudication_time_cannot_be_treated_as_pass() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E2",
        command="review governed change",
        baseline=_baseline(),
        criteria=["change remains fail-closed"],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=0,
        stdout=b"reviewed",
        stderr=b"",
    )
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="eventually",
    )

    assert "observation adjudicated_at is invalid" in errors
    assert artifact is None


def test_runtime_observation_rejects_non_object_expected_baseline_without_crashing() -> None:
    observations = _load("observations")
    receipt = observations.build_runtime_observation_receipt(
        producer_role="OPS",
        probe_kind="service_health",
        command="observe local runtime",
        baseline=_baseline(),
        runtime_head="d" * 40,
        host="trade-core",
        environment="demo",
        observed_at="2026-07-11T10:00:00Z",
        expiry="2026-07-11T10:10:00Z",
        exit_code=0,
        facts={"active": True},
        stdout=b"active\n",
        stderr=b"",
    )
    evidence = {
        "scope": "runtime",
        "kind": "runtime_observation_receipt_v1",
        "digest": receipt["receipt_digest"],
        "host": receipt["host"],
        "environment": receipt["environment"],
        "observed_at": receipt["observed_at"],
        "expiry": receipt["expiry"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=None,
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "expected observation baseline must be an object" in errors
    assert artifact is None


def test_non_scalar_observation_role_fails_closed_without_registry_lookup_crash() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E2",
        command="review governed change",
        baseline=_baseline(),
        criteria=["change remains fail-closed"],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=0,
        stdout=b"reviewed",
        stderr=b"",
    )
    receipt["producer_role"] = []
    receipt["receipt_digest"] = observations.observation_receipt_digest(receipt)
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "source review receipt producer must be read-only" in errors
    assert artifact is None


def test_non_scalar_authority_class_fails_closed_without_registry_lookup_crash() -> None:
    authority = _load("authority")
    claim = authority.build_authority_claim(
        authority_class="normative_policy",
        subject="deploy.mainnet_allowed",
        value=False,
        source="CLAUDE.md#Hard Boundaries",
        source_ref="ev-normative-source",
        source_digest="sha256:" + "8" * 64,
        observed_at="2026-07-11T10:00:00Z",
        scope="deploy:trade-core",
        strength="direct",
        expiry=None,
    )
    claim["class"] = []
    claim["claim_digest"] = authority.authority_claim_digest(claim)

    decision = authority.resolve_authority_claims(
        [claim], adjudicated_at="2026-07-11T10:05:00Z"
    )

    assert decision["status"] == "INVALID"
    assert decision["gate_verdict"] == "BLOCKED"


def test_authority_resolver_rejects_non_array_claims_without_crashing() -> None:
    authority = _load("authority")

    decision = authority.resolve_authority_claims(7)

    assert decision["status"] == "INVALID"
    assert decision["gate_verdict"] == "BLOCKED"


def test_boolean_exit_code_cannot_prove_observation_success() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E2",
        command="review governed change",
        baseline=_baseline(),
        criteria=["change remains fail-closed"],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=False,
        stdout=b"reviewed",
        stderr=b"",
    )
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "observation receipt exit_code must be an integer" in errors
    assert artifact is None


def test_runtime_receipt_validates_its_own_flattened_baseline_identity() -> None:
    observations = _load("observations")
    source_only_baseline = {
        **_baseline(),
        "runtime_head": None,
        "runtime_observed_at": None,
    }
    receipt = observations.build_runtime_observation_receipt(
        producer_role="OPS",
        probe_kind="service_health",
        command="observe local runtime",
        baseline=source_only_baseline,
        runtime_head="not-a-head",
        host="trade-core",
        environment="demo",
        observed_at="2026-07-11T10:00:00Z",
        expiry="2026-07-11T10:10:00Z",
        exit_code=0,
        facts={"active": True},
        stdout=b"active\n",
        stderr=b"",
    )
    evidence = {
        "scope": "runtime",
        "kind": "runtime_observation_receipt_v1",
        "digest": receipt["receipt_digest"],
        "host": receipt["host"],
        "environment": receipt["environment"],
        "observed_at": receipt["observed_at"],
        "expiry": receipt["expiry"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=source_only_baseline,
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "runtime observation baseline runtime_head is invalid" in errors
    assert artifact is None


def test_source_change_receipt_requires_a_real_baseline_transition() -> None:
    observations = _load("observations")
    receipt = observations.build_source_change_receipt(
        producer_role="E1",
        before_baseline=_baseline(),
        after_baseline=_baseline(),
        changed_paths=["helper_scripts/example.py"],
        patch_digest="sha256:" + "9" * 64,
        observed_at="2026-07-11T10:02:00Z",
    )
    evidence = {
        "scope": "source",
        "kind": "source_change_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        task_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "source change receipt baseline did not change" in errors
    assert artifact is None


def test_source_observation_wrapper_time_must_match_the_self_hashed_receipt() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E2",
        command="review governed change",
        baseline=_baseline(),
        criteria=["change remains fail-closed"],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=0,
        stdout=b"reviewed",
        stderr=b"",
    )
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": "2026-07-11T09:00:00Z",
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "observation wrapper observed_at is not receipt-bound" in errors
    assert artifact is None


def test_partial_consumption_cannot_claim_reserve_without_planned_tokens() -> None:
    consumption = _load("consumption")
    packet = {
        "consumption": {
            "measurement_status": "partial",
            "measurement_source": "orchestrator_receipt",
            "telemetry_digest": "sha256:" + "a" * 64,
            "input_tokens": 10,
            "quality_reserve_used": False,
            "missing_metrics": [
                "output_tokens", "cache_read_tokens", "tool_calls", "retry_count",
                "fan_out", "wall_time_ms", "accepted_findings", "rework_count",
                "planned_tokens",
            ],
            "unavailable_reason": "planning telemetry unavailable",
        }
    }

    errors = consumption.validate_consumption_binding(packet, [], None)

    assert "closure quality_reserve_used requires planned_tokens" in errors


def test_non_hashable_changed_path_fails_closed_without_crashing() -> None:
    observations = _load("observations")
    after = {**_baseline(), "dirty_diff_hash": "sha256:" + "d" * 64}
    receipt = observations.build_source_change_receipt(
        producer_role="E1",
        before_baseline=_baseline(),
        after_baseline=after,
        changed_paths=[["helper_scripts/example.py"]],
        patch_digest="sha256:" + "b" * 64,
        observed_at="2026-07-11T10:02:00Z",
    )
    evidence = {
        "scope": "source",
        "kind": "source_change_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=after,
        task_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert "source change receipt changed_paths are unsafe or duplicated" in errors
    assert artifact is None


def test_non_scalar_observation_schema_version_fails_closed_without_crashing() -> None:
    observations = _load("observations")
    receipt = observations.build_source_review_receipt(
        producer_role="E2",
        command="review governed change",
        baseline=_baseline(),
        criteria=["change remains fail-closed"],
        observed_at="2026-07-11T10:02:00Z",
        exit_code=0,
        stdout=b"reviewed",
        stderr=b"",
    )
    receipt["schema_version"] = []
    receipt["receipt_digest"] = observations.observation_receipt_digest(receipt)
    evidence = {
        "scope": "source",
        "kind": "source_review_receipt_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["observed_at"],
        "artifact": receipt,
    }

    errors, artifact = observations.validate_observation_evidence(
        evidence,
        expected_baseline=_baseline(),
        adjudicated_at="2026-07-11T10:05:00Z",
    )

    assert errors == ["typed observation artifact schema_version is unsupported"]
    assert artifact is None


@pytest.mark.parametrize(
    ("target", "field", "bad_value"),
    [
        ("fragment", "measurement_status", []),
        ("fragment", "measurement_source", {}),
        ("closure", "measurement_status", []),
        ("closure", "measurement_source", {}),
        ("closure", "wall_time_ms", None),
    ],
)
def test_malformed_consumption_fields_fail_closed_without_type_errors(target: str, field: str, bad_value) -> None:
    consumption = _load("consumption")
    fragment = _measured_role_consumption("c")
    aggregate = _measured_closure_consumption("d")
    (fragment if target == "fragment" else aggregate)[field] = bad_value

    errors = consumption.validate_consumption_binding(
        {"consumption": aggregate}, [{"consumption": fragment}], None
    )

    assert errors
