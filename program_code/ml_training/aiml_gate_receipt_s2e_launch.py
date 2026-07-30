"""Closed, Git-bound launch receipt payloads for S2E-LW1 through S2E-LW5."""

from __future__ import annotations

import base64
import json
import hashlib
import os
import stat
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
S2E_RECEIPT_SIGNER_IDENTITY = "aiml-s2e-receipt-signer-v1"
S2E_RECEIPT_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2e-receipts"
S2E_RECEIPT_TRUST_ROOT_PATH = Path(
    "/etc/arcane-equilibrium/aiml/s2e-receipt-trust-root-v1.json"
)
S2E_RECEIPT_TRUST_ROOT_OWNER_UID = 0
S2E_RECEIPT_TRUST_ROOT_MODE = 0o644
_S2E_RECEIPT_TRUST_ROOT_FIELDS = {
    "schema_version",
    "signer_identity",
    "signature_namespace",
    "algorithm",
    "key_generation",
    "anchor",
    "public_key",
    "key_fingerprint",
}
_S2E_RECEIPT_TRUST_ROOT_MAX_BYTES = 16 * 1024
_S2E_REVIEW_COMMON_PREDICATES = (
    "CANDIDATE_SCHEMA_VALID",
    "EXACT_SOURCE_HEAD_TREE_VALID",
    "EXTERNAL_WORM_IMMUTABLE_READBACK_VALID",
    "INDEPENDENT_GOVERNED_REVIEW_VALID",
    "INDEPENDENT_SSHSIG_VALID",
)


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


def s2e_carrier_signed_bytes(attestation: dict[str, Any]) -> bytes:
    """Domain-separated SSHSIG subject for one carrier attestation."""

    return json.dumps(
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
    ).encode("utf-8")


def _s2e_worm_envelope(
    schema_version: str,
    content: bytes,
    *,
    digest_field: str,
    bytes_field: str,
    bindings: dict[str, Any],
) -> dict[str, Any]:
    """One shared exact-byte envelope for carrier and signed-review WORM writes."""

    return {
        "schema_version": schema_version,
        **bindings,
        digest_field: _raw_digest(content),
        bytes_field: base64.b64encode(content).decode("ascii"),
    }


def s2e_carrier_worm_payload(
    attestation: dict[str, Any], *, payload_receipt: dict[str, Any]
) -> dict[str, Any]:
    """Envelope the exact canonical carrier bytes for established WORM adapters."""

    carrier_bytes = canonical_launch_payload_bytes(payload_receipt)
    return _s2e_worm_envelope(
        "s2e_carrier_worm_payload_v1",
        carrier_bytes,
        digest_field="carrier_raw_digest",
        bytes_field="carrier_bytes_base64",
        bindings={
            "payload_digest": payload_receipt.get("payload_digest"),
            "carrier_head": attestation.get("carrier_head"),
            "carrier_path": attestation.get("carrier_path"),
        },
    )


def s2e_review_predicate_results(wave: str) -> list[dict[str, str]]:
    """Return the exact code-owned acceptance predicates for one launch wave."""

    if wave == GENESIS_WAVE:
        predicates = _S2E_REVIEW_COMMON_PREDICATES
    elif wave in LAUNCH_WAVES:
        predicates = _S2E_REVIEW_COMMON_PREDICATES + (
            "PREDECESSOR_CHAIN_VALID",
        )
    else:
        raise ValueError("unknown S2E launch wave")
    return [
        {"predicate_id": predicate_id, "result": "PASS"}
        for predicate_id in predicates
    ]


def s2e_acceptance_review_signed_bytes(bundle: dict[str, Any]) -> bytes:
    """Canonical review subject shared by SSHSIG and the external WORM payload."""

    return json.dumps(
        {
            key: value
            for key, value in bundle.items()
            if key not in {
                "signed_core_digest",
                "signature",
                "external_worm_binding",
                "bundle_digest",
            }
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def s2e_acceptance_review_worm_payload(
    bundle: dict[str, Any],
) -> dict[str, Any]:
    signed_bytes = s2e_acceptance_review_signed_bytes(bundle)
    return _s2e_worm_envelope(
        "s2e_acceptance_review_worm_payload_v1",
        signed_bytes,
        digest_field="signed_core_digest",
        bytes_field="signed_core_bytes_base64",
        bindings={
            "candidate_payload_digest": bundle.get("candidate_payload_digest"),
            "reviewed_source_head": bundle.get("reviewed_source_head"),
        },
    )


def s2e_acceptance_review_bundle_digest(bundle: dict[str, Any]) -> str:
    return canonical_digest({
        key: value for key, value in bundle.items() if key != "bundle_digest"
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


def load_s2e_receipt_signer_trust_root() -> tuple[dict[str, Any] | None, list[str]]:
    """Securely load the one code-owned off-repository public signer root."""

    import agent_governance_aiml_trusted_host as trusted_host

    path = S2E_RECEIPT_TRUST_ROOT_PATH
    errors: list[str] = []
    if not path.is_absolute():
        return None, ["S2E receipt trust-root path is not absolute"]
    try:
        if path.is_relative_to(Path(__file__).resolve().parents[2]):
            return None, ["S2E receipt trust-root path must be off-repository"]
    except ValueError:
        pass
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode):
            raise ValueError("trust-root path is a symlink")
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                errors.append("S2E receipt trust root is not a regular file")
            if opened.st_nlink != 1:
                errors.append("S2E receipt trust root link count is not one")
            if opened.st_uid != S2E_RECEIPT_TRUST_ROOT_OWNER_UID:
                errors.append("S2E receipt trust root owner is not trusted")
            if stat.S_IMODE(opened.st_mode) != S2E_RECEIPT_TRUST_ROOT_MODE:
                errors.append("S2E receipt trust root mode is not exact")
            raw = bytearray()
            while len(raw) <= _S2E_RECEIPT_TRUST_ROOT_MAX_BYTES:
                chunk = os.read(
                    fd,
                    min(
                        4096,
                        _S2E_RECEIPT_TRUST_ROOT_MAX_BYTES + 1 - len(raw),
                    ),
                )
                if not chunk:
                    break
                raw.extend(chunk)
        finally:
            os.close(fd)
        after = os.lstat(path)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
        ) or (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
        ):
            errors.append("S2E receipt trust root changed while being read")
    except (OSError, ValueError) as error:
        return None, [f"S2E receipt trust root is unavailable or untrusted: {error}"]
    if len(raw) > _S2E_RECEIPT_TRUST_ROOT_MAX_BYTES:
        errors.append("S2E receipt trust root exceeds size limit")
        return None, errors
    try:
        profile = _strict_json_object(bytes(raw))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return None, errors + [f"S2E receipt trust root JSON is invalid: {error}"]
    if not isinstance(profile, dict) or set(profile) != _S2E_RECEIPT_TRUST_ROOT_FIELDS:
        return None, errors + ["S2E receipt trust root fields are not exact"]
    expected_values = {
        "schema_version": "s2e_receipt_signer_trust_root_v1",
        "signer_identity": S2E_RECEIPT_SIGNER_IDENTITY,
        "signature_namespace": S2E_RECEIPT_SIGNATURE_NAMESPACE,
        "algorithm": "SSH-ED25519",
        "key_generation": "independent_off_repo_ed25519_v1",
        "anchor": "fixed_off_repo_public_trust_root_v1",
    }
    for field, expected in expected_values.items():
        if profile.get(field) != expected:
            errors.append(f"S2E receipt trust root {field} is invalid")
    public_key = profile.get("public_key")
    fingerprint = profile.get("key_fingerprint")
    try:
        derived = trusted_host.ssh_public_key_fingerprint(str(public_key))
    except ValueError as error:
        errors.append(f"S2E receipt trust root public key is invalid: {error}")
    else:
        if fingerprint != derived:
            errors.append("S2E receipt trust root fingerprint does not match public key")
        if (
            public_key == trusted_host.TRUSTED_EXECUTION_PUBLIC_KEY
            or derived == trusted_host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT
        ):
            errors.append(
                "S2E receipt trust root is not independent from governed capture root"
            )
    if _contains_github_secret_like_content(profile):
        errors.append("S2E receipt trust root contains secret-like content")
    return (profile if not errors else None), errors


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
    checkpoint = receipt.get("checkpoint_status")
    review_digest = receipt.get("acceptance_review_bundle_digest")
    if checkpoint == "PENDING_REVIEW" and review_digest is not None:
        errors.append("pending launch candidate cannot bind an acceptance review")
    if checkpoint != "PENDING_REVIEW" and review_digest is None:
        errors.append("ready launch receipt must bind an acceptance review bundle")
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
    """Verify a carrier through fixed-root SSHSIG, capture, and external WORM."""

    from agent_governance_command_capture_v2 import (
        validate_governed_command_capture,
    )
    import agent_governance_terminal_receipt_external_sink as external_sink
    import agent_governance_terminal_receipt_sink as terminal_sink

    errors = validate_receipt_carrier_attestation(
        attestation,
        payload_receipt=payload_receipt,
        repo_root=repo_root,
        now=now,
    )
    errors = [
        error
        for error in errors
        if not error.startswith("carrier attestation EXTERNAL_VERIFICATION_PENDING:")
    ]
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
        if governed_capture_record.get("result") != "PASS":
            errors.append("governed command capture did not PASS")
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
    if isinstance(external_append_result, dict) and external_append_result.get(
        "append_status"
    ) not in external_sink.EXTERNAL_COMMITTED_STATUSES:
        errors.append("external worm carrier append is not committed")
    if isinstance(external_readback_ack, dict) and not (
        external_readback_ack.get("ack") is True
        and external_readback_ack.get("immutability_proven") is True
    ):
        errors.append("external worm carrier readback is not independently immutable")
    if isinstance(attestation, dict) and isinstance(payload_receipt, dict):
        append_result = (
            external_append_result
            if isinstance(external_append_result, dict)
            else {}
        )
        readback_ack = (
            external_readback_ack
            if isinstance(external_readback_ack, dict)
            else {}
        )
        worm_payload = s2e_carrier_worm_payload(
            attestation, payload_receipt=payload_receipt
        )
        expected_worm_digest = terminal_sink.terminal_payload_digest(worm_payload)
        intent_digest = (
            (external_append_intent.get("append_intent") or {})
            .get("payload_binding", {})
            .get("terminal_payload_digest")
            if isinstance(external_append_intent, dict)
            else None
        )
        if intent_digest != expected_worm_digest:
            errors.append(
                "external worm intent does not bind exact canonical carrier bytes"
            )
        immutable = attestation.get("immutable_readback", {})
        for field, actual in (
            ("object_id", append_result.get("record_locator")),
            ("version_id", append_result.get("object_version_id")),
            ("readback_digest", readback_ack.get("ack_digest")),
        ):
            if immutable.get(field) != actual:
                errors.append(
                    f"carrier immutable readback {field} is not bound to external WORM"
                )
    profile, trust_errors = load_s2e_receipt_signer_trust_root()
    errors.extend(trust_errors)
    if isinstance(attestation, dict) and profile is not None:
        import agent_governance_aiml_trusted_host as trusted_host

        signer = attestation.get("signer", {})
        signature = attestation.get("signature", {})
        for field, profile_field in (
            ("identity", "signer_identity"),
            ("namespace", "signature_namespace"),
            ("key_generation", "key_generation"),
            ("anchor", "anchor"),
            ("key_fingerprint", "key_fingerprint"),
        ):
            if signer.get(field) != profile.get(profile_field):
                errors.append(f"carrier signer {field} differs from fixed trust root")
        if not trusted_host._verify_ssh_signature(
            s2e_carrier_signed_bytes(attestation),
            str(signature.get("signature", "")).encode("ascii", errors="ignore"),
            public_key=str(profile["public_key"]),
            identity=S2E_RECEIPT_SIGNER_IDENTITY,
            namespace=S2E_RECEIPT_SIGNATURE_NAMESPACE,
        ):
            errors.append("carrier SSHSIG authentication against fixed root failed")
    status = "VERIFIED" if not errors else "EXTERNAL_VERIFICATION_PENDING"
    result = {
        "schema_version": "receipt_carrier_verification_result_v1",
        "status": status,
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
        "independent_signing_key_available": profile is not None,
        "errors": sorted(set(errors)),
    }
    result["verification_result_digest"] = canonical_digest(result)
    return result


def validate_s2e_launch_acceptance_review_bundle(
    bundle: Any,
    *,
    candidate: Any,
    governed_capture_record: Any,
    external_append_intent: Any,
    external_append_result: Any,
    external_readback_ack: Any,
    repo_root: Path,
    now: str | datetime,
) -> list[str]:
    """Validate one signed, capture-bound, externally immutable review bundle."""

    from agent_governance_command_capture_v2 import (
        validate_governed_command_capture,
    )
    import agent_governance_aiml_trusted_host as trusted_host
    import agent_governance_terminal_receipt_external_sink as external_sink
    import agent_governance_terminal_receipt_sink as terminal_sink

    schema_errors = _schema_errors(bundle, "s2e_launch_acceptance_review_bundle_v1")
    if schema_errors:
        return [
            f"acceptance review bundle schema violation: {error}"
            for error in schema_errors
        ]
    errors: list[str] = []
    assert isinstance(bundle, dict)
    if not isinstance(candidate, dict):
        return ["acceptance review bundle requires the exact launch candidate"]
    if candidate.get("schema_version") == "s2e_launch_genesis_receipt_v1":
        errors.extend(
            validate_s2e_launch_genesis_receipt(candidate, repo_root=repo_root)
        )
        reviewed_head = candidate.get("schema_carrier_head")
        reviewed_tree = candidate.get("schema_carrier_tree")
    elif candidate.get("schema_version") == "s2e_launch_wave_receipt_v1":
        errors.extend(validate_s2e_launch_wave_receipt(candidate, repo_root=repo_root))
        reviewed_head = candidate.get("source_head")
        reviewed_tree = candidate.get("source_tree")
    else:
        return ["acceptance review bundle candidate schema is unsupported"]
    if candidate.get("checkpoint_status") != "PENDING_REVIEW":
        errors.append("acceptance review bundle requires a pending candidate")
    for field, expected in (
        ("candidate_payload_digest", candidate.get("payload_digest")),
        ("launch_id", candidate.get("launch_id")),
        ("wave", candidate.get("wave")),
        ("reviewed_source_head", reviewed_head),
        ("reviewed_source_tree", reviewed_tree),
        (
            "generation_task_contract_digest",
            candidate.get("generation_task_contract_digest"),
        ),
    ):
        if bundle.get(field) != expected:
            errors.append(f"acceptance review bundle {field} binding differs")
    if bundle.get("predicate_results") != s2e_review_predicate_results(
        str(candidate.get("wave"))
    ):
        errors.append("acceptance review bundle predicates are not the exact code-owned set")
    if bundle.get("bundle_digest") != s2e_acceptance_review_bundle_digest(bundle):
        errors.append("acceptance review bundle digest is invalid")
    signed_bytes = s2e_acceptance_review_signed_bytes(bundle)
    signed_digest = _raw_digest(signed_bytes)
    if bundle.get("signed_core_digest") != signed_digest:
        errors.append("acceptance review signed core digest is invalid")
    signature = bundle.get("signature", {})
    if signature.get("signed_digest") != signed_digest:
        errors.append("acceptance review signature does not bind signed core")
    try:
        issued_at = _time(bundle["issued_at"])
        expires_at = _time(bundle["expires_at"])
        evaluated_at = _time(now)
        if not issued_at < expires_at:
            errors.append("acceptance review freshness window is invalid")
        if (expires_at - issued_at).total_seconds() > 600:
            errors.append("acceptance review freshness window exceeds 600 seconds")
        if not issued_at <= evaluated_at < expires_at:
            errors.append("acceptance review bundle is stale or not yet valid")
    except (TypeError, ValueError) as error:
        errors.append(f"acceptance review bundle timestamp is invalid: {error}")
    capture_identity = bundle.get("governed_capture_identity", {})
    capture_errors = validate_governed_command_capture(
        governed_capture_record,
        expected_context_artifact_digest=capture_identity.get(
            "context_artifact_digest"
        ),
        expected_task_contract_digest=capture_identity.get("task_contract_digest"),
        expected_source_head=reviewed_head,
        root=repo_root,
    )
    errors.extend(f"acceptance review governed capture: {error}" for error in capture_errors)
    if isinstance(governed_capture_record, dict):
        capture_projection = {
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
        if capture_identity != capture_projection:
            errors.append("acceptance review governed capture projection differs")
        if bundle.get("governed_capture_record_digest") != (
            governed_capture_record.get("record_digest")
        ):
            errors.append("acceptance review governed capture digest differs")
        reviewer_projection = {
            field: governed_capture_record.get(field)
            for field in ("node_id", "role_id", "native_agent", "permission")
        }
        if bundle.get("reviewer_identity") != reviewer_projection:
            errors.append("acceptance review reviewer identity differs from capture")
        if governed_capture_record.get("result") != "PASS":
            errors.append("acceptance review governed capture did not PASS")
        if bundle.get("signer", {}).get("role") == governed_capture_record.get(
            "role_id"
        ):
            errors.append("acceptance review signer role must differ from reviewer role")
    now_text = _time(now).isoformat()
    errors.extend(
        f"acceptance review external worm intent: {error}"
        for error in external_sink.validate_external_worm_append_intent(
            external_append_intent, now=now_text
        )
    )
    errors.extend(
        f"acceptance review external worm result: {error}"
        for error in external_sink.validate_external_worm_append_result(
            external_append_result,
            intent=external_append_intent,
            now=now_text,
        )
    )
    errors.extend(
        f"acceptance review external worm readback: {error}"
        for error in external_sink.validate_external_worm_readback_ack(
            external_readback_ack,
            result=external_append_result,
            now=now_text,
        )
    )
    if not (
        isinstance(external_append_result, dict)
        and external_append_result.get("append_status")
        in external_sink.EXTERNAL_COMMITTED_STATUSES
    ):
        errors.append("acceptance review external WORM append is not committed")
    if not (
        isinstance(external_readback_ack, dict)
        and external_readback_ack.get("ack") is True
        and external_readback_ack.get("immutability_proven") is True
    ):
        errors.append("acceptance review external WORM readback is not immutable")
    expected_worm_digest = terminal_sink.terminal_payload_digest(
        s2e_acceptance_review_worm_payload(bundle)
    )
    intent_digest = (
        (external_append_intent.get("append_intent") or {})
        .get("payload_binding", {})
        .get("terminal_payload_digest")
        if isinstance(external_append_intent, dict)
        else None
    )
    if intent_digest != expected_worm_digest:
        errors.append("acceptance review external WORM bytes binding differs")
    worm_binding = bundle.get("external_worm_binding", {})
    for field, actual in (
        (
            "result_digest",
            external_append_result.get("result_digest")
            if isinstance(external_append_result, dict)
            else None,
        ),
        (
            "readback_ack_digest",
            external_readback_ack.get("ack_digest")
            if isinstance(external_readback_ack, dict)
            else None,
        ),
        (
            "record_locator",
            external_append_result.get("record_locator")
            if isinstance(external_append_result, dict)
            else None,
        ),
        (
            "object_version_id",
            external_append_result.get("object_version_id")
            if isinstance(external_append_result, dict)
            else None,
        ),
        (
            "checksum_sha256",
            external_append_result.get("checksum_sha256")
            if isinstance(external_append_result, dict)
            else None,
        ),
    ):
        if worm_binding.get(field) != actual:
            errors.append(f"acceptance review external WORM {field} binding differs")
    profile, trust_errors = load_s2e_receipt_signer_trust_root()
    errors.extend(trust_errors)
    if profile is not None:
        signer = bundle.get("signer", {})
        for field, profile_field in (
            ("identity", "signer_identity"),
            ("namespace", "signature_namespace"),
            ("key_generation", "key_generation"),
            ("anchor", "anchor"),
            ("key_fingerprint", "key_fingerprint"),
        ):
            if signer.get(field) != profile.get(profile_field):
                errors.append(
                    f"acceptance review signer {field} differs from fixed trust root"
                )
        if not trusted_host._verify_ssh_signature(
            signed_bytes,
            str(signature.get("signature", "")).encode("ascii", errors="ignore"),
            public_key=str(profile["public_key"]),
            identity=S2E_RECEIPT_SIGNER_IDENTITY,
            namespace=S2E_RECEIPT_SIGNATURE_NAMESPACE,
        ):
            errors.append("acceptance review SSHSIG verification failed")
    if _contains_github_secret_like_content(bundle):
        errors.append("acceptance review bundle contains secret-like content")
    return errors


def issue_s2e_launch_receipt(
    candidate: Any,
    *,
    acceptance_review_bundle: Any,
    repo_root: Path,
    now: str | datetime,
    governed_capture_record: Any = None,
    external_append_intent: Any = None,
    external_append_result: Any = None,
    external_readback_ack: Any = None,
    predecessor_receipt: Any = None,
) -> dict[str, Any]:
    """Issue one ready receipt only after the complete review path verifies."""

    if isinstance(candidate, dict) and candidate.get("schema_version") == (
        "s2e_launch_genesis_receipt_v1"
    ):
        errors = validate_s2e_launch_genesis_receipt(candidate, repo_root=repo_root)
        ready_status = "W0_GENESIS_READY"
    elif isinstance(candidate, dict) and candidate.get("schema_version") == (
        "s2e_launch_wave_receipt_v1"
    ):
        if predecessor_receipt is None:
            errors = ["wave receipt issuance requires its exact predecessor receipt"]
        else:
            errors = validate_s2e_launch_transition(
                candidate,
                predecessor_receipt=predecessor_receipt,
                repo_root=repo_root,
            )
        ready_status = "TASK_BRANCH_CHECKPOINT_READY"
    else:
        errors = ["launch receipt candidate schema is unsupported"]
        ready_status = None
    errors.extend(
        validate_s2e_launch_acceptance_review_bundle(
            acceptance_review_bundle,
            candidate=candidate,
            governed_capture_record=governed_capture_record,
            external_append_intent=external_append_intent,
            external_append_result=external_append_result,
            external_readback_ack=external_readback_ack,
            repo_root=repo_root,
            now=now,
        )
    )
    issued_receipt = None
    if not errors and ready_status is not None:
        issued_receipt = dict(candidate)
        issued_receipt["checkpoint_status"] = ready_status
        issued_receipt["acceptance_review_bundle_digest"] = (
            acceptance_review_bundle["bundle_digest"]
        )
        issued_receipt["payload_digest"] = launch_payload_digest(issued_receipt)
        if ready_status == "W0_GENESIS_READY":
            errors.extend(
                validate_s2e_launch_genesis_receipt(
                    issued_receipt, repo_root=repo_root
                )
            )
        else:
            errors.extend(
                validate_s2e_launch_transition(
                    issued_receipt,
                    predecessor_receipt=predecessor_receipt,
                    repo_root=repo_root,
                )
            )
        if errors:
            issued_receipt = None
    result = {
        "schema_version": "launch_receipt_issuance_result_v1",
        "status": "ISSUED" if issued_receipt is not None else (
            "EXTERNAL_VERIFICATION_PENDING"
        ),
        "candidate_payload_digest": (
            candidate.get("payload_digest") if isinstance(candidate, dict) else None
        ),
        "acceptance_review_bundle_digest": (
            acceptance_review_bundle.get("bundle_digest")
            if isinstance(acceptance_review_bundle, dict)
            else None
        ),
        "issued_receipt": issued_receipt,
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
        "acceptance_review_bundle_digest": None,
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
        "acceptance_review_bundle_digest": None,
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
