"""Independent external evidence gates for formal S2E launch receipts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import agent_governance_aiml_trusted_host as trusted_host
from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _contains_github_secret_like_content,
    _load_schema,
    canonical_digest,
)


LAUNCH_ID = "S2E-LW1-LW5"
EXTERNAL_WORM_SCHEMA = "s2e_external_worm_provider_attestation_v1"
PREDECESSOR_REGISTRY_SCHEMA = "s2e_predecessor_registry_attestation_v1"
EXTERNAL_WORM_PROVIDER_IDENTITY = (
    "aiml-s2e-external-worm-provider-attestor-v1"
)
EXTERNAL_WORM_PROVIDER_NAMESPACE = (
    "arcane-equilibrium-aiml-s2e-external-worm-provider"
)
PREDECESSOR_REGISTRY_IDENTITY = (
    "aiml-s2e-predecessor-registry-attestor-v1"
)
PREDECESSOR_REGISTRY_NAMESPACE = (
    "arcane-equilibrium-aiml-s2e-predecessor-registry"
)
LOCAL_EVIDENCE_LOCATOR_SCHEMES = frozenset({
    "fixture", "memory", "local", "test",
})
EXTERNAL_WORM_PROVIDER_LOCATOR_PREFIX = "aws:s3-object-lock-attestor:"
PREDECESSOR_REGISTRY_LOCATOR_PREFIX = "registry:external-append-only:"
EXTERNAL_WORM_PROVIDER_TRUST_ROOT_PATH = Path(
    "/etc/arcane-equilibrium/aiml/"
    "s2e-external-worm-provider-trust-root-v1.json"
)
PREDECESSOR_REGISTRY_TRUST_ROOT_PATH = Path(
    "/etc/arcane-equilibrium/aiml/"
    "s2e-predecessor-registry-trust-root-v1.json"
)
TRUST_ROOT_OWNER_UID = 0
TRUST_ROOT_MODE = 0o644
MAX_TRUST_ROOT_BYTES = 16 * 1024
MAX_ATTESTATION_TTL = timedelta(minutes=10)
_TRUST_ROOT_FIELDS = {
    "schema_version",
    "signer_identity",
    "signature_namespace",
    "algorithm",
    "key_generation",
    "anchor",
    "public_key",
    "key_fingerprint",
    "attestor_class",
}


def _raw_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _strict_json_object(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs)


def _timestamp(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _read_trust_root(
    path: Path,
    *,
    schema_version: str,
    signer_identity: str,
    signature_namespace: str,
    attestor_class: str,
    label: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    repo_root = Path(__file__).resolve().parents[2]
    if not path.is_absolute() or path.is_relative_to(repo_root):
        return None, [f"{label} trust-root path is not fixed off-repository"]
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode):
            raise ValueError("trust-root path is a symlink")
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                errors.append(f"{label} trust root is not a regular file")
            if opened.st_nlink != 1:
                errors.append(f"{label} trust root link count is not one")
            if opened.st_uid != TRUST_ROOT_OWNER_UID:
                errors.append(f"{label} trust root owner is not trusted")
            if stat.S_IMODE(opened.st_mode) != TRUST_ROOT_MODE:
                errors.append(f"{label} trust root mode is not exact")
            raw = bytearray()
            while len(raw) <= MAX_TRUST_ROOT_BYTES:
                chunk = os.read(
                    descriptor,
                    min(4096, MAX_TRUST_ROOT_BYTES + 1 - len(raw)),
                )
                if not chunk:
                    break
                raw.extend(chunk)
        finally:
            os.close(descriptor)
        after = os.lstat(path)
        identity = (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_uid)
        if identity != (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
        ) or identity != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
        ):
            errors.append(f"{label} trust root changed while being read")
    except (OSError, ValueError) as error:
        return None, [f"{label} trust root is unavailable or untrusted: {error}"]
    if len(raw) > MAX_TRUST_ROOT_BYTES:
        return None, errors + [f"{label} trust root exceeds size limit"]
    try:
        profile = _strict_json_object(bytes(raw))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return None, errors + [f"{label} trust root JSON is invalid: {error}"]
    if not isinstance(profile, dict) or set(profile) != _TRUST_ROOT_FIELDS:
        return None, errors + [f"{label} trust root fields are not exact"]
    expected = {
        "schema_version": schema_version,
        "signer_identity": signer_identity,
        "signature_namespace": signature_namespace,
        "algorithm": "SSH-ED25519",
        "key_generation": "independent_off_repo_ed25519_v1",
        "anchor": "fixed_off_repo_public_trust_root_v1",
        "attestor_class": attestor_class,
    }
    for field, value in expected.items():
        if profile.get(field) != value:
            errors.append(f"{label} trust root {field} is invalid")
    try:
        fingerprint = trusted_host.ssh_public_key_fingerprint(
            str(profile.get("public_key"))
        )
    except ValueError as error:
        errors.append(f"{label} trust root public key is invalid: {error}")
    else:
        if profile.get("key_fingerprint") != fingerprint:
            errors.append(f"{label} trust root fingerprint does not match public key")
    if _contains_github_secret_like_content(profile):
        errors.append(f"{label} trust root contains secret-like content")
    return (profile if not errors else None), errors


def _load_external_worm_provider_trust_root(
) -> tuple[dict[str, Any] | None, list[str]]:
    return _read_trust_root(
        EXTERNAL_WORM_PROVIDER_TRUST_ROOT_PATH,
        schema_version="s2e_external_worm_provider_trust_root_v1",
        signer_identity=EXTERNAL_WORM_PROVIDER_IDENTITY,
        signature_namespace=EXTERNAL_WORM_PROVIDER_NAMESPACE,
        attestor_class="S3_OBJECT_LOCK_EXTERNAL_ATTESTOR_V1",
        label="S2E external WORM provider",
    )


def _load_predecessor_registry_trust_root(
) -> tuple[dict[str, Any] | None, list[str]]:
    return _read_trust_root(
        PREDECESSOR_REGISTRY_TRUST_ROOT_PATH,
        schema_version="s2e_predecessor_registry_trust_root_v1",
        signer_identity=PREDECESSOR_REGISTRY_IDENTITY,
        signature_namespace=PREDECESSOR_REGISTRY_NAMESPACE,
        attestor_class="EXTERNAL_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
        label="S2E predecessor registry",
    )


def _load_s2e_receipt_signer_profile(
) -> tuple[dict[str, Any] | None, list[str]]:
    from aiml_gate_receipt_s2e_launch import load_s2e_receipt_signer_trust_root

    return load_s2e_receipt_signer_trust_root()


def _signed_bytes(attestation: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            key: value
            for key, value in attestation.items()
            if key not in {"signed_core_digest", "signature", "attestation_digest"}
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def external_worm_provider_signed_bytes(attestation: dict[str, Any]) -> bytes:
    return _signed_bytes(attestation)


def predecessor_registry_signed_bytes(attestation: dict[str, Any]) -> bytes:
    return _signed_bytes(attestation)


def external_worm_provider_attestation_digest(
    attestation: dict[str, Any],
) -> str:
    return canonical_digest({
        key: value for key, value in attestation.items()
        if key != "attestation_digest"
    })


def external_worm_provider_digest_or_none(value: Any) -> str | None:
    return value.get("attestation_digest") if isinstance(value, dict) else None


def predecessor_registry_attestation_digest(
    attestation: dict[str, Any],
) -> str:
    return canonical_digest({
        key: value for key, value in attestation.items()
        if key != "attestation_digest"
    })


def s2e_predecessor_registry_slot_id(predecessor_payload_digest: str) -> str:
    return canonical_digest({
        "schema_version": "s2e_launch_predecessor_single_use_slot_v1",
        "launch_id": LAUNCH_ID,
        "predecessor_payload_digest": predecessor_payload_digest,
    })


def predecessor_registry_entry_digest(attestation: dict[str, Any]) -> str:
    fields = (
        "registry_class",
        "registry_locator",
        "launch_id",
        "slot_id",
        "predecessor_payload_digest",
        "successor_candidate_payload_digest",
        "successor_wave",
        "successor_source_head",
        "acceptance_review_bundle_digest",
        "prior_consumption_ledger_digest",
        "expected_consumption_entry_digest",
        "expected_result_ledger_digest",
        "decision",
        "conflicting_grant_absent",
        "registry_generation",
        "previous_registry_head_digest",
    )
    return canonical_digest({
        "schema_version": "s2e_predecessor_registry_entry_v1",
        **{field: attestation.get(field) for field in fields},
    })


def predecessor_registry_head_digest(attestation: dict[str, Any]) -> str:
    return canonical_digest({
        "schema_version": "s2e_predecessor_registry_head_v1",
        "registry_class": attestation.get("registry_class"),
        "registry_locator": attestation.get("registry_locator"),
        "registry_generation": attestation.get("registry_generation"),
        "previous_registry_head_digest": attestation.get(
            "previous_registry_head_digest"
        ),
        "registry_entry_digest": attestation.get("registry_entry_digest"),
    })


def _freshness_errors(
    attestation: dict[str, Any], *, now: str | datetime, label: str
) -> list[str]:
    errors: list[str] = []
    try:
        observed = _timestamp(attestation.get("observed_at"))
        expires = _timestamp(attestation.get("expires_at"))
        evaluated = _timestamp(now)
        if not observed < expires:
            errors.append(f"{label} freshness window is invalid")
        if expires - observed > MAX_ATTESTATION_TTL:
            errors.append(f"{label} freshness window exceeds ten minutes")
        if not observed <= evaluated < expires:
            errors.append(f"{label} is stale or not yet valid")
    except (TypeError, ValueError) as error:
        errors.append(f"{label} timestamp is invalid: {error}")
    return errors


def _signature_errors(
    attestation: dict[str, Any],
    *,
    profile_loader: Callable[[], tuple[dict[str, Any] | None, list[str]]],
    identity: str,
    namespace: str,
    label: str,
) -> tuple[list[str], dict[str, Any] | None]:
    profile, errors = profile_loader()
    if profile is None:
        return list(errors), None
    signer = attestation.get("signer", {})
    for field, profile_field in (
        ("identity", "signer_identity"),
        ("namespace", "signature_namespace"),
        ("key_generation", "key_generation"),
        ("anchor", "anchor"),
        ("key_fingerprint", "key_fingerprint"),
    ):
        if signer.get(field) != profile.get(profile_field):
            errors.append(f"{label} signer {field} differs from fixed trust root")
    signed = _signed_bytes(attestation)
    signed_digest = _raw_digest(signed)
    if attestation.get("signed_core_digest") != signed_digest:
        errors.append(f"{label} signed core digest is invalid")
    signature = attestation.get("signature", {})
    if signature.get("signed_digest") != signed_digest:
        errors.append(f"{label} signature binding differs")
    if not trusted_host._verify_ssh_signature(
        signed,
        str(signature.get("signature", "")).encode("ascii", errors="ignore"),
        public_key=str(profile["public_key"]),
        identity=identity,
        namespace=namespace,
    ):
        errors.append(f"{label} SSHSIG verification failed")
    return errors, profile


def _distinct_fingerprint_errors(
    *,
    subject: dict[str, Any] | None,
    peers: list[tuple[str, dict[str, Any] | None]],
    label: str,
) -> list[str]:
    if subject is None:
        return []
    fingerprint = subject.get("key_fingerprint")
    errors: list[str] = []
    for peer_label, peer in peers:
        if peer is None:
            errors.append(f"{label} cannot prove key separation from {peer_label}")
        elif fingerprint == peer.get("key_fingerprint"):
            errors.append(f"{label} key is not independent from {peer_label}")
    return errors


def _external_locator_errors(
    value: Any,
    *,
    label: str,
    required_prefix: str | None = None,
    admitted_class: str = "external registry class",
) -> list[str]:
    if not isinstance(value, str):
        return [f"{label} locator is not a string"]
    canonical = value.strip()
    if canonical != value:
        return [f"{label} locator is not canonical"]
    scheme, separator, _remainder = canonical.partition(":")
    if not separator or scheme.lower() in LOCAL_EVIDENCE_LOCATOR_SCHEMES:
        return [f"{label} locator is fixture or local evidence"]
    if required_prefix is not None and not canonical.startswith(required_prefix):
        return [f"{label} locator is outside the admitted {admitted_class}"]
    return []


def validate_s2e_external_worm_provider_attestation(
    attestation: Any,
    *,
    external_append_intent: Any,
    external_append_result: Any,
    external_readback_ack: Any,
    now: str | datetime,
) -> list[str]:
    """Require authenticated provider proof above caller-injected S3 results."""

    schema = _load_schema(EXTERNAL_WORM_SCHEMA)
    errors = schema_subset_errors(attestation, schema, root_schema=schema)
    if not isinstance(attestation, dict):
        return errors
    errors.extend(_external_locator_errors(
        attestation.get("provider_locator"),
        label="external WORM provider",
        required_prefix=EXTERNAL_WORM_PROVIDER_LOCATOR_PREFIX,
        admitted_class="external S3 Object Lock provider class",
    ))
    if errors:
        return sorted(set(errors))
    import agent_governance_terminal_receipt_external_sink as external_sink

    now_text = _timestamp(now).isoformat()
    errors.extend(
        "external WORM provider intent: " + error
        for error in external_sink.validate_external_worm_append_intent(
            external_append_intent, now=now_text
        )
    )
    errors.extend(
        "external WORM provider result: " + error
        for error in external_sink.validate_external_worm_append_result(
            external_append_result,
            intent=external_append_intent,
            now=now_text,
        )
    )
    errors.extend(
        "external WORM provider readback: " + error
        for error in external_sink.validate_external_worm_readback_ack(
            external_readback_ack,
            result=external_append_result,
            now=now_text,
        )
    )
    intent = external_append_intent if isinstance(external_append_intent, dict) else {}
    result = external_append_result if isinstance(external_append_result, dict) else {}
    readback = external_readback_ack if isinstance(external_readback_ack, dict) else {}
    destination = intent.get("destination_contract") or {}
    payload_binding = (intent.get("append_intent") or {}).get("payload_binding") or {}
    expected_destination = {
        field: destination.get(field)
        for field in (
            "endpoint",
            "region",
            "bucket",
            "credential_channel_id",
            "object_lock_mode",
            "retain_until",
        )
    }
    expected_object = {
        "record_locator": result.get("record_locator"),
        "object_version_id": result.get("object_version_id"),
        "checksum_sha256": result.get("checksum_sha256"),
        "append_status": result.get("append_status"),
        "readback_ack": readback.get("ack"),
        "immutability_proven": readback.get("immutability_proven"),
        "object_lock_enabled": readback.get("object_lock_enabled"),
    }
    for field, expected in (
        ("external_intent_digest", intent.get("external_intent_digest")),
        ("external_result_digest", result.get("result_digest")),
        ("external_readback_ack_digest", readback.get("ack_digest")),
        ("terminal_payload_digest", payload_binding.get("terminal_payload_digest")),
        ("destination", expected_destination),
        ("immutable_object", expected_object),
    ):
        if attestation.get(field) != expected:
            errors.append(f"external WORM provider {field} binding differs")
    if destination.get("object_lock_mode") != "COMPLIANCE":
        errors.append("external WORM provider requires COMPLIANCE Object Lock")
    if intent.get("compliance_operator_approved") is not True:
        errors.append("external WORM COMPLIANCE intent lacks operator approval")
    if result.get("append_status") not in external_sink.EXTERNAL_COMMITTED_STATUSES:
        errors.append("external WORM provider append is not committed")
    if result.get("external_verification_pending") is not False:
        errors.append("external WORM provider result remains verification-pending")
    if not (
        readback.get("ack") is True
        and readback.get("immutability_proven") is True
        and readback.get("object_lock_enabled") is True
    ):
        errors.append("external WORM provider immutable readback is not proven")
    errors.extend(_freshness_errors(attestation, now=now, label="external WORM provider"))
    try:
        if _timestamp(attestation["observed_at"]) < _timestamp(readback["observed_at"]):
            errors.append("external WORM provider predates immutable readback")
        if _timestamp(destination["retain_until"]) <= _timestamp(attestation["expires_at"]):
            errors.append("external WORM retention does not outlive attestation")
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"external WORM provider binding timestamp is invalid: {error}")
    signature_errors, provider_profile = _signature_errors(
        attestation,
        profile_loader=_load_external_worm_provider_trust_root,
        identity=EXTERNAL_WORM_PROVIDER_IDENTITY,
        namespace=EXTERNAL_WORM_PROVIDER_NAMESPACE,
        label="external WORM provider",
    )
    errors.extend(signature_errors)
    receipt_profile, receipt_errors = _load_s2e_receipt_signer_profile()
    errors.extend(receipt_errors)
    errors.extend(_distinct_fingerprint_errors(
        subject=provider_profile,
        peers=[("S2E receipt signer", receipt_profile)],
        label="external WORM provider",
    ))
    if attestation.get("attestation_digest") != (
        external_worm_provider_attestation_digest(attestation)
    ):
        errors.append("external WORM provider attestation digest is invalid")
    if _contains_github_secret_like_content(attestation):
        errors.append("external WORM provider attestation contains secret-like content")
    return sorted(set(errors))


def validate_s2e_predecessor_registry_attestation(
    attestation: Any,
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    acceptance_review_bundle_digest: str,
    prior_consumption_ledger_digest: str,
    expected_consumption_entry: dict[str, Any],
    expected_result_ledger_digest: str,
    now: str | datetime,
) -> list[str]:
    """Validate one independent, append-only predecessor single-use grant."""

    schema = _load_schema(PREDECESSOR_REGISTRY_SCHEMA)
    errors = schema_subset_errors(attestation, schema, root_schema=schema)
    if errors or not isinstance(attestation, dict):
        return errors
    predecessor_digest = str(predecessor_receipt.get("payload_digest", ""))
    expected = {
        "launch_id": LAUNCH_ID,
        "slot_id": s2e_predecessor_registry_slot_id(predecessor_digest),
        "predecessor_payload_digest": predecessor_digest,
        "successor_candidate_payload_digest": candidate.get("payload_digest"),
        "successor_wave": candidate.get("wave"),
        "successor_source_head": candidate.get("source_head"),
        "acceptance_review_bundle_digest": acceptance_review_bundle_digest,
        "prior_consumption_ledger_digest": prior_consumption_ledger_digest,
        "expected_consumption_entry_digest": expected_consumption_entry.get(
            "entry_digest"
        ),
        "expected_result_ledger_digest": expected_result_ledger_digest,
        "decision": "GRANTED_ONCE",
        "conflicting_grant_absent": True,
    }
    for field, value in expected.items():
        if attestation.get(field) != value:
            errors.append(f"predecessor registry {field} binding differs")
    errors.extend(_external_locator_errors(
        attestation.get("registry_locator"),
        label="predecessor registry",
        required_prefix=PREDECESSOR_REGISTRY_LOCATOR_PREFIX,
    ))
    generation = attestation.get("registry_generation")
    previous = attestation.get("previous_registry_head_digest")
    if (generation == 1 and previous is not None) or (
        isinstance(generation, int) and generation > 1 and previous is None
    ):
        errors.append("predecessor registry generation/head continuity is invalid")
    if attestation.get("registry_entry_digest") != (
        predecessor_registry_entry_digest(attestation)
    ):
        errors.append("predecessor registry entry digest is invalid")
    if attestation.get("registry_head_digest") != (
        predecessor_registry_head_digest(attestation)
    ):
        errors.append("predecessor registry head digest is invalid")
    errors.extend(_freshness_errors(attestation, now=now, label="predecessor registry"))
    signature_errors, registry_profile = _signature_errors(
        attestation,
        profile_loader=_load_predecessor_registry_trust_root,
        identity=PREDECESSOR_REGISTRY_IDENTITY,
        namespace=PREDECESSOR_REGISTRY_NAMESPACE,
        label="predecessor registry",
    )
    errors.extend(signature_errors)
    receipt_profile, receipt_errors = _load_s2e_receipt_signer_profile()
    provider_profile, provider_errors = _load_external_worm_provider_trust_root()
    errors.extend(receipt_errors)
    errors.extend(provider_errors)
    errors.extend(_distinct_fingerprint_errors(
        subject=registry_profile,
        peers=[
            ("S2E receipt signer", receipt_profile),
            ("external WORM provider", provider_profile),
        ],
        label="predecessor registry",
    ))
    if attestation.get("attestation_digest") != (
        predecessor_registry_attestation_digest(attestation)
    ):
        errors.append("predecessor registry attestation digest is invalid")
    if _contains_github_secret_like_content(attestation):
        errors.append("predecessor registry attestation contains secret-like content")
    return sorted(set(errors))
