"""Reproducible, truth-labelled multi-agent efficiency benchmark tests."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
MODULE_PATH = HELPERS / "agent_governance_efficiency_evaluation.py"
SCHEMA_PATH = ROOT / ".codex/schemas/multi_agent_efficiency_evaluation_v1.schema.json"
FIXTURE_PATH = (
    ROOT
    / "tests/fixtures/agent_governance/multi_agent_efficiency_evaluation_v1.json"
)

if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "agent_governance_efficiency_evaluation_test",
        MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _resign(module, record: dict) -> None:
    record["record_digest"] = module.multi_agent_efficiency_evaluation_digest(
        record
    )


def _profile(record: dict, name: str) -> dict:
    return next(item for item in record["profiles"] if item["profile"] == name)


def _canonical_digest(value: dict) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _measured_with_attestation_index(module) -> tuple[dict, dict]:
    fixture = _fixture()
    fixture["evidence_kind"] = "platform_or_external_attested"
    producer = {"id": "platform-usage-export-v1", "kind": "platform"}
    records: dict[str, dict] = {}
    for index, profile in enumerate(fixture["profiles"]):
        reference = f"platform-attestation:run-{index}"
        attestation = {
            "schema_version": "multi_agent_efficiency_attestation_v1",
            "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
            "attestation_id": reference,
            "evaluation_id": fixture["evaluation_id"],
            "profile": profile["profile"],
            "run_id": f"immutable-platform-run-{index}",
            "workload_digest": profile["workload_digest"],
            "baseline_digest": profile["baseline_digest"],
            "observed_at": "2026-07-30T12:05:00Z",
            "call_record_digests": [
                "sha256:" + str(index + 1) * 64,
                "sha256:" + str(index + 4) * 64,
            ],
            "metrics_payload_digest": _canonical_digest(profile["metrics"]),
            "producer": producer,
        }
        attestation["record_digest"] = _canonical_digest(attestation)
        profile.update(
            measurement_status="measured",
            evidence_ref=reference,
            evidence_digest=attestation["record_digest"],
        )
        records[reference] = attestation
    _resign(module, fixture)
    index_record = {
        "schema_version": "multi_agent_efficiency_attestation_index_v1",
        "trust_tier": "PLATFORM_OR_EXTERNAL_ATTESTED",
        "index_id": "platform-efficiency-export-20260730",
        "evaluation_id": fixture["evaluation_id"],
        "producer": producer,
        "records": records,
    }
    index_record["record_digest"] = _canonical_digest(index_record)
    return fixture, index_record


def test_checked_in_fixture_compares_all_profiles_without_a_measured_claim() -> None:
    module = _load_module()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fixture = _fixture()

    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["title"] == "multi_agent_efficiency_evaluation_v1"
    assert module.validate_multi_agent_efficiency_evaluation(fixture) == []
    assert {item["profile"] for item in fixture["profiles"]} == {
        "current",
        "single_agent",
        "bounded_role",
    }

    result = module.evaluate_multi_agent_efficiency(fixture)
    assert result["schema_version"] == (
        "multi_agent_efficiency_evaluation_result_v1"
    )
    assert result["baseline_profile"] == "current"
    assert result["measurement_status"] == "synthetic"
    assert result["measured_claim_allowed"] is False
    assert result["adoption_verdict"] == (
        "SYNTHETIC_ONLY_NO_MEASURED_CLAIM"
    )
    assert set(result["comparisons"]) == {"single_agent", "bounded_role"}
    assert (
        result["comparisons"]["single_agent"]["quality_noninferiority"]["status"]
        == "FAIL"
    )
    assert (
        result["comparisons"]["bounded_role"]["quality_noninferiority"]["status"]
        == "PASS"
    )
    assert result["comparisons"]["bounded_role"]["efficiency_ratios"][
        "elapsed_time_ms"
    ] < 1
    assert result["comparisons"]["bounded_role"]["efficiency_ratios"][
        "input_tokens"
    ] < 1
    assert result["comparisons"]["bounded_role"]["efficiency_claim_allowed"] is False
    assert result["benchmark_only_candidates"] == ["bounded_role"]
    assert result["measured_efficiency_candidates"] == []


def test_efficiency_evaluation_is_exposed_through_the_public_facade() -> None:
    import agent_governance as governance

    assert "evaluate_multi_agent_efficiency" in governance.__all__
    assert "validate_multi_agent_efficiency_evaluation" in governance.__all__
    completed = subprocess.run(
        [
            sys.executable,
            str(HELPERS / "agent_governance.py"),
            "efficiency-evaluation",
            f"@{FIXTURE_PATH}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["adoption_verdict"] == (
        "SYNTHETIC_ONLY_NO_MEASURED_CLAIM"
    )


def test_registry_owns_and_validates_the_exact_quality_policy() -> None:
    import agent_governance as governance

    registry = governance.load_registry()
    assert registry["efficiency_evaluation_attestation_schema_path"] == (
        ".codex/schemas/multi_agent_efficiency_attestation_index_v1.schema.json"
    )
    assert "EfficiencyAttestationVerifier" in governance.__all__
    assert "efficiency_attestation_index_digest" in governance.__all__
    assert "validate_efficiency_attestation_index" in governance.__all__
    policy = registry["efficiency_evaluation_policy"]
    assert policy["thresholds"] == {
        "max_closure_quality_score_drop": 0.0,
        "max_reopen_count_increase": 0,
        "minimum_decision_changing_findings_retention_ratio": 1.0,
    }
    assert governance.registry_efficiency_evaluation_policy_errors(registry) == []
    assert policy["policy_digest"] == governance.efficiency_evaluation_policy_digest(
        policy
    )

    drifted = deepcopy(registry)
    drifted_policy = drifted["efficiency_evaluation_policy"]
    drifted_policy["thresholds"]["max_reopen_count_increase"] = 999999
    drifted_policy["policy_digest"] = (
        governance.efficiency_evaluation_policy_digest(drifted_policy)
    )
    assert any(
        "zero reopen increase" in error
        for error in governance.validate_registry(drifted, ROOT)
    )

    bad_schema_path = deepcopy(registry)
    bad_schema_path["efficiency_evaluation_attestation_schema_path"] = (
        ".codex/schemas/closure_quality_attestation_v1.schema.json"
    )
    assert any(
        "efficiency_evaluation_attestation_schema_path" in error
        for error in governance.validate_registry(bad_schema_path, ROOT)
    )


def test_profiles_must_bind_the_same_workload_and_baseline() -> None:
    module = _load_module()
    fixture = _fixture()

    wrong_workload = deepcopy(fixture)
    _profile(wrong_workload, "bounded_role")["workload_digest"] = (
        "sha256:" + "1" * 64
    )
    _resign(module, wrong_workload)
    assert any(
        "same workload" in error
        for error in module.validate_multi_agent_efficiency_evaluation(
            wrong_workload
        )
    )

    wrong_baseline = deepcopy(fixture)
    _profile(wrong_baseline, "single_agent")["baseline_digest"] = (
        "sha256:" + "2" * 64
    )
    _resign(module, wrong_baseline)
    assert any(
        "same baseline" in error
        for error in module.validate_multi_agent_efficiency_evaluation(
            wrong_baseline
        )
    )

    duplicate = deepcopy(fixture)
    duplicate["profiles"][1]["profile"] = "current"
    _resign(module, duplicate)
    assert any(
        "exactly one current, single_agent, and bounded_role" in error
        for error in module.validate_multi_agent_efficiency_evaluation(duplicate)
    )


def test_unavailable_metrics_remain_null_and_are_never_zero_filled() -> None:
    module = _load_module()
    fixture = _fixture()
    bounded = _profile(fixture, "bounded_role")
    bounded.update(
        measurement_status="unavailable",
        evidence_ref=None,
        evidence_digest=None,
        unavailable_reason="provider usage and quality telemetry unavailable",
    )
    bounded["metrics"] = {field: None for field in bounded["metrics"]}
    fixture["evidence_kind"] = "mixed"
    _resign(module, fixture)

    assert module.validate_multi_agent_efficiency_evaluation(fixture) == []
    result = module.evaluate_multi_agent_efficiency(fixture)
    comparison = result["comparisons"]["bounded_role"]
    assert comparison["quality_noninferiority"]["status"] == "UNAVAILABLE"
    assert all(value is None for value in comparison["efficiency_ratios"].values())
    assert comparison["efficiency_claim_allowed"] is False

    zero_filled = deepcopy(fixture)
    _profile(zero_filled, "bounded_role")["metrics"]["elapsed_time_ms"] = 0
    _resign(module, zero_filled)
    assert any(
        "unavailable profile metrics must all be null" in error
        for error in module.validate_multi_agent_efficiency_evaluation(
            zero_filled
        )
    )


def test_quality_noninferiority_blocks_a_cheaper_but_degraded_profile() -> None:
    module = _load_module()
    result = module.evaluate_multi_agent_efficiency(_fixture())

    single = result["comparisons"]["single_agent"]
    assert single["efficiency_ratios"]["elapsed_time_ms"] < 1
    assert single["efficiency_ratios"]["input_tokens"] < 1
    assert single["quality_noninferiority"]["status"] == "FAIL"
    assert {
        name
        for name, check in single["quality_noninferiority"]["checks"].items()
        if check["status"] == "FAIL"
    } == {
        "closure_quality_score",
        "reopen_count",
        "decision_changing_findings",
    }
    assert single["efficiency_claim_allowed"] is False


def test_measured_record_cannot_relax_the_registry_quality_gate() -> None:
    module = _load_module()
    fixture = _fixture()
    fixture["evidence_kind"] = "platform_or_external_attested"
    trusted_refs: set[str] = set()
    for index, profile in enumerate(fixture["profiles"]):
        evidence_ref = f"telemetry:measured-profile-{index}"
        trusted_refs.add(evidence_ref)
        profile.update(
            measurement_status="measured",
            evidence_ref=evidence_ref,
            evidence_digest="sha256:" + str(index + 4) * 64,
        )
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"].update(
        closure_quality_score=0,
        reopen_count=999999,
        decision_changing_findings=0,
    )
    fixture["quality_noninferiority_gate"] = {
        "max_closure_quality_score_drop": 1,
        "max_reopen_count_increase": 999999,
        "minimum_decision_changing_findings_retention_ratio": 0,
    }
    _resign(module, fixture)

    errors = module.validate_multi_agent_efficiency_evaluation(
        fixture,
        attested_evidence_refs=trusted_refs,
    )
    assert any(
        "Registry-owned quality non-inferiority policy" in error
        for error in errors
    )
    with pytest.raises(
        ValueError,
        match="Registry-owned quality non-inferiority policy",
    ):
        module.evaluate_multi_agent_efficiency(
            fixture,
            attested_evidence_refs=trusted_refs,
        )


def test_registry_quality_policy_blocks_a_measured_degraded_profile() -> None:
    module = _load_module()
    fixture = _fixture()
    fixture["evidence_kind"] = "platform_or_external_attested"
    trusted_refs: set[str] = set()
    for index, profile in enumerate(fixture["profiles"]):
        evidence_ref = f"telemetry:strict-measured-profile-{index}"
        trusted_refs.add(evidence_ref)
        profile.update(
            measurement_status="measured",
            evidence_ref=evidence_ref,
            evidence_digest="sha256:" + str(index + 7) * 64,
        )
    _profile(fixture, "bounded_role")["metrics"].update(
        closure_quality_score=0,
        reopen_count=999999,
        decision_changing_findings=0,
    )
    _resign(module, fixture)

    assert (
        module.validate_multi_agent_efficiency_evaluation(
            fixture,
            attested_evidence_refs=trusted_refs,
        )
        == []
    )
    result = module.evaluate_multi_agent_efficiency(
        fixture,
        attested_evidence_refs=trusted_refs,
    )
    bounded = result["comparisons"]["bounded_role"]
    assert bounded["quality_noninferiority"]["status"] == "FAIL"
    assert bounded["efficiency_claim_allowed"] is False
    assert "bounded_role" not in result["measured_efficiency_candidates"]


def test_free_form_attested_refs_can_never_unlock_a_measured_claim() -> None:
    module = _load_module()
    fixture = _fixture()
    fixture["evidence_kind"] = "platform_or_external_attested"
    refs: set[str] = set()
    for index, profile in enumerate(fixture["profiles"]):
        evidence_ref = f"telemetry:caller-self-asserted-{index}"
        refs.add(evidence_ref)
        profile.update(
            measurement_status="measured",
            evidence_ref=evidence_ref,
            evidence_digest="sha256:" + str(index + 1) * 64,
        )
    _resign(module, fixture)

    result = module.evaluate_multi_agent_efficiency(
        fixture,
        attested_evidence_refs=refs,
    )
    assert result["measurement_status"] == "external_limit"
    assert result["measured_claim_allowed"] is False
    assert result["adoption_verdict"] == (
        "EXTERNAL_LIMIT_PLATFORM_ATTESTATION_UNVERIFIED"
    )
    assert result["measured_efficiency_candidates"] == []


def test_typed_attestation_index_is_structurally_bound_but_not_self_trusting() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)

    assert (
        module.validate_efficiency_attestation_index(
            fixture,
            attestation_index,
        )
        == []
    )
    result = module.evaluate_multi_agent_efficiency(
        fixture,
        attestation_index=attestation_index,
    )
    assert result["measurement_status"] == "external_limit"
    assert result["measured_claim_allowed"] is False
    assert result["attestation_index_digest"] == attestation_index["record_digest"]


def test_trusted_host_verifier_unlocks_only_the_exact_attestation_index() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)

    class ExactVerifier:
        def __init__(self) -> None:
            self.binding: dict | None = None

        def verify_efficiency_attestation_index(self, **binding) -> bool:
            self.binding = binding
            return True

    verifier = ExactVerifier()
    result = module.evaluate_multi_agent_efficiency(
        fixture,
        attestation_index=attestation_index,
        attestation_verifier=verifier,
    )

    assert result["measurement_status"] == "measured"
    assert result["measured_claim_allowed"] is True
    assert result["adoption_verdict"] == "MEASURED_COMPARISON_AVAILABLE"
    assert result["measured_efficiency_candidates"] == ["bounded_role"]
    assert verifier.binding == {
        "index_digest": attestation_index["record_digest"],
        "evaluation_id": fixture["evaluation_id"],
        "run_ids": (
            "immutable-platform-run-0",
            "immutable-platform-run-1",
            "immutable-platform-run-2",
        ),
        "call_record_digests": tuple(
            "sha256:" + str(index) * 64 for index in range(1, 7)
        ),
        "metrics_payload_digests": tuple(
            sorted(
                attestation["metrics_payload_digest"]
                for attestation in attestation_index["records"].values()
            )
        ),
        "attestation_record_digests": tuple(
            sorted(
                attestation["record_digest"]
                for attestation in attestation_index["records"].values()
            )
        ),
    }


def test_attestation_index_rejects_metrics_or_call_inventory_drift() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)

    changed_metrics = deepcopy(fixture)
    _profile(changed_metrics, "bounded_role")["metrics"]["input_tokens"] += 1
    _resign(module, changed_metrics)
    assert any(
        "metrics payload digest differs" in error
        for error in module.validate_efficiency_attestation_index(
            changed_metrics,
            attestation_index,
        )
    )

    changed_inventory = deepcopy(attestation_index)
    first = next(iter(changed_inventory["records"].values()))
    first["call_record_digests"].append(first["call_record_digests"][0])
    first["record_digest"] = _canonical_digest(first)
    changed_inventory["record_digest"] = _canonical_digest(changed_inventory)
    assert any(
        "sorted unique inventory" in error
        for error in module.validate_efficiency_attestation_index(
            fixture,
            changed_inventory,
        )
    )


def test_call_record_digest_cannot_be_reused_across_platform_runs() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    references = sorted(attestation_index["records"])
    first = attestation_index["records"][references[0]]
    second = attestation_index["records"][references[1]]
    second["call_record_digests"][0] = first["call_record_digests"][0]
    second["call_record_digests"] = sorted(second["call_record_digests"])
    second["record_digest"] = _canonical_digest(second)
    _profile(fixture, second["profile"])["evidence_digest"] = second["record_digest"]
    _resign(module, fixture)
    attestation_index["record_digest"] = _canonical_digest(attestation_index)

    assert any(
        "cannot be reused across run_id values" in error
        for error in module.validate_efficiency_attestation_index(
            fixture,
            attestation_index,
        )
    )


def test_cli_reads_typed_index_but_has_no_self_attestation_escape(
    tmp_path: Path,
) -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    evaluation_path = tmp_path / "evaluation.json"
    index_path = tmp_path / "attestation-index.json"
    evaluation_path.write_text(json.dumps(fixture), encoding="utf-8")
    index_path.write_text(json.dumps(attestation_index), encoding="utf-8")

    for runner in (
        [sys.executable, str(MODULE_PATH)],
        [
            sys.executable,
            str(HELPERS / "agent_governance.py"),
            "efficiency-evaluation",
        ],
    ):
        completed = subprocess.run(
            [
                *runner,
                f"@{evaluation_path}",
                "--attestation-index",
                f"@{index_path}",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        assert result["measurement_status"] == "external_limit"
        assert result["measured_claim_allowed"] is False

    old_escape = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            f"@{evaluation_path}",
            "--attested-ref",
            next(iter(attestation_index["records"])),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert old_escape.returncode != 0


def test_synthetic_fixture_cannot_be_relabelled_as_measured() -> None:
    module = _load_module()
    fixture = _fixture()
    current = _profile(fixture, "current")
    current.update(
        measurement_status="measured",
        evidence_ref="telemetry:forged",
        evidence_digest="sha256:" + "3" * 64,
    )
    _resign(module, fixture)

    assert any(
        "synthetic fixture profiles must remain synthetic" in error
        for error in module.validate_multi_agent_efficiency_evaluation(fixture)
    )


def test_runner_is_a_read_only_machine_consumer() -> None:
    completed = subprocess.run(
        [sys.executable, str(MODULE_PATH), f"@{FIXTURE_PATH}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["measurement_status"] == "synthetic"
    assert result["measured_claim_allowed"] is False


def test_standalone_runner_loads_siblings_under_governed_safe_path() -> None:
    governed_environment = dict(os.environ)
    governed_environment.pop("PYTHONPATH", None)
    governed_environment.update(
        PYTHONNOUSERSITE="1",
        PYTHONSAFEPATH="1",
    )

    # -I preserves the no-implicit-script-path contract on Python 3.10, where
    # PYTHONSAFEPATH is not yet implemented.
    completed = subprocess.run(
        [sys.executable, "-I", str(MODULE_PATH), f"@{FIXTURE_PATH}"],
        cwd=ROOT,
        env=governed_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["measurement_status"] == "synthetic"
