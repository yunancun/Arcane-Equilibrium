"""Eligibility gate for a future fresh S2E LW2 admission.

Validation is offline and structural by default: it authenticates no platform
identity and creates no task, DAG, admission, lease, source write, or artifact.
Task admission may additionally replay the exact deterministic read-only proof
before it persists admission state.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from agent_governance_pytest_provider import (
    GOVERNED_PYTEST_PREFIX,
    GOVERNED_PYTEST_REQUIRED_ARGS,
)
from agent_governance_execution_dag import execution_dag_digest


LW2_ADMISSION_PROFILE = "aiml_s2e_lw2_readmission_v1"
LW2_CLAIM_KEYS = frozenset({
    "lw2_combined_main_identity",
    "lw2_combined_main_unreachability_capture",
    "lw2_independent_review",
})
HEAD_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
IDENTITY_FIELDS = {"schema_version", "head", "tree"}
CAPTURE_FIELDS = {
    "schema_version", "head", "tree", "context_artifact_digest",
    "task_contract_digest", "capture_digest", "evidence_dag_digest",
    "command_capture",
}
REVIEW_FIELDS = {
    "schema_version", "head", "tree", "context_artifact_digest",
    "task_contract_digest", "workflow_call_record", "role_fragment",
    "trust_ceiling", "evidence_dag_digest",
}
ROLE_FRAGMENT_FIELDS = {
    "schema_version", "id", "node_id", "role", "task_contract_digest",
    "context_artifact_digest", "producer_call_ref",
    "producer_call_receipt_digest", "producer_record_kind", "work_status",
    "gate_verdict", "classification", "confidence", "summary",
    "evidence_refs", "concerns", "next_action", "consumption",
    "payload_kind", "payload",
}
REVIEW_PAYLOAD_FIELDS = {
    "schema_version", "status", "reviewed_head", "reviewed_tree",
    "reviewed_capture_digest", "writer_native_identity", "trust_ceiling",
}
LW2_CAPTURE_NODE_ID = "lw2_combined_main_unreachability_capture"
LW2_REVIEW_NODE_ID = "independent_review"
LW2_CAPTURE_PATH_SCOPE = (
    "tests/structure/test_agent_governance_context_pack_reachability.py",
    "tests/structure/test_agent_governance_s2e_launch_chain.py",
)
LW2_FOCUSED_CAPTURE_ARGV = (
    *GOVERNED_PYTEST_PREFIX,
    *GOVERNED_PYTEST_REQUIRED_ARGS,
    "-q",
    (
        "tests/structure/test_agent_governance_context_pack_reachability.py::"
        "test_active_state_contains_the_exact_empty_dispatch_projection"
    ),
    (
        "tests/structure/test_agent_governance_s2e_launch_chain.py::"
        "test_lw1_through_lw5_require_the_exact_unconsumed_prior_digest"
    ),
    (
        "tests/structure/test_agent_governance_s2e_launch_chain.py::"
        "test_lw2_rejects_a_predecessor_receipt_from_a_sibling_branch"
    ),
)
LW2_TRUST_CEILING = "ORCHESTRATOR_BOUND_STRUCTURAL_PROVENANCE_ONLY"
LW2_EVIDENCE_DAG = (
    {
        "node_id": LW2_CAPTURE_NODE_ID,
        "role": "E3",
        "native_agent": "E3",
        "requires": [],
        "node_class": "verification",
        "permission": "read_only",
    },
    {
        "node_id": LW2_REVIEW_NODE_ID,
        "role": "E2",
        "native_agent": "E2",
        "requires": [LW2_CAPTURE_NODE_ID],
        "node_class": "verification",
        "permission": "read_only",
    },
)
LW2_EVIDENCE_DAG_DIGEST = execution_dag_digest(list(LW2_EVIDENCE_DAG))


def canonical_claim_digest(value: Any) -> str:
    """Return the task-contract claim digest for one exact JSON payload."""

    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("LW2 claim payload must be canonical JSON") from error
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def capture_current_repository_identity(repo: Path) -> tuple[str, str]:
    """Read the exact Git commit/tree identity used by route or admission."""

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("LW2 admission cannot capture current repository HEAD/tree") from error
    if not HEAD_RE.fullmatch(head) or not HEAD_RE.fullmatch(tree):
        raise ValueError("LW2 admission repository HEAD/tree is not raw lowercase 40-hex")
    return head, tree


def _exact_object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields are not exact")
    return value


def _identity(value: Any, *, label: str) -> tuple[str, str]:
    if not HEAD_RE.fullmatch(str(value.get("head", ""))):
        raise ValueError(f"{label} head must be raw lowercase 40-hex")
    if not HEAD_RE.fullmatch(str(value.get("tree", ""))):
        raise ValueError(f"{label} tree must be raw lowercase 40-hex")
    return value["head"], value["tree"]


def validate_lw2_readmission_eligibility(
    *,
    admission_profile: Any,
    claim_inputs: Any,
    claim_payloads: Any,
    current_head: str,
    current_tree: str,
    expected_writer_identity: str | None = None,
    repo: Path | None = None,
    reexecute_capture: bool = False,
) -> bool:
    """Return only eligibility for the exact current-head LW2 claim bundle."""

    if admission_profile != LW2_ADMISSION_PROFILE:
        raise ValueError("LW2 admission_profile is invalid")
    if not HEAD_RE.fullmatch(str(current_head)) or not HEAD_RE.fullmatch(str(current_tree)):
        raise ValueError("LW2 current repository HEAD/tree must be raw lowercase 40-hex")
    if not isinstance(claim_inputs, dict) or set(claim_inputs) != LW2_CLAIM_KEYS:
        raise ValueError("LW2 claim_inputs must contain exactly three required keys")
    if not isinstance(claim_payloads, dict) or set(claim_payloads) != LW2_CLAIM_KEYS:
        raise ValueError("LW2 claim_payloads must contain exactly three required keys")
    for key in sorted(LW2_CLAIM_KEYS):
        digest = claim_inputs[key]
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            raise ValueError(f"LW2 claim_inputs {key} digest is invalid")
        if canonical_claim_digest(claim_payloads[key]) != digest:
            raise ValueError(f"LW2 claim payload digest mismatch: {key}")

    identity = _exact_object(
        claim_payloads["lw2_combined_main_identity"],
        IDENTITY_FIELDS,
        "LW2 combined-main identity",
    )
    if identity["schema_version"] != "lw2_combined_main_identity_v1":
        raise ValueError("LW2 combined-main identity schema is invalid")
    head, tree = _identity(identity, label="LW2 combined-main identity")
    if (head, tree) != (current_head, current_tree):
        raise ValueError("LW2 combined-main identity is not current repository HEAD/tree")

    raw_capture = claim_payloads["lw2_combined_main_unreachability_capture"]
    if not isinstance(raw_capture, dict) or set(raw_capture) != CAPTURE_FIELDS:
        raise ValueError(
            "LW2 combined-main capture must embed one complete command_capture_v2"
        )
    capture = raw_capture
    if capture["schema_version"] != "lw2_combined_main_unreachability_capture_v1":
        raise ValueError("LW2 combined-main capture schema is invalid")
    if _identity(capture, label="LW2 combined-main capture") != (head, tree):
        raise ValueError("LW2 combined-main capture head/tree mismatch")
    command_capture = capture["command_capture"]
    if not isinstance(command_capture, dict):
        raise ValueError(
            "LW2 combined-main capture must embed one complete command_capture_v2"
        )
    if repo is None:
        raise ValueError("LW2 combined-main capture validation requires repository root")
    expected_execution_task = {
        "node_id": LW2_CAPTURE_NODE_ID,
        "role": "E3",
        "native_agent": "E3",
        "node_class": "verification",
        "permission": "read_only",
        "requires": [],
        "path_scope": [],
    }
    from agent_governance_command_capture_v2 import (  # local to avoid cycle
        validate_governed_command_capture,
    )
    capture_validation = {
        "expected_context_artifact_digest": capture["context_artifact_digest"],
        "expected_task_contract_digest": capture["task_contract_digest"],
        "expected_execution_task": expected_execution_task,
        "expected_path_scope": list(LW2_CAPTURE_PATH_SCOPE),
        "expected_source_head": head,
        "root": Path(repo),
    }
    capture_errors = validate_governed_command_capture(
        command_capture,
        reexecute=False,
        **capture_validation,
    )
    if capture_errors:
        raise ValueError(
            "LW2 governed command capture is invalid: " + "; ".join(capture_errors)
        )
    if (
        capture["capture_digest"] != command_capture.get("record_digest")
        or capture["evidence_dag_digest"] != LW2_EVIDENCE_DAG_DIGEST
        or command_capture.get("schema_version") != "command_capture_v2"
        or command_capture.get("argv") != list(LW2_FOCUSED_CAPTURE_ARGV)
        or command_capture.get("result") != "PASS"
        or command_capture.get("exit_code") != 0
        or command_capture.get("timed_out") is not False
    ):
        raise ValueError(
            "LW2 capture must bind the exact governed focused PASS record"
        )

    review = _exact_object(
        claim_payloads["lw2_independent_review"],
        REVIEW_FIELDS,
        "LW2 independent review",
    )
    if review["schema_version"] != "lw2_independent_review_v1":
        raise ValueError("LW2 independent review schema is invalid")
    if _identity(review, label="LW2 independent review") != (head, tree):
        raise ValueError("LW2 independent review head/tree mismatch")
    if (
        review["trust_ceiling"] != LW2_TRUST_CEILING
        or review["task_contract_digest"] != capture["task_contract_digest"]
        or review["context_artifact_digest"] == capture["context_artifact_digest"]
        or review["evidence_dag_digest"] != LW2_EVIDENCE_DAG_DIGEST
    ):
        raise ValueError(
            "LW2 review must bind a distinct E2 Context and the capture task contract"
        )
    call = review["workflow_call_record"]
    fragment = review["role_fragment"]
    if not isinstance(call, dict) or not isinstance(fragment, dict):
        raise ValueError(
            "LW2 independent review must embed workflow_call_record_v1 and role_fragment_v1"
        )
    from agent_governance_workflow_receipts import (  # local to avoid cycle
        validate_role_fragment_producer,
        validate_workflow_call_record,
    )
    call_errors = validate_workflow_call_record(
        call,
        expected_task_contract_digest=review["task_contract_digest"],
        expected_context_artifact_digest=review["context_artifact_digest"],
        expected_node_id=LW2_REVIEW_NODE_ID,
        expected_role_id="E2",
    )
    if call_errors:
        raise ValueError(
            "LW2 independent review call is invalid: " + "; ".join(call_errors)
        )
    if (
        call.get("returned_null") is not False
        or call.get("dag_digest") != LW2_EVIDENCE_DAG_DIGEST
        or call.get("requires") != [LW2_CAPTURE_NODE_ID]
        or call.get("producer_generation")
        != {LW2_CAPTURE_NODE_ID: command_capture["record_digest"]}
    ):
        raise ValueError(
            "LW2 independent review producer generation must bind the command capture"
        )
    if set(fragment) != ROLE_FRAGMENT_FIELDS:
        raise ValueError("LW2 independent review role fragment fields are not exact")
    producer_errors = validate_role_fragment_producer(
        fragment,
        calls_by_id={str(call.get("logical_call_id")): call},
        wave_records_by_digest={},
        expected_task_contract_digest=review["task_contract_digest"],
        expected_context_artifact_digest=review["context_artifact_digest"],
    )
    if producer_errors:
        raise ValueError(
            "LW2 independent review role fragment is invalid: "
            + "; ".join(producer_errors)
        )
    payload = fragment.get("payload")
    if not isinstance(payload, dict) or set(payload) != REVIEW_PAYLOAD_FIELDS:
        raise ValueError("LW2 independent review judgment payload fields are not exact")
    writer_identity = payload.get("writer_native_identity")
    if (
        fragment.get("schema_version") != "role_fragment_v1"
        or fragment.get("node_id") != LW2_REVIEW_NODE_ID
        or fragment.get("role") != "E2"
        or fragment.get("payload_kind") != "review_fragment_v1"
        or fragment.get("work_status") != "DONE"
        or fragment.get("gate_verdict") != "PASS"
        or fragment.get("classification") != "FACT"
        or fragment.get("confidence") != "high"
        or fragment.get("concerns") != []
        or payload.get("schema_version")
        != "lw2_independent_review_judgment_v1"
        or payload.get("status") != "PASS"
        or payload.get("reviewed_head") != head
        or payload.get("reviewed_tree") != tree
        or payload.get("reviewed_capture_digest")
        != command_capture["record_digest"]
        or payload.get("trust_ceiling") != LW2_TRUST_CEILING
        or not isinstance(writer_identity, str)
        or not writer_identity.strip()
        or writer_identity == "E2"
    ):
        raise ValueError(
            "LW2 independent review must be exact E2 read-only PASS and not self-review"
        )
    if (
        expected_writer_identity is not None
        and writer_identity != expected_writer_identity
    ):
        raise ValueError("LW2 declared writer identity differs from admission owner")
    if reexecute_capture:
        replay_errors = validate_governed_command_capture(
            command_capture,
            reexecute=True,
            **capture_validation,
        )
        if replay_errors:
            raise ValueError(
                "LW2 governed command capture replay is invalid: "
                + "; ".join(replay_errors)
            )
    return True
