"""Exact S0.3 AIML Program-adoption Registry and routing contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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


def registry_contract_errors(registry: dict[str, Any], root: Path) -> list[str]:
    """Validate exact Registry declarations and their checked-in source paths."""

    errors: list[str] = []
    adoption = registry["workflow_contracts"].get("aiml_program_adoption_v1")
    if adoption != AIML_PROGRAM_ADOPTION_CONTRACT:
        errors.append("workflow_contracts.aiml_program_adoption_v1 is invalid")
    else:
        for path in [*adoption["schema_paths"], adoption["canonical_validator_path"]]:
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
