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
from aiml_gate_receipt_s2e_consumption import (
    build_s2e_launch_consumption_bootstrap_authority_core,
    build_s2e_predecessor_registry_request,
    consume_s2e_launch_predecessor,
    s2e_launch_consumption_bootstrap_authority_digest,
    s2e_launch_consumption_bootstrap_signed_bytes,
    validate_s2e_launch_consumption_entry,
    validate_s2e_launch_consumption_entry_structure,
    validate_s2e_launch_consumption_bootstrap_authority,
)
from aiml_gate_receipt_s2e_external_evidence import (
    durability_anchor_digest_or_none, validate_s2e_durability_anchor_attestation,
)
from aiml_gate_receipt_s2e_review import (
    build_s2e_disposable_test_effect_chain,
    s2e_review_predicate_results,
    s2e_review_source_blob_manifest,
    s2e_review_test_argv,
    validate_s2e_disposable_test_effect_chain,
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
    "governed_pytest_provider_profile_id",
    "governed_pytest_provider_lock_sha256",
}
_S2E_RECEIPT_TRUST_ROOT_MAX_BYTES = 16 * 1024
S2E_WAVE_EXIT_IDS = {
    GENESIS_WAVE: "W0_GENESIS_READY",
    "S2E-LW1": "S2E_2B_2A_SECURITY_RECOVERY_READY",
    "S2E-LW2": "S2E_2B_2B_HOST_RUNNER_CHECKPOINT_READY",
    "S2E-LW3": "S2E_2B_3_ROW_DRIVERS_CHECKPOINT_READY",
    "S2E-LW4": "S2E_4_RUNTIME_CLOSURE_CHECKPOINT_READY",
    "S2E-LW5": "S2E_LW5_IMPLEMENTATION_READY",
}


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


def s2e_carrier_verification_argv(attestation: dict[str, Any]) -> list[str]:
    """One shell-free Git-blob replay command for an exact carrier."""

    return [
        "git",
        "cat-file",
        "blob",
        f"{attestation.get('carrier_head')}:{attestation.get('carrier_path')}",
    ]


def _without_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def s2e_acceptance_review_signed_bytes(bundle: dict[str, Any]) -> bytes:
    """Canonical review subject shared by SSHSIG and the external WORM payload."""

    return json.dumps(
        {
            key: value
            for key, value in bundle.items()
            if key not in {
                "signed_core_digest",
                "signature",
                "durability_anchor_binding",
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
    from agent_governance_pytest_provider import (
        GOVERNED_PYTEST_PROVIDER_PROFILE_ID,
    )

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
        "governed_pytest_provider_profile_id": (
            GOVERNED_PYTEST_PROVIDER_PROFILE_ID
        ),
    }
    for field, expected in expected_values.items():
        if profile.get(field) != expected:
            errors.append(f"S2E receipt trust root {field} is invalid")
    public_key = profile.get("public_key")
    fingerprint = profile.get("key_fingerprint")
    provider_lock_sha256 = profile.get(
        "governed_pytest_provider_lock_sha256"
    )
    if (
        not isinstance(provider_lock_sha256, str)
        or len(provider_lock_sha256) != 71
        or not provider_lock_sha256.startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in provider_lock_sha256[7:]
        )
    ):
        errors.append(
            "S2E receipt trust root governed pytest provider lock digest is invalid"
        )
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


def _trusted_issuance_now() -> datetime:
    """Capture receipt-issuance time from the host clock, never a caller."""

    return datetime.now(timezone.utc)


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
    if receipt.get("wave_exit_id") != S2E_WAVE_EXIT_IDS.get(
        str(receipt.get("wave"))
    ):
        errors.append("launch receipt wave_exit_id is not code-owned for its wave")
    effect_digests = receipt.get("disposable_effect_chain_digests")
    if checkpoint == "PENDING_REVIEW":
        if receipt.get("side_effect_class") != "SOURCE_ONLY":
            errors.append("pending launch candidate must remain source-only")
        if effect_digests != []:
            errors.append(
                "pending launch candidate cannot bind disposable effect chains"
            )
    else:
        if receipt.get("side_effect_class") != "DISPOSABLE_TEST":
            errors.append(
                "ready launch receipt must record its disposable test effect"
            )
        if not isinstance(effect_digests, list) or not effect_digests:
            errors.append(
                "ready launch receipt requires paired typed effect chain digests"
            )
    if receipt.get("schema_version") == "s2e_launch_wave_receipt_v1":
        consumption = receipt.get("predecessor_consumption")
        if checkpoint == "PENDING_REVIEW" and consumption is not None:
            errors.append("pending wave cannot consume its predecessor")
        if checkpoint != "PENDING_REVIEW" and not isinstance(
            consumption, dict
        ):
            errors.append(
                "ready wave must bind one durable predecessor consumption"
            )
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
    if receipt.get("checkpoint_status") != "PENDING_REVIEW":
        errors.extend(
            validate_s2e_launch_consumption_entry_structure(
                receipt.get("predecessor_consumption")
            )
        )
    return errors


def validate_s2e_launch_transition_payload(
    receipt: Any,
    *,
    predecessor_receipt: Any,
    repo_root: Path,
    consumed_predecessor_digests: set[str] | frozenset[str],
) -> list[str]:
    """Validate payload topology only; this function never grants Advance."""

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
    if receipt.get("checkpoint_status") != "PENDING_REVIEW":
        errors.extend(
            validate_s2e_launch_consumption_entry(
                receipt.get("predecessor_consumption"),
                candidate=_pending_candidate_from_issued(receipt),
                predecessor_receipt=predecessor_receipt,
                acceptance_review_bundle_digest=str(
                    receipt.get("acceptance_review_bundle_digest", "")
                ),
            )
        )
    return errors


_S2E_PREDECESSOR_AUTHORITY_FIELDS = {
    "schema_version",
    "predecessor_payload_digest",
    "launch_chain_before_predecessor",
    "acceptance_review_bundle",
    "review_governed_capture_record",
    "review_disposable_test_effect_chains",
    "review_durability_anchor_attestation",
    "carrier_attestation",
    "carrier_governed_capture_record",
    "carrier_durability_anchor_attestation",
    "authority_digest",
}


def s2e_predecessor_authority_digest(authority: dict[str, Any]) -> str:
    return canonical_digest(
        _without_digest(authority, "authority_digest")
    )


def _pending_candidate_from_issued(receipt: dict[str, Any]) -> dict[str, Any]:
    pending = dict(receipt)
    pending["checkpoint_status"] = "PENDING_REVIEW"
    pending["acceptance_review_bundle_digest"] = None
    pending["side_effect_class"] = "SOURCE_ONLY"
    pending["disposable_effect_chain_digests"] = []
    if pending.get("schema_version") == "s2e_launch_wave_receipt_v1":
        pending["predecessor_consumption"] = None
    pending["payload_digest"] = launch_payload_digest(pending)
    return pending


def _ready_status_for(receipt: dict[str, Any]) -> str | None:
    if receipt.get("schema_version") == "s2e_launch_genesis_receipt_v1":
        return "W0_GENESIS_READY"
    if receipt.get("schema_version") == "s2e_launch_wave_receipt_v1":
        return "TASK_BRANCH_CHECKPOINT_READY"
    return None


def _launch_chain_errors(
    chain: Any,
    *,
    predecessor_receipt: dict[str, Any],
    repo_root: Path,
) -> list[str]:
    if not isinstance(chain, list):
        return ["predecessor authority launch chain must be a list"]
    expected_predecessor_wave = str(predecessor_receipt.get("wave", ""))
    if expected_predecessor_wave == GENESIS_WAVE:
        expected_waves: list[str] = []
    elif expected_predecessor_wave in LAUNCH_WAVES:
        expected_waves = [
            GENESIS_WAVE,
            *LAUNCH_WAVES[: LAUNCH_WAVES.index(expected_predecessor_wave)],
        ]
    else:
        return ["predecessor authority names an unknown predecessor wave"]
    errors: list[str] = []
    actual_waves = [
        item.get("wave") if isinstance(item, dict) else None for item in chain
    ]
    if actual_waves != expected_waves:
        errors.append("predecessor authority launch chain wave order differs")
    payload_digests = [
        item.get("payload_digest") if isinstance(item, dict) else None
        for item in chain
    ]
    if len(payload_digests) != len(set(payload_digests)):
        errors.append("predecessor authority launch chain contains duplicate payloads")
    prior: dict[str, Any] | None = None
    consumed: set[str] = set()
    for index, item in enumerate(chain):
        if not isinstance(item, dict):
            errors.append(f"predecessor authority chain item {index} is not an object")
            continue
        expected_ready = _ready_status_for(item)
        if item.get("checkpoint_status") != expected_ready:
            errors.append(f"predecessor authority chain item {index} is not READY")
        if expected_ready == "W0_GENESIS_READY":
            errors.extend(
                f"predecessor authority chain item {index}: {error}"
                for error in validate_s2e_launch_genesis_receipt(
                    item, repo_root=repo_root
                )
            )
        elif prior is not None:
            errors.extend(
                f"predecessor authority chain item {index}: {error}"
                for error in validate_s2e_launch_transition_payload(
                    item,
                    predecessor_receipt=prior,
                    repo_root=repo_root,
                    consumed_predecessor_digests=frozenset(consumed),
                )
            )
            consumed.add(str(prior.get("payload_digest")))
        prior = item
    if chain:
        last = chain[-1]
        if isinstance(last, dict):
            if predecessor_receipt.get("predecessor") != last.get("payload_digest"):
                errors.append(
                    "predecessor authority immediate receipt does not extend chain tail"
                )
    elif predecessor_receipt.get("wave") != GENESIS_WAVE:
        errors.append("non-genesis predecessor authority chain is empty")
    return errors


def validate_s2e_launch_predecessor_authority(
    authority: Any,
    *,
    predecessor_receipt: Any,
    repo_root: Path,
    now: str | datetime,
) -> list[str]:
    """Recompute the immediate predecessor's signed review and carrier proof."""

    if not isinstance(authority, dict):
        return ["S2E predecessor authority must be an object"]
    errors: list[str] = []
    if set(authority) != _S2E_PREDECESSOR_AUTHORITY_FIELDS:
        errors.append("S2E predecessor authority fields differ from closed contract")
    if authority.get("schema_version") != "s2e_launch_predecessor_authority_v1":
        errors.append("S2E predecessor authority schema_version is invalid")
    if not isinstance(predecessor_receipt, dict):
        return errors + ["S2E predecessor authority requires exact predecessor receipt"]
    if authority.get("predecessor_payload_digest") != predecessor_receipt.get(
        "payload_digest"
    ):
        errors.append("S2E predecessor authority payload binding differs")
    if authority.get("authority_digest") != s2e_predecessor_authority_digest(
        authority
    ):
        errors.append("S2E predecessor authority digest is invalid")
    expected_ready = _ready_status_for(predecessor_receipt)
    if predecessor_receipt.get("checkpoint_status") != expected_ready:
        errors.append("S2E predecessor receipt is not an issued READY checkpoint")
    chain = authority.get("launch_chain_before_predecessor")
    errors.extend(
        _launch_chain_errors(
            chain,
            predecessor_receipt=predecessor_receipt,
            repo_root=repo_root,
        )
    )
    pending_candidate = _pending_candidate_from_issued(predecessor_receipt)
    review_bundle = authority.get("acceptance_review_bundle")
    if (
        not isinstance(review_bundle, dict)
        or review_bundle.get("bundle_digest")
        != predecessor_receipt.get("acceptance_review_bundle_digest")
    ):
        errors.append("S2E predecessor READY receipt review binding differs")
    errors.extend(
        f"S2E predecessor review: {error}"
        for error in validate_s2e_launch_acceptance_review_bundle(
            review_bundle,
            candidate=pending_candidate,
            governed_capture_record=authority.get(
                "review_governed_capture_record"
            ),
            disposable_test_effect_chains=authority.get(
                "review_disposable_test_effect_chains"
            ),
            predecessor_chain=chain,
            durability_anchor_attestation=authority.get(
                "review_durability_anchor_attestation"
            ),
            repo_root=repo_root,
            now=now,
            require_current_generation=False,
        )
    )
    carrier_result = verify_receipt_carrier_attestation(
        authority.get("carrier_attestation"),
        payload_receipt=predecessor_receipt,
        repo_root=repo_root,
        now=now,
        governed_capture_record=authority.get(
            "carrier_governed_capture_record"
        ),
        durability_anchor_attestation=authority.get(
            "carrier_durability_anchor_attestation"
        ),
    )
    if carrier_result.get("status") != "VERIFIED":
        errors.extend(
            f"S2E predecessor carrier: {error}"
            for error in carrier_result.get("errors", [])
        )
        if not carrier_result.get("errors"):
            errors.append("S2E predecessor carrier is not VERIFIED")
    return sorted(set(errors))


def build_s2e_launch_predecessor_authority(
    *,
    predecessor_receipt: dict[str, Any],
    launch_chain_before_predecessor: list[dict[str, Any]],
    acceptance_review_bundle: dict[str, Any],
    review_governed_capture_record: dict[str, Any],
    review_disposable_test_effect_chains: list[dict[str, Any]],
    review_durability_anchor_attestation: dict[str, Any],
    carrier_attestation: dict[str, Any],
    carrier_governed_capture_record: dict[str, Any],
    carrier_durability_anchor_attestation: dict[str, Any],
    repo_root: Path,
    now: str | datetime,
) -> dict[str, Any]:
    authority = {
        "schema_version": "s2e_launch_predecessor_authority_v1",
        "predecessor_payload_digest": predecessor_receipt.get("payload_digest"),
        "launch_chain_before_predecessor": launch_chain_before_predecessor,
        "acceptance_review_bundle": acceptance_review_bundle,
        "review_governed_capture_record": review_governed_capture_record,
        "review_disposable_test_effect_chains": (
            review_disposable_test_effect_chains
        ),
        "review_durability_anchor_attestation": (
            review_durability_anchor_attestation
        ),
        "carrier_attestation": carrier_attestation,
        "carrier_governed_capture_record": carrier_governed_capture_record,
        "carrier_durability_anchor_attestation": (
            carrier_durability_anchor_attestation
        ),
    }
    authority["authority_digest"] = s2e_predecessor_authority_digest(authority)
    errors = validate_s2e_launch_predecessor_authority(
        authority,
        predecessor_receipt=predecessor_receipt,
        repo_root=repo_root,
        now=now,
    )
    if errors:
        raise ValueError("; ".join(errors))
    return authority


def validate_s2e_launch_transition(
    receipt: Any,
    *,
    predecessor_receipt: Any,
    predecessor_authority: Any,
    repo_root: Path,
    now: str | datetime,
    consumed_predecessor_digests: set[str] | frozenset[str],
) -> list[str]:
    """Authority-bearing Advance gate; structural validation alone never enters."""

    errors = validate_s2e_launch_transition_payload(
        receipt,
        predecessor_receipt=predecessor_receipt,
        repo_root=repo_root,
        consumed_predecessor_digests=consumed_predecessor_digests,
    )
    errors.extend(
        validate_s2e_launch_predecessor_authority(
            predecessor_authority,
            predecessor_receipt=predecessor_receipt,
            repo_root=repo_root,
            now=now,
        )
    )
    if isinstance(predecessor_authority, dict):
        chain = predecessor_authority.get("launch_chain_before_predecessor")
        expected_consumed = {
            str(item.get("payload_digest"))
            for item in chain
            if isinstance(chain, list) and isinstance(item, dict)
        } if isinstance(chain, list) else set()
        if set(consumed_predecessor_digests) != expected_consumed:
            errors.append(
                "transition consumed-predecessor set differs from authenticated chain"
            )
    return sorted(set(errors))


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
    durability_anchor_attestation: Any,
) -> dict[str, Any]:
    """Verify a carrier through fixed-root SSHSIG, capture, and durability anchor.

    durability 側走 carrier schema 早已宣告的 `TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1`
    adapter:單一 trusted-host 簽章綁 append-only head 與 off-host latest-generation
    回讀,不依賴任何外部付費 WORM 服務。
    """

    from agent_governance_command_capture_v2 import (
        validate_governed_command_capture,
    )
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
        reexecute=(
            isinstance(carrier_head, str)
            and _commit(repo_root, "HEAD") == carrier_head
        ),
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
        expected_argv = (
            s2e_carrier_verification_argv(attestation)
            if isinstance(attestation, dict)
            else []
        )
        if governed_capture_record.get("argv") != expected_argv:
            errors.append("carrier governed capture argv is not code-owned")
        if governed_capture_record.get("stdout", {}).get("digest") != (
            attestation.get("carrier_raw_digest")
            if isinstance(attestation, dict)
            else None
        ):
            errors.append("carrier governed capture did not replay exact carrier bytes")
        signer_role = (
            attestation.get("signer", {}).get("role")
            if isinstance(attestation, dict)
            else None
        )
        if signer_role == governed_capture_record.get("role_id"):
            errors.append("carrier signer role must differ from capture role")
        if governed_capture_record.get("result") != "PASS":
            errors.append("governed command capture did not PASS")
    if isinstance(attestation, dict) and isinstance(payload_receipt, dict):
        expected_worm_digest = terminal_sink.terminal_payload_digest(
            s2e_carrier_worm_payload(attestation, payload_receipt=payload_receipt)
        )
    else:
        expected_worm_digest = None
    errors.extend(
        f"durability anchor: {error}"
        for error in validate_s2e_durability_anchor_attestation(
            durability_anchor_attestation,
            terminal_payload_digest=expected_worm_digest,
            now=now,
        )
    )
    anchor_digest = durability_anchor_digest_or_none(durability_anchor_attestation)
    anchor = (
        durability_anchor_attestation
        if isinstance(durability_anchor_attestation, dict)
        else {}
    )
    if isinstance(attestation, dict) and isinstance(payload_receipt, dict):
        immutable = attestation.get("immutable_readback", {})
        if immutable.get("adapter") != "TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1":
            errors.append(
                "carrier immutable readback adapter is not trusted-host append-only"
            )
        generation = anchor.get("anchor_generation")
        for field, actual in (
            ("object_id", anchor.get("anchor_locator")),
            ("version_id", str(generation) if generation is not None else None),
            ("readback_digest", anchor.get("anchor_head_digest")),
            ("provider_attestation_digest", anchor_digest),
        ):
            if immutable.get(field) != actual:
                errors.append(
                    f"carrier immutable readback {field} is not bound to durability anchor"
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
        "durability_anchor_head_digest": anchor.get("anchor_head_digest"),
        "durability_anchor_generation": anchor.get("anchor_generation"),
        "durability_anchor_attestation_digest": anchor_digest,
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
    disposable_test_effect_chains: Any,
    predecessor_chain: Any,
    durability_anchor_attestation: Any,
    repo_root: Path,
    now: str | datetime,
    require_current_generation: bool = True,
) -> list[str]:
    """Validate one signed, capture-bound, durably anchored review bundle."""

    from agent_governance_command_capture_v2 import (
        validate_governed_command_capture,
    )
    import agent_governance_aiml_trusted_host as trusted_host
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
    if require_current_generation:
        try:
            _require_clean(repo_root)
            if (
                _commit(repo_root, "HEAD") != reviewed_head
                or _tree(repo_root, "HEAD") != reviewed_tree
            ):
                errors.append(
                    "acceptance review candidate is not the clean current HEAD"
                )
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            errors.append(
                f"acceptance review current generation is unavailable: {error}"
            )
    if candidate.get("checkpoint_status") != "PENDING_REVIEW":
        errors.append("acceptance review bundle requires a pending candidate")
    for field, expected in (
        ("candidate_payload_digest", candidate.get("payload_digest")),
        ("launch_id", candidate.get("launch_id")),
        ("wave", candidate.get("wave")),
        ("wave_exit_id", candidate.get("wave_exit_id")),
        ("reviewed_source_head", reviewed_head),
        ("reviewed_source_tree", reviewed_tree),
        (
            "generation_task_contract_digest",
            candidate.get("generation_task_contract_digest"),
        ),
    ):
        if bundle.get(field) != expected:
            errors.append(f"acceptance review bundle {field} binding differs")
    try:
        expected_blob_manifest = s2e_review_source_blob_manifest(
            candidate, repo_root=repo_root
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        expected_blob_manifest = []
        errors.append(f"acceptance review Git blob replay failed: {error}")
    if bundle.get("source_blob_manifest") != expected_blob_manifest:
        errors.append("acceptance review source blob manifest differs from Git")
    if not isinstance(predecessor_chain, list):
        errors.append("acceptance review predecessor chain must be a list")
        predecessor_chain = []
    expected_consumed = [
        item.get("payload_digest")
        for item in predecessor_chain[:-1]
        if isinstance(item, dict)
    ]
    if bundle.get("consumed_predecessor_digests") != expected_consumed:
        errors.append(
            "acceptance review consumed predecessor digests differ from exact chain"
        )
    if candidate.get("wave") == GENESIS_WAVE:
        if predecessor_chain:
            errors.append("genesis acceptance review cannot carry a predecessor chain")
    else:
        if not predecessor_chain:
            errors.append("wave acceptance review requires the full predecessor chain")
        elif (
            not isinstance(predecessor_chain[-1], dict)
            or predecessor_chain[-1].get("payload_digest")
            != candidate.get("predecessor")
        ):
            errors.append(
                "acceptance review predecessor chain does not end at exact predecessor"
            )
    try:
        expected_predicate_results = s2e_review_predicate_results(
            candidate,
            source_blob_manifest=bundle.get("source_blob_manifest"),
            governed_capture_record=governed_capture_record,
            disposable_test_effect_chains=disposable_test_effect_chains,
            predecessor_chain=predecessor_chain,
            repo_root=repo_root,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:
        expected_predicate_results = []
        errors.append(f"acceptance review predicate oracle failed: {error}")
    if bundle.get("predicate_results") != expected_predicate_results:
        errors.append(
            "acceptance review predicate evidence is not the exact code-owned result"
        )
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
        expected_task_contract_digest=candidate.get(
            "generation_task_contract_digest"
        ),
        expected_source_head=reviewed_head,
        root=repo_root,
        reexecute=(
            isinstance(reviewed_head, str)
            and _commit(repo_root, "HEAD") == reviewed_head
        ),
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
        try:
            expected_argv = s2e_review_test_argv(
                candidate, repo_root=repo_root
            )
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            expected_argv = []
            errors.append(f"acceptance review test profile failed: {error}")
        if governed_capture_record.get("argv") != expected_argv:
            errors.append(
                "acceptance review governed capture argv is not code-owned"
            )
        if governed_capture_record.get("task_contract_digest") != candidate.get(
            "generation_task_contract_digest"
        ):
            errors.append(
                "acceptance review capture task generation differs from candidate"
            )
        if bundle.get("signer", {}).get("role") == governed_capture_record.get(
            "role_id"
        ):
            errors.append("acceptance review signer role must differ from reviewer role")
    if not isinstance(disposable_test_effect_chains, list):
        errors.append("acceptance review disposable test chains must be a list")
        disposable_test_effect_chains = []
    chain_digests = [
        chain.get("chain_digest")
        for chain in disposable_test_effect_chains
        if isinstance(chain, dict)
    ]
    if not chain_digests:
        errors.append("acceptance review requires typed disposable test evidence")
    if bundle.get("disposable_test_effect_chain_digests") != chain_digests:
        errors.append("acceptance review disposable test chain digests differ")
    for index, chain in enumerate(disposable_test_effect_chains):
        errors.extend(
            f"acceptance review disposable chain {index}: {error}"
            for error in validate_s2e_disposable_test_effect_chain(
                chain,
                candidate=candidate,
                governed_capture_record=governed_capture_record,
                repo_root=repo_root,
            )
        )
    expected_worm_digest = terminal_sink.terminal_payload_digest(
        s2e_acceptance_review_worm_payload(bundle)
    )
    errors.extend(
        f"acceptance review durability anchor: {error}"
        for error in validate_s2e_durability_anchor_attestation(
            durability_anchor_attestation,
            terminal_payload_digest=expected_worm_digest,
            now=now,
        )
    )
    anchor_digest = durability_anchor_digest_or_none(durability_anchor_attestation)
    anchor = (
        durability_anchor_attestation
        if isinstance(durability_anchor_attestation, dict)
        else {}
    )
    replica_readback = anchor.get("offhost_replica_readback")
    replica_readback = replica_readback if isinstance(replica_readback, dict) else {}
    anchor_binding = bundle.get("durability_anchor_binding", {})
    for field, actual in (
        ("anchor_locator", anchor.get("anchor_locator")),
        ("anchor_generation", anchor.get("anchor_generation")),
        ("anchor_head_digest", anchor.get("anchor_head_digest")),
        ("replica_head_digest", replica_readback.get("replica_head_digest")),
        ("anchor_attestation_digest", anchor_digest),
    ):
        if anchor_binding.get(field) != actual:
            errors.append(
                f"acceptance review durability anchor {field} binding differs"
            )
    profile, trust_errors = load_s2e_receipt_signer_trust_root()
    errors.extend(trust_errors)
    if profile is not None:
        pytest_provider = (
            governed_capture_record.get("pytest_provider")
            if isinstance(governed_capture_record, dict)
            else None
        )
        if not isinstance(pytest_provider, dict):
            errors.append(
                "acceptance review governed pytest provider is absent"
            )
        else:
            if pytest_provider.get("profile_id") != profile.get(
                "governed_pytest_provider_profile_id"
            ):
                errors.append(
                    "acceptance review governed pytest provider profile differs "
                    "from fixed off-repository trust root"
                )
            if pytest_provider.get("lock_sha256") != profile.get(
                "governed_pytest_provider_lock_sha256"
            ):
                errors.append(
                    "acceptance review pytest provider lock differs from fixed "
                    "off-repository trust root"
                )
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
    governed_capture_record: Any = None,
    disposable_test_effect_chains: Any = None,
    durability_anchor_attestation: Any = None,
    predecessor_receipt: Any = None,
    predecessor_authority: Any = None,
    predecessor_consumption_bootstrap_authority: Any = None,
) -> dict[str, Any]:
    """Issue one ready receipt only after the complete review path verifies."""

    trusted_now = _time(_trusted_issuance_now())
    if isinstance(candidate, dict) and candidate.get("schema_version") == (
        "s2e_launch_genesis_receipt_v1"
    ):
        errors = validate_s2e_launch_genesis_receipt(candidate, repo_root=repo_root)
        ready_status = "W0_GENESIS_READY"
        review_predecessor_chain: list[dict[str, Any]] = []
    elif isinstance(candidate, dict) and candidate.get("schema_version") == (
        "s2e_launch_wave_receipt_v1"
    ):
        if predecessor_receipt is None or not isinstance(
            predecessor_authority, dict
        ):
            errors = [
                "wave receipt issuance requires exact predecessor authority"
            ]
            review_predecessor_chain = []
        else:
            chain_before = predecessor_authority.get(
                "launch_chain_before_predecessor"
            )
            review_predecessor_chain = (
                [*chain_before, predecessor_receipt]
                if isinstance(chain_before, list)
                else []
            )
            consumed = {
                str(item.get("payload_digest"))
                for item in chain_before
                if isinstance(item, dict)
            } if isinstance(chain_before, list) else set()
            errors = validate_s2e_launch_transition(
                candidate,
                predecessor_receipt=predecessor_receipt,
                predecessor_authority=predecessor_authority,
                repo_root=repo_root,
                now=trusted_now,
                consumed_predecessor_digests=frozenset(consumed),
            )
        ready_status = "TASK_BRANCH_CHECKPOINT_READY"
    else:
        errors = ["launch receipt candidate schema is unsupported"]
        ready_status = None
        review_predecessor_chain = []
    errors.extend(
        validate_s2e_launch_acceptance_review_bundle(
            acceptance_review_bundle,
            candidate=candidate,
            governed_capture_record=governed_capture_record,
            disposable_test_effect_chains=disposable_test_effect_chains,
            predecessor_chain=review_predecessor_chain,
            durability_anchor_attestation=durability_anchor_attestation,
            repo_root=repo_root,
            now=trusted_now,
        )
    )
    issued_receipt = None
    predecessor_consumption_result = None
    if not errors and ready_status is not None:
        issued_receipt = dict(candidate)
        issued_receipt["checkpoint_status"] = ready_status
        issued_receipt["acceptance_review_bundle_digest"] = (
            acceptance_review_bundle["bundle_digest"]
        )
        issued_receipt["side_effect_class"] = "DISPOSABLE_TEST"
        issued_receipt["disposable_effect_chain_digests"] = list(
            acceptance_review_bundle["disposable_test_effect_chain_digests"]
        )
        if ready_status != "W0_GENESIS_READY":
            try:
                predecessor_consumption_result = (
                    consume_s2e_launch_predecessor(
                        repo_root=repo_root,
                        candidate=candidate,
                        predecessor_receipt=predecessor_receipt,
                        predecessor_chain=review_predecessor_chain,
                        acceptance_review_bundle_digest=(
                            acceptance_review_bundle["bundle_digest"]
                        ),
                        now=trusted_now,
                        bootstrap_authority=(
                            predecessor_consumption_bootstrap_authority
                        ),
                    )
                )
                issued_receipt["predecessor_consumption"] = (
                    predecessor_consumption_result["entry"]
                )
            except (
                OSError,
                TypeError,
                ValueError,
                subprocess.CalledProcessError,
            ) as error:
                errors.append(
                    f"wave predecessor durable consumption failed: {error}"
                )
        issued_receipt["payload_digest"] = launch_payload_digest(issued_receipt)
        if errors:
            issued_receipt = None
        elif ready_status == "W0_GENESIS_READY":
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
                    predecessor_authority=predecessor_authority,
                    repo_root=repo_root,
                    now=trusted_now,
                    consumed_predecessor_digests=frozenset(consumed),
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
        "predecessor_consumption_result": predecessor_consumption_result,
        "issued_receipt": issued_receipt,
        "errors": sorted(set(errors)),
    }
    result["issuance_result_digest"] = canonical_digest(result)
    return result


def _build_genesis_candidate_payload(
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
        "wave_exit_id": S2E_WAVE_EXIT_IDS[GENESIS_WAVE],
        "checkpoint_status": "PENDING_REVIEW",
        "acceptance_review_bundle_digest": None,
        "side_effect_class": "SOURCE_ONLY",
        "disposable_effect_chain_digests": [],
        "production_effect_count": 0,
    }
    receipt["payload_digest"] = launch_payload_digest(receipt)
    errors = validate_s2e_launch_genesis_receipt(receipt, repo_root=repo_root)
    if errors:
        raise ValueError("; ".join(errors))
    return receipt


def build_genesis_candidate(
    *,
    repo_root: Path,
    baseline_head: str,
    schema_carrier_head: str,
    launch_contract_digest: str,
    generation_task_contract_digest: str,
) -> dict[str, Any]:
    """Generate W0 only from the clean, current tooling generation."""

    resolved_carrier = _commit(repo_root, schema_carrier_head)
    if resolved_carrier != _commit(repo_root, "HEAD"):
        raise ValueError(
            "genesis schema_carrier_head must equal current repository HEAD"
        )
    return _build_genesis_candidate_payload(
        repo_root=repo_root,
        baseline_head=baseline_head,
        schema_carrier_head=resolved_carrier,
        launch_contract_digest=launch_contract_digest,
        generation_task_contract_digest=generation_task_contract_digest,
    )


def _build_wave_candidate_payload(
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
    resolved_source_head = _commit(repo_root, source_head)
    current_head = _commit(repo_root, "HEAD")
    if resolved_source_head != current_head:
        raise ValueError("wave candidate source_head must equal current repository HEAD")
    if side_effect_class != "SOURCE_ONLY":
        raise ValueError(
            "DISPOSABLE_TEST wave candidates require a paired typed effect-chain binder"
        )
    receipt: dict[str, Any] = {
        "schema_version": "s2e_launch_wave_receipt_v1",
        "launch_id": LAUNCH_ID,
        "wave": wave,
        "predecessor": predecessor_receipt.get("payload_digest"),
        "source_head": resolved_source_head,
        "source_tree": _tree(repo_root, source_head),
        "schema_carrier_head": _commit(repo_root, schema_carrier_head),
        "schema_carrier_tree": _tree(repo_root, schema_carrier_head),
        "launch_contract_digest": launch_contract_digest,
        "generation_task_contract_digest": generation_task_contract_digest,
        "wave_exit_id": S2E_WAVE_EXIT_IDS[wave],
        "checkpoint_status": "PENDING_REVIEW",
        "acceptance_review_bundle_digest": None,
        "side_effect_class": side_effect_class,
        "disposable_effect_chain_digests": [],
        "predecessor_consumption": None,
        "production_effect_count": 0,
    }
    receipt["payload_digest"] = launch_payload_digest(receipt)
    errors = validate_s2e_launch_transition_payload(
        receipt,
        predecessor_receipt=predecessor_receipt,
        repo_root=repo_root,
        consumed_predecessor_digests=frozenset(),
    )
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
    predecessor_authority: dict[str, Any],
    launch_contract_digest: str,
    generation_task_contract_digest: str,
    now: str | datetime,
    side_effect_class: str = "SOURCE_ONLY",
) -> dict[str, Any]:
    """Build only after the predecessor review and carrier reverify."""

    receipt = _build_wave_candidate_payload(
        repo_root=repo_root,
        wave=wave,
        source_head=source_head,
        schema_carrier_head=schema_carrier_head,
        predecessor_receipt=predecessor_receipt,
        launch_contract_digest=launch_contract_digest,
        generation_task_contract_digest=generation_task_contract_digest,
        side_effect_class=side_effect_class,
    )
    chain = predecessor_authority.get("launch_chain_before_predecessor")
    consumed = {
        str(item.get("payload_digest"))
        for item in chain
        if isinstance(item, dict)
    } if isinstance(chain, list) else set()
    errors = validate_s2e_launch_transition(
        receipt,
        predecessor_receipt=predecessor_receipt,
        predecessor_authority=predecessor_authority,
        repo_root=repo_root,
        now=now,
        consumed_predecessor_digests=frozenset(consumed),
    )
    if errors:
        raise ValueError("; ".join(errors))
    return receipt
