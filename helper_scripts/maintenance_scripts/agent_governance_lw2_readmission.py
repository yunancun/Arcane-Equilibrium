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

from agent_governance_capture import PLATFORM_OR_EXTERNAL_ATTESTED
from agent_governance_external_evidence import ExternalEvidenceVerifier
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
LW2_REPOSITORY_URL = "https://github.com/yunancun/Arcane-Equilibrium.git"
LW2_DESTINATION_REF = "refs/heads/main"
IDENTITY_FIELDS = {
    "schema_version", "repository_url", "destination_ref", "head", "tree",
    "publication_provenance",
}
PUBLICATION_FIELDS = {
    "schema_version", "trust_tier", "provider", "provider_record_id",
    "repository_url", "destination_ref", "head", "tree", "status",
    "record_digest",
}
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


def lw2_readmission_policy(
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the one Registry-owned LW2 selector and exact binding policy."""

    if registry is None:
        from agent_governance_registry import load_registry  # local: avoid cycle

        registry = load_registry()
    policy = registry.get("lw2_readmission_policy")
    required = {
        "schema_version", "work_item_id", "lane_id", "task_id_aliases",
        "lane_id_aliases", "direct_interface", "direct_interface_signals",
        "protected_scope_prefixes", "protected_scope_paths",
        "admission_profile", "claim_keys",
    }
    if not isinstance(policy, dict) or set(policy) != required:
        raise ValueError("Registry LW2 readmission policy fields are not exact")
    if (
        policy["schema_version"] != "lw2_readmission_policy_v1"
        or policy["work_item_id"] != "S2E-LW2"
        or policy["lane_id"] != "S2E.2b-2"
        or policy["direct_interface"] != "S2E-LW2"
        or policy["admission_profile"] != LW2_ADMISSION_PROFILE
        or set(policy["claim_keys"]) != LW2_CLAIM_KEYS
    ):
        raise ValueError("Registry LW2 readmission policy canonical binding is invalid")
    for field in (
        "task_id_aliases", "lane_id_aliases", "direct_interface_signals",
        "protected_scope_prefixes", "protected_scope_paths", "claim_keys",
    ):
        value = policy[field]
        if (
            not isinstance(value, list)
            or not value
            or len(value) != len(set(value))
            or any(not isinstance(item, str) or not item for item in value)
        ):
            raise ValueError(f"Registry LW2 readmission policy {field} is invalid")
    return policy


def _separator_normalized_lw2_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return re.sub(r"[._:]", "-", value) == "S2E-LW2"


def _scope_values(contract: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for field in ("scope", "dirty_scope", "verification_scope"):
        supplied = contract.get(field, [])
        if isinstance(supplied, str):
            supplied = [supplied]
        if isinstance(supplied, list):
            values.extend(item for item in supplied if isinstance(item, str))
    return tuple(values)


def _policy_protected_path(path: Any, policy: dict[str, Any]) -> bool:
    return isinstance(path, str) and (
        path in policy["protected_scope_paths"]
        or any(
            path.startswith(prefix)
            for prefix in policy["protected_scope_prefixes"]
        )
    )


def lw2_protected_inventory(
    repo: Path,
    *,
    registry: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    """Resolve the complete deterministic LW2 protected repository inventory."""

    policy = lw2_readmission_policy(registry)
    try:
        cached = subprocess.run(
            ["git", "ls-files", "--cached", "-z"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        completed = subprocess.run(
            [
                "git", "ls-files", "--cached", "--others",
                "--exclude-standard", "-z",
            ],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        tracked = {
            raw.decode("utf-8")
            for raw in cached.stdout.split(b"\0")
            if raw
        }
        candidates = {
            raw.decode("utf-8")
            for raw in completed.stdout.split(b"\0")
            if raw
        }
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
        raise ValueError("LW2 protected inventory is unavailable") from error
    exact_paths = set(policy["protected_scope_paths"])
    if not exact_paths.issubset(tracked):
        raise ValueError("LW2 protected inventory is missing an exact required path")
    inventory = set(exact_paths)
    for prefix in policy["protected_scope_prefixes"]:
        matches = {path for path in candidates if path.startswith(prefix)}
        if not matches:
            raise ValueError(
                f"LW2 protected inventory prefix has no repository files: {prefix}"
            )
        inventory.update(matches)
    for relative in inventory:
        target = repo / relative
        if target.is_symlink() or not target.is_file():
            raise ValueError(
                f"LW2 protected inventory path is not a regular file: {relative}"
            )
    return tuple(sorted(inventory))


def validate_lw2_protected_inventory_scope(
    scope: Any,
    *,
    registry: dict[str, Any] | None = None,
) -> None:
    """Validate a persisted canonical protected inventory without recapturing."""

    policy = lw2_readmission_policy(registry)
    if (
        not isinstance(scope, list)
        or not scope
        or scope != sorted(set(scope))
        or not set(policy["protected_scope_paths"]).issubset(scope)
        or any(not _policy_protected_path(path, policy) for path in scope)
        or any(
            not any(path.startswith(prefix) for path in scope)
            for prefix in policy["protected_scope_prefixes"]
        )
    ):
        raise ValueError("LW2 accepted generation protected inventory is invalid")


def lw2_contract_selected(
    contract: Any,
    *,
    task_id: str | None = None,
    registry: dict[str, Any] | None = None,
) -> bool:
    """Select LW2 from identifiers, claims, interface, or protected source scope.

    Objective text is deliberately excluded.  Alias signals select so that they
    fail the subsequent exact binding check rather than bypassing it.
    """

    if not isinstance(contract, dict):
        return False
    policy = lw2_readmission_policy(registry)
    identifiers = (task_id, contract.get("work_item_id"))
    if any(_separator_normalized_lw2_id(value) for value in identifiers):
        return True
    lane_id = contract.get("lane_id")
    if lane_id == policy["lane_id"] or lane_id in policy["lane_id_aliases"]:
        return True
    if task_id in policy["task_id_aliases"]:
        return True
    interfaces = contract.get("direct_interfaces", [])
    if isinstance(interfaces, list) and set(interfaces).intersection(
        policy["direct_interface_signals"]
    ):
        return True
    for field in ("claim_inputs", "claim_payloads"):
        claims = contract.get(field)
        if isinstance(claims, dict) and set(claims).intersection(
            policy["claim_keys"]
        ):
            return True
    if contract.get("admission_profile") == policy["admission_profile"]:
        return True
    for path in _scope_values(contract):
        if _policy_protected_path(path, policy):
            return True
    return False


def validate_lw2_contract_binding(
    contract: Any,
    *,
    task_id: str | None = None,
    registry: dict[str, Any] | None = None,
    repo: Path | None = None,
) -> None:
    """Require the exact canonical contract whenever any LW2 signal selects."""

    if not isinstance(contract, dict):
        raise ValueError("LW2 selected contract requires an object")
    policy = lw2_readmission_policy(registry)
    errors: list[str] = []
    expected = {
        "work_item_id": policy["work_item_id"],
        "lane_id": policy["lane_id"],
        "admission_profile": policy["admission_profile"],
    }
    for field, value in expected.items():
        if contract.get(field) != value:
            errors.append(f"{field}={value}")
    if contract.get("direct_interfaces") != [policy["direct_interface"]]:
        errors.append(f"direct_interfaces=[{policy['direct_interface']}]")
    dirty_scope = contract.get("dirty_scope")
    if (
        not isinstance(dirty_scope, list)
        or not dirty_scope
        or dirty_scope != sorted(set(dirty_scope))
        or any(not _policy_protected_path(path, policy) for path in dirty_scope)
    ):
        errors.append("nonempty protected-only dirty_scope")
    elif repo is not None and not set(dirty_scope).issubset(
        lw2_protected_inventory(repo, registry=registry)
    ):
        errors.append("dirty_scope contained in current protected inventory")
    if not isinstance(contract.get("claim_inputs"), dict) or set(
        contract["claim_inputs"]
    ) != set(policy["claim_keys"]):
        errors.append("exact three claim_inputs")
    if not isinstance(contract.get("claim_payloads"), dict) or set(
        contract["claim_payloads"]
    ) != set(policy["claim_keys"]):
        errors.append("exact three claim_payloads")
    if task_id is not None and task_id != policy["work_item_id"]:
        errors.append(f"task_id={policy['work_item_id']}")
    if errors:
        raise ValueError(
            "LW2 selected contract requires exact canonical binding: "
            + ", ".join(errors)
        )


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


def _git_text(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("LW2 admission local merged-main identity is unavailable") from error
    return completed.stdout.strip()


def validate_local_merged_main(repo: Path, *, head: str, tree: str) -> None:
    """Bind eligibility to a published local checkout of exact origin/main."""

    actual_head, actual_tree = capture_current_repository_identity(repo)
    branch = _git_text(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    origin_url = _git_text(repo, "remote", "get-url", "origin")
    origin_main = _git_text(repo, "rev-parse", "refs/remotes/origin/main")
    if branch != "main":
        raise ValueError("LW2 combined-main validation requires local branch main")
    if origin_url != LW2_REPOSITORY_URL:
        raise ValueError("LW2 combined-main validation requires the exact origin URL")
    if origin_main != actual_head:
        raise ValueError("LW2 combined-main validation requires origin/main == HEAD")
    if (actual_head, actual_tree) != (head, tree):
        raise ValueError("LW2 combined-main local HEAD/tree differs from claims")


def _record_self_digest(record: dict[str, Any]) -> str:
    return canonical_claim_digest({
        key: value for key, value in record.items() if key != "record_digest"
    })


def _require_external_verification(
    verifier: ExternalEvidenceVerifier | None,
    request: dict[str, Any],
    *,
    label: str,
) -> None:
    try:
        verified = verifier is not None and verifier(request) is True
    except Exception:
        verified = False
    if not verified:
        raise ValueError(f"{label} requires an out-of-band trusted verifier")


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
    external_evidence_verifier: ExternalEvidenceVerifier | None = None,
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
    if identity["schema_version"] != "lw2_combined_main_identity_v2":
        raise ValueError("LW2 combined-main identity schema is invalid")
    if (
        identity["repository_url"] != LW2_REPOSITORY_URL
        or identity["destination_ref"] != LW2_DESTINATION_REF
    ):
        raise ValueError("LW2 combined-main identity destination is invalid")
    head, tree = _identity(identity, label="LW2 combined-main identity")
    if (head, tree) != (current_head, current_tree):
        raise ValueError("LW2 combined-main identity is not current repository HEAD/tree")
    publication = _exact_object(
        identity["publication_provenance"],
        PUBLICATION_FIELDS,
        "LW2 combined-main publication provenance",
    )
    if (
        publication["schema_version"]
        != "lw2_destination_publication_provenance_v1"
        or publication["trust_tier"] != PLATFORM_OR_EXTERNAL_ATTESTED
        or publication["provider"] != "github"
        or not isinstance(publication["provider_record_id"], str)
        or not publication["provider_record_id"].strip()
        or publication["repository_url"] != LW2_REPOSITORY_URL
        or publication["destination_ref"] != LW2_DESTINATION_REF
        or (publication["head"], publication["tree"]) != (head, tree)
        or publication["status"] != "PUBLISHED"
        or publication["record_digest"] != _record_self_digest(publication)
    ):
        raise ValueError("LW2 combined-main publication provenance is invalid")
    if repo is None:
        raise ValueError("LW2 combined-main validation requires repository root")
    validate_local_merged_main(Path(repo), head=head, tree=tree)
    _require_external_verification(
        external_evidence_verifier,
        {
            "schema_version": "lw2_publication_verification_request_v1",
            "repository_url": LW2_REPOSITORY_URL,
            "destination_ref": LW2_DESTINATION_REF,
            "head": head,
            "tree": tree,
            "publication_provenance": publication,
        },
        label="LW2 combined-main publication provenance",
    )

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
    _require_external_verification(
        external_evidence_verifier,
        {
            "schema_version": "lw2_independent_review_verification_request_v1",
            "repository_url": LW2_REPOSITORY_URL,
            "destination_ref": LW2_DESTINATION_REF,
            "head": head,
            "tree": tree,
            "task_contract_digest": review["task_contract_digest"],
            "context_artifact_digest": review["context_artifact_digest"],
            "evidence_dag_digest": review["evidence_dag_digest"],
            "node_id": LW2_REVIEW_NODE_ID,
            "capture_digest": command_capture["record_digest"],
            "reviewer_identity": "E2",
            "workflow_call_record_digest": call["record_digest"],
            "role_fragment_digest": canonical_claim_digest(fragment),
            "verdict": "PASS",
        },
        label="LW2 independent review provenance",
    )
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
