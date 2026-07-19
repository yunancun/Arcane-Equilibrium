#!/usr/bin/python3
"""Fail-closed ALR-only source-mismatch crash-loop current-head repin."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import stat
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROLLFORWARD_SOURCE = Path(__file__).with_name("p0b_alr_current_head_rollforward_v1.py")
ROLLFORWARD_SOURCE_SHA256 = "978713cc782519e0b296699a0e45cb6b734fbe489a4f8c4f718ba87f1f097c4e"


class ServiceRepinError(RuntimeError):
    """Fail-closed authorization, admission, or transaction error."""


class PersistentAmbiguousReceiptError(ServiceRepinError):
    """An exact PASS receipt path could not be proven non-authoritative."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256_bytes(raw)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _fsync_parent(path: Path) -> None:
    parent_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _load_rollforward_module():
    before = ROLLFORWARD_SOURCE.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ServiceRepinError("rollforward_source_identity_invalid")
    fd = os.open(
        ROLLFORWARD_SOURCE,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(fd)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final = os.fstat(fd)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if (
        (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or opened.st_size != final.st_size
        or opened.st_mtime_ns != final.st_mtime_ns
        or len(raw) != opened.st_size
        or sha256_bytes(raw) != ROLLFORWARD_SOURCE_SHA256
    ):
        raise ServiceRepinError("rollforward_source_identity_or_hash_mismatch")
    module = types.ModuleType("sealed_p0b_alr_current_head_rollforward_v1")
    module.__file__ = str(ROLLFORWARD_SOURCE)
    module.__package__ = ""
    exec(compile(raw, str(ROLLFORWARD_SOURCE), "exec", dont_inherit=True), module.__dict__)
    return module


BASE = _load_rollforward_module()
Runtime = BASE.Runtime
UNIT_NAME = BASE.UNIT_NAME
UNIT_PATH = BASE.UNIT_PATH
UNIT_LOCK = BASE.UNIT_LOCK
COST_LOCK = BASE.COST_LOCK
ALPHA_LOCK = BASE.ALPHA_LOCK
RECEIPT_DIR = BASE.RECEIPT_DIR / "service-only-repin"

FACTS_SCHEMA = "p0b_alr_service_only_repin_facts_v1"
AUTHORIZATION_SCHEMA = "p0b_alr_service_only_repin_authorization_v1"
INTENT_SCHEMA = "p0b_alr_service_only_repin_intent_v1"
RECEIPT_SCHEMA = "p0b_alr_service_only_repin_receipt_v1"
CRASH_FINGERPRINT = "AlrEventConsumerError: source_head_mismatch"
FAILURE_EVIDENCE_SCHEMA = "p0b_alr_source_mismatch_observation_v1"
FACTS_TTL_SECONDS = 300
MUTATION_PLAN = (
    "block-effect-signals",
    f"stop:{UNIT_NAME}",
    "atomic-generation-repin",
    "atomic-unit-repin",
    "daemon-reload",
    f"reset-failed:{UNIT_NAME}",
    f"restart:{UNIT_NAME}",
    "receipt-common:xcreate-receipt-guard",
    "receipt-common:persist-pass-receipt",
    "receipt-success:transition-receipt-guard-to-committed",
    "receipt-failure:quarantine-uncommitted-pass-receipt",
    f"receipt-failure:compensation-stop:{UNIT_NAME}",
    "receipt-failure:persist-nonpass-receipt",
)
RECEIPT_COMMON_ACTIONS = MUTATION_PLAN[7:9]
RECEIPT_SUCCESS_ACTIONS = MUTATION_PLAN[9:10]
RECEIPT_FAILURE_ACTIONS = MUTATION_PLAN[10:]
FAILURE_POLICY = (
    "post_stop_failure_freeze_alr_stopped_no_backward_pin_no_old_restart_"
    "guarded_pass_commit_and_deterministic_quarantine_required_"
    "compensation_only_after_pass_closure_inadmissible_"
    "two_phase_committed_marker_before_irreversible_guard_unlink_"
    "authoritative_pass_recovery_otherwise_no_compensation_no_commit_rollback"
)
BOUNDARIES = {
    "broker_contact": False,
    "pg_access": False,
    "credential_content_read": False,
    "source_mutation": False,
    "order_effect": False,
    "risk_or_cost_gate_mutation": False,
    "policy_or_dsn_mutation": False,
    "engine_api_watchdog_mutation": False,
}
EFFECT_SIGNALS = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
FACTS_FIELDS = {
    "schema_version", "captured_at_utc", "expires_at_utc", "target_host",
    "target_user_unit", "target_head", "old_head", "source_snapshot",
    "source_snapshot_digest", "old_pin", "old_unit", "proposed_unit_sha256",
    "crash_loop", "lock_identities", "protected_projection",
    "protected_projection_digest", "receipt_destination", "mutation_plan",
    "failure_policy", "boundaries", "facts_digest",
}
CRASH_LOOP_FIELDS = {
    "active_state", "sub_state", "main_pid", "nrestarts", "invocation_id",
    "control_group", "alr_source_head", "fingerprint",
    "fingerprint_observed_at_utc", "fingerprint_sha256",
    "evidence_path", "evidence_sha256", "evidence_digest",
}
FAILURE_EVIDENCE_FIELDS = {
    "schema_version", "observed_at_utc", "target_host", "target_user_unit",
    "old_head", "target_head", "invocation_id", "nrestarts", "fingerprint",
    "journal_slice_sha256", "journal_cursor", "observation_digest",
}
INTENT_FIELDS = {
    "schema_version", "kind", "authorization_id", "authorization_digest",
    "facts_digest", "target_head", "old_head", "started_at_utc",
    "mutation_plan", "failure_policy", "boundaries",
}
RECEIPT_FIELDS = {
    "schema_version", "status", "authorization_id", "authorization_digest",
    "facts_digest", "target_head", "old_head", "intent", "mutations",
    "stopped_proofs", "target_service", "final_postcheck", "completed_at_utc",
    "boundaries", "error_type", "error_digest", "receipt_digest",
}
AUTHORIZATION_FIELDS = {
    "schema_version", "authorization_id", "approved_by", "approved_at_utc",
    "expires_at_utc", "target_host", "target_user_unit", "facts_path",
    "facts_sha256", "facts_digest", "target_head", "old_head",
    "source_snapshot_digest", "old_pin_digest", "old_unit_digest",
    "proposed_unit_sha256", "crash_loop_digest", "lock_identities_digest",
    "protected_projection_digest", "intent_path", "receipt_path",
    "receipt_guard_path", "receipt_committed_marker_path",
    "receipt_quarantine_path", "receipt_protocol_path_digest",
    "mutation_plan", "failure_policy", "typed_confirm", "authorization_digest",
}


def receipt_protocol_paths(receipt_path: Path, *, authorization_id: str) -> dict[str, Path]:
    if (
        re.fullmatch(r"[A-Za-z0-9_.-]{8,128}", authorization_id) is None
        or receipt_path.name != f"{authorization_id}.receipt.json"
    ):
        raise ServiceRepinError("receipt_protocol_path_input_invalid")
    return {
        "guard": receipt_path.with_name(f"{authorization_id}.receipt.guard.json"),
        "committed": receipt_path.with_name(
            f"{authorization_id}.receipt.committed.json"
        ),
        "quarantine": receipt_path.with_name(
            f"{authorization_id}.receipt.quarantine.json"
        ),
    }


def receipt_protocol_path_bundle(
    receipt_path: Path, *, authorization_id: str,
) -> dict[str, str]:
    paths = receipt_protocol_paths(receipt_path, authorization_id=authorization_id)
    return {
        "schema_version": "p0b_alr_receipt_protocol_paths_v1",
        "receipt_path": str(receipt_path),
        "guard_path": str(paths["guard"]),
        "committed_marker_path": str(paths["committed"]),
        "quarantine_path": str(paths["quarantine"]),
    }


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ServiceRepinError("utc_timestamp_required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ServiceRepinError(f"invalid_timestamp:{label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ServiceRepinError(f"non_utc_timestamp:{label}")
    return parsed.astimezone(timezone.utc)


def _require_digest(value: Any, *, raw: bool = False) -> bool:
    pattern = r"[0-9a-f]{64}" if raw else r"sha256:[0-9a-f]{64}"
    return re.fullmatch(pattern, str(value)) is not None


def validate_failure_evidence(
    evidence: dict[str, Any], *, now: datetime, target_head: str, old_head: str,
) -> None:
    if set(evidence) != FAILURE_EVIDENCE_FIELDS:
        raise ServiceRepinError("failure_evidence_fields_invalid")
    observed = parse_utc(evidence.get("observed_at_utc"), label="failure_evidence_observed")
    projection = {
        key: value for key, value in evidence.items() if key != "observation_digest"
    }
    if (
        evidence.get("schema_version") != FAILURE_EVIDENCE_SCHEMA
        or evidence.get("observation_digest") != canonical_digest(projection)
        or not observed <= now
        or (now - observed).total_seconds() > FACTS_TTL_SECONDS
        or evidence.get("target_host") != "trade-core"
        or evidence.get("target_user_unit") != UNIT_NAME
        or evidence.get("old_head") != old_head
        or evidence.get("target_head") != target_head
        or not isinstance(evidence.get("invocation_id"), str)
        or not evidence.get("invocation_id")
        or re.fullmatch(r"[1-9][0-9]*", str(evidence.get("nrestarts", ""))) is None
        or evidence.get("fingerprint") != CRASH_FINGERPRINT
        or re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("journal_slice_sha256", ""))) is None
        or not isinstance(evidence.get("journal_cursor"), str)
        or not evidence.get("journal_cursor")
    ):
        raise ServiceRepinError("failure_evidence_semantic_invalid")


def validate_authorization(
    authorization: dict[str, Any], *, facts: dict[str, Any], facts_path: Path,
    facts_sha256: str, now: datetime,
) -> None:
    if set(facts) != FACTS_FIELDS or set(authorization) != AUTHORIZATION_FIELDS:
        raise ServiceRepinError("authorization_or_facts_fields_invalid")
    facts_projection = {key: value for key, value in facts.items() if key != "facts_digest"}
    auth_projection = {
        key: value for key, value in authorization.items() if key != "authorization_digest"
    }
    captured = parse_utc(facts["captured_at_utc"], label="facts_captured")
    facts_expires = parse_utc(facts["expires_at_utc"], label="facts_expires")
    fingerprint_observed = parse_utc(
        facts["crash_loop"].get("fingerprint_observed_at_utc"), label="fingerprint_observed"
    )
    approved = parse_utc(authorization["approved_at_utc"], label="approved")
    expires = parse_utc(authorization["expires_at_utc"], label="authorization_expires")
    authorization_id = authorization.get("authorization_id")
    target_head = facts.get("target_head")
    old_head = facts.get("old_head")
    expected_intent = RECEIPT_DIR / f"{authorization_id}.intent.json"
    expected_receipt = RECEIPT_DIR / f"{authorization_id}.receipt.json"
    try:
        expected_protocol_paths = receipt_protocol_paths(
            expected_receipt, authorization_id=str(authorization_id),
        )
        expected_protocol_path_digest = canonical_digest(
            receipt_protocol_path_bundle(
                expected_receipt, authorization_id=str(authorization_id),
            )
        )
    except ServiceRepinError as exc:
        raise ServiceRepinError("authorization_semantic_binding_invalid") from exc
    crash = facts.get("crash_loop")
    evidence = read_bound_json(
        Path(str(crash.get("evidence_path", ""))),
        expected_sha256=str(crash.get("evidence_sha256", "")),
        label="failure_evidence", require_private=True,
    )
    validate_failure_evidence(
        evidence, now=now, target_head=str(target_head), old_head=str(old_head),
    )
    if (
        facts.get("schema_version") != FACTS_SCHEMA
        or facts.get("target_host") != "trade-core"
        or facts.get("target_user_unit") != UNIT_NAME
        or re.fullmatch(r"[0-9a-f]{40}", str(target_head)) is None
        or re.fullmatch(r"[0-9a-f]{40}", str(old_head)) is None
        or target_head == old_head
        or facts.get("facts_digest") != canonical_digest(facts_projection)
        or facts.get("source_snapshot_digest") != canonical_digest(facts.get("source_snapshot"))
        or any(
            facts.get("source_snapshot", {}).get(key) != target_head
            for key in ("head", "origin_main", "remote_origin_main")
        )
        or facts.get("source_snapshot", {}).get("clean") is not True
        or facts.get("old_pin", {}).get("payload", {}).get("head") != old_head
        or facts.get("old_unit", {}).get("head") != old_head
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(facts.get("old_pin", {}).get("identity", {}).get("sha256", "")),
        ) is None
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(facts.get("old_unit", {}).get("identity", {}).get("sha256", "")),
        ) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(facts.get("proposed_unit_sha256", ""))) is None
        or facts.get("protected_projection_digest") != canonical_digest(facts.get("protected_projection"))
        or not isinstance(facts.get("protected_projection", {}).get("user_unit_inventory"), dict)
        or UNIT_NAME in facts.get("protected_projection", {}).get("user_unit_inventory", {})
        or set(facts.get("lock_identities", {})) != {"cost", "alpha", "unit"}
        or facts.get("receipt_destination") != str(RECEIPT_DIR)
        or facts.get("mutation_plan") != list(MUTATION_PLAN)
        or facts.get("failure_policy") != FAILURE_POLICY
        or facts.get("boundaries") != BOUNDARIES
        or set(crash or {}) != CRASH_LOOP_FIELDS
        or crash.get("fingerprint") != CRASH_FINGERPRINT
        or crash.get("fingerprint_sha256") != sha256_bytes(CRASH_FINGERPRINT.encode())
        or crash.get("fingerprint_observed_at_utc") != evidence["observed_at_utc"]
        or crash.get("evidence_digest") != evidence["observation_digest"]
        or crash.get("active_state") != "activating"
        or crash.get("sub_state") != "auto-restart"
        or str(crash.get("main_pid")) != "0"
        or not isinstance(crash.get("invocation_id"), str)
        or not crash.get("invocation_id")
        or not isinstance(crash.get("control_group"), str)
        or not crash.get("control_group", "").startswith("/")
        or re.fullmatch(r"[1-9][0-9]*", str(crash.get("nrestarts", ""))) is None
        or crash.get("alr_source_head") != old_head
        or int(str(crash.get("nrestarts"))) < int(str(evidence.get("nrestarts")))
        or not fingerprint_observed <= captured <= now <= facts_expires
        or (facts_expires - captured).total_seconds() != FACTS_TTL_SECONDS
        or (captured - fingerprint_observed).total_seconds() > FACTS_TTL_SECONDS
    ):
        raise ServiceRepinError("facts_semantic_binding_invalid")
    if (
        authorization.get("schema_version") != AUTHORIZATION_SCHEMA
        or authorization.get("authorization_digest") != canonical_digest(auth_projection)
        or re.fullmatch(r"[A-Za-z0-9_.-]{8,128}", str(authorization_id)) is None
        or authorization.get("approved_by") != "PM/operator"
        or not captured <= approved <= now <= expires <= facts_expires
        or (expires - approved).total_seconds() > FACTS_TTL_SECONDS
        or authorization.get("target_host") != "trade-core"
        or authorization.get("target_user_unit") != UNIT_NAME
        or authorization.get("facts_path") != str(facts_path)
        or authorization.get("facts_sha256") != facts_sha256
        or not _require_digest(facts_sha256, raw=True)
        or authorization.get("facts_digest") != facts["facts_digest"]
        or authorization.get("target_head") != target_head
        or authorization.get("old_head") != old_head
        or authorization.get("source_snapshot_digest") != facts["source_snapshot_digest"]
        or authorization.get("old_pin_digest") != "sha256:" + facts["old_pin"]["identity"]["sha256"]
        or authorization.get("old_unit_digest") != "sha256:" + facts["old_unit"]["identity"]["sha256"]
        or authorization.get("proposed_unit_sha256") != facts["proposed_unit_sha256"]
        or authorization.get("crash_loop_digest") != canonical_digest(crash)
        or authorization.get("lock_identities_digest") != canonical_digest(facts["lock_identities"])
        or authorization.get("protected_projection_digest") != facts["protected_projection_digest"]
        or authorization.get("intent_path") != str(expected_intent)
        or authorization.get("receipt_path") != str(expected_receipt)
        or authorization.get("receipt_guard_path")
        != str(expected_protocol_paths["guard"])
        or authorization.get("receipt_committed_marker_path")
        != str(expected_protocol_paths["committed"])
        or authorization.get("receipt_quarantine_path")
        != str(expected_protocol_paths["quarantine"])
        or authorization.get("receipt_protocol_path_digest")
        != expected_protocol_path_digest
        or authorization.get("mutation_plan") != list(MUTATION_PLAN)
        or authorization.get("failure_policy") != FAILURE_POLICY
        or authorization.get("typed_confirm")
        != (
            f"p0b-alr-service-only-repin:trade-core:{target_head}:"
            f"{authorization_id}:{expected_protocol_path_digest}"
        )
    ):
        raise ServiceRepinError("authorization_semantic_binding_invalid")


def _proposed_unit_sha256(raw: bytes, *, old_head: str, target_head: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ServiceRepinError("unit_not_utf8") from exc
    old_line = f"ALR_SOURCE_HEAD={old_head}"
    new_line = f"ALR_SOURCE_HEAD={target_head}"
    if text.splitlines().count(old_line) != 1 or new_line in text:
        raise ServiceRepinError("unit_source_line_cardinality_mismatch")
    return sha256_bytes(text.replace(old_line, new_line, 1).encode())


def _other_user_unit_inventory(runtime: Any) -> dict[str, Any]:
    listed = runtime.run([
        BASE.SYSTEMD, "--user", "list-unit-files", "--type=service",
        "--no-legend", "--no-pager",
    ]).stdout
    names = sorted({
        line.split()[0] for line in listed.splitlines()
        if line.strip()
        and re.fullmatch(r"[A-Za-z0-9@_.:-]+\.service", line.split()[0])
        and line.split()[0] != UNIT_NAME
    })
    if not names:
        raise ServiceRepinError("protected_other_unit_inventory_empty")
    result: dict[str, Any] = {}
    for name in names:
        command = [BASE.SYSTEMD, "--user", "show", name]
        for prop in ("LoadState", "NeedDaemonReload", "FragmentPath", "DropInPaths"):
            command.extend(["-p", prop])
        raw = runtime.run(command).stdout
        values = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        if values.get("NeedDaemonReload") != "no":
            raise ServiceRepinError(f"protected_other_unit_reload_pending:{name}")
        fragment = Path(values.get("FragmentPath", ""))
        if values.get("LoadState") != "loaded" or not fragment.is_absolute():
            raise ServiceRepinError(f"protected_other_unit_disk_identity_missing:{name}")
        try:
            dropins = [Path(value) for value in shlex.split(values.get("DropInPaths", ""))]
        except ValueError as exc:
            raise ServiceRepinError(f"protected_other_unit_dropins_invalid:{name}") from exc
        if any(not path.is_absolute() for path in dropins):
            raise ServiceRepinError(f"protected_other_unit_dropins_invalid:{name}")
        result[name] = {
            "fragment": BASE.metadata(fragment, include_hash=True),
            "dropins": [BASE.metadata(path, include_hash=True) for path in dropins],
        }
    return result


def protected_projection(runtime: Any) -> dict[str, Any]:
    seam = getattr(runtime, "protected_snapshot_without_alr", None)
    if seam is not None:
        projection = json.loads(json.dumps(seam()))
    else:
        crontab_raw = runtime.run(["/usr/bin/crontab", "-l"]).stdout
        projection = {
            "units": {
                name: runtime.protected_unit_snapshot(name)
                for name in (
                    "openclaw-trading-api.service", "openclaw-watchdog.service"
                )
            },
            "engine": runtime.protected_engine_processes(),
            "auth_metadata": runtime.pin.auth_metadata(),
            "crontab": {
                "sha256": sha256_bytes(crontab_raw.encode()),
                "bytes": len(crontab_raw.encode()),
                "generation_overrides": [],
            },
            "global_pin_consumers": runtime.crontab_consumers_from_text(crontab_raw),
            "user_unit_inventory": _other_user_unit_inventory(runtime),
            "user_manager_jobs": runtime.no_queued_job(),
            "policy": BASE.metadata(BASE.POLICY_PATH, include_hash=True),
            "dsn_metadata": BASE.metadata(BASE.DSN_PATH, include_hash=False),
        }
    inventory = projection.get("user_unit_inventory")
    if not isinstance(inventory, dict) or UNIT_NAME in inventory:
        raise ServiceRepinError("protected_projection_contains_alr")
    return projection


def _continuing_crash_loop(service: dict[str, Any], facts: dict[str, Any]) -> None:
    captured = facts["crash_loop"]
    try:
        restarts = int(str(service.get("NRestarts", "")))
        captured_restarts = int(str(captured.get("nrestarts", "")))
    except ValueError as exc:
        raise ServiceRepinError("source_mismatch_crash_loop_not_exact") from exc
    if (
        service.get("ActiveState") != "activating"
        or service.get("SubState") != "auto-restart"
        or str(service.get("MainPID")) != "0"
        or restarts < max(1, captured_restarts)
        or service.get("ALRSourceHead") != facts["old_head"]
        or service.get("ControlGroup") != captured.get("control_group")
    ):
        raise ServiceRepinError("source_mismatch_crash_loop_not_exact")


def block_effect_signals() -> dict[str, Any]:
    if not hasattr(signal, "pthread_sigmask"):
        raise ServiceRepinError("pthread_sigmask_unavailable")
    prior = signal.pthread_sigmask(signal.SIG_BLOCK, EFFECT_SIGNALS)
    return {
        "blocked": sorted(member.name for member in EFFECT_SIGNALS),
        "prior_blocked": sorted(member.name for member in prior),
        "restore_performed": False,
    }


def validate_mutation_log(
    mutations: list[dict[str, Any]], *, status: str,
) -> None:
    if not all(
        isinstance(entry, dict) and isinstance(entry.get("action"), str)
        for entry in mutations
    ):
        raise ServiceRepinError("mutation_log_entry_invalid")
    actions = [entry["action"] for entry in mutations]
    allowed = list(MUTATION_PLAN[:7]) + list(RECEIPT_COMMON_ACTIONS)
    if status == "APPLIED_POSTCHECK_PASS":
        allowed += list(RECEIPT_SUCCESS_ACTIONS)
        if actions != allowed:
            raise ServiceRepinError("pass_mutation_log_not_exact_plan")
    else:
        allowed += list(RECEIPT_FAILURE_ACTIONS)
        if any(action in RECEIPT_SUCCESS_ACTIONS for action in actions):
            raise ServiceRepinError("failure_mutation_log_contains_success_branch")
    cursor = -1
    for action in actions:
        try:
            position = allowed.index(action, cursor + 1)
        except ValueError as exc:
            raise ServiceRepinError("mutation_log_not_declared_subsequence") from exc
        cursor = position


def receipt_marker_payload(
    *, authorization_id: str, receipt_path: Path, receipt_digest: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": "p0b_alr_receipt_commit_marker_v1",
        "authorization_id": authorization_id,
        "receipt_path": str(receipt_path),
        "receipt_digest": receipt_digest,
    }
    payload["marker_digest"] = canonical_digest(payload)
    return payload


def _xcreate_durable_json(path: Path, payload: dict[str, Any]) -> None:
    raw = canonical_json_bytes(payload)
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise ServiceRepinError("receipt_protocol_short_write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_parent(path)


def create_receipt_guard(
    path: Path, *, marker: dict[str, Any], committed_path: Path,
    quarantine_path: Path,
) -> None:
    if any(
        _path_entry_exists(candidate)
        for candidate in (path, committed_path, quarantine_path)
    ):
        raise ServiceRepinError("receipt_protocol_path_already_exists")
    _xcreate_durable_json(path, marker)


def transition_receipt_guard_to_committed(
    guard_path: Path, *, committed_path: Path, quarantine_path: Path,
    marker: dict[str, Any],
) -> None:
    expected_raw = canonical_json_bytes(marker)
    expected_sha = sha256_bytes(expected_raw)
    read_bound_json(
        guard_path, expected_sha256=expected_sha, label="receipt_guard",
        require_private=True,
    )
    if _path_entry_exists(committed_path) or _path_entry_exists(quarantine_path):
        raise ServiceRepinError("receipt_protocol_transition_destination_exists")
    _xcreate_durable_json(committed_path, marker)
    committed = read_bound_json(
        committed_path, expected_sha256=expected_sha, label="receipt_committed_marker",
        require_private=True,
    )
    guard_after_commit = read_bound_json(
        guard_path, expected_sha256=expected_sha, label="receipt_guard_after_commit",
        require_private=True,
    )
    if committed != marker or guard_after_commit != marker:
        raise ServiceRepinError("receipt_protocol_transition_postcheck_failed")
    os.unlink(guard_path)
    try:
        _fsync_parent(guard_path)
    except BaseException:
        # The committed marker was already file- and parent-fsynced.  Once guard
        # absence is visible, rollback could revoke a concurrently accepted PASS.
        pass


def invalidate_failed_pass_receipt(
    path: Path, *, attempted_receipt: dict[str, Any], persist_error: BaseException,
    guard_path: Path, committed_path: Path, quarantine_path: Path,
    marker: dict[str, Any],
) -> dict[str, Any]:
    """Move only the exact attempted PASS away from its authoritative path."""
    expected = canonical_json_bytes(attempted_receipt)
    guard_durable = False
    try:
        expected_paths = receipt_protocol_paths(
            path, authorization_id=attempted_receipt["authorization_id"],
        )
        if (
            guard_path != expected_paths["guard"]
            or committed_path != expected_paths["committed"]
            or quarantine_path != expected_paths["quarantine"]
        ):
            raise PersistentAmbiguousReceiptError("receipt_protocol_cleanup_path_mismatch")
        if not _path_entry_exists(guard_path):
            raise PersistentAmbiguousReceiptError(
                "receipt_guard_absent_irreversible_commit_boundary"
            )
        guard_durable = True
        expected_marker_sha = sha256_bytes(canonical_json_bytes(marker))
        if read_bound_json(
            guard_path, expected_sha256=expected_marker_sha,
            label="receipt_guard_cleanup", require_private=True,
        ) != marker:
            raise PersistentAmbiguousReceiptError("receipt_guard_cleanup_mismatch")
    except BaseException as guard_exc:
        return {
            "status": "PERSISTENT_AMBIGUOUS_PASS_RECEIPT",
            "path": str(path), "guard_path": str(guard_path),
            "closure_inadmissible": False,
            "guard_error_type": type(guard_exc).__name__,
            "guard_error_digest": sha256_bytes(str(guard_exc).encode()),
        }
    try:
        before = path.lstat()
    except FileNotFoundError:
        return {
            "status": "PASS_RECEIPT_ABSENT_CONFIRMED", "path": str(path),
            "closure_inadmissible": guard_durable,
        }
    try:
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise PersistentAmbiguousReceiptError("pass_receipt_identity_invalid")
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(fd)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            final = os.fstat(fd)
        finally:
            os.close(fd)
        raw = b"".join(chunks)
        after_read = path.lstat()
        if (
            (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or (after_read.st_dev, after_read.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_size != final.st_size
            or opened.st_mtime_ns != final.st_mtime_ns
            or raw != expected
        ):
            raise PersistentAmbiguousReceiptError("pass_receipt_not_exact_attempt")
        if _path_entry_exists(quarantine_path):
            raise PersistentAmbiguousReceiptError("pass_receipt_quarantine_collision")
        os.rename(path, quarantine_path)
        directory_fsync_error: BaseException | None = None
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            try:
                os.fsync(parent_fd)
            except BaseException as exc:
                directory_fsync_error = exc
        finally:
            os.close(parent_fd)
        if (
            _path_entry_exists(path)
            or not quarantine_path.is_file()
            or quarantine_path.read_bytes() != expected
        ):
            raise PersistentAmbiguousReceiptError("pass_receipt_quarantine_postcheck_failed")
        return {
            "status": (
                "PASS_RECEIPT_QUARANTINED_CONFIRMED"
                if directory_fsync_error is None
                else "PASS_RECEIPT_QUARANTINED_DIRECTORY_FSYNC_UNVERIFIED"
            ),
            "path": str(path), "quarantine_path": str(quarantine_path),
            "closure_inadmissible": (
                guard_durable or directory_fsync_error is None
            ),
            "sha256": sha256_bytes(expected),
            "directory_fsync_error_digest": (
                None if directory_fsync_error is None
                else sha256_bytes(str(directory_fsync_error).encode())
            ),
        }
    except BaseException as cleanup_exc:
        return {
            "status": "PERSISTENT_AMBIGUOUS_PASS_RECEIPT",
            "path": str(path), "guard_path": str(guard_path),
            "closure_inadmissible": guard_durable,
            "persist_error_digest": sha256_bytes(str(persist_error).encode()),
            "cleanup_error_type": type(cleanup_exc).__name__,
            "cleanup_error_digest": sha256_bytes(str(cleanup_exc).encode()),
        }


def validate_authoritative_receipt(path: Path, *, expected_sha256: str) -> dict[str, Any]:
    payload = read_bound_json(
        path, expected_sha256=expected_sha256, label="service_repin_receipt",
        require_private=True,
    )
    if payload.get("status") == "APPLIED_POSTCHECK_PASS":
        try:
            receipt_projection = {
                key: value for key, value in payload.items()
                if key != "receipt_digest"
            }
            if payload.get("receipt_digest") != canonical_digest(receipt_projection):
                raise PersistentAmbiguousReceiptError(
                    "authoritative_pass_receipt_digest_invalid"
                )
            paths = receipt_protocol_paths(
                path, authorization_id=str(payload.get("authorization_id", "")),
            )
            marker = receipt_marker_payload(
                authorization_id=payload["authorization_id"], receipt_path=path,
                receipt_digest=payload["receipt_digest"],
            )
            marker_raw = canonical_json_bytes(marker)
            if (
                _path_entry_exists(paths["guard"])
                or _path_entry_exists(paths["quarantine"])
            ):
                raise PersistentAmbiguousReceiptError(
                    "authoritative_pass_receipt_ambiguous"
                )
            committed = read_bound_json(
                paths["committed"], expected_sha256=sha256_bytes(marker_raw),
                label="receipt_committed_marker", require_private=True,
            )
            if committed != marker:
                raise PersistentAmbiguousReceiptError(
                    "authoritative_pass_receipt_commit_mismatch"
                )
        except (KeyError, OSError, ServiceRepinError) as exc:
            if isinstance(exc, PersistentAmbiguousReceiptError):
                raise
            raise PersistentAmbiguousReceiptError(
                "authoritative_pass_receipt_not_committed"
            ) from exc
    return payload


class ServiceOnlyRepinTransaction:
    """One-shot ALR-only transaction over the sealed rollforward Runtime."""

    def __init__(
        self, runtime: Any, authorization: dict[str, Any], facts: dict[str, Any], *,
        facts_path: Path, facts_sha256: str, now=None,
    ) -> None:
        self.runtime = runtime
        self.authorization = authorization
        self.facts = facts
        self.facts_path = facts_path
        self.facts_sha256 = facts_sha256
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.block_signals = getattr(
            runtime, "block_effect_signals", block_effect_signals
        )
        runtime.approval = {
            "service_baseline": {
                "cost_lock_identity": facts["lock_identities"]["cost"],
                "alpha_lock_identity": facts["lock_identities"]["alpha"],
                "unit_lock_identity": facts["lock_identities"]["unit"],
            },
            "evidence": {"proposed_unit_sha256": facts["proposed_unit_sha256"]},
        }

    @property
    def intent_path(self) -> Path:
        return Path(self.authorization["intent_path"])

    @property
    def receipt_path(self) -> Path:
        return Path(self.authorization["receipt_path"])

    @property
    def receipt_guard_path(self) -> Path:
        return Path(self.authorization["receipt_guard_path"])

    @property
    def receipt_committed_marker_path(self) -> Path:
        return Path(self.authorization["receipt_committed_marker_path"])

    @property
    def receipt_quarantine_path(self) -> Path:
        return Path(self.authorization["receipt_quarantine_path"])

    def preflight(self) -> dict[str, Any]:
        validate_authorization(
            self.authorization, facts=self.facts, facts_path=self.facts_path,
            facts_sha256=self.facts_sha256, now=self.now(),
        )
        if any(
            _path_entry_exists(path) for path in (
                self.intent_path, self.receipt_path, self.receipt_guard_path,
                self.receipt_committed_marker_path, self.receipt_quarantine_path,
            )
        ):
            raise ServiceRepinError("authorization_already_consumed")
        source = self.runtime.source_snapshot()
        if canonical_digest(source) != self.facts["source_snapshot_digest"]:
            raise ServiceRepinError("source_snapshot_drift")
        self.runtime.lane_snapshot()
        self.runtime.no_queued_job()
        pin = self.runtime.pin_snapshot(expected_head=self.facts["old_head"])
        unit = self.runtime.unit_snapshot(expected_head=self.facts["old_head"])
        if (
            pin["identity"] != self.facts["old_pin"]["identity"]
            or unit["identity"] != self.facts["old_unit"]["identity"]
            or _proposed_unit_sha256(
                unit["raw"], old_head=self.facts["old_head"],
                target_head=self.facts["target_head"],
            ) != self.facts["proposed_unit_sha256"]
        ):
            raise ServiceRepinError("old_generation_identity_drift")
        service = self.runtime.service_snapshot(require_active=None)
        _continuing_crash_loop(service, self.facts)
        projection = protected_projection(self.runtime)
        if canonical_digest(projection) != self.facts["protected_projection_digest"]:
            raise ServiceRepinError("protected_projection_drift")
        return {"source": source, "pin": pin, "unit": unit, "service": service, "protected": projection}

    def _intent_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": INTENT_SCHEMA,
            "kind": "intent",
            "authorization_id": self.authorization["authorization_id"],
            "authorization_digest": self.authorization["authorization_digest"],
            "facts_digest": self.facts["facts_digest"],
            "target_head": self.facts["target_head"],
            "old_head": self.facts["old_head"],
            "started_at_utc": utc_text(self.now()),
            "mutation_plan": list(MUTATION_PLAN),
            "failure_policy": FAILURE_POLICY,
            "boundaries": BOUNDARIES,
        }
        if set(payload) != INTENT_FIELDS:
            raise ServiceRepinError("internal_intent_fields_invalid")
        return payload

    @staticmethod
    def _stable_admission(value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value[key] for key in ("source", "pin", "unit", "protected")
        }

    def _receipt_payload(
        self, *, status: str, intent: dict[str, Any], mutations: list[dict[str, Any]],
        stopped_proofs: Any, target_service: Any, final_postcheck: Any,
        error: BaseException | None,
    ) -> dict[str, Any]:
        if status not in {
            "APPLIED_POSTCHECK_PASS", "BLOCKED_NO_EFFECT",
            "POST_STOP_FAILURE_STOPPED_VERIFIED", "POST_STOP_STATE_UNVERIFIED",
            "POST_EFFECT_CLOSURE_UNVERIFIED_NO_COMPENSATION",
        }:
            raise ServiceRepinError("internal_receipt_status_invalid")
        validate_mutation_log(mutations, status=status)
        payload = {
            "schema_version": RECEIPT_SCHEMA,
            "status": status,
            "authorization_id": self.authorization["authorization_id"],
            "authorization_digest": self.authorization["authorization_digest"],
            "facts_digest": self.facts["facts_digest"],
            "target_head": self.facts["target_head"],
            "old_head": self.facts["old_head"],
            "intent": intent,
            "mutations": mutations,
            "stopped_proofs": stopped_proofs,
            "target_service": target_service,
            "final_postcheck": final_postcheck,
            "completed_at_utc": utc_text(self.now()),
            "boundaries": BOUNDARIES,
            "error_type": None if error is None else type(error).__name__,
            "error_digest": None if error is None else sha256_bytes(str(error).encode()),
        }
        payload["receipt_digest"] = canonical_digest(payload)
        if set(payload) != RECEIPT_FIELDS:
            raise ServiceRepinError("internal_receipt_fields_invalid")
        return payload

    def apply(self) -> dict[str, Any]:
        before = self.preflight()
        mutations: list[dict[str, Any]] = []
        intent_binding: dict[str, Any] | None = None
        stop_attempted = False
        effect_signal_mask: dict[str, Any] | None = None
        attempted_success_receipt: dict[str, Any] | None = None
        attempted_success_marker: dict[str, Any] | None = None
        try:
            with self.runtime.transaction_lock() as locks:
                locked = self.preflight()
                if (
                    locks != self.facts["lock_identities"]
                    or self._stable_admission(locked) != self._stable_admission(before)
                ):
                    raise ServiceRepinError("locked_admission_drift")
                effect_signal_mask = self.block_signals()
                mutations.append({
                    "action": "block-effect-signals",
                    "result": effect_signal_mask,
                })
                intent_binding = self.runtime.persist_path(
                    self.intent_path, self._intent_payload()
                )
                stop_attempted = True
                stop_mutation = {"action": f"stop:{UNIT_NAME}"}
                mutations.append(stop_mutation)
                stop_mutation["result"] = self.runtime.stop_alr()
                stopped = self.runtime.prove_old_absent_twice(before["service"])
                if canonical_digest(self.runtime.source_snapshot()) != self.facts["source_snapshot_digest"]:
                    raise ServiceRepinError("source_snapshot_drift_after_stop")
                if canonical_digest(protected_projection(self.runtime)) != self.facts["protected_projection_digest"]:
                    raise ServiceRepinError("protected_projection_drift_after_stop")
                pin_mutation = {"action": "atomic-generation-repin"}
                mutations.append(pin_mutation)
                pin_mutation["result"] = self.runtime.advance_pin()
                unit_mutation = {"action": "atomic-unit-repin"}
                mutations.append(unit_mutation)
                _old_raw, target_unit = self.runtime.atomic_unit_to_target()
                unit_mutation["sha256"] = target_unit["identity"]["sha256"]
                if target_unit["identity"].get("sha256") != self.facts["proposed_unit_sha256"]:
                    raise ServiceRepinError("target_unit_digest_mismatch")
                if canonical_digest(protected_projection(self.runtime)) != self.facts["protected_projection_digest"]:
                    raise ServiceRepinError("protected_projection_drift_before_reload")
                reload_mutation = {"action": "daemon-reload"}
                mutations.append(reload_mutation)
                reload_mutation["result"] = self.runtime.daemon_reload()
                manager = self.runtime.service_snapshot(require_active=False)
                if manager.get("ALRSourceHead") != self.facts["target_head"]:
                    raise ServiceRepinError("manager_not_reloaded_to_target")
                reset_mutation = {"action": f"reset-failed:{UNIT_NAME}"}
                mutations.append(reset_mutation)
                reset_mutation["result"] = self.runtime.reset_failed()
                if (
                    canonical_digest(self.runtime.source_snapshot()) != self.facts["source_snapshot_digest"]
                    or canonical_digest(protected_projection(self.runtime))
                    != self.facts["protected_projection_digest"]
                ):
                    raise ServiceRepinError("pre_restart_collateral_drift")
                restart_mutation = {"action": f"restart:{UNIT_NAME}"}
                mutations.append(restart_mutation)
                restart_mutation["result"] = self.runtime.restart_alr()
                target_service = self.runtime.wait_stable_target(prior=before["service"])
                final_unit = self.runtime.unit_snapshot(expected_head=self.facts["target_head"])
                final_pin = self.runtime.pin_snapshot(expected_head=self.facts["target_head"])
                final_protected = protected_projection(self.runtime)
                final_source = self.runtime.source_snapshot()
                final_lane = self.runtime.lane_snapshot()
                final_jobs = self.runtime.no_queued_job()
                if (
                    final_unit["identity"].get("sha256") != self.facts["proposed_unit_sha256"]
                    or canonical_digest(final_protected) != self.facts["protected_projection_digest"]
                    or canonical_digest(final_source) != self.facts["source_snapshot_digest"]
                    or target_service.get("ALRSourceHead") != self.facts["target_head"]
                ):
                    raise ServiceRepinError("final_postcheck_drift")
                final_postcheck = {
                    "source_snapshot_digest": canonical_digest(final_source),
                    "protected_projection_digest": canonical_digest(final_protected),
                    "unit_digest": "sha256:" + final_unit["identity"]["sha256"],
                    "pin_digest": "sha256:" + final_pin["identity"]["sha256"],
                    "lane": final_lane,
                    "user_manager_jobs": final_jobs,
                    "lock_identities": locks,
                    "lock_identities_digest": canonical_digest(locks),
                    "effect_signal_mask": effect_signal_mask,
                }
                pass_mutations = mutations + [
                    {"action": action}
                    for action in RECEIPT_COMMON_ACTIONS + RECEIPT_SUCCESS_ACTIONS
                ]
                receipt = self._receipt_payload(
                    status="APPLIED_POSTCHECK_PASS", intent=intent_binding,
                    mutations=pass_mutations, stopped_proofs=stopped,
                    target_service=target_service, final_postcheck=final_postcheck,
                    error=None,
                )
                attempted_success_receipt = receipt
                attempted_success_marker = receipt_marker_payload(
                    authorization_id=self.authorization["authorization_id"],
                    receipt_path=self.receipt_path,
                    receipt_digest=receipt["receipt_digest"],
                )
                mutations.append({"action": RECEIPT_COMMON_ACTIONS[0]})
                create_receipt_guard(
                    self.receipt_guard_path, marker=attempted_success_marker,
                    committed_path=self.receipt_committed_marker_path,
                    quarantine_path=self.receipt_quarantine_path,
                )
                mutations.append({"action": RECEIPT_COMMON_ACTIONS[1]})
                self.runtime.persist_path(self.receipt_path, receipt)
                read_bound_json(
                    self.receipt_path,
                    expected_sha256=sha256_bytes(canonical_json_bytes(receipt)),
                    label="persisted_pass_receipt", require_private=True,
                )
                transition_receipt_guard_to_committed(
                    self.receipt_guard_path,
                    committed_path=self.receipt_committed_marker_path,
                    quarantine_path=self.receipt_quarantine_path,
                    marker=attempted_success_marker,
                )
                mutations.append({"action": RECEIPT_SUCCESS_ACTIONS[0]})
                return receipt
        except BaseException as exc:
            if not stop_attempted:
                raise
            receipt_invalidation = None
            if (
                attempted_success_receipt is not None
                and attempted_success_marker is not None
            ):
                try:
                    authoritative = validate_authoritative_receipt(
                        self.receipt_path,
                        expected_sha256=sha256_bytes(
                            canonical_json_bytes(attempted_success_receipt)
                        ),
                    )
                except BaseException:
                    authoritative = None
                if authoritative == attempted_success_receipt:
                    return attempted_success_receipt
                if not _path_entry_exists(self.receipt_guard_path):
                    irreversible_state = {
                        "status": "IRREVERSIBLE_COMMIT_STATE_UNVERIFIED",
                        "receipt_path": str(self.receipt_path),
                        "committed_marker_present": _path_entry_exists(
                            self.receipt_committed_marker_path
                        ),
                        "quarantine_present": _path_entry_exists(
                            self.receipt_quarantine_path
                        ),
                    }
                    closure_error = PersistentAmbiguousReceiptError(
                        "irreversible_commit_unverified_without_compensation:"
                        + canonical_digest(irreversible_state)
                    )
                    return self._receipt_payload(
                        status="POST_EFFECT_CLOSURE_UNVERIFIED_NO_COMPENSATION",
                        intent=intent_binding or {}, mutations=mutations,
                        stopped_proofs=None, target_service=None,
                        final_postcheck=None, error=closure_error,
                    )
                receipt_invalidation = invalidate_failed_pass_receipt(
                    self.receipt_path,
                    attempted_receipt=attempted_success_receipt,
                    persist_error=exc,
                    guard_path=self.receipt_guard_path,
                    committed_path=self.receipt_committed_marker_path,
                    quarantine_path=self.receipt_quarantine_path,
                    marker=attempted_success_marker,
                )
                mutations.append({
                    "action": RECEIPT_FAILURE_ACTIONS[0],
                    "result": receipt_invalidation,
                })
                if receipt_invalidation.get("closure_inadmissible") is not True:
                    closure_error = PersistentAmbiguousReceiptError(
                        "pass_closure_unverified_without_compensation:"
                        + canonical_digest(receipt_invalidation)
                    )
                    return self._receipt_payload(
                        status="POST_EFFECT_CLOSURE_UNVERIFIED_NO_COMPENSATION",
                        intent=intent_binding or {}, mutations=mutations,
                        stopped_proofs=None, target_service=None,
                        final_postcheck=None, error=closure_error,
                    )
            compensation_proofs = None
            compensation_mutation = {
                "action": RECEIPT_FAILURE_ACTIONS[1],
            }
            mutations.append(compensation_mutation)
            try:
                compensation_mutation["result"] = self.runtime.stop_alr()
                compensation_proofs = self.runtime.prove_old_absent_twice(before["service"])
            except BaseException as compensation_exc:
                compensation_mutation["error_type"] = type(compensation_exc).__name__
                compensation_mutation["error_digest"] = sha256_bytes(
                    str(compensation_exc).encode()
                )
                compensation_proofs = None
            status = (
                "POST_STOP_FAILURE_STOPPED_VERIFIED"
                if compensation_proofs is not None else "POST_STOP_STATE_UNVERIFIED"
            )
            failure_error: BaseException = exc
            if receipt_invalidation is not None and receipt_invalidation["status"] not in {
                "PASS_RECEIPT_ABSENT_CONFIRMED",
                "PASS_RECEIPT_QUARANTINED_CONFIRMED",
            }:
                status = "POST_STOP_STATE_UNVERIFIED"
                compensation_proofs = None
                failure_error = PersistentAmbiguousReceiptError(
                    "persistent_or_durability_ambiguous_pass_receipt:"
                    + canonical_digest(receipt_invalidation)
                )
            if (
                receipt_invalidation is not None
                and receipt_invalidation["status"]
                == "PERSISTENT_AMBIGUOUS_PASS_RECEIPT"
            ):
                return self._receipt_payload(
                    status=status, intent=intent_binding or {}, mutations=mutations,
                    stopped_proofs=compensation_proofs, target_service=None,
                    final_postcheck=None, error=failure_error,
                )
            mutations.append({"action": RECEIPT_FAILURE_ACTIONS[2]})
            failure = self._receipt_payload(
                status=status, intent=intent_binding or {}, mutations=mutations,
                stopped_proofs=compensation_proofs, target_service=None,
                final_postcheck=None, error=failure_error,
            )
            try:
                self.runtime.persist_path(self.receipt_path, failure)
                return failure
            except BaseException as persist_exc:
                persistence_error = ServiceRepinError(
                    "post_stop_receipt_persist_unverified:"
                    + sha256_bytes(str(exc).encode())
                    + ":"
                    + sha256_bytes(str(persist_exc).encode())
                )
                return self._receipt_payload(
                    status="POST_STOP_STATE_UNVERIFIED",
                    intent=intent_binding or {}, mutations=mutations,
                    stopped_proofs=None, target_service=None,
                    final_postcheck=None, error=persistence_error,
                )


def capture_facts(
    runtime: Any, *, now: datetime, failure_evidence: dict[str, Any],
    failure_evidence_path: Path, failure_evidence_sha256: str, old_head: str,
) -> dict[str, Any]:
    reopened_evidence = read_bound_json(
        failure_evidence_path, expected_sha256=failure_evidence_sha256,
        label="failure_evidence", require_private=True,
    )
    if reopened_evidence != failure_evidence:
        raise ServiceRepinError("failure_evidence_reopen_mismatch")
    target_head = runtime.source_snapshot().get("head")
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(target_head)) is None
        or re.fullmatch(r"[0-9a-f]{40}", old_head) is None
        or target_head == old_head
    ):
        raise ServiceRepinError("source_generation_invalid")
    source = runtime.source_snapshot()
    if any(source.get(key) != target_head for key in ("head", "origin_main", "remote_origin_main")) or source.get("clean") is not True:
        raise ServiceRepinError("target_source_not_exact_current_main")
    runtime.lane_snapshot()
    validate_failure_evidence(
        failure_evidence, now=now, target_head=str(target_head), old_head=old_head,
    )
    fingerprint_observed_at = parse_utc(
        failure_evidence["observed_at_utc"], label="failure_evidence_observed"
    )
    service = runtime.service_snapshot(require_active=None)
    if (
        service.get("ActiveState") != "activating"
        or service.get("SubState") != "auto-restart"
        or str(service.get("MainPID")) != "0"
        or re.fullmatch(r"[1-9][0-9]*", str(service.get("NRestarts", ""))) is None
        or service.get("ALRSourceHead") != old_head
        or not service.get("InvocationID")
        or int(str(service.get("NRestarts"))) < int(str(failure_evidence["nrestarts"]))
    ):
        raise ServiceRepinError("source_mismatch_crash_loop_not_exact")
    old_pin = runtime.pin_snapshot(expected_head=old_head)
    old_unit = runtime.unit_snapshot(expected_head=old_head)
    projection = protected_projection(runtime)
    captured_at = utc_text(now)
    facts = {
        "schema_version": FACTS_SCHEMA,
        "captured_at_utc": captured_at,
        "expires_at_utc": utc_text(now + timedelta(seconds=FACTS_TTL_SECONDS)),
        "target_host": "trade-core",
        "target_user_unit": UNIT_NAME,
        "target_head": target_head,
        "old_head": old_head,
        "source_snapshot": source,
        "source_snapshot_digest": canonical_digest(source),
        "old_pin": old_pin,
        "old_unit": {"identity": old_unit["identity"], "head": old_unit["head"]},
        "proposed_unit_sha256": _proposed_unit_sha256(
            old_unit["raw"], old_head=old_head, target_head=target_head,
        ),
        "crash_loop": {
            "active_state": service["ActiveState"],
            "sub_state": service["SubState"],
            "main_pid": service["MainPID"],
            "nrestarts": service["NRestarts"],
            "invocation_id": service.get("InvocationID", ""),
            "control_group": service["ControlGroup"],
            "alr_source_head": service["ALRSourceHead"],
            "fingerprint": CRASH_FINGERPRINT,
            "fingerprint_observed_at_utc": utc_text(fingerprint_observed_at),
            "fingerprint_sha256": sha256_bytes(CRASH_FINGERPRINT.encode()),
            "evidence_path": str(failure_evidence_path),
            "evidence_sha256": failure_evidence_sha256,
            "evidence_digest": failure_evidence["observation_digest"],
        },
        "lock_identities": {
            "cost": runtime.lock_snapshot(COST_LOCK, label="cost"),
            "alpha": runtime.lock_snapshot(ALPHA_LOCK, label="alpha"),
            "unit": runtime.unit_lock_snapshot(),
        },
        "protected_projection": projection,
        "protected_projection_digest": canonical_digest(projection),
        "receipt_destination": str(RECEIPT_DIR),
        "mutation_plan": list(MUTATION_PLAN),
        "failure_policy": FAILURE_POLICY,
        "boundaries": BOUNDARIES,
    }
    facts["facts_digest"] = canonical_digest(facts)
    return facts


def strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ServiceRepinError(f"duplicate_json_key:{label}")
            value[key] = item
        return value

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceRepinError(f"invalid_json:{label}") from exc
    if not isinstance(result, dict):
        raise ServiceRepinError(f"json_object_required:{label}")
    return result


def read_bound_json(
    path: Path, *, expected_sha256: str, label: str, require_private: bool = False,
    after_open: Any = None,
) -> dict[str, Any]:
    if not path.is_absolute() or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ServiceRepinError(f"bound_file_argument_invalid:{label}")
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ServiceRepinError(f"bound_file_identity_invalid:{label}")
    fd = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        opened = os.fstat(fd)
        if after_open is not None:
            after_open()
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final = os.fstat(fd)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    try:
        after_path = path.lstat()
    except OSError as exc:
        raise ServiceRepinError(f"bound_file_replaced_after_open:{label}") from exc
    if (
        (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or (after_path.st_dev, after_path.st_ino) != (opened.st_dev, opened.st_ino)
        or opened.st_size != final.st_size
        or opened.st_mtime_ns != final.st_mtime_ns
        or len(raw) != opened.st_size
        or sha256_bytes(raw) != expected_sha256
        or (
            require_private
            and (
                opened.st_uid != os.getuid()
                or opened.st_gid != os.getgid()
                or stat.S_IMODE(opened.st_mode) & 0o077
            )
        )
    ):
        raise ServiceRepinError(f"bound_file_identity_or_hash_mismatch:{label}")
    return strict_json(raw, label=label)


def blocked_no_effect(
    authorization: dict[str, Any], facts: dict[str, Any], error: BaseException,
) -> dict[str, Any]:
    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "BLOCKED_NO_EFFECT",
        "authorization_id": authorization.get("authorization_id"),
        "authorization_digest": authorization.get("authorization_digest"),
        "facts_digest": facts.get("facts_digest"),
        "target_head": facts.get("target_head"),
        "old_head": facts.get("old_head"),
        "intent": None,
        "mutations": [],
        "stopped_proofs": None,
        "target_service": None,
        "final_postcheck": None,
        "completed_at_utc": utc_text(datetime.now(timezone.utc)),
        "boundaries": BOUNDARIES,
        "error_type": type(error).__name__,
        "error_digest": sha256_bytes(str(error).encode()),
    }
    payload["receipt_digest"] = canonical_digest(payload)
    return payload


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture-facts", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--facts-out", type=Path)
    parser.add_argument("--failure-evidence-json", type=Path)
    parser.add_argument("--failure-evidence-sha256")
    parser.add_argument("--authorization-json", type=Path)
    parser.add_argument("--authorization-sha256")
    args = parser.parse_args(argv)

    if args.capture_facts:
        if (
            args.facts_out is None or args.failure_evidence_json is None
            or args.failure_evidence_sha256 is None
        ):
            parser.error(
                "--capture-facts requires --facts-out, --failure-evidence-json, "
                "and --failure-evidence-sha256"
            )
        if not args.facts_out.is_absolute() or args.facts_out.exists():
            raise ServiceRepinError("facts_output_invalid_or_exists")
        runtime = Runtime(discover=True)
        failure_evidence = read_bound_json(
            args.failure_evidence_json,
            expected_sha256=args.failure_evidence_sha256,
            label="failure_evidence", require_private=True,
        )
        facts = capture_facts(
            runtime, now=datetime.now(timezone.utc),
            failure_evidence=failure_evidence,
            failure_evidence_path=args.failure_evidence_json,
            failure_evidence_sha256=args.failure_evidence_sha256,
            old_head=BASE.OLD_HEAD,
        )
        runtime.persist_path(args.facts_out, facts)
        _emit(facts)
        return 0

    if args.authorization_json is None or args.authorization_sha256 is None:
        parser.error("--apply requires --authorization-json and --authorization-sha256")
    authorization: dict[str, Any] | None = None
    facts: dict[str, Any] | None = None
    try:
        authorization = read_bound_json(
            args.authorization_json, expected_sha256=args.authorization_sha256,
            label="authorization", require_private=True,
        )
        facts_path = Path(str(authorization.get("facts_path", "")))
        facts_sha256 = str(authorization.get("facts_sha256", ""))
        facts = read_bound_json(
            facts_path, expected_sha256=facts_sha256, label="facts",
            require_private=True,
        )
        old_pin_digest = str(authorization.get("old_pin_digest", ""))
        old_unit_digest = str(authorization.get("old_unit_digest", ""))
        if not old_pin_digest.startswith("sha256:") or not old_unit_digest.startswith("sha256:"):
            raise ServiceRepinError("old_generation_digest_invalid")
        BASE.configure_runtime_generation(
            target_head=str(authorization.get("target_head", "")),
            old_head=str(authorization.get("old_head", "")),
            old_pin_sha256=old_pin_digest.removeprefix("sha256:"),
            old_unit_sha256=old_unit_digest.removeprefix("sha256:"),
        )
        runtime = Runtime()
        result = ServiceOnlyRepinTransaction(
            runtime, authorization, facts, facts_path=facts_path,
            facts_sha256=facts_sha256,
        ).apply()
    except BaseException as exc:
        if authorization is None or facts is None:
            raise
        result = blocked_no_effect(authorization, facts, exc)
        _emit(result)
        return 2
    _emit(result)
    return 0 if result["status"] == "APPLIED_POSTCHECK_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
