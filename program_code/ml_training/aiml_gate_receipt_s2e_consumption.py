"""Durable consume-once state for S2E launch predecessor receipts."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _load_schema, canonical_digest, git_subprocess_env,
)
from aiml_gate_receipt_s2e_external_evidence import (
    s2e_predecessor_registry_slot_id,
    validate_s2e_predecessor_registry_attestation,
)


LAUNCH_ID = "S2E-LW1-LW5"
LAUNCH_WAVES = ("S2E-LW1", "S2E-LW2", "S2E-LW3", "S2E-LW4", "S2E-LW5")
LEDGER_SCHEMA = "s2e_launch_predecessor_consumption_ledger_v1"
ENTRY_SCHEMA = "s2e_launch_predecessor_consumption_entry_v1"
BOOTSTRAP_SCHEMA = "s2e_launch_consumption_bootstrap_authority_v1"
BOOTSTRAP_PURPOSE = "AUTHORIZE_PREDECESSOR_SINGLE_USE_CONSUMPTION"
S2E_RECEIPT_SIGNER_IDENTITY = "aiml-s2e-receipt-signer-v1"
S2E_RECEIPT_SIGNATURE_NAMESPACE = "arcane-equilibrium-aiml-s2e-receipts"
STATE_BASENAME = "codex-s2e-launch-consumption-v1.json"
ANCHOR_BASENAME = "codex-s2e-launch-consumption-v1.anchor.json"
LOCK_BASENAME = "codex-s2e-launch-consumption-v1.lock"
MAX_STATE_BYTES = 512 * 1024


def _without_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def s2e_launch_consumption_entry_digest(entry: dict[str, Any]) -> str:
    return canonical_digest(_without_digest(entry, "entry_digest"))


def s2e_launch_consumption_ledger_digest(ledger: dict[str, Any]) -> str:
    return canonical_digest(_without_digest(ledger, "ledger_digest"))


def _timestamp(value: str | datetime) -> str:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("consumption timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def validate_s2e_launch_consumption_ledger(ledger: Any) -> list[str]:
    schema = _load_schema(LEDGER_SCHEMA)
    errors = schema_subset_errors(ledger, schema)
    if errors or not isinstance(ledger, dict):
        return errors
    if ledger.get("ledger_digest") != s2e_launch_consumption_ledger_digest(
        ledger
    ):
        errors.append("S2E launch consumption ledger digest is invalid")
    entries = ledger.get("entries", [])
    predecessor_digests: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if entry.get("sequence") != index + 1:
            errors.append("S2E launch consumption sequence is not contiguous")
        expected_previous = (
            None if index == 0 else entries[index - 1].get("entry_digest")
        )
        if entry.get("previous_entry_digest") != expected_previous:
            errors.append("S2E launch consumption hash chain is broken")
        if entry.get("entry_digest") != s2e_launch_consumption_entry_digest(
            entry
        ):
            errors.append("S2E launch consumption entry digest is invalid")
        predecessor = str(entry.get("predecessor_payload_digest", ""))
        if predecessor in predecessor_digests:
            errors.append("S2E launch predecessor was consumed more than once")
        predecessor_digests.add(predecessor)
        if entry.get("successor_wave") != LAUNCH_WAVES[index]:
            errors.append("S2E launch consumption wave order is not canonical")
        try:
            _timestamp(entry.get("consumed_at"))
        except (TypeError, ValueError) as error:
            errors.append(f"S2E launch consumption timestamp is invalid: {error}")
    return sorted(set(errors))


def validate_s2e_launch_consumption_entry(
    entry: Any,
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    acceptance_review_bundle_digest: str,
) -> list[str]:
    errors = validate_s2e_launch_consumption_entry_structure(entry)
    if errors or not isinstance(entry, dict):
        return errors
    for field, expected in (
        ("launch_id", LAUNCH_ID),
        (
            "predecessor_payload_digest",
            predecessor_receipt.get("payload_digest"),
        ),
        ("successor_candidate_payload_digest", candidate.get("payload_digest")),
        ("successor_wave", candidate.get("wave")),
        ("successor_source_head", candidate.get("source_head")),
        (
            "acceptance_review_bundle_digest",
            acceptance_review_bundle_digest,
        ),
        ("side_effect_class", "LOCAL_SOURCE_CONTROL_STATE"),
        ("production_effect", False),
    ):
        if entry.get(field) != expected:
            errors.append(f"S2E launch consumption {field} binding differs")
    return sorted(set(errors))


def validate_s2e_launch_consumption_entry_structure(entry: Any) -> list[str]:
    """Validate the self-contained portion before a predecessor is supplied."""

    schema = _load_schema(LEDGER_SCHEMA)
    errors = schema_subset_errors(
        entry, schema["$defs"]["entry"], root_schema=schema
    )
    if errors or not isinstance(entry, dict):
        return errors
    if entry.get("entry_digest") != s2e_launch_consumption_entry_digest(entry):
        errors.append("S2E launch consumption entry digest is invalid")
    try:
        _timestamp(entry.get("consumed_at"))
    except (TypeError, ValueError) as error:
        errors.append(f"S2E launch consumption timestamp is invalid: {error}")
    return sorted(set(errors))


def _empty_ledger() -> dict[str, Any]:
    ledger = {
        "schema_version": LEDGER_SCHEMA,
        "launch_id": LAUNCH_ID,
        "entries": [],
    }
    ledger["ledger_digest"] = s2e_launch_consumption_ledger_digest(ledger)
    return ledger


def s2e_launch_consumption_bootstrap_slot_id(
    predecessor_payload_digest: str,
) -> str:
    return s2e_predecessor_registry_slot_id(predecessor_payload_digest)


def s2e_launch_consumption_bootstrap_signed_bytes(
    authority: dict[str, Any],
) -> bytes:
    return json.dumps(
        {
            key: value
            for key, value in authority.items()
            if key not in {
                "signed_core_digest",
                "signature",
                "authority_digest",
            }
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def s2e_launch_consumption_bootstrap_authority_digest(
    authority: dict[str, Any],
) -> str:
    return canonical_digest(_without_digest(authority, "authority_digest"))


def _raw_digest(value: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value).hexdigest()


def _ledger_from_predecessor_chain(
    predecessor_chain: list[dict[str, Any]],
) -> dict[str, Any]:
    entries = [
        receipt["predecessor_consumption"]
        for receipt in predecessor_chain
        if receipt.get("schema_version") == "s2e_launch_wave_receipt_v1"
        and isinstance(receipt.get("predecessor_consumption"), dict)
    ]
    ledger = {
        "schema_version": LEDGER_SCHEMA,
        "launch_id": LAUNCH_ID,
        "entries": entries,
    }
    ledger["ledger_digest"] = s2e_launch_consumption_ledger_digest(ledger)
    errors = validate_s2e_launch_consumption_ledger(ledger)
    if errors:
        raise ValueError(
            "authenticated predecessor chain does not form a consumption ledger: "
            + "; ".join(errors)
        )
    return ledger


def _s2e_launch_consumption_bootstrap_material(
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    predecessor_chain: list[dict[str, Any]],
    acceptance_review_bundle_digest: str,
    consumed_at: str | datetime,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    prior = _ledger_from_predecessor_chain(predecessor_chain)
    consumed = _timestamp(consumed_at)
    sequence = len(prior["entries"]) + 1
    entry = {
        "schema_version": ENTRY_SCHEMA,
        "sequence": sequence,
        "previous_entry_digest": (
            prior["entries"][-1]["entry_digest"]
            if prior["entries"]
            else None
        ),
        "launch_id": LAUNCH_ID,
        "predecessor_payload_digest": predecessor_receipt.get(
            "payload_digest"
        ),
        "successor_candidate_payload_digest": candidate.get("payload_digest"),
        "successor_wave": candidate.get("wave"),
        "successor_source_head": candidate.get("source_head"),
        "acceptance_review_bundle_digest": acceptance_review_bundle_digest,
        "consumed_at": consumed,
        "side_effect_class": "LOCAL_SOURCE_CONTROL_STATE",
        "production_effect": False,
    }
    entry["entry_digest"] = s2e_launch_consumption_entry_digest(entry)
    result_ledger = {
        "schema_version": LEDGER_SCHEMA,
        "launch_id": LAUNCH_ID,
        "entries": [*prior["entries"], entry],
    }
    result_ledger["ledger_digest"] = s2e_launch_consumption_ledger_digest(
        result_ledger
    )
    return prior, entry, result_ledger


def build_s2e_predecessor_registry_request(
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    predecessor_chain: list[dict[str, Any]],
    acceptance_review_bundle_digest: str,
    consumed_at: str | datetime,
) -> dict[str, Any]:
    """Build the exact non-authoritative subject an external registry consumes."""

    prior, entry, result_ledger = _s2e_launch_consumption_bootstrap_material(
        candidate=candidate,
        predecessor_receipt=predecessor_receipt,
        predecessor_chain=predecessor_chain,
        acceptance_review_bundle_digest=acceptance_review_bundle_digest,
        consumed_at=consumed_at,
    )
    predecessor_digest = str(predecessor_receipt.get("payload_digest", ""))
    request = {
        "schema_version": "s2e_predecessor_registry_request_v1",
        "launch_id": LAUNCH_ID,
        "slot_id": s2e_launch_consumption_bootstrap_slot_id(predecessor_digest),
        "predecessor_payload_digest": predecessor_digest,
        "successor_candidate_payload_digest": candidate.get("payload_digest"),
        "successor_wave": candidate.get("wave"),
        "successor_source_head": candidate.get("source_head"),
        "acceptance_review_bundle_digest": acceptance_review_bundle_digest,
        "prior_consumption_ledger_digest": prior["ledger_digest"],
        "expected_consumption_entry_digest": entry["entry_digest"],
        "expected_result_ledger_digest": result_ledger["ledger_digest"],
        "consumed_at": entry["consumed_at"],
        "requested_decision": "GRANTED_ONCE",
        "conflicting_grant_required_absent": True,
        "production_authority": False,
        "production_effect": False,
    }
    request["request_digest"] = canonical_digest(request)
    return request


def build_s2e_launch_consumption_bootstrap_authority_core(
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    predecessor_chain: list[dict[str, Any]],
    acceptance_review_bundle_digest: str,
    registry_attestation: dict[str, Any],
    signer: dict[str, Any],
    issued_at: str | datetime,
    expires_at: str | datetime,
) -> dict[str, Any]:
    """Build a receipt-signer core only after independent registry proof."""

    issued = _timestamp(issued_at)
    prior, entry, result_ledger = _s2e_launch_consumption_bootstrap_material(
        candidate=candidate,
        predecessor_receipt=predecessor_receipt,
        predecessor_chain=predecessor_chain,
        acceptance_review_bundle_digest=acceptance_review_bundle_digest,
        consumed_at=issued,
    )
    registry_errors = validate_s2e_predecessor_registry_attestation(
        registry_attestation,
        candidate=candidate,
        predecessor_receipt=predecessor_receipt,
        acceptance_review_bundle_digest=acceptance_review_bundle_digest,
        prior_consumption_ledger_digest=prior["ledger_digest"],
        expected_consumption_entry=entry,
        expected_result_ledger_digest=result_ledger["ledger_digest"],
        now=issued,
    )
    if registry_errors:
        raise ValueError(
            "independent predecessor registry attestation is invalid: "
            + "; ".join(registry_errors)
        )
    predecessor_digest = str(predecessor_receipt.get("payload_digest", ""))
    return {
        "schema_version": BOOTSTRAP_SCHEMA,
        "purpose": BOOTSTRAP_PURPOSE,
        "launch_id": LAUNCH_ID,
        "predecessor_payload_digest": predecessor_digest,
        "successor_candidate_payload_digest": candidate.get("payload_digest"),
        "successor_wave": candidate.get("wave"),
        "successor_source_head": candidate.get("source_head"),
        "acceptance_review_bundle_digest": acceptance_review_bundle_digest,
        "prior_consumption_ledger_digest": prior["ledger_digest"],
        "expected_consumption_entry": entry,
        "expected_result_ledger_digest": result_ledger["ledger_digest"],
        "registry_attestation": deepcopy(registry_attestation),
        "issued_at": issued,
        "expires_at": _timestamp(expires_at),
        "side_effect_class": "LOCAL_SOURCE_CONTROL_STATE",
        "production_authority": False,
        "production_effect": False,
        "signer": signer,
    }


def validate_s2e_launch_consumption_bootstrap_authority(
    authority: Any,
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    predecessor_chain: list[dict[str, Any]],
    acceptance_review_bundle_digest: str,
    now: str | datetime,
) -> list[str]:
    schema = _load_schema(BOOTSTRAP_SCHEMA)
    errors = schema_subset_errors(authority, schema, root_schema=schema)
    if errors or not isinstance(authority, dict):
        return errors
    try:
        prior = _ledger_from_predecessor_chain(predecessor_chain)
    except ValueError as error:
        return [str(error)]
    expected_entry = authority.get("expected_consumption_entry")
    errors.extend(validate_s2e_launch_consumption_entry(
        expected_entry,
        candidate=candidate,
        predecessor_receipt=predecessor_receipt,
        acceptance_review_bundle_digest=acceptance_review_bundle_digest,
    ))
    for field, expected in (
        ("purpose", BOOTSTRAP_PURPOSE),
        ("launch_id", LAUNCH_ID),
        (
            "predecessor_payload_digest",
            predecessor_receipt.get("payload_digest"),
        ),
        (
            "successor_candidate_payload_digest",
            candidate.get("payload_digest"),
        ),
        ("successor_wave", candidate.get("wave")),
        ("successor_source_head", candidate.get("source_head")),
        (
            "acceptance_review_bundle_digest",
            acceptance_review_bundle_digest,
        ),
        ("prior_consumption_ledger_digest", prior["ledger_digest"]),
        ("side_effect_class", "LOCAL_SOURCE_CONTROL_STATE"),
        ("production_authority", False),
        ("production_effect", False),
    ):
        if authority.get(field) != expected:
            errors.append(f"S2E consumption bootstrap {field} binding differs")
    if isinstance(expected_entry, dict):
        if expected_entry.get("sequence") != len(prior["entries"]) + 1:
            errors.append("S2E consumption bootstrap entry sequence differs")
        expected_previous = (
            prior["entries"][-1]["entry_digest"]
            if prior["entries"]
            else None
        )
        if expected_entry.get("previous_entry_digest") != expected_previous:
            errors.append(
                "S2E consumption bootstrap previous entry binding differs"
            )
        result_ledger = {
            "schema_version": LEDGER_SCHEMA,
            "launch_id": LAUNCH_ID,
            "entries": [*prior["entries"], expected_entry],
        }
        result_ledger["ledger_digest"] = (
            s2e_launch_consumption_ledger_digest(result_ledger)
        )
        errors.extend(validate_s2e_launch_consumption_ledger(result_ledger))
        if authority.get("expected_result_ledger_digest") != result_ledger[
            "ledger_digest"
        ]:
            errors.append(
                "S2E consumption bootstrap result ledger digest differs"
            )
    registry = authority.get("registry_attestation", {})
    errors.extend(
        "S2E consumption bootstrap registry: " + error
        for error in validate_s2e_predecessor_registry_attestation(
            registry,
            candidate=candidate,
            predecessor_receipt=predecessor_receipt,
            acceptance_review_bundle_digest=acceptance_review_bundle_digest,
            prior_consumption_ledger_digest=prior["ledger_digest"],
            expected_consumption_entry=(
                expected_entry if isinstance(expected_entry, dict) else {}
            ),
            expected_result_ledger_digest=str(
                authority.get("expected_result_ledger_digest", "")
            ),
            now=now,
        )
    )
    signed_bytes = s2e_launch_consumption_bootstrap_signed_bytes(authority)
    signed_digest = _raw_digest(signed_bytes)
    if authority.get("signed_core_digest") != signed_digest:
        errors.append("S2E consumption bootstrap signed core digest is invalid")
    signature = authority.get("signature", {})
    if signature.get("signed_digest") != signed_digest:
        errors.append("S2E consumption bootstrap signature binding differs")
    if authority.get("authority_digest") != (
        s2e_launch_consumption_bootstrap_authority_digest(authority)
    ):
        errors.append("S2E consumption bootstrap authority digest is invalid")
    try:
        issued = datetime.fromisoformat(
            str(authority["issued_at"]).replace("Z", "+00:00")
        )
        expires = datetime.fromisoformat(
            str(authority["expires_at"]).replace("Z", "+00:00")
        )
        evaluated = (
            now
            if isinstance(now, datetime)
            else datetime.fromisoformat(str(now).replace("Z", "+00:00"))
        )
        if (
            issued.tzinfo is None
            or expires.tzinfo is None
            or evaluated.tzinfo is None
            or not issued < expires
            or (expires - issued).total_seconds() > 600
            or not issued <= evaluated < expires
        ):
            errors.append(
                "S2E consumption bootstrap freshness window is invalid"
            )
        if isinstance(expected_entry, dict) and (
            expected_entry.get("consumed_at") != _timestamp(issued)
            or registry.get("observed_at") != _timestamp(issued)
        ):
            errors.append(
                "S2E consumption bootstrap signed timestamps differ"
            )
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"S2E consumption bootstrap timestamp is invalid: {error}")
    try:
        from aiml_gate_receipt_s2e_launch import (
            load_s2e_receipt_signer_trust_root,
        )
        import agent_governance_aiml_trusted_host as trusted_host

        profile, trust_errors = load_s2e_receipt_signer_trust_root()
        errors.extend(trust_errors)
        if profile is not None:
            signer = authority.get("signer", {})
            for field, profile_field in (
                ("identity", "signer_identity"),
                ("namespace", "signature_namespace"),
                ("key_generation", "key_generation"),
                ("anchor", "anchor"),
                ("key_fingerprint", "key_fingerprint"),
            ):
                if signer.get(field) != profile.get(profile_field):
                    errors.append(
                        f"S2E consumption bootstrap signer {field} differs "
                        "from fixed trust root"
                    )
            if not trusted_host._verify_ssh_signature(
                signed_bytes,
                str(signature.get("signature", "")).encode(
                    "ascii", errors="ignore"
                ),
                public_key=str(profile["public_key"]),
                identity=S2E_RECEIPT_SIGNER_IDENTITY,
                namespace=S2E_RECEIPT_SIGNATURE_NAMESPACE,
            ):
                errors.append(
                    "S2E consumption bootstrap SSHSIG verification failed"
                )
    except (ImportError, OSError, ValueError) as error:
        errors.append(
            f"S2E consumption bootstrap trusted signer is unavailable: {error}"
        )
    return sorted(set(errors))


def _git_common_dir(repo_root: Path) -> Path:
    raw = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        env=git_subprocess_env(),
        text=True,
    ).stdout.strip()
    path = Path(raw)
    return (path if path.is_absolute() else repo_root / path).resolve(strict=True)


def _private_regular_file(descriptor: int, *, label: str) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError(f"{label} must be one owner-only regular file")


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


class FileS2ELaunchConsumptionStore:
    """Atomic ledger plus an independent local reset-evident tombstone copy."""

    def __init__(self, repo_root: Path) -> None:
        self.common_dir = _git_common_dir(repo_root)
        self.state_path = self.common_dir / STATE_BASENAME
        self.anchor_path = self.common_dir / ANCHOR_BASENAME
        self.lock_path = self.common_dir / LOCK_BASENAME
        self.last_state_recovery_performed = False
        self.last_bootstrap_authority_applied = False

    def _read_file(
        self, path: Path, *, label: str
    ) -> dict[str, Any] | None:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            return None
        try:
            metadata = os.fstat(descriptor)
            _private_regular_file(descriptor, label=label)
            if metadata.st_size > MAX_STATE_BYTES:
                raise ValueError(
                    f"S2E launch {label} exceeds size limit"
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_STATE_BYTES:
                    raise ValueError(
                        f"S2E launch {label} exceeds size limit"
                    )
                chunks.append(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
        try:
            ledger = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"S2E launch {label} is unreadable: {error}"
            ) from error
        errors = validate_s2e_launch_consumption_ledger(ledger)
        if errors:
            raise ValueError("; ".join(errors))
        return ledger

    def _read_pair(
        self,
        *,
        bootstrap_prior_ledger: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool, bool]:
        state = self._read_file(
            self.state_path, label="consumption ledger"
        )
        anchor = self._read_file(
            self.anchor_path, label="consumption tombstone anchor"
        )
        if state is None and anchor is None:
            if bootstrap_prior_ledger is not None:
                return bootstrap_prior_ledger, False, True
            raise ValueError(
                "S2E launch consumption state and tombstone anchor were reset"
            )
        if anchor is None:
            raise ValueError(
                "S2E launch consumption tombstone anchor is missing"
            )
        if state is None:
            if not anchor["entries"]:
                raise ValueError(
                    "S2E launch valid-empty durable consumption generation "
                    "is forbidden"
                )
            return anchor, True, False
        if state != anchor:
            raise ValueError(
                "S2E launch consumption ledger differs from tombstone anchor"
            )
        if not state["entries"]:
            raise ValueError(
                "S2E launch valid-empty durable consumption generation "
                "is forbidden"
            )
        return state, False, False

    def _atomic_write(self, path: Path, ledger: dict[str, Any]) -> None:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f"{path.name}.", suffix=".tmp", dir=self.common_dir
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(ledger, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            parent_fd = os.open(
                self.common_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        finally:
            temporary.unlink(missing_ok=True)

    def _open_lock(self) -> tuple[int, bool]:
        base_flags = (
            os.O_RDWR
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(
                self.lock_path,
                base_flags | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            created = True
            os.fchmod(descriptor, 0o600)
        except FileExistsError:
            descriptor = os.open(self.lock_path, base_flags)
            created = False
        try:
            _private_regular_file(
                descriptor, label="consumption ledger tombstone lock"
            )
        except Exception:
            os.close(descriptor)
            raise
        return descriptor, created

    def read(self) -> dict[str, Any]:
        try:
            lock_fd = os.open(
                self.lock_path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
        except FileNotFoundError:
            if _path_entry_exists(self.state_path) or _path_entry_exists(
                self.anchor_path
            ):
                raise ValueError(
                    "S2E launch consumption tombstone lock is missing"
                )
            return _empty_ledger()
        try:
            _private_regular_file(
                lock_fd, label="consumption ledger tombstone lock"
            )
            fcntl.flock(lock_fd, fcntl.LOCK_SH)
            ledger, _, _ = self._read_pair()
            return ledger
        finally:
            os.close(lock_fd)

    def update(
        self,
        mutation: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        bootstrap_prior_ledger: dict[str, Any] | None = None,
        bootstrap_result_ledger_digest: str | None = None,
    ) -> dict[str, Any]:
        if (
            bootstrap_prior_ledger is None
            and not _path_entry_exists(self.state_path)
            and not _path_entry_exists(self.anchor_path)
            and not _path_entry_exists(self.lock_path)
        ):
            raise ValueError(
                "S2E launch explicit signed bootstrap authority is required"
            )
        lock_fd, _ = self._open_lock()
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current, recovery_required, bootstrap_required = self._read_pair(
                bootstrap_prior_ledger=bootstrap_prior_ledger
            )
            self.last_state_recovery_performed = recovery_required
            self.last_bootstrap_authority_applied = bootstrap_required
            candidate = mutation(current)
            errors = validate_s2e_launch_consumption_ledger(candidate)
            if errors:
                raise ValueError("; ".join(errors))
            if (
                candidate != current
                and bootstrap_result_ledger_digest is not None
                and candidate.get("ledger_digest")
                != bootstrap_result_ledger_digest
            ):
                raise ValueError(
                    "S2E launch bootstrap authority result ledger differs"
                )
            if bootstrap_required:
                if bootstrap_result_ledger_digest is None:
                    raise ValueError(
                        "S2E launch bootstrap result ledger binding is absent"
                    )
                # Never persist a valid-empty intermediate generation.  The
                # first durable bytes already contain the signed consumption.
                self._atomic_write(self.anchor_path, candidate)
                self._atomic_write(self.state_path, candidate)
                readback, _, _ = self._read_pair()
                if readback != candidate:
                    raise ValueError(
                        "S2E launch bootstrap durable readback differs"
                    )
                return candidate
            if recovery_required:
                self._atomic_write(self.state_path, current)
            if candidate == current:
                return current
            # Anchor first: a crash before the state replace leaves both
            # generations visible, so the next caller fails closed instead of
            # silently accepting a reset or partial commit.
            self._atomic_write(self.anchor_path, candidate)
            self._atomic_write(self.state_path, candidate)
            readback, _, _ = self._read_pair()
            if readback != candidate:
                raise ValueError("S2E launch consumption durable readback differs")
            return candidate
        finally:
            os.close(lock_fd)


def consume_s2e_launch_predecessor(
    *,
    repo_root: Path,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    predecessor_chain: list[dict[str, Any]],
    acceptance_review_bundle_digest: str,
    now: str | datetime,
    bootstrap_authority: Any = None,
) -> dict[str, Any]:
    """Consume one predecessor atomically; exact retries are idempotent."""

    if bootstrap_authority is None:
        raise ValueError(
            "S2E launch fresh signed external single-use registry authority "
            "is required for every predecessor consumption"
        )
    store = FileS2ELaunchConsumptionStore(repo_root)
    selected: dict[str, Any] = {}
    status = "CONSUMED"
    bootstrap_prior_ledger = None
    bootstrap_result_ledger_digest = None
    bootstrap_authority_digest = None
    if bootstrap_authority is not None:
        authority_errors = validate_s2e_launch_consumption_bootstrap_authority(
            bootstrap_authority,
            candidate=candidate,
            predecessor_receipt=predecessor_receipt,
            predecessor_chain=predecessor_chain,
            acceptance_review_bundle_digest=acceptance_review_bundle_digest,
            now=now,
        )
        if authority_errors:
            raise ValueError(
                "S2E launch consumption bootstrap authority is invalid: "
                + "; ".join(authority_errors)
            )
        bootstrap_prior_ledger = _ledger_from_predecessor_chain(
            predecessor_chain
        )
        bootstrap_result_ledger_digest = bootstrap_authority[
            "expected_result_ledger_digest"
        ]
        bootstrap_authority_digest = bootstrap_authority["authority_digest"]

    def mutation(ledger: dict[str, Any]) -> dict[str, Any]:
        nonlocal selected, status
        matching = [
            entry
            for entry in ledger["entries"]
            if entry["predecessor_payload_digest"]
            == predecessor_receipt.get("payload_digest")
        ]
        if matching:
            errors = validate_s2e_launch_consumption_entry(
                matching[0],
                candidate=candidate,
                predecessor_receipt=predecessor_receipt,
                acceptance_review_bundle_digest=acceptance_review_bundle_digest,
            )
            if errors:
                raise ValueError(
                    "S2E launch predecessor already consumed by another "
                    "successor: " + "; ".join(errors)
                )
            selected = matching[0]
            status = "IDEMPOTENT_REPLAY"
            return ledger
        entries = list(ledger["entries"])
        if isinstance(bootstrap_authority, dict):
            # The signed authority owns the first-generation timestamp and
            # entry bytes.  Reusing those exact bytes makes a crash/reset retry
            # reproduce the original issued receipt instead of minting a new
            # consumption identity from the retry wall clock.
            entry = dict(bootstrap_authority["expected_consumption_entry"])
        else:
            entry = {
                "schema_version": ENTRY_SCHEMA,
                "sequence": len(entries) + 1,
                "previous_entry_digest": (
                    entries[-1]["entry_digest"] if entries else None
                ),
                "launch_id": LAUNCH_ID,
                "predecessor_payload_digest": predecessor_receipt.get(
                    "payload_digest"
                ),
                "successor_candidate_payload_digest": candidate.get(
                    "payload_digest"
                ),
                "successor_wave": candidate.get("wave"),
                "successor_source_head": candidate.get("source_head"),
                "acceptance_review_bundle_digest": (
                    acceptance_review_bundle_digest
                ),
                "consumed_at": _timestamp(now),
                "side_effect_class": "LOCAL_SOURCE_CONTROL_STATE",
                "production_effect": False,
            }
            entry["entry_digest"] = s2e_launch_consumption_entry_digest(entry)
        entries.append(entry)
        updated = {
            "schema_version": LEDGER_SCHEMA,
            "launch_id": LAUNCH_ID,
            "entries": entries,
        }
        updated["ledger_digest"] = s2e_launch_consumption_ledger_digest(updated)
        selected = entry
        return updated

    ledger = store.update(
        mutation,
        bootstrap_prior_ledger=bootstrap_prior_ledger,
        bootstrap_result_ledger_digest=bootstrap_result_ledger_digest,
    )
    if store.last_bootstrap_authority_applied:
        # The external registry's signed GRANTED_ONCE claim is the authority
        # event.  Reconstructing its exact entry in the resettable local cache
        # is an idempotent physical recovery write, never a second logical
        # predecessor consumption.
        status = "IDEMPOTENT_AUTHORITY_RESTORE"
    physical_state_write_performed = bool(
        store.last_bootstrap_authority_applied
        or store.last_state_recovery_performed
        or status == "CONSUMED"
    )
    result = {
        "schema_version": "s2e_launch_predecessor_consumption_result_v1",
        "status": status,
        "entry": selected,
        "ledger_digest": ledger["ledger_digest"],
        "state_location_class": "GIT_COMMON_DIRECTORY",
        "reset_evidence_class": (
            "SIGNED_EXTERNAL_SINGLE_USE_REGISTRY_REQUIRED_PLUS_LOCAL_DUAL_COPY_V1"
        ),
        "tombstone_anchor_ledger_digest": ledger["ledger_digest"],
        "state_recovery_performed": bool(
            store.last_state_recovery_performed
            or store.last_bootstrap_authority_applied
        ),
        "physical_state_write_performed": (
            physical_state_write_performed
        ),
        "bootstrap_authority_applied": (
            store.last_bootstrap_authority_applied
        ),
        "bootstrap_authority_digest": bootstrap_authority_digest,
        "external_single_use_registry_authority_validated": True,
        "external_immutability_proven": False,
        "file_fsynced": True,
        "parent_directory_fsynced": True,
        "mutation_performed": (
            status == "CONSUMED"
            and not store.last_bootstrap_authority_applied
        ),
        "production_effect": False,
    }
    result["result_digest"] = canonical_digest(result)
    return result
