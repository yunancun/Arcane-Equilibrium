from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_registry import load_registry, validate_registry  # noqa: E402
from agent_governance_routing import route_task  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
import agent_governance_aiml_adoption as aiml_adoption  # noqa: E402
import agent_governance_closure as closure_validation  # noqa: E402
import agent_governance_evidence as governance_evidence  # noqa: E402
from agent_governance_closure_inputs import (  # noqa: E402
    normalize_closure_packet_inputs,
)


S0_1_RECEIPT = "sha256:8fc9417f984025deabdc1b83ace95921ccfff1acb26a1b29243fc0a0a5ba79ad"
S0_2_RECEIPT = "sha256:0115dbd3dc62d84e183aae5a28cbfd252eb45ecee51a652d8a4a155f14dfb41a"
GITHUB_POLICY_ATTESTATION = "sha256:" + "a" * 64
SCHEMA_ROOT = "program_code/ml_training/schemas/aiml_gate_receipts"
SCHEMA_PATHS = [
    f"{SCHEMA_ROOT}/aiml_receipt_dependency_graph_v1.schema.json",
    f"{SCHEMA_ROOT}/aiml_required_effect_classification_v1.schema.json",
    f"{SCHEMA_ROOT}/github_repository_policy_attestation_v1.schema.json",
    f"{SCHEMA_ROOT}/landing_scope_v1.schema.json",
    f"{SCHEMA_ROOT}/program_adoption_receipt_v1.schema.json",
    f"{SCHEMA_ROOT}/session_attempt_v1.schema.json",
    f"{SCHEMA_ROOT}/terminal_receipt_sink_v1.schema.json",
]
CLAIM_KEYS = [
    "aiml_github_policy_attestation",
    "aiml_program_adoption_selection",
    "aiml_program_s0_1_receipt",
    "aiml_program_s0_2_receipt",
]
GENERIC_GOVERNANCE_TEST_PATH = (
    ROOT / "tests/structure/test_development_agent_governance.py"
)


def _digest(value: object) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _selection_digest() -> str:
    return _digest({
        "issuer_session": "S0.3",
        "schema_version": "aiml_program_adoption_selection_v1",
        "workflow_contract": "aiml_program_adoption_v1",
    })


def _claims() -> dict[str, str]:
    return {
        "aiml_github_policy_attestation": GITHUB_POLICY_ATTESTATION,
        "aiml_program_adoption_selection": _selection_digest(),
        "aiml_program_s0_1_receipt": S0_1_RECEIPT,
        "aiml_program_s0_2_receipt": S0_2_RECEIPT,
    }


def _finalization_facts() -> dict[str, object]:
    return {
        "task_shape": "query",
        "surfaces": [
            "acceptance", "authority", "closure", "governance", "ml_data",
            "policy", "schema",
        ],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "task_prompt": "finalize AIML Program adoption from source evidence",
        "claim_inputs": _claims(),
    }


def _load_generic_governance_test_support():
    spec = importlib.util.spec_from_file_location(
        "aiml_generic_governance_test_support", GENERIC_GOVERNANCE_TEST_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Finding 1:採納收尾 DAG 的 7 個強制 reviewer(node_id 等同 PROGRAM_REVIEW_NODES 值)。
_ADOPTION_REVIEW_NODES = [
    ("E2", "independent_review"),
    ("E4", "regression"),
    ("CC", "constitutional_gate"),
    ("E3", "security_gate"),
    ("MIT", "data_ml_review"),
    ("R4", "docs_integrity_review"),
    ("QA", "business_acceptance"),
]


def _adoption_review_control(governance, node_id, task_facts, generation):
    """單一 reviewer、無 blocker 的 review_control,final_generation 綁定可信位元代。"""

    return {
        "schema_version": "review_control_v1",
        "task_contract_digest": governance.review_task_contract_digest(task_facts),
        "non_goals": ["expand beyond the source-only adoption review"],
        "final_generation": generation,
        "reviewers": [{
            "node_id": node_id,
            "rounds": [{
                "round": 1,
                "kind": "initial",
                "reviewed_generation": generation,
                "findings": [],
            }],
        }],
    }


def _adoption_review_fragment(
    governance, role, node_id, task_contract_digest, context_digest,
    evidence_refs, generation, task_facts,
):
    return {
        "schema_version": "role_fragment_v1",
        "id": f"frag-{node_id}",
        "node_id": node_id,
        "role": role,
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "classification": "FACT",
        "confidence": "high",
        "summary": f"{role} review of the source-only adoption bundle passed",
        "task_contract_digest": task_contract_digest,
        "context_artifact_digest": context_digest,
        "producer_call_ref": "pending-standard-lineage",
        "producer_call_receipt_digest": "sha256:" + "0" * 64,
        "producer_record_kind": "workflow_call_record_v1",
        "evidence_refs": evidence_refs,
        "concerns": [],
        "next_action": None,
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform telemetry unavailable",
        },
        "payload_kind": governance.load_registry()["roles"][role]["payload_kind"],
        "payload": {
            "review_control": _adoption_review_control(
                governance, node_id, task_facts, generation
            )
        },
    }


def test_validate_closure_accepts_exact_program_adoption_only_with_trust_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    support = _load_generic_governance_test_support()
    governance = support._load_module()
    source_baseline = governance.capture_repository_baseline()
    criterion = (
        "the exact source-only AIML Program adoption bundle is accepted without "
        "granting runtime or effect authority"
    )
    objective = "finalize source-only AIML Program adoption"
    scope = [
        ".codex/agent_registry_v1.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/program_adoption_receipt_v1.schema.json",
    ]
    facts = {
        **_finalization_facts(),
        "objective": objective,
        "scope": scope,
        "acceptance_criteria": [criterion],
        "hard_stops": [
            "do not claim runtime, deployment, broker, order, ML5, or ML6 authority",
        ],
        "baseline": source_baseline,
        "direct_interfaces": [],
        "previous_failure": (
            "the Program-adoption seam lacked a complete generic closure PASS"
        ),
    }
    route = governance.route_task(facts)
    task_facts = route["task_facts"]
    context_plan = governance.compile_context("PM", task_facts)
    assert context_plan["budget"]["claim_pass_eligible"] is True
    context_artifact = governance.materialize_context_artifact(context_plan)
    task_contract_digest = context_plan["task_contract_digest"]
    context_digest = context_artifact["artifact_digest"]
    repository_capture = governance.capture_repository(task_facts["dirty_scope"])
    # E4 regression 需直接 test 證據:一個綁定 role_id=E4/node=regression 的本地
    # command capture。Finding 2 已在 merge_head blob 驗過測試檔一致,故此重放合法。
    e4_command = "git rev-parse HEAD"
    e4_capture = governance.capture_command(
        role_id="E4",
        node_id="regression",
        task_contract_digest=task_contract_digest,
        command=e4_command,
        scope=task_facts["dirty_scope"],
    )
    adjudicated_at = (
        datetime.now(timezone.utc) + timedelta(seconds=2)
    ).isoformat().replace("+00:00", "Z")
    baseline = {
        **source_baseline,
        "runtime_head": None,
        "runtime_observed_at": None,
    }
    # review_generation == 可信 repo 位元代;7 個 reviewer 的 final_generation 與
    # receipt.review_generation 皆綁定它。
    review_generation = dict(source_baseline)
    task_specs, projection_errors = governance.delegated_execution_projection(
        route["required_role_nodes"],
        [],
        excluded_nodes=governance.non_call_controller_node_ids(task_facts),
    )
    assert projection_errors == []
    dag_digest = governance.execution_dag_digest(task_specs)
    artifacts = {
        "s0_1_receipt": {"self_digest": S0_1_RECEIPT},
        "s0_2_receipt": {"self_digest": S0_2_RECEIPT},
        "source_attempt": {},
        "finalization_attempt": {
            "bootstrap_admission": {
                "task_id": "AIML-S0-3-GOVERNANCE-V1",
                "task_contract_digest": task_contract_digest,
                "dag_digest": dag_digest,
                "context_artifact_digest": context_digest,
                "baseline_head": baseline["source_head"],
            },
        },
        "effect_classification": {},
        "dependency_graph": {},
        "github_attestation": {"self_digest": GITHUB_POLICY_ATTESTATION},
        "terminal_sink_contract": {},
    }
    bundle = {
        "receipt": {
            "adoption_id": "program-adoption",
            "review_generation": review_generation,
            "review_bindings": [
                {
                    "role": role,
                    "node_id": node_id,
                    "verdict": "PASS",
                    "fragment_id": f"frag-{node_id}",
                }
                for role, node_id in _ADOPTION_REVIEW_NODES
            ],
        },
        "artifacts": artifacts,
    }
    review_evidence_refs = {
        node_id: (
            ["ev-e4-command"]
            if node_id == "regression"
            else ["finalization-source-capture", "program-adoption"]
            if node_id == "business_acceptance"
            else ["finalization-source-capture"]
        )
        for _role, node_id in _ADOPTION_REVIEW_NODES
    }
    role_fragments = [
        _adoption_review_fragment(
            governance, role, node_id, task_contract_digest, context_digest,
            review_evidence_refs[node_id], review_generation, task_facts,
        )
        for role, node_id in _ADOPTION_REVIEW_NODES
    ]
    authority_refs = deepcopy(
        support._valid_failed_review_closure()["authority_refs"]
    )
    packet = {
        "schema_version": "closure_packet_v1",
        "task_id": "AIML-S0-3-GOVERNANCE-V1",
        "human_summary": {
            "objective": objective,
            "scope": scope,
            "outcome": "source-only AIML Program adoption evidence accepted",
        },
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "disposition": "NO_CHANGE_NEEDED",
        "confidence": "high",
        "adjudicated_at": adjudicated_at,
        "baseline": baseline,
        "dispatch": {
            "task_facts": task_facts,
            "context_artifact": context_artifact,
            "dag_digest": dag_digest,
            "required_role_nodes": route["required_role_nodes"],
            "admitted_role_nodes": [],
        },
        "authority_refs": authority_refs,
        "acceptance": [{
            "criterion": criterion,
            "status": "PASS",
            "evidence_refs": ["finalization-source-capture", "program-adoption"],
        }],
        "evidence": [
            {
                "id": "program-adoption",
                "scope": "data",
                "kind": "program_adoption_receipt_v1",
                "digest": _digest(bundle),
                "artifact": bundle,
            },
            {
                "id": "finalization-source-capture",
                "scope": "source",
                "kind": "repository_capture_v1",
                "digest": repository_capture["record_digest"],
                "observed_at": repository_capture["observed_at"],
                "artifact": repository_capture,
            },
            {
                "id": "ev-e4-command",
                "scope": "test",
                "kind": "command_capture_v1",
                "digest": e4_capture["record_digest"],
                "artifact": e4_capture,
            },
        ],
        "role_fragments": role_fragments,
        "checks": [{
            "id": "check-e4-regression",
            "status": "EXECUTED",
            "command": e4_command,
            "signature": e4_capture["record_digest"],
            "evidence_ref": "ev-e4-command",
            "command_capture_ref": "ev-e4-command",
            "executed_at": e4_capture["completed_at"],
        }],
        "side_effects": {
            "repo_mutation": False,
            "runtime_contact": False,
            "private_external_contact": False,
            "broker_effect": False,
        },
        "unverified": [],
        "skipped_roles": route["skipped"],
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "pending standard workflow lineage",
        },
        "next_action": None,
    }
    support._refresh_standard_workflow_lineage(governance, packet)

    missing_external = (
        "program adoption requires caller-supplied external GitHub verification"
    )
    missing_source = (
        "program adoption requires caller-supplied source manifest verification"
    )

    def canonical_validator(receipt: object, **kwargs: object) -> list[str]:
        assert receipt == bundle["receipt"]
        assert kwargs["artifacts"] == bundle["artifacts"]
        assert kwargs["now"] == packet["adjudicated_at"]
        errors = []
        if kwargs["external_verifier"] is None:
            errors.append(missing_external)
        if kwargs["source_manifest_verifier"] is None:
            errors.append(missing_source)
        return errors

    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", canonical_validator,
    )
    execution_verifier = support._test_execution_attestation_verifier(packet)
    external_verifier = lambda artifact: artifact is not None
    source_verifier = lambda reviewed, merged, manifest: True

    assert governance.validate_closure(
        packet,
        execution_attestation_verifier=execution_verifier,
        external_evidence_verifier=external_verifier,
        source_manifest_verifier=source_verifier,
    ) == []

    # Finding 1 負向 (iv):即便 7 個 review fragment 齊備,若無 out-of-band
    # execution_attestation_verifier,wave record 無法被認證,validate_closure 經
    # validate_execution_attestations 失敗關閉。
    forged_without_attestation = governance.validate_closure(
        packet,
        external_evidence_verifier=external_verifier,
        source_manifest_verifier=source_verifier,
    )
    assert any(
        "lacks out-of-band execution attestation" in error
        for error in forged_without_attestation
    )

    without_external = governance.validate_closure(
        packet,
        execution_attestation_verifier=execution_verifier,
        source_manifest_verifier=source_verifier,
    )
    assert without_external == [missing_external]
    without_source = governance.validate_closure(
        packet,
        execution_attestation_verifier=execution_verifier,
        external_evidence_verifier=external_verifier,
    )
    assert without_source == [missing_source]

    # 移除 finalization-source-capture:讀取型 reviewer 失去可直接擷取的證據,採納
    # receipt(data scope)不能取代 repository/command capture,採納 PASS 失敗關閉。
    adoption_only = deepcopy(packet)
    adoption_only["evidence"] = [
        evidence for evidence in adoption_only["evidence"]
        if evidence["id"] != "finalization-source-capture"
    ]
    adoption_only["acceptance"][0]["evidence_refs"] = ["program-adoption"]
    for fragment in adoption_only["role_fragments"]:
        remaining = [
            ref for ref in fragment["evidence_refs"]
            if ref != "finalization-source-capture"
        ]
        fragment["evidence_refs"] = remaining or ["program-adoption"]
    support._refresh_standard_workflow_lineage(governance, adoption_only)
    adoption_only_errors = governance.validate_closure(
        adoption_only,
        execution_attestation_verifier=(
            support._test_execution_attestation_verifier(adoption_only)
        ),
        external_evidence_verifier=external_verifier,
        source_manifest_verifier=source_verifier,
    )
    assert any(
        "lacks direct captured source/test/attested evidence" in error
        for error in adoption_only_errors
    )
    assert (
        "acceptance[0] source/test PASS requires repository or command capture"
        in adoption_only_errors
    )


def _program_adoption_packet() -> tuple[dict[str, object], dict[str, object], str]:
    task_contract_digest = "sha256:" + "1" * 64
    dag_digest = "sha256:" + "2" * 64
    context_digest = "sha256:" + "3" * 64
    baseline_head = "4" * 40
    artifacts = {
        "s0_1_receipt": {"self_digest": S0_1_RECEIPT},
        "s0_2_receipt": {"self_digest": S0_2_RECEIPT},
        "source_attempt": {},
        "finalization_attempt": {
            "bootstrap_admission": {
                "task_id": "AIML-S0-3-GOVERNANCE-V1",
                "task_contract_digest": task_contract_digest,
                "dag_digest": dag_digest,
                "context_artifact_digest": context_digest,
                "baseline_head": baseline_head,
            },
        },
        "effect_classification": {},
        "dependency_graph": {},
        "github_attestation": {"self_digest": GITHUB_POLICY_ATTESTATION},
        "terminal_sink_contract": {},
    }
    # Finding 1:7 個 reviewer 綁定與其 PASS role_fragment 的最小化正向樣本,供
    # validate_program_adoption_closure_binding 的直接綁定測試使用。
    review_generation = {
        "source_head": baseline_head,
        "dirty_diff_hash": "sha256:" + "a" * 64,
        "untracked_relevant_hash": "sha256:" + "b" * 64,
    }
    review_bindings = [
        {
            "role": role,
            "node_id": node_id,
            "verdict": "PASS",
            "fragment_id": f"frag-{node_id}",
        }
        for role, node_id in aiml_adoption.PROGRAM_REVIEW_NODES.items()
    ]
    role_fragments = [
        {
            "id": f"frag-{node_id}",
            "node_id": node_id,
            "role": role,
            "gate_verdict": "PASS",
            "payload": {"review_control": {"final_generation": review_generation}},
        }
        for role, node_id in aiml_adoption.PROGRAM_REVIEW_NODES.items()
    ]
    bundle = {
        "receipt": {
            "adoption_id": "program-adoption",
            "review_bindings": review_bindings,
            "review_generation": review_generation,
        },
        "artifacts": artifacts,
    }
    packet = {
        "task_id": "AIML-S0-3-GOVERNANCE-V1",
        "gate_verdict": "PASS",
        "adjudicated_at": "2026-07-21T12:00:00Z",
        "baseline": {"source_head": baseline_head},
        "dispatch": {
            "task_facts": _finalization_facts(),
            "dag_digest": dag_digest,
            "context_artifact": {"artifact_digest": context_digest},
        },
        "role_fragments": role_fragments,
        "evidence": [{
            "id": "program-adoption",
            "scope": "data",
            "kind": "program_adoption_receipt_v1",
            "digest": _digest(bundle),
            "artifact": bundle,
        }],
        "side_effects": {
            "repo_mutation": False,
            "runtime_contact": False,
            "private_external_contact": False,
            "broker_effect": False,
        },
    }
    return packet, route_task(_finalization_facts()), task_contract_digest


def _real_closure_harness(
    program_packet: dict[str, object],
) -> tuple[object, object, dict[str, object]]:
    support = _load_generic_governance_test_support()
    governance = support._load_module()
    packet = support._valid_failed_review_closure()
    packet["gate_verdict"] = "PASS"
    packet["work_status"] = "DONE"
    packet["disposition"] = "NO_CHANGE_NEEDED"
    packet["next_action"] = None
    packet["side_effects"] = {
        "repo_mutation": False,
        "runtime_contact": False,
        "private_external_contact": False,
        "broker_effect": False,
    }
    packet["dispatch"]["task_facts"] = deepcopy(_finalization_facts())
    packet["evidence"].append(program_packet["evidence"][0])
    return support, governance, packet


def test_trusted_host_time_rejects_packet_rollback_and_drives_canonical_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    support, governance, packet = _real_closure_harness(program_packet)
    packet_time = datetime.fromisoformat(
        str(packet["adjudicated_at"]).replace("Z", "+00:00")
    )
    host_time = packet_time + timedelta(seconds=30)
    observed_now: list[object] = []

    def canonical_validator(_receipt: object, **kwargs: object) -> list[str]:
        observed_now.append(kwargs["now"])
        return []

    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", canonical_validator,
    )
    verifier = support._test_execution_attestation_verifier(packet)
    common = {
        "execution_attestation_verifier": verifier,
        "external_evidence_verifier": lambda artifact: artifact is not None,
        "source_manifest_verifier": lambda reviewed, merged, manifest: True,
        "trusted_evaluated_at": host_time,
    }

    in_window_errors = governance.validate_closure(packet, **common)
    assert not any("trusted host evaluation time" in error for error in in_window_errors)
    assert observed_now[-1] == host_time.isoformat()

    rolled_back = deepcopy(packet)
    rolled_back["adjudicated_at"] = (
        host_time - timedelta(minutes=2)
    ).isoformat().replace("+00:00", "Z")
    rollback_errors = governance.validate_closure(rolled_back, **common)
    assert (
        "packet adjudicated_at is not bound to trusted host evaluation time"
        in rollback_errors
    )
    assert observed_now[-1] == host_time.isoformat()


def test_normalize_closure_packet_inputs_is_shallow_indexed_and_non_mutating() -> None:
    authority_a = {"id": "authority-a"}
    authority_b = {"id": "authority-b"}
    valid_acceptance = {"criterion": "valid", "evidence_refs": []}
    nested_marker = {"preserve": None}
    malformed_acceptance = {
        "criterion": "malformed",
        "evidence_refs": None,
        "nested": nested_marker,
    }
    packet = {
        "human_summary": {"objective": "test"},
        "baseline": {"source_head": "a" * 40},
        "dispatch": {"task_facts": {"task_shape": "query"}},
        "side_effects": {},
        "consumption": {},
        "authority_refs": [authority_a, None, authority_b],
        "acceptance": [valid_acceptance, malformed_acceptance],
        "evidence": [],
        "role_fragments": [],
        "checks": [],
        "skipped_roles": [],
        "unverified": [],
    }
    original = deepcopy(packet)

    safe_packet, errors = normalize_closure_packet_inputs(packet)

    assert packet == original
    assert safe_packet is not packet
    assert safe_packet["human_summary"] is packet["human_summary"]
    assert safe_packet["baseline"] is packet["baseline"]
    assert safe_packet["dispatch"] is packet["dispatch"]
    assert safe_packet["authority_refs"][0] is authority_a
    assert safe_packet["authority_refs"][1] == {}
    assert safe_packet["authority_refs"][2] is authority_b
    assert safe_packet["acceptance"][0] is valid_acceptance
    assert safe_packet["acceptance"][1] is not malformed_acceptance
    assert safe_packet["acceptance"][1]["nested"] is nested_marker
    assert safe_packet["acceptance"][1]["evidence_refs"] == []
    assert errors == [
        "authority_refs[1] must be an object",
        "closure acceptance[1].evidence_refs must be a list",
    ]


def _assert_malformed_program_adoption_bundle_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    packet: dict[str, object],
    expected_route: dict[str, object],
    task_contract_digest: str,
    mapping_error: str,
) -> None:
    bundle = packet["evidence"][0]["artifact"]
    original_receipt = bundle["receipt"]
    original_artifacts = bundle["artifacts"]
    canonical_error = "canonical validator rejected malformed adoption artifacts"
    calls = 0

    def canonical_validator(receipt: object, **kwargs: object) -> list[str]:
        nonlocal calls
        calls += 1
        assert receipt is original_receipt
        assert kwargs["artifacts"] is original_artifacts
        return [canonical_error]

    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", canonical_validator,
    )
    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )
    assert canonical_error in errors
    assert mapping_error in errors
    assert refs == set()

    support, governance, closure_packet = _real_closure_harness(packet)
    closure_errors = governance.validate_closure(
        closure_packet,
        execution_attestation_verifier=(
            support._test_execution_attestation_verifier(closure_packet)
        ),
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )
    assert canonical_error in closure_errors
    assert mapping_error in closure_errors
    assert calls == 2


def _assert_malformed_closure_projection_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    packet: dict[str, object],
    expected_route: dict[str, object],
    task_contract_digest: str,
    mapping_error: str,
) -> None:
    bundle = packet["evidence"][0]["artifact"]
    original_receipt = bundle["receipt"]
    original_artifacts = bundle["artifacts"]
    packet["evidence"][0]["digest"] = _digest(bundle)
    canonical_error = "canonical validator rejected malformed closure projection"
    calls = 0

    def canonical_validator(receipt: object, **kwargs: object) -> list[str]:
        nonlocal calls
        calls += 1
        assert receipt is original_receipt
        assert kwargs["artifacts"] is original_artifacts
        return [canonical_error]

    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", canonical_validator,
    )
    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )
    assert canonical_error in errors
    assert mapping_error in errors
    assert refs == set()
    assert calls == 1


def test_public_validate_closure_fails_closed_for_null_human_summary_without_mutation() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet["human_summary"] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "closure human_summary must be an object" in errors
    assert any("$.human_summary" in error for error in errors)
    assert "human_summary requires objective, scope, and outcome" in errors


@pytest.mark.parametrize("field", ["side_effects", "consumption"])
def test_public_validate_closure_fails_closed_for_null_top_level_object(
    field: str,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet[field] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert f"closure {field} must be an object" in errors
    assert any(f"$.{field}" in error for error in errors)


def test_public_validate_closure_fails_closed_for_null_baseline_without_mutation() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet["baseline"] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "closure baseline must be an object" in errors
    assert any("$.baseline" in error for error in errors)
    assert "baseline source_head must be exact 40-hex" in errors


def test_public_validate_closure_fails_closed_for_null_dispatch_without_mutation() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet["dispatch"] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "closure dispatch must be an object" in errors
    assert any("$.dispatch" in error for error in errors)
    assert any("dispatch task facts are invalid" in error for error in errors)


def test_public_validate_closure_fails_closed_for_null_dispatch_task_facts() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet["dispatch"]["task_facts"] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "closure dispatch.task_facts must be an object" in errors
    assert any("$.dispatch.task_facts" in error for error in errors)
    assert any("dispatch task facts are invalid" in error for error in errors)


@pytest.mark.parametrize("field", ["acceptance", "role_fragments"])
def test_public_validate_closure_fails_closed_for_null_nested_evidence_refs(
    field: str,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet[field][0]["evidence_refs"] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert f"closure {field}[0].evidence_refs must be a list" in errors
    assert any(f"$.{field}[0].evidence_refs" in error for error in errors)


@pytest.mark.parametrize("field", ["acceptance", "role_fragments"])
def test_public_validate_closure_filters_non_string_nested_evidence_refs(
    field: str,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    valid_a = "".join(("valid", "-evidence-a"))
    valid_b = "".join(("valid", "-evidence-b"))
    identity_marker = "".join(("preserve", "-item-value"))
    identity_field = "criterion" if field == "acceptance" else "summary"
    item = packet[field][0]
    item["evidence_refs"] = [valid_a, None, [], {}, 1, valid_b]
    item[identity_field] = identity_marker
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    for index in (1, 2, 3, 4):
        assert (
            f"closure {field}[0].evidence_refs[{index}] must be a string"
            in errors
        )
    missing_a = f"{field}[0] references missing evidence {valid_a}"
    missing_b = f"{field}[0] references missing evidence {valid_b}"
    assert missing_a in errors
    assert missing_b in errors
    assert errors.index(missing_a) < errors.index(missing_b)
    assert not any(
        error.startswith(f"{field}[0] references missing evidence ")
        and error not in {missing_a, missing_b}
        for error in errors
    )

    safe_packet, normalization_errors = normalize_closure_packet_inputs(packet)
    safe_item = safe_packet[field][0]
    assert safe_packet[field] is not packet[field]
    assert safe_item is not item
    assert safe_item[identity_field] is identity_marker
    assert safe_item["evidence_refs"][0] is valid_a
    assert safe_item["evidence_refs"][1] is valid_b
    assert normalization_errors == [
        f"closure {field}[0].evidence_refs[{index}] must be a string"
        for index in (1, 2, 3, 4)
    ]


def test_public_validate_closure_fails_closed_for_null_execution_receipt_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    command_capture_ref = "capture:test-command"
    original_collect = closure_validation.collect_closure_captures

    def collect_with_command(*args: object, **kwargs: object) -> dict[str, object]:
        captures = original_collect(*args, **kwargs)
        captures["commands"][command_capture_ref] = {"role_id": "E4"}
        return captures

    monkeypatch.setattr(
        closure_validation, "collect_closure_captures", collect_with_command,
    )
    packet["checks"] = [{
        "id": "check:malformed-facts",
        "status": "EXECUTED",
        "command": "python3 -m pytest -q",
        "signature": "sha256:" + "f" * 64,
        "evidence_ref": "ev-source-1",
        "command_capture_ref": command_capture_ref,
        "executed_at": packet["adjudicated_at"],
        "execution_receipt": {"facts": None},
    }]
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "closure checks[0].execution_receipt.facts must be an object" in errors


def test_public_validate_closure_rejects_reused_list_execution_facts() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    facts = {
        "source_head": packet["baseline"]["source_head"],
        "dirty_diff_hash": packet["baseline"]["dirty_diff_hash"],
        "untracked_relevant_hash": packet["baseline"]["untracked_relevant_hash"],
        "command": "python3 -m pytest -q",
        "selected_tests": ["tests/structure/test_local_only.py"],
        "toolchain": "python-3/pytest",
        "dependency_lock_hash": "sha256:" + "d" * 64,
        "os": "macOS",
        "arch": "arm64",
        "env_mode": "source-only-no-secrets",
        "config_hash": "sha256:" + "e" * 64,
        "runtime_head": None,
        "authorization_hash": None,
    }
    execution = governance_evidence.build_test_execution_receipt(
        facts,
        executor_role="E4",
        started_at="2026-07-21T10:00:00Z",
        completed_at="2026-07-21T10:01:00Z",
        exit_code=0,
        result="PASS",
        evidence_digest=packet["evidence"][0]["digest"],
        output_digest="sha256:" + "2" * 64,
    )
    recheck = governance_evidence.build_test_recheck_receipt(
        execution,
        reviewer_role="E2",
        observed_at="2026-07-21T10:30:00Z",
        result="PASS",
        evidence_digest="sha256:" + "3" * 64,
    )
    reuse_receipt = governance_evidence.assess_test_evidence_reuse(
        {
            "schema_version": "test_evidence_capsule_v2",
            "status": "PASS",
            "signature": governance_evidence.test_evidence_signature(facts),
            "created_at": execution["completed_at"],
            "expires_at": "2026-07-22T10:00:00Z",
            "critical": True,
            "flaky": False,
            "execution_receipt": execution,
            "independent_recheck_receipt": recheck,
        },
        facts,
        now="2026-07-21T11:00:00Z",
    )
    reuse_receipt["execution_receipt"]["facts"] = []
    reuse_receipt["execution_receipt"][
        "receipt_digest"
    ] = governance_evidence.evidence_receipt_digest(
        reuse_receipt["execution_receipt"]
    )
    reuse_receipt["execution_receipt_digest"] = reuse_receipt[
        "execution_receipt"
    ]["receipt_digest"]
    reuse_receipt["receipt_digest"] = governance_evidence.evidence_receipt_digest(
        reuse_receipt
    )
    packet["checks"] = [{
        "id": "check:reused-malformed-facts",
        "status": "REUSED",
        "command": facts["command"],
        "signature": governance_evidence.test_evidence_signature(facts),
        "evidence_ref": "ev-source-1",
        "command_capture_ref": "capture:local-only",
        "reused_from": execution["completed_at"],
        "reuse_receipt": reuse_receipt,
    }]
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert any(
        "typed independent recheck execution facts must be an object" in error
        for error in errors
    )
    assert any("typed execution receipt lacks signed facts" in error for error in errors)


@pytest.mark.parametrize(
    "field",
    ["authority_refs", "acceptance", "role_fragments", "checks", "skipped_roles"],
)
def test_public_validate_closure_fails_closed_for_null_object_collection(
    field: str,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet[field] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert f"closure {field} must be a list" in errors
    assert any(f"$.{field}" in error for error in errors)


def test_public_validate_closure_fails_closed_for_null_unverified_without_mutation() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet["unverified"] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "closure unverified must be a list" in errors
    assert any("$.unverified" in error for error in errors)


@pytest.mark.parametrize(
    "field",
    [
        "authority_refs",
        "acceptance",
        "evidence",
        "role_fragments",
        "checks",
        "skipped_roles",
    ],
)
def test_public_validate_closure_fails_closed_for_mixed_object_collection_items(
    field: str,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    valid_item = packet[field][0] if packet[field] else {}
    packet[field] = [valid_item, None, [], valid_item]
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert f"{field}[1] must be an object" in errors
    assert f"{field}[2] must be an object" in errors


def test_public_validate_closure_reports_independent_mixed_shape_errors() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet.update({
        "human_summary": None,
        "baseline": None,
        "dispatch": None,
        "authority_refs": [None],
        "acceptance": [None, {"evidence_refs": None}],
        "evidence": [None],
        "role_fragments": [None],
        "checks": [None, {"execution_receipt": {"facts": None}}],
        "side_effects": None,
        "unverified": None,
        "skipped_roles": [None],
        "consumption": None,
    })
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert {
        "closure human_summary must be an object",
        "closure baseline must be an object",
        "closure dispatch must be an object",
        "closure side_effects must be an object",
        "closure consumption must be an object",
        "authority_refs[0] must be an object",
        "acceptance[0] must be an object",
        "evidence[0] must be an object",
        "role_fragments[0] must be an object",
        "checks[0] must be an object",
        "skipped_roles[0] must be an object",
        "closure unverified must be a list",
        "closure dispatch.task_facts must be an object",
        "closure acceptance[1].evidence_refs must be a list",
        "closure checks[1].execution_receipt.facts must be an object",
    }.issubset(errors)


def test_public_validate_closure_fails_closed_for_null_evidence_without_mutation() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet["evidence"] = None
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "closure evidence must be a list" in errors
    assert any("$.evidence" in error for error in errors)
    assert any("references missing evidence" in error for error in errors)


def test_public_validate_closure_skips_null_evidence_item_and_continues() -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    packet["evidence"] = [None]
    original = deepcopy(packet)

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "evidence[0] must be an object" in errors
    assert any("$.evidence[0]" in error for error in errors)
    assert any("references missing evidence" in error for error in errors)


def test_public_validate_closure_converts_canonical_digest_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)
    original = deepcopy(packet)
    validator_calls = 0

    def raise_digest(_bundle: object) -> str:
        raise RuntimeError("digest boundary failed")

    def canonical_validator(_receipt: object, **_kwargs: object) -> list[str]:
        nonlocal validator_calls
        validator_calls += 1
        return []

    monkeypatch.setattr(aiml_adoption, "canonical_digest", raise_digest)
    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", canonical_validator,
    )

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert "AIML Program adoption evidence digest calculation failed" in errors
    assert validator_calls == 1


def test_public_validate_closure_retains_prior_error_on_validator_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    program_packet["evidence"][0]["digest"] = "sha256:" + "f" * 64
    _, governance, packet = _real_closure_harness(program_packet)
    original = deepcopy(packet)

    def raise_validator(_receipt: object, **_kwargs: object) -> list[str]:
        raise RuntimeError("canonical validator boundary failed")

    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", raise_validator,
    )

    errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert packet == original
    assert (
        "AIML Program adoption evidence digest does not bind the complete bundle"
        in errors
    )
    assert "AIML Program adoption canonical validator failed" in errors


@pytest.mark.parametrize(
    "invalid_errors", [None, "error", [1], ["valid", 1]],
    ids=["null", "string", "non-string-item", "mixed-items"],
)
def test_program_adoption_rejects_invalid_canonical_error_return(
    monkeypatch: pytest.MonkeyPatch,
    invalid_errors: object,
) -> None:
    program_packet, expected_route, task_contract_digest = _program_adoption_packet()
    monkeypatch.setattr(
        aiml_adoption,
        "validate_program_adoption_receipt",
        lambda *args, **kwargs: invalid_errors,
    )

    direct_errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        program_packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )
    return_error = (
        "AIML Program adoption canonical validator returned invalid errors"
    )
    assert return_error in direct_errors
    assert refs == set()

    _, governance, packet = _real_closure_harness(program_packet)
    closure_errors = governance.validate_closure(
        packet,
        external_evidence_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )
    assert return_error in closure_errors


@pytest.mark.parametrize("boundary", ["digest", "validator"])
@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_public_validate_closure_propagates_control_flow_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    exception_type: type[BaseException],
) -> None:
    program_packet, _, _ = _program_adoption_packet()
    _, governance, packet = _real_closure_harness(program_packet)

    def raise_control_flow(*_args: object, **_kwargs: object) -> object:
        raise exception_type("operator control flow")

    monkeypatch.setattr(
        aiml_adoption,
        "canonical_digest" if boundary == "digest" else "validate_program_adoption_receipt",
        raise_control_flow,
    )

    with pytest.raises(exception_type, match="operator control flow"):
        governance.validate_closure(
            packet,
            external_evidence_verifier=lambda artifact: True,
            source_manifest_verifier=lambda reviewed, merged, manifest: True,
        )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_evidence_item_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["evidence"] = [malformed]
    monkeypatch.setattr(
        aiml_adoption,
        "validate_program_adoption_receipt",
        lambda *args, **kwargs: pytest.fail("malformed evidence must not be validated"),
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert "AIML Program adoption evidence[0] must be an object" in errors
    assert any("PASS requires exactly one evidence bundle" in error for error in errors)
    assert refs == set()


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_dispatch_mapping_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["dispatch"] = malformed
    _assert_malformed_closure_projection_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption closure dispatch must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_task_facts_mapping_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["dispatch"]["task_facts"] = malformed
    _assert_malformed_closure_projection_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption closure task_facts must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_claim_inputs_mapping_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["dispatch"]["task_facts"]["claim_inputs"] = malformed
    _assert_malformed_closure_projection_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption closure claim_inputs must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_context_artifact_mapping_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["dispatch"]["context_artifact"] = malformed
    _assert_malformed_closure_projection_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption closure context_artifact must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_baseline_mapping_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["baseline"] = malformed
    _assert_malformed_closure_projection_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption closure baseline must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_s0_1_mapping_fails_closed_without_coercion(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    bundle = packet["evidence"][0]["artifact"]
    bundle["artifacts"]["s0_1_receipt"] = malformed
    packet["evidence"][0]["digest"] = _digest(bundle)
    _assert_malformed_program_adoption_bundle_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption s0_1_receipt must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_s0_2_mapping_fails_closed_without_coercion(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    bundle = packet["evidence"][0]["artifact"]
    bundle["artifacts"]["s0_2_receipt"] = malformed
    packet["evidence"][0]["digest"] = _digest(bundle)
    _assert_malformed_program_adoption_bundle_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption s0_2_receipt must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_github_mapping_fails_closed_without_coercion(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    bundle = packet["evidence"][0]["artifact"]
    bundle["artifacts"]["github_attestation"] = malformed
    packet["evidence"][0]["digest"] = _digest(bundle)
    _assert_malformed_program_adoption_bundle_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption github_attestation must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_finalization_attempt_fails_closed_without_coercion(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    bundle = packet["evidence"][0]["artifact"]
    bundle["artifacts"]["finalization_attempt"] = malformed
    packet["evidence"][0]["digest"] = _digest(bundle)
    _assert_malformed_program_adoption_bundle_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption finalization_attempt must be an object",
    )


@pytest.mark.parametrize("malformed", [None, []], ids=["null", "list"])
def test_program_adoption_bootstrap_admission_fails_closed_without_coercion(
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    bundle = packet["evidence"][0]["artifact"]
    bundle["artifacts"]["finalization_attempt"]["bootstrap_admission"] = malformed
    packet["evidence"][0]["digest"] = _digest(bundle)
    _assert_malformed_program_adoption_bundle_fails_closed(
        monkeypatch,
        packet,
        expected_route,
        task_contract_digest,
        "AIML Program adoption bootstrap_admission must be an object",
    )


def test_program_adoption_closure_binding_passes_both_trust_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    external_verifier = lambda artifact: artifact is not None
    source_verifier = lambda reviewed, merged, manifest: bool(manifest)
    received: dict[str, object] = {}

    def canonical_validator(receipt: object, **kwargs: object) -> list[str]:
        received["receipt"] = receipt
        received.update(kwargs)
        return []

    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", canonical_validator,
    )
    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=external_verifier,
        source_manifest_verifier=source_verifier,
    )

    assert errors == []
    assert refs == {"program-adoption"}
    assert received == {
        "receipt": packet["evidence"][0]["artifact"]["receipt"],
        "artifacts": packet["evidence"][0]["artifact"]["artifacts"],
        "now": packet["adjudicated_at"],
        "external_verifier": external_verifier,
        "source_manifest_verifier": source_verifier,
    }


# Finding 1 負向 (i):review_binding.fragment_id 指向不存在的 PASS fragment → 失敗。
def test_program_adoption_closure_rejects_review_binding_without_matching_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    bundle = packet["evidence"][0]["artifact"]
    bundle["receipt"]["review_bindings"][0]["fragment_id"] = "frag-nonexistent"
    packet["evidence"][0]["digest"] = _digest(bundle)
    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", lambda *a, **k: [],
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any(
        "fragment_id is not bound to a PASS fragment" in error for error in errors
    )
    assert refs == set()


# Finding 1 負向 (iii):某 reviewer fragment 的 review_control.final_generation 與
# receipt.review_generation 不一致 → 失敗。
def test_program_adoption_closure_rejects_fragment_generation_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["role_fragments"][0]["payload"]["review_control"]["final_generation"] = {
        "source_head": "9" * 40,
        "dirty_diff_hash": "sha256:" + "9" * 64,
        "untracked_relevant_hash": "sha256:" + "9" * 64,
    }
    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", lambda *a, **k: [],
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any(
        "review_control generation is not bound to receipt review_generation" in error
        for error in errors
    )
    assert refs == set()


def test_program_adoption_pass_requires_one_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["evidence"] = []
    monkeypatch.setattr(
        aiml_adoption,
        "validate_program_adoption_receipt",
        lambda *args, **kwargs: pytest.fail("missing bundle must not be validated"),
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("PASS requires exactly one evidence bundle" in error for error in errors)
    assert refs == set()


def test_program_adoption_closure_rejects_duplicate_bundles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    duplicate = deepcopy(packet["evidence"][0])
    duplicate["id"] = "program-adoption-duplicate"
    packet["evidence"].append(duplicate)
    monkeypatch.setattr(
        aiml_adoption,
        "validate_program_adoption_receipt",
        lambda *args, **kwargs: pytest.fail("ambiguous bundles must not be validated"),
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("at most one evidence bundle" in error for error in errors)
    assert refs == set()


@pytest.mark.parametrize(
    "gate_verdict", ["FAIL", "CONDITIONAL", "UNVERIFIED", "NOT_APPLICABLE"],
)
def test_non_pass_program_adoption_closure_rejects_bundle_without_validation(
    monkeypatch: pytest.MonkeyPatch,
    gate_verdict: str,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["gate_verdict"] = gate_verdict
    monkeypatch.setattr(
        aiml_adoption,
        "validate_program_adoption_receipt",
        lambda *args, **kwargs: pytest.fail("non-PASS bundle must not be validated"),
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("non-PASS closure cannot carry" in error for error in errors)
    assert refs == set()


def test_non_pass_program_adoption_closure_allows_zero_bundles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["gate_verdict"] = "FAIL"
    packet["evidence"] = []
    monkeypatch.setattr(
        aiml_adoption,
        "validate_program_adoption_receipt",
        lambda *args, **kwargs: pytest.fail("absent bundle must not be validated"),
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=None,
        source_manifest_verifier=None,
    )

    assert errors == []
    assert refs == set()


def test_program_adoption_closure_rejects_bundle_digest_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["evidence"][0]["digest"] = "sha256:" + "f" * 64
    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", lambda *args, **kwargs: [],
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("digest does not bind the complete bundle" in error for error in errors)
    assert refs == set()


def test_program_adoption_closure_propagates_canonical_verifier_errors_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    canonical_errors = [
        "program adoption requires caller-supplied external GitHub verification",
        "program adoption source manifest verification failed",
    ]

    def canonical_validator(receipt: object, **kwargs: object) -> list[str]:
        assert kwargs["external_verifier"] is None
        with pytest.raises(RuntimeError, match="source verifier failed"):
            kwargs["source_manifest_verifier"]("reviewed", "merged", {})
        return canonical_errors

    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", canonical_validator,
    )

    def throwing_source_verifier(
        reviewed: str, merged: str, manifest: dict[str, str],
    ) -> bool:
        raise RuntimeError("source verifier failed")

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=None,
        source_manifest_verifier=throwing_source_verifier,
    )

    assert errors == canonical_errors
    assert refs == set()


def test_program_adoption_closure_binds_selector_claims_to_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, _, task_contract_digest = _program_adoption_packet()
    packet["dispatch"]["task_facts"]["claim_inputs"][
        "aiml_github_policy_attestation"
    ] = "sha256:" + "9" * 64
    expected_route = route_task(packet["dispatch"]["task_facts"])
    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", lambda *args, **kwargs: [],
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("selector claims differ from bundled artifacts" in error for error in errors)
    assert refs == set()


@pytest.mark.parametrize(
    "field",
    ["task_contract_digest", "dag_digest", "context_artifact_digest", "baseline_head"],
)
def test_program_adoption_closure_binds_finalization_bootstrap_to_packet(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    replacement = "5" * 40 if field == "baseline_head" else "sha256:" + "5" * 64
    packet["evidence"][0]["artifact"]["artifacts"]["finalization_attempt"][
        "bootstrap_admission"
    ][field] = replacement
    packet["evidence"][0]["digest"] = _digest(packet["evidence"][0]["artifact"])
    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", lambda *args, **kwargs: [],
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("bootstrap differs from closure generation" in error for error in errors)
    assert refs == set()


@pytest.mark.parametrize(
    "effect",
    ["repo_mutation", "runtime_contact", "private_external_contact", "broker_effect"],
)
def test_program_adoption_pass_requires_four_zero_effects(
    monkeypatch: pytest.MonkeyPatch,
    effect: str,
) -> None:
    packet, expected_route, task_contract_digest = _program_adoption_packet()
    packet["side_effects"][effect] = True
    monkeypatch.setattr(
        aiml_adoption, "validate_program_adoption_receipt", lambda *args, **kwargs: [],
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("must record four zero effects" in error for error in errors)
    assert refs == set()


def test_program_adoption_closure_rejects_selector_free_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet, _, task_contract_digest = _program_adoption_packet()
    unselected_facts = {
        "task_shape": "query",
        "surfaces": ["governance"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "task_prompt": "ordinary governance query",
        "claim_inputs": {},
    }
    packet["dispatch"]["task_facts"] = unselected_facts
    expected_route = route_task(unselected_facts)
    monkeypatch.setattr(
        aiml_adoption,
        "validate_program_adoption_receipt",
        lambda *args, **kwargs: pytest.fail("selector-free bundle must not be validated"),
    )

    errors, refs = aiml_adoption.validate_program_adoption_closure_binding(
        packet,
        expected_route,
        task_contract_digest,
        external_verifier=lambda artifact: True,
        source_manifest_verifier=lambda reviewed, merged, manifest: True,
    )

    assert any("requires the exact AIML selector" in error for error in errors)
    assert refs == set()


def test_closure_schema_requires_exact_data_scoped_program_adoption_bundle() -> None:
    schema = json.loads((ROOT / ".codex/schemas/closure_packet_v1.schema.json").read_text())
    evidence_schema = schema["$defs"]["evidence"]
    bundle = {
        "receipt": {},
        "artifacts": {
            name: {}
            for name in (
                "s0_1_receipt",
                "s0_2_receipt",
                "source_attempt",
                "finalization_attempt",
                "effect_classification",
                "dependency_graph",
                "github_attestation",
                "terminal_sink_contract",
            )
        },
    }
    evidence = {
        "id": "program-adoption",
        "scope": "data",
        "kind": "program_adoption_receipt_v1",
        "digest": _digest(bundle),
        "artifact": bundle,
    }

    assert schema_subset_errors(evidence, evidence_schema, schema) == []
    wrong_scope = {**evidence, "scope": "external"}
    assert schema_subset_errors(wrong_scope, evidence_schema, schema)
    missing_dependency = deepcopy(evidence)
    missing_dependency["artifact"]["artifacts"].pop("terminal_sink_contract")
    assert schema_subset_errors(missing_dependency, evidence_schema, schema)


def test_registry_binds_exact_aiml_adoption_contract_and_contract_only_sink(
    tmp_path: Path,
) -> None:
    registry = load_registry()
    contract = registry["workflow_contracts"]["aiml_program_adoption_v1"]

    assert contract == {
        "schema_version": "aiml_program_adoption_v1",
        "selector_claim_key": "aiml_program_adoption_selection",
        "selector_digest": _selection_digest(),
        "claim_inventory": CLAIM_KEYS,
        "sole_issuer_session": "S0.3",
        "schema_paths": SCHEMA_PATHS,
        "canonical_validator_path": (
            "program_code/ml_training/aiml_gate_receipt_validator.py"
        ),
        "trusted_host_finalizer_path": (
            "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py"
        ),
        "execution_signer_fingerprint": (
            "SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ"
        ),
        "github_capture_projection_version": "github_capture_projection_v2",
        "mandatory_review_roles": ["CC", "E2", "E3", "E4", "MIT", "QA", "R4"],
        "finalization_validator_node_id": "aiml_program_adoption_validator",
    }
    assert registry["effect_adapters"]["terminal_receipt_sink_v1"] == {
        "status": "CONTRACT_ONLY",
        "owner_session": "S1.2",
        "authority": "terminal receipt append/readback is unavailable in S0.3",
        "invariant": "no executable component or append path exists before S1.2",
        "contract_schema_path": (
            f"{SCHEMA_ROOT}/terminal_receipt_sink_v1.schema.json"
        ),
        "implementation_paths": [],
        "component_paths": [],
    }
    assert validate_registry(registry, ROOT) == []

    drifted = deepcopy(registry)
    drifted["workflow_contracts"]["aiml_program_adoption_v1"][
        "sole_issuer_session"
    ] = "S0.2"
    assert any(
        "aiml_program_adoption_v1" in error
        for error in validate_registry(drifted, ROOT)
    )

    missing_path_errors = aiml_adoption.registry_contract_errors(registry, tmp_path)
    assert any(
        contract["trusted_host_finalizer_path"] in error
        for error in missing_path_errors
    )

    executable_sink = deepcopy(registry)
    executable_sink["effect_adapters"]["terminal_receipt_sink_v1"][
        "component_paths"
    ] = ["helper_scripts/maintenance_scripts/agent_governance.py"]
    assert any(
        "terminal_receipt_sink_v1" in error
        for error in validate_registry(executable_sink, ROOT)
    )


def test_exact_aiml_selector_routes_seven_reviewers_then_non_call_validator_without_effects() -> None:
    route = route_task(_finalization_facts())
    nodes = route["nodes"]
    node_ids = [node["id"] for node in nodes]
    review_node_ids = [
        "independent_review",
        "regression",
        "constitutional_gate",
        "security_gate",
        "data_ml_review",
        "docs_integrity_review",
        "business_acceptance",
    ]

    assert route["task_facts"]["claim_inputs"] == _claims()
    # 合約範圍覆寫 narrow_query 抑制:pm_triage → 7 個 reviewer 扇出 → 非呼叫
    # validator → pm_closure。
    assert node_ids == [
        "pm_triage",
        *review_node_ids,
        "aiml_program_adoption_validator",
        "pm_closure",
    ]
    by_id = {node["id"]: node for node in nodes}
    assert all(by_id[node_id]["requires"] == ["pm_triage"] for node_id in review_node_ids)
    validator = by_id["aiml_program_adoption_validator"]
    assert validator["kind"] == "validator"
    assert validator["requires"] == review_node_ids
    assert nodes[-1]["requires"] == ["aiml_program_adoption_validator"]
    # 7 個 reviewer 皆為必需 role 節點(自動真實性+producer 認證);validator 不是。
    assert [
        (node["node_id"], node["role"]) for node in route["required_role_nodes"]
    ] == [
        ("independent_review", "E2"),
        ("regression", "E4"),
        ("constitutional_gate", "CC"),
        ("security_gate", "E3"),
        ("data_ml_review", "MIT"),
        ("docs_integrity_review", "R4"),
        ("business_acceptance", "QA"),
    ]
    assert "aiml_program_adoption_validator" not in {
        node["node_id"] for node in route["required_role_nodes"]
    }
    assert not any(
        node.get("role") in {"OPS", "BB", "IB"}
        or node["kind"] in {"effect_adapter", "unsupported_effect"}
        for node in nodes
    )


def test_aiml_selector_claim_inventory_fails_closed_without_generic_confusion() -> None:
    missing = _finalization_facts()
    missing["claim_inputs"].pop("aiml_program_s0_2_receipt")
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(missing)

    extra = _finalization_facts()
    extra["claim_inputs"]["generic_source_task"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(extra)

    substituted = _finalization_facts()
    substituted["claim_inputs"]["s0_1_receipt"] = substituted[
        "claim_inputs"
    ].pop("aiml_program_s0_1_receipt")
    with pytest.raises(ValueError, match="exact claim_inputs"):
        route_task(substituted)

    orphan = _finalization_facts()
    orphan["claim_inputs"].pop("aiml_program_adoption_selection")
    with pytest.raises(ValueError, match="selection digest"):
        route_task(orphan)

    invalid_selector = _finalization_facts()
    invalid_selector["claim_inputs"][
        "aiml_program_adoption_selection"
    ] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="selection digest"):
        route_task(invalid_selector)

    selector_typo = _finalization_facts()
    selector_typo["claim_inputs"][
        "aiml_program_adoption_selection_v1"
    ] = selector_typo["claim_inputs"].pop(
        "aiml_program_adoption_selection"
    )
    with pytest.raises(ValueError, match="selection digest"):
        route_task(selector_typo)

    generic_source = {
        "task_shape": "implementation",
        "surfaces": ["python"],
        "risk": "medium",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "repo_write",
        "task_prompt": "ordinary source task",
        "dirty_scope": ["example.py"],
        "claim_inputs": {"generic_source_task": "sha256:" + "c" * 64},
    }
    assert "aiml_program_adoption_validator" not in {
        node["id"] for node in route_task(generic_source)["nodes"]
    }


def test_aiml_selector_rejects_non_finalization_task_facts() -> None:
    mutations = [
        {"task_shape": "analysis"},
        {"risk": "critical"},
        {"uncertainty": "high"},
        {"runtime_claim": True},
        {"end_to_end_claim": True},
        {
            "side_effect_class": "public_web_read",
            "surfaces": [*_finalization_facts()["surfaces"], "public_web_read"],
        },
    ]
    for mutation in mutations:
        disguised = _finalization_facts()
        disguised.update(mutation)
        with pytest.raises(
            ValueError, match="source-only POST_MERGE finalization facts",
        ):
            route_task(disguised)


def test_aiml_selector_binds_exact_predecessor_receipt_digests() -> None:
    for key in ("aiml_program_s0_1_receipt", "aiml_program_s0_2_receipt"):
        substituted = _finalization_facts()
        substituted["claim_inputs"][key] = "sha256:" + "e" * 64
        with pytest.raises(ValueError, match="predecessor receipt digests"):
            route_task(substituted)


def test_aiml_selector_rejects_non_string_claim_entries_with_value_error() -> None:
    non_string_key = _finalization_facts()
    non_string_key["claim_inputs"][1] = "sha256:" + "f" * 64
    non_string_key["claim_inputs"]["extra"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="claim_inputs"):
        route_task(non_string_key)

    non_string_value = _finalization_facts()
    non_string_value["claim_inputs"]["aiml_program_s0_1_receipt"] = 1
    with pytest.raises(ValueError, match="claim_inputs"):
        route_task(non_string_value)
