#!/usr/bin/python3
"""Deploy-only staged lane plus short ALR cutover to the exact current head.

Phase 1 keeps the old ALR running while the normal lane produces a target-head
board in an ALR-unwatched staging rendezvous.  Phase 2 is one short, fenced
cutover: stop old ALR, repin, publish the preapproved board live, repin the unit,
reload and restart ALR once.  After stop, every ambiguity freezes ALR stopped;
there is deliberately no backward pin or old-generation restart path.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
import time
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


SCHEMA = "p0b_alr_current_head_rollforward_v1"
AUTHORIZATION_SCHEMA = "p0b_alr_runtime_authorization_v1"
ADAPTER_ID = "p0b_alr_rollforward_adapter_v1"
RUNTIME_BINDINGS_SCHEMA = "phase_runtime_bindings_v1"
INTERNAL_PLAN_SCHEMA = "p0b_alr_rollforward_internal_plan_v1"
TARGET_HEAD = ""
OLD_HEAD = ""
OLD_PIN_SHA256 = ""
OLD_UNIT_SHA256 = ""
PIN_OVERLAY = Path(__file__).with_name("p0b_generation_pin_apply_current_head_v1.py")
PIN_OVERLAY_SHA256 = "bf913816f3d404391e5ccf6cdb76f0b47704013b1c88bfdb65ba3482a36499e1"
PRIVATE_BUNDLE_STAGER = Path(__file__).with_name("p0b_psycopg_private_bundle_stage_v1.py")
PRIVATE_BUNDLE_STAGER_SHA256 = "d01769287fe5b649bbafb1b81c3aa2174b2d7b55475592d38511423fce3bcfc4"
PRIVATE_BUNDLE_DESTINATION = Path("/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps")
PRIVATE_BUNDLE_MANIFEST_SHA256 = "05a42a3e5893c35e4bca9d4e8b3ba8f8ffcbe23883682eb5345ccb454abddf24"
OBSERVER_V2 = Path(__file__).with_name("p0b_alr_current_head_two_cycle_observer_v2.py")
OBSERVER_V2_SHA256 = "0bdced688dc8603839c316a0f40a3e5f034b3463cee786f7523b1a74d287406a"

REPO = Path("/home/ncyu/BybitOpenClaw/srv")
DATA = Path("/home/ncyu/BybitOpenClaw/var/openclaw")
SECRETS_ROOT = Path("/home/ncyu/BybitOpenClaw/secrets")
STANDING_AUTH_PATH = (
    DATA / "cost_gate_learning_lane/standing_demo_operator_authorization.json"
)
PUBLISHER = REPO / "helper_scripts/research/cost_gate_learning_lane/candidate_board_publisher.py"
PUBLISHER_SHA256 = "22acf9f095f0b0b6b47263c9ad8860b1704180a4bad9970317669eaf50b8c34e"
LANE_CRON = REPO / "helper_scripts/cron/cost_gate_learning_lane_cron.sh"
LANE_CRON_SHA256 = "6421178d0e87caa25651085967694e4dd40ce9dae8a2cde2aa22d52c20c6e7aa"
PIN_HELPER = REPO / "helper_scripts/deploy/derive_expected_source_head.sh"
UNIT_NAME = "openclaw-alr-shadow.service"
UNIT_PATH = Path("/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service")
UNIT_LOCK = UNIT_PATH.parent / ".openclaw-alr-shadow.service.p0b-recovery.lock"
COST_LOCK = DATA / "locks/cost_gate_learning_lane_cron.lock"
COST_OWNER = DATA / "locks/cost_gate_learning_lane_cron.owner.owner.json"
ALPHA_LOCK = DATA / "locks/alpha_discovery_throughput_cron.lock"
ALPHA_OWNER = DATA / "locks/alpha_discovery_throughput_cron.owner.owner.json"
PIN_PATH = DATA / "runtime_generation/expected_source_head.json"
RECEIPT_DIR = DATA / "runtime_recovery/alr-current-head-rollforward"
POLICY_PATH = Path("/home/ncyu/.config/openclaw/alr-candidate-arbiter-policy.json")
DSN_PATH = Path("/home/ncyu/.config/openclaw/alr-shadow.dsn")
EVIDENCE_DIR = Path("/home/ncyu/.local/share/openclaw/alr-candidate-evidence")
COMPLETION_DIR = DATA / "research_workload_guard/cost"
PRODUCER_DIR = DATA / "cost_gate_learning_lane"
LEDGER_PATH = PRODUCER_DIR / "probe_ledger.jsonl"
STAGING_ROOT = DATA / "runtime_recovery/alr-current-head-rollforward/staging"
SYSTEMD = "/usr/bin/systemctl"
ALR_STABLE_WINDOW_SECONDS = 5


def configure_runtime_generation(
    *, target_head: str, old_head: str, old_pin_sha256: str, old_unit_sha256: str
) -> None:
    """Install one authorization-bound generation for this one-shot process."""
    values = (target_head, old_head)
    hashes = (old_pin_sha256, old_unit_sha256)
    if any(re.fullmatch(r"[0-9a-f]{40}", value) is None for value in values):
        raise RollforwardError("runtime_generation_head_invalid")
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes):
        raise RollforwardError("runtime_generation_hash_invalid")
    global TARGET_HEAD, OLD_HEAD, OLD_PIN_SHA256, OLD_UNIT_SHA256
    TARGET_HEAD = target_head
    OLD_HEAD = old_head
    OLD_PIN_SHA256 = old_pin_sha256
    OLD_UNIT_SHA256 = old_unit_sha256

SYSTEM_ENV = {
    "HOME": "/home/ncyu",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "USER": "ncyu",
    "LOGNAME": "ncyu",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "XDG_RUNTIME_DIR": "/run/user/1000",
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_KEY_0": "core.fsmonitor",
    "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "core.hooksPath",
    "GIT_CONFIG_VALUE_1": "/dev/null",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
}
SERVICE_PROPERTIES = (
    "LoadState", "ActiveState", "SubState", "MainPID",
    "ExecMainStartTimestampMonotonic", "NRestarts", "InvocationID",
    "FragmentPath", "DropInPaths", "ControlGroup", "Environment",
    "NeedDaemonReload",
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
LANE_BOUNDARIES = {
    **BOUNDARIES,
    "pg_access": "normal_lane_readonly",
    "credential_content_read": "normal_lane_existing_environment_load",
    "adapter_pg_access": False,
    "adapter_credential_content_read": False,
    "normal_lane_pg_readonly": True,
    "normal_lane_existing_environment_load": True,
    "live_alr_publication": False,
    "alr_service_mutation": False,
    "generation_pin_mutation": False,
}


class RollforwardError(RuntimeError):
    """Fail-closed admission or transaction error."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + sha256_bytes(raw)


def parse_utc(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise RollforwardError(f"invalid_timestamp:{label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise RollforwardError(f"non_utc_timestamp:{label}")
    return parsed.astimezone(timezone.utc)


def strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RollforwardError(f"duplicate_json_key:{label}")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RollforwardError(f"invalid_json:{label}") from exc
    if not isinstance(value, dict):
        raise RollforwardError(f"json_object_required:{label}")
    return value


# Frozen to the producer validator and observer v2. Audit-only candidate fields
# must never perturb the semantic candidate-set identity.
CANDIDATE_SELECTION_FIELDS = (
    "schema_version", "candidate_id", "candidate_family_key",
    "stable_cohort_hash", "candidate_identity", "identity_complete",
    "arbiter_input", "arbiter_input_complete", "selection_eligible", "blockers",
)
CANDIDATE_BOARD_AUDIT_FIELDS = (
    "lineage_partition_complete", "raw_blocked_outcome_row_count",
    "qualified_lineage_outcome_row_count", "unqualified_lineage_outcome_row_count",
    "invalid_lineage_outcome_row_count", "invalid_exact_cohort_row_count",
    "invalid_identity_family_row_count", "unassigned_invalid_lineage_outcome_row_count",
    "unqualified_raw_valid_evaluation_missing_row_count",
    "unqualified_event_outside_evaluation_window_row_count",
    "consistent_duplicate_event_hash_extra_row_count",
    "conflicting_duplicate_event_hash_row_count",
    "conflicting_duplicate_event_hash_attribution_row_count",
    "lineage_exclusion_reason_counts",
)


def observer_canonical_sha256(value: Any) -> str:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RollforwardError("observer_board_not_canonicalizable") from exc
    return sha256_bytes(raw)


def validate_observer_board_hashes(board: dict[str, Any]) -> dict[str, str]:
    """Rebuild the producer's semantic selection, audit, and board hashes."""
    rows = board.get("candidate_rows")
    if (
        not isinstance(rows, list)
        or not all(isinstance(row, dict) for row in rows)
        or any(any(field not in row for field in CANDIDATE_SELECTION_FIELDS) for row in rows)
        or any(not isinstance(row.get("candidate_id"), str) or not row["candidate_id"] for row in rows)
        or any(field not in board for field in CANDIDATE_BOARD_AUDIT_FIELDS)
    ):
        raise RollforwardError("observer_board_semantic_projection_invalid")
    semantic_rows = [
        {field: row[field] for field in CANDIDATE_SELECTION_FIELDS}
        for row in rows
    ]
    semantic_rows.sort(
        key=lambda row: (row["candidate_id"], observer_canonical_sha256(row))
    )
    selection_hash = observer_canonical_sha256({
        "schema_version": "cost_gate_learning_candidate_selection_v2",
        "candidate_rows": semantic_rows,
    })
    selection_fields = set(CANDIDATE_SELECTION_FIELDS)
    candidate_audit_rows = [
        {
            "candidate_id": row["candidate_id"],
            **{
                key: value for key, value in row.items()
                if key not in selection_fields and key != "candidate_id"
            },
        }
        for row in rows
    ]
    candidate_audit_rows.sort(key=lambda row: row["candidate_id"])
    audit_hash = observer_canonical_sha256({
        "schema_version": "cost_gate_learning_candidate_audit_v2",
        **{field: board[field] for field in CANDIDATE_BOARD_AUDIT_FIELDS},
        "candidate_audit_rows": candidate_audit_rows,
    })
    board_hash = observer_canonical_sha256({
        key: value for key, value in board.items() if key != "board_hash"
    })
    expected = {
        "board_hash": board_hash,
        "audit_hash": audit_hash,
        "selection_hash": selection_hash,
        "candidate_set_hash": observer_canonical_sha256(semantic_rows),
    }
    for key in ("selection_hash", "audit_hash", "board_hash"):
        if board.get(key) != expected[key]:
            raise RollforwardError(f"observer_{key}_mismatch")
    return expected


def metadata(path: Path, *, include_hash: bool = False) -> dict[str, Any]:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode):
        raise RollforwardError(f"symlink_forbidden:{path.name}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RollforwardError(f"identity_race:{path.name}")
        raw = b""
        if include_hash:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if opened.st_size != after.st_size or opened.st_mtime_ns != after.st_mtime_ns:
        raise RollforwardError(f"changed_during_read:{path.name}")
    result = {
        "dev": after.st_dev, "ino": after.st_ino, "uid": after.st_uid,
        "gid": after.st_gid, "mode": stat.S_IMODE(after.st_mode),
        "nlink": after.st_nlink, "size": after.st_size,
        "mtime_ns": after.st_mtime_ns, "ctime_ns": after.st_ctime_ns,
    }
    if include_hash:
        if len(raw) != after.st_size:
            raise RollforwardError(f"short_read:{path.name}")
        result["sha256"] = sha256_bytes(raw)
    return result


def require_private_directory(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(before.st_mode)
        or path.resolve() != path
        or before.st_uid != 1000
        or before.st_gid != 1000
        or stat.S_IMODE(before.st_mode) & 0o077
    ):
        raise RollforwardError(f"private_directory_identity_invalid:{path.name}")
    return {
        "dev": before.st_dev, "ino": before.st_ino, "uid": before.st_uid,
        "gid": before.st_gid, "mode": stat.S_IMODE(before.st_mode),
        "nlink": before.st_nlink,
    }


def load_pin_engine(*, generation: dict[str, Any] | None = None):
    before = PIN_OVERLAY.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RollforwardError("pin_overlay_not_regular")
    fd = os.open(PIN_OVERLAY, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        raw = b""
        while len(raw) < opened.st_size:
            chunk = os.read(fd, opened.st_size - len(raw))
            if not chunk:
                break
            raw += chunk
        final = os.fstat(fd)
    finally:
        os.close(fd)
    if (
        (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or opened.st_size != final.st_size
        or opened.st_mtime_ns != final.st_mtime_ns
        or sha256_bytes(raw) != PIN_OVERLAY_SHA256
    ):
        raise RollforwardError("pin_overlay_identity_or_hash_mismatch")
    module = types.ModuleType("p0b_generation_pin_current_head_overlay")
    module.__file__ = str(PIN_OVERLAY)
    exec(compile(raw, str(PIN_OVERLAY), "exec", dont_inherit=True), module.__dict__)
    engine = module.load_transaction_engine()
    if generation is None:
        return engine
    return module.configure(engine, **generation)


def load_publisher():
    before = PUBLISHER.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RollforwardError("publisher_source_not_regular")
    fd = os.open(PUBLISHER, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
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
        or sha256_bytes(raw) != PUBLISHER_SHA256
    ):
        raise RollforwardError("publisher_source_hash_mismatch")
    module = types.ModuleType("sealed_candidate_board_publisher")
    module.__file__ = str(PUBLISHER)
    module.__package__ = "cost_gate_learning_lane"
    # The publisher imports its sibling package.  Import is constrained by the
    # exact clean target checkout and the execution-tree lease checked around
    # every staging/cutover operation.
    root = str(REPO / "helper_scripts/research")
    inserted = root not in sys.path
    if inserted:
        sys.path.insert(0, root)
    try:
        exec(compile(raw, str(PUBLISHER), "exec", dont_inherit=True), module.__dict__)
    finally:
        if inserted:
            sys.path.remove(root)
    return module


def load_private_bundle_stager():
    before = PRIVATE_BUNDLE_STAGER.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RollforwardError("private_bundle_stager_not_regular")
    fd = os.open(
        PRIVATE_BUNDLE_STAGER,
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
        not stat.S_ISREG(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        or opened.st_size != final.st_size
        or opened.st_mtime_ns != final.st_mtime_ns
        or len(raw) != opened.st_size
        or sha256_bytes(raw) != PRIVATE_BUNDLE_STAGER_SHA256
    ):
        raise RollforwardError("private_bundle_stager_identity_mismatch")
    module = types.ModuleType("sealed_p0b_private_bundle_stager")
    module.__file__ = str(PRIVATE_BUNDLE_STAGER)
    module.__package__ = ""
    exec(compile(raw, str(PRIVATE_BUNDLE_STAGER), "exec", dont_inherit=True), module.__dict__)
    if module.canonical_manifest_sha256(module.SEALED_MANIFEST) != PRIVATE_BUNDLE_MANIFEST_SHA256:
        raise RollforwardError("private_bundle_manifest_mismatch")
    return module


AUTHORIZATION_FIELDS = {
    "schema_version", "adapter_id", "phase", "intent_id", "intent_digest",
    "task_contract_digest", "context_artifact_digest", "governance_bindings",
    "claim_bindings", "expected_source_head", "expected_origin_main_head",
    "expected_old_runtime_source_head", "expected_old_pin_digest",
    "expected_source_tree_digest", "expected_pin_consumer_inventory_digest",
    "expected_runtime_identity_digest", "target_host", "target_environment",
    "target_user_unit", "require_clean_tree", "require_fresh_origin_main",
    "phase1_effect_receipt_digest", "phase1_closure_digest",
    "sealed_lineage_bundle_digest", "private_bundle_destination",
    "observer_requirement", "approved_by", "approved_at", "expires_at",
    "typed_confirm", "hard_stops", "authorization_digest",
}
GOVERNANCE_BINDING_FIELDS = {
    "compiled_route_schema", "compiled_route_digest", "route_dag_digest",
    "context_artifact_schema", "pm_context_artifact_digest",
    "pa_context_artifact_digest", "e3_context_artifact_digest",
    "ops_preflight_context_artifact_digest", "pa_role_fragment_digest",
    "pa_command_capture_digest", "e3_role_fragment_digest",
    "e3_command_capture_digest", "ops_preflight_role_fragment_digest",
    "ops_preflight_command_capture_digest", "ops_preflight_attestation_digest",
    "ops_preflight_observed_at", "ops_preflight_expires_at",
    "pm_approval_artifact_digest", "authorized_argv_digest",
    "protected_baseline_digest", "phase_runtime_bindings_artifact_digest",
    "phase_runtime_bindings_path", "authorization_path",
}
STAGE_CLAIM_FIELDS = {
    "p0b_effect_adapter_selection", "p0b_adapter_source", "p0b_adapter_tests",
    "p0b_base_adapter_source", "p0b_generation_apply_source",
    "p0b_private_bundle_stager_source", "p0b_private_bundle_stager_tests",
    "p0b_private_bundle_source_manifest",
    "p0b_private_bundle_destination_absent_attestation",
    "p0b_target_source_attestation", "p0b_completion_inventory",
    "p0b_producer_inventory", "p0b_live_inventory",
    "p0b_protected_runtime_baseline", "p0b_p0a_completed_board_input",
    "p0b_phase_runtime_bindings", "p0b_runtime_source_binding",
    "p0b_runtime_protected_binding", "p0b_runtime_paths_binding",
    "p0b_runtime_inventories_binding", "p0b_runtime_lineage_binding",
}
CUTOVER_CLAIM_FIELDS = {
    "p0b_effect_adapter_selection", "p0b_adapter_source", "p0b_adapter_tests",
    "p0b_base_adapter_source", "p0b_generation_apply_source",
    "p0b_observer_source", "p0b_observer_tests", "p0b_observer_dependency_source",
    "p0b_phase1_task_contract", "p0b_phase1_route",
    "p0b_phase1_context_artifact", "p0b_phase1_intent", "p0b_phase1_receipt",
    "p0b_phase1_closure", "p0b_sealed_lineage_bundle",
    "p0b_private_bundle_receipt", "p0b_private_bundle_destination",
    "p0b_target_source_attestation", "p0b_completion_inventory",
    "p0b_producer_inventory", "p0b_live_inventory",
    "p0b_protected_runtime_baseline", "p0b_staged_candidate_board",
    "p0b_phase_runtime_bindings", "p0b_runtime_source_binding",
    "p0b_runtime_protected_binding", "p0b_runtime_paths_binding",
    "p0b_runtime_inventories_binding", "p0b_runtime_lineage_binding",
}

RUNTIME_BINDINGS_FIELDS = {
    "schema_version", "phase", "intent_id", "target_head",
    "source_attestation", "protected_runtime_baseline", "phase_paths",
    "inventories", "lineage", "section_claims", "observed_at", "expires_at",
    "artifact_digest",
}
RUNTIME_BINDING_SECTIONS = {
    "source_attestation": "p0b_runtime_source_binding",
    "protected_runtime_baseline": "p0b_runtime_protected_binding",
    "phase_paths": "p0b_runtime_paths_binding",
    "inventories": "p0b_runtime_inventories_binding",
    "lineage": "p0b_runtime_lineage_binding",
}
SOURCE_ATTESTATION_FIELDS = {"source", "execution_tree", "source_tree_digest"}
PROTECTED_BASELINE_FIELDS = {
    "service_baseline", "protected", "protected_digest",
    "pin_consumer_inventory", "pin_consumer_inventory_digest",
    "runtime_identity", "runtime_identity_digest",
}
STAGE_PATH_FIELDS = {
    "staging_root", "cron_destination", "sealed_destination",
    "publisher_receipt_path", "private_deps_receipt_path",
    "private_deps_destination", "phase1_receipt_path", "phase1_closure_path",
}
CUTOVER_PATH_FIELDS = {
    "phase1_receipt_path", "phase1_closure_path", "live_destination",
    "provisional_cutover_path", "observer_input_path",
}
INVENTORY_FIELDS = {
    "live_inventory", "live_inventory_digest", "completion_inventory",
    "completion_inventory_digest", "producer_inventory",
    "producer_inventory_digest", "ledger_inventory", "ledger_inventory_digest",
    "lane_effective_config", "lane_effective_config_digest",
}
STAGE_LINEAGE_FIELDS = {
    "p0a_completed_board_input", "private_bundle_destination_absent",
}
CUTOVER_LINEAGE_FIELDS = {
    "phase1_receipt", "phase1_closure", "sealed_lineage_bundle",
    "completion", "producer_board", "staged_board",
    "staging_publisher_receipt", "private_deps_receipt", "token",
    "max_age_seconds", "proposed_unit_sha256", "private_deps_destination",
    "private_deps_manifest_sha256", "completion_inventory_digest",
    "producer_inventory_digest", "ledger_pre_inventory_digest",
    "ledger_post_inventory_digest", "lane_effective_config_digest",
}


def _governance_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def validate_runtime_authorization(
    authorization: dict[str, Any], *, phase: str, now: datetime
) -> None:
    if set(authorization) != AUTHORIZATION_FIELDS:
        raise RollforwardError("runtime_authorization_fields_invalid")
    governance = authorization.get("governance_bindings")
    claims = authorization.get("claim_bindings")
    if (
        authorization.get("schema_version") != AUTHORIZATION_SCHEMA
        or authorization.get("adapter_id") != ADAPTER_ID
        or authorization.get("phase") != phase
        or re.fullmatch(r"[a-z0-9][a-z0-9._-]{7,127}", str(authorization.get("intent_id", ""))) is None
        or not isinstance(governance, dict)
        or set(governance) != GOVERNANCE_BINDING_FIELDS
        or governance.get("compiled_route_schema") != "hybrid_execution_dag_v1"
        or governance.get("context_artifact_schema") != "context_artifact_v1"
        or not isinstance(claims, dict)
        or set(claims) != (STAGE_CLAIM_FIELDS if phase == "stage" else CUTOVER_CLAIM_FIELDS)
    ):
        raise RollforwardError("runtime_authorization_contract_invalid")
    top_digests = (
        "intent_digest", "task_contract_digest", "context_artifact_digest",
        "expected_old_pin_digest", "expected_source_tree_digest",
        "expected_pin_consumer_inventory_digest", "expected_runtime_identity_digest",
        "authorization_digest",
    )
    governance_digests = GOVERNANCE_BINDING_FIELDS - {
        "compiled_route_schema", "context_artifact_schema",
        "ops_preflight_observed_at", "ops_preflight_expires_at",
        "phase_runtime_bindings_path", "authorization_path",
    }
    if (
        any(not _governance_digest(authorization.get(key)) for key in top_digests)
        or any(not _governance_digest(governance.get(key)) for key in governance_digests)
        or any(not _governance_digest(value) for value in claims.values())
        or re.fullmatch(r"[0-9a-f]{40}", str(authorization.get("expected_source_head", ""))) is None
        or authorization.get("expected_origin_main_head") != authorization.get("expected_source_head")
        or re.fullmatch(r"[0-9a-f]{40}", str(authorization.get("expected_old_runtime_source_head", ""))) is None
        or authorization.get("target_host") != "trade-core"
        or authorization.get("target_environment") != "trade_core_alr"
        or authorization.get("target_user_unit") != UNIT_NAME
        or authorization.get("require_clean_tree") is not True
        or authorization.get("require_fresh_origin_main") is not True
        or authorization.get("private_bundle_destination") != str(PRIVATE_BUNDLE_DESTINATION)
        or not Path(str(governance.get("phase_runtime_bindings_path", ""))).is_absolute()
        or "latest" in Path(str(governance.get("phase_runtime_bindings_path", ""))).name.lower()
        or not Path(str(governance.get("authorization_path", ""))).is_absolute()
        or "latest" in Path(str(governance.get("authorization_path", ""))).name.lower()
        or not isinstance(authorization.get("approved_by"), str)
        or not authorization["approved_by"]
        or not isinstance(authorization.get("hard_stops"), list)
        or len(set(authorization["hard_stops"])) != len(authorization["hard_stops"])
        or len(authorization["hard_stops"]) < 7
    ):
        raise RollforwardError("runtime_authorization_value_invalid")
    if phase == "stage":
        if (
            any(authorization.get(key) is not None for key in (
                "phase1_effect_receipt_digest", "phase1_closure_digest",
                "sealed_lineage_bundle_digest",
            ))
            or authorization.get("observer_requirement") != "NOT_APPLICABLE"
        ):
            raise RollforwardError("stage_authorization_scope_invalid")
    elif (
        any(not _governance_digest(authorization.get(key)) for key in (
            "phase1_effect_receipt_digest", "phase1_closure_digest",
            "sealed_lineage_bundle_digest",
        ))
        or authorization.get("observer_requirement") != "REQUIRED_PASS"
    ):
        raise RollforwardError("cutover_authorization_scope_invalid")
    approved = parse_utc(authorization.get("approved_at"), label="authorization_approved")
    expires = parse_utc(authorization.get("expires_at"), label="authorization_expires")
    ops_observed = parse_utc(
        governance.get("ops_preflight_observed_at"), label="ops_preflight_observed"
    )
    ops_expires = parse_utc(
        governance.get("ops_preflight_expires_at"), label="ops_preflight_expires"
    )
    if not approved <= now <= expires or not ops_observed <= now <= ops_expires:
        raise RollforwardError("runtime_authorization_expired_or_not_yet_valid")
    expected_confirm = (
        f"p0b-alr-rollforward:{phase}:trade-core:"
        f"{authorization['expected_source_head']}:{authorization['intent_id']}"
    )
    if authorization.get("typed_confirm") != expected_confirm:
        raise RollforwardError("runtime_authorization_typed_confirm_invalid")
    projection = {key: value for key, value in authorization.items() if key != "authorization_digest"}
    if authorization["authorization_digest"] != canonical_digest(projection):
        raise RollforwardError("runtime_authorization_digest_invalid")


def _exact_fields(value: Any, fields: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise RollforwardError(f"runtime_bindings_fields_invalid:{label}")
    return value


def _raw_binding(value: Any, *, label: str) -> dict[str, str]:
    binding = _exact_fields(value, {"path", "sha256"}, label=label)
    if (
        not Path(str(binding["path"])).is_absolute()
        or re.fullmatch(r"[0-9a-f]{64}", str(binding["sha256"])) is None
    ):
        raise RollforwardError(f"runtime_bindings_value_invalid:{label}")
    return binding


PHASE1_RECEIPT_FIELDS = {
    "schema_version", "phase", "status", "approval_id", "authorization_digest",
    "stage_authorization", "stage_authorization_digest", "stage_runtime_bindings",
    "stage_runtime_bindings_artifact_digest", "stage_authorized_runtime",
    "target_head", "old_head", "protected_sha256", "old_alr_retained_running",
    "global_pin_retained_old", "live_publication_performed", "sealed_lineage",
    "completed_at_utc", "intent", "locks_held_through_effect_receipt", "boundaries",
}
PHASE1_SEALED_LINEAGE_FIELDS = {
    "started_at_utc", "completed_at_utc", "token", "completion", "producer_board",
    "cron_staged_board", "staged_board", "staging_publisher_receipt",
    "private_deps_receipt", "private_deps_destination",
    "private_deps_manifest_sha256", "publisher_result", "execution_tree",
    "live_inventory_sha256", "completion_inventory_sha256",
    "producer_inventory_sha256", "ledger_pre_inventory_sha256",
    "ledger_post_inventory_sha256", "lane_effective_config_sha256",
    "alr_availability_monitor", "normal_lane_returncode", "observer_source_sha256",
}
PHASE1_CLOSURE_FIELDS = {
    "schema_version", "status", "phase", "intent_id", "intent_digest",
    "task_contract_digest", "compiled_route_digest", "context_artifact_digest",
    "stage_authorization_digest", "stage_runtime_bindings_artifact_digest",
    "phase1_effect_receipt_digest", "phase_result_digest", "ops_postcheck",
    "ops_postcheck_digest", "closed_at_utc", "closure_digest",
}
OPS_POSTCHECK_FIELDS = {
    "schema_version", "adapter_id", "phase", "intent_id", "intent_digest",
    "task_contract_digest", "context_artifact_digest", "compiled_route_digest",
    "source_head", "target_host", "target_user_unit", "effect_receipt_digest",
    "phase_result_digest", "observer_receipt_digest", "observed_at", "expires_at",
    "verified", "operation_digest",
}
PHASE1_LINEAGE_BUNDLE_FIELDS = {
    "schema_version", "target_head", "intent_id", "intent_digest",
    "task_contract_digest", "compiled_route_digest", "context_artifact_digest",
    "stage_authorization", "stage_authorization_digest", "stage_runtime_bindings",
    "stage_runtime_bindings_artifact_digest", "phase1_effect_receipt",
    "phase1_effect_receipt_digest", "phase1_closure", "phase1_closure_digest",
    "private_deps_receipt", "private_deps_destination",
    "private_deps_manifest_sha256", "staged_board", "bundle_digest",
}


def _load_semantic_binding(
    runtime: Any, binding: dict[str, str], *, label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _raw_binding(binding, label=label)
    raw, identity = runtime.load_bound(binding, label=label)
    if identity.get("sha256") != binding["sha256"] or identity.get("nlink") != 1:
        raise RollforwardError(f"phase1_{label}_identity_mismatch")
    return strict_json(raw, label=label), identity


def validate_phase1_semantic_lineage(
    runtime: Any, *, phase1_receipt: dict[str, str], phase1_closure: dict[str, str],
    sealed_lineage_bundle: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Reopen and semantically bind the legal Phase1 PASS lineage."""
    receipt, _receipt_identity = _load_semantic_binding(
        runtime, phase1_receipt, label="effect_receipt"
    )
    closure, _closure_identity = _load_semantic_binding(
        runtime, phase1_closure, label="closure"
    )
    try:
        _exact_fields(receipt, PHASE1_RECEIPT_FIELDS, label="phase1_effect_receipt")
        _exact_fields(closure, PHASE1_CLOSURE_FIELDS, label="phase1_closure")
        stage_authorization_binding = _raw_binding(
            receipt["stage_authorization"], label="stage_authorization"
        )
        stage_runtime_binding = _raw_binding(
            receipt["stage_runtime_bindings"], label="stage_runtime_bindings"
        )
        stage_authorization, _ = _load_semantic_binding(
            runtime, stage_authorization_binding, label="stage_authorization"
        )
        stage_bindings, _ = _load_semantic_binding(
            runtime, stage_runtime_binding, label="stage_runtime_bindings"
        )
        completed_at = parse_utc(receipt["completed_at_utc"], label="phase1_completed")
        validate_runtime_authorization(
            stage_authorization, phase="stage", now=completed_at
        )
        validate_phase_runtime_bindings(
            stage_bindings, stage_authorization, now=completed_at,
            bindings_path=Path(stage_runtime_binding["path"]),
        )
        intent, _ = _load_semantic_binding(runtime, receipt["intent"], label="intent")
    except (KeyError, TypeError, RollforwardError) as exc:
        if isinstance(exc, RollforwardError) and str(exc).startswith("phase1_"):
            raise
        raise RollforwardError("phase1_effect_receipt_invalid") from exc

    authorized_runtime_fields = {
        "expected_old_runtime_source_head", "expected_old_pin_digest",
        "expected_source_tree_digest", "expected_pin_consumer_inventory_digest",
        "expected_runtime_identity_digest",
    }
    sealed = receipt["sealed_lineage"]
    expected_authorized_runtime = {
        key: stage_authorization[key] for key in authorized_runtime_fields
    }
    intent_fields = {
        "schema_version", "phase", "kind", "approval_id", "target_head", "source",
        "execution_tree", "mutation_scope",
    }
    try:
        _exact_fields(receipt["stage_authorized_runtime"], authorized_runtime_fields,
                      label="stage_authorized_runtime")
        _exact_fields(intent, intent_fields, label="phase1_intent")
        _exact_fields(sealed, PHASE1_SEALED_LINEAGE_FIELDS, label="sealed_lineage")
        for key in (
            "completion", "producer_board", "cron_staged_board", "staged_board",
            "staging_publisher_receipt", "private_deps_receipt",
        ):
            _raw_binding(sealed[key], label=f"sealed_{key}")
    except (KeyError, TypeError, RollforwardError) as exc:
        raise RollforwardError("phase1_effect_receipt_invalid") from exc

    inventories = stage_bindings["inventories"]
    source_attestation = stage_bindings["source_attestation"]
    protected = stage_bindings["protected_runtime_baseline"]
    receipt_raw_digest = "sha256:" + phase1_receipt["sha256"]
    phase_result_digest = canonical_digest(receipt)
    if (
        receipt["schema_version"] != SCHEMA
        or receipt["phase"] != 1
        or receipt["status"] != "PHASE1_STAGING_APPLIED_PASS"
        or receipt["approval_id"] != stage_authorization["intent_id"]
        or receipt["authorization_digest"] != stage_authorization["authorization_digest"]
        or receipt["stage_authorization_digest"] != stage_authorization["authorization_digest"]
        or receipt["stage_runtime_bindings_artifact_digest"] != stage_bindings["artifact_digest"]
        or receipt["stage_authorized_runtime"] != expected_authorized_runtime
        or receipt["target_head"] != stage_authorization["expected_source_head"]
        or receipt["old_head"] != stage_authorization["expected_old_runtime_source_head"]
        or receipt["protected_sha256"] != protected["protected_digest"]
        or receipt["old_alr_retained_running"] is not True
        or receipt["global_pin_retained_old"] is not True
        or receipt["live_publication_performed"] is not False
        or receipt["boundaries"] != LANE_BOUNDARIES
        or not isinstance(receipt["locks_held_through_effect_receipt"], dict)
        or set(receipt["locks_held_through_effect_receipt"])
        != {"cost", "alpha", "unit", "publisher"}
        or receipt["locks_held_through_effect_receipt"]["publisher"] is not True
        or any(
            not isinstance(receipt["locks_held_through_effect_receipt"].get(key), dict)
            for key in ("cost", "alpha", "unit")
        )
        or receipt["locks_held_through_effect_receipt"]["cost"]
        != protected["service_baseline"]["cost_lock_identity"]
        or receipt["locks_held_through_effect_receipt"]["alpha"]
        != protected["service_baseline"]["alpha_lock_identity"]
        or receipt["locks_held_through_effect_receipt"]["unit"]
        != protected["service_baseline"]["unit_lock_identity"]
        or intent != {
            "schema_version": SCHEMA, "phase": 1, "kind": "intent",
            "approval_id": receipt["approval_id"], "target_head": receipt["target_head"],
            "source": source_attestation["source"],
            "execution_tree": source_attestation["execution_tree"],
            "mutation_scope": "normal_lane_and_unwatched_staging_only",
        }
        or sealed["execution_tree"] != source_attestation["execution_tree"]
        or sealed["live_inventory_sha256"] != inventories["live_inventory_digest"]
        or sealed["ledger_pre_inventory_sha256"] != inventories["ledger_inventory_digest"]
        or sealed["lane_effective_config_sha256"] != inventories["lane_effective_config_digest"]
        or sealed["private_deps_destination"] != str(PRIVATE_BUNDLE_DESTINATION)
        or sealed["private_deps_manifest_sha256"] != PRIVATE_BUNDLE_MANIFEST_SHA256
        or sealed["observer_source_sha256"] != OBSERVER_V2_SHA256
        or sealed["normal_lane_returncode"] != 0
        or re.fullmatch(r"[0-9a-f]{32}", str(sealed["token"])) is None
    ):
        raise RollforwardError("phase1_effect_receipt_semantic_mismatch")

    ops = closure.get("ops_postcheck")
    try:
        _exact_fields(ops, OPS_POSTCHECK_FIELDS, label="phase1_ops_postcheck")
    except RollforwardError as exc:
        raise RollforwardError("phase1_closure_invalid") from exc
    route_digest = stage_authorization["governance_bindings"]["compiled_route_digest"]
    expected_common = {
        "intent_id": stage_authorization["intent_id"],
        "intent_digest": stage_authorization["intent_digest"],
        "task_contract_digest": stage_authorization["task_contract_digest"],
        "compiled_route_digest": route_digest,
        "context_artifact_digest": stage_authorization["context_artifact_digest"],
    }
    ops_projection = {key: value for key, value in ops.items() if key != "operation_digest"}
    closure_projection = {
        key: value for key, value in closure.items() if key != "closure_digest"
    }
    try:
        observed = parse_utc(ops["observed_at"], label="phase1_ops_observed")
        expires = parse_utc(ops["expires_at"], label="phase1_ops_expires")
        closed = parse_utc(closure["closed_at_utc"], label="phase1_closure_closed")
    except (KeyError, TypeError, RollforwardError) as exc:
        raise RollforwardError("phase1_closure_invalid") from exc
    if (
        closure.get("schema_version") != "p0b_alr_phase1_governance_closure_v1"
        or closure.get("status") != "PHASE1_GOVERNANCE_CLOSURE_PASS"
        or closure.get("phase") != "stage"
        or any(closure.get(key) != value for key, value in expected_common.items())
        or closure.get("stage_authorization_digest")
        != stage_authorization["authorization_digest"]
        or closure.get("stage_runtime_bindings_artifact_digest")
        != stage_bindings["artifact_digest"]
        or closure.get("phase1_effect_receipt_digest") != receipt_raw_digest
        or closure.get("phase_result_digest") != phase_result_digest
        or closure.get("ops_postcheck_digest") != ops.get("operation_digest")
        or closure.get("closure_digest") != canonical_digest(closure_projection)
        or ops.get("schema_version") != "ops_p0b_alr_postcheck_v1"
        or ops.get("adapter_id") != ADAPTER_ID
        or ops.get("phase") != "stage"
        or any(ops.get(key) != value for key, value in expected_common.items())
        or ops.get("source_head") != receipt["target_head"]
        or ops.get("target_host") != "trade-core"
        or ops.get("target_user_unit") != UNIT_NAME
        or ops.get("effect_receipt_digest") != receipt_raw_digest
        or ops.get("phase_result_digest") != phase_result_digest
        or ops.get("observer_receipt_digest") is not None
        or ops.get("verified") is not True
        or ops.get("operation_digest") != canonical_digest(ops_projection)
        or not completed_at <= observed <= closed < expires
        or expires <= observed
        or (expires - observed).total_seconds() > 15 * 60
    ):
        raise RollforwardError("phase1_closure_semantic_mismatch")

    bundle = None
    if sealed_lineage_bundle is not None:
        bundle, _ = _load_semantic_binding(
            runtime, sealed_lineage_bundle, label="sealed_lineage_bundle"
        )
        try:
            _exact_fields(bundle, PHASE1_LINEAGE_BUNDLE_FIELDS,
                          label="phase1_sealed_lineage_bundle")
            for key in (
                "stage_authorization", "stage_runtime_bindings", "phase1_effect_receipt",
                "phase1_closure", "private_deps_receipt", "staged_board",
            ):
                _raw_binding(bundle[key], label=f"bundle_{key}")
        except (KeyError, TypeError, RollforwardError) as exc:
            raise RollforwardError("phase1_sealed_lineage_bundle_invalid") from exc
        bundle_projection = {
            key: value for key, value in bundle.items() if key != "bundle_digest"
        }
        if (
            bundle.get("schema_version") != "p0b_alr_phase1_sealed_lineage_bundle_v1"
            or bundle.get("target_head") != receipt["target_head"]
            or any(bundle.get(key) != value for key, value in expected_common.items())
            or bundle.get("stage_authorization") != receipt["stage_authorization"]
            or bundle.get("stage_authorization_digest")
            != receipt["stage_authorization_digest"]
            or bundle.get("stage_runtime_bindings") != receipt["stage_runtime_bindings"]
            or bundle.get("stage_runtime_bindings_artifact_digest")
            != receipt["stage_runtime_bindings_artifact_digest"]
            or bundle.get("phase1_effect_receipt") != phase1_receipt
            or bundle.get("phase1_effect_receipt_digest") != receipt_raw_digest
            or bundle.get("phase1_closure") != phase1_closure
            or bundle.get("phase1_closure_digest") != "sha256:" + phase1_closure["sha256"]
            or bundle.get("private_deps_receipt") != sealed["private_deps_receipt"]
            or bundle.get("private_deps_destination") != sealed["private_deps_destination"]
            or bundle.get("private_deps_manifest_sha256")
            != sealed["private_deps_manifest_sha256"]
            or bundle.get("staged_board") != sealed["staged_board"]
            or bundle.get("bundle_digest") != canonical_digest(bundle_projection)
        ):
            raise RollforwardError("phase1_sealed_lineage_bundle_semantic_mismatch")
    return {
        "status": "PHASE1_SEMANTIC_LINEAGE_PASS", "receipt": receipt,
        "closure": closure, "sealed_lineage": sealed, "bundle": bundle,
        "receipt_digest": receipt_raw_digest,
        "closure_raw_digest": "sha256:" + phase1_closure["sha256"],
        "bundle_raw_digest": (
            None if sealed_lineage_bundle is None
            else "sha256:" + sealed_lineage_bundle["sha256"]
        ),
    }


def validate_phase_runtime_bindings(
    bindings: dict[str, Any], authorization: dict[str, Any], *, now: datetime,
    bindings_path: Path | None = None,
) -> None:
    """Validate the sole concrete data-plane input beneath formal authority."""
    _exact_fields(bindings, RUNTIME_BINDINGS_FIELDS, label="artifact")
    phase = authorization["phase"]
    claims = authorization["claim_bindings"]
    if (
        bindings.get("schema_version") != RUNTIME_BINDINGS_SCHEMA
        or bindings.get("phase") != phase
        or bindings.get("intent_id") != authorization["intent_id"]
        or bindings.get("target_head") != authorization["expected_source_head"]
    ):
        raise RollforwardError("runtime_bindings_authority_mismatch")
    observed = parse_utc(bindings.get("observed_at"), label="runtime_bindings_observed")
    expires = parse_utc(bindings.get("expires_at"), label="runtime_bindings_expires")
    if (
        not observed <= now <= expires
        or expires <= observed
        or (expires - observed).total_seconds() > 15 * 60
    ):
        raise RollforwardError("runtime_bindings_expired_or_not_yet_valid")
    projection = {key: value for key, value in bindings.items() if key != "artifact_digest"}
    if (
        bindings.get("artifact_digest") != canonical_digest(projection)
        or claims.get("p0b_phase_runtime_bindings") != bindings.get("artifact_digest")
        or authorization["governance_bindings"].get(
            "phase_runtime_bindings_artifact_digest"
        ) != bindings.get("artifact_digest")
        or (
            bindings_path is not None
            and authorization["governance_bindings"].get(
                "phase_runtime_bindings_path"
            ) != str(bindings_path)
        )
    ):
        raise RollforwardError("runtime_bindings_artifact_digest_invalid")

    section_claims = _exact_fields(
        bindings.get("section_claims"), set(RUNTIME_BINDING_SECTIONS),
        label="section_claims",
    )
    for section, claim_name in RUNTIME_BINDING_SECTIONS.items():
        claim = _exact_fields(
            section_claims.get(section), {"claim", "digest"},
            label=f"section_claims.{section}",
        )
        digest = canonical_digest(bindings[section])
        if (
            claim.get("claim") != claim_name
            or claim.get("digest") != digest
            or claims.get(claim_name) != digest
        ):
            raise RollforwardError(f"runtime_bindings_section_claim_invalid:{section}")

    source = _exact_fields(
        bindings["source_attestation"], SOURCE_ATTESTATION_FIELDS,
        label="source_attestation",
    )
    source_snapshot = source.get("source")
    if (
        not isinstance(source_snapshot, dict)
        or source_snapshot.get("head") != authorization["expected_source_head"]
        or source_snapshot.get("origin_main") != authorization["expected_origin_main_head"]
        or source_snapshot.get("remote_origin_main") != authorization["expected_origin_main_head"]
        or source.get("source_tree_digest") != canonical_digest(source.get("execution_tree"))
        or source.get("source_tree_digest") != authorization["expected_source_tree_digest"]
        or claims.get("p0b_target_source_attestation")
        != canonical_digest(bindings["source_attestation"])
    ):
        raise RollforwardError("runtime_bindings_source_invalid")

    protected = _exact_fields(
        bindings["protected_runtime_baseline"], PROTECTED_BASELINE_FIELDS,
        label="protected_runtime_baseline",
    )
    service = protected.get("service_baseline")
    runtime_identity = protected.get("runtime_identity")
    runtime_identity_fields = {
        "schema_version", "target_host", "target_user_unit", "source_head",
        "invocation_id", "main_pid", "main_pid_start_ticks", "control_group",
        "unit_fragment_path", "unit_file_sha256", "pin_path", "pin_sha256",
        "cost_pin_lock_path", "alpha_pin_lock_path", "nrestarts",
        "active_state", "sub_state", "observed_at",
    }
    _exact_fields(runtime_identity, runtime_identity_fields, label="runtime_identity")
    service_fields = {
        "unit_sha256", "pin_sha256", "unit_head", "pin_head", "active_identity",
        "unit_identity", "pin_identity", "unit_lock_identity",
        "cost_lock_identity", "alpha_lock_identity",
    }
    _exact_fields(service, service_fields, label="service_baseline")
    if (
        protected.get("protected_digest") != canonical_digest(protected.get("protected"))
        or protected.get("pin_consumer_inventory_digest")
        != canonical_digest(protected.get("pin_consumer_inventory"))
        or protected.get("runtime_identity_digest") != canonical_digest(runtime_identity)
        or protected["pin_consumer_inventory_digest"]
        != authorization["expected_pin_consumer_inventory_digest"]
        or protected["runtime_identity_digest"] != authorization["expected_runtime_identity_digest"]
        or claims.get("p0b_protected_runtime_baseline") != protected["protected_digest"]
        or service.get("unit_head") != authorization["expected_old_runtime_source_head"]
        or service.get("pin_head") != authorization["expected_old_runtime_source_head"]
        or "sha256:" + str(service.get("pin_sha256"))
        != authorization["expected_old_pin_digest"]
    ):
        raise RollforwardError("runtime_bindings_protected_invalid")

    paths = _exact_fields(
        bindings["phase_paths"],
        STAGE_PATH_FIELDS if phase == "stage" else CUTOVER_PATH_FIELDS,
        label="phase_paths",
    )
    intent_id = authorization["intent_id"]
    if phase == "stage":
        root = STAGING_ROOT / intent_id
        expected_paths = {
            "staging_root": str(root),
            "cron_destination": str(root / "cron-scratch"),
            "sealed_destination": str(root / "sealed"),
            "publisher_receipt_path": str(root / "staging-publisher-result.json"),
            "private_deps_receipt_path": str(root / "private-deps-receipt.json"),
            "private_deps_destination": str(PRIVATE_BUNDLE_DESTINATION),
            "phase1_receipt_path": str(RECEIPT_DIR / f"{intent_id}.phase1.json"),
            "phase1_closure_path": str(RECEIPT_DIR / f"{intent_id}.phase1.closure.json"),
        }
    else:
        expected_paths = {
            "phase1_receipt_path": str(paths.get("phase1_receipt_path")),
            "phase1_closure_path": str(paths.get("phase1_closure_path")),
            "live_destination": str(EVIDENCE_DIR),
            "provisional_cutover_path": str(RECEIPT_DIR / f"{intent_id}.phase2.provisional.json"),
            "observer_input_path": str(RECEIPT_DIR / f"{intent_id}.phase2.observer-input.json"),
        }
        for key in ("phase1_receipt_path", "phase1_closure_path"):
            if not Path(expected_paths[key]).is_absolute() or "latest" in Path(expected_paths[key]).name.lower():
                raise RollforwardError("runtime_bindings_paths_invalid")
    if paths != expected_paths:
        raise RollforwardError("runtime_bindings_paths_invalid")

    inventories = _exact_fields(
        bindings["inventories"], INVENTORY_FIELDS, label="inventories"
    )
    inventory_pairs = (
        ("live_inventory", "live_inventory_digest"),
        ("completion_inventory", "completion_inventory_digest"),
        ("producer_inventory", "producer_inventory_digest"),
        ("ledger_inventory", "ledger_inventory_digest"),
        ("lane_effective_config", "lane_effective_config_digest"),
    )
    if any(
        inventories[digest_key] != canonical_digest(inventories[value_key])
        for value_key, digest_key in inventory_pairs
    ):
        raise RollforwardError("runtime_bindings_inventory_digest_invalid")
    if (
        claims.get("p0b_live_inventory") != inventories["live_inventory_digest"]
        or claims.get("p0b_completion_inventory")
        != inventories["completion_inventory_digest"]
        or claims.get("p0b_producer_inventory")
        != inventories["producer_inventory_digest"]
    ):
        raise RollforwardError("runtime_bindings_inventory_claim_invalid")

    lineage_fields = STAGE_LINEAGE_FIELDS if phase == "stage" else CUTOVER_LINEAGE_FIELDS
    lineage = _exact_fields(bindings["lineage"], lineage_fields, label="lineage")
    if phase == "stage":
        p0a = _raw_binding(lineage.get("p0a_completed_board_input"), label="p0a_completed_board_input")
        absent = _exact_fields(
            lineage.get("private_bundle_destination_absent"), {"destination", "absent"},
            label="private_bundle_destination_absent",
        )
        if (
            claims.get("p0b_p0a_completed_board_input") != "sha256:" + p0a["sha256"]
            or absent != {"destination": str(PRIVATE_BUNDLE_DESTINATION), "absent": True}
            or claims.get("p0b_private_bundle_destination_absent_attestation")
            != canonical_digest(absent)
        ):
            raise RollforwardError("runtime_bindings_stage_lineage_invalid")
    else:
        for key in (
            "phase1_receipt", "phase1_closure", "sealed_lineage_bundle", "completion",
            "producer_board", "staged_board", "staging_publisher_receipt",
            "private_deps_receipt",
        ):
            _raw_binding(lineage.get(key), label=key)
        lineage_claims = {
            "phase1_receipt": "p0b_phase1_receipt",
            "phase1_closure": "p0b_phase1_closure",
            "sealed_lineage_bundle": "p0b_sealed_lineage_bundle",
            "private_deps_receipt": "p0b_private_bundle_receipt",
            "staged_board": "p0b_staged_candidate_board",
        }
        if any(
            claims.get(claim_name) != "sha256:" + lineage[key]["sha256"]
            for key, claim_name in lineage_claims.items()
        ):
            raise RollforwardError("runtime_bindings_cutover_lineage_invalid")
        if (
            authorization["phase1_effect_receipt_digest"]
            != "sha256:" + lineage["phase1_receipt"]["sha256"]
            or authorization["phase1_closure_digest"]
            != "sha256:" + lineage["phase1_closure"]["sha256"]
            or authorization["sealed_lineage_bundle_digest"]
            != "sha256:" + lineage["sealed_lineage_bundle"]["sha256"]
            or lineage.get("private_deps_destination") != str(PRIVATE_BUNDLE_DESTINATION)
            or lineage.get("private_deps_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
            or not isinstance(lineage.get("max_age_seconds"), int)
            or not 1 <= lineage["max_age_seconds"] <= 172800
            or re.fullmatch(r"[0-9a-f]{32}", str(lineage.get("token", ""))) is None
            or re.fullmatch(r"[0-9a-f]{64}", str(lineage.get("proposed_unit_sha256", ""))) is None
            or any(
                not _governance_digest(lineage.get(key))
                for key in (
                    "completion_inventory_digest", "producer_inventory_digest",
                    "ledger_pre_inventory_digest", "ledger_post_inventory_digest",
                    "lane_effective_config_digest",
                )
            )
            or lineage["completion_inventory_digest"]
            != inventories["completion_inventory_digest"]
            or lineage["producer_inventory_digest"]
            != inventories["producer_inventory_digest"]
            or lineage["ledger_post_inventory_digest"]
            != inventories["ledger_inventory_digest"]
            or lineage["lane_effective_config_digest"]
            != inventories["lane_effective_config_digest"]
        ):
            raise RollforwardError("runtime_bindings_cutover_lineage_invalid")


def derive_internal_plan(
    authorization: dict[str, Any], bindings: dict[str, Any], *,
    authorization_binding: dict[str, str] | None = None,
    runtime_bindings_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Materialize transaction inputs only after both formal layers pass."""
    protected = bindings["protected_runtime_baseline"]
    inventories = bindings["inventories"]
    authorization_binding = authorization_binding or {
        "path": "/tmp/formal-authorization.json",
        "sha256": authorization["authorization_digest"].removeprefix("sha256:"),
    }
    runtime_bindings_binding = runtime_bindings_binding or {
        "path": authorization["governance_bindings"]["phase_runtime_bindings_path"],
        "sha256": bindings["artifact_digest"].removeprefix("sha256:"),
    }
    common = {
        "schema_version": INTERNAL_PLAN_SCHEMA,
        "phase": 1 if authorization["phase"] == "stage" else 2,
        "approval_id": authorization["intent_id"],
        "authorization_digest": authorization["authorization_digest"],
        "target_head": authorization["expected_source_head"],
        "old_head": authorization["expected_old_runtime_source_head"],
        "not_before_utc": authorization["approved_at"],
        "expires_at_utc": min(authorization["expires_at"], bindings["expires_at"]),
        "protected_sha256": protected["protected_digest"],
        "service_baseline": protected["service_baseline"],
        "formal_authority": {
            "authorization": authorization_binding,
            "authorization_digest": authorization["authorization_digest"],
            "runtime_bindings": runtime_bindings_binding,
            "runtime_bindings_artifact_digest": bindings["artifact_digest"],
            "authorized_runtime": {
                key: authorization[key] for key in (
                    "expected_old_runtime_source_head", "expected_old_pin_digest",
                    "expected_source_tree_digest",
                    "expected_pin_consumer_inventory_digest",
                    "expected_runtime_identity_digest",
                )
            },
        },
    }
    if authorization["phase"] == "stage":
        paths = bindings["phase_paths"]
        common["staging"] = {
            "cron_destination": paths["cron_destination"],
            "sealed_destination": paths["sealed_destination"],
            "publisher_receipt_path": paths["publisher_receipt_path"],
            "private_deps_receipt_path": paths["private_deps_receipt_path"],
            "private_deps_destination": paths["private_deps_destination"],
            "private_deps_manifest_sha256": PRIVATE_BUNDLE_MANIFEST_SHA256,
            "expected_head_override": authorization["expected_source_head"],
            "baseline_live_inventory_sha256": inventories["live_inventory_digest"],
            "baseline_ledger_inventory_sha256": inventories["ledger_inventory_digest"],
            "lane_effective_config_sha256": inventories["lane_effective_config_digest"],
            "lane_timeout_seconds": 3600,
        }
    else:
        lineage = bindings["lineage"]
        common["evidence"] = {
            key: lineage[key] for key in (
                "phase1_receipt", "phase1_closure", "sealed_lineage_bundle",
                "completion", "producer_board", "staged_board",
                "staging_publisher_receipt", "private_deps_receipt",
            )
        }
        common["evidence"].update({
            "token": lineage["token"],
            "max_age_seconds": lineage["max_age_seconds"],
            "proposed_unit_sha256": lineage["proposed_unit_sha256"],
            "live_destination": str(EVIDENCE_DIR),
            "live_board_absent": True,
            "live_inventory_sha256": inventories["live_inventory_digest"],
            "completion_inventory_sha256": inventories["completion_inventory_digest"],
            "producer_inventory_sha256": inventories["producer_inventory_digest"],
            "ledger_pre_inventory_sha256": lineage["ledger_pre_inventory_digest"],
            "ledger_post_inventory_sha256": lineage["ledger_post_inventory_digest"],
            "lane_effective_config_sha256": lineage["lane_effective_config_digest"],
            "private_deps_destination": lineage["private_deps_destination"],
            "private_deps_manifest_sha256": lineage["private_deps_manifest_sha256"],
        })
        common["observer"] = {
            "provisional_cutover_path": bindings["phase_paths"]["provisional_cutover_path"],
            "observer_input_path": bindings["phase_paths"]["observer_input_path"],
            "observer_source_digest": authorization["claim_bindings"]["p0b_observer_source"],
        }
        common["lineage_authority"] = {
            "phase1_effect_receipt_digest": authorization["phase1_effect_receipt_digest"],
            "phase1_closure_digest": authorization["phase1_closure_digest"],
            "sealed_lineage_bundle_digest": authorization["sealed_lineage_bundle_digest"],
        }
    return common


def validate_approval(approval: dict[str, Any], *, phase: int, now: datetime) -> None:
    if (
        approval.get("schema_version") != INTERNAL_PLAN_SCHEMA
        or approval.get("phase") != phase
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{7,127}", str(approval.get("approval_id", "")))
        or approval.get("target_head") != TARGET_HEAD
        or approval.get("old_head") != OLD_HEAD
        or not _governance_digest(approval.get("authorization_digest"))
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(approval.get("protected_sha256", ""))) is None
        or not isinstance(approval.get("service_baseline"), dict)
        or not isinstance(approval.get("formal_authority"), dict)
    ):
        raise RollforwardError("approval_binding_mismatch")
    not_before = parse_utc(approval.get("not_before_utc"), label="approval_not_before")
    expires = parse_utc(approval.get("expires_at_utc"), label="approval_expires")
    if not not_before <= now <= expires or expires <= not_before:
        raise RollforwardError("approval_outside_validity_window")
    baseline = approval["service_baseline"]
    formal = approval["formal_authority"]
    if set(formal) != {
        "authorization", "authorization_digest", "runtime_bindings",
        "runtime_bindings_artifact_digest", "authorized_runtime",
    }:
        raise RollforwardError("approval_formal_authority_mismatch")
    _raw_binding(formal.get("authorization"), label="formal_authorization")
    _raw_binding(formal.get("runtime_bindings"), label="formal_runtime_bindings")
    authorized_runtime = _exact_fields(
        formal.get("authorized_runtime"), {
            "expected_old_runtime_source_head", "expected_old_pin_digest",
            "expected_source_tree_digest", "expected_pin_consumer_inventory_digest",
            "expected_runtime_identity_digest",
        }, label="authorized_runtime",
    )
    if (
        formal.get("authorization_digest") != approval["authorization_digest"]
        or not _governance_digest(formal.get("runtime_bindings_artifact_digest"))
        or authorized_runtime.get("expected_old_runtime_source_head") != OLD_HEAD
        or authorized_runtime.get("expected_old_pin_digest") != "sha256:" + OLD_PIN_SHA256
        or any(
            not _governance_digest(authorized_runtime.get(key))
            for key in (
                "expected_source_tree_digest",
                "expected_pin_consumer_inventory_digest",
                "expected_runtime_identity_digest",
            )
        )
    ):
        raise RollforwardError("approval_formal_authority_mismatch")
    required_identity = {"sha256", "dev", "ino", "uid", "gid", "mode", "nlink", "size"}
    unit_identity = baseline.get("unit_identity")
    pin_identity = baseline.get("pin_identity")
    lock_identity = baseline.get("unit_lock_identity")
    cost_lock_identity = baseline.get("cost_lock_identity")
    alpha_lock_identity = baseline.get("alpha_lock_identity")
    active = baseline.get("active_identity")
    if (
        baseline.get("unit_sha256") != OLD_UNIT_SHA256
        or baseline.get("pin_sha256") != OLD_PIN_SHA256
        or baseline.get("unit_head") != OLD_HEAD
        or baseline.get("pin_head") != OLD_HEAD
        or not isinstance(unit_identity, dict)
        or not required_identity.issubset(unit_identity)
        or unit_identity.get("sha256") != OLD_UNIT_SHA256
        or not isinstance(pin_identity, dict)
        or not required_identity.issubset(pin_identity)
        or pin_identity.get("sha256") != OLD_PIN_SHA256
        or not isinstance(active, dict)
        or not {"MainPID", "ProcessStartTicks", "InvocationID", "NRestarts", "ControlGroup", "ALRSourceHead"}.issubset(active)
        or not str(active.get("MainPID", "")).isdigit()
        or int(active.get("MainPID", 0)) <= 0
        or not str(active.get("ProcessStartTicks", "")).isdigit()
        or re.fullmatch(r"[0-9a-f]{32}", str(active.get("InvocationID", ""))) is None
        or active.get("NRestarts") not in {0, "0"}
        or not str(active.get("ControlGroup", "")).startswith("/")
        or active.get("ALRSourceHead") != OLD_HEAD
        or not isinstance(lock_identity, dict)
        or not {"dev", "ino", "uid", "gid", "mode", "nlink"}.issubset(lock_identity)
        or lock_identity.get("uid") != 1000
        or lock_identity.get("gid") != 1000
        or lock_identity.get("mode") != 0o600
        or lock_identity.get("nlink") != 1
        or not isinstance(cost_lock_identity, dict)
        or not {"dev", "ino", "uid", "gid", "mode", "nlink"}.issubset(cost_lock_identity)
        or cost_lock_identity.get("uid") != 1000
        or cost_lock_identity.get("gid") != 1000
        or cost_lock_identity.get("mode") != 0o600
        or cost_lock_identity.get("nlink") != 1
        or not isinstance(alpha_lock_identity, dict)
        or not {"dev", "ino", "uid", "gid", "mode", "nlink"}.issubset(alpha_lock_identity)
        or alpha_lock_identity.get("uid") != 1000
        or alpha_lock_identity.get("gid") != 1000
        or alpha_lock_identity.get("mode") != 0o600
        or alpha_lock_identity.get("nlink") != 1
    ):
        raise RollforwardError("approval_service_baseline_mismatch")
    if phase == 1:
        staging = approval.get("staging")
        if not isinstance(staging, dict):
            raise RollforwardError("staging_binding_missing")
        expected_root = STAGING_ROOT / str(approval["approval_id"])
        if (
            Path(str(staging.get("cron_destination", ""))) != expected_root / "cron-scratch"
            or Path(str(staging.get("sealed_destination", ""))) != expected_root / "sealed"
            or Path(str(staging.get("publisher_receipt_path", "")))
            != expected_root / "staging-publisher-result.json"
            or Path(str(staging.get("private_deps_receipt_path", "")))
            != expected_root / "private-deps-receipt.json"
            or staging.get("private_deps_destination") != str(PRIVATE_BUNDLE_DESTINATION)
            or staging.get("private_deps_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
            or staging.get("expected_head_override") != TARGET_HEAD
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(staging.get("baseline_live_inventory_sha256", ""))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(staging.get("baseline_ledger_inventory_sha256", ""))) is None
            or staging.get("lane_effective_config_sha256")
            != Runtime.lane_effective_config_sha256()
        ):
            raise RollforwardError("noncanonical_staging_binding")
    if phase == 2:
        evidence = approval.get("evidence")
        observer = approval.get("observer")
        lineage_authority = approval.get("lineage_authority")
        if (
            not isinstance(evidence, dict)
            or not isinstance(observer, dict)
            or not isinstance(lineage_authority, dict)
        ):
            raise RollforwardError("phase2_evidence_binding_missing")
        if (
            set(lineage_authority) != {
                "phase1_effect_receipt_digest", "phase1_closure_digest",
                "sealed_lineage_bundle_digest",
            }
            or lineage_authority != {
                "phase1_effect_receipt_digest": "sha256:" + evidence["phase1_receipt"]["sha256"],
                "phase1_closure_digest": "sha256:" + evidence["phase1_closure"]["sha256"],
                "sealed_lineage_bundle_digest": "sha256:" + evidence["sealed_lineage_bundle"]["sha256"],
            }
        ):
            raise RollforwardError("phase2_lineage_authority_mismatch")
        expected_observer_paths = {
            "provisional_cutover_path": str(
                RECEIPT_DIR / f"{approval['approval_id']}.phase2.provisional.json"
            ),
            "observer_input_path": str(
                RECEIPT_DIR / f"{approval['approval_id']}.phase2.observer-input.json"
            ),
            "observer_source_digest": "sha256:" + OBSERVER_V2_SHA256,
        }
        if observer != expected_observer_paths:
            raise RollforwardError("phase2_observer_binding_invalid")
        for key in (
            "phase1_receipt", "phase1_closure", "sealed_lineage_bundle",
            "completion", "producer_board", "staged_board", "staging_publisher_receipt",
            "private_deps_receipt",
        ):
            binding = evidence.get(key)
            if (
                not isinstance(binding, dict)
                or not Path(str(binding.get("path", ""))).is_absolute()
                or re.fullmatch(r"[0-9a-f]{64}", str(binding.get("sha256", ""))) is None
            ):
                raise RollforwardError(f"invalid_evidence_binding:{key}")
        if (
            not re.fullmatch(r"[0-9a-f]{32}", str(evidence.get("token", "")))
            or not isinstance(evidence.get("max_age_seconds"), int)
            or not 1 <= evidence["max_age_seconds"] <= 172800
            or re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("proposed_unit_sha256", ""))) is None
            or evidence.get("live_destination") != str(EVIDENCE_DIR)
            or evidence.get("live_board_absent") is not True
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(evidence.get("live_inventory_sha256", ""))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(evidence.get("completion_inventory_sha256", ""))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(evidence.get("producer_inventory_sha256", ""))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(evidence.get("ledger_pre_inventory_sha256", ""))) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", str(evidence.get("ledger_post_inventory_sha256", ""))) is None
            or evidence.get("lane_effective_config_sha256")
            != Runtime.lane_effective_config_sha256()
            or evidence.get("private_deps_destination") != str(PRIVATE_BUNDLE_DESTINATION)
            or evidence.get("private_deps_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
        ):
            raise RollforwardError("invalid_phase2_evidence_constants")


def require_identity(observed: dict[str, Any], expected: dict[str, Any], *, label: str) -> None:
    if any(observed.get(key) != value for key, value in expected.items()):
        raise RollforwardError(f"approved_identity_drift:{label}")


def assert_no_authority(board: dict[str, Any]) -> dict[str, bool]:
    safe_strings = {"", "DENIED", "DISABLED", "FALSE", "NONE", "NOT_GRANTED", "NO_AUTHORITY"}
    def safe(value: Any) -> bool:
        return value is False or value is None or (
            isinstance(value, str) and value.upper() in safe_strings
        )
    def visit(value: Any, path: str = "board") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                sensitive = (
                    any(domain in lowered and "authority" in lowered
                        for domain in ("order", "probe", "promotion", "runtime"))
                    or lowered == "promotion_evidence"
                )
                if sensitive and not safe(child):
                    raise RollforwardError(f"authority_grant_present:{path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
    if board.get("order_authority") != "NOT_GRANTED" or board.get("promotion_evidence") is not False:
        raise RollforwardError("board_authority_not_denied")
    visit(board)
    return {"order": False, "probe": False, "promotion": False, "runtime": False}


class Runtime:
    def __init__(
        self, approval: dict[str, Any] | None = None, *, discover: bool = False
    ) -> None:
        self.approval = approval or {}
        base = load_pin_engine()
        if discover:
            completed = subprocess.run(
                ["/usr/bin/git", "rev-parse", "HEAD"], cwd=REPO, env=SYSTEM_ENV,
                text=True, capture_output=True, timeout=30, check=False,
            )
            if completed.returncode != 0:
                raise RollforwardError("capture_source_head_unavailable")
            target_head = completed.stdout.strip()
            pin_raw, pin_identity = base.read_regular_bytes(PIN_PATH)
            pin_payload = strict_json(pin_raw, label="capture_generation_pin")
            old_head = str(pin_payload.get("head", ""))
            _unit_raw, unit_identity = base.read_regular_bytes(UNIT_PATH)
            configure_runtime_generation(
                target_head=target_head, old_head=old_head,
                old_pin_sha256=pin_identity["sha256"],
                old_unit_sha256=unit_identity["sha256"],
            )
        if not all((TARGET_HEAD, OLD_HEAD, OLD_PIN_SHA256, OLD_UNIT_SHA256)):
            raise RollforwardError("runtime_generation_not_bound")
        pin_raw, pin_identity = base.read_regular_bytes(PIN_PATH)
        pin_payload = strict_json(pin_raw, label="generation_pin_binding")
        if (
            pin_identity.get("sha256") != OLD_PIN_SHA256
            or pin_payload.get("head") != OLD_HEAD
            or not isinstance(pin_identity.get("ino"), int)
        ):
            raise RollforwardError("runtime_old_pin_binding_mismatch")
        self.pin = load_pin_engine(generation={
            "expected_head": TARGET_HEAD,
            "old_head": OLD_HEAD,
            "old_pin_sha256": OLD_PIN_SHA256,
            "old_pin_base64": base64.b64encode(pin_raw).decode("ascii"),
            "expected_old_pin_ino": pin_identity["ino"],
        })

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def command_allowed(command: list[str], *, mutate: bool) -> bool:
        if mutate:
            return command in (
                [SYSTEMD, "--user", "stop", UNIT_NAME],
                [SYSTEMD, "--user", "daemon-reload"],
                [SYSTEMD, "--user", "reset-failed", UNIT_NAME],
                [SYSTEMD, "--user", "restart", UNIT_NAME],
            )
        if command == ["/usr/bin/git", "rev-parse", "origin/main"]:
            return True
        if command in (
            ["/usr/bin/git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            ["/usr/bin/git", "rev-parse", "HEAD"],
            ["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"],
            ["/usr/bin/git", "ls-files", "-z"],
            ["/usr/bin/git", "ls-files", "--stage", "-z"],
            ["/usr/bin/git", "rev-parse", "HEAD:program_code/ml_training"],
            ["/usr/bin/git", "rev-parse", "--git-path", "index"],
            [
                "/usr/bin/git", "ls-tree", "HEAD", "--",
                "program_code/ml_training/alr_event_consumer.py",
            ],
        ):
            return True
        if command == [
            "/usr/bin/git", "ls-remote", "--exit-code", "origin", "refs/heads/main"
        ]:
            return True
        if len(command) >= 6 and command[:5] == ["/usr/bin/git", "ls-tree", "-r", "HEAD", "--"]:
            return all(not value.startswith("-") and ".." not in value for value in command[5:])
        if command == [SYSTEMD, "--user", "list-jobs", "--no-legend", "--no-pager"]:
            return True
        if command == [
            SYSTEMD, "--user", "list-units", "--type=scope", "--state=active",
            "--no-legend", "--no-pager",
        ]:
            return True
        if command == [
            SYSTEMD, "--user", "list-unit-files", "--type=service",
            "--no-legend", "--no-pager",
        ]:
            return True
        if len(command) >= 5 and command[:3] == [SYSTEMD, "--user", "show"]:
            if re.fullmatch(r"[A-Za-z0-9@_.:-]+\.service", command[3]) is None:
                return False
            tail = command[4:]
            known_unit = command[3] in {
                UNIT_NAME, "openclaw-trading-api.service", "openclaw-watchdog.service"
            }
            permitted = set(SERVICE_PROPERTIES) if known_unit else {
                "LoadState", "NeedDaemonReload", "FragmentPath", "DropInPaths"
            }
            return len(tail) % 2 == 0 and all(
                tail[index] == "-p" and tail[index + 1] in permitted
                for index in range(0, len(tail), 2)
            )
        return command == ["/usr/bin/crontab", "-l"]

    def run(self, command: list[str], *, mutate: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if not self.command_allowed(command, mutate=mutate):
            raise RollforwardError("command_not_allowlisted")
        completed = subprocess.run(
            command, cwd=cwd, env=SYSTEM_ENV, text=True, capture_output=True,
            timeout=30, check=False,
        )
        if completed.returncode != 0:
            raise RollforwardError(f"command_failed:{Path(command[0]).name}:{command[-1]}")
        return completed

    def source_snapshot(self) -> dict[str, Any]:
        branch = self.run(
            ["/usr/bin/git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=REPO
        ).stdout.strip()
        head = self.run(["/usr/bin/git", "rev-parse", "HEAD"], cwd=REPO).stdout.strip()
        status_text = self.run(
            ["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=REPO,
        ).stdout
        origin = self.run(["/usr/bin/git", "rev-parse", "origin/main"], cwd=REPO).stdout.strip()
        remote_raw = self.run(
            ["/usr/bin/git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
            cwd=REPO,
        ).stdout
        remote_lines = remote_raw.splitlines()
        expected_remote = f"{TARGET_HEAD}\trefs/heads/main"
        if (
            branch != "main"
            or head != TARGET_HEAD
            or status_text != ""
            or origin != TARGET_HEAD
            or remote_lines != [expected_remote]
            or os.getuid() != 1000
            or os.getgid() != 1000
        ):
            raise RollforwardError("target_no_longer_current")
        return {
            "branch": branch, "head": head, "clean": True,
            "origin_main": origin, "remote_origin_main": TARGET_HEAD,
            "uid": os.getuid(), "gid": os.getgid(),
        }

    @staticmethod
    def lane_environment(staging: dict[str, Any]) -> dict[str, str]:
        """Return the complete admission environment; inherited values are forbidden."""
        config = Runtime.lane_effective_config()
        return {
            **SYSTEM_ENV,
            "OPENCLAW_BASE_DIR": str(REPO),
            "OPENCLAW_DATA_DIR": str(DATA),
            "OPENCLAW_SECRETS_ROOT": str(SECRETS_ROOT),
            "OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON": str(STANDING_AUTH_PATH),
            "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD": TARGET_HEAD,
            "OPENCLAW_EXPECTED_SOURCE_HEAD": TARGET_HEAD,
            "OPENCLAW_COST_GATE_LEARNING_LEDGER": config["ledger_path"],
            "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS": str(
                int(config["materialize_rejects"])
            ),
            "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS": str(
                int(config["append_materialized_rejects"])
            ),
            "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES": str(
                int(config["append_outcomes"])
            ),
            "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES": str(
                int(config["record_probe_outcomes"])
            ),
            "OPENCLAW_CRON_OOM_VICTIM_SCORE": "800",
            "ALR_CANDIDATE_EVIDENCE_DIR": str(staging["cron_destination"]),
        }

    @staticmethod
    def lane_effective_config() -> dict[str, Any]:
        return {
            "ledger_path": str(LEDGER_PATH),
            "materialize_rejects": True,
            "append_materialized_rejects": True,
            "append_outcomes": True,
            "record_probe_outcomes": False,
        }

    @staticmethod
    def lane_effective_config_sha256() -> str:
        return canonical_digest(Runtime.lane_effective_config())

    def lane_snapshot(self) -> dict[str, Any]:
        return {
            "cost": self.pin.assert_lane_quiescent(),
            "alpha": self.alpha_lane_snapshot(),
        }

    def alpha_lane_snapshot(self) -> dict[str, Any]:
        processes: list[int] = []
        own_pid = os.getpid()
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit() or int(proc.name) == own_pid:
                continue
            try:
                command = (proc / "cmdline").read_bytes().replace(b"\0", b" ")
            except OSError:
                continue
            if b"alpha_discovery_throughput_cron.sh" in command:
                processes.append(int(proc.name))
        raw_scopes = self.run([
            SYSTEMD, "--user", "list-units", "--type=scope", "--state=active",
            "--no-legend", "--no-pager",
        ]).stdout
        scopes = sorted(
            line.split()[0] for line in raw_scopes.splitlines()
            if line.strip() and line.split()[0].startswith("openclaw-research-alpha-")
        )
        if ALPHA_OWNER.exists() or processes or scopes:
            raise RollforwardError("alpha_natural_lane_not_quiescent")
        return {"owner_exists": False, "processes": [], "active_alpha_scopes": []}

    @staticmethod
    def crontab_consumers_from_text(raw: str) -> dict[str, Any]:
        active = [
            line.strip() for line in raw.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        generation_names = (
            "OPENCLAW_EXPECTED_SOURCE_HEAD",
            "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD",
            "ALR_SOURCE_HEAD",
        )
        overrides = sorted(
            name for name in generation_names
            if any(re.search(rf"(^|\s){re.escape(name)}=", line) for line in active)
        )
        if overrides:
            raise RollforwardError("inline_generation_override_present")
        consumers: dict[str, Any] = {"generation_overrides": []}
        for lane, script in (
            ("cost", "cost_gate_learning_lane_cron.sh"),
            ("alpha", "alpha_discovery_throughput_cron.sh"),
        ):
            lines = [line for line in active if script in line]
            if len(lines) != 1:
                raise RollforwardError(f"global_pin_consumer_count:{lane}")
            consumers[lane] = {
                "count": 1,
                "line_sha256": sha256_bytes(lines[0].encode()),
            }
        consumers["active_crontab_sha256"] = sha256_bytes(raw.encode())
        return consumers

    def global_pin_consumers(self) -> dict[str, Any]:
        return self.crontab_consumers_from_text(
            self.run(["/usr/bin/crontab", "-l"]).stdout
        )

    def protected_snapshot(self) -> dict[str, Any]:
        crontab_raw = self.run(["/usr/bin/crontab", "-l"]).stdout
        global_consumers = self.crontab_consumers_from_text(crontab_raw)
        return {
            "units": {
                name: self.protected_unit_snapshot(name)
                for name in ("openclaw-trading-api.service", "openclaw-watchdog.service")
            },
            "engine": self.protected_engine_processes(),
            "auth_metadata": self.pin.auth_metadata(),
            "crontab": {
                "sha256": sha256_bytes(crontab_raw.encode()),
                "bytes": len(crontab_raw.encode()),
                "generation_overrides": [],
            },
            "global_pin_consumers": global_consumers,
            "user_unit_inventory": self.user_unit_inventory(),
            "user_manager_jobs": self.no_queued_job(),
            # Policy is non-secret and content-bound; DSN remains metadata-only.
            "policy": metadata(POLICY_PATH, include_hash=True),
            "dsn_metadata": metadata(DSN_PATH, include_hash=False),
        }

    @staticmethod
    def _openclaw_engine_pid_candidates(
        proc_root: Path = Path("/proc"),
    ) -> list[int]:
        candidates: list[int] = []
        for proc in proc_root.iterdir():
            if not proc.name.isdigit():
                continue
            try:
                comm = (proc / "comm").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if comm == "openclaw-engine":
                candidates.append(int(proc.name))
        return sorted(candidates)

    def protected_engine_processes(self) -> list[dict[str, Any]]:
        """Bind exact engine identity when present and exact stable absence otherwise."""

        try:
            sealed = self.pin.engine_processes()
        except Exception as exc:
            if str(exc) != "engine_process_topology_mismatch":
                raise
            sealed = []
        sealed_pids = sorted(int(row["pid"]) for row in sealed)
        if self._openclaw_engine_pid_candidates() != sealed_pids:
            raise RollforwardError("protected_engine_process_topology_invalid")
        time.sleep(0.05)
        if self._openclaw_engine_pid_candidates() != sealed_pids:
            raise RollforwardError("protected_engine_process_topology_invalid")
        return sealed

    def protected_unit_snapshot(self, name: str) -> dict[str, str]:
        properties = (
            "LoadState", "ActiveState", "SubState", "MainPID",
            "ExecMainStartTimestampMonotonic", "NRestarts", "InvocationID",
            "FragmentPath", "DropInPaths", "ControlGroup", "NeedDaemonReload",
        )
        command = [SYSTEMD, "--user", "show", name]
        for prop in properties:
            command.extend(["-p", prop])
        raw = self.run(command).stdout
        result = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        if (
            result.get("LoadState") != "loaded"
            or result.get("ActiveState") != "active"
            or result.get("SubState") != "running"
            or result.get("NeedDaemonReload") != "no"
            or result.get("DropInPaths") != ""
            or re.fullmatch(
                r"(?:0|[1-9][0-9]*)", str(result.get("NRestarts", ""))
            ) is None
        ):
            raise RollforwardError(f"protected_unit_not_stable:{name}")
        return result

    def user_unit_inventory(self) -> dict[str, Any]:
        listed = self.run([
            SYSTEMD, "--user", "list-unit-files", "--type=service",
            "--no-legend", "--no-pager",
        ]).stdout
        names = sorted({
            line.split()[0] for line in listed.splitlines()
            if line.strip() and re.fullmatch(r"[A-Za-z0-9@_.:-]+\.service", line.split()[0])
        })
        if not names:
            raise RollforwardError("user_unit_inventory_empty")
        result: dict[str, Any] = {}
        for name in names:
            command = [SYSTEMD, "--user", "show", name]
            for prop in ("LoadState", "NeedDaemonReload", "FragmentPath", "DropInPaths"):
                command.extend(["-p", prop])
            raw = self.run(command).stdout
            values = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
            if values.get("NeedDaemonReload") != "no":
                raise RollforwardError(f"user_unit_reload_pending:{name}")
            fragment_path = Path(values.get("FragmentPath", ""))
            if values.get("LoadState") != "loaded" or not fragment_path.is_absolute():
                raise RollforwardError(f"user_unit_disk_identity_missing:{name}")
            try:
                dropins = [Path(value) for value in shlex.split(values.get("DropInPaths", ""))]
            except ValueError as exc:
                raise RollforwardError(f"user_unit_dropins_invalid:{name}") from exc
            if any(not path.is_absolute() for path in dropins):
                raise RollforwardError(f"user_unit_dropins_invalid:{name}")
            result[name] = {
                "fragment": metadata(fragment_path, include_hash=True),
                "dropins": [metadata(path, include_hash=True) for path in dropins],
            }
        return result

    def service_snapshot(self, *, require_active: bool | None) -> dict[str, Any]:
        command = [SYSTEMD, "--user", "show", UNIT_NAME]
        for prop in SERVICE_PROPERTIES:
            command.extend(["-p", prop])
        raw = self.run(command).stdout
        values = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        try:
            environment = shlex.split(values.get("Environment", ""))
        except ValueError as exc:
            raise RollforwardError("manager_environment_invalid") from exc
        heads = [item.split("=", 1)[1] for item in environment if item.startswith("ALR_SOURCE_HEAD=")]
        if (
            values.get("LoadState") != "loaded"
            or values.get("FragmentPath") != str(UNIT_PATH)
            or values.get("DropInPaths") != ""
            or values.get("NeedDaemonReload") != "no"
            or len(heads) != 1
        ):
            raise RollforwardError("alr_manager_identity_mismatch")
        values["ALRSourceHead"] = heads[0]
        pid = int(values.get("MainPID") or "0")
        values["ProcessStartTicks"] = self.pin.process_start_ticks(pid) if pid else ""
        if require_active is True and (
            values.get("ActiveState") != "active" or values.get("SubState") != "running"
            or pid <= 0 or values.get("NRestarts") != "0"
            or not values.get("InvocationID") or not values["ProcessStartTicks"]
        ):
            raise RollforwardError("alr_not_stable_active")
        if require_active is False and (
            values.get("ActiveState") not in {"inactive", "failed"}
            or values.get("SubState") not in {"dead", "failed"} or pid != 0
        ):
            raise RollforwardError("alr_not_stopped")
        return values

    def unit_snapshot(self, *, expected_head: str) -> dict[str, Any]:
        raw, identity = self.pin.read_regular_bytes(UNIT_PATH)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RollforwardError("unit_not_utf8") from exc
        head_lines = re.findall(r"(?m)^ALR_SOURCE_HEAD=([0-9a-f]{40})$", text)
        if head_lines != [expected_head]:
            raise RollforwardError("unit_source_head_mismatch")
        return {"raw": raw, "identity": identity, "head": expected_head}

    def pin_snapshot(self, *, expected_head: str) -> dict[str, Any]:
        raw, identity = self.pin.read_regular_bytes(PIN_PATH)
        payload = strict_json(raw, label="generation_pin")
        if payload.get("head") != expected_head:
            raise RollforwardError("generation_pin_head_mismatch")
        if expected_head == OLD_HEAD and identity.get("sha256") != OLD_PIN_SHA256:
            raise RollforwardError("old_generation_pin_hash_mismatch")
        if expected_head == TARGET_HEAD:
            self.pin.post_generation_match()
        return {"identity": identity, "payload": payload}

    def no_queued_job(self) -> dict[str, Any]:
        raw = self.run([SYSTEMD, "--user", "list-jobs", "--no-legend", "--no-pager"]).stdout
        jobs = [line for line in raw.splitlines() if line.strip()]
        if jobs:
            raise RollforwardError("user_manager_job_queued")
        return {"status": "NO_QUEUED_JOB", "inventory_sha256": canonical_digest([])}

    def unit_lock_snapshot(self) -> dict[str, Any]:
        return self.lock_snapshot(UNIT_LOCK, label="unit")

    @staticmethod
    def lock_snapshot(path: Path, *, label: str) -> dict[str, Any]:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise RollforwardError(f"{label}_lock_not_regular")
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(fd)
        finally:
            os.close(fd)
        result = {
            "dev": opened.st_dev, "ino": opened.st_ino,
            "uid": opened.st_uid, "gid": opened.st_gid,
            "mode": stat.S_IMODE(opened.st_mode), "nlink": opened.st_nlink,
        }
        if (
            (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or result["uid"] != 1000
            or result["gid"] != 1000
            or result["mode"] != 0o600
            or result["nlink"] != 1
        ):
            raise RollforwardError(f"{label}_lock_identity_invalid")
        return result

    def execution_tree_lease(self) -> dict[str, Any]:
        paths = [
            "helper_scripts/cron/cost_gate_learning_lane_cron.sh",
            "helper_scripts/cron/lib",
            "helper_scripts/research/cost_gate_learning_lane",
            "program_code/ml_training",
        ]
        command = ["/usr/bin/git", "ls-tree", "-r", "HEAD", "--", *paths]
        raw = self.run(command, cwd=REPO).stdout.encode()
        if not raw:
            raise RollforwardError("execution_tree_lease_empty")
        cron_identity = metadata(LANE_CRON, include_hash=True)
        publisher_identity = metadata(PUBLISHER, include_hash=True)
        helper_identity = metadata(PIN_HELPER, include_hash=True)
        if cron_identity["sha256"] != LANE_CRON_SHA256 or publisher_identity["sha256"] != PUBLISHER_SHA256:
            raise RollforwardError("execution_entrypoint_hash_drift")
        return {
            "git_tree_listing_sha256": sha256_bytes(raw),
            "git_tree_entries": len(raw.splitlines()),
            "cron_sha256": cron_identity["sha256"],
            "publisher_sha256": publisher_identity["sha256"],
            "generation_pin_helper_sha256": helper_identity["sha256"],
        }

    def artifact_inventory(self, directory: Path, pattern: str) -> dict[str, str]:
        if not directory.exists():
            return {}
        result: dict[str, str] = {}
        for path in sorted(directory.glob(pattern)):
            if path.is_symlink() or not path.is_file():
                raise RollforwardError(f"unsafe_inventory_entry:{directory.name}")
            identity = metadata(path, include_hash=True)
            if identity["nlink"] < 1:
                raise RollforwardError("invalid_inventory_link_count")
            result[path.name] = identity["sha256"]
        return result

    @staticmethod
    def ledger_inventory(directory: Path = PRODUCER_DIR) -> dict[str, dict[str, Any]]:
        """Stream and bind every canonical retained-ledger shard without following links."""
        if not directory.exists():
            raise RollforwardError("retained_ledger_directory_missing")
        name_pattern = re.compile(r"probe_ledger(?:[._-][A-Za-z0-9][A-Za-z0-9._-]*)?\.jsonl")
        result: dict[str, dict[str, Any]] = {}
        for path in sorted(directory.glob("probe_ledger*.jsonl")):
            if name_pattern.fullmatch(path.name) is None:
                raise RollforwardError("noncanonical_ledger_entry")
            before = path.lstat()
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
                raise RollforwardError("unsafe_ledger_entry")
            fd = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                opened = os.fstat(fd)
                digest = hashlib.sha256()
                byte_count = 0
                newline_count = 0
                final_byte = b""
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    byte_count += len(chunk)
                    newline_count += chunk.count(b"\n")
                    final_byte = chunk[-1:]
                final = os.fstat(fd)
            finally:
                os.close(fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or (final.st_dev, final.st_ino) != (opened.st_dev, opened.st_ino)
                or final.st_size != opened.st_size
                or final.st_mtime_ns != opened.st_mtime_ns
                or byte_count != opened.st_size
            ):
                raise RollforwardError("unsafe_ledger_entry")
            result[path.name] = {
                "sha256": digest.hexdigest(),
                "bytes": byte_count,
                "lines": newline_count + int(byte_count > 0 and final_byte != b"\n"),
                "dev": opened.st_dev,
                "ino": opened.st_ino,
                "uid": opened.st_uid,
                "gid": opened.st_gid,
                "mode": stat.S_IMODE(opened.st_mode),
                "nlink": opened.st_nlink,
            }
        if "probe_ledger.jsonl" not in result:
            raise RollforwardError("canonical_retained_ledger_missing")
        return result

    def lane_inventories(self, *, staging: dict[str, Any]) -> dict[str, Any]:
        return {
            "completion": self.artifact_inventory(COMPLETION_DIR, "*.completion.json"),
            "producer": self.artifact_inventory(PRODUCER_DIR, "blocked_outcome_review_*.json"),
            "cron_staging": self.artifact_inventory(Path(staging["cron_destination"]), "blocked_outcome_review_*.json"),
            "sealed_staging": self.artifact_inventory(Path(staging["sealed_destination"]), "blocked_outcome_review_*.json"),
            "live": self.artifact_inventory(EVIDENCE_DIR, "blocked_outcome_review_*.json"),
        }

    def generation_fence_snapshot(self) -> dict[str, str]:
        completion = self.artifact_inventory(COMPLETION_DIR, "*.completion.json")
        producer = self.artifact_inventory(PRODUCER_DIR, "blocked_outcome_review_*.json")
        ledger = self.ledger_inventory()
        return {
            "completion_inventory_sha256": self.inventory_digest(completion),
            "producer_inventory_sha256": self.inventory_digest(producer),
            "ledger_post_inventory_sha256": self.inventory_digest(ledger),
            "lane_effective_config_sha256": self.lane_effective_config_sha256(),
        }

    @staticmethod
    def inventory_digest(inventory: dict[str, str]) -> str:
        return canonical_digest(inventory)

    def persist_path(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        require_private_directory(path.parent)
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise RollforwardError("durable_ledger_short_write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        parent = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return {"path": str(path), "sha256": sha256_bytes(raw), "size": len(raw)}

    def stage_private_dependencies(self, receipt_path: Path) -> dict[str, Any]:
        stager = load_private_bundle_stager()
        if receipt_path.exists() or PRIVATE_BUNDLE_DESTINATION.exists():
            raise RollforwardError("private_bundle_destination_or_receipt_exists")
        result = stager.stage_bundle(
            source_root=stager.SOURCE_ROOT,
            destination_parent=stager.DESTINATION_PARENT,
            destination_name=stager.DESTINATION_NAME,
            manifest=stager.SEALED_MANIFEST,
            apply=True,
            strict_anchors=True,
        )
        expected_boundaries = {
            "service_mutation": False,
            "database_access": False,
            "broker_contact": False,
            "credential_access": False,
            "subprocess_spawned": False,
            "source_repository_mutation": False,
        }
        if (
            result.get("schema_version") != "p0b_psycopg_private_bundle_stage_v1"
            or result.get("status") != "APPLIED_POSTCHECK_PASS"
            or result.get("destination") != str(PRIVATE_BUNDLE_DESTINATION)
            or result.get("source_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
            or result.get("destination_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
            or result.get("mutation_performed") is not True
            or result.get("boundaries") != expected_boundaries
        ):
            raise RollforwardError("private_bundle_stage_not_applied_postcheck_pass")
        receipt = self.persist_path(receipt_path, result)
        return {
            "private_deps_receipt": {
                "path": receipt["path"], "sha256": receipt["sha256"]
            },
            "private_deps_destination": str(PRIVATE_BUNDLE_DESTINATION),
            "private_deps_manifest_sha256": PRIVATE_BUNDLE_MANIFEST_SHA256,
        }

    def stage_lane(self, before: dict[str, Any]) -> dict[str, Any]:
        staging = self.approval["staging"]
        if self.source_snapshot() != before["source"] or self.execution_tree_lease() != before["execution_tree"]:
            raise RollforwardError("staging_start_source_lease_drift")
        cron_destination = Path(staging["cron_destination"])
        sealed_destination = Path(staging["sealed_destination"])
        publisher_receipt_path = Path(staging["publisher_receipt_path"])
        private_deps_receipt_path = Path(staging["private_deps_receipt_path"])
        for directory in (STAGING_ROOT, cron_destination.parent):
            directory.mkdir(mode=0o700, exist_ok=True)
            require_private_directory(directory)
        for path in (cron_destination, sealed_destination):
            if path.exists():
                raise RollforwardError("staging_destination_must_be_absent")
            path.mkdir(mode=0o700, exist_ok=False)
            require_private_directory(path)
        started = self.now()
        env = self.lane_environment(staging)
        timeout = int(staging.get("lane_timeout_seconds", 10800))
        if not 60 <= timeout <= 10800:
            raise RollforwardError("lane_timeout_invalid")
        availability_samples: list[dict[str, Any]] = []

        def monitor_alr() -> dict[str, Any]:
            sample = self.alr_availability_probe(before["service"])
            availability_samples.append(sample)
            return sample

        completed = self.run_contained(
            [str(LANE_CRON)], cwd=REPO, env=env, timeout=timeout,
            monitor=monitor_alr, monitor_interval=2.0,
        )
        if completed.returncode != 0:
            raise RollforwardError("normal_lane_nonzero")
        after = self.lane_inventories(staging=staging)
        ledger_after = self.ledger_inventory()
        new_completion = sorted(set(after["completion"]) - set(before["inventories"]["completion"]))
        new_producer = sorted(set(after["producer"]) - set(before["inventories"]["producer"]))
        new_cron = sorted(set(after["cron_staging"]) - set(before["inventories"]["cron_staging"]))
        if len(new_completion) != 1 or len(new_producer) != 1 or len(new_cron) != 1:
            raise RollforwardError("lane_exactly_one_new_artifact_set_required")
        completion_path = COMPLETION_DIR / new_completion[0]
        producer_path = PRODUCER_DIR / new_producer[0]
        cron_board_path = cron_destination / new_cron[0]
        completion_raw, completion_id = self.pin.read_regular_bytes(completion_path)
        producer_raw, producer_id = self.pin.read_regular_bytes(producer_path)
        cron_raw, cron_id = self.pin.read_regular_bytes(cron_board_path)
        completion = strict_json(completion_raw, label="staging_completion")
        if (
            completion.get("schema_version") != "research_workload_completion_v1"
            or completion.get("lane") != "cost"
            or completion.get("status") != "COMPLETE"
            or completion.get("source_head") != TARGET_HEAD
            or completion.get("completion_paths") != [str(producer_path)]
            or completion.get("sha256_by_path") != {str(producer_path): producer_id["sha256"]}
            or producer_path.name != cron_board_path.name
            or producer_raw != cron_raw
            or re.fullmatch(r"[0-9a-f]{32}", str(completion.get("token", ""))) is None
        ):
            raise RollforwardError("staging_lane_lineage_mismatch")
        board = strict_json(producer_raw, label="staging_board")
        candidate = board.get("learning_candidate_board")
        if (
            board.get("candidate_board_generation_state") != "COMPLETE"
            or board.get("ledger_scan_status") != "COMPLETE"
            or not isinstance(candidate, dict)
            or candidate.get("candidate_universe_complete") is not True
            or not isinstance(candidate.get("candidate_rows"), list)
        ):
            raise RollforwardError("staging_board_incomplete")
        assert_no_authority(board)
        generated_at = parse_utc(board.get("generated_at_utc"), label="staging_board_generated")
        completed_at = parse_utc(completion.get("ts_utc"), label="staging_completion")
        if not started.timestamp() - 5 <= generated_at.timestamp() <= completed_at.timestamp() <= self.now().timestamp():
            raise RollforwardError("staging_artifact_time_window_invalid")
        publisher = load_publisher()
        try:
            publish_result = publisher.publish_candidate_board(
                producer_path,
                sealed_destination,
                retention_limit=128,
                slippage_artifact_path=PRODUCER_DIR / "slippage_quantiles_latest.json",
                max_total_bytes=64 * 1024 * 1024,
            )
        except (OSError, ValueError) as exc:
            raise RollforwardError("staging_publisher_nonzero") from exc
        staged_path = sealed_destination / producer_path.name
        staged_raw, staged_id = self.pin.read_regular_bytes(staged_path)
        if (
            publish_result.get("schema_version") != "alr_candidate_board_publish_result_v2"
            or publish_result.get("status") != "PUBLISHED"
            or publish_result.get("published_path") != str(staged_path)
            or publish_result.get("source_content_sha256") != producer_id["sha256"]
            or publish_result.get("latest_alias_written") is not False
            or staged_raw != producer_raw
        ):
            raise RollforwardError("staging_raw_publisher_result_not_new")
        publisher_receipt = self.persist_path(publisher_receipt_path, publish_result)
        private_deps = self.stage_private_dependencies(private_deps_receipt_path)
        end_source = self.source_snapshot()
        end_tree = self.execution_tree_lease()
        end_service = self.service_snapshot(require_active=True)
        end_inventories = self.lane_inventories(staging=staging)
        if (
            end_source != before["source"]
            or end_tree != before["execution_tree"]
            or end_service != before["service"]
            or end_inventories["live"] != before["inventories"]["live"]
            or self.ledger_inventory() != ledger_after
        ):
            raise RollforwardError("staging_end_lease_or_live_drift")
        return {
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": self.now().isoformat().replace("+00:00", "Z"),
            "token": completion.get("token"),
            "completion": {"path": str(completion_path), "sha256": completion_id["sha256"]},
            "producer_board": {"path": str(producer_path), "sha256": producer_id["sha256"]},
            "cron_staged_board": {"path": str(cron_board_path), "sha256": cron_id["sha256"]},
            "staged_board": {"path": str(staged_path), "sha256": staged_id["sha256"]},
            "staging_publisher_receipt": publisher_receipt,
            **private_deps,
            "publisher_result": publish_result,
            "execution_tree": end_tree,
            "live_inventory_sha256": self.inventory_digest(end_inventories["live"]),
            "completion_inventory_sha256": self.inventory_digest(end_inventories["completion"]),
            "producer_inventory_sha256": self.inventory_digest(end_inventories["producer"]),
            "ledger_pre_inventory_sha256": self.inventory_digest(before["ledger_inventory"]),
            "ledger_post_inventory_sha256": self.inventory_digest(ledger_after),
            "lane_effective_config_sha256": self.lane_effective_config_sha256(),
            "alr_availability_monitor": {
                "sample_count": len(availability_samples),
                "first": availability_samples[0],
                "last": availability_samples[-1],
                "final_service_identity": {
                    key: end_service.get(key)
                    for key in (
                        "MainPID", "ProcessStartTicks", "InvocationID", "NRestarts",
                        "ControlGroup", "ALRSourceHead",
                    )
                },
            },
            "normal_lane_returncode": completed.returncode,
        }

    @staticmethod
    def alr_availability_probe(
        baseline: dict[str, Any], *,
        proc_root: Path = Path("/proc"),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
    ) -> dict[str, Any]:
        try:
            pid = int(baseline["MainPID"])
            expected_ticks = str(baseline["ProcessStartTicks"])
            control_group = str(baseline["ControlGroup"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RollforwardError("alr_availability_baseline_invalid") from exc
        parts = [part for part in control_group.split("/") if part]
        if pid <= 0 or not expected_ticks.isdigit() or not control_group.startswith("/") or ".." in parts:
            raise RollforwardError("alr_availability_baseline_invalid")
        try:
            raw_stat = (proc_root / str(pid) / "stat").read_text()
            close = raw_stat.rindex(")")
            fields_after_comm = raw_stat[close + 1:].split()
            observed_ticks = fields_after_comm[19]
            cgroup = cgroup_root.joinpath(*parts)
            pids = {int(value) for value in (cgroup / "cgroup.procs").read_text().split()}
            events = dict(
                line.split(None, 1)
                for line in (cgroup / "cgroup.events").read_text().splitlines()
                if line.strip() and len(line.split(None, 1)) == 2
            )
        except (OSError, ValueError, IndexError) as exc:
            raise RollforwardError("alr_availability_probe_failed") from exc
        if observed_ticks != expected_ticks or pid not in pids or events.get("populated") != "1":
            raise RollforwardError("alr_availability_identity_lost")
        return {
            "pid": pid,
            "start_ticks": observed_ticks,
            "control_group": control_group,
            "cgroup_populated": events["populated"],
        }

    @staticmethod
    def run_contained(
        command: list[str], *, cwd: Path, env: dict[str, str], timeout: int,
        monitor: Callable[[], dict[str, Any]] | None = None,
        monitor_interval: float = 2.0,
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        def terminate_group() -> None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)

        deadline = time.monotonic() + timeout
        if not 0 < monitor_interval <= 10:
            terminate_group()
            raise RollforwardError("monitor_interval_invalid")
        try:
            if monitor is not None:
                monitor()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(
                        timeout=min(monitor_interval, remaining)
                    )
                    break
                except subprocess.TimeoutExpired:
                    if monitor is not None:
                        monitor()
        except subprocess.TimeoutExpired as exc:
            terminate_group()
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise RollforwardError("contained_process_group_still_present") from exc
            raise RollforwardError("contained_process_timeout") from exc
        except BaseException:
            terminate_group()
            raise
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            raise RollforwardError("contained_process_group_leaked_after_exit")
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    def receipt_path(self, phase: int) -> Path:
        return RECEIPT_DIR / f"{self.approval['approval_id']}.phase{phase}.json"

    def receipt_absent(self, phase: int) -> None:
        if self.receipt_path(phase).exists():
            raise RollforwardError(f"phase{phase}_receipt_already_exists")

    def persist_receipt(self, phase: int, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.receipt_path(phase)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise RollforwardError("receipt_short_write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return {"path": str(path), "sha256": sha256_bytes(raw), "size": len(raw)}

    @contextmanager
    def transaction_lock(self) -> Iterator[dict[str, Any]]:
        baseline = self.approval["service_baseline"]
        cost_fd = os.open(
            COST_LOCK,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            fcntl.flock(cost_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(cost_fd)
            raise
        cost_observed = os.fstat(cost_fd)
        cost_identity = {
            "dev": cost_observed.st_dev, "ino": cost_observed.st_ino,
            "uid": cost_observed.st_uid, "gid": cost_observed.st_gid,
            "mode": stat.S_IMODE(cost_observed.st_mode), "nlink": cost_observed.st_nlink,
        }
        if cost_identity != baseline["cost_lock_identity"]:
            fcntl.flock(cost_fd, fcntl.LOCK_UN)
            os.close(cost_fd)
            raise RollforwardError("cost_lock_identity_mismatch")
        try:
            alpha_fd = os.open(
                ALPHA_LOCK,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
        except BaseException:
            fcntl.flock(cost_fd, fcntl.LOCK_UN)
            os.close(cost_fd)
            raise
        try:
            alpha_observed = os.fstat(alpha_fd)
            alpha_identity = {
                "dev": alpha_observed.st_dev, "ino": alpha_observed.st_ino,
                "uid": alpha_observed.st_uid, "gid": alpha_observed.st_gid,
                "mode": stat.S_IMODE(alpha_observed.st_mode), "nlink": alpha_observed.st_nlink,
            }
            if alpha_identity != baseline["alpha_lock_identity"]:
                raise RollforwardError("alpha_lock_identity_mismatch")
            fcntl.flock(alpha_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                unit_fd = os.open(
                    UNIT_LOCK,
                    os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    unit_observed = os.fstat(unit_fd)
                    unit_identity = {
                        "dev": unit_observed.st_dev, "ino": unit_observed.st_ino,
                        "uid": unit_observed.st_uid, "gid": unit_observed.st_gid,
                        "mode": stat.S_IMODE(unit_observed.st_mode), "nlink": unit_observed.st_nlink,
                    }
                    if unit_identity != baseline["unit_lock_identity"]:
                        raise RollforwardError("unit_lock_identity_mismatch")
                    fcntl.flock(unit_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    yield {
                        "cost": cost_identity,
                        "alpha": alpha_identity,
                        "unit": unit_identity,
                    }
                finally:
                    try:
                        fcntl.flock(unit_fd, fcntl.LOCK_UN)
                    finally:
                        os.close(unit_fd)
            finally:
                fcntl.flock(alpha_fd, fcntl.LOCK_UN)
        finally:
            try:
                os.close(alpha_fd)
            finally:
                fcntl.flock(cost_fd, fcntl.LOCK_UN)
                os.close(cost_fd)

    @contextmanager
    def cutover_lock(self) -> Iterator[dict[str, Any]]:
        publisher = load_publisher()
        with self.transaction_lock() as base_lock:
            live_lock = publisher._acquire_destination_lock(EVIDENCE_DIR)
            try:
                yield {**base_lock, "publisher": True, "publisher_module": publisher}
            finally:
                publisher._release_destination_lock(live_lock)

    def live_inventory(self) -> dict[str, str]:
        return self.artifact_inventory(EVIDENCE_DIR, "blocked_outcome_review_*.json")

    def publish_live_locked(self, publisher: Any, board_binding: dict[str, str]) -> dict[str, Any]:
        source = Path(board_binding["path"])
        raw, identity = self.pin.read_regular_bytes(source)
        if identity.get("sha256") != board_binding["sha256"]:
            raise RollforwardError("cutover_board_hash_drift")
        published = EVIDENCE_DIR / source.name
        inventory = self.live_inventory()
        if published.name in inventory:
            raise RollforwardError("live_board_not_absent")
        if len(inventory) >= 128 or sum((EVIDENCE_DIR / name).stat().st_size for name in inventory) + len(raw) > 64 * 1024 * 1024:
            raise RollforwardError("live_publish_would_prune")
        source_stamp = publisher._filename_stamp(source.name, error="source_name_not_stamped")
        publisher._validate_payload(raw, slippage_artifact_path=None)
        result = publisher._publish_locked(
            source=source, destination=EVIDENCE_DIR, raw=raw,
            source_stamp=source_stamp, retention_limit=128,
            max_total_bytes=64 * 1024 * 1024,
        )
        if (
            result.get("status") != "PUBLISHED"
            or result.get("published_path") != str(published)
            or result.get("source_content_sha256") != identity["sha256"]
            or result.get("latest_alias_written") is not False
        ):
            raise RollforwardError("live_publisher_not_exact_new")
        return result

    def stop_alr(self) -> dict[str, Any]:
        self.run([SYSTEMD, "--user", "stop", UNIT_NAME], mutate=True)
        return {"action": "stop", "unit": UNIT_NAME, "request_count": 1}

    def cgroup_empty(self, prior_control_group: str) -> dict[str, Any]:
        if not prior_control_group.startswith("/") or ".." in prior_control_group:
            raise RollforwardError("invalid_prior_control_group")
        path = Path("/sys/fs/cgroup") / prior_control_group.lstrip("/")
        if not path.exists():
            return {"control_group": prior_control_group, "exists": False, "pids": [], "threads": [], "populated": 0}
        pids: list[str] = []
        threads: list[str] = []
        for probe in path.rglob("cgroup.procs"):
            pids.extend(probe.read_text().split())
        for probe in path.rglob("cgroup.threads"):
            threads.extend(probe.read_text().split())
        events = dict(line.split() for line in (path / "cgroup.events").read_text().splitlines())
        populated = int(events.get("populated", "1"))
        if pids or threads or populated:
            raise RollforwardError("prior_alr_cgroup_not_empty")
        return {"control_group": prior_control_group, "exists": True, "pids": [], "threads": [], "populated": 0}

    def prove_old_absent_twice(self, prior: dict[str, Any]) -> list[dict[str, Any]]:
        proofs: list[dict[str, Any]] = []
        for index in range(2):
            old_pid = str(prior.get("MainPID", ""))
            deadline = time.monotonic() + 20
            while True:
                stopped = self.wait_stopped(prior_control_group=prior["ControlGroup"])
                if not old_pid or old_pid == "0" or not Path("/proc", old_pid).exists():
                    break
                if time.monotonic() >= deadline:
                    raise RollforwardError("old_alr_pid_still_exists")
                time.sleep(0.2)
            proofs.append({"ordinal": index + 1, **stopped})
            if index == 0:
                time.sleep(0.5)
        return proofs

    def advance_pin(self) -> dict[str, Any]:
        self.pin.old_pin_snapshot()
        helper_identity = metadata(PIN_HELPER, include_hash=True)
        expected_helper_sha256 = self.execution_tree_lease()["generation_pin_helper_sha256"]
        if helper_identity["sha256"] != expected_helper_sha256:
            raise RollforwardError("generation_pin_helper_tree_drift")
        helper_raw, _identity = self.pin.capture_verified_helper(
            path=PIN_HELPER, expected_identity=helper_identity,
            expected_sha256=expected_helper_sha256,
        )
        started = self.pin.utc_now()
        completed = self.pin.run_verified_helper(helper_raw)
        self.pin.fsync_path_and_parent(PIN_PATH)
        new_pin = self.pin.validate_new_pin(PIN_PATH, started_at=started, finished_at=self.pin.utc_now())
        generation = self.pin.post_generation_match()
        return {"status": "APPLIED_POSTCHECK_PASS", "new_pin": new_pin, "generation": generation, "helper_returncode": completed.returncode}

    def atomic_unit_to_target(self) -> tuple[bytes, dict[str, Any]]:
        before = self.unit_snapshot(expected_head=OLD_HEAD)
        original = before["raw"]
        text = original.decode("utf-8")
        old_line = f"ALR_SOURCE_HEAD={OLD_HEAD}"
        new_line = f"ALR_SOURCE_HEAD={TARGET_HEAD}"
        if text.splitlines().count(old_line) != 1 or new_line in text:
            raise RollforwardError("unit_source_line_cardinality_mismatch")
        proposed = text.replace(old_line, new_line, 1).encode()
        expected_hash = self.approval["evidence"]["proposed_unit_sha256"]
        if sha256_bytes(proposed) != expected_hash:
            raise RollforwardError("proposed_unit_hash_mismatch")
        self._atomic_write_unit(proposed, before["identity"])
        after = self.unit_snapshot(expected_head=TARGET_HEAD)
        if after["identity"].get("sha256") != expected_hash:
            raise RollforwardError("unit_postwrite_hash_mismatch")
        return original, after

    def _atomic_write_unit(self, raw: bytes, prior: dict[str, Any]) -> None:
        temp = UNIT_PATH.parent / f".{UNIT_PATH.name}.rollforward-{os.getpid()}-{time.time_ns()}.tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), prior["mode"])
        try:
            os.fchmod(fd, prior["mode"])
            os.fchown(fd, prior["uid"], prior["gid"])
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise RollforwardError("unit_short_write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temp, UNIT_PATH)
            parent = os.open(UNIT_PATH.parent, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def daemon_reload(self) -> dict[str, Any]:
        self.run([SYSTEMD, "--user", "daemon-reload"], mutate=True)
        return {"action": "daemon-reload", "request_count": 1}

    def reset_failed(self) -> dict[str, Any]:
        self.run([SYSTEMD, "--user", "reset-failed", UNIT_NAME], mutate=True)
        return {"action": "reset-failed", "unit": UNIT_NAME, "request_count": 1}

    def restart_alr(self) -> dict[str, Any]:
        self.run([SYSTEMD, "--user", "restart", UNIT_NAME], mutate=True)
        return {"action": "restart", "unit": UNIT_NAME, "request_count": 1}

    def wait_stopped(self, *, prior_control_group: str) -> dict[str, Any]:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                stopped = self.service_snapshot(require_active=False)
                cgroup = self.cgroup_empty(prior_control_group)
                return {"service": stopped, "cgroup": cgroup}
            except RollforwardError:
                time.sleep(0.2)
        raise RollforwardError("alr_stop_not_observed")

    def wait_stable_target(self, *, prior: dict[str, Any]) -> dict[str, Any]:
        deadline = time.monotonic() + 30
        first: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                first = self.service_snapshot(require_active=True)
                if first["ALRSourceHead"] == TARGET_HEAD:
                    break
            except RollforwardError:
                pass
            time.sleep(0.25)
        if first is None:
            raise RollforwardError("target_alr_active_not_observed")
        time.sleep(ALR_STABLE_WINDOW_SECONDS)
        second = self.service_snapshot(require_active=True)
        keys = ("MainPID", "ProcessStartTicks", "InvocationID", "NRestarts", "ALRSourceHead")
        if any(first.get(key) != second.get(key) for key in keys):
            raise RollforwardError("target_alr_identity_not_stable")
        if any(second.get(key) == prior.get(key) for key in ("MainPID", "ProcessStartTicks", "InvocationID")):
            raise RollforwardError("target_alr_identity_not_new")
        return second

    def observer_git_seals(self) -> tuple[dict[str, Any], dict[str, Any]]:
        consumer_path = REPO / "program_code/ml_training/alr_event_consumer.py"
        consumer_identity = metadata(consumer_path, include_hash=True)
        tree_line = self.run([
            "/usr/bin/git", "ls-tree", "HEAD", "--",
            "program_code/ml_training/alr_event_consumer.py",
        ], cwd=REPO).stdout.strip()
        match = re.fullmatch(
            r"100644 blob ([0-9a-f]{40})\tprogram_code/ml_training/alr_event_consumer\.py",
            tree_line,
        )
        if match is None:
            raise RollforwardError("observer_consumer_git_binding_invalid")
        ml_tree = self.run(
            ["/usr/bin/git", "rev-parse", "HEAD:program_code/ml_training"], cwd=REPO
        ).stdout.strip()
        tracked_raw = self.run(["/usr/bin/git", "ls-files", "-z"], cwd=REPO).stdout.encode()
        stage_raw = self.run(
            ["/usr/bin/git", "ls-files", "--stage", "-z"], cwd=REPO
        ).stdout.encode()
        index_text = self.run(
            ["/usr/bin/git", "rev-parse", "--git-path", "index"], cwd=REPO
        ).stdout.strip()
        index_path = Path(index_text)
        if not index_path.is_absolute():
            index_path = REPO / index_path
        index = metadata(index_path, include_hash=True)
        tracked_count = len([item for item in tracked_raw.split(b"\0") if item])
        if tracked_count < 1 or not stage_raw:
            raise RollforwardError("observer_git_inventory_empty")
        return (
            {
                "path": str(consumer_path),
                "sha256": consumer_identity["sha256"],
                "blob_sha1": match.group(1),
                "ml_training_tree_sha1": ml_tree,
            },
            {
                "origin_main_head": TARGET_HEAD,
                "tracked_file_count": tracked_count,
                "git_index_sha256": index["sha256"],
                "git_index_size": index["size"],
                "git_stage_inventory_sha256": sha256_bytes(stage_raw),
                "git_stage_inventory_size": len(stage_raw),
            },
        )

    def observer_runtime_fence(
        self, active: dict[str, str], *, unit_identity: dict[str, Any],
        pin_identity: dict[str, Any]
    ) -> dict[str, Any]:
        observed = self.service_snapshot(require_active=True)
        identity_keys = (
            "MainPID", "ProcessStartTicks", "InvocationID",
            "ExecMainStartTimestampMonotonic", "NRestarts", "ALRSourceHead",
        )
        if any(str(observed.get(key, "")) != str(active.get(key, "")) for key in identity_keys):
            raise RollforwardError("observer_wait_active_identity_drift")
        unit = self.unit_snapshot(expected_head=TARGET_HEAD)["identity"]
        pin = self.pin_snapshot(expected_head=TARGET_HEAD)["identity"]
        if (
            unit != unit_identity
            or pin != pin_identity
            or canonical_digest(self.protected_snapshot()) != self.approval["protected_sha256"]
        ):
            raise RollforwardError("observer_wait_runtime_file_or_protected_drift")
        source = self.source_snapshot()
        if source.get("head") != TARGET_HEAD or source.get("remote_origin_main") != TARGET_HEAD:
            raise RollforwardError("observer_wait_source_drift")
        return {
            "active_identity": {key: observed.get(key) for key in identity_keys},
            "unit_sha256": unit["sha256"], "pin_sha256": pin["sha256"],
            "source_head": source["head"],
        }

    @staticmethod
    def run_observer_process(
        command: list[str], *, monitor: Callable[[], dict[str, Any]], timeout: int = 7200
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(
            command, cwd=REPO, env=SYSTEM_ENV, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        try:
            monitor()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(5.0, remaining))
                    break
                except subprocess.TimeoutExpired:
                    monitor()
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=10)
            except BaseException:
                pass
            raise
        monitor()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    def current_observer_v2_admission(self, **bindings: Any) -> dict[str, Any]:
        """Persist exact provisional/input artifacts and run the sealed observer."""
        if (
            bindings.get("target_head") != TARGET_HEAD
            or self.approval["observer"]["observer_source_digest"]
            != "sha256:" + OBSERVER_V2_SHA256
        ):
            raise RollforwardError("observer_v2_authority_binding_invalid")
        staged_binding = self.approval["evidence"]["staged_board"]
        board_raw, board_identity = self.load_bound(staged_binding, label="observer_staged_board")
        outer = strict_json(board_raw, label="observer_staged_board")
        board = outer.get("learning_candidate_board")
        if not isinstance(board, dict) or not isinstance(board.get("candidate_rows"), list):
            raise RollforwardError("observer_board_payload_invalid")
        board_hashes = validate_observer_board_hashes(board)
        generated_at = outer.get("generated_at_utc")
        parse_utc(generated_at, label="observer_board_generated")
        live_path = EVIDENCE_DIR / Path(staged_binding["path"]).name
        _live_raw, live_identity = self.pin.read_regular_bytes(live_path)
        if live_identity.get("sha256") != board_identity["sha256"]:
            raise RollforwardError("observer_live_board_hash_mismatch")
        pin_raw, pin_identity = self.pin.read_regular_bytes(PIN_PATH)
        pin_payload = strict_json(pin_raw, label="observer_generation_pin")
        if pin_payload.get("head") != TARGET_HEAD:
            raise RollforwardError("observer_generation_pin_head_invalid")
        parse_utc(pin_payload.get("derived_at_utc"), label="observer_pin_derived")
        consumer_source, git_seals = self.observer_git_seals()
        active = bindings["active_identity"]
        active_contract = {
            key: str(active.get(key, ""))
            for key in (
                "MainPID", "ProcessStartTicks", "InvocationID",
                "ExecMainStartTimestampMonotonic", "NRestarts", "ALRSourceHead",
            )
        }
        base_input = {
            "schema_version": "p0b_alr_current_head_observer_input_v2",
            "target_head": TARGET_HEAD,
            "observer_not_before_utc": bindings["observer_not_before_utc"],
            "active_identity": active_contract,
            "phase1_receipt": self.approval["evidence"]["phase1_receipt"],
            "cutover_authorization": self.approval["formal_authority"]["authorization"],
            "admitted_board": {
                "staged_path": staged_binding["path"], "live_path": str(live_path),
                "source_content_sha256": board_identity["sha256"],
                "generated_at_utc": generated_at,
                "board_hash": board_hashes["board_hash"],
                "audit_hash": board_hashes["audit_hash"],
                "selection_hash": board_hashes["selection_hash"],
                "candidate_set_hash": board_hashes["candidate_set_hash"],
            },
            "runtime_files": {
                "unit": {"path": str(UNIT_PATH), "sha256": bindings["final_unit"]["sha256"]},
                "pin": {"path": str(PIN_PATH), "sha256": pin_identity["sha256"]},
                "pin_derived_at_utc": pin_payload["derived_at_utc"],
            },
            "consumer_source": consumer_source,
            "git_seals": git_seals,
            "private_deps": {
                "receipt": self.approval["evidence"]["private_deps_receipt"],
                "destination": self.approval["evidence"]["private_deps_destination"],
                "manifest_sha256": self.approval["evidence"]["private_deps_manifest_sha256"],
            },
            "no_authority": {
                "order": False, "probe": False, "promotion": False, "runtime": False,
            },
        }
        contract_sha256 = sha256_bytes(json.dumps(
            base_input, sort_keys=True, separators=(",", ":")
        ).encode())
        provisional_payload = {
            "schema_version": "p0b_alr_current_head_rollforward_provisional_cutover_v1",
            "status": "PHASE2_PROVISIONAL_CUTOVER_READY",
            "target_head": TARGET_HEAD,
            "phase1_receipt": self.approval["evidence"]["phase1_receipt"],
            "cutover_authorization": self.approval["formal_authority"]["authorization"],
            "cutover_authorization_digest": self.approval["authorization_digest"],
            "live_board": {"path": str(live_path), "sha256": live_identity["sha256"]},
            "unit": {"path": str(UNIT_PATH), "sha256": bindings["final_unit"]["sha256"]},
            "pin": {"path": str(PIN_PATH), "sha256": pin_identity["sha256"]},
            "private_deps_receipt": self.approval["evidence"]["private_deps_receipt"],
            "private_deps_destination": self.approval["evidence"]["private_deps_destination"],
            "private_deps_manifest_sha256": self.approval["evidence"]["private_deps_manifest_sha256"],
            "active_identity": active_contract,
            "generation_fence": bindings["generation_fence"],
            "observer_input_contract_sha256": contract_sha256,
        }
        self.observer_runtime_fence(
            active_contract,
            unit_identity=bindings["final_unit"], pin_identity=bindings["final_pin"],
        )
        provisional = self.persist_path(
            Path(self.approval["observer"]["provisional_cutover_path"]),
            provisional_payload,
        )
        observer_input = {**base_input, "provisional_cutover": {
            "path": provisional["path"], "sha256": provisional["sha256"]
        }}
        input_binding = self.persist_path(
            Path(self.approval["observer"]["observer_input_path"]), observer_input
        )
        observer_raw, observer_identity = self.pin.read_regular_bytes(OBSERVER_V2)
        if observer_identity.get("sha256") != OBSERVER_V2_SHA256:
            raise RollforwardError("observer_v2_source_hash_mismatch")
        command = [
            "/usr/bin/python3", "-I", "-B", str(OBSERVER_V2),
            "--observer-input", input_binding["path"],
            "--observer-input-sha256", input_binding["sha256"],
        ]
        completed = self.run_observer_process(
            command,
            monitor=lambda: self.observer_runtime_fence(
                active_contract,
                unit_identity=bindings["final_unit"],
                pin_identity=bindings["final_pin"],
            ),
        )
        if completed.returncode != 0:
            raise RollforwardError(
                "observer_v2_nonzero:" + sha256_bytes(completed.stderr.encode())
            )
        result = strict_json(completed.stdout.encode(), label="observer_v2_result")
        if result.get("status") != "OBSERVER_V2_EXACT_POSTCHECK_PASS":
            raise RollforwardError("observer_v2_exact_status_missing")
        after_raw, after_identity = self.pin.read_regular_bytes(OBSERVER_V2)
        if after_raw != observer_raw or after_identity.get("sha256") != OBSERVER_V2_SHA256:
            raise RollforwardError("observer_v2_source_changed_during_execution")
        self.load_bound(
            {"path": provisional["path"], "sha256": provisional["sha256"]},
            label="observer_provisional_postcheck",
        )
        self.load_bound(
            {"path": input_binding["path"], "sha256": input_binding["sha256"]},
            label="observer_input_postcheck",
        )
        return {
            **result,
            "provisional_cutover": provisional,
            "observer_input": input_binding,
            "observer_source_sha256": OBSERVER_V2_SHA256,
        }

    def load_bound(self, binding: dict[str, str], *, label: str) -> tuple[bytes, dict[str, Any]]:
        path = Path(binding["path"])
        raw, identity = self.pin.read_regular_bytes(path)
        if identity.get("sha256") != binding["sha256"] or identity.get("nlink") != 1:
            raise RollforwardError(f"bound_artifact_hash_mismatch:{label}")
        return raw, identity

    def phase1_receipt(self) -> dict[str, Any]:
        binding = self.approval["evidence"]["phase1_receipt"]
        receipt_path = Path(binding["path"])
        if receipt_path.parent != RECEIPT_DIR or not receipt_path.name.endswith(".phase1.json"):
            raise RollforwardError("noncanonical_phase1_receipt_path")
        raw, identity = self.load_bound(binding, label="phase1_receipt")
        payload = strict_json(raw, label="phase1_receipt")
        if (
            payload.get("schema_version") != SCHEMA
            or payload.get("phase") != 1
            or payload.get("status") != "PHASE1_STAGING_APPLIED_PASS"
            or payload.get("target_head") != TARGET_HEAD
            or payload.get("old_head") != OLD_HEAD
            or payload.get("old_alr_retained_running") is not True
            or payload.get("protected_sha256") != self.approval["protected_sha256"]
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{7,127}", str(payload.get("approval_id", ""))) is None
            or receipt_path != RECEIPT_DIR / f"{payload.get('approval_id')}.phase1.json"
        ):
            raise RollforwardError("phase1_receipt_binding_mismatch")
        return {"payload": payload, "identity": identity}

    def validate_authorized_phase1_lineage(self) -> dict[str, Any]:
        evidence = self.approval["evidence"]
        result = validate_phase1_semantic_lineage(
            self,
            phase1_receipt=evidence["phase1_receipt"],
            phase1_closure=evidence["phase1_closure"],
            sealed_lineage_bundle=evidence["sealed_lineage_bundle"],
        )
        authority = self.approval["lineage_authority"]
        if authority != {
            "phase1_effect_receipt_digest": result["receipt_digest"],
            "phase1_closure_digest": result["closure_raw_digest"],
            "sealed_lineage_bundle_digest": result["bundle_raw_digest"],
        }:
            raise RollforwardError("phase1_cutover_authority_semantic_mismatch")
        return result

    @staticmethod
    def _path_parent_exact(path: Path, parent: Path) -> bool:
        return path.is_absolute() and path.parent == parent and "latest" not in path.name.lower()

    def evidence_snapshot(self) -> dict[str, Any]:
        ev = self.approval["evidence"]
        phase1_payload = self.phase1_receipt()["payload"]
        phase1_approval_id = str(phase1_payload.get("approval_id", ""))
        if re.fullmatch(r"[a-z0-9][a-z0-9._-]{7,127}", phase1_approval_id) is None:
            raise RollforwardError("noncanonical_evidence_path")
        expected_staging_root = STAGING_ROOT / phase1_approval_id
        sealed = phase1_payload.get("sealed_lineage")
        if (
            not isinstance(sealed, dict)
            or sealed.get("token") != ev.get("token")
            or sealed.get("completion") != ev.get("completion")
            or sealed.get("producer_board") != ev.get("producer_board")
            or sealed.get("staged_board") != ev.get("staged_board")
            or sealed.get("staging_publisher_receipt") != ev.get("staging_publisher_receipt")
            or sealed.get("completion_inventory_sha256") != ev.get("completion_inventory_sha256")
            or sealed.get("producer_inventory_sha256") != ev.get("producer_inventory_sha256")
            or sealed.get("ledger_pre_inventory_sha256") != ev.get("ledger_pre_inventory_sha256")
            or sealed.get("ledger_post_inventory_sha256") != ev.get("ledger_post_inventory_sha256")
            or sealed.get("lane_effective_config_sha256") != ev.get("lane_effective_config_sha256")
            or sealed.get("private_deps_receipt") != ev.get("private_deps_receipt")
            or sealed.get("private_deps_destination") != ev.get("private_deps_destination")
            or sealed.get("private_deps_manifest_sha256")
            != ev.get("private_deps_manifest_sha256")
        ):
            raise RollforwardError("phase1_to_phase2_lineage_mismatch")
        paths = {
            key: Path(ev[key]["path"])
            for key in (
                "completion", "producer_board", "staged_board",
                "staging_publisher_receipt", "private_deps_receipt",
            )
        }
        if (
            not self._path_parent_exact(paths["completion"], COMPLETION_DIR)
            or not self._path_parent_exact(paths["producer_board"], PRODUCER_DIR)
            or paths["staged_board"].parent != expected_staging_root / "sealed"
            or paths["staging_publisher_receipt"]
            != expected_staging_root / "staging-publisher-result.json"
            or paths["private_deps_receipt"]
            != expected_staging_root / "private-deps-receipt.json"
            or paths["producer_board"].name != paths["staged_board"].name
        ):
            raise RollforwardError("noncanonical_evidence_path")
        completion_raw, completion_id = self.load_bound(ev["completion"], label="completion")
        producer_raw, producer_id = self.load_bound(ev["producer_board"], label="producer_board")
        board_raw, board_id = self.load_bound(ev["staged_board"], label="staged_board")
        publisher_raw, publisher_id = self.load_bound(ev["staging_publisher_receipt"], label="staging_publisher_receipt")
        private_raw, private_id = self.load_bound(
            ev["private_deps_receipt"], label="private_deps_receipt"
        )
        if producer_raw != board_raw or producer_id["sha256"] != board_id["sha256"]:
            raise RollforwardError("producer_published_board_bytes_mismatch")
        completion = strict_json(completion_raw, label="completion")
        board = strict_json(board_raw, label="staged_board")
        publisher = strict_json(publisher_raw, label="staging_publisher_receipt")
        private = strict_json(private_raw, label="private_deps_receipt")
        candidate_board = board.get("learning_candidate_board")
        token = ev["token"]
        if (
            completion.get("schema_version") != "research_workload_completion_v1"
            or completion.get("lane") != "cost" or completion.get("status") != "COMPLETE"
            or completion.get("token") != token or completion.get("source_head") != TARGET_HEAD
            or completion.get("completion_paths") != [str(paths["producer_board"])]
            or completion.get("sha256_by_path") != {str(paths["producer_board"]): producer_id["sha256"]}
            or board.get("schema_version") != "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
            or board.get("candidate_board_generation_state") != "COMPLETE"
            or board.get("ledger_scan_status") != "COMPLETE"
            or board.get("latest_alias_used", False) is not False
            or not isinstance(candidate_board, dict)
            or candidate_board.get("schema_version") != "cost_gate_learning_candidate_board_v2"
            or candidate_board.get("candidate_universe_complete") is not True
            or not isinstance(candidate_board.get("candidate_rows"), list)
        ):
            raise RollforwardError("current_head_completion_or_board_mismatch")
        parsed = publisher
        if (
            publisher.get("schema_version") != "alr_candidate_board_publish_result_v2"
            or publisher.get("status") != "PUBLISHED"
            or parsed.get("published_path") != str(paths["staged_board"])
            or parsed.get("source_content_sha256") != board_id["sha256"]
            or parsed.get("latest_alias_written") is not False
        ):
            raise RollforwardError("publisher_receipt_binding_mismatch")
        if (
            private.get("schema_version") != "p0b_psycopg_private_bundle_stage_v1"
            or private.get("status") != "APPLIED_POSTCHECK_PASS"
            or private.get("destination") != str(PRIVATE_BUNDLE_DESTINATION)
            or private.get("source_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
            or private.get("destination_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
            or private.get("mutation_performed") is not True
        ):
            raise RollforwardError("private_deps_receipt_binding_mismatch")
        authority = assert_no_authority(board)
        generated = parse_utc(board.get("generated_at_utc"), label="board_generated")
        completed = parse_utc(completion.get("ts_utc"), label="manifest_completed")
        publisher_time = parse_utc(self.phase1_receipt()["payload"].get("completed_at_utc"), label="publisher_completed")
        now = self.now()
        phase1_time = parse_utc(self.phase1_receipt()["payload"].get("completed_at_utc"), label="phase1_completed")
        if publisher_time != phase1_time or not generated <= completed <= phase1_time <= now:
            raise RollforwardError("evidence_lineage_order_invalid")
        if (now - generated).total_seconds() > ev["max_age_seconds"]:
            raise RollforwardError("candidate_board_stale")
        return {
            "status": "COMPLETE", "source_head": TARGET_HEAD,
            "candidate_count": len(candidate_board["candidate_rows"]),
            "authority": authority, "generated_at_utc": board.get("generated_at_utc"),
            "completion": completion_id, "producer": producer_id,
            "staged": board_id, "publisher": publisher_id,
            "private_deps": private_id,
        }


class Phase1Transaction:
    def __init__(self, runtime: Runtime, approval: dict[str, Any]) -> None:
        self.runtime = runtime
        self.approval = approval

    def preflight(self) -> dict[str, Any]:
        validate_approval(self.approval, phase=1, now=self.runtime.now())
        self.runtime.receipt_absent(1)
        staging = self.approval["staging"]
        for value in (
            staging["cron_destination"], staging["sealed_destination"],
            staging["publisher_receipt_path"], staging["private_deps_receipt_path"],
        ):
            if Path(value).exists():
                raise RollforwardError("phase1_staging_path_not_absent")
        if PRIVATE_BUNDLE_DESTINATION.exists():
            raise RollforwardError("phase1_private_bundle_destination_not_absent")
        source = self.runtime.source_snapshot()
        execution_tree = self.runtime.execution_tree_lease()
        lane = self.runtime.lane_snapshot()
        protected = self.runtime.protected_snapshot()
        if canonical_digest(protected) != self.approval["protected_sha256"]:
            raise RollforwardError("protected_snapshot_not_approved")
        unit = self.runtime.unit_snapshot(expected_head=OLD_HEAD)
        if unit["identity"].get("sha256") != OLD_UNIT_SHA256:
            raise RollforwardError("old_unit_hash_mismatch")
        pin = self.runtime.pin_snapshot(expected_head=OLD_HEAD)
        require_identity(unit["identity"], self.approval["service_baseline"]["unit_identity"], label="unit")
        require_identity(pin["identity"], self.approval["service_baseline"]["pin_identity"], label="pin")
        service = self.runtime.service_snapshot(require_active=True)
        expected_identity = self.approval["service_baseline"]["active_identity"]
        if any(service.get(key) != str(value) for key, value in expected_identity.items()):
            raise RollforwardError("active_service_identity_not_approved")
        if service.get("ALRSourceHead") != OLD_HEAD:
            raise RollforwardError("active_service_head_not_old")
        self.runtime.no_queued_job()
        inventories = self.runtime.lane_inventories(staging=staging)
        if self.runtime.inventory_digest(inventories["live"]) != staging["baseline_live_inventory_sha256"]:
            raise RollforwardError("phase1_live_inventory_not_approved")
        ledger_inventory = self.runtime.ledger_inventory()
        if (
            self.runtime.inventory_digest(ledger_inventory)
            != staging["baseline_ledger_inventory_sha256"]
            or self.runtime.lane_effective_config_sha256()
            != staging["lane_effective_config_sha256"]
        ):
            raise RollforwardError("phase1_ledger_or_config_not_approved")
        return {
            "schema": SCHEMA, "phase": 1, "status": "PHASE1_STAGING_PREFLIGHT_PASS",
            "source": source, "execution_tree": execution_tree, "lane": lane,
            "protected": protected, "unit": unit["identity"], "pin": pin,
            "service": service, "inventories": inventories,
            "ledger_inventory": ledger_inventory,
            "lane_effective_config_sha256": self.runtime.lane_effective_config_sha256(),
            "boundaries": LANE_BOUNDARIES,
        }

    def apply(self) -> dict[str, Any]:
        before = self.preflight()
        intent_path = RECEIPT_DIR / f"{self.approval['approval_id']}.phase1.intent.json"
        attempt_path = RECEIPT_DIR / f"{self.approval['approval_id']}.phase1.attempt.json"
        with self.runtime.transaction_lock():
            locked = self.preflight()
            if locked != before:
                raise RollforwardError("phase1_locked_admission_drift")
            intent = self.runtime.persist_path(intent_path, {
                "schema_version": SCHEMA, "phase": 1, "kind": "intent",
                "approval_id": self.approval["approval_id"], "target_head": TARGET_HEAD,
                "source": before["source"], "execution_tree": before["execution_tree"],
                "mutation_scope": "normal_lane_and_unwatched_staging_only",
            })
            self.runtime.persist_path(attempt_path, {
                "schema_version": SCHEMA, "phase": 1, "kind": "attempt",
                "intent_sha256": intent["sha256"],
                "started_at_utc": self.runtime.now().isoformat().replace("+00:00", "Z"),
            })
        try:
            staged = self.runtime.stage_lane(before)
            with self.runtime.cutover_lock() as final_lock:
                if (
                    self.runtime.source_snapshot() != before["source"]
                    or self.runtime.execution_tree_lease() != before["execution_tree"]
                    or self.runtime.protected_snapshot() != before["protected"]
                    or self.runtime.pin_snapshot(expected_head=OLD_HEAD)["identity"]["sha256"] != OLD_PIN_SHA256
                    or self.runtime.unit_snapshot(expected_head=OLD_HEAD)["identity"]["sha256"] != OLD_UNIT_SHA256
                    or self.runtime.service_snapshot(require_active=True) != before["service"]
                    or self.runtime.inventory_digest(self.runtime.live_inventory())
                    != self.approval["staging"]["baseline_live_inventory_sha256"]
                    or self.runtime.generation_fence_snapshot()
                    != {
                        key: staged[key]
                        for key in (
                            "completion_inventory_sha256",
                            "producer_inventory_sha256",
                            "ledger_post_inventory_sha256",
                            "lane_effective_config_sha256",
                        )
                    }
                ):
                    raise RollforwardError("phase1_old_runtime_or_source_drift")
                payload = {
                    "schema_version": SCHEMA, "phase": 1,
                    "status": "PHASE1_STAGING_APPLIED_PASS",
                    "approval_id": self.approval["approval_id"],
                    "authorization_digest": self.approval["authorization_digest"],
                    "stage_authorization": self.approval["formal_authority"]["authorization"],
                    "stage_authorization_digest": self.approval["formal_authority"]["authorization_digest"],
                    "stage_runtime_bindings": self.approval["formal_authority"]["runtime_bindings"],
                    "stage_runtime_bindings_artifact_digest": self.approval["formal_authority"]["runtime_bindings_artifact_digest"],
                    "stage_authorized_runtime": self.approval["formal_authority"]["authorized_runtime"],
                    "target_head": TARGET_HEAD, "old_head": OLD_HEAD,
                    "protected_sha256": self.approval["protected_sha256"],
                    "old_alr_retained_running": True,
                    "global_pin_retained_old": True,
                    "live_publication_performed": False,
                    "sealed_lineage": staged,
                    "completed_at_utc": self.runtime.now().isoformat().replace("+00:00", "Z"),
                    "intent": intent,
                    "locks_held_through_effect_receipt": {
                        key: value for key, value in final_lock.items() if key != "publisher_module"
                    },
                    "boundaries": LANE_BOUNDARIES,
                }
                receipt = self.runtime.persist_receipt(1, payload)
                return {**payload, "receipt": receipt}
        except BaseException as exc:
            old_runtime_verified = False
            try:
                old_runtime_verified = (
                    self.runtime.pin_snapshot(expected_head=OLD_HEAD)["identity"]["sha256"] == OLD_PIN_SHA256
                    and self.runtime.unit_snapshot(expected_head=OLD_HEAD)["identity"]["sha256"] == OLD_UNIT_SHA256
                    and self.runtime.service_snapshot(require_active=True)["ALRSourceHead"] == OLD_HEAD
                )
            except BaseException:
                pass
            failure = {
                "schema_version": SCHEMA, "phase": 1,
                "status": "PHASE1_STAGING_FAILED_OLD_ALR_VERIFIED" if old_runtime_verified else "PHASE1_STAGING_FAILED_UNVERIFIED",
                "error_type": type(exc).__name__, "error_digest": sha256_bytes(str(exc).encode()),
                "old_runtime_verified": old_runtime_verified,
                "staging_artifacts_never_deleted": True,
                "receipt_persisted": False, "boundaries": LANE_BOUNDARIES,
            }
            try:
                failure["failure_ledger"] = self.runtime.persist_path(
                    RECEIPT_DIR / f"{self.approval['approval_id']}.phase1.failure.json",
                    failure,
                )
                failure["receipt_persisted"] = True
            except BaseException:
                failure["status"] = "PHASE1_STAGING_FAILED_UNVERIFIED"
            return failure


class Phase2Transaction:
    def __init__(self, runtime: Runtime, approval: dict[str, Any]) -> None:
        self.runtime = runtime
        self.approval = approval

    def require_generation_fence(self) -> dict[str, str]:
        observed = self.runtime.generation_fence_snapshot()
        expected = {
            key: self.approval["evidence"][key]
            for key in (
                "completion_inventory_sha256", "producer_inventory_sha256",
                "ledger_post_inventory_sha256", "lane_effective_config_sha256",
            )
        }
        if observed != expected:
            raise RollforwardError("generation_fence_inventory_drift")
        return observed

    def preflight(self) -> dict[str, Any]:
        validate_approval(self.approval, phase=2, now=self.runtime.now())
        self.runtime.receipt_absent(2)
        semantic_lineage = self.runtime.validate_authorized_phase1_lineage()
        source = self.runtime.source_snapshot()
        execution_tree = self.runtime.execution_tree_lease()
        lane = self.runtime.lane_snapshot()
        protected = self.runtime.protected_snapshot()
        if canonical_digest(protected) != self.approval["protected_sha256"]:
            raise RollforwardError("protected_snapshot_not_approved")
        phase1 = self.runtime.phase1_receipt()
        evidence = self.runtime.evidence_snapshot()
        # The global pin remains old until the short cutover.
        pin = self.runtime.pin_snapshot(expected_head=OLD_HEAD)
        unit = self.runtime.unit_snapshot(expected_head=OLD_HEAD)
        if unit["identity"].get("sha256") != OLD_UNIT_SHA256:
            raise RollforwardError("old_unit_hash_mismatch")
        require_identity(unit["identity"], self.approval["service_baseline"]["unit_identity"], label="unit")
        require_identity(pin["identity"], self.approval["service_baseline"]["pin_identity"], label="pin")
        service = self.runtime.service_snapshot(require_active=True)
        if service.get("ALRSourceHead") != OLD_HEAD:
            raise RollforwardError("running_manager_head_not_old")
        expected_identity = self.approval["service_baseline"]["active_identity"]
        if any(service.get(key) != str(value) for key, value in expected_identity.items()):
            raise RollforwardError("cutover_active_identity_not_approved")
        live = self.runtime.live_inventory()
        if self.runtime.inventory_digest(live) != self.approval["evidence"]["live_inventory_sha256"]:
            raise RollforwardError("live_inventory_drift")
        board_name = Path(self.approval["evidence"]["staged_board"]["path"]).name
        if board_name in live:
            raise RollforwardError("admitted_live_board_not_absent")
        generation_fence = self.require_generation_fence()
        self.runtime.no_queued_job()
        return {
            "schema": SCHEMA, "phase": 2, "status": "PHASE2_CUTOVER_PREFLIGHT_PASS",
            "source": source, "execution_tree": execution_tree, "lane": lane,
            "protected": protected, "phase1": phase1, "evidence": evidence,
            "semantic_lineage": semantic_lineage,
            "pin": pin, "unit": unit["identity"], "service": service,
            "live_inventory": live, "generation_fence": generation_fence,
            "boundaries": BOUNDARIES,
        }

    def apply(self) -> dict[str, Any]:
        before = self.preflight()
        intent_path = RECEIPT_DIR / f"{self.approval['approval_id']}.phase2.intent.json"
        attempt_path = RECEIPT_DIR / f"{self.approval['approval_id']}.phase2.attempt.json"
        intent = self.runtime.persist_path(intent_path, {
            "schema_version": SCHEMA, "phase": 2, "kind": "intent",
            "approval_id": self.approval["approval_id"], "target_head": TARGET_HEAD,
            "phase1_receipt_sha256": self.approval["evidence"]["phase1_receipt"]["sha256"],
            "board_sha256": self.approval["evidence"]["staged_board"]["sha256"],
            "failure_policy": "after_stop_freeze_stopped_no_backward_pin_no_old_restart",
        })
        stop_attempted = False
        restart_attempted = False
        mutations: list[dict[str, Any]] = []
        lock_evidence: dict[str, Any] = {}
        try:
            # This is the only mutation-critical section.  Natural cost/alpha
            # cycles must be able to run while the two-cycle observer waits.
            with self.runtime.cutover_lock() as lock:
                locked = self.preflight()
                if locked["evidence"] != before["evidence"] or locked["protected"] != before["protected"]:
                    raise RollforwardError("phase2_locked_admission_drift")
                if self.runtime.inventory_digest(self.runtime.live_inventory()) != self.approval["evidence"]["live_inventory_sha256"]:
                    raise RollforwardError("locked_live_inventory_drift")
                attempt = self.runtime.persist_path(attempt_path, {
                    "schema_version": SCHEMA, "phase": 2, "kind": "attempt",
                    "intent_sha256": intent["sha256"],
                    "started_at_utc": self.runtime.now().isoformat().replace("+00:00", "Z"),
                })
                # Reopen every authorized Phase1 artifact at the last possible
                # pre-service-mutation fence.  Hash identity alone is not legal lineage.
                self.runtime.validate_authorized_phase1_lineage()
                stop_attempted = True
                stop = self.runtime.stop_alr()
                mutations.append(stop)
                empty_proofs = self.runtime.prove_old_absent_twice(before["service"])
                self.require_generation_fence()
                pin_result = self.runtime.advance_pin()
                mutations.append({"action": "atomic-generation-repin", "request_count": 1})
                self.runtime.pin_snapshot(expected_head=TARGET_HEAD)
                live_publish = self.runtime.publish_live_locked(
                    lock["publisher_module"], self.approval["evidence"]["staged_board"]
                )
                mutations.append({"action": "live-board-publish", "request_count": 1, "result": live_publish})
                _original, target_unit = self.runtime.atomic_unit_to_target()
                mutations.append({"action": "atomic-unit-repin", "request_count": 1})
                if self.runtime.protected_snapshot() != before["protected"]:
                    raise RollforwardError("protected_or_need_daemon_reload_drift_before_reload")
                mutations.append(self.runtime.daemon_reload())
                manager = self.runtime.service_snapshot(require_active=False)
                if manager.get("ALRSourceHead") != TARGET_HEAD:
                    raise RollforwardError("manager_not_reloaded_to_target")
                mutations.append(self.runtime.reset_failed())
                if (
                    self.runtime.source_snapshot() != before["source"]
                    or self.runtime.execution_tree_lease() != before["execution_tree"]
                    or self.runtime.protected_snapshot() != before["protected"]
                ):
                    raise RollforwardError("cutover_lease_drift_before_restart")
                self.require_generation_fence()
                self.runtime.pin_snapshot(expected_head=TARGET_HEAD)
                restart_attempted = True
                mutations.append(self.runtime.restart_alr())
                active = self.runtime.wait_stable_target(prior=self.approval["service_baseline"]["active_identity"])
                final_unit = self.runtime.unit_snapshot(expected_head=TARGET_HEAD)
                final_pin = self.runtime.pin_snapshot(expected_head=TARGET_HEAD)
                if self.runtime.source_snapshot() != before["source"] or self.runtime.protected_snapshot() != before["protected"]:
                    raise RollforwardError("phase2_final_collateral_drift")
                self.runtime.lane_snapshot()
                self.runtime.no_queued_job()
                final_generation_fence = self.require_generation_fence()
                lock_evidence = {
                    key: value for key, value in lock.items() if key != "publisher_module"
                }

            # Locks are released here.  The observer needs natural cron cycles.
            observer_v2 = self.runtime.current_observer_v2_admission(
                target_head=TARGET_HEAD,
                active_identity=active,
                generation_fence=final_generation_fence,
                board_sha256=self.approval["evidence"]["staged_board"]["sha256"],
                final_unit=final_unit["identity"], final_pin=final_pin["identity"],
                observer_not_before_utc=self.runtime.now().isoformat().replace("+00:00", "Z"),
            )
            if observer_v2.get("status") != "OBSERVER_V2_EXACT_POSTCHECK_PASS":
                raise RollforwardError("observer_v2_exact_postcheck_failed")
            post_service = self.runtime.service_snapshot(require_active=True)
            identity_keys = (
                "MainPID", "ProcessStartTicks", "InvocationID",
                "ExecMainStartTimestampMonotonic", "NRestarts", "ALRSourceHead",
            )
            if any(post_service.get(key) != active.get(key) for key in identity_keys):
                raise RollforwardError("post_observer_active_identity_drift")
            post_unit = self.runtime.unit_snapshot(expected_head=TARGET_HEAD)
            post_pin = self.runtime.pin_snapshot(expected_head=TARGET_HEAD)
            if (
                post_unit["identity"] != final_unit["identity"]
                or post_pin["identity"] != final_pin["identity"]
                or self.runtime.source_snapshot() != before["source"]
                or self.runtime.execution_tree_lease() != before["execution_tree"]
                or self.runtime.protected_snapshot() != before["protected"]
            ):
                raise RollforwardError("post_observer_generation_or_collateral_drift")
            self.runtime.no_queued_job()
            payload = {
                "schema_version": SCHEMA, "phase": 2,
                "status": "PHASE2_APPLIED_POSTCHECK_PASS",
                "approval_id": self.approval["approval_id"],
                "authorization_digest": self.approval["authorization_digest"],
                "target_head": TARGET_HEAD, "old_head": OLD_HEAD,
                "unit_sha256": post_unit["identity"]["sha256"],
                "pin_sha256": post_pin["identity"]["sha256"],
                "protected_sha256": self.approval["protected_sha256"],
                "completed_at_utc": self.runtime.now().isoformat().replace("+00:00", "Z"),
                "active_identity": {key: active.get(key) for key in identity_keys},
                "phase1_receipt_sha256": self.approval["evidence"]["phase1_receipt"]["sha256"],
                "board_sha256": self.approval["evidence"]["staged_board"]["sha256"],
                "live_publisher_result": live_publish,
                "old_cgroup_empty_proofs": empty_proofs,
                "pin_apply": pin_result,
                "generation_fence": final_generation_fence,
                "observer_v2": observer_v2,
                "intent": intent, "attempt": attempt,
                "mutations": mutations,
                "mutation_locks_released_before_observer": True,
                "cutover_lock_evidence": lock_evidence,
                "boundaries": BOUNDARIES,
            }
            receipt = self.runtime.persist_receipt(2, payload)
            return {**payload, "receipt": receipt}
        except BaseException as exc:
            if stop_attempted:
                failure_prior = before["service"]
                if restart_attempted:
                    try:
                        observed_after_restart = self.runtime.service_snapshot(require_active=None)
                        if observed_after_restart.get("MainPID") not in {None, "", "0"}:
                            failure_prior = observed_after_restart
                    except BaseException:
                        pass
                compensation_error: BaseException | None = None
                try:
                    mutations.append(self.runtime.stop_alr())
                except BaseException as compensation_exc:
                    compensation_error = compensation_exc
                stopped: dict[str, Any] | None = None
                try:
                    first_stopped = self.runtime.service_snapshot(require_active=False)
                    empty_proofs_after_compensation = self.runtime.prove_old_absent_twice(
                        failure_prior
                    )
                    second_stopped = self.runtime.service_snapshot(require_active=False)
                    if (
                        first_stopped.get("MainPID") in {None, "", "0"}
                        and second_stopped.get("MainPID") in {None, "", "0"}
                    ):
                        stopped = {
                            "service_before_proof": first_stopped,
                            "cgroup_empty_proofs": empty_proofs_after_compensation,
                            "service_after_proof": second_stopped,
                        }
                except BaseException:
                    pass
                failure = {
                    "schema_version": SCHEMA, "phase": 2,
                    "status": (
                        "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
                        if stopped else "PHASE2_POST_STOP_ATTEMPT_STATE_UNVERIFIED"
                    ),
                    "error_type": type(exc).__name__, "error_digest": sha256_bytes(str(exc).encode()),
                    "no_backward_pin_attempted": True,
                    "no_old_generation_restart_attempted": True,
                    "stop_attempted": True,
                    "compensation_stop_attempted": True,
                    "compensation_stop_error_digest": (
                        sha256_bytes(str(compensation_error).encode())
                        if compensation_error is not None else None
                    ),
                    "alr_stopped": stopped, "mutations": mutations,
                    "observer_v2_integration": (
                        "FAILED_EXACT_POSTCHECK"
                        if "observer_v2" in str(exc) else "NOT_REACHED_OR_FAILED"
                    ),
                    "mutation_locks_released_before_observer": bool(lock_evidence),
                    "receipt_persisted": False, "boundaries": BOUNDARIES,
                }
                try:
                    failure["failure_ledger"] = self.runtime.persist_path(
                        RECEIPT_DIR / f"{self.approval['approval_id']}.phase2.failure.json",
                        failure,
                    )
                    failure["receipt_persisted"] = True
                except BaseException:
                    failure["failure_ledger_persist_failed"] = True
                return failure
            raise


def capture_phase1_facts(runtime: Runtime) -> dict[str, Any]:
    source = runtime.source_snapshot()
    execution_tree = runtime.execution_tree_lease()
    lane = runtime.lane_snapshot()
    protected = runtime.protected_snapshot()
    unit = runtime.unit_snapshot(expected_head=OLD_HEAD)
    pin = runtime.pin_snapshot(expected_head=OLD_HEAD)
    service = runtime.service_snapshot(require_active=True)
    unit_lock = runtime.unit_lock_snapshot()
    cost_lock = runtime.lock_snapshot(COST_LOCK, label="cost")
    alpha_lock = runtime.lock_snapshot(ALPHA_LOCK, label="alpha")
    live = runtime.live_inventory()
    ledger = runtime.ledger_inventory()
    if (
        unit["identity"].get("sha256") != OLD_UNIT_SHA256
        or pin["identity"].get("sha256") != OLD_PIN_SHA256
        or service.get("ALRSourceHead") != OLD_HEAD
        or service.get("NRestarts") not in {0, "0"}
    ):
        raise RollforwardError("phase1_capture_old_runtime_mismatch")
    return {
        "schema_version": SCHEMA,
        "status": "PHASE1_FACTS_CAPTURE_PASS",
        "target_head": TARGET_HEAD,
        "old_head": OLD_HEAD,
        "authorization_required_for_effect": AUTHORIZATION_SCHEMA,
        "source": source,
        "execution_tree": execution_tree,
        "lane": lane,
        "protected": protected,
        "protected_sha256": canonical_digest(protected),
        "old_unit": {"head": OLD_HEAD, "identity": unit["identity"]},
        "old_pin": {"head": OLD_HEAD, "identity": pin["identity"]},
        "active_service_identity": {
            key: service.get(key)
            for key in (
                "MainPID", "ProcessStartTicks", "InvocationID", "NRestarts",
                "ControlGroup", "ALRSourceHead", "ActiveState", "SubState",
                "ExecMainStartTimestampMonotonic", "FragmentPath", "NeedDaemonReload",
            )
            if key in service
        },
        "unit_lock_identity": unit_lock,
        "cost_lock_identity": cost_lock,
        "alpha_lock_identity": alpha_lock,
        "live_inventory": live,
        "live_inventory_sha256": runtime.inventory_digest(live),
        "ledger_inventory": ledger,
        "ledger_inventory_sha256": runtime.inventory_digest(ledger),
        "lane_effective_config": runtime.lane_effective_config(),
        "lane_effective_config_sha256": runtime.lane_effective_config_sha256(),
        "mutation_performed": False,
        "boundaries": BOUNDARIES,
    }


def capture_phase2_facts(
    runtime: Runtime, *, phase1_receipt: dict[str, str],
    phase1_closure: dict[str, str],
) -> dict[str, Any]:
    """Capture fresh post-Phase1 compiler facts without performing any mutation."""
    _raw_binding(phase1_receipt, label="capture_phase1_receipt")
    _raw_binding(phase1_closure, label="capture_phase1_closure")
    semantic_lineage = validate_phase1_semantic_lineage(
        runtime, phase1_receipt=phase1_receipt, phase1_closure=phase1_closure,
    )
    receipt = semantic_lineage["receipt"]
    closure = semantic_lineage["closure"]
    sealed = semantic_lineage["sealed_lineage"]
    private_raw, private_identity = runtime.load_bound(
        sealed["private_deps_receipt"], label="capture_private_deps_receipt"
    )
    private = strict_json(private_raw, label="capture_private_deps_receipt")
    if (
        private.get("status") != "APPLIED_POSTCHECK_PASS"
        or private.get("destination") != str(PRIVATE_BUNDLE_DESTINATION)
        or private.get("destination_manifest_sha256") != PRIVATE_BUNDLE_MANIFEST_SHA256
    ):
        raise RollforwardError("phase2_capture_private_receipt_invalid")

    source = runtime.source_snapshot()
    execution_tree = runtime.execution_tree_lease()
    lane = runtime.lane_snapshot()
    protected = runtime.protected_snapshot()
    unit = runtime.unit_snapshot(expected_head=OLD_HEAD)
    pin = runtime.pin_snapshot(expected_head=OLD_HEAD)
    service = runtime.service_snapshot(require_active=True)
    unit_lock = runtime.unit_lock_snapshot()
    cost_lock = runtime.lock_snapshot(COST_LOCK, label="cost")
    alpha_lock = runtime.lock_snapshot(ALPHA_LOCK, label="alpha")
    live = runtime.live_inventory()
    completion = runtime.artifact_inventory(COMPLETION_DIR, "*.completion.json")
    producer = runtime.artifact_inventory(PRODUCER_DIR, "blocked_outcome_review_*.json")
    ledger = runtime.ledger_inventory()
    staged_name = Path(sealed["staged_board"]["path"]).name
    if (
        unit["identity"].get("sha256") != OLD_UNIT_SHA256
        or pin["identity"].get("sha256") != OLD_PIN_SHA256
        or service.get("ALRSourceHead") != OLD_HEAD
        or service.get("NRestarts") not in {0, "0"}
        or staged_name in live
    ):
        raise RollforwardError("phase2_capture_old_runtime_or_live_absence_invalid")
    return {
        "schema_version": SCHEMA,
        "status": "PHASE2_FACTS_CAPTURE_PASS",
        "captured_at_utc": runtime.now().isoformat().replace("+00:00", "Z"),
        "target_head": TARGET_HEAD, "old_head": OLD_HEAD,
        "phase1_receipt": {
            "path": phase1_receipt["path"], "sha256": phase1_receipt["sha256"]
        },
        "phase1_closure": {
            "path": phase1_closure["path"], "sha256": phase1_closure["sha256"]
        },
        "phase1_closure_payload_digest": canonical_digest(closure),
        "sealed_lineage": sealed,
        "source": source, "execution_tree": execution_tree, "lane": lane,
        "protected": protected, "protected_sha256": canonical_digest(protected),
        "old_unit": {"head": OLD_HEAD, "identity": unit["identity"]},
        "old_pin": {"head": OLD_HEAD, "identity": pin["identity"]},
        "active_service_identity": service,
        "unit_lock_identity": unit_lock,
        "cost_lock_identity": cost_lock,
        "alpha_lock_identity": alpha_lock,
        "live_inventory": live,
        "live_inventory_sha256": runtime.inventory_digest(live),
        "admitted_live_board_absent": True,
        "completion_inventory": completion,
        "completion_inventory_sha256": runtime.inventory_digest(completion),
        "producer_inventory": producer,
        "producer_inventory_sha256": runtime.inventory_digest(producer),
        "ledger_inventory": ledger,
        "ledger_inventory_sha256": runtime.inventory_digest(ledger),
        "lane_effective_config": runtime.lane_effective_config(),
        "lane_effective_config_sha256": runtime.lane_effective_config_sha256(),
        "private_deps_receipt_identity": private_identity,
        "private_deps_destination": str(PRIVATE_BUNDLE_DESTINATION),
        "private_deps_manifest_sha256": PRIVATE_BUNDLE_MANIFEST_SHA256,
        "mutation_performed": False, "boundaries": BOUNDARIES,
    }


def read_bound_json(
    path: Path, *, label: str, expected_sha256: str | None = None
) -> tuple[dict[str, Any], dict[str, str]]:
    if not path.is_absolute() or "latest" in path.name.lower():
        raise RollforwardError(f"noncanonical_bound_path:{label}")
    raw, identity = load_pin_engine().read_regular_bytes(path)
    if (
        identity.get("nlink") != 1
        or re.fullmatch(r"[0-9a-f]{64}", str(identity.get("sha256", ""))) is None
        or (expected_sha256 is not None and identity["sha256"] != expected_sha256)
    ):
        raise RollforwardError(f"bound_hash_or_identity_mismatch:{label}")
    return strict_json(raw, label=label), {
        "path": str(path), "sha256": identity["sha256"]
    }


def authorized_effect_argv_digest(argv: list[str]) -> str:
    """Digest one exact ordered effect argv; no authorization file hash cycle."""
    return canonical_digest(argv)


def revalidate_cutover_lineage(
    bindings: dict[str, Any], *, phase1_receipt_path: Path,
    phase1_receipt_sha256: str,
) -> dict[str, dict[str, str]]:
    receipt = {
        "path": str(phase1_receipt_path), "sha256": phase1_receipt_sha256,
    }
    if bindings["lineage"].get("phase1_receipt") != receipt:
        raise RollforwardError("cutover_phase1_receipt_cli_binding_mismatch")
    reopened = {"phase1_receipt": receipt}
    for key in ("phase1_receipt", "phase1_closure", "sealed_lineage_bundle"):
        binding = bindings["lineage"][key]
        read_bound_json(
            Path(binding["path"]), label=key, expected_sha256=binding["sha256"]
        )
        reopened[key] = binding
    return reopened


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--phase1-preflight", action="store_true")
    modes.add_argument("--phase1-apply", action="store_true")
    modes.add_argument("--phase2-preflight", action="store_true")
    modes.add_argument("--phase2-apply", action="store_true")
    modes.add_argument("--capture-phase1-facts", action="store_true")
    modes.add_argument("--capture-phase2-facts", action="store_true")
    parser.add_argument("--authorization-json", type=Path)
    parser.add_argument("--runtime-bindings-json", type=Path)
    parser.add_argument("--runtime-bindings-sha256")
    parser.add_argument("--phase1-receipt-json", type=Path)
    parser.add_argument("--phase1-receipt-sha256")
    parser.add_argument("--phase1-closure-json", type=Path)
    parser.add_argument("--phase1-closure-sha256")
    args = parser.parse_args(raw_argv)
    selected = [
        args.phase1_preflight, args.phase1_apply,
        args.phase2_preflight, args.phase2_apply,
        args.capture_phase1_facts, args.capture_phase2_facts,
    ]
    if not any(selected):
        emit({"schema": SCHEMA, "status": "BLOCKED_NO_EFFECT", "reason": "explicit_phase_required", "boundaries": BOUNDARIES})
        return 4
    apply_mode = args.phase1_apply or args.phase2_apply
    previous: set[signal.Signals] | None = None
    try:
        if args.capture_phase1_facts:
            result = capture_phase1_facts(Runtime(discover=True))
            emit(result)
            return 0
        if args.capture_phase2_facts:
            if (
                args.phase1_receipt_json is None
                or args.phase1_closure_json is None
                or re.fullmatch(r"[0-9a-f]{64}", str(args.phase1_receipt_sha256 or "")) is None
                or re.fullmatch(r"[0-9a-f]{64}", str(args.phase1_closure_sha256 or "")) is None
            ):
                raise RollforwardError("phase2_capture_lineage_cli_binding_required")
            result = capture_phase2_facts(
                Runtime(discover=True),
                phase1_receipt={"path": str(args.phase1_receipt_json), "sha256": args.phase1_receipt_sha256},
                phase1_closure={"path": str(args.phase1_closure_json), "sha256": args.phase1_closure_sha256},
            )
            emit(result)
            return 0
        if (
            args.authorization_json is None
            or args.runtime_bindings_json is None
            or re.fullmatch(r"[0-9a-f]{64}", str(args.runtime_bindings_sha256 or "")) is None
        ):
            raise RollforwardError("formal_authority_cli_binding_required")
        phase_name = "stage" if (args.phase1_preflight or args.phase1_apply) else "cutover"
        authorization, authorization_binding = read_bound_json(
            args.authorization_json, label="runtime_authorization"
        )
        validate_runtime_authorization(authorization, phase=phase_name, now=Runtime.now())
        if authorization["governance_bindings"]["authorized_argv_digest"] != authorized_effect_argv_digest(raw_argv):
            raise RollforwardError("authorized_argv_digest_mismatch")
        bindings, bindings_binding = read_bound_json(
            args.runtime_bindings_json, label="phase_runtime_bindings",
            expected_sha256=args.runtime_bindings_sha256,
        )
        validate_phase_runtime_bindings(
            bindings, authorization, now=Runtime.now(),
            bindings_path=args.runtime_bindings_json,
        )
        service = bindings["protected_runtime_baseline"]["service_baseline"]
        configure_runtime_generation(
            target_head=authorization["expected_source_head"],
            old_head=authorization["expected_old_runtime_source_head"],
            old_pin_sha256=authorization["expected_old_pin_digest"].removeprefix("sha256:"),
            old_unit_sha256=service["unit_sha256"],
        )
        if phase_name == "cutover":
            if (
                args.phase1_receipt_json is None
                or re.fullmatch(r"[0-9a-f]{64}", str(args.phase1_receipt_sha256 or "")) is None
            ):
                raise RollforwardError("cutover_lineage_cli_binding_required")
            revalidate_cutover_lineage(
                bindings,
                phase1_receipt_path=args.phase1_receipt_json,
                phase1_receipt_sha256=args.phase1_receipt_sha256,
            )
        approval = derive_internal_plan(
            authorization, bindings,
            authorization_binding=authorization_binding,
            runtime_bindings_binding=bindings_binding,
        )
        runtime = Runtime(approval)
        transaction: Phase1Transaction | Phase2Transaction
        transaction = Phase1Transaction(runtime, approval) if (args.phase1_preflight or args.phase1_apply) else Phase2Transaction(runtime, approval)
        if apply_mode:
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, (signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
            result = transaction.apply()
        else:
            result = transaction.preflight()
        emit(result)
        return 0 if result.get("status") in {
            "PHASE1_STAGING_PREFLIGHT_PASS", "PHASE1_STAGING_APPLIED_PASS",
            "PHASE2_CUTOVER_PREFLIGHT_PASS", "PHASE2_APPLIED_POSTCHECK_PASS",
        } else 4
    except BaseException as exc:
        emit({
            "schema": SCHEMA,
            "status": "FAIL_CLOSED_UNVERIFIED" if apply_mode else "BLOCKED_NO_EFFECT",
            "error_type": type(exc).__name__, "error_digest": sha256_bytes(str(exc).encode()),
            "boundaries": {**BOUNDARIES, "mutation_performed": "unknown" if apply_mode else False},
        })
        return 4
    finally:
        if previous is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)


if __name__ == "__main__":
    raise SystemExit(main())
