#!/usr/bin/env python3
"""Strict local manifest store for disposable S2.5 recovery rehearsals.

The public store has one code-owned path and no unit/path/identity/nonce input.
All filesystem work goes through an injected driver.  The driver is given exact
open-flag tuples and the store validates the returned directory/file facts before
using them.  A successful local commit remains
``UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED``: local checksums cannot detect a coherent
rewrite by the same writer.  The external append-only anchor/controller is the
next checkpoint and is deliberately not implemented here.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (Path(__file__).resolve().parent, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_attestation as attestation  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


DISPOSABLE_STATE_ROOT = (
    "/run/user/1000/arcane-equilibrium-aiml-s2e/s2_5-recovery"
)
MANIFEST_BASENAME = "recovery-store-manifest.json"
MANIFEST_TEMP_BASENAME = ".recovery-store-manifest.json.tmp"
REPLAY_LEDGER_BASENAME = "authorization-replay-ledger.json"
PROFILE_ID = "s2_5_recovery_user_systemd_disposable_v1"
PROFILE_UID = 1000
PROFILE_GID = 1000

PARENT_OPEN_FLAGS = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
READ_OPEN_FLAGS = ("O_NOFOLLOW", "O_CLOEXEC")
TEMP_OPEN_FLAGS = ("O_NOFOLLOW", "O_CREAT", "O_EXCL", "O_CLOEXEC")
ROOT_MODE = "0700"
FILE_MODE = "0600"
FILE_MODE_BITS = 0o600

STATUS_UNVERIFIED = "UNVERIFIED_EXTERNAL_ANCHOR_REQUIRED"
STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_AUTHORIZATION_RE = re.compile(r"^s2-5-auth-[0-9a-f]{64}$")
_JOURNAL_RE = re.compile(r"^(s2-5-[0-9a-f]{64})\.journal\.json$")
_JOURNAL_TERMINAL_STATES = frozenset({
    "TERMINAL_SUCCESS",
    "TERMINAL_ROLLED_BACK",
    "TERMINAL_FAILED",
})
_SCHEMA_DIR = REPO_ROOT / ".codex" / "schemas"
_LOCAL_SCHEMAS = frozenset({
    "s2_5_recovery_store_manifest_v1",
    "s2_5_recovery_store_intent_v1",
    "s2_5_recovery_store_result_v1",
    "s2_5_recovery_store_postcheck_v1",
    "s2_5_recovery_store_rollback_v1",
    "s2_5_recovery_anchor_entry_v1",
})
_COMMON = {
    "side_effect_class": "DISPOSABLE_TEST",
    "target_class": "disposable_systemd",
    "target_profile_id": PROFILE_ID,
    "production_effect": False,
    "production_authority": False,
    "production_effect_count": 0,
}


class RecoveryStoreError(RuntimeError):
    """Typed fail-closed store error with a stable, non-secret code."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class RecoveryStoreCrash(RuntimeError):
    """Test-injected process-crash marker; never converted into a success."""


def _raw_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["self_digest"] = central_validator.artifact_self_digest(sealed)
    return sealed


@lru_cache(maxsize=None)
def _local_schema(schema_version: str) -> dict[str, Any]:
    if schema_version not in _LOCAL_SCHEMAS:
        raise RecoveryStoreError("local_schema_version_unknown")
    path = _SCHEMA_DIR / f"{schema_version}.schema.json"
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RecoveryStoreError(
            "local_schema_unreadable", type(error).__name__
        ) from error
    if not isinstance(schema, dict):
        raise RecoveryStoreError("local_schema_is_not_an_object")
    return schema


def validate_local_artifact(artifact: Any) -> list[str]:
    """Validate one of the six local schemas without central ``SCHEMA_FILES``."""

    if not isinstance(artifact, dict):
        return ["local recovery-store artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if schema_version not in _LOCAL_SCHEMAS:
        return ["local recovery-store schema_version is unknown"]
    schema = _local_schema(schema_version)
    errors = schema_subset_errors(artifact, schema, schema)
    if artifact.get("self_digest") != central_validator.artifact_self_digest(artifact):
        errors.append("local recovery-store self_digest does not re-derive")
    for key, expected in _COMMON.items():
        if artifact.get(key) != expected:
            errors.append(f"local recovery-store {key} differs from the closed profile")
    errors.extend(_semantic_errors(artifact))
    return errors


def _aware_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise RecoveryStoreError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RecoveryStoreError(f"{field}_invalid") from error
    if parsed.tzinfo is None:
        raise RecoveryStoreError(f"{field}_timezone_missing")
    return parsed


def _validate_ttl(issued_at: Any, expires_at: Any) -> None:
    issued = _aware_timestamp(issued_at, field="issued_at")
    expires = _aware_timestamp(expires_at, field="expires_at")
    seconds = (expires - issued).total_seconds()
    if seconds <= 0 or seconds > 300:
        raise RecoveryStoreError("intent_ttl_outside_closed_five_minute_window")


def _integer(value: Any, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _manifest_semantic_errors(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    generation = artifact.get("generation")
    previous = artifact.get("previous_manifest_digest")
    if _integer(generation, minimum=1):
        if generation == 1 and previous is not None:
            errors.append("manifest generation one must have no predecessor")
        if generation > 1 and previous is None:
            errors.append("manifest generation after one must bind its predecessor")
    phase = artifact.get("phase")
    unresolved = artifact.get("unresolved_state_digest")
    anchor = artifact.get("anchor_head_digest")
    consumed = artifact.get("consumed_authorization_ids")
    if isinstance(consumed, list) and consumed != sorted(consumed):
        errors.append("manifest consumed authorization ids are not canonical-sorted")
    if phase in {"PREPARED", "COMMITTED"} and unresolved is None:
        errors.append(f"manifest {phase} phase must retain unresolved state")
    if phase in {"COMMITTED", "RESOLVED"} and anchor is None:
        errors.append(f"manifest {phase} phase must bind an external anchor")
    if phase == "RESOLVED":
        if unresolved is not None:
            errors.append("resolved manifest must clear unresolved state")
        if not isinstance(consumed, list) or not consumed:
            errors.append("resolved manifest must bind consumed authorization")
    replay = artifact.get("replay_ledger")
    if isinstance(replay, dict):
        present = replay.get("present")
        count = replay.get("entry_count")
        file_digest = replay.get("file_digest")
        head_digest = replay.get("head_digest")
        if present is False and (
            count != 0 or file_digest is not None or head_digest is not None
        ):
            errors.append("absent replay ledger must have an empty null head")
        if present is True:
            if file_digest is None:
                errors.append("present replay ledger must bind its file digest")
            if count == 0 and head_digest is not None:
                errors.append("empty replay ledger must have a null head")
            if _integer(count, minimum=1) and head_digest is None:
                errors.append("non-empty replay ledger must bind its head")
        if isinstance(consumed, list) and _integer(count):
            if len(consumed) != count:
                errors.append(
                    "manifest consumed authorization count differs from replay ledger"
                )
    inventory = artifact.get("journal_inventory")
    if isinstance(inventory, list):
        if inventory != sorted(
            inventory,
            key=lambda entry: (
                entry.get("basename", "") if isinstance(entry, dict) else ""
            ),
        ):
            errors.append("manifest journal inventory is not canonical-sorted")
        expected_set_digest = central_validator.canonical_digest({
            "schema_version": "s2_5_recovery_journal_set_v1",
            "entries": inventory,
        })
        if artifact.get("journal_set_digest") != expected_set_digest:
            errors.append("manifest journal-set digest does not re-derive")
        for index, entry in enumerate(inventory):
            if not isinstance(entry, dict):
                continue
            if entry.get("basename") != f"{entry.get('start_id')}.journal.json":
                errors.append(
                    f"manifest journal inventory entry {index} basename/start_id differ"
                )
    identity = artifact.get("state_root_identity")
    if isinstance(identity, dict):
        state_root_id = central_validator.canonical_digest(identity)
        if artifact.get("state_root_id") != state_root_id:
            errors.append("manifest state-root id does not re-derive")
        expected_store_digest = central_validator.canonical_digest({
            "profile_id": PROFILE_ID,
            "state_root_id": state_root_id,
        })
        expected_store_id = (
            "s2-5-store-" + expected_store_digest.removeprefix("sha256:")
        )
        if artifact.get("store_id") != expected_store_id:
            errors.append("manifest store id does not re-derive")
    return errors


def _intent_semantic_errors(artifact: dict[str, Any]) -> list[str]:
    try:
        _validate_ttl(artifact.get("issued_at"), artifact.get("expires_at"))
    except RecoveryStoreError as error:
        return [f"store intent TTL is invalid: {error.code}"]
    return []


def _result_semantic_errors(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = artifact.get("status")
    bits = tuple(
        artifact.get(field)
        for field in (
            "file_fsynced",
            "atomic_replace",
            "directory_fsynced",
            "parent_identity_rechecked",
        )
    )
    failure = artifact.get("failure_code")
    manifest_digest = artifact.get("manifest_digest")
    candidate_temp_identity = artifact.get("candidate_temp_identity")
    if status == "COMMITTED":
        errors.append("local recovery-store result can never be COMMITTED")
    elif status == "EXTERNAL_VERIFICATION_PENDING":
        if bits != (True, True, True, True):
            errors.append("pending result requires the complete durability chain")
        if manifest_digest is None:
            errors.append("pending result must bind a manifest")
        if not isinstance(candidate_temp_identity, dict):
            errors.append("pending result must bind the candidate temp identity")
        if failure != STATUS_UNVERIFIED:
            errors.append("pending result must retain the external-anchor requirement")
    elif status == "RECOVERY_REQUIRED":
        if not isinstance(failure, str) or failure in {"", STATUS_UNVERIFIED}:
            errors.append("recovery result must carry its concrete failure code")
        if bits == (True, True, True, True):
            errors.append("recovery result cannot claim a complete durability chain")
    elif status == "REJECTED":
        if bits != (False, False, False, False):
            errors.append("rejected result cannot claim durability progress")
        if manifest_digest is not None:
            errors.append("rejected result cannot bind a committed manifest")
        if not isinstance(failure, str) or not failure:
            errors.append("rejected result must carry a failure code")
    file_fsynced, atomic_replace, directory_fsynced, parent_rechecked = bits
    if atomic_replace is True and (
        file_fsynced is not True or parent_rechecked is not True
    ):
        errors.append("atomic replace requires file fsync and parent recheck")
    if atomic_replace is True and not isinstance(candidate_temp_identity, dict):
        errors.append("atomic replace must bind the candidate temp identity")
    if parent_rechecked is True and file_fsynced is not True:
        errors.append("parent recheck cannot precede file fsync")
    if directory_fsynced is True and atomic_replace is not True:
        errors.append("directory fsync cannot precede atomic replace")
    return errors


def _postcheck_semantic_errors(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = artifact.get("status")
    safe_bits = (
        artifact.get("manifest_match"),
        artifact.get("manifest_identity_match"),
        artifact.get("parent_identity_match"),
        artifact.get("temp_residue_absent"),
    )
    failure = artifact.get("failure_code")
    if status == "PASS":
        if safe_bits != (True, True, True, True):
            errors.append("PASS postcheck requires every independent safety check")
        if artifact.get("readback_digest") is None:
            errors.append("PASS postcheck must bind an independent readback")
        if failure is not None:
            errors.append("PASS postcheck cannot carry a failure code")
    elif status == "RECOVERY_REQUIRED":
        if not isinstance(failure, str) or not failure:
            errors.append("recovery postcheck must carry a failure code")
    elif status == "NOT_PERFORMED":
        if safe_bits != (False, False, False, False):
            errors.append("unperformed postcheck cannot claim safety checks")
        if artifact.get("readback_digest") is not None:
            errors.append("unperformed postcheck cannot bind a readback")
        if not isinstance(failure, str) or not failure:
            errors.append("unperformed postcheck must carry a failure code")
    if (
        artifact.get("manifest_match") is True
        or artifact.get("manifest_identity_match") is True
    ) and artifact.get("readback_digest") is None:
        errors.append("postcheck match claims require an independent readback")
    return errors


def _rollback_semantic_errors(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    status = artifact.get("status")
    restored = artifact.get("restored_manifest_digest")
    temp_absent = artifact.get("temp_residue_absent")
    operator_required = artifact.get("operator_action_required")
    if status == "NOT_REQUIRED" and (
        restored is not None or temp_absent is not True or operator_required is not False
    ):
        errors.append("NOT_REQUIRED rollback must be residue-free and locally safe")
    elif status == "ROLLED_BACK" and (
        restored is None or temp_absent is not True or operator_required is not False
    ):
        errors.append("ROLLED_BACK receipt must bind restoration and no residue")
    elif status == "RECOVERY_REQUIRED" and (
        restored is not None or operator_required is not True
    ):
        errors.append("recovery rollback must require an operator and no fake restore")
    return errors


def _anchor_semantic_errors(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("append_actor_identity") == artifact.get(
        "readback_verifier_identity"
    ):
        errors.append("anchor append and readback identities must differ")
    sequence = artifact.get("sequence")
    previous = artifact.get("previous_anchor_digest")
    if _integer(sequence, minimum=1):
        if sequence == 1 and previous is not None:
            errors.append("anchor sequence one must have no predecessor")
        if sequence > 1 and previous is None:
            errors.append("anchor sequence after one must bind its predecessor")
    if artifact.get("entry_status") == "CONSUMED" and artifact.get(
        "authorization_id"
    ) is None:
        errors.append("consumed anchor must bind an authorization")
    if artifact.get("entry_status") == "RESOLVED" and artifact.get(
        "unresolved_state_digest"
    ) is not None:
        errors.append("resolved anchor must clear unresolved state")
    if artifact.get("entry_status") != "RESOLVED" and artifact.get(
        "unresolved_state_digest"
    ) is None:
        errors.append("non-resolved anchor must retain unresolved state")
    return errors


def _semantic_errors(artifact: dict[str, Any]) -> list[str]:
    return {
        "s2_5_recovery_store_manifest_v1": _manifest_semantic_errors,
        "s2_5_recovery_store_intent_v1": _intent_semantic_errors,
        "s2_5_recovery_store_result_v1": _result_semantic_errors,
        "s2_5_recovery_store_postcheck_v1": _postcheck_semantic_errors,
        "s2_5_recovery_store_rollback_v1": _rollback_semantic_errors,
        "s2_5_recovery_anchor_entry_v1": _anchor_semantic_errors,
    }[artifact["schema_version"]](artifact)


def _root_reasons(observed: Any) -> list[str]:
    if not isinstance(observed, dict):
        return ["state-root observation is not an object"]
    reasons: list[str] = []
    if observed.get("is_directory") is not True:
        reasons.append("state root is not a directory")
    if observed.get("is_symlink") is True:
        reasons.append("state root is a symlink")
    if observed.get("uid") != PROFILE_UID or observed.get("gid") != PROFILE_GID:
        reasons.append("state root owner differs from the fixed uid=1000 user profile")
    if str(observed.get("mode")) != ROOT_MODE:
        reasons.append("state root mode is not 0700")
    if not _integer(observed.get("device")):
        reasons.append("state root device is not bound")
    if not _integer(observed.get("inode"), minimum=1):
        reasons.append("state root inode is not bound")
    if not _integer(observed.get("nlink"), minimum=1):
        reasons.append("state root link count is invalid")
    if observed.get("fd") is None:
        reasons.append("state root directory descriptor is absent")
    return reasons


def _root_identity(observed: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_path": DISPOSABLE_STATE_ROOT,
        "device": int(observed["device"]),
        "inode": int(observed["inode"]),
        "mode": str(observed["mode"]),
        "uid": int(observed["uid"]),
        "gid": int(observed["gid"]),
        "nlink": int(observed["nlink"]),
        "is_directory": True,
    }


def _file_reasons(
    observed: Any, *, basename: str, expected_device: int
) -> list[str]:
    if not isinstance(observed, dict):
        return [f"{basename} observation is not an object"]
    reasons: list[str] = []
    if observed.get("is_regular_file") is not True:
        reasons.append(f"{basename} is not a regular file")
    if observed.get("uid") != PROFILE_UID or observed.get("gid") != PROFILE_GID:
        reasons.append(f"{basename} owner differs from the fixed uid=1000 user profile")
    if str(observed.get("mode")) != FILE_MODE:
        reasons.append(f"{basename} mode is not 0600")
    if observed.get("nlink") != 1:
        reasons.append(f"{basename} link count is not one")
    if observed.get("device") != expected_device:
        reasons.append(f"{basename} is not on the bound state-root device")
    if not _integer(observed.get("inode"), minimum=1):
        reasons.append(f"{basename} inode is not bound")
    if not isinstance(observed.get("bytes"), bytes):
        reasons.append(f"{basename} bytes are absent")
    return reasons


def _temp_reasons(observed: Any, *, expected_device: int) -> list[str]:
    if not isinstance(observed, dict):
        return ["manifest temp observation is not an object"]
    facts = dict(observed)
    facts.setdefault("bytes", b"")
    return _file_reasons(
        facts, basename=MANIFEST_TEMP_BASENAME, expected_device=expected_device
    )


def _file_identity(observed: dict[str, Any]) -> dict[str, Any]:
    return {
        "device": observed["device"],
        "inode": observed["inode"],
        "mode": observed["mode"],
        "uid": observed["uid"],
        "gid": observed["gid"],
        "nlink": observed["nlink"],
        "is_regular_file": observed["is_regular_file"],
    }


def _decode_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise RecoveryStoreError(f"{label}_json_invalid") from error
    if not isinstance(value, dict):
        raise RecoveryStoreError(f"{label}_is_not_an_object")
    return value


def _journal_errors(
    journal: dict[str, Any], *, start_id: str
) -> list[str]:
    errors: list[str] = []
    if journal.get("schema_version") != "s2_5_start_journal_v2_informal":
        errors.append("journal schema_version is not v2")
    if journal.get("start_id") != start_id:
        errors.append("journal embedded start_id differs from its basename")
    if journal.get("append_only") is not True:
        errors.append("journal is not append-only")
    if journal.get("integrity_broken") is not False:
        errors.append("journal records a sticky broken-integrity latch")
    if journal.get("prior_payload_digest") is not None:
        errors.append("journal retains a prior broken-payload digest")
    if journal.get("self_digest") != central_validator.artifact_self_digest(journal):
        errors.append("journal self_digest does not re-derive")
    history = journal.get("history")
    if not isinstance(history, list) or not history:
        errors.append("journal history is absent or empty")
        return errors
    errors.extend(attestation.s2_5_journal_entry_errors(history))
    tail = history[-1] if isinstance(history[-1], dict) else {}
    if journal.get("state") != tail.get("state"):
        errors.append("journal top-level state differs from its tail")
    if journal.get("updated_at") != tail.get("updated_at"):
        errors.append("journal top-level timestamp differs from its tail")
    if journal.get("state") not in _JOURNAL_TERMINAL_STATES:
        errors.append("journal state is not terminal")
    replay_head = journal.get("replay_ledger_head")
    if replay_head is not None and (
        not isinstance(replay_head, dict)
        or set(replay_head) != {"entry_count", "tail_entry_digest"}
        or not _integer(replay_head.get("entry_count"), minimum=1)
        or not isinstance(replay_head.get("tail_entry_digest"), str)
        or _DIGEST_RE.fullmatch(replay_head["tail_entry_digest"]) is None
    ):
        errors.append("journal replay-ledger head is malformed")
    return errors


def _ledger_errors(ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if ledger.get("schema_version") != "s2_5_authorization_replay_ledger_v1":
        errors.append("replay ledger schema_version is invalid")
    expected_path = f"{DISPOSABLE_STATE_ROOT}/{REPLAY_LEDGER_BASENAME}"
    if ledger.get("ledger_path") != expected_path:
        errors.append("replay ledger path differs from the code-owned path")
    if ledger.get("append_only") is not True:
        errors.append("replay ledger is not append-only")
    if ledger.get("self_digest") != central_validator.artifact_self_digest(ledger):
        errors.append("replay ledger self_digest does not re-derive")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return errors + ["replay ledger entries are not an array"]
    errors.extend(attestation.s2_5_replay_ledger_entry_errors(entries))
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"replay ledger entry {index} is not an object")
            continue
        authorization_id = entry.get("authorization_id")
        if not isinstance(authorization_id, str) or not _AUTHORIZATION_RE.fullmatch(
            authorization_id
        ):
            errors.append(f"replay ledger entry {index} authorization id is invalid")
        elif authorization_id in seen:
            errors.append("replay ledger contains a duplicate authorization id")
        else:
            seen.add(authorization_id)
        start_id = entry.get("start_id")
        if not isinstance(start_id, str) or _JOURNAL_RE.fullmatch(
            f"{start_id}.journal.json"
        ) is None:
            errors.append(f"replay ledger entry {index} start id is invalid")
    return errors


def _journal_ledger_coverage_errors(
    journals: list[dict[str, Any]], ledger_entries: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    for journal in journals:
        start_id = journal["start_id"]
        head = journal.get("replay_ledger_head")
        start_entry_indexes = [
            index
            for index, entry in enumerate(ledger_entries)
            if entry.get("start_id") == start_id
        ]
        if start_entry_indexes and not isinstance(head, dict):
            errors.append(
                f"terminal journal {start_id} does not pin its replay-ledger consumption"
            )
            continue
        if not isinstance(head, dict):
            continue
        count = head["entry_count"]
        if (
            len(ledger_entries) < count
            or ledger_entries[count - 1].get("entry_digest")
            != head["tail_entry_digest"]
            or any(index >= count for index in start_entry_indexes)
        ):
            errors.append(
                f"terminal journal {start_id} replay-ledger head is not covered"
            )
    return errors


def _same_root(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _root_identity(left) == _root_identity(right)


class S2_5RecoveryStore:
    """Atomic local manifest writer over one injected, capability-narrow driver."""

    def __init__(self, driver: Any) -> None:
        if driver is None:
            raise RecoveryStoreError("recovery_store_driver_absent")
        self._driver = driver

    def _close(self, fd: Any) -> None:
        if fd is None:
            return
        try:
            self._driver.close(fd=fd)
        except Exception:
            pass

    def _open_root(self) -> dict[str, Any]:
        try:
            observed = self._driver.open_parent_directory(
                path=DISPOSABLE_STATE_ROOT, flags=PARENT_OPEN_FLAGS
            )
        except Exception as error:
            raise RecoveryStoreError(
                "state_root_open_failed", type(error).__name__
            ) from error
        reasons = _root_reasons(observed)
        if reasons:
            if isinstance(observed, dict):
                self._close(observed.get("fd"))
            raise RecoveryStoreError("state_root_precheck_failed", "; ".join(reasons))
        return observed

    def _read(
        self, parent_fd: Any, root: dict[str, Any], basename: str
    ) -> dict[str, Any] | None:
        try:
            observed = self._driver.read_file_observation(
                parent_fd=parent_fd, basename=basename, flags=READ_OPEN_FLAGS
            )
        except Exception as error:
            raise RecoveryStoreError(
                "state_file_read_failed", type(error).__name__
            ) from error
        if observed is None:
            return None
        reasons = _file_reasons(
            observed, basename=basename, expected_device=root["device"]
        )
        if reasons:
            raise RecoveryStoreError("state_file_precheck_failed", "; ".join(reasons))
        return observed

    def _snapshot(
        self,
        parent_fd: Any,
        root: dict[str, Any],
        *,
        permit_own_temp: bool = False,
    ) -> dict[str, Any]:
        try:
            listed = self._driver.list_basenames(parent_fd=parent_fd)
        except Exception as error:
            raise RecoveryStoreError(
                "state_root_enumeration_failed", type(error).__name__
            ) from error
        if not isinstance(listed, list) or not all(
            isinstance(name, str) and "/" not in name and name not in {"", ".", ".."}
            for name in listed
        ):
            raise RecoveryStoreError("state_root_enumeration_invalid")
        if len(set(listed)) != len(listed):
            raise RecoveryStoreError("state_root_duplicate_basename")
        names = sorted(listed)
        if MANIFEST_TEMP_BASENAME in names and not permit_own_temp:
            raise RecoveryStoreError("manifest_temp_residue_recovery_required")
        allowed_fixed = {
            MANIFEST_BASENAME,
            MANIFEST_TEMP_BASENAME,
            REPLAY_LEDGER_BASENAME,
        }
        extras = [
            name for name in names
            if name not in allowed_fixed and _JOURNAL_RE.fullmatch(name) is None
        ]
        if extras:
            raise RecoveryStoreError("unexpected_state_root_basename", ",".join(extras))

        manifest_observation = self._read(
            parent_fd, root, MANIFEST_BASENAME
        ) if MANIFEST_BASENAME in names else None
        journal_inventory: list[dict[str, Any]] = []
        journals: list[dict[str, Any]] = []
        for basename in names:
            matched = _JOURNAL_RE.fullmatch(basename)
            if matched is None:
                continue
            observed = self._read(parent_fd, root, basename)
            if observed is None:
                raise RecoveryStoreError("journal_disappeared_during_enumeration")
            journal = _decode_object(observed["bytes"], label="journal")
            journal_errors = _journal_errors(journal, start_id=matched.group(1))
            if journal_errors:
                raise RecoveryStoreError(
                    "journal_integrity_failed", "; ".join(journal_errors)
                )
            journals.append(journal)
            journal_inventory.append({
                "basename": basename,
                "start_id": matched.group(1),
                "file_digest": _raw_digest(observed["bytes"]),
                "journal_head_digest": journal["history"][-1]["entry_digest"],
            })
        journal_inventory.sort(key=lambda entry: entry["basename"])
        journal_set_digest = central_validator.canonical_digest({
            "schema_version": "s2_5_recovery_journal_set_v1",
            "entries": journal_inventory,
        })

        ledger_observation = self._read(
            parent_fd, root, REPLAY_LEDGER_BASENAME
        ) if REPLAY_LEDGER_BASENAME in names else None
        if ledger_observation is None:
            replay_ledger = {
                "basename": REPLAY_LEDGER_BASENAME,
                "present": False,
                "file_digest": None,
                "entry_count": 0,
                "head_digest": None,
            }
            ledger_authorization_ids: list[str] = []
            ledger_entries: list[dict[str, Any]] = []
        else:
            ledger = _decode_object(ledger_observation["bytes"], label="replay_ledger")
            ledger_errors = _ledger_errors(ledger)
            if ledger_errors:
                raise RecoveryStoreError(
                    "replay_ledger_integrity_failed", "; ".join(ledger_errors)
                )
            entries = ledger["entries"]
            ledger_entries = entries
            replay_ledger = {
                "basename": REPLAY_LEDGER_BASENAME,
                "present": True,
                "file_digest": _raw_digest(ledger_observation["bytes"]),
                "entry_count": len(entries),
                "head_digest": entries[-1]["entry_digest"] if entries else None,
            }
            ledger_authorization_ids = sorted(
                entry["authorization_id"] for entry in entries
            )
        coverage_errors = _journal_ledger_coverage_errors(journals, ledger_entries)
        if coverage_errors:
            raise RecoveryStoreError(
                "journal_replay_ledger_coverage_failed",
                "; ".join(coverage_errors),
            )
        identity = _root_identity(root)
        return {
            "state_root_identity": identity,
            "state_root_id": central_validator.canonical_digest(identity),
            "journal_inventory": journal_inventory,
            "journal_set_digest": journal_set_digest,
            "replay_ledger": replay_ledger,
            "_ledger_authorization_ids": ledger_authorization_ids,
            "manifest_observation": manifest_observation,
        }

    def _validate_manifest(
        self,
        manifest: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        source_head: str | None = None,
    ) -> list[str]:
        errors = validate_local_artifact(manifest)
        if manifest.get("state_root_identity") != snapshot["state_root_identity"]:
            errors.append("manifest state-root identity differs from live root")
        if manifest.get("state_root_id") != snapshot["state_root_id"]:
            errors.append("manifest state-root id differs from live root")
        expected_store_id = self._store_id(snapshot["state_root_id"])
        if manifest.get("store_id") != expected_store_id:
            errors.append("manifest store id differs from the code-owned root")
        if manifest.get("journal_inventory") != snapshot["journal_inventory"]:
            errors.append("manifest exact journal inventory differs from live root")
        if manifest.get("journal_set_digest") != snapshot["journal_set_digest"]:
            errors.append("manifest journal-set digest differs from live root")
        if manifest.get("replay_ledger") != snapshot["replay_ledger"]:
            errors.append("manifest replay-ledger head differs from live root")
        if source_head is not None and manifest.get("source_head") != source_head:
            errors.append("manifest source head differs from current source head")
        consumed = manifest.get("consumed_authorization_ids")
        if isinstance(consumed, list) and consumed != sorted(consumed):
            errors.append("manifest consumed authorization ids are not canonical-sorted")
        if consumed != snapshot["_ledger_authorization_ids"]:
            errors.append(
                "manifest consumed authorization ids differ from the validated replay ledger"
            )
        return errors

    @staticmethod
    def _store_id(state_root_id: str) -> str:
        digest = central_validator.canonical_digest({
            "profile_id": PROFILE_ID,
            "state_root_id": state_root_id,
        })
        return "s2-5-store-" + digest.removeprefix("sha256:")

    def _existing_manifest(
        self,
        snapshot: dict[str, Any],
        *,
        source_head: str,
    ) -> dict[str, Any] | None:
        observed = snapshot["manifest_observation"]
        if observed is None:
            return None
        manifest = _decode_object(observed["bytes"], label="manifest")
        errors = self._validate_manifest(
            manifest,
            snapshot,
            source_head=source_head,
        )
        if errors:
            raise RecoveryStoreError(
                "manifest_integrity_failed", "; ".join(errors)
            )
        return manifest

    def _candidate(
        self,
        snapshot: dict[str, Any],
        previous: dict[str, Any] | None,
        *,
        source_head: str,
        phase: str,
        unresolved_state_digest: str | None,
        anchor_head_digest: str | None,
    ) -> dict[str, Any]:
        if phase not in {"PREPARED", "COMMITTED", "RESOLVED"}:
            raise RecoveryStoreError("manifest_phase_invalid")
        for label, value in (
            ("unresolved_state_digest", unresolved_state_digest),
            ("anchor_head_digest", anchor_head_digest),
        ):
            if value is not None and (
                not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None
            ):
                raise RecoveryStoreError(f"{label}_invalid")
        consumed_authorization_ids = snapshot["_ledger_authorization_ids"]
        candidate = {
            "schema_version": "s2_5_recovery_store_manifest_v1",
            "store_id": self._store_id(snapshot["state_root_id"]),
            "state_root_id": snapshot["state_root_id"],
            "source_head": source_head,
            "generation": 1 if previous is None else previous["generation"] + 1,
            "phase": phase,
            "previous_manifest_digest": (
                None if previous is None else previous["self_digest"]
            ),
            "unresolved_state_digest": unresolved_state_digest,
            "anchor_head_digest": anchor_head_digest,
            "consumed_authorization_ids": consumed_authorization_ids,
            "state_root_identity": snapshot["state_root_identity"],
            "journal_inventory": snapshot["journal_inventory"],
            "journal_set_digest": snapshot["journal_set_digest"],
            "replay_ledger": snapshot["replay_ledger"],
            **_COMMON,
        }
        sealed = _seal(candidate)
        errors = validate_local_artifact(sealed)
        if errors:
            raise RecoveryStoreError(
                "candidate_manifest_invalid", "; ".join(errors)
            )
        return sealed

    @staticmethod
    def _operation(phase: str) -> str:
        return {
            "PREPARED": "PREPARE",
            "COMMITTED": "PROMOTE",
            "RESOLVED": "RESOLVE",
        }[phase]

    def _intent(
        self,
        manifest: dict[str, Any],
        *,
        issued_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        intent = _seal({
            "schema_version": "s2_5_recovery_store_intent_v1",
            "store_id": manifest["store_id"],
            "state_root_id": manifest["state_root_id"],
            "source_head": manifest["source_head"],
            "operation": self._operation(manifest["phase"]),
            "expected_previous_manifest_digest": manifest[
                "previous_manifest_digest"
            ],
            "candidate_manifest_digest": manifest["self_digest"],
            "issued_at": issued_at,
            "expires_at": expires_at,
            **_COMMON,
        })
        errors = validate_local_artifact(intent)
        if errors:
            raise RecoveryStoreError("store_intent_invalid", "; ".join(errors))
        return intent

    def _recheck_root(
        self, bound_root: dict[str, Any]
    ) -> tuple[bool, dict[str, Any] | None]:
        observed: dict[str, Any] | None = None
        try:
            observed = self._open_root()
            return _same_root(bound_root, observed), observed
        except RecoveryStoreError:
            return False, observed

    def _postcheck(
        self,
        *,
        candidate: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        root: dict[str, Any] | None = None
        manifest_match = False
        manifest_identity_match = False
        parent_match = False
        temp_absent = False
        readback_digest = None
        failure_code = None
        try:
            root = self._open_root()
            snapshot = self._snapshot(root["fd"], root)
            parent_match = (
                snapshot["state_root_identity"] == candidate["state_root_identity"]
            )
            observed = snapshot["manifest_observation"]
            if observed is not None:
                readback_digest = _raw_digest(observed["bytes"])
                readback = _decode_object(observed["bytes"], label="manifest_readback")
                manifest_match = readback == candidate and not self._validate_manifest(
                    readback, snapshot, source_head=candidate["source_head"]
                )
                expected_identity = result.get("candidate_temp_identity")
                manifest_identity_match = (
                    isinstance(expected_identity, dict)
                    and _file_identity(observed) == expected_identity
                )
            else:
                failure_code = "manifest_independent_readback_missing"
            temp_absent = True
        except RecoveryStoreError:
            failure_code = "manifest_independent_readback_failed"
        finally:
            if root is not None:
                self._close(root.get("fd"))
        durability_complete = all(
            result.get(field) is True
            for field in (
                "file_fsynced",
                "atomic_replace",
                "directory_fsynced",
                "parent_identity_rechecked",
            )
        )
        if failure_code is None:
            if not durability_complete:
                failure_code = "manifest_durability_incomplete"
            elif not manifest_match:
                failure_code = "manifest_independent_readback_mismatch"
            elif not manifest_identity_match:
                failure_code = "manifest_candidate_identity_mismatch"
            elif not parent_match:
                failure_code = "manifest_parent_identity_mismatch"
            elif not temp_absent:
                failure_code = "manifest_temp_residue_present"
        status = "PASS" if (
            manifest_match
            and manifest_identity_match
            and parent_match
            and temp_absent
            and durability_complete
        ) else "RECOVERY_REQUIRED"
        postcheck = _seal({
            "schema_version": "s2_5_recovery_store_postcheck_v1",
            "result_digest": result["self_digest"],
            "manifest_digest": candidate["self_digest"],
            "readback_digest": readback_digest,
            "manifest_match": manifest_match,
            "manifest_identity_match": manifest_identity_match,
            "parent_identity_match": parent_match,
            "temp_residue_absent": temp_absent,
            "status": status,
            "failure_code": failure_code,
            **_COMMON,
        })
        errors = validate_local_artifact(postcheck)
        if errors:
            raise RecoveryStoreError("store_postcheck_invalid", "; ".join(errors))
        return postcheck

    @staticmethod
    def _rollback(
        intent: dict[str, Any],
        result: dict[str, Any],
        postcheck: dict[str, Any],
    ) -> dict[str, Any]:
        locally_safe = (
            result["status"] == "EXTERNAL_VERIFICATION_PENDING"
            and postcheck["status"] == "PASS"
        )
        rollback = _seal({
            "schema_version": "s2_5_recovery_store_rollback_v1",
            "intent_digest": intent["self_digest"],
            "result_digest": result["self_digest"],
            "status": "NOT_REQUIRED" if locally_safe else "RECOVERY_REQUIRED",
            "restored_manifest_digest": None,
            "temp_residue_absent": postcheck["temp_residue_absent"],
            "operator_action_required": not locally_safe,
            **_COMMON,
        })
        errors = validate_local_artifact(rollback)
        if errors:
            raise RecoveryStoreError("store_rollback_invalid", "; ".join(errors))
        return rollback

    def inspect(self, *, source_head: str) -> dict[str, Any]:
        """Read and validate local state; never upgrades it to externally trusted."""

        if not isinstance(source_head, str) or _HEAD_RE.fullmatch(source_head) is None:
            raise RecoveryStoreError("source_head_invalid")
        root: dict[str, Any] | None = None
        try:
            root = self._open_root()
            snapshot = self._snapshot(root["fd"], root)
            manifest = self._existing_manifest(snapshot, source_head=source_head)
            if manifest is None:
                if (
                    snapshot["journal_inventory"]
                    or snapshot["replay_ledger"]["present"]
                ):
                    raise RecoveryStoreError(
                        "manifest_missing_for_nonempty_state_root"
                    )
                return {"status": "ABSENT", "manifest": None, "reasons": []}
            return {
                "status": STATUS_UNVERIFIED,
                "manifest": manifest,
                "reasons": [
                    "the local manifest is internally consistent but has no independently "
                    "controlled append-only latest anchor"
                ],
            }
        except RecoveryStoreError as error:
            return {
                "status": STATUS_RECOVERY_REQUIRED,
                "manifest": None,
                "reasons": [error.code],
            }
        finally:
            if root is not None:
                self._close(root.get("fd"))

    def persist(
        self,
        *,
        source_head: str,
        phase: str,
        unresolved_state_digest: str | None,
        anchor_head_digest: str | None,
        issued_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        """Durably replace the local manifest and return its typed four-step chain."""

        if not isinstance(source_head, str) or _HEAD_RE.fullmatch(source_head) is None:
            raise RecoveryStoreError("source_head_invalid")
        _validate_ttl(issued_at, expires_at)
        root: dict[str, Any] | None = None
        temp_fd = None
        candidate: dict[str, Any] | None = None
        intent: dict[str, Any] | None = None
        failure_code: str | None = None
        file_fsynced = False
        atomic_replace = False
        directory_fsynced = False
        parent_identity_rechecked = False
        candidate_temp_identity: dict[str, Any] | None = None
        try:
            root = self._open_root()
            try:
                before = self._snapshot(root["fd"], root)
            except RecoveryStoreError as precheck_error:
                if precheck_error.code != "manifest_temp_residue_recovery_required":
                    raise
                # A restarted process must be able to issue a typed recovery chain
                # without trusting or deleting the stranded temp.  Re-enumerate while
                # explicitly excluding only the code-owned temp basename, derive the
                # candidate/intent from the remaining verified state, then carry the
                # original residue failure into result/postcheck/rollback.
                before = self._snapshot(
                    root["fd"], root, permit_own_temp=True
                )
                previous = self._existing_manifest(
                    before,
                    source_head=source_head,
                )
                if previous is None:
                    raise RecoveryStoreError("verified_external_bootstrap_required")
                candidate = self._candidate(
                    before,
                    previous,
                    source_head=source_head,
                    phase=phase,
                    unresolved_state_digest=unresolved_state_digest,
                    anchor_head_digest=anchor_head_digest,
                )
                intent = self._intent(
                    candidate, issued_at=issued_at, expires_at=expires_at
                )
                raise precheck_error
            previous = self._existing_manifest(
                before,
                source_head=source_head,
            )
            if previous is None:
                raise RecoveryStoreError("verified_external_bootstrap_required")
            candidate = self._candidate(
                before,
                previous,
                source_head=source_head,
                phase=phase,
                unresolved_state_digest=unresolved_state_digest,
                anchor_head_digest=anchor_head_digest,
            )
            intent = self._intent(
                candidate, issued_at=issued_at, expires_at=expires_at
            )
            try:
                temp = self._driver.create_temp_file(
                    parent_fd=root["fd"],
                    basename=MANIFEST_TEMP_BASENAME,
                    flags=TEMP_OPEN_FLAGS,
                    mode=FILE_MODE_BITS,
                )
            except FileExistsError as error:
                raise RecoveryStoreError(
                    "manifest_temp_residue_recovery_required"
                ) from error
            except RecoveryStoreCrash:
                raise
            except Exception as error:
                raise RecoveryStoreError(
                    "manifest_temp_create_failed", type(error).__name__
                ) from error
            if isinstance(temp, dict):
                temp_fd = temp.get("fd")
            temp_reasons = _temp_reasons(
                temp, expected_device=root["device"]
            )
            if temp_reasons:
                raise RecoveryStoreError(
                    "manifest_temp_precheck_failed", "; ".join(temp_reasons)
                )
            candidate_temp_identity = _file_identity(temp)
            payload = _canonical_bytes(candidate)
            try:
                written = self._driver.write_bytes(fd=temp_fd, payload=payload)
            except RecoveryStoreCrash:
                raise
            except Exception as error:
                raise RecoveryStoreError(
                    "manifest_temp_write_failed", type(error).__name__
                ) from error
            if not _integer(written) or written != len(payload):
                raise RecoveryStoreError("manifest_temp_write_short")
            try:
                self._driver.fsync_file(fd=temp_fd)
            except RecoveryStoreCrash:
                raise
            except Exception as error:
                raise RecoveryStoreError(
                    "manifest_temp_fsync_failed", type(error).__name__
                ) from error
            file_fsynced = True

            parent_match, re_resolved = self._recheck_root(root)
            if re_resolved is not None:
                self._close(re_resolved.get("fd"))
            if not parent_match:
                raise RecoveryStoreError("state_root_replaced_before_atomic_replace")
            parent_identity_rechecked = True
            current = self._snapshot(root["fd"], root, permit_own_temp=True)
            if (
                current["state_root_identity"] != before["state_root_identity"]
                or current["journal_inventory"] != before["journal_inventory"]
                or current["journal_set_digest"] != before["journal_set_digest"]
                or current["replay_ledger"] != before["replay_ledger"]
            ):
                raise RecoveryStoreError("state_root_changed_during_manifest_write")
            try:
                temp_readback = self._read(
                    root["fd"], root, MANIFEST_TEMP_BASENAME
                )
            except RecoveryStoreError as error:
                raise RecoveryStoreError(
                    "manifest_temp_identity_changed"
                ) from error
            if (
                temp_readback is None
                or temp_readback.get("device") != temp.get("device")
                or temp_readback.get("inode") != temp.get("inode")
                or temp_readback.get("bytes") != payload
            ):
                raise RecoveryStoreError("manifest_temp_identity_changed")
            current_manifest = current["manifest_observation"]
            current_digest = None
            if current_manifest is not None:
                current_payload = _decode_object(
                    current_manifest["bytes"], label="current_manifest"
                )
                current_digest = current_payload.get("self_digest")
            if current_digest != candidate["previous_manifest_digest"]:
                raise RecoveryStoreError("manifest_changed_during_manifest_write")

            try:
                self._driver.atomic_replace(
                    parent_fd=root["fd"],
                    from_basename=MANIFEST_TEMP_BASENAME,
                    to_basename=MANIFEST_BASENAME,
                )
            except RecoveryStoreCrash:
                raise
            except Exception as error:
                raise RecoveryStoreError(
                    "manifest_atomic_replace_failed", type(error).__name__
                ) from error
            atomic_replace = True
            try:
                self._driver.fsync_parent_dir(fd=root["fd"])
            except RecoveryStoreCrash:
                raise
            except Exception as error:
                raise RecoveryStoreError(
                    "manifest_directory_fsync_failed", type(error).__name__
                ) from error
            directory_fsynced = True
        except RecoveryStoreCrash:
            raise
        except RecoveryStoreError as error:
            if candidate is None or intent is None:
                raise
            failure_code = error.code
        except Exception as error:  # noqa: BLE001 - injected driver failure is typed
            if candidate is None or intent is None:
                raise RecoveryStoreError(
                    "store_driver_failed_before_intent", type(error).__name__
                ) from error
            failure_code = "store_driver_failure_" + type(error).__name__
        finally:
            self._close(temp_fd)
            if root is not None:
                self._close(root.get("fd"))

        if candidate is None or intent is None:
            raise RecoveryStoreError("store_transaction_lost_its_typed_intent")
        local_commit_complete = failure_code is None
        result = _seal({
            "schema_version": "s2_5_recovery_store_result_v1",
            "intent_digest": intent["self_digest"],
            "status": (
                "EXTERNAL_VERIFICATION_PENDING"
                if local_commit_complete else "RECOVERY_REQUIRED"
            ),
            "manifest_digest": candidate["self_digest"],
            "file_fsynced": file_fsynced,
            "atomic_replace": atomic_replace,
            "directory_fsynced": directory_fsynced,
            "parent_identity_rechecked": parent_identity_rechecked,
            "candidate_temp_identity": candidate_temp_identity,
            "failure_code": (
                STATUS_UNVERIFIED if local_commit_complete else failure_code
            ),
            **_COMMON,
        })
        result_errors = validate_local_artifact(result)
        if result_errors:
            raise RecoveryStoreError(
                "store_result_invalid", "; ".join(result_errors)
            )
        postcheck = self._postcheck(candidate=candidate, result=result)
        rollback = self._rollback(intent, result, postcheck)
        return {
            "status": (
                STATUS_UNVERIFIED
                if local_commit_complete and postcheck["status"] == "PASS"
                else STATUS_RECOVERY_REQUIRED
            ),
            "manifest": candidate,
            "intent": intent,
            "result": result,
            "postcheck": postcheck,
            "rollback": rollback,
        }
