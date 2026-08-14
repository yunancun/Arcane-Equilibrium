"""Pure eligibility gate for a future fresh S2E LW2 admission.

The gate authenticates no external fact and creates no task, DAG, admission,
lease, source write, or artifact.  It only rejects a non-canonical or stale
three-claim bundle before those later control-plane objects may be constructed.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


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
    "schema_version", "head", "tree", "status", "command_capture_schema",
    "governed", "permission", "producer_identity",
}
REVIEW_FIELDS = {
    "schema_version", "head", "tree", "status", "permission", "governed",
    "reviewer_identity", "writer_identity", "reviewed_capture_digest",
}


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

    capture = _exact_object(
        claim_payloads["lw2_combined_main_unreachability_capture"],
        CAPTURE_FIELDS,
        "LW2 combined-main capture",
    )
    if capture["schema_version"] != "lw2_combined_main_unreachability_capture_v1":
        raise ValueError("LW2 combined-main capture schema is invalid")
    if _identity(capture, label="LW2 combined-main capture") != (head, tree):
        raise ValueError("LW2 combined-main capture head/tree mismatch")
    if (
        capture["status"] != "PASS"
        or capture["command_capture_schema"] != "command_capture_v2"
        or capture["governed"] is not True
        or capture["permission"] != "read-only"
        or not isinstance(capture["producer_identity"], str)
        or not capture["producer_identity"].strip()
    ):
        raise ValueError("LW2 combined-main capture must be governed read-only PASS")

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
        review["status"] != "PASS"
        or review["permission"] != "read-only"
        or review["governed"] is not True
        or not isinstance(review["reviewer_identity"], str)
        or not review["reviewer_identity"].strip()
        or not isinstance(review["writer_identity"], str)
        or not review["writer_identity"].strip()
        or review["writer_identity"] != capture["producer_identity"]
        or review["reviewer_identity"] == review["writer_identity"]
    ):
        raise ValueError("LW2 independent review must be read-only PASS and not self-review")
    capture_digest = claim_inputs["lw2_combined_main_unreachability_capture"]
    if review["reviewed_capture_digest"] != capture_digest:
        raise ValueError("LW2 independent review does not bind the governed capture")
    if (
        expected_writer_identity is not None
        and review["writer_identity"] != expected_writer_identity
    ):
        raise ValueError("LW2 declared writer identity differs from admission owner")
    return True
