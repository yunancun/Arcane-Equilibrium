"""Closed, Git-bound launch receipt payloads for S2E-LW1 through S2E-LW5."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any, Callable

from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _contains_github_secret_like_content,
    _load_schema,
    canonical_digest,
)


LAUNCH_ID = "S2E-LW1-LW5"
GENESIS_WAVE = "W0-GENESIS"
LAUNCH_WAVES = ("S2E-LW1", "S2E-LW2", "S2E-LW3", "S2E-LW4", "S2E-LW5")
CarrierVerifier = Callable[[dict[str, Any]], bool]


def launch_payload_digest(receipt: dict[str, Any]) -> str:
    """Digest a payload without making the digest field self-referential."""

    return canonical_digest({
        key: value for key, value in receipt.items() if key != "payload_digest"
    })


def s2e_carrier_attested_core_digest(attestation: dict[str, Any]) -> str:
    return canonical_digest({
        key: value
        for key, value in attestation.items()
        if key not in {"attested_core_digest", "signature", "attestation_digest"}
    })


def s2e_carrier_attestation_digest(attestation: dict[str, Any]) -> str:
    return canonical_digest({
        key: value
        for key, value in attestation.items()
        if key != "attestation_digest"
    })


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
    )


def _commit(repo_root: Path, head: str) -> str:
    return _git(repo_root, "rev-parse", "--verify", f"{head}^{{commit}}").stdout.strip()


def _tree(repo_root: Path, head: str) -> str:
    return _git(repo_root, "rev-parse", "--verify", f"{head}^{{tree}}").stdout.strip()


def _is_ancestor(repo_root: Path, older: str, newer: str) -> bool:
    return _git(
        repo_root, "merge-base", "--is-ancestor", older, newer, check=False
    ).returncode == 0


def _require_clean(repo_root: Path) -> None:
    status = _git(
        repo_root, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout
    if status:
        raise ValueError("repository must be clean before launch receipt generation")


def _schema_errors(receipt: Any, schema_version: str) -> list[str]:
    if not isinstance(receipt, dict):
        return ["launch receipt must be an object"]
    return schema_subset_errors(
        receipt, _load_schema(schema_version), _load_schema(schema_version)
    )


def _time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _git_binding_errors(
    repo_root: Path, *, head: str, tree: str, label: str
) -> list[str]:
    try:
        resolved_head = _commit(repo_root, head)
        resolved_tree = _tree(repo_root, head)
    except (OSError, subprocess.CalledProcessError) as error:
        return [f"{label} is not a readable Git commit: {error}"]
    errors: list[str] = []
    if resolved_head != head:
        errors.append(f"{label} must be a full exact commit id")
    if resolved_tree != tree:
        errors.append(f"{label} tree does not match the exact commit")
    return errors


def _common_payload_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt["payload_digest"] != launch_payload_digest(receipt):
        errors.append("launch receipt payload_digest is not canonical")
    if _contains_github_secret_like_content(receipt):
        errors.append("launch receipt contains secret-like content")
    return errors


def validate_s2e_launch_genesis_receipt(
    receipt: Any, *, repo_root: Path
) -> list[str]:
    errors = _schema_errors(receipt, "s2e_launch_genesis_receipt_v1")
    if errors:
        return errors
    assert isinstance(receipt, dict)
    errors.extend(_common_payload_errors(receipt))
    errors.extend(_git_binding_errors(
        repo_root,
        head=receipt["baseline_head"],
        tree=receipt["baseline_tree"],
        label="genesis baseline_head",
    ))
    errors.extend(_git_binding_errors(
        repo_root,
        head=receipt["schema_carrier_head"],
        tree=receipt["schema_carrier_tree"],
        label="genesis schema_carrier_head",
    ))
    if receipt["baseline_head"] == receipt["schema_carrier_head"]:
        errors.append("genesis baseline and schema carrier heads must be separate")
    elif not _is_ancestor(
        repo_root, receipt["baseline_head"], receipt["schema_carrier_head"]
    ):
        errors.append("genesis schema carrier must descend from the W0 baseline")
    return errors


def validate_s2e_launch_wave_receipt(
    receipt: Any, *, repo_root: Path
) -> list[str]:
    errors = _schema_errors(receipt, "s2e_launch_wave_receipt_v1")
    if errors:
        return errors
    assert isinstance(receipt, dict)
    errors.extend(_common_payload_errors(receipt))
    errors.extend(_git_binding_errors(
        repo_root,
        head=receipt["source_head"],
        tree=receipt["source_tree"],
        label="wave source_head",
    ))
    errors.extend(_git_binding_errors(
        repo_root,
        head=receipt["schema_carrier_head"],
        tree=receipt["schema_carrier_tree"],
        label="wave schema_carrier_head",
    ))
    if not _is_ancestor(
        repo_root, receipt["schema_carrier_head"], receipt["source_head"]
    ):
        errors.append("wave source head must descend from the schema carrier")
    return errors


def validate_s2e_launch_transition(
    receipt: Any,
    *,
    predecessor_receipt: Any,
    repo_root: Path,
    consumed_predecessor_digests: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    errors = validate_s2e_launch_wave_receipt(receipt, repo_root=repo_root)
    if errors or not isinstance(receipt, dict):
        return errors
    expected_index = LAUNCH_WAVES.index(receipt["wave"])
    if expected_index == 0:
        predecessor_errors = validate_s2e_launch_genesis_receipt(
            predecessor_receipt, repo_root=repo_root
        )
        expected_wave = GENESIS_WAVE
    else:
        predecessor_errors = validate_s2e_launch_wave_receipt(
            predecessor_receipt, repo_root=repo_root
        )
        expected_wave = LAUNCH_WAVES[expected_index - 1]
    errors.extend(f"predecessor: {error}" for error in predecessor_errors)
    if not isinstance(predecessor_receipt, dict):
        return errors
    if predecessor_receipt.get("wave") != expected_wave:
        errors.append(f"{receipt['wave']} predecessor must be {expected_wave}")
    if receipt["predecessor"] != predecessor_receipt.get("payload_digest"):
        errors.append("wave predecessor does not bind the exact prior payload digest")
    if receipt["predecessor"] in consumed_predecessor_digests:
        errors.append("wave predecessor payload digest was already consumed")
    if receipt["task_contract_digest"] != predecessor_receipt.get(
        "task_contract_digest"
    ):
        errors.append("wave task contract differs from its predecessor")
    return errors


def _external_verifier_error(
    verifier: CarrierVerifier | None,
    value: dict[str, Any],
    label: str,
) -> str | None:
    if verifier is None:
        return f"carrier attestation requires a trusted {label} verifier"
    try:
        admitted = verifier(value)
    except Exception as error:  # pragma: no cover - verifier boundary is fail-closed
        return f"carrier attestation {label} verifier failed: {error}"
    if admitted is not True:
        return f"carrier attestation {label} verifier rejected the artifact"
    return None


def validate_receipt_carrier_attestation(
    attestation: Any,
    *,
    payload_receipt: Any,
    repo_root: Path,
    now: str | datetime | None,
    governed_capture_identity_verifier: CarrierVerifier | None = None,
    signature_verifier: CarrierVerifier | None = None,
    immutable_readback_verifier: CarrierVerifier | None = None,
    consumed_attestation_digests: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    errors = _schema_errors(attestation, "receipt_carrier_attestation_v1")
    if errors:
        return errors
    assert isinstance(attestation, dict)
    if not isinstance(payload_receipt, dict):
        return ["carrier attestation requires the exact payload receipt"]
    payload_schema = payload_receipt.get("schema_version")
    if payload_schema == "s2e_launch_genesis_receipt_v1":
        errors.extend(
            f"payload: {error}"
            for error in validate_s2e_launch_genesis_receipt(
                payload_receipt, repo_root=repo_root
            )
        )
    elif payload_schema == "s2e_launch_wave_receipt_v1":
        errors.extend(
            f"payload: {error}"
            for error in validate_s2e_launch_wave_receipt(
                payload_receipt, repo_root=repo_root
            )
        )
    else:
        errors.append("carrier attestation payload schema is not a launch receipt")
    if attestation["payload_schema_version"] != payload_schema:
        errors.append("carrier attestation payload schema binding differs")
    if attestation["payload_digest"] != payload_receipt.get("payload_digest"):
        errors.append("carrier attestation payload digest binding differs")
    if attestation["schema_carrier_head"] != payload_receipt.get(
        "schema_carrier_head"
    ):
        errors.append("carrier attestation schema carrier head differs from payload")
    if attestation["schema_carrier_tree"] != payload_receipt.get(
        "schema_carrier_tree"
    ):
        errors.append("carrier attestation schema carrier tree differs from payload")
    errors.extend(_git_binding_errors(
        repo_root,
        head=attestation["schema_carrier_head"],
        tree=attestation["schema_carrier_tree"],
        label="attestation schema_carrier_head",
    ))
    errors.extend(_git_binding_errors(
        repo_root,
        head=attestation["carrier_head"],
        tree=attestation["carrier_tree"],
        label="attestation carrier_head",
    ))
    if not _is_ancestor(
        repo_root, attestation["schema_carrier_head"], attestation["carrier_head"]
    ):
        errors.append("attestation carrier head must descend from schema carrier")
    try:
        blob = _git(
            repo_root,
            "rev-parse",
            "--verify",
            f"{attestation['carrier_head']}:{attestation['carrier_path']}",
        ).stdout.strip()
        carrier_bytes = _git(
            repo_root,
            "show",
            f"{attestation['carrier_head']}:{attestation['carrier_path']}",
        ).stdout
        carrier_payload = json.loads(carrier_bytes)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        errors.append(f"carrier attestation exact blob is unreadable: {error}")
    else:
        if blob != attestation["carrier_blob"]:
            errors.append("carrier attestation blob differs from exact Git blob")
        if carrier_payload != payload_receipt:
            errors.append("carrier Git blob does not contain the exact payload receipt")
    if attestation["attested_core_digest"] != s2e_carrier_attested_core_digest(
        attestation
    ):
        errors.append("carrier attested_core_digest is invalid")
    if attestation["signature"]["signed_digest"] != attestation[
        "attested_core_digest"
    ]:
        errors.append("carrier signature does not bind attested_core_digest")
    if attestation["attestation_digest"] != s2e_carrier_attestation_digest(
        attestation
    ):
        errors.append("carrier attestation_digest is invalid")
    if attestation["attestation_digest"] in consumed_attestation_digests:
        errors.append("carrier attestation digest was already consumed")
    try:
        issued_at = _time(attestation["issued_at"])
        expires_at = _time(attestation["expires_at"])
        evaluated_at = _time(now or datetime.now(timezone.utc))
        if not issued_at < expires_at:
            errors.append("carrier attestation freshness window is invalid")
        if (expires_at - issued_at).total_seconds() > 600:
            errors.append("carrier attestation freshness window exceeds 600 seconds")
        if not issued_at <= evaluated_at < expires_at:
            errors.append("carrier attestation is stale or not yet valid")
    except (TypeError, ValueError) as error:
        errors.append(f"carrier attestation timestamp is invalid: {error}")
    capture_identity = attestation["governed_capture_identity"]
    if capture_identity["task_contract_digest"] != payload_receipt.get(
        "task_contract_digest"
    ):
        errors.append("governed capture identity task contract differs from payload")
    for verifier, value, label in (
        (
            governed_capture_identity_verifier,
            capture_identity,
            "governed-capture identity",
        ),
        (signature_verifier, attestation, "signature"),
        (immutable_readback_verifier, attestation, "immutable-readback"),
    ):
        error = _external_verifier_error(verifier, value, label)
        if error is not None:
            errors.append(error)
    if _contains_github_secret_like_content(attestation):
        errors.append("carrier attestation contains secret-like content")
    return errors


def build_genesis_candidate(
    *,
    repo_root: Path,
    baseline_head: str,
    schema_carrier_head: str,
    task_contract_digest: str,
) -> dict[str, Any]:
    _require_clean(repo_root)
    receipt: dict[str, Any] = {
        "schema_version": "s2e_launch_genesis_receipt_v1",
        "launch_id": LAUNCH_ID,
        "wave": GENESIS_WAVE,
        "predecessor": None,
        "baseline_head": _commit(repo_root, baseline_head),
        "baseline_tree": _tree(repo_root, baseline_head),
        "schema_carrier_head": _commit(repo_root, schema_carrier_head),
        "schema_carrier_tree": _tree(repo_root, schema_carrier_head),
        "task_contract_digest": task_contract_digest,
        "checkpoint_status": "W0_GENESIS_READY",
        "side_effect_class": "SOURCE_ONLY",
        "production_effect_count": 0,
    }
    receipt["payload_digest"] = launch_payload_digest(receipt)
    errors = validate_s2e_launch_genesis_receipt(receipt, repo_root=repo_root)
    if errors:
        raise ValueError("; ".join(errors))
    return receipt


def build_wave_candidate(
    *,
    repo_root: Path,
    wave: str,
    source_head: str,
    schema_carrier_head: str,
    predecessor_receipt: dict[str, Any],
    task_contract_digest: str,
    side_effect_class: str = "SOURCE_ONLY",
) -> dict[str, Any]:
    _require_clean(repo_root)
    receipt: dict[str, Any] = {
        "schema_version": "s2e_launch_wave_receipt_v1",
        "launch_id": LAUNCH_ID,
        "wave": wave,
        "predecessor": predecessor_receipt.get("payload_digest"),
        "source_head": _commit(repo_root, source_head),
        "source_tree": _tree(repo_root, source_head),
        "schema_carrier_head": _commit(repo_root, schema_carrier_head),
        "schema_carrier_tree": _tree(repo_root, schema_carrier_head),
        "task_contract_digest": task_contract_digest,
        "checkpoint_status": "TASK_BRANCH_CHECKPOINT_READY",
        "side_effect_class": side_effect_class,
        "production_effect_count": 0,
    }
    receipt["payload_digest"] = launch_payload_digest(receipt)
    errors = validate_s2e_launch_transition(
        receipt, predecessor_receipt=predecessor_receipt, repo_root=repo_root
    )
    if errors:
        raise ValueError("; ".join(errors))
    return receipt
