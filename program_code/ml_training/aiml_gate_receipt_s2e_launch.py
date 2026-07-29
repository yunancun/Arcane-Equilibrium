"""Closed, Git-bound launch receipt payloads for S2E-LW1 through S2E-LW5."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any

from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _contains_github_secret_like_content,
    _load_schema,
    canonical_digest,
)


LAUNCH_ID = "S2E-LW1-LW5"
GENESIS_WAVE = "W0-GENESIS"
LAUNCH_WAVES = ("S2E-LW1", "S2E-LW2", "S2E-LW3", "S2E-LW4", "S2E-LW5")


def launch_payload_digest(receipt: dict[str, Any]) -> str:
    """Digest a payload without making the digest field self-referential."""

    return canonical_digest({
        key: value for key, value in receipt.items() if key != "payload_digest"
    })


def canonical_launch_payload_bytes(receipt: dict[str, Any]) -> bytes:
    """One carrier serialization: canonical UTF-8 JSON followed by one LF."""

    return (
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _raw_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


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


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout


def _strict_json_object(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs)


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
    if expected_index > 0 and not _is_ancestor(
        repo_root,
        str(predecessor_receipt.get("source_head", "")),
        receipt["source_head"],
    ):
        errors.append(
            "wave predecessor source head must be an ancestor of current source head"
        )
    if receipt["predecessor"] != predecessor_receipt.get("payload_digest"):
        errors.append("wave predecessor does not bind the exact prior payload digest")
    if receipt["predecessor"] in consumed_predecessor_digests:
        errors.append("wave predecessor payload digest was already consumed")
    if receipt["launch_contract_digest"] != predecessor_receipt.get(
        "launch_contract_digest"
    ):
        errors.append("wave launch contract differs from its predecessor")
    return errors


def validate_receipt_carrier_attestation(
    attestation: Any,
    *,
    payload_receipt: Any,
    repo_root: Path,
    now: str | datetime | None,
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
    if attestation["launch_contract_digest"] != payload_receipt.get(
        "launch_contract_digest"
    ):
        errors.append("carrier attestation launch contract binding differs")
    if attestation["payload_generation_task_contract_digest"] != (
        payload_receipt.get("generation_task_contract_digest")
    ):
        errors.append("carrier attestation payload generation binding differs")
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
        carrier_bytes = _git_bytes(
            repo_root, "show", f"{attestation['carrier_head']}:{attestation['carrier_path']}"
        )
        carrier_text = carrier_bytes.decode("utf-8")
        if _contains_github_secret_like_content(carrier_text):
            errors.append("carrier contains secret-like raw carrier content")
        carrier_payload = _strict_json_object(carrier_bytes)
    except (
        OSError,
        subprocess.CalledProcessError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        errors.append(f"carrier attestation exact blob is unreadable: {error}")
    else:
        if blob != attestation["carrier_blob"]:
            errors.append("carrier attestation blob differs from exact Git blob")
        if _raw_digest(carrier_bytes) != attestation["carrier_raw_digest"]:
            errors.append("carrier attestation raw digest differs from exact Git blob")
        if carrier_bytes != canonical_launch_payload_bytes(payload_receipt):
            errors.append(
                "carrier Git blob bytes differ from canonical launch payload serialization"
            )
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
    if capture_identity["task_contract_digest"] != attestation[
        "verification_task_contract_digest"
    ]:
        errors.append(
            "governed capture identity task contract differs from verification generation"
        )
    if _contains_github_secret_like_content(attestation):
        errors.append("carrier attestation contains secret-like content")
    errors.append(
        "carrier attestation EXTERNAL_VERIFICATION_PENDING: trusted-host governed "
        "capture, independent SSHSIG, and immutable readback evidence are required"
    )
    return errors


def verify_receipt_carrier_attestation(
    attestation: Any,
    *,
    payload_receipt: Any,
    repo_root: Path,
    now: str | datetime,
    governed_capture_record: Any,
    external_append_intent: Any,
    external_append_result: Any,
    external_readback_ack: Any,
) -> dict[str, Any]:
    """Validate real typed inputs but remain pending without an independent key."""

    from agent_governance_command_capture_v2 import (
        validate_governed_command_capture,
    )
    import agent_governance_aiml_trusted_host as trusted_host
    import agent_governance_terminal_receipt_external_sink as external_sink

    errors = validate_receipt_carrier_attestation(
        attestation,
        payload_receipt=payload_receipt,
        repo_root=repo_root,
        now=now,
    )
    if isinstance(attestation, dict):
        identity = attestation.get("governed_capture_identity", {})
        verification_digest = attestation.get("verification_task_contract_digest")
        carrier_head = attestation.get("carrier_head")
    else:
        identity, verification_digest, carrier_head = {}, None, None
    capture_errors = validate_governed_command_capture(
        governed_capture_record,
        expected_context_artifact_digest=identity.get("context_artifact_digest"),
        expected_task_contract_digest=verification_digest,
        expected_source_head=carrier_head,
        root=repo_root,
    )
    errors.extend(f"governed command capture: {error}" for error in capture_errors)
    if isinstance(governed_capture_record, dict):
        projection = {
            "schema_version": "governed_capture_identity_v1",
            "record_digest": governed_capture_record.get("record_digest"),
            "context_artifact_digest": governed_capture_record.get(
                "context_artifact_digest"
            ),
            "task_contract_digest": governed_capture_record.get(
                "task_contract_digest"
            ),
            "node_id": governed_capture_record.get("node_id"),
            "role_id": governed_capture_record.get("role_id"),
            "native_agent": governed_capture_record.get("native_agent"),
            "permission": governed_capture_record.get("permission"),
        }
        if projection != identity:
            errors.append("governed command capture identity projection mismatch")
        signer_role = (
            attestation.get("signer", {}).get("role")
            if isinstance(attestation, dict)
            else None
        )
        if signer_role == governed_capture_record.get("role_id"):
            errors.append("carrier signer role must differ from capture role")
    now_text = _time(now).isoformat()
    errors.extend(
        f"external worm intent: {error}"
        for error in external_sink.validate_external_worm_append_intent(
            external_append_intent, now=now_text
        )
    )
    errors.extend(
        f"external worm result: {error}"
        for error in external_sink.validate_external_worm_append_result(
            external_append_result,
            intent=external_append_intent,
            now=now_text,
        )
    )
    errors.extend(
        f"external worm readback: {error}"
        for error in external_sink.validate_external_worm_readback_ack(
            external_readback_ack,
            result=external_append_result,
            now=now_text,
        )
    )
    if isinstance(attestation, dict):
        signer = attestation.get("signer", {})
        signature = attestation.get("signature", {})
        signature_valid = bool(
            signer.get("key_fingerprint")
            == trusted_host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT
            and trusted_host._verify_ssh_signature(
                json.dumps(
                    {
                        key: value
                        for key, value in attestation.items()
                        if key not in {
                            "attested_core_digest",
                            "signature",
                            "attestation_digest",
                        }
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8"),
                str(signature.get("signature", "")).encode("utf-8"),
                public_key=trusted_host.TRUSTED_EXECUTION_PUBLIC_KEY,
                identity="aiml-s2e-receipt-carrier-v1",
                namespace="arcane-equilibrium-aiml-s2e-receipt-carrier",
            )
        )
        if not signature_valid:
            errors.append("carrier SSHSIG authentication against pinned key failed")
    errors.append(
        "independent carrier signing key unavailable: existing trusted profiles "
        "share one physical key with capture authentication"
    )
    result = {
        "schema_version": "receipt_carrier_verification_result_v1",
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "attestation_digest": (
            attestation.get("attestation_digest")
            if isinstance(attestation, dict)
            else None
        ),
        "verification_task_contract_digest": verification_digest,
        "governed_capture_record_digest": (
            governed_capture_record.get("record_digest")
            if isinstance(governed_capture_record, dict)
            else None
        ),
        "external_result_digest": (
            external_append_result.get("result_digest")
            if isinstance(external_append_result, dict)
            else None
        ),
        "external_readback_ack_digest": (
            external_readback_ack.get("ack_digest")
            if isinstance(external_readback_ack, dict)
            else None
        ),
        "independent_signing_key_available": False,
        "errors": sorted(set(errors)),
    }
    result["verification_result_digest"] = canonical_digest(result)
    return result


def issue_s2e_launch_receipt(
    candidate: Any,
    *,
    acceptance_review_bundle: Any,
    repo_root: Path,
    now: str | datetime,
) -> dict[str, Any]:
    """Keep candidate issuance pending until governed review is independently verified."""

    if isinstance(candidate, dict) and candidate.get("schema_version") == (
        "s2e_launch_genesis_receipt_v1"
    ):
        errors = validate_s2e_launch_genesis_receipt(candidate, repo_root=repo_root)
        reviewed_head = candidate.get("schema_carrier_head")
        reviewed_tree = candidate.get("schema_carrier_tree")
    elif isinstance(candidate, dict) and candidate.get("schema_version") == (
        "s2e_launch_wave_receipt_v1"
    ):
        errors = validate_s2e_launch_wave_receipt(candidate, repo_root=repo_root)
        reviewed_head = candidate.get("source_head")
        reviewed_tree = candidate.get("source_tree")
    else:
        errors = ["launch receipt candidate schema is unsupported"]
        reviewed_head = reviewed_tree = None

    required_bundle_fields = {
        "schema_version",
        "launch_contract_digest",
        "wave",
        "reviewed_source_head",
        "reviewed_source_tree",
        "generation_task_contract_digest",
        "predicate_results",
        "reviewer_identity",
        "command_capture_record_digests",
        "issued_at",
        "expires_at",
        "signature",
        "immutable_readback",
        "bundle_digest",
    }
    if not isinstance(acceptance_review_bundle, dict):
        errors.append("acceptance review bundle must be an object")
    elif set(acceptance_review_bundle) != required_bundle_fields:
        errors.append("acceptance review bundle fields are not exact")
    else:
        bindings = {
            "launch_contract_digest": candidate.get("launch_contract_digest"),
            "wave": candidate.get("wave"),
            "reviewed_source_head": reviewed_head,
            "reviewed_source_tree": reviewed_tree,
            "generation_task_contract_digest": candidate.get(
                "generation_task_contract_digest"
            ),
        }
        for field, expected in bindings.items():
            if acceptance_review_bundle.get(field) != expected:
                errors.append(f"acceptance review bundle {field} binding differs")
        if acceptance_review_bundle["schema_version"] != (
            "s2e_launch_acceptance_review_bundle_v1"
        ):
            errors.append("acceptance review bundle schema version is invalid")
        if acceptance_review_bundle["bundle_digest"] != canonical_digest({
            key: value
            for key, value in acceptance_review_bundle.items()
            if key != "bundle_digest"
        }):
            errors.append("acceptance review bundle digest is invalid")
        try:
            issued_at = _time(acceptance_review_bundle["issued_at"])
            expires_at = _time(acceptance_review_bundle["expires_at"])
            evaluated_at = _time(now)
            if not issued_at <= evaluated_at < expires_at:
                errors.append("acceptance review bundle is stale or not yet valid")
        except (TypeError, ValueError) as error:
            errors.append(f"acceptance review bundle timestamp is invalid: {error}")

    errors.append(
        "acceptance review bundle EXTERNAL_VERIFICATION_PENDING: governed "
        "predicate review, independent SSHSIG, and immutable readback are required"
    )
    result = {
        "schema_version": "launch_receipt_issuance_result_v1",
        "status": "EXTERNAL_VERIFICATION_PENDING",
        "candidate_payload_digest": (
            candidate.get("payload_digest") if isinstance(candidate, dict) else None
        ),
        "acceptance_review_bundle_digest": (
            acceptance_review_bundle.get("bundle_digest")
            if isinstance(acceptance_review_bundle, dict)
            else None
        ),
        "issued_receipt": None,
        "errors": sorted(set(errors)),
    }
    result["issuance_result_digest"] = canonical_digest(result)
    return result


def build_genesis_candidate(
    *,
    repo_root: Path,
    baseline_head: str,
    schema_carrier_head: str,
    launch_contract_digest: str,
    generation_task_contract_digest: str,
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
        "launch_contract_digest": launch_contract_digest,
        "generation_task_contract_digest": generation_task_contract_digest,
        "checkpoint_status": "PENDING_REVIEW",
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
    launch_contract_digest: str,
    generation_task_contract_digest: str,
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
        "launch_contract_digest": launch_contract_digest,
        "generation_task_contract_digest": generation_task_contract_digest,
        "checkpoint_status": "PENDING_REVIEW",
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
