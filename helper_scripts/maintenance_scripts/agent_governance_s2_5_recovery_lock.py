#!/usr/bin/env python3
"""Recovery-only fixed-profile S2.4 -> S2.5 dual-lock leaf.

This leaf deliberately does not reuse the ordinary S2.4 install-lock token.
It owns a separate pair of disposable recovery locks outside the replaceable
state root and exposes only an injected filesystem/flock protocol.  It cannot
execute a process, choose a path, unlink a lock, or claim production runtime.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (Path(__file__).resolve().parent, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
from agent_governance_s2_5_disposable_profile import (  # noqa: E402
    DISPOSABLE_LOCK_ROOT,
    DISPOSABLE_STATE_ROOT,
    PROFILE_GID,
    PROFILE_ID,
    PROFILE_UID,
    S2_4_RECOVERY_INSTALL_FENCE_LOCK_BASENAME,
    S2_4_RECOVERY_INSTALL_FENCE_LOCK_PATH,
    S2_5_RECOVERY_LIFECYCLE_LOCK_BASENAME,
    S2_5_RECOVERY_LIFECYCLE_LOCK_PATH,
)


LOCK_PARENT_OPEN_FLAGS = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
LOCK_FILE_OPEN_FLAGS = ("O_NOFOLLOW", "O_CREAT", "O_CLOEXEC")
LOCK_EXISTING_FILE_OPEN_FLAGS = ("O_NOFOLLOW", "O_CLOEXEC")
LOCK_ROOT_MODE = "0700"
LOCK_FILE_MODE = "0600"
LOCK_FILE_MODE_BITS = 0o600
LOCK_ORDER = ("S2.4", "S2.5")
LOCK_PATHS = (
    S2_4_RECOVERY_INSTALL_FENCE_LOCK_PATH,
    S2_5_RECOVERY_LIFECYCLE_LOCK_PATH,
)
LOCK_BASENAMES = (
    S2_4_RECOVERY_INSTALL_FENCE_LOCK_BASENAME,
    S2_5_RECOVERY_LIFECYCLE_LOCK_BASENAME,
)

FORBIDDEN_LOCK_METHODS = (
    "chmod",
    "chown",
    "remove",
    "rename",
    "rmdir",
    "truncate",
    "unlink",
    "unlink_lock",
)

STATUS_ACQUIRED = "RECOVERY_DUAL_LOCK_ACQUIRED"
STATUS_CONTENDED = "RECOVERY_DUAL_LOCK_CONTENDED"
STATUS_REJECTED = "REJECTED"
STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"

_HEAD_RE_LENGTH = 40
_SCHEMA_DIR = REPO_ROOT / ".codex" / "schemas"
_LOCAL_SCHEMAS = frozenset({
    "s2_5_recovery_lock_intent_v1",
    "s2_5_recovery_lock_result_v1",
    "s2_5_recovery_lock_postcheck_v1",
    "s2_5_recovery_lock_rollback_v1",
})
_COMMON = {
    "side_effect_class": "DISPOSABLE_TEST",
    "target_class": "disposable_systemd",
    "target_profile_id": PROFILE_ID,
    "evidence_class": "LOCAL_REPRODUCIBLE",
    "runtime_observed": False,
    "production_effect": False,
    "production_authority": False,
    "production_effect_count": 0,
}


class RecoveryDualLockError(RuntimeError):
    """Typed fail-closed dual-lock contract error."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class RecoveryDualLockDriver(Protocol):
    """Narrow lock driver; destructive methods are structurally forbidden."""

    def open_parent_directory(
        self, *, path: str, flags: tuple[str, ...]
    ) -> dict[str, Any]: ...

    def openat_lock_file(
        self,
        *,
        parent_fd: Any,
        basename: str,
        flags: tuple[str, ...],
        mode: int,
    ) -> dict[str, Any]: ...

    def fstat_lock_file(self, *, fd: Any) -> dict[str, Any]: ...

    def openat_existing_lock_file(
        self,
        *,
        parent_fd: Any,
        basename: str,
        flags: tuple[str, ...],
    ) -> dict[str, Any]: ...

    def flock_exclusive_nonblocking(self, *, fd: Any) -> bool: ...

    def close(self, *, fd: Any) -> None: ...


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["self_digest"] = central_validator.artifact_self_digest(sealed)
    errors = validate_local_artifact(sealed)
    if errors:
        raise RecoveryDualLockError(
            "recovery_lock_receipt_invalid",
            "; ".join(errors),
        )
    return sealed


@lru_cache(maxsize=None)
def _local_schema(schema_version: str) -> dict[str, Any]:
    if schema_version not in _LOCAL_SCHEMAS:
        raise RecoveryDualLockError("local_schema_version_unknown")
    try:
        schema = json.loads(
            (_SCHEMA_DIR / f"{schema_version}.schema.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError) as error:
        raise RecoveryDualLockError(
            "local_schema_unreadable", type(error).__name__
        ) from error
    if not isinstance(schema, dict):
        raise RecoveryDualLockError("local_schema_not_object")
    return schema


def validate_local_artifact(artifact: Any) -> list[str]:
    """Validate one recursively closed recovery-lock receipt."""

    if not isinstance(artifact, dict):
        return ["recovery-lock artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if schema_version not in _LOCAL_SCHEMAS:
        return ["recovery-lock schema_version is unknown"]
    schema = _local_schema(schema_version)
    errors = schema_subset_errors(artifact, schema, schema)
    if artifact.get("self_digest") != central_validator.artifact_self_digest(
        artifact
    ):
        errors.append("recovery-lock self_digest does not re-derive")
    for key, expected in _COMMON.items():
        if artifact.get(key) != expected:
            errors.append(f"recovery-lock {key} differs from fixed profile")
    if schema_version == "s2_5_recovery_lock_intent_v1":
        if artifact.get("state_root") != DISPOSABLE_STATE_ROOT:
            errors.append("recovery-lock intent state root differs from fixed profile")
        if artifact.get("lock_root") != DISPOSABLE_LOCK_ROOT:
            errors.append("recovery-lock intent lock root differs from fixed profile")
        if artifact.get("lock_order") != list(LOCK_ORDER):
            errors.append("recovery-lock intent order is not S2.4 then S2.5")
        if artifact.get("lock_paths") != list(LOCK_PATHS):
            errors.append("recovery-lock intent paths differ from fixed profile")
    elif schema_version == "s2_5_recovery_lock_result_v1":
        if artifact.get("acquisition_order") != list(LOCK_ORDER):
            errors.append("recovery-lock result order is not S2.4 then S2.5")
        if artifact.get("lock_files_unlinked") is not False:
            errors.append("recovery-lock result cannot claim lock unlink")
        status = artifact.get("status")
        if status == STATUS_ACQUIRED and (
            artifact.get("s2_4_lock_acquired") is not True
            or artifact.get("s2_5_lock_acquired") is not True
            or artifact.get("failure_code") is not None
        ):
            errors.append("acquired result requires both locks and no failure")
        if status != STATUS_ACQUIRED:
            if (
                artifact.get("s2_4_lock_acquired") is True
                or artifact.get("s2_5_lock_acquired") is True
            ):
                errors.append("non-acquired result cannot claim a held lock")
            if (
                not isinstance(artifact.get("failure_code"), str)
                or not artifact.get("failure_code")
            ):
                errors.append("non-acquired result requires a typed failure")
    elif schema_version == "s2_5_recovery_lock_postcheck_v1":
        if artifact.get("status") == "PASS" and (
            artifact.get("both_locks_held") is not True
            or artifact.get("lock_chain_digest") is None
            or artifact.get("failure_code") is not None
        ):
            errors.append("PASS postcheck requires live dual-lock chain")
        expected_authority = (
            artifact.get("status") == "PASS"
            and artifact.get("session_class") == "FIXED_POSIX_RECOVERY_SESSION"
        )
        if artifact.get("store_write_authority") is not expected_authority:
            errors.append("store write authority contradicts session class or status")
        if artifact.get("status") != "PASS" and artifact.get("both_locks_held") is True:
            errors.append("non-PASS postcheck cannot claim both locks held")
        if artifact.get("lock_files_unlinked") is not False:
            errors.append("recovery-lock postcheck cannot claim lock unlink")
    else:
        if artifact.get("release_order") != ["S2.5", "S2.4"]:
            errors.append("recovery-lock release order is not S2.5 then S2.4")
        if artifact.get("lock_files_unlinked") is not False:
            errors.append("recovery-lock rollback cannot claim lock unlink")
        status = artifact.get("status")
        s2_5_attempted = artifact.get("s2_5_release_attempted")
        s2_5_released = artifact.get("s2_5_released")
        s2_4_attempted = artifact.get("s2_4_release_attempted")
        s2_4_released = artifact.get("s2_4_released")
        failure_code = artifact.get("failure_code")
        if status == "NOT_REQUIRED" and (
            s2_5_attempted is not False
            or s2_5_released is not False
            or s2_4_attempted is not False
            or s2_4_released is not False
            or failure_code is not None
        ):
            errors.append("NOT_REQUIRED rollback forbids release claims or failure")
        if status == "RELEASED_AFTER_PARTIAL_ACQUIRE" and (
            s2_5_attempted is not False
            or s2_5_released is not False
            or s2_4_attempted is not True
            or s2_4_released is not True
            or artifact.get("session_closed") is not True
            or failure_code is not None
        ):
            errors.append("partial-acquire rollback requires only S2.4 release")
        if status == "RELEASED" and (
            s2_5_attempted is not True
            or s2_5_released is not True
            or s2_4_attempted is not True
            or s2_4_released is not True
            or artifact.get("session_closed") is not True
            or failure_code is not None
        ):
            errors.append("RELEASED rollback requires reverse release and session close")
        if status == "RECOVERY_REQUIRED" and (
            artifact.get("session_closed") is True
            or not isinstance(failure_code, str)
            or not failure_code
        ):
            errors.append("recovery rollback must retain an unclosed failed session")
        if s2_5_released is True and s2_5_attempted is not True:
            errors.append("S2.5 release cannot succeed without an attempt")
        if s2_4_released is True and s2_4_attempted is not True:
            errors.append("S2.4 release cannot succeed without an attempt")
    return errors


def _chain_digest(intent: dict[str, Any], result: dict[str, Any]) -> str:
    return central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_lock_chain_v1",
        "intent_digest": intent["self_digest"],
        "result_digest": result["self_digest"],
        "lock_order": list(LOCK_ORDER),
        "lock_paths": list(LOCK_PATHS),
    })


def _valid_head(source_head: Any) -> bool:
    return (
        type(source_head) is str
        and len(source_head) == _HEAD_RE_LENGTH
        and all(character in "0123456789abcdef" for character in source_head)
    )


def assert_no_recovery_lock_destructive_surface(driver: Any) -> list[str]:
    """Reject the complete hostile method shape before touching the driver."""

    return [
        f"recovery dual-lock driver exposes forbidden method {name}"
        for name in FORBIDDEN_LOCK_METHODS
        if callable(getattr(driver, name, None))
    ]


def _root_reasons(observed: Any) -> list[str]:
    if not isinstance(observed, dict):
        return ["lock_root_observation_not_object"]
    reasons: list[str] = []
    if observed.get("is_directory") is not True:
        reasons.append("lock_root_not_directory")
    if observed.get("is_symlink") is True:
        reasons.append("lock_root_is_symlink")
    if observed.get("uid") != PROFILE_UID or observed.get("gid") != PROFILE_GID:
        reasons.append("lock_root_owner_mismatch")
    if str(observed.get("mode")) != LOCK_ROOT_MODE:
        reasons.append("lock_root_mode_mismatch")
    if not isinstance(observed.get("device"), int):
        reasons.append("lock_root_device_unbound")
    if not isinstance(observed.get("inode"), int):
        reasons.append("lock_root_inode_unbound")
    if observed.get("fd") is None:
        reasons.append("lock_root_fd_absent")
    return reasons


def _root_identity(observed: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_path": DISPOSABLE_LOCK_ROOT,
        "device": observed["device"],
        "inode": observed["inode"],
        "mode": str(observed["mode"]),
        "uid": observed["uid"],
        "gid": observed["gid"],
        "is_directory": True,
    }


def _file_reasons(observed: Any, *, expected_device: Any) -> list[str]:
    if not isinstance(observed, dict):
        return ["lock_file_observation_not_object"]
    reasons: list[str] = []
    if observed.get("is_regular_file") is not True:
        reasons.append("lock_file_not_regular")
    if observed.get("uid") != PROFILE_UID or observed.get("gid") != PROFILE_GID:
        reasons.append("lock_file_owner_mismatch")
    if str(observed.get("mode")) != LOCK_FILE_MODE:
        reasons.append("lock_file_mode_mismatch")
    if observed.get("nlink") != 1:
        reasons.append("lock_file_link_count_mismatch")
    if observed.get("device") != expected_device:
        reasons.append("lock_file_device_mismatch")
    if not isinstance(observed.get("inode"), int):
        reasons.append("lock_file_inode_unbound")
    return reasons


def _close(driver: Any, fd: Any) -> bool:
    if fd is None:
        return True
    try:
        driver.close(fd=fd)
    except Exception:
        return False
    return True


def _reresolve_root(driver: Any, bound: dict[str, Any]) -> list[str]:
    observed = driver.open_parent_directory(
        path=DISPOSABLE_LOCK_ROOT,
        flags=LOCK_PARENT_OPEN_FLAGS,
    )
    reasons: list[str] = []
    try:
        reasons = _root_reasons(observed)
        if not reasons and _root_identity(observed) != bound:
            reasons.append("lock_root_replaced")
        return reasons
    finally:
        if (
            isinstance(observed, dict)
            and not _close(driver, observed.get("fd"))
        ):
            reasons.append("lock_root_probe_close_failed")


def _intent(source_head: str, *, session_class: str) -> dict[str, Any]:
    return _seal({
        "schema_version": "s2_5_recovery_lock_intent_v1",
        "source_head": source_head,
        "operation": "ACQUIRE_RECOVERY_DUAL_LOCK",
        "session_class": session_class,
        "state_root": DISPOSABLE_STATE_ROOT,
        "lock_root": DISPOSABLE_LOCK_ROOT,
        "lock_order": list(LOCK_ORDER),
        "lock_paths": list(LOCK_PATHS),
        **_COMMON,
    })


def _result(
    intent: dict[str, Any],
    *,
    status: str,
    s2_4_acquired: bool,
    s2_5_acquired: bool,
    first_released: bool,
    driver_engaged: bool,
    failure_code: str | None,
    session_class: str,
) -> dict[str, Any]:
    return _seal({
        "schema_version": "s2_5_recovery_lock_result_v1",
        "intent_digest": intent["self_digest"],
        "status": status,
        "session_class": session_class,
        "acquisition_order": list(LOCK_ORDER),
        "s2_4_lock_acquired": s2_4_acquired,
        "s2_5_lock_acquired": s2_5_acquired,
        "first_lock_released_after_second_failure": first_released,
        "lock_files_unlinked": False,
        "driver_engaged": driver_engaged,
        "failure_code": failure_code,
        **_COMMON,
    })


def _postcheck(
    result: dict[str, Any],
    *,
    chain_digest: str | None,
    session_class: str,
    both_locks_held: bool,
    failure_code: str | None,
) -> dict[str, Any]:
    if both_locks_held:
        status = "PASS"
    elif result["status"] in {STATUS_PENDING, STATUS_REJECTED, STATUS_CONTENDED}:
        status = "NOT_PERFORMED"
    else:
        status = "RECOVERY_REQUIRED"
    return _seal({
        "schema_version": "s2_5_recovery_lock_postcheck_v1",
        "result_digest": result["self_digest"],
        "status": status,
        "lock_chain_digest": chain_digest,
        "session_class": session_class,
        "store_write_authority": (
            both_locks_held and session_class == "FIXED_POSIX_RECOVERY_SESSION"
        ),
        "both_locks_held": both_locks_held,
        "lock_files_unlinked": False,
        "failure_code": failure_code,
        **_COMMON,
    })


def _rollback(
    intent: dict[str, Any],
    result: dict[str, Any],
    *,
    status: str,
    s2_5_attempted: bool,
    s2_5_released: bool,
    s2_4_attempted: bool,
    s2_4_released: bool,
    session_closed: bool,
    failure_code: str | None,
) -> dict[str, Any]:
    return _seal({
        "schema_version": "s2_5_recovery_lock_rollback_v1",
        "intent_digest": intent["self_digest"],
        "result_digest": result["self_digest"],
        "status": status,
        "release_order": ["S2.5", "S2.4"],
        "s2_5_release_attempted": s2_5_attempted,
        "s2_5_released": s2_5_released,
        "s2_4_release_attempted": s2_4_attempted,
        "s2_4_released": s2_4_released,
        "session_closed": session_closed,
        "lock_files_unlinked": False,
        "failure_code": failure_code,
        **_COMMON,
    })


def _outcome_without_lease(
    intent: dict[str, Any],
    result: dict[str, Any],
    *,
    rollback: dict[str, Any],
) -> dict[str, Any]:
    postcheck = _postcheck(
        result,
        chain_digest=None,
        session_class=result["session_class"],
        both_locks_held=False,
        failure_code=result["failure_code"],
    )
    return {
        "status": result["status"],
        "intent": intent,
        "result": result,
        "postcheck": postcheck,
        "rollback": rollback,
    }


def _file_identity(observed: dict[str, Any]) -> dict[str, Any]:
    return {
        key: observed[key]
        for key in ("device", "inode", "mode", "uid", "gid", "nlink")
    }


def _lease_binding(lease: dict[str, Any]) -> dict[str, str]:
    return {
        "recovery_lock_intent_digest": lease["intent_digest"],
        "recovery_lock_result_digest": lease["result_digest"],
        "recovery_lock_postcheck_digest": lease["postcheck_digest"],
        "recovery_lock_chain_digest": lease["lock_chain_digest"],
    }


def _verify_lease(
    lease: Any,
    *,
    driver: Any,
    source_head: str,
    require_transaction: bool,
    expected_binding: dict[str, str] | None = None,
) -> dict[str, str]:
    if (
        not isinstance(lease, dict)
        or lease.get("driver") is not driver
        or lease.get("source_head") != source_head
        or lease.get("closed") is True
    ):
        raise RecoveryDualLockError("fixed_recovery_session_invalid")
    if require_transaction and lease.get("transaction_active") is not True:
        raise RecoveryDualLockError("fixed_recovery_transaction_inactive")
    held_probe = getattr(driver, "lock_is_held", None)
    existing_probe = getattr(driver, "openat_existing_lock_file", None)
    failures: list[str] = []
    if not callable(held_probe):
        failures.append("lock_held_probe_absent")
    if not callable(existing_probe):
        failures.append("lock_existing_probe_absent")
    root: dict[str, Any] | None = None
    try:
        root = driver.open_parent_directory(
            path=DISPOSABLE_LOCK_ROOT,
            flags=LOCK_PARENT_OPEN_FLAGS,
        )
        reasons = _root_reasons(root)
        if not reasons and _root_identity(root) != lease["root_identity"]:
            reasons.append("lock_root_replaced")
        failures.extend(reasons)
        if not reasons and callable(existing_probe):
            for label, basename in zip(("s2_4", "s2_5"), LOCK_BASENAMES):
                held_fd = lease[f"{label}_fd"]
                try:
                    held = driver.fstat_lock_file(fd=held_fd)
                    held_reasons = _file_reasons(
                        held,
                        expected_device=lease["root_identity"]["device"],
                    )
                    failures.extend(held_reasons)
                    if (
                        not held_reasons
                        and _file_identity(held) != lease[f"{label}_identity"]
                    ):
                        failures.append(f"{label}_lock_identity_changed")
                    if callable(held_probe) and held_probe(fd=held_fd) is not True:
                        failures.append(f"{label}_lock_not_held")
                except Exception as error:
                    failures.append(
                        f"{label}_held_lock_probe_{type(error).__name__}"
                    )
                probe_fd = None
                try:
                    opened = existing_probe(
                        parent_fd=root["fd"],
                        basename=basename,
                        flags=LOCK_EXISTING_FILE_OPEN_FLAGS,
                    )
                    probe_fd = (
                        opened.get("fd") if isinstance(opened, dict) else None
                    )
                    if probe_fd is None:
                        failures.append(f"{label}_lock_path_fd_absent")
                        continue
                    path_observed = driver.fstat_lock_file(fd=probe_fd)
                    path_reasons = _file_reasons(
                        path_observed,
                        expected_device=lease["root_identity"]["device"],
                    )
                    failures.extend(path_reasons)
                    if (
                        not path_reasons
                        and _file_identity(path_observed)
                        != lease[f"{label}_identity"]
                    ):
                        failures.append(f"{label}_lock_path_identity_changed")
                except Exception as error:
                    failures.append(
                        f"{label}_lock_path_probe_{type(error).__name__}"
                    )
                finally:
                    if probe_fd is not None and not _close(driver, probe_fd):
                        failures.append(f"{label}_lock_path_probe_close_failed")
    except Exception as error:
        failures.append("lock_root_probe_" + type(error).__name__)
    finally:
        if (
            isinstance(root, dict)
            and not _close(driver, root.get("fd"))
        ):
            failures.append("lock_root_probe_close_failed")
    if failures:
        raise RecoveryDualLockError(failures[0], ";".join(failures))
    binding = _lease_binding(lease)
    if expected_binding is not None and binding != expected_binding:
        raise RecoveryDualLockError("recovery_dual_lock_binding_changed")
    return binding


def _release_lease(lease: dict[str, Any]) -> dict[str, Any]:
    intent = {"self_digest": lease["intent_digest"]}
    result = {"self_digest": lease["result_digest"]}
    if lease.get("transaction_active") is True:
        return _rollback(
            intent,
            result,
            status="RECOVERY_REQUIRED",
            s2_5_attempted=False,
            s2_5_released=False,
            s2_4_attempted=False,
            s2_4_released=False,
            session_closed=False,
            failure_code="fixed_recovery_transaction_active",
        )
    driver = lease["driver"]
    s2_5_released = _close(driver, lease["s2_5_fd"])
    s2_4_released = _close(driver, lease["s2_4_fd"])
    session_closed = s2_5_released and s2_4_released
    lease["closed"] = session_closed
    return _rollback(
        intent,
        result,
        status="RELEASED" if session_closed else "RECOVERY_REQUIRED",
        s2_5_attempted=True,
        s2_5_released=s2_5_released,
        s2_4_attempted=True,
        s2_4_released=s2_4_released,
        session_closed=session_closed,
        failure_code=(
            None if session_closed else "recovery_dual_lock_release_incomplete"
        ),
    )


def _acquire_recovery_dual_lock(
    *,
    driver: Any,
    source_head: str,
    session_class: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Internal lease acquisition; no lease is returned by a public API."""

    if not _valid_head(source_head):
        raise RecoveryDualLockError("source_head_invalid")
    if session_class not in {"SIMULATION_ONLY", "FIXED_POSIX_RECOVERY_SESSION"}:
        raise RecoveryDualLockError("session_class_invalid")
    if (
        DISPOSABLE_LOCK_ROOT == DISPOSABLE_STATE_ROOT
        or DISPOSABLE_LOCK_ROOT.startswith(DISPOSABLE_STATE_ROOT + "/")
    ):
        raise RecoveryDualLockError("lock_root_inside_replaceable_state_root")
    intent = _intent(source_head, session_class=session_class)
    if driver is None:
        result = _result(
            intent,
            status=STATUS_PENDING,
            s2_4_acquired=False,
            s2_5_acquired=False,
            first_released=False,
            driver_engaged=False,
            failure_code="fixed_posix_recovery_session_unavailable",
            session_class=session_class,
        )
        rollback = _rollback(
            intent,
            result,
            status="NOT_REQUIRED",
            s2_5_attempted=False,
            s2_5_released=False,
            s2_4_attempted=False,
            s2_4_released=False,
            session_closed=True,
            failure_code=None,
        )
        return _outcome_without_lease(intent, result, rollback=rollback), None
    hostile = assert_no_recovery_lock_destructive_surface(driver)
    if hostile:
        result = _result(
            intent,
            status=STATUS_REJECTED,
            s2_4_acquired=False,
            s2_5_acquired=False,
            first_released=False,
            driver_engaged=False,
            failure_code="driver_destructive_surface",
            session_class=session_class,
        )
        rollback = _rollback(
            intent,
            result,
            status="NOT_REQUIRED",
            s2_5_attempted=False,
            s2_5_released=False,
            s2_4_attempted=False,
            s2_4_released=False,
            session_closed=True,
            failure_code=None,
        )
        return _outcome_without_lease(intent, result, rollback=rollback), None

    parent_fd = None
    s2_4_fd = None
    s2_5_fd = None
    root_identity: dict[str, Any] | None = None
    identities: list[dict[str, Any]] = []
    status = STATUS_RECOVERY_REQUIRED
    failure_code = "recovery_lock_acquisition_failed"
    acquired = [False, False]
    acquisition_complete = False
    try:
        root = driver.open_parent_directory(
            path=DISPOSABLE_LOCK_ROOT,
            flags=LOCK_PARENT_OPEN_FLAGS,
        )
        parent_fd = root.get("fd") if isinstance(root, dict) else None
        reasons = _root_reasons(root)
        if reasons:
            status = STATUS_REJECTED
            raise RecoveryDualLockError(reasons[0])
        root_identity = _root_identity(root)
        for index, basename in enumerate(LOCK_BASENAMES):
            reasons = _reresolve_root(driver, root_identity)
            if reasons:
                status = STATUS_REJECTED
                raise RecoveryDualLockError(reasons[0])
            opened = driver.openat_lock_file(
                parent_fd=parent_fd,
                basename=basename,
                flags=LOCK_FILE_OPEN_FLAGS,
                mode=LOCK_FILE_MODE_BITS,
            )
            fd = opened.get("fd") if isinstance(opened, dict) else None
            if fd is None:
                status = STATUS_REJECTED
                raise RecoveryDualLockError("lock_file_fd_absent")
            if index == 0:
                s2_4_fd = fd
            else:
                s2_5_fd = fd
            observed = driver.fstat_lock_file(fd=fd)
            reasons = _file_reasons(
                observed,
                expected_device=root_identity["device"],
            )
            if reasons:
                status = STATUS_REJECTED
                raise RecoveryDualLockError(reasons[0])
            identities.append(_file_identity(observed))
            if driver.flock_exclusive_nonblocking(fd=fd) is not True:
                status = STATUS_CONTENDED
                raise RecoveryDualLockError(
                    f"s2_{index + 4}_recovery_lock_contended"
                )
            acquired[index] = True
        if not _close(driver, parent_fd):
            raise RecoveryDualLockError("lock_parent_close_failed")
        parent_fd = None
        acquisition_complete = True
    except RecoveryDualLockError as error:
        failure_code = error.code
    except Exception as error:
        failure_code = "recovery_lock_driver_" + type(error).__name__

    if not acquisition_complete:
        s2_5_closed = _close(driver, s2_5_fd)
        s2_4_closed = _close(driver, s2_4_fd)
        parent_closed = _close(driver, parent_fd)
        release_incomplete = not (
            s2_5_closed and s2_4_closed and parent_closed
        )
        if release_incomplete:
            status = STATUS_RECOVERY_REQUIRED
            failure_code = "partial_recovery_lock_release_incomplete"
        result = _result(
            intent,
            status=status,
            s2_4_acquired=False,
            s2_5_acquired=False,
            first_released=acquired[0] and s2_4_closed,
            driver_engaged=True,
            failure_code=failure_code,
            session_class=session_class,
        )
        acquisition_vector = tuple(acquired)
        rollback = _rollback(
            intent,
            result,
            status=(
                "RECOVERY_REQUIRED" if release_incomplete
                else "RELEASED" if acquisition_vector == (True, True)
                else "RELEASED_AFTER_PARTIAL_ACQUIRE"
                if acquisition_vector == (True, False) else "NOT_REQUIRED"
            ),
            s2_5_attempted=acquired[1],
            s2_5_released=acquired[1] and s2_5_closed,
            s2_4_attempted=acquired[0],
            s2_4_released=acquired[0] and s2_4_closed,
            session_closed=not release_incomplete,
            failure_code=(
                "partial_recovery_lock_release_incomplete"
                if release_incomplete else None
            ),
        )
        return _outcome_without_lease(intent, result, rollback=rollback), None

    result = _result(
        intent,
        status=STATUS_ACQUIRED,
        s2_4_acquired=True,
        s2_5_acquired=True,
        first_released=False,
        driver_engaged=True,
        failure_code=None,
        session_class=session_class,
    )
    chain_digest = _chain_digest(intent, result)
    postcheck = _postcheck(
        result,
        chain_digest=chain_digest,
        session_class=session_class,
        both_locks_held=True,
        failure_code=None,
    )
    lease = {
        "driver": driver,
        "source_head": source_head,
        "root_identity": root_identity,
        "s2_4_fd": s2_4_fd,
        "s2_5_fd": s2_5_fd,
        "s2_4_identity": identities[0],
        "s2_5_identity": identities[1],
        "intent_digest": intent["self_digest"],
        "result_digest": result["self_digest"],
        "postcheck_digest": postcheck["self_digest"],
        "lock_chain_digest": chain_digest,
        "transaction_active": False,
        "closed": False,
    }
    try:
        _verify_lease(
            lease,
            driver=driver,
            source_head=source_head,
            require_transaction=False,
        )
    except RecoveryDualLockError as error:
        release = _release_lease(lease)
        failed_result = _result(
            intent,
            status=STATUS_RECOVERY_REQUIRED,
            s2_4_acquired=False,
            s2_5_acquired=False,
            first_released=release["s2_4_released"],
            driver_engaged=True,
            failure_code=error.code,
            session_class=session_class,
        )
        return _outcome_without_lease(
            intent,
            failed_result,
            rollback=_rollback(
                intent,
                failed_result,
                status=release["status"],
                s2_5_attempted=release["s2_5_release_attempted"],
                s2_5_released=release["s2_5_released"],
                s2_4_attempted=release["s2_4_release_attempted"],
                s2_4_released=release["s2_4_released"],
                session_closed=release["session_closed"],
                failure_code=release["failure_code"],
            ),
        ), None
    rollback = _rollback(
        intent,
        result,
        status="NOT_REQUIRED",
        s2_5_attempted=False,
        s2_5_released=False,
        s2_4_attempted=False,
        s2_4_released=False,
        session_closed=False,
        failure_code=None,
    )
    return {
        "status": STATUS_ACQUIRED,
        "intent": intent,
        "result": result,
        "postcheck": postcheck,
        "rollback": rollback,
    }, lease


def _exercise_recovery_dual_lock_simulation(
    *,
    driver: Any,
    source_head: str,
    while_held: Any = None,
) -> dict[str, Any]:
    """Exercise the protocol without returning a session or write authority."""

    if while_held is not None and not callable(while_held):
        raise RecoveryDualLockError("simulation_callback_invalid")
    outcome, lease = _acquire_recovery_dual_lock(
        driver=driver,
        source_head=source_head,
        session_class="SIMULATION_ONLY",
    )
    outcome["simulation_only"] = True
    outcome["store_write_authority"] = False
    if lease is None:
        return outcome
    try:
        if while_held is not None:
            while_held()
    finally:
        outcome["rollback"] = _release_lease(lease)
    if outcome["rollback"]["status"] == "RECOVERY_REQUIRED":
        outcome["status"] = STATUS_RECOVERY_REQUIRED
    return outcome


def simulate_recovery_dual_lock(*, source_head: str) -> dict[str, Any]:
    """Return a typed, pure no-effect simulation plan with no injected code."""

    outcome, lease = _acquire_recovery_dual_lock(
        driver=None,
        source_head=source_head,
        session_class="SIMULATION_ONLY",
    )
    if lease is not None:
        raise RecoveryDualLockError("no_effect_simulation_issued_lease")
    outcome["simulation_only"] = True
    outcome["effect_performed"] = False
    outcome["store_write_authority"] = False
    return outcome
