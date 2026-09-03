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
GOVERNANCE_DOC_PATH = ROOT / "docs/agents/development-agent-governance.md"
FIXTURE_PATH = (
    ROOT
    / "tests/fixtures/agent_governance/multi_agent_efficiency_evaluation_v1.json"
)
CORPUS_SCHEMA_PATH = (
    ROOT
    / ".codex/schemas/multi_agent_efficiency_baseline_corpus_v1.schema.json"
)
CORPUS_FIXTURE_PATH = (
    ROOT
    / "tests/fixtures/agent_governance/"
    "multi_agent_efficiency_baseline_corpus_v1.json"
)
MANIFEST_SCHEMA_PATH = (
    ROOT
    / ".codex/schemas/multi_agent_efficiency_baseline_manifest_v1.schema.json"
)
MANIFEST_FIXTURE_PATH = (
    ROOT
    / "tests/fixtures/agent_governance/"
    "multi_agent_efficiency_baseline_manifest_v1.json"
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


def _corpus_fixture() -> dict:
    return json.loads(CORPUS_FIXTURE_PATH.read_text(encoding="utf-8"))


def _manifest_fixture() -> dict:
    return json.loads(MANIFEST_FIXTURE_PATH.read_text(encoding="utf-8"))


def _resign(module, record: dict) -> None:
    if record.get("evidence_kind") != "synthetic_fixture":
        record["quality_noninferiority_policy"]["policy_digest"] = (
            module._registry_efficiency_evaluation_policy()["policy_digest"]
        )
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


def _resign_corpus(module, corpus: dict) -> None:
    for case in corpus["cases"]:
        case["case_digest"] = module.multi_agent_efficiency_baseline_case_digest(
            case
        )
    corpus["corpus_digest"] = (
        module.multi_agent_efficiency_baseline_corpus_digest(corpus)
    )


def _resign_manifest(module, manifest: dict) -> None:
    for record in (
        manifest["current_profile_records"]
        + manifest["candidate_profile_records"]
    ):
        for run in record["runs"]:
            run["run_digest"] = module.multi_agent_efficiency_baseline_run_digest(
                run
            )
        record["record_digest"] = (
            module.multi_agent_efficiency_baseline_case_record_digest(record)
        )
    manifest["manifest_digest"] = (
        module.multi_agent_efficiency_baseline_manifest_digest(manifest)
    )


def _platform_manifest(module) -> tuple[dict, dict, dict]:
    import agent_governance as governance

    corpus = _corpus_fixture()
    registry = governance.load_registry()
    manifest = _manifest_fixture()
    candidates = []
    for current in manifest["current_profile_records"]:
        case = next(
            item for item in corpus["cases"] if item["case_id"] == current["case_id"]
        )
        quality = case["expected"]["quality_oracle"] or {}
        safety = case["expected"]["safety_oracle"] or {}
        finding_ids = quality.get("gold_p0_ids", []) + quality.get("gold_p1_ids", [])
        decision_ids = quality.get("decision_changing_finding_ids", [])
        values = {
            metric_id: {"value": 0, "unavailable_reason": None}
            for metric_id in current["metrics"]
        }
        values.update(
            closure_quality_score={"value": 1.0, "unavailable_reason": None},
            required_coverage_ratio={"value": 1.0, "unavailable_reason": None},
            elapsed_time_ms={"value": 1000, "unavailable_reason": None},
            input_tokens={"value": 100, "unavailable_reason": None},
            output_tokens={"value": 10, "unavailable_reason": None},
            cache_read_tokens={"value": 20, "unavailable_reason": None},
            calls={"value": 1, "unavailable_reason": None},
            p0_p1_recall_ratio={"value": 1.0, "unavailable_reason": None},
            decision_changing_findings={
                "value": len(decision_ids),
                "unavailable_reason": None,
            },
            expected_terminal_match={"value": True, "unavailable_reason": None},
            expected_coverage_match={"value": True, "unavailable_reason": None},
            route_sentinel_match={"value": True, "unavailable_reason": None},
            permission_sentinel_match={"value": True, "unavailable_reason": None},
            depth_sentinel_match={"value": True, "unavailable_reason": None},
            full_audit_sentinel_match={"value": True, "unavailable_reason": None},
            orchestration_load={"value": 1, "unavailable_reason": None},
        )
        for record in (current, deepcopy(current)):
            profile = "current" if record is current else "candidate"
            arm = "A_CURRENT" if profile == "current" else "B_CANDIDATE"
            record.update(
                profile=profile,
                treatment={"arm": arm, "differences": {}},
                evidence_status="PLATFORM_OR_EXTERNAL_ATTESTED",
                measurement_status="measured",
                adoption_eligible=True,
                evidence_ref=f"platform-attestation:{profile}:{record['case_id']}",
            )
            record["metrics"] = deepcopy(values)
            record["runs"] = []
            for ordinal in range(1, record["expected_run_count"] + 1):
                observed_facts = {
                    "route_nodes": deepcopy(case["expected"]["route_nodes"]),
                    "route_edges": deepcopy(case["expected"]["required_edges"]),
                    "finding_ids": deepcopy(finding_ids),
                    "permission_decision": safety.get("expected_permission_decision"),
                    "depth": safety.get("expected_depth"),
                    "terminal_receipt_digest": "sha256:" + "a" * 64,
                    "coverage_receipt_digest": "sha256:" + "b" * 64,
                    "permission_receipt_digest": (
                        "sha256:" + "c" * 64 if safety else None
                    ),
                    "depth_receipt_digest": (
                        "sha256:" + "d" * 64 if safety else None
                    ),
                }
                run = {
                    "run_id": f"{profile}:{record['case_id']}:{ordinal}",
                    "arm": arm,
                    "ordinal": ordinal,
                    "qualification_status": "qualified",
                    "observed_terminal": case["expected"]["terminal"],
                    "observed_facts": observed_facts,
                    "metrics": deepcopy(values),
                    "evidence_status": "PLATFORM_OR_EXTERNAL_ATTESTED",
                    "evidence_ref": f"platform-run:{profile}:{record['case_id']}:{ordinal}",
                    "evidence_digest": _canonical_digest(observed_facts),
                }
                run["run_digest"] = module.multi_agent_efficiency_baseline_run_digest(
                    run
                )
                record["runs"].append(run)
            record["evidence_digest"] = _canonical_digest(
                {"run_digests": [run["run_digest"] for run in record["runs"]]}
            )
            record["record_digest"] = (
                module.multi_agent_efficiency_baseline_case_record_digest(record)
            )
        candidates.append(record)
    manifest["candidate_profile_records"] = candidates
    manifest["adoption_status"] = "ADOPTION_EVIDENCE_AVAILABLE"
    _resign_manifest(module, manifest)
    return manifest, corpus, registry


class _ExactManifestVerifier:
    def __init__(self) -> None:
        self.binding: dict | None = None

    def verify_efficiency_baseline_manifest(self, **binding) -> bool:
        self.binding = binding
        return True


def test_baseline_corpus_and_manifest_are_canonical_registry_bound_inputs() -> None:
    import agent_governance as governance

    module = _load_module()
    corpus = _corpus_fixture()
    manifest = _manifest_fixture()
    registry = governance.load_registry()

    assert json.loads(CORPUS_SCHEMA_PATH.read_text(encoding="utf-8"))["title"] == (
        "multi_agent_efficiency_baseline_corpus_v1"
    )
    assert json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))["title"] == (
        "multi_agent_efficiency_baseline_manifest_v1"
    )
    assert registry["efficiency_baseline_corpus_schema_path"] == (
        ".codex/schemas/multi_agent_efficiency_baseline_corpus_v1.schema.json"
    )
    assert registry["efficiency_baseline_manifest_schema_path"] == (
        ".codex/schemas/multi_agent_efficiency_baseline_manifest_v1.schema.json"
    )
    assert module.validate_multi_agent_efficiency_baseline_corpus(corpus) == []
    assert (
        module.validate_multi_agent_efficiency_baseline_manifest(
            manifest,
            corpus=corpus,
            registry=registry,
        )
        == []
    )
    assert [case["case_class"] for case in corpus["cases"]] == [
        "q0_governance_query",
        "q1_low_risk_source_change",
        "quality_sentinel",
        "safety_full_audit_sentinel",
    ]
    assert corpus["run_protocol"] == {
        "arms": ["A_CURRENT", "B_CANDIDATE"],
        "assignment": "interleaved_ab_v1",
        "q0_q1_repeats_per_arm": 3,
        "sentinel_min_repeats_per_arm": 1,
        "qualification": "all_runs_individually_qualified_v1",
        "failure_aggregation": "no_failure_averaging_v1",
        "elapsed_time_evaluation": "each_qualified_run_lte_case_target_v1",
    }
    q0, q1 = corpus["cases"][:2]
    assert q0["expected"]["elapsed_time_target_ms"] == 300000
    assert q1["expected"]["elapsed_time_target_ms"] == 900000
    assert all(
        record["evidence_status"] == "UNAVAILABLE"
        and record["measurement_status"] == "unavailable"
        and record["adoption_eligible"] is False
        and record["runs"] == []
        and all(
            metric["value"] is None and metric["unavailable_reason"]
            for metric in record["metrics"].values()
        )
        for record in manifest["current_profile_records"]
    )
    assert manifest["candidate_profile_records"] == []
    assert manifest["adoption_status"] == "PENDING_CANDIDATE_RUNS"


def test_registry_metric_catalog_is_closed_versioned_and_preserves_v1_axes() -> None:
    import agent_governance as governance

    registry = governance.load_registry()
    policy = registry["efficiency_evaluation_policy"]
    catalog = policy["metric_catalog"]

    assert catalog["schema_version"] == "multi_agent_efficiency_metric_catalog_v1"
    assert set(catalog["metrics"]) >= {
        "elapsed_time_ms",
        "input_tokens",
        "cache_read_tokens",
        "time_to_first_valid_result_ms",
        "wait_duration_ms",
        "waits",
        "max_single_turn_input_tokens",
        "compactions",
        "duplicate_exec_count",
        "duplicate_wait_agent_count",
        "expected_terminal_match",
        "expected_coverage_match",
        "missed_p0_p1_count",
        "full_audit_sentinel_match",
        "orchestration_load",
    }
    required_definition_fields = {
        "definition",
        "unit",
        "grain",
        "direction",
        "aggregation",
        "clock_boundary",
        "source_kind",
        "minimum_trust_tier",
        "missing_value_behavior",
    }
    assert all(
        set(definition) == required_definition_fields
        for definition in catalog["metrics"].values()
    )
    assert catalog["metrics"]["elapsed_time_ms"]["clock_boundary"] == (
        "host_task_receipt_or_admission_start_to_verified_terminal_receipt_v1"
    )
    assert "cached input" in catalog["metrics"]["input_tokens"][
        "definition"
    ].lower()
    assert "no dollar" in catalog["metrics"]["input_tokens"][
        "definition"
    ].lower()
    assert catalog["metrics"]["orchestration_load"]["definition"] == (
        "calls + waits + retries + compactions + duplicate_exec_count + "
        "duplicate_wait_agent_count"
    )
    assert policy["efficiency_improvement"]["axes"] == [
        "elapsed_time_ms",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "calls",
        "waits",
        "retries",
        "compactions",
    ]
    assert governance.registry_efficiency_evaluation_policy_errors(registry) == []
    assert policy["policy_digest"] == governance.efficiency_evaluation_policy_digest(
        policy
    )


def test_corpus_rejects_digest_drift_case_substitution_and_averaged_targets() -> None:
    module = _load_module()
    corpus = _corpus_fixture()

    digest_drift = deepcopy(corpus)
    digest_drift["description"] += " changed"
    assert any(
        "corpus_digest differs" in error
        for error in module.validate_multi_agent_efficiency_baseline_corpus(
            digest_drift
        )
    )

    substituted = deepcopy(corpus)
    substituted["cases"][0]["case_class"] = "quality_sentinel"
    _resign_corpus(module, substituted)
    assert any(
        "exactly one" in error or "ordered immutable cases" in error
        for error in module.validate_multi_agent_efficiency_baseline_corpus(
            substituted
        )
    )

    averaged = deepcopy(corpus)
    averaged["run_protocol"]["elapsed_time_evaluation"] = "median_lte_target"
    averaged["cases"][0]["expected"]["elapsed_time_target_ms"] = 300001
    _resign_corpus(module, averaged)
    errors = module.validate_multi_agent_efficiency_baseline_corpus(averaged)
    assert any("every qualified run" in error for error in errors)
    assert any("Q0" in error and "300000" in error for error in errors)

    resigned_content_change = deepcopy(corpus)
    resigned_content_change["cases"][0]["sanitized_task_facts"]["objective"] += (
        " substituted"
    )
    resigned_content_change["cases"][0]["replay"]["replay_digest"] = (
        _canonical_digest(
            resigned_content_change["cases"][0]["sanitized_task_facts"]
        )
    )
    _resign_corpus(module, resigned_content_change)
    assert any(
        "immutable case authority" in error
        for error in module.validate_multi_agent_efficiency_baseline_corpus(
            resigned_content_change
        )
    )


def test_corpus_rejects_removed_full_audit_hard_edge() -> None:
    module = _load_module()
    corpus = _corpus_fixture()
    safety = next(
        case
        for case in corpus["cases"]
        if case["case_class"] == "safety_full_audit_sentinel"
    )
    safety["expected"]["required_edges"].remove("pm_triage->full_audit")
    _resign_corpus(module, corpus)

    assert any(
        "full-audit hard edge" in error
        for error in module.validate_multi_agent_efficiency_baseline_corpus(corpus)
    )


def test_manifest_rejects_binding_drift_case_substitution_and_unknown_as_zero() -> None:
    import agent_governance as governance

    module = _load_module()
    corpus = _corpus_fixture()
    registry = governance.load_registry()
    manifest = _manifest_fixture()

    manifest["corpus_binding"]["corpus_digest"] = "sha256:" + "1" * 64
    manifest["policy_binding"]["policy_digest"] = "sha256:" + "2" * 64
    manifest["registry_binding"]["registry_digest"] = "sha256:" + "3" * 64
    record = manifest["current_profile_records"][0]
    record["case_digest"] = manifest["current_profile_records"][1]["case_digest"]
    metric = record["metrics"]["elapsed_time_ms"]
    metric["value"] = 0
    metric["unavailable_reason"] = None
    _resign_manifest(module, manifest)

    errors = module.validate_multi_agent_efficiency_baseline_manifest(
        manifest,
        corpus=corpus,
        registry=registry,
    )
    assert any("corpus binding" in error for error in errors)
    assert any("policy binding" in error for error in errors)
    assert any("Registry binding" in error for error in errors)
    assert any("case substitution" in error for error in errors)
    assert any("unknown-as-zero" in error for error in errors)


def test_manifest_rejects_unauthorized_treatment_and_provisional_promotion() -> None:
    import agent_governance as governance

    module = _load_module()
    corpus = _corpus_fixture()
    registry = governance.load_registry()
    manifest = _manifest_fixture()
    candidate = deepcopy(manifest["current_profile_records"][0])
    candidate.update(
        profile="candidate",
        evidence_status="PROVISIONAL_LOCAL_HOST_EXPORT",
        measurement_status="measured",
        adoption_eligible=True,
        evidence_ref="local-host-export:unattested",
        evidence_digest="sha256:" + "4" * 64,
        treatment={"arm": "B_CANDIDATE", "differences": {"model": "cheaper"}},
    )
    candidate["metrics"]["elapsed_time_ms"] = {
        "value": 100,
        "unavailable_reason": None,
    }
    manifest["candidate_profile_records"] = [candidate]
    _resign_manifest(module, manifest)

    errors = module.validate_multi_agent_efficiency_baseline_manifest(
        manifest,
        corpus=corpus,
        registry=registry,
    )
    assert any("unauthorized treatment difference" in error for error in errors)
    assert any("provisional" in error and "measured" in error for error in errors)
    assert any("provisional" in error and "adoption" in error for error in errors)


def test_manifest_platform_claim_requires_exact_out_of_band_verification() -> None:
    module = _load_module()
    manifest, corpus, registry = _platform_manifest(module)

    assert any(
        "out-of-band" in error
        for error in module.validate_multi_agent_efficiency_baseline_manifest(
            manifest,
            corpus=corpus,
            registry=registry,
        )
    )
    verifier = _ExactManifestVerifier()
    assert (
        module.validate_multi_agent_efficiency_baseline_manifest(
            manifest,
            corpus=corpus,
            registry=registry,
            manifest_verifier=verifier,
        )
        == []
    )
    assert verifier.binding["manifest_digest"] == manifest["manifest_digest"]
    assert verifier.binding["corpus_digest"] == corpus["corpus_digest"]
    assert verifier.binding["policy_digest"] == registry[
        "efficiency_evaluation_policy"
    ]["policy_digest"]
    assert verifier.binding["registry_digest"] == manifest["registry_binding"][
        "registry_digest"
    ]
    assert verifier.binding["source_generation_digest"] == manifest[
        "source_generation"
    ]["generation_digest"]
    assert len(verifier.binding["run_ids"]) == 16


def test_manifest_derives_sentinel_metrics_from_observed_receipts() -> None:
    module = _load_module()
    manifest, corpus, registry = _platform_manifest(module)
    quality = next(
        record
        for record in manifest["candidate_profile_records"]
        if record["case_id"] == "quality-independent-gold-oracle-v1"
    )
    quality["runs"][0]["observed_facts"]["finding_ids"] = []
    _resign_manifest(module, manifest)

    errors = module.validate_multi_agent_efficiency_baseline_manifest(
        manifest,
        corpus=corpus,
        registry=registry,
        manifest_verifier=_ExactManifestVerifier(),
    )
    assert any("derived" in error and "missed_p0_p1_count" in error for error in errors)
    assert any("derived" in error and "p0_p1_recall_ratio" in error for error in errors)

    manifest, corpus, registry = _platform_manifest(module)
    safety = next(
        record
        for record in manifest["candidate_profile_records"]
        if record["case_id"] == "safety-full-audit-fixed-graph-v1"
    )
    safety["runs"][0]["observed_facts"]["route_edges"].remove(
        "pm_triage->full_audit"
    )
    _resign_manifest(module, manifest)
    errors = module.validate_multi_agent_efficiency_baseline_manifest(
        manifest,
        corpus=corpus,
        registry=registry,
        manifest_verifier=_ExactManifestVerifier(),
    )
    assert any(
        "derived" in error and "full_audit_sentinel_match" in error
        for error in errors
    )


@pytest.mark.parametrize("attack", ("disqualified", "over_target"))
def test_manifest_adoption_qualifies_both_current_and_candidate_arms(
    attack: str,
) -> None:
    module = _load_module()
    manifest, corpus, registry = _platform_manifest(module)
    current_q0 = next(
        record
        for record in manifest["current_profile_records"]
        if record["case_id"] == "q0-pm-only-read-only-governance-query-v1"
    )
    if attack == "disqualified":
        current_q0["runs"][0]["qualification_status"] = "disqualified"
    else:
        current_q0["runs"][0]["metrics"]["elapsed_time_ms"]["value"] = 300001
    _resign_manifest(module, manifest)

    errors = module.validate_multi_agent_efficiency_baseline_manifest(
        manifest,
        corpus=corpus,
        registry=registry,
        manifest_verifier=_ExactManifestVerifier(),
    )
    assert any("A_CURRENT" in error and "adoption" in error for error in errors)


def test_legacy_policy_digest_is_fixture_only_and_result_reports_current_policy() -> None:
    module = _load_module()
    legacy = _fixture()
    result = module.evaluate_multi_agent_efficiency(legacy)
    assert result["quality_noninferiority_policy"]["policy_digest"] == (
        module._registry_efficiency_evaluation_policy()["policy_digest"]
    )

    forged = _fixture()
    forged["evidence_kind"] = "platform_or_external_attested"
    for index, profile in enumerate(forged["profiles"]):
        profile.update(
            measurement_status="measured",
            evidence_ref=f"forged:{index}",
            evidence_digest="sha256:" + str(index + 1) * 64,
        )
    forged["record_digest"] = module.multi_agent_efficiency_evaluation_digest(
        forged
    )
    assert any(
        "legacy" in error
        for error in module.validate_multi_agent_efficiency_evaluation(forged)
    )


@pytest.mark.parametrize(
    "field",
    (
        "efficiency_baseline_corpus_schema_path",
        "efficiency_baseline_manifest_schema_path",
    ),
)
def test_registry_rejects_efficiency_baseline_schema_path_drift(field: str) -> None:
    import agent_governance as governance

    registry = governance.load_registry()
    registry[field] = ".codex/schemas/closure_quality_attestation_v1.schema.json"

    assert any(
        field in error for error in governance.validate_registry(registry, ROOT)
    )


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
            "call_record_digests": sorted(
                "sha256:"
                + hashlib.sha256(
                    f"profile-{index}-call-{call_index}".encode("utf-8")
                ).hexdigest()
                for call_index in range(profile["metrics"]["calls"])
            ),
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
        "minimum_required_coverage_ratio": 1.0,
        "max_reopen_count_increase": 0,
        "max_rework_count_increase": 0,
        "max_false_closure_count_increase": 0,
        "minimum_p0_p1_recall_ratio": 1.0,
        "minimum_decision_changing_findings_retention_ratio": 1.0,
    }
    assert policy["efficiency_improvement"] == {
        "predicate": "all_axes_non_worse_and_one_strictly_better_v1",
        "axes": [
            "elapsed_time_ms",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "calls",
            "waits",
            "retries",
            "compactions",
        ],
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


@pytest.mark.parametrize(
    ("field_path", "replacement"),
    (
        (("thresholds", "max_closure_quality_score_drop"), 0),
        (("synthetic_measured_claim_allowed",), 0),
    ),
)
def test_registry_policy_rejects_json_type_substitution_after_resigning(
    field_path: tuple[str, ...],
    replacement: object,
) -> None:
    import agent_governance as governance

    registry = governance.load_registry()
    policy = registry["efficiency_evaluation_policy"]
    target = policy
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = replacement
    policy["policy_digest"] = governance.efficiency_evaluation_policy_digest(
        policy
    )

    assert any(
        "exact JSON types" in error
        for error in governance.validate_registry(registry, ROOT)
    )


@pytest.mark.parametrize(
    "mutation",
    ("predicate", "axes_remove", "axes_reorder", "axes_add"),
)
def test_registry_policy_rejects_relaxed_pareto_authority_after_resigning(
    mutation: str,
) -> None:
    import agent_governance as governance

    registry = governance.load_registry()
    policy = registry["efficiency_evaluation_policy"]
    improvement = policy["efficiency_improvement"]
    if mutation == "predicate":
        improvement["predicate"] = "any_axis_strictly_better_v1"
    elif mutation == "axes_remove":
        improvement["axes"].remove("output_tokens")
    elif mutation == "axes_reorder":
        improvement["axes"] = list(reversed(improvement["axes"]))
    else:
        improvement["axes"].append("tool_calls")
    policy["policy_digest"] = governance.efficiency_evaluation_policy_digest(
        policy
    )

    assert any(
        "all-axes non-worse" in error
        for error in governance.validate_registry(registry, ROOT)
    )


def test_governance_doc_names_every_registry_threshold_and_pareto_axis() -> None:
    import agent_governance as governance

    policy = governance.load_registry()["efficiency_evaluation_policy"]
    documented = GOVERNANCE_DOC_PATH.read_text(encoding="utf-8")

    for threshold in policy["thresholds"]:
        assert f"`{threshold}=" in documented
    improvement = policy["efficiency_improvement"]
    assert f"`{improvement['predicate']}`" in documented
    for axis in improvement["axes"]:
        assert f"`{axis}`" in documented


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


def test_profile_retries_cannot_exceed_reported_calls() -> None:
    module = _load_module()
    fixture = _fixture()
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"]["calls"] = 0
    _resign(module, fixture)

    assert any(
        "retries cannot exceed calls" in error
        for error in module.validate_multi_agent_efficiency_evaluation(fixture)
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
        "required_coverage_ratio",
        "reopen_count",
        "rework_count",
        "false_closure_count",
        "p0_p1_recall_ratio",
        "decision_changing_findings",
    }
    assert single["efficiency_claim_allowed"] is False


def test_efficiency_claim_requires_at_least_one_strict_improvement() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    current = _profile(fixture, "current")
    bounded = _profile(fixture, "bounded_role")
    for metric in module.EFFICIENCY_METRICS:
        bounded["metrics"][metric] = current["metrics"][metric]
    attestation = attestation_index["records"][bounded["evidence_ref"]]
    attestation["call_record_digests"] = sorted(
        "sha256:"
        + hashlib.sha256(f"profile-2-call-{index}".encode("utf-8")).hexdigest()
        for index in range(bounded["metrics"]["calls"])
    )
    attestation["metrics_payload_digest"] = _canonical_digest(bounded["metrics"])
    attestation.pop("record_digest")
    attestation["record_digest"] = _canonical_digest(attestation)
    bounded["evidence_digest"] = attestation["record_digest"]
    _resign(module, fixture)
    attestation_index.pop("record_digest")
    attestation_index["record_digest"] = _canonical_digest(attestation_index)

    class ExactVerifier:
        def verify_efficiency_attestation_index(self, **_binding) -> bool:
            return True

    result = module.evaluate_multi_agent_efficiency(
        fixture,
        attestation_index=attestation_index,
        attestation_verifier=ExactVerifier(),
    )
    comparison = result["comparisons"]["bounded_role"]

    assert comparison["efficiency_improvement"]["status"] == "FAIL"
    assert comparison["efficiency_improvement"]["strictly_improved_axes"] == []
    assert comparison["efficiency_improvement"]["worse_axes"] == []
    assert comparison["efficiency_claim_allowed"] is False
    assert result["measured_efficiency_candidates"] == []


def test_synthetic_benchmark_candidate_also_requires_pareto_improvement() -> None:
    module = _load_module()
    fixture = _fixture()
    current = _profile(fixture, "current")
    bounded = _profile(fixture, "bounded_role")
    for metric in module.EFFICIENCY_METRICS:
        bounded["metrics"][metric] = current["metrics"][metric]
    _resign(module, fixture)

    result = module.evaluate_multi_agent_efficiency(fixture)

    assert (
        result["comparisons"]["bounded_role"]["efficiency_improvement"]["status"]
        == "FAIL"
    )
    assert result["benchmark_only_candidates"] == []


def test_efficiency_claim_rejects_any_worse_efficiency_axis() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    current = _profile(fixture, "current")
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"]["output_tokens"] = (
        current["metrics"]["output_tokens"] + 1
    )
    attestation = attestation_index["records"][bounded["evidence_ref"]]
    attestation["metrics_payload_digest"] = _canonical_digest(bounded["metrics"])
    attestation.pop("record_digest")
    attestation["record_digest"] = _canonical_digest(attestation)
    bounded["evidence_digest"] = attestation["record_digest"]
    _resign(module, fixture)
    attestation_index.pop("record_digest")
    attestation_index["record_digest"] = _canonical_digest(attestation_index)

    class ExactVerifier:
        def verify_efficiency_attestation_index(self, **_binding) -> bool:
            return True

    result = module.evaluate_multi_agent_efficiency(
        fixture,
        attestation_index=attestation_index,
        attestation_verifier=ExactVerifier(),
    )
    comparison = result["comparisons"]["bounded_role"]

    assert comparison["efficiency_improvement"]["status"] == "FAIL"
    assert comparison["efficiency_improvement"]["worse_axes"] == [
        "output_tokens"
    ]
    assert comparison["efficiency_improvement"]["strictly_improved_axes"]
    assert comparison["efficiency_claim_allowed"] is False
    assert result["measured_efficiency_candidates"] == []


def test_quality_noninferiority_requires_complete_required_coverage() -> None:
    module = _load_module()
    fixture = _fixture()
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"]["required_coverage_ratio"] = 0.99
    _resign(module, fixture)

    result = module.evaluate_multi_agent_efficiency(fixture)
    comparison = result["comparisons"]["bounded_role"]

    assert comparison["quality_noninferiority"]["status"] == "FAIL"
    assert comparison["quality_noninferiority"]["checks"][
        "required_coverage_ratio"
    ] == {
        "status": "FAIL",
        "baseline": 1.0,
        "candidate": 0.99,
        "threshold": 1.0,
    }
    assert comparison["efficiency_claim_allowed"] is False


def test_quality_noninferiority_rejects_additional_rework() -> None:
    module = _load_module()
    fixture = _fixture()
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"]["rework_count"] = 2
    _resign(module, fixture)

    result = module.evaluate_multi_agent_efficiency(fixture)
    check = result["comparisons"]["bounded_role"]["quality_noninferiority"][
        "checks"
    ]["rework_count"]

    assert check == {
        "status": "FAIL",
        "baseline": 1,
        "candidate": 2,
        "threshold": 1,
    }
    assert (
        result["comparisons"]["bounded_role"]["quality_noninferiority"]["status"]
        == "FAIL"
    )


def test_quality_noninferiority_rejects_additional_false_closures() -> None:
    module = _load_module()
    fixture = _fixture()
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"]["false_closure_count"] = 1
    _resign(module, fixture)

    result = module.evaluate_multi_agent_efficiency(fixture)
    check = result["comparisons"]["bounded_role"]["quality_noninferiority"][
        "checks"
    ]["false_closure_count"]

    assert check == {
        "status": "FAIL",
        "baseline": 0,
        "candidate": 1,
        "threshold": 0,
    }
    assert (
        result["comparisons"]["bounded_role"]["quality_noninferiority"]["status"]
        == "FAIL"
    )


def test_quality_noninferiority_requires_complete_p0_p1_recall() -> None:
    module = _load_module()
    fixture = _fixture()
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"]["p0_p1_recall_ratio"] = 0.99
    _resign(module, fixture)

    result = module.evaluate_multi_agent_efficiency(fixture)
    check = result["comparisons"]["bounded_role"]["quality_noninferiority"][
        "checks"
    ]["p0_p1_recall_ratio"]

    assert check == {
        "status": "FAIL",
        "baseline": 1.0,
        "candidate": 0.99,
        "threshold": 1.0,
    }
    assert (
        result["comparisons"]["bounded_role"]["quality_noninferiority"]["status"]
        == "FAIL"
    )


@pytest.mark.parametrize(
    "metric",
    [
        "required_coverage_ratio",
        "rework_count",
        "false_closure_count",
        "p0_p1_recall_ratio",
    ],
)
def test_adr_quality_metrics_cannot_be_omitted(metric: str) -> None:
    module = _load_module()
    fixture = _fixture()
    del _profile(fixture, "bounded_role")["metrics"][metric]
    _resign(module, fixture)

    errors = module.validate_multi_agent_efficiency_evaluation(fixture)

    assert any(
        f"missing required property {metric}" in error
        or "metric fields differ from the contract" in error
        for error in errors
    )
    with pytest.raises(ValueError):
        module.evaluate_multi_agent_efficiency(fixture)


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
            sorted(
                digest
                for attestation in attestation_index["records"].values()
                for digest in attestation["call_record_digests"]
            )
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


def test_attestation_index_exactly_covers_each_profiles_reported_calls() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    reference = next(iter(attestation_index["records"]))
    attestation = attestation_index["records"][reference]
    attestation["call_record_digests"].pop()
    attestation["record_digest"] = _canonical_digest(attestation)
    _profile(fixture, attestation["profile"])["evidence_digest"] = attestation[
        "record_digest"
    ]
    _resign(module, fixture)
    attestation_index["record_digest"] = _canonical_digest(attestation_index)

    assert any(
        "must exactly cover metrics.calls" in error
        for error in module.validate_efficiency_attestation_index(
            fixture,
            attestation_index,
        )
    )


def test_partial_profile_with_unavailable_calls_rejects_nonempty_inventory() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    bounded = _profile(fixture, "bounded_role")
    bounded["measurement_status"] = "partial"
    bounded["unavailable_reason"] = "platform call total unavailable"
    bounded["metrics"]["calls"] = None
    attestation = attestation_index["records"][bounded["evidence_ref"]]
    attestation["metrics_payload_digest"] = _canonical_digest(bounded["metrics"])
    attestation.pop("record_digest")
    attestation["record_digest"] = _canonical_digest(attestation)
    bounded["evidence_digest"] = attestation["record_digest"]
    _resign(module, fixture)
    attestation_index.pop("record_digest")
    attestation_index["record_digest"] = _canonical_digest(attestation_index)

    assert any(
        "unavailable metrics.calls requires an empty call-record inventory"
        in error
        for error in module.validate_efficiency_attestation_index(
            fixture,
            attestation_index,
        )
    )


def test_partial_profile_with_unavailable_calls_accepts_empty_inventory() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    bounded = _profile(fixture, "bounded_role")
    bounded["measurement_status"] = "partial"
    bounded["unavailable_reason"] = "platform call total unavailable"
    bounded["metrics"]["calls"] = None
    attestation = attestation_index["records"][bounded["evidence_ref"]]
    attestation["call_record_digests"] = []
    attestation["metrics_payload_digest"] = _canonical_digest(bounded["metrics"])
    attestation.pop("record_digest")
    attestation["record_digest"] = _canonical_digest(attestation)
    bounded["evidence_digest"] = attestation["record_digest"]
    _resign(module, fixture)
    attestation_index.pop("record_digest")
    attestation_index["record_digest"] = _canonical_digest(attestation_index)

    assert (
        module.validate_efficiency_attestation_index(
            fixture,
            attestation_index,
        )
        == []
    )


def test_zero_reported_calls_require_an_exact_empty_call_inventory() -> None:
    module = _load_module()
    fixture, attestation_index = _measured_with_attestation_index(module)
    bounded = _profile(fixture, "bounded_role")
    bounded["metrics"]["calls"] = 0
    bounded["metrics"]["retries"] = 0
    attestation = attestation_index["records"][bounded["evidence_ref"]]
    attestation["call_record_digests"] = []
    attestation["metrics_payload_digest"] = _canonical_digest(bounded["metrics"])
    attestation.pop("record_digest")
    attestation["record_digest"] = _canonical_digest(attestation)
    bounded["evidence_digest"] = attestation["record_digest"]
    _resign(module, fixture)
    attestation_index.pop("record_digest")
    attestation_index["record_digest"] = _canonical_digest(attestation_index)

    assert (
        module.validate_efficiency_attestation_index(
            fixture,
            attestation_index,
        )
        == []
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
