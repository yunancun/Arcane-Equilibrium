"""Durable-closure follow-up ledger contract and trust-boundary tests."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "helper_scripts/maintenance_scripts/agent_governance.py"


def _load():
    spec = importlib.util.spec_from_file_location("closure_quality_facade", FACADE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _closure() -> dict:
    return {
        "schema_version": "closure_packet_v1",
        "task_id": "quality-followup-fixture",
        "adjudicated_at": "2026-07-11T10:00:00Z",
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform usage telemetry unavailable",
        },
    }


def _measured_fixture(governance, closure: dict, scheduled: dict):
    metrics = {
        "reopened": False,
        "false_closure": False,
        "rework_count": 2,
        "accepted_decision_changing_findings": 3,
        "realized_value_status": "positive",
    }
    attestation = {
        "schema_version": "closure_quality_attestation_v1",
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "closure_digest": scheduled["closure_digest"],
        "followup_window": deepcopy(scheduled["followup_window"]),
        "observed_at": "2026-07-12T12:00:00Z",
        "producer": {"id": "quality-fixture", "kind": "platform"},
        "metrics": deepcopy(metrics),
    }
    attestation["record_digest"] = governance.canonical_digest(attestation)
    measured = deepcopy(scheduled)
    measured.update(
        measurement_status="measured",
        observed_at=attestation["observed_at"],
        attestation_ref="quality-attestation:1",
        attestation_digest=attestation["record_digest"],
        unavailable_reason=None,
        metrics=deepcopy(metrics),
    )
    measured["record_digest"] = governance.closure_quality_followup_digest(
        measured
    )
    index = {
        "platform_attested": ["quality-attestation:1"],
        "records": {"quality-attestation:1": attestation},
    }
    return measured, index


def test_scheduled_and_measured_followups_bind_one_immutable_closure() -> None:
    governance = _load()
    closure = _closure()
    scheduled = governance.build_scheduled_closure_quality_followup(
        closure,
        opens_at="2026-07-12T00:00:00Z",
        closes_at="2026-07-13T00:00:00Z",
        created_at="2026-07-11T11:00:00Z",
    )

    assert scheduled["measurement_status"] == "scheduled"
    assert scheduled["metrics"] is None
    assert governance.validate_closure_quality_followup(
        scheduled, closure
    ) == []
    unavailable_summary = governance.summarize_closure_quality_followups(
        [scheduled],
        {scheduled["closure_digest"]: closure},
        attestation_index=None,
    )
    assert unavailable_summary["measurement_status"] == "unavailable"
    assert unavailable_summary["metrics"] is None

    measured, attestation_index = _measured_fixture(
        governance, closure, scheduled
    )
    assert governance.validate_closure_quality_followup(
        measured, closure, attestation_index=attestation_index
    ) == []
    summary = governance.summarize_closure_quality_followups(
        [measured],
        {measured["closure_digest"]: closure},
        attestation_index=attestation_index,
    )
    assert summary["measurement_status"] == "measured"
    assert summary["metrics"] == {
        "observed_closures": 1,
        "durable_closures": 1,
        "reopened_closures": 0,
        "false_closures": 0,
        "rework_count": 2,
        "accepted_decision_changing_findings": 3,
        "realized_value_status_counts": {
            "positive": 1,
            "neutral": 0,
            "negative": 0,
            "not_realized": 0,
            "indeterminate": 0,
        },
    }
    assert summary["cost_per_durable_closure_status"] == (
        "requires_separate_platform_attested_cost"
    )


def test_followup_rejects_zero_filled_unknowns_and_untrusted_measurements() -> None:
    governance = _load()
    closure = _closure()
    scheduled = governance.build_scheduled_closure_quality_followup(
        closure,
        opens_at="2026-07-12T00:00:00Z",
        closes_at="2026-07-13T00:00:00Z",
        created_at="2026-07-11T11:00:00Z",
    )

    zero_filled = deepcopy(scheduled)
    zero_filled["metrics"] = {
        "reopened": False,
        "false_closure": False,
        "rework_count": 0,
        "accepted_decision_changing_findings": 0,
        "realized_value_status": "indeterminate",
    }
    zero_filled["record_digest"] = governance.closure_quality_followup_digest(
        zero_filled
    )
    assert any(
        "scheduled/unavailable follow-up cannot carry measured values" in error
        for error in governance.validate_closure_quality_followup(
            zero_filled, closure
        )
    )

    measured, attestation_index = _measured_fixture(
        governance, closure, scheduled
    )
    self_labeled = deepcopy(attestation_index)
    self_labeled["platform_attested"] = []
    assert any(
        "requires a platform/external-attested ref" in error
        for error in governance.validate_closure_quality_followup(
            measured, closure, attestation_index=self_labeled
        )
    )

    changed_closure = deepcopy(closure)
    changed_closure["task_id"] = "different-closure"
    assert any(
        "closure digest differs" in error
        for error in governance.validate_closure_quality_followup(
            measured, changed_closure, attestation_index=attestation_index
        )
    )

    changed_metric = deepcopy(measured)
    changed_metric["metrics"]["rework_count"] = 4
    changed_metric["record_digest"] = governance.closure_quality_followup_digest(
        changed_metric
    )
    assert any(
        "metrics differ from attestation" in error
        for error in governance.validate_closure_quality_followup(
            changed_metric, closure, attestation_index=attestation_index
        )
    )


def test_closure_quality_cli_is_a_read_only_machine_consumer(tmp_path: Path) -> None:
    governance = _load()
    closure = _closure()
    followup = governance.build_scheduled_closure_quality_followup(
        closure,
        opens_at="2026-07-12T00:00:00Z",
        closes_at="2026-07-13T00:00:00Z",
        created_at="2026-07-11T11:00:00Z",
    )
    bundle = tmp_path / "followup.json"
    bundle.write_text(
        json.dumps({"followup": followup, "closure": closure}),
        encoding="utf-8",
    )

    assert governance.main(["closure-quality", f"@{bundle}"]) == 0


def test_closure_quality_contract_is_indexed_for_ai_e_without_a_producer() -> None:
    governance = _load()
    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )
    interface = registry["interfaces"]["closure_quality_followup"]
    assert "summarize_closure_quality_followups" in interface
    assert "PLATFORM_OR_EXTERNAL_ATTESTED" in interface
    ai_e = registry["roles"]["AI-E"]
    assert "durable closure follow-up" in ai_e["activation"]
    assert "self-attested durability or realized value" in ai_e["refuses"]
    assert any(
        "closure_quality_followup_v1" in rule and "unavailable" in rule
        for rule in ai_e["judgment_rules"]
    )

    for key, expected_title in (
        ("closure_quality_followup_schema_path", "closure_quality_followup_v1"),
        ("closure_quality_attestation_schema_path", "closure_quality_attestation_v1"),
    ):
        schema_path = ROOT / registry[key]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["title"] == expected_title
        assert schema["additionalProperties"] is False

    decision = governance.authorize_command(
        "AI-E",
        "python3 helper_scripts/maintenance_scripts/agent_governance.py "
        "closure-quality @tests/fixtures/closure-quality.json",
        registry,
    )
    assert decision["allowed"] is True
