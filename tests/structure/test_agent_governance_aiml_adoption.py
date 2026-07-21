from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_registry import load_registry, validate_registry  # noqa: E402
from agent_governance_routing import route_task  # noqa: E402


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


def test_registry_binds_exact_aiml_adoption_contract_and_contract_only_sink() -> None:
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

    executable_sink = deepcopy(registry)
    executable_sink["effect_adapters"]["terminal_receipt_sink_v1"][
        "component_paths"
    ] = ["helper_scripts/maintenance_scripts/agent_governance.py"]
    assert any(
        "terminal_receipt_sink_v1" in error
        for error in validate_registry(executable_sink, ROOT)
    )


def test_exact_aiml_selector_routes_qa_then_non_call_validator_without_effects() -> None:
    route = route_task(_finalization_facts())
    nodes = route["nodes"]
    node_ids = [node["id"] for node in nodes]

    assert route["task_facts"]["claim_inputs"] == _claims()
    assert node_ids == [
        "pm_triage",
        "business_acceptance",
        "aiml_program_adoption_validator",
        "pm_closure",
    ]
    validator = nodes[node_ids.index("aiml_program_adoption_validator")]
    assert validator["kind"] == "validator"
    assert validator["requires"] == ["business_acceptance"]
    assert nodes[-1]["requires"] == ["aiml_program_adoption_validator"]
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
