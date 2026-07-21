"""Exact S0.3 AIML Program-adoption Registry and routing contract."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


AIML_GATE_ROOT = Path(__file__).resolve().parents[2] / "program_code/ml_training"
if str(AIML_GATE_ROOT) not in sys.path:
    sys.path.insert(0, str(AIML_GATE_ROOT))

from aiml_gate_receipt_validator import (  # noqa: E402
    PROGRAM_REVIEW_NODES,
    SourceManifestVerifier,
    canonical_digest,
    validate_program_adoption_receipt,
)


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
AIML_GATE_SCHEMA_ROOT = "program_code/ml_training/schemas/aiml_gate_receipts"
AIML_PROGRAM_ADOPTION_CLAIM_KEYS = frozenset({
    "aiml_github_policy_attestation",
    "aiml_program_adoption_selection",
    "aiml_program_s0_1_receipt",
    "aiml_program_s0_2_receipt",
})
AIML_PROGRAM_ADOPTION_SELECTOR_DIGEST = (
    "sha256:81f0779a172aaa743be8deb31be49f33736a8fd775adaebb4798fb77d510338c"
)
AIML_PROGRAM_ADOPTION_PREDECESSOR_DIGESTS = {
    "aiml_program_s0_1_receipt": (
        "sha256:8fc9417f984025deabdc1b83ace95921ccfff1acb26a1b29243fc0a0a5ba79ad"
    ),
    "aiml_program_s0_2_receipt": (
        "sha256:0115dbd3dc62d84e183aae5a28cbfd252eb45ecee51a652d8a4a155f14dfb41a"
    ),
}
AIML_PROGRAM_ADOPTION_SURFACES = frozenset({
    "acceptance", "authority", "closure", "governance", "ml_data", "policy",
    "schema",
})
AIML_PROGRAM_ADOPTION_CONTRACT = {
    "schema_version": "aiml_program_adoption_v1",
    "selector_claim_key": "aiml_program_adoption_selection",
    "selector_digest": AIML_PROGRAM_ADOPTION_SELECTOR_DIGEST,
    "claim_inventory": sorted(AIML_PROGRAM_ADOPTION_CLAIM_KEYS),
    "sole_issuer_session": "S0.3",
    "schema_paths": [
        f"{AIML_GATE_SCHEMA_ROOT}/aiml_receipt_dependency_graph_v1.schema.json",
        f"{AIML_GATE_SCHEMA_ROOT}/aiml_required_effect_classification_v1.schema.json",
        f"{AIML_GATE_SCHEMA_ROOT}/github_repository_policy_attestation_v1.schema.json",
        f"{AIML_GATE_SCHEMA_ROOT}/landing_scope_v1.schema.json",
        f"{AIML_GATE_SCHEMA_ROOT}/program_adoption_receipt_v1.schema.json",
        f"{AIML_GATE_SCHEMA_ROOT}/session_attempt_v1.schema.json",
        f"{AIML_GATE_SCHEMA_ROOT}/terminal_receipt_sink_v1.schema.json",
    ],
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
TERMINAL_RECEIPT_SINK_CONTRACT = {
    "status": "CONTRACT_ONLY",
    "owner_session": "S1.2",
    "authority": "terminal receipt append/readback is unavailable in S0.3",
    "invariant": "no executable component or append path exists before S1.2",
    "contract_schema_path": (
        f"{AIML_GATE_SCHEMA_ROOT}/terminal_receipt_sink_v1.schema.json"
    ),
    "implementation_paths": [],
    "component_paths": [],
}
_RESERVED_CLAIM_PREFIXES = (
    "aiml_program_adoption_",
    "aiml_program_s0_",
    "aiml_github_policy_attestation",
)
PROGRAM_ADOPTION_EVIDENCE_KIND = "program_adoption_receipt_v1"
ExternalVerifier = Callable[[dict[str, Any]], bool]


def registry_contract_errors(registry: dict[str, Any], root: Path) -> list[str]:
    """Validate exact Registry declarations and their checked-in source paths."""

    errors: list[str] = []
    adoption = registry["workflow_contracts"].get("aiml_program_adoption_v1")
    if adoption != AIML_PROGRAM_ADOPTION_CONTRACT:
        errors.append("workflow_contracts.aiml_program_adoption_v1 is invalid")
    else:
        for path in [
            *adoption["schema_paths"],
            adoption["canonical_validator_path"],
            adoption["trusted_host_finalizer_path"],
        ]:
            if Path(path).is_absolute() or not (root / path).is_file():
                errors.append(
                    "workflow_contracts.aiml_program_adoption_v1 references "
                    f"a missing repository path: {path}"
                )

    sink = registry["effect_adapters"].get("terminal_receipt_sink_v1")
    if sink != TERMINAL_RECEIPT_SINK_CONTRACT:
        errors.append("effect_adapters.terminal_receipt_sink_v1 is invalid")
    elif not (root / sink["contract_schema_path"]).is_file():
        errors.append(
            "effect_adapters.terminal_receipt_sink_v1 references a missing "
            "contract schema"
        )
    return errors


def aiml_program_adoption_selected(claim_inputs: Any) -> bool:
    """Return true only for the exact S0.3 selector and predecessor lineage."""

    if not isinstance(claim_inputs, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or DIGEST_RE.fullmatch(value) is None
        for key, value in (
            claim_inputs.items() if isinstance(claim_inputs, dict) else ()
        )
    ):
        raise ValueError(
            "task facts claim_inputs must map non-empty names to sha256 digests"
        )
    keys = set(claim_inputs)
    stripped_keys = {key.strip() for key in keys}
    reserved = bool(
        stripped_keys.intersection(AIML_PROGRAM_ADOPTION_CLAIM_KEYS)
        or any(key.startswith(_RESERVED_CLAIM_PREFIXES) for key in stripped_keys)
    )
    selector = claim_inputs.get("aiml_program_adoption_selection")
    if selector is None:
        if reserved:
            raise ValueError(
                "AIML Program adoption claim_inputs require an exact selection digest"
            )
        return False
    if selector != AIML_PROGRAM_ADOPTION_SELECTOR_DIGEST:
        raise ValueError("AIML Program adoption selection digest is invalid")
    if keys != AIML_PROGRAM_ADOPTION_CLAIM_KEYS:
        raise ValueError(
            "AIML Program adoption selection digest requires exact claim_inputs: "
            f"missing={sorted(AIML_PROGRAM_ADOPTION_CLAIM_KEYS - keys)} "
            f"extra={sorted(keys - AIML_PROGRAM_ADOPTION_CLAIM_KEYS)}"
        )
    if any(
        claim_inputs[key] != digest
        for key, digest in AIML_PROGRAM_ADOPTION_PREDECESSOR_DIGESTS.items()
    ):
        raise ValueError(
            "AIML Program adoption requires exact S0.1/S0.2 predecessor receipt digests"
        )
    return True


def validate_aiml_finalization_facts(facts: dict[str, Any]) -> None:
    """Fail unless selector-bearing facts describe the source-only finalization."""

    errors = []
    if facts.get("task_shape") != "query":
        errors.append("task_shape=query")
    if facts.get("side_effect_class") != "none":
        errors.append("side_effect_class=none")
    if facts.get("risk") != "high" or facts.get("uncertainty") != "low":
        errors.append("risk=high and uncertainty=low")
    if facts.get("runtime_claim") is not False or facts.get("end_to_end_claim") is not False:
        errors.append("runtime_claim=false and end_to_end_claim=false")
    if set(facts.get("surfaces", [])) != AIML_PROGRAM_ADOPTION_SURFACES:
        errors.append("exact adoption surfaces")
    if facts.get("continuation_mode") != "finite":
        errors.append("continuation_mode=finite")
    if errors:
        raise ValueError(
            "AIML Program adoption selector requires source-only POST_MERGE "
            "finalization facts: " + ", ".join(errors)
        )


def validate_program_adoption_closure_binding(
    packet: dict[str, Any],
    expected_route: dict[str, Any] | None,
    task_contract_digest: str | None,
    *,
    external_verifier: ExternalVerifier | None,
    source_manifest_verifier: SourceManifestVerifier | None,
    evaluated_at: str | datetime | None = None,
) -> tuple[list[str], set[str]]:
    """Validate closure selection/binding; delegate AIML semantics canonically."""

    errors: list[str] = []
    dispatch = packet.get("dispatch")
    if not isinstance(dispatch, dict):
        errors.append("AIML Program adoption closure dispatch must be an object")
        dispatch = {}
    task_facts = dispatch.get("task_facts")
    if not isinstance(task_facts, dict):
        errors.append("AIML Program adoption closure task_facts must be an object")
        task_facts = {}
    try:
        routed_facts = (expected_route or {}).get("task_facts", {})
        selected = aiml_program_adoption_selected(
            routed_facts.get("claim_inputs", {})
        )
    except (AttributeError, TypeError, ValueError) as error:
        selected = False
        errors.append(f"AIML Program adoption closure selector is invalid: {error}")
    raw_evidence = packet.get("evidence")
    if not isinstance(raw_evidence, list):
        errors.append("AIML Program adoption closure evidence must be a list")
        raw_evidence = []
    evidence = []
    for index, item in enumerate(raw_evidence):
        if not isinstance(item, dict):
            errors.append(f"AIML Program adoption evidence[{index}] must be an object")
        elif item.get("kind") == PROGRAM_ADOPTION_EVIDENCE_KIND:
            evidence.append(item)
    if evidence and not selected:
        errors.append("Program-adoption evidence requires the exact AIML selector")
    if not selected:
        return errors, set()
    if packet.get("gate_verdict") != "PASS":
        if evidence:
            errors.append(
                "AIML Program adoption non-PASS closure cannot carry an evidence bundle"
            )
        return errors, set()
    if len(evidence) > 1:
        errors.append("AIML Program adoption permits at most one evidence bundle")
    if len(evidence) != 1:
        errors.append("AIML Program adoption PASS requires exactly one evidence bundle")
        return errors, set()

    item = evidence[0]
    bundle = item.get("artifact")
    if not isinstance(bundle, dict):
        return [*errors, "AIML Program adoption evidence bundle must be an object"], set()
    try:
        bundle_digest = canonical_digest(bundle)
    except Exception:
        errors.append("AIML Program adoption evidence digest calculation failed")
    else:
        if item.get("digest") != bundle_digest:
            errors.append(
                "AIML Program adoption evidence digest does not bind the complete bundle"
            )
    receipt = bundle.get("receipt")
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, dict):
        return [*errors, "AIML Program adoption artifact bundle must be an object"], set()
    try:
        canonical_errors = validate_program_adoption_receipt(
            receipt,
            artifacts=artifacts,
            now=evaluated_at or packet.get("adjudicated_at"),
            external_verifier=external_verifier,
            source_manifest_verifier=source_manifest_verifier,
        )
    except Exception:
        errors.append("AIML Program adoption canonical validator failed")
    else:
        if not isinstance(canonical_errors, list) or any(
            not isinstance(error, str) for error in canonical_errors
        ):
            errors.append(
                "AIML Program adoption canonical validator returned invalid errors"
            )
        else:
            errors.extend(canonical_errors)

    claims = task_facts.get("claim_inputs")
    if not isinstance(claims, dict):
        errors.append("AIML Program adoption closure claim_inputs must be an object")
        claims = {}
    s0_1_receipt = artifacts.get("s0_1_receipt")
    if not isinstance(s0_1_receipt, dict):
        errors.append("AIML Program adoption s0_1_receipt must be an object")
        s0_1_receipt = {}
    s0_2_receipt = artifacts.get("s0_2_receipt")
    if not isinstance(s0_2_receipt, dict):
        errors.append("AIML Program adoption s0_2_receipt must be an object")
        s0_2_receipt = {}
    github_attestation = artifacts.get("github_attestation")
    if not isinstance(github_attestation, dict):
        errors.append("AIML Program adoption github_attestation must be an object")
        github_attestation = {}
    expected_claims = {
        "aiml_program_s0_1_receipt": s0_1_receipt.get("self_digest"),
        "aiml_program_s0_2_receipt": s0_2_receipt.get("self_digest"),
        "aiml_github_policy_attestation": github_attestation.get("self_digest"),
    }
    if any(claims.get(key) != value for key, value in expected_claims.items()):
        errors.append("AIML Program adoption selector claims differ from bundled artifacts")

    final_attempt = artifacts.get("finalization_attempt")
    if not isinstance(final_attempt, dict):
        errors.append("AIML Program adoption finalization_attempt must be an object")
        final_attempt = {}
    bootstrap = final_attempt.get("bootstrap_admission")
    if not isinstance(bootstrap, dict):
        errors.append("AIML Program adoption bootstrap_admission must be an object")
        bootstrap = {}
    context_artifact = dispatch.get("context_artifact")
    if not isinstance(context_artifact, dict):
        errors.append("AIML Program adoption closure context_artifact must be an object")
        context_artifact = {}
    baseline = packet.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("AIML Program adoption closure baseline must be an object")
        baseline = {}
    expected_bootstrap = {
        "task_id": packet.get("task_id"),
        "task_contract_digest": task_contract_digest,
        "dag_digest": dispatch.get("dag_digest"),
        "context_artifact_digest": context_artifact.get("artifact_digest"),
        "baseline_head": baseline.get("source_head"),
    }
    if any(bootstrap.get(key) != value for key, value in expected_bootstrap.items()):
        errors.append("AIML finalization attempt bootstrap differs from closure generation")

    # Finding 1:把 receipt 的 7 個 reviewer 綁定接到已認證的 PASS role_fragment。
    # fragment 的真實性與 no-blocker 由 validate_closure 的 mandatory-node loop
    # (verification_fragment_truth_errors)與 validate_execution_attestations 保證,
    # 此處僅綁定 role/id/gate_verdict 及 review_control.final_generation==review_generation,
    # 不重覆實作認證。
    review_bindings = receipt.get("review_bindings") if isinstance(receipt, dict) else None
    review_generation = (
        receipt.get("review_generation") if isinstance(receipt, dict) else None
    )
    fragments_by_node = {
        fragment.get("node_id"): fragment
        for fragment in packet.get("role_fragments", [])
        if isinstance(fragment, dict)
    }
    if not isinstance(review_bindings, list):
        errors.append("AIML Program adoption receipt review_bindings must be a list")
    else:
        for binding in review_bindings:
            if not isinstance(binding, dict):
                errors.append("AIML Program adoption review binding must be an object")
                continue
            node_id = binding.get("node_id")
            fragment = fragments_by_node.get(node_id)
            if not isinstance(fragment, dict):
                errors.append(
                    f"AIML Program adoption review binding {node_id} lacks a bound role fragment"
                )
                continue
            if fragment.get("role") != binding.get("role"):
                errors.append(
                    f"AIML Program adoption review binding {node_id} role differs from its fragment"
                )
            if fragment.get("id") != binding.get("fragment_id"):
                errors.append(
                    f"AIML Program adoption review binding {node_id} fragment_id is not bound to a PASS fragment"
                )
            if fragment.get("gate_verdict") != "PASS":
                errors.append(
                    f"AIML Program adoption review binding {node_id} requires a PASS role fragment"
                )
            payload = fragment.get("payload")
            control = (
                payload.get("review_control") if isinstance(payload, dict) else None
            )
            if not isinstance(control, dict):
                errors.append(
                    f"AIML Program adoption review binding {node_id} fragment lacks review_control"
                )
            elif control.get("final_generation") != review_generation:
                errors.append(
                    f"AIML Program adoption review binding {node_id} review_control generation is not bound to receipt review_generation"
                )

    if packet.get("gate_verdict") == "PASS" and packet.get("side_effects") != {
        "repo_mutation": False,
        "runtime_contact": False,
        "private_external_contact": False,
        "broker_effect": False,
    }:
        errors.append("AIML Program adoption finalization must record four zero effects")
    return errors, ({str(item.get("id"))} if not errors else set())
