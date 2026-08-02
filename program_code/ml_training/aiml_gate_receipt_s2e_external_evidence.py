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
DURABILITY_ANCHOR_SCHEMA = "s2e_durability_anchor_attestation_v1"
PREDECESSOR_REGISTRY_SCHEMA = "s2e_predecessor_registry_attestation_v1"
DURABILITY_ANCHOR_IDENTITY = (
    "aiml-s2e-durability-anchor-attestor-v1"
)
DURABILITY_ANCHOR_NAMESPACE = (
    "arcane-equilibrium-aiml-s2e-durability-anchor"
)
PREDECESSOR_REGISTRY_IDENTITY = (
    "aiml-s2e-predecessor-registry-attestor-v1"
)
PREDECESSOR_REGISTRY_NAMESPACE = (
    "arcane-equilibrium-aiml-s2e-predecessor-registry"
)
# 這組 scheme 擋的是 fixture／stub 證據冒充真實 attestation,與「證據在不在本機」
# 無關;Tier 1 的 anchor 本來就是 host-local capability,仍必須擋掉測試替身。
LOCAL_EVIDENCE_LOCATOR_SCHEMES = frozenset({
    "fixture", "memory", "local", "test",
})
DURABILITY_ANCHOR_LOCATOR_PREFIX = "host:append-only-durability-anchor:"
OFFHOST_REPLICA_LOCATOR_PREFIX = "replica:offhost-append-only:"
PREDECESSOR_REGISTRY_LOCATOR_PREFIX = "registry:host-append-only:"
DURABILITY_ANCHOR_TRUST_ROOT_PATH = Path(
    "/etc/arcane-equilibrium/aiml/"
    "s2e-durability-anchor-trust-root-v1.json"
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


def _load_durability_anchor_trust_root(
) -> tuple[dict[str, Any] | None, list[str]]:
    return _read_trust_root(
        DURABILITY_ANCHOR_TRUST_ROOT_PATH,
        schema_version="s2e_durability_anchor_trust_root_v1",
        signer_identity=DURABILITY_ANCHOR_IDENTITY,
        signature_namespace=DURABILITY_ANCHOR_NAMESPACE,
        attestor_class="HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1",
        label="S2E durability anchor",
    )


def _load_predecessor_registry_trust_root(
) -> tuple[dict[str, Any] | None, list[str]]:
    return _read_trust_root(
        PREDECESSOR_REGISTRY_TRUST_ROOT_PATH,
        schema_version="s2e_predecessor_registry_trust_root_v1",
        signer_identity=PREDECESSOR_REGISTRY_IDENTITY,
        signature_namespace=PREDECESSOR_REGISTRY_NAMESPACE,
        attestor_class="HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
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


def durability_anchor_signed_bytes(attestation: dict[str, Any]) -> bytes:
    return _signed_bytes(attestation)


def predecessor_registry_signed_bytes(attestation: dict[str, Any]) -> bytes:
    return _signed_bytes(attestation)


def durability_anchor_attestation_digest(
    attestation: dict[str, Any],
) -> str:
    return canonical_digest({
        key: value for key, value in attestation.items()
        if key != "attestation_digest"
    })


def durability_anchor_digest_or_none(value: Any) -> str | None:
    return value.get("attestation_digest") if isinstance(value, dict) else None


def durability_anchor_entry_digest(attestation: dict[str, Any]) -> str:
    """單筆 append-only 條目的規範摘要,與 registry 條目採同一形制。"""

    fields = (
        "anchor_class",
        "anchor_locator",
        "launch_id",
        "terminal_payload_digest",
        "anchor_generation",
        "previous_anchor_head_digest",
    )
    return canonical_digest({
        "schema_version": "s2e_durability_anchor_entry_v1",
        **{field: attestation.get(field) for field in fields},
    })


def durability_anchor_head_digest(attestation: dict[str, Any]) -> str:
    """append-only head 的規範摘要;off-host 副本必須回讀到同一個值。"""

    return canonical_digest({
        "schema_version": "s2e_durability_anchor_head_v1",
        "anchor_class": attestation.get("anchor_class"),
        "anchor_locator": attestation.get("anchor_locator"),
        "anchor_generation": attestation.get("anchor_generation"),
        "previous_anchor_head_digest": attestation.get(
            "previous_anchor_head_digest"
        ),
        "anchor_entry_digest": attestation.get("anchor_entry_digest"),
    })


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


def validate_s2e_durability_anchor_attestation(
    attestation: Any,
    *,
    terminal_payload_digest: str,
    now: str | datetime,
) -> list[str]:
    """Require one trusted-host SSHSIG binding append-only head and off-host readback.

    這是 §LW1 spec anchor 選言的第二支:單一 trusted-host 簽章同時綁獨立 key
    identity、append-only monotonic head、trusted freshness window 與
    latest-generation immutable readback。caller 不能自選 anchor 或 replica 後端。
    """

    schema = _load_schema(DURABILITY_ANCHOR_SCHEMA)
    errors = schema_subset_errors(attestation, schema, root_schema=schema)
    if not isinstance(attestation, dict):
        return errors
    errors.extend(_external_locator_errors(
        attestation.get("anchor_locator"),
        label="durability anchor",
        required_prefix=DURABILITY_ANCHOR_LOCATOR_PREFIX,
        admitted_class="host append-only durability anchor class",
    ))
    errors.extend(_external_locator_errors(
        attestation.get("offhost_replica_locator"),
        label="durability anchor replica",
        required_prefix=OFFHOST_REPLICA_LOCATOR_PREFIX,
        admitted_class="off-host append-only replica class",
    ))
    if errors:
        return sorted(set(errors))
    if attestation.get("launch_id") != LAUNCH_ID:
        errors.append("durability anchor launch_id binding differs")
    if attestation.get("terminal_payload_digest") != terminal_payload_digest:
        errors.append("durability anchor terminal_payload_digest binding differs")
    # generation 與 previous head 必須連續:第一代不得帶前手,後續代不得缺前手。
    generation = attestation.get("anchor_generation")
    previous = attestation.get("previous_anchor_head_digest")
    if (generation == 1 and previous is not None) or (
        isinstance(generation, int) and generation > 1 and previous is None
    ):
        errors.append("durability anchor generation/head continuity is invalid")
    if attestation.get("anchor_entry_digest") != (
        durability_anchor_entry_digest(attestation)
    ):
        errors.append("durability anchor entry digest is invalid")
    if attestation.get("anchor_head_digest") != (
        durability_anchor_head_digest(attestation)
    ):
        errors.append("durability anchor head digest is invalid")
    readback = attestation.get("offhost_replica_readback")
    readback = readback if isinstance(readback, dict) else {}
    if not (
        readback.get("ack") is True
        and readback.get("entry_present") is True
        and readback.get("latest_generation_matches") is True
    ):
        errors.append("durability anchor off-host readback is not proven")
    # 副本必須回讀到與本機 anchor 完全相同的 head,否則不成立 latest-generation。
    if readback.get("replica_head_digest") != attestation.get("anchor_head_digest"):
        errors.append("durability anchor replica head does not match anchor head")
    errors.extend(_freshness_errors(attestation, now=now, label="durability anchor"))
    try:
        if _timestamp(attestation["observed_at"]) < _timestamp(
            readback["observed_at"]
        ):
            errors.append("durability anchor predates off-host readback")
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"durability anchor binding timestamp is invalid: {error}")
    signature_errors, anchor_profile = _signature_errors(
        attestation,
        profile_loader=_load_durability_anchor_trust_root,
        identity=DURABILITY_ANCHOR_IDENTITY,
        namespace=DURABILITY_ANCHOR_NAMESPACE,
        label="durability anchor",
    )
    errors.extend(signature_errors)
    receipt_profile, receipt_errors = _load_s2e_receipt_signer_profile()
    errors.extend(receipt_errors)
    errors.extend(_distinct_fingerprint_errors(
        subject=anchor_profile,
        peers=[("S2E receipt signer", receipt_profile)],
        label="durability anchor",
    ))
    if attestation.get("attestation_digest") != (
        durability_anchor_attestation_digest(attestation)
    ):
        errors.append("durability anchor attestation digest is invalid")
    if _contains_github_secret_like_content(attestation):
        errors.append("durability anchor attestation contains secret-like content")
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
    anchor_profile, anchor_errors = _load_durability_anchor_trust_root()
    errors.extend(receipt_errors)
    errors.extend(anchor_errors)
    errors.extend(_distinct_fingerprint_errors(
        subject=registry_profile,
        peers=[
            ("S2E receipt signer", receipt_profile),
            ("durability anchor", anchor_profile),
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
