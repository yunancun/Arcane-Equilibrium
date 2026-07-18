from __future__ import annotations

import copy
from datetime import datetime
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import types

import pytest


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE.parents[1] / "helper_scripts/maintenance_scripts/p0b_alr_two_natural_cycle_observer_v1.py"
TARGET_HEAD = "275901baa09656e842f14b11e94c00f9bfe0c380"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
FALSE_AUTHORITY = {
    "exchange_authority": False,
    "trading_authority": False,
    "order_or_probe_authority": False,
    "decision_lease_authority": False,
    "cost_gate_authority": False,
    "proof_authority": False,
    "serving_authority": False,
    "promotion_authority": False,
    "latest_authority": False,
}
ZERO_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_or_promotion_count": 0,
}
HEALTH_ZERO_COUNTERS = {
    "run_authority_mismatch_count": 0,
    "feedback_authority_mismatch_count": 0,
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_promotion_count": 0,
    "latest_pointer_update_count": 0,
}


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "p0b_cycle_observer_under_test", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _active() -> dict[str, str]:
    return {
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "running",
        "MainPID": "2001",
        "ProcessStartTicks": "9000000",
        "InvocationID": "a" * 32,
        "ExecMainStartTimestampMonotonic": "9000001",
        "NRestarts": "0",
        "Result": "success",
        "ExecMainCode": "0",
        "ExecMainStatus": "0",
        "FragmentPath": "/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service",
        "DropInPaths": "",
        "ControlGroup": "/user.slice/alr",
        "Environment": f"ALR_SOURCE_HEAD={TARGET_HEAD}",
        "NeedDaemonReload": "no",
    }


def _manager() -> dict[str, object]:
    return {
        "head": TARGET_HEAD,
        "conflicting_generation_environment": [],
        "fragment_path": "/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service",
        "drop_in_paths": "",
        "need_daemon_reload": "no",
        "active_required": True,
        "main_pid": "2001",
        "process_start_ticks": "9000000",
        "invocation_id": "a" * 32,
    }


class _Runtime:
    def source_snapshot(self):
        return {
            "boot_id": "boot",
            "uid": 1000,
            "gid": 1000,
            "branch": "main",
            "head": TARGET_HEAD,
            "clean": True,
        }

    def alr_active_snapshot(self):
        return copy.deepcopy(_active())

    def manager_loaded_alr_head(self, *, expected_head: str, require_active: bool):
        assert expected_head == TARGET_HEAD and require_active is True
        return copy.deepcopy(_manager())

    def assert_no_queued_systemd_job(self):
        return {"status": "NO_QUEUED_JOB", "unit": "openclaw-alr-shadow.service"}

    def assert_lane_quiescent(self):
        return {"owner": False, "processes": [], "scopes": []}


def _clean_index_inventory() -> str:
    return "".join(f"H tracked/file-{index:05d}\0" for index in range(8764))


@lru_cache(maxsize=None)
def _clean_stage_inventory(
    *, first_mode: str = "100644", first_stage: str = "0",
    tracked_gitmodules: bool = False,
) -> str:
    paths = [f"tracked/stage-file-{index:05d}" for index in range(8764)]
    if tracked_gitmodules:
        paths[0] = ".gitmodules"
    modes = [first_mode, *(["100644"] * 8763)]
    stages = [first_stage, *(["0"] * 8763)]
    base_size = sum(
        len(f"{mode} {'a' * 40} {stage}\t{path}\0".encode("utf-8"))
        for mode, stage, path in zip(modes, stages, paths)
    )
    eligible = list(range(1 if tracked_gitmodules else 0, len(paths)))
    padding, remainder = divmod(1_166_201 - base_size, len(eligible))
    for offset, index in enumerate(eligible):
        paths[index] += "x" * (padding + (offset < remainder))
    inventory = "".join(
        f"{mode} {'a' * 40} {stage}\t{path}\0"
        for mode, stage, path in zip(modes, stages, paths)
    )
    assert len(inventory.encode("utf-8")) == 1_166_201
    return inventory


def _recovery_module(
    *, git_calls=None, index_inventory: str | None = None,
    stage_inventory: str | None = None, shared_index_stdout: str = "",
    config_inventory: str | None = None,
):
    class RecoveryRuntime:
        @staticmethod
        def run(argv, *, cwd=None, env=None, timeout=60):
            if git_calls is not None:
                git_calls.append((list(argv), dict(env or {})))
            if "config" in argv:
                stdout = (
                    "core.repositoryformatversion\0core.filemode\0"
                    if config_inventory is None else config_inventory
                )
            elif "--shared-index-path" in argv:
                stdout = shared_index_stdout
            elif "--stage" in argv:
                stdout = (
                    _clean_stage_inventory()
                    if stage_inventory is None else stage_inventory
                )
            elif "ls-files" in argv and "-v" in argv:
                stdout = (
                    _clean_index_inventory()
                    if index_inventory is None
                    else index_inventory
                )
            else:
                raise AssertionError("baseline fixture only executes inventories")
            return types.SimpleNamespace(stdout=stdout)

        def git(self, *args):
            return self.run(
                ["/usr/bin/git", "-C", str(base.REPO), *args],
                env=base.SYSTEM_ENV,
            ).stdout.strip()

    class Runtime(_Runtime, RecoveryRuntime):
        pass

    base = types.SimpleNamespace(
        SYSTEM_ENV={
            "HOME": "/home/ncyu",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "USER": "ncyu",
            "LOGNAME": "ncyu",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        },
        REPO=Path("/home/ncyu/BybitOpenClaw/srv"),
        RecoveryRuntime=RecoveryRuntime,
    )
    return types.SimpleNamespace(Runtime=Runtime, base=base)


def _source_payload(index: int, *, microsecond: int = 0) -> dict[str, object]:
    minute = 41 + index
    source_at = _dt(f"2026-07-17T13:{minute:02d}:00Z").replace(
        microsecond=microsecond
    )
    return {
        "ts": source_at.isoformat(
            timespec="microseconds" if microsecond else "seconds"
        ).replace("+00:00", "Z"),
        "scan_id": f"scan-{index}",
        "active_symbols": ["BTCUSDT"],
        "added": [],
        "removed": [],
        "rejected_count": 0,
        "scan_duration_ms": 5,
        "candidates": [{"symbol": "BTCUSDT"}],
        "config": {"fixture": True},
    }


def _cycle(index: int, *, microsecond: int = 0) -> dict[str, object]:
    payload = _source_payload(index, microsecond=microsecond)
    source_hash = _sha(payload)
    source_at = _dt(str(payload["ts"]))
    lane_at = source_at.replace(second=10)
    details = {"rows_seen": 1, "persisted": 1, "duplicates": 0}
    scan_id = str(payload["scan_id"])
    source_key = f"{scan_id}|{payload['ts']}"
    return {
        "lane_success_event_id": f"00000000-0000-4000-8000-{index:012d}",
        "session_id": SESSION_ID,
        "lane_success_recorded_at": lane_at,
        "source_ts": source_at,
        "lane_source_scan_id": scan_id,
        "lane_source_scan_id_bytes": len(scan_id),
        "source_hash": source_hash,
        "details_bytes": 128,
        "details": details,
        "rows_seen_kind": "number",
        "rows_seen_text_bytes": 1,
        "rows_seen_value": 1,
        "source_table": "trading.scanner_snapshots",
        "source_key": source_key,
        "source_key_bytes": len(source_key),
        "source_scan_id": scan_id,
        "source_scan_id_bytes": len(scan_id),
        "typed_source_ts": source_at,
        "typed_source_hash": source_hash,
        "cycle_schema_version": "alr_scanner_cycle_v1",
        "source_artifact_kind": "scanner_cycle",
        "source_payload_bytes": 256,
        "source_canonical_payload": payload,
        "notification_event_id": f"10000000-0000-4000-8000-{index:012d}",
        "notification_recorded_at": source_at.replace(second=5),
        "notification_ts_ms": int(source_at.timestamp() * 1000),
    }


def _decision(module, cycle: dict[str, object]) -> tuple[dict[str, object], list[dict[str, object]]]:
    evaluated_at = cycle["source_ts"].isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    source_hashes = [str(cycle["source_hash"])]
    source_set_hash = _sha(source_hashes)
    evidence = {
        "schema_version": "alr_candidate_evidence_snapshot_v2",
        "source_status": "READY",
        "source_content_sha256": module.BOARD_SOURCE_CONTENT_SHA256,
        "board_hash": module.BOARD_HASH,
        "selection_hash": module.SELECTION_HASH,
        "audit_hash": module.BOARD_AUDIT_HASH,
        "candidate_set_hash": module.CANDIDATE_SET_HASH,
        "generated_at": "2026-07-17T12:27:01Z",
        "evaluated_at": evaluated_at,
        "cost_source_payload_sha256": None,
        "cost_normalized_projection_sha256": None,
        "cost_source_asof_utc": None,
    }
    handoff = {
        "schema_version": "alr_candidate_board_handoff_v1",
        "evidence": evidence,
        "source_head": TARGET_HEAD,
        "source_set_hash": source_set_hash,
        "source_cursor": {
            "source_hash": cycle["source_hash"],
            "source_key": cycle["source_key"],
            "source_ts": evaluated_at,
        },
        "decision_time": evaluated_at,
        "policy_input_hash": "c" * 64,
        "policy_config_hash": "d" * 64,
        "prior_decisions_hash": "e" * 64,
    }
    handoff["handoff_hash"] = _sha(handoff)
    decision = {
        "schema_version": "alr_candidate_learning_decision_v2",
        "decision_code": module.DECISION_CODE,
        "evaluated_at": evaluated_at,
        "source_head": TARGET_HEAD,
        "source_set_hash": source_set_hash,
        "evidence_source_status": "READY",
        "evidence_selection_hash": module.SELECTION_HASH,
        "candidate_set_hash": module.CANDIDATE_SET_HASH,
        "policy_hash": "d" * 64,
        "selected_candidate": None,
        "selected_collection_target": None,
        "candidate_count": 0,
        "eligible_candidate_count": 0,
        "evaluated_candidates": [],
        "training_run_created": False,
        "model_training_performed": False,
        "serving_ready": False,
        "promotion_ready": False,
        "order_or_probe_created": False,
        "no_authority": copy.deepcopy(FALSE_AUTHORITY),
        "authority_counters": copy.deepcopy(ZERO_COUNTERS),
    }
    decision["decision_hash"] = _sha(decision)
    payload = {
        "schema_version": "alr_candidate_learning_projection_artifact_v2",
        "decision_code": module.DECISION_CODE,
        "decision_hash": decision["decision_hash"],
        "selected_candidate": None,
        "selected_collection_target": None,
        "decision": decision,
        "source_refs": {
            "evidence_source_status": "READY",
            "evidence_selection_hash": module.SELECTION_HASH,
            "candidate_set_hash": module.CANDIDATE_SET_HASH,
            "handoff": handoff,
        },
        "training_run_created": False,
        "model_training_performed": False,
        "serving_ready": False,
        "promotion_ready": False,
        "order_or_probe_created": False,
        "next_stage": "WP4_VERSIONED_TRAINING_SCHEMA_REQUIRED",
        "no_authority": copy.deepcopy(FALSE_AUTHORITY),
        "authority_counters": copy.deepcopy(ZERO_COUNTERS),
    }
    artifact_hash = _sha(payload)
    row = {
        "artifact_hash": artifact_hash,
        "artifact_kind": "target_rotation",
        "created_at": cycle["lane_success_recorded_at"].replace(second=11),
        "payload_bytes": 4096,
        "canonical_payload": payload,
    }
    edge_body = {
        "from_artifact_hash": cycle["source_hash"],
        "to_artifact_hash": artifact_hash,
        "edge_role": "training_input",
    }
    edge = {
        **edge_body,
        "edge_hash": _sha(edge_body),
        "source_hash": cycle["source_hash"],
        "source_key": cycle["source_key"],
        "source_key_bytes": len(str(cycle["source_key"])),
        "source_ts": cycle["source_ts"],
        "source_scan_id": cycle["source_scan_id"],
        "source_scan_id_bytes": len(str(cycle["source_scan_id"])),
        "source_table": "trading.scanner_snapshots",
        "cycle_schema_version": "alr_scanner_cycle_v1",
    }
    return row, [edge]


def _write_metrics(index: int) -> dict[str, object]:
    return {
        "schema_version": "alr_write_metrics_v1",
        "scope": {
            "kind": "consumer_session_cumulative",
            "session_id": SESSION_ID,
            "through_completed_health_attempt": index,
        },
        "health": {
            "attempts": index,
            "emitted": index,
            "state_delta_writes": index,
            "heartbeat_writes": 0,
            "writes_suppressed": 0,
            "rows_written": index,
            "payload_bytes_written": index * 100,
            "suppression_ratio": 0.0,
        },
        "decision": {
            "attempts": index,
            "writes_suppressed": 0,
            "duplicate_retries": 0,
            "artifact_rows_written": index,
            "provenance_rows_written": index,
            "run_rows_written": 0,
            "feedback_rows_written": 0,
            "defer_artifact_rows_written": 0,
            "payload_bytes_written": index * 100,
            "source_rows_consumed": index,
            "suppression_ratio": 0.0,
        },
        "feedback": {
            "attempts": 0,
            "persisted": 0,
            "duplicate_retries": 0,
            "persisted_ratio": 0.0,
            "duplicate_retry_ratio": 0.0,
            "artifact_rows_written": 0,
            "provenance_rows_written": 0,
            "event_rows_written": 0,
            "total_rows_written": 0,
            "payload_bytes_written": 0,
        },
    }


def _health(cycle: dict[str, object], decision: dict[str, object], index: int) -> dict[str, object]:
    source_text = cycle["source_ts"].isoformat().replace("+00:00", "Z")
    lane_at = cycle["lane_success_recorded_at"]
    payload = {
        "schema_version": "alr_health_snapshot_v2",
        "source_head": TARGET_HEAD,
        "observed_at": lane_at.replace(second=12).isoformat().replace("+00:00", "Z"),
        "watermark": {
            "source_ts": source_text,
            "source_scan_id": cycle["source_scan_id"],
            "source_hash": cycle["source_hash"],
        },
        "ingestion": {
            "fresh_cursor_ts": source_text,
            "fresh_cursor_scan_id": cycle["source_scan_id"],
        },
        "target": {
            "run_hash": "f" * 64,
            "candidate_artifact_hash": "9" * 64,
            "run_status": "DEFER_EVIDENCE",
        },
        "failure": {"count": 0, "last_failure_at": None, "last_failure_code": None},
        "restart_recovery": {
            "watermark_present": True,
            "restart_count": 0,
            "unclean_recovery_count": 0,
            "last_success_at": lane_at.isoformat().replace("+00:00", "Z"),
            "source_duplicate_key_count": 0,
        },
        "authority_counters": copy.deepcopy(HEALTH_ZERO_COUNTERS),
        "no_authority": copy.deepcopy(FALSE_AUTHORITY),
        "write_metrics": _write_metrics(index),
    }
    payload["snapshot_hash"] = _sha(payload)
    return {
        "snapshot_hash": payload["snapshot_hash"],
        "source_head": TARGET_HEAD,
        "recorded_at": lane_at.replace(second=13),
        "fresh_cursor_ts": cycle["source_ts"],
        "fresh_cursor_scan_id": cycle["source_scan_id"],
        "payload_bytes": 8192,
        "canonical_payload": payload,
    }


def _standing() -> dict[str, object]:
    return {
        "run_hash": "f" * 64,
        "candidate_artifact_hash": "9" * 64,
        "run_status": "DEFER_EVIDENCE",
        "run_no_authority": copy.deepcopy(FALSE_AUTHORITY),
        "run_authority_counters": copy.deepcopy(ZERO_COUNTERS),
        "feedback_status": "DEFER_EVIDENCE",
        "proof_packet_present": False,
        "reward_record_count": 0,
        "rotate_next_target": True,
        "global_stop": False,
        "feedback_no_authority": copy.deepcopy(FALSE_AUTHORITY),
        "feedback_authority_counters": copy.deepcopy(ZERO_COUNTERS),
        "bound_to_both_health_targets": True,
    }


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows: list[dict[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=()):
        self.connection.executed.append((sql, params))
        module = self.connection.module
        if sql == module.TX_START_SQL:
            self.rows = [copy.deepcopy(self.connection.tx_start)]
        elif sql == module.OPEN_SESSION_SQL:
            self.rows = copy.deepcopy(self.connection.sessions)
        elif sql == module.CYCLES_SQL:
            candidates = [
                row
                for row in self.connection.cycles
                if not (
                    row.get("notification_event_id") is None
                    and row.get("notification_recorded_at") is None
                    and row.get("notification_ts_ms") is None
                )
            ]
            candidates.sort(
                key=lambda row: (
                    row["source_ts"],
                    str(row["lane_source_scan_id"]),
                    str(row["lane_success_event_id"]),
                ),
                reverse=True,
            )
            self.rows = copy.deepcopy(candidates[:257])
        elif sql == module.DECISION_SQL:
            self.rows = copy.deepcopy(
                self.connection.decisions.get(str(params[8]), [])
            )
        elif sql == module.EDGES_SQL:
            self.rows = copy.deepcopy(self.connection.edges[str(params[0])])
        elif sql == module.HEALTH_SQL:
            row = self.connection.health.get(str(params[4]))
            self.rows = [] if row is None else [copy.deepcopy(row)]
        elif sql == module.STANDING_DEFER_SQL:
            self.rows = [] if self.connection.standing is None else [copy.deepcopy(self.connection.standing)]
        elif sql == module.TX_FINAL_SQL:
            self.rows = [copy.deepcopy(self.connection.tx_final)]
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return None if not self.rows else self.rows[0]

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, module, *, cycle_count: int = 2, source_microsecond: int = 0):
        self.module = module
        self.executed = []
        self.set_session_calls = []
        self.rollbacks = 0
        self.closed = False
        self.tx_start = {
            "transaction_read_only": "on",
            "transaction_isolation": "repeatable read",
            "search_path": "pg_catalog",
            "statement_timeout": "15s",
            "lock_timeout": "1s",
            "idle_timeout": "30s",
            "current_user": "alr_shadow",
            "current_database": "trading_ai",
            "server_addr": "127.0.0.1",
            "server_port": 5432,
            "txid_current_if_assigned": None,
        }
        self.tx_final = {
            "tuples_inserted": 0,
            "tuples_updated": 0,
            "tuples_deleted": 0,
            "txid_current_if_assigned": None,
        }
        self.sessions = [
            {
                "session_id": SESSION_ID,
                "start_event_id": "20000000-0000-4000-8000-000000000001",
                "started_at": _dt("2026-07-17T13:41:02Z"),
            }
        ]
        all_cycles = [
            _cycle(1, microsecond=source_microsecond),
            _cycle(2, microsecond=source_microsecond),
        ]
        self.cycles = all_cycles[:cycle_count]
        self.decisions: dict[str, list[dict[str, object]]] = {}
        self.edges: dict[str, list[dict[str, object]]] = {}
        self.health: dict[str, dict[str, object]] = {}
        for index, cycle in enumerate(all_cycles, 1):
            decision, edges = _decision(module, cycle)
            self.decisions[str(cycle["source_hash"])] = [decision]
            self.edges[str(decision["artifact_hash"])] = edges
            self.health[str(cycle["source_hash"])] = _health(cycle, decision, index)
        self.standing = _standing()

    def set_session(self, **kwargs):
        self.set_session_calls.append(kwargs)

    def cursor(self):
        return _Cursor(self)

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _RuntimeFiles:
    def __init__(
        self,
        module,
        *,
        drift_after: bool = False,
        git_metadata_drift: str | None = None,
        git_path_drift: str | None = None,
        git_attributes_present: bool = False,
    ):
        self.module = module
        self.drift_after = drift_after
        self.git_metadata_drift = git_metadata_drift
        self.git_path_drift = git_path_drift
        self.git_attributes_present = git_attributes_present
        self.git_path_calls = 0
        self.calls = {
            "unit": 0,
            "pin": 0,
            "info_exclude": 0,
            "index": 0,
            "passwd": 0,
            "group": 0,
        }
        self.pin_raw = (
            '{\n  "head": "275901baa09656e842f14b11e94c00f9bfe0c380",\n'
            '  "derived_at_utc": "2026-07-17T13:41:01Z",\n'
            '  "writer": "derive_expected_source_head.sh",\n'
            '  "base_dir": "/home/ncyu/BybitOpenClaw/srv"\n}\n'
        ).encode()

    def __call__(self, path, expected_sha256, **_kwargs):
        if path == self.module.UNIT_PATH:
            label = "unit"
        elif path == self.module.PIN_PATH:
            label = "pin"
        elif str(path).endswith("/.git/info/exclude"):
            label = "info_exclude"
        elif str(path).endswith("/.git/index"):
            label = "index"
        elif str(path) == "/etc/passwd":
            label = "passwd"
        elif str(path) == "/etc/group":
            label = "group"
        else:
            raise AssertionError(f"unexpected fixed file: {path}")
        self.calls[label] += 1
        if label == "unit":
            raw = f"Environment=ALR_SOURCE_HEAD={TARGET_HEAD}\n".encode()
        elif label == "pin":
            raw = self.pin_raw
        elif label == "info_exclude":
            raw = b"#" * 240
        elif label == "index":
            raw = b"I" * 1_322_183
        elif label == "passwd":
            prefix = b"ncyu:x:1000:1000:NCYu:/home/ncyu:/bin/bash\n"
            raw = prefix + b"#" * (3_100 - len(prefix))
        else:
            prefix = b"ncyu:x:1000:\n"
            raw = prefix + b"#" * (1_183 - len(prefix))
        identity = {
            "dev": 66_312 if label in {"passwd", "group"} else 1,
            "ino": {
                "unit": 10,
                "pin": 11,
                "info_exclude": 12,
                "index": 13,
                "passwd": 19_139_851,
                "group": 19_139_973,
            }[label],
            "uid": 0 if label in {"passwd", "group"} else 1000,
            "gid": 0 if label in {"passwd", "group"} else 1000,
            "mode": (
                0o600
                if label in {"unit", "pin"}
                else 0o644
                if label in {"passwd", "group"}
                else 0o664
            ),
            "nlink": 1,
            "size": len(raw),
            "mtime_ns": 1,
            "ctime_ns": 1,
            "sha256": expected_sha256,
        }
        if (
            self.drift_after
            and label in {"unit", "pin"}
            and self.calls[label] > 1
        ):
            identity["ino"] += 100
        if self.git_metadata_drift == label and self.calls[label] > 1:
            identity["ino"] += 100
        return raw, identity

    def observe_git_paths(self):
        self.git_path_calls += 1
        if self.git_attributes_present:
            raise self.module.ObserverUnverified(
                "recovery_git_info_attributes_present"
            )
        repo = {
            "dev": 66_312,
            "ino": 60_430_267,
            "uid": 1000,
            "gid": 1000,
            "mode": 0o775,
            "nlink": 21,
            "size": 4096,
            "mtime_ns": 1,
            "ctime_ns": 1,
        }
        git = {
            "dev": 66_312,
            "ino": 60_430_269,
            "uid": 1000,
            "gid": 1000,
            "mode": 0o775,
            "nlink": 8,
            "size": 4096,
            "mtime_ns": 1,
            "ctime_ns": 1,
        }
        if self.git_path_calls > 1 and self.git_path_drift == "repo":
            repo["ino"] += 1
        if self.git_path_calls > 1 and self.git_path_drift == "git":
            git["ino"] += 1
        return {
            "repo": repo,
            "git": git,
            "info_attributes_absent": True,
            "private_group_boundary": (
                "uid_gid_1000_same_principal_private_primary_group"
            ),
        }


def _trust(module) -> dict[str, object]:
    return {
        "lower_bound": _dt("2026-07-17T13:41:01.096052Z"),
        "lower_bound_text": "2026-07-17T13:41:01.096052+00:00",
        "service_identity": module._active_identity(_active()),
        "board": {"candidate_count": 0},
    }


def _lock_evidence(pid: int) -> dict[str, object]:
    return {
        "pid": pid,
        "fd": 3,
        "dev": 63,
        "ino": 101465,
        "mode": "0600",
        "owner": {"uid": 1000, "gid": 1000},
        "granted_write_flock_count": 1,
    }


def _run(
    module,
    connection: _Connection,
    *,
    files=None,
    recovery_loader=_recovery_module,
    environment=None,
    **kwargs,
):
    runtime_files = files or _RuntimeFiles(module)
    return module.run_observation(
        trust_loader=lambda _reader: _trust(module),
        file_reader=runtime_files,
        recovery_module_loader=recovery_loader,
        dsn_loader=lambda: {
            "host": "127.0.0.1",
            "port": "5432",
            "dbname": "trading_ai",
            "user": "alr_shadow",
            "password": "secret-not-output",
        },
        connect=lambda _parameters: connection,
        lock_observer=_lock_evidence,
        environment={} if environment is None else environment,
        now=lambda: _dt("2026-07-17T13:50:00Z"),
        **kwargs,
    )


def _reseal_decision(connection: _Connection, source_hash: str) -> None:
    row = connection.decisions[source_hash][0]
    payload = row["canonical_payload"]
    decision = payload["decision"]
    decision["decision_hash"] = _sha(
        {key: value for key, value in decision.items() if key != "decision_hash"}
    )
    payload["decision_hash"] = decision["decision_hash"]
    handoff = payload["source_refs"]["handoff"]
    handoff["handoff_hash"] = _sha(
        {key: value for key, value in handoff.items() if key != "handoff_hash"}
    )
    old_hash = row["artifact_hash"]
    row["artifact_hash"] = _sha(payload)
    edges = connection.edges.pop(old_hash)
    for edge in edges:
        edge["to_artifact_hash"] = row["artifact_hash"]
        edge["edge_hash"] = _sha(
            {
                "from_artifact_hash": edge["from_artifact_hash"],
                "to_artifact_hash": edge["to_artifact_hash"],
                "edge_role": edge["edge_role"],
            }
        )
    connection.edges[row["artifact_hash"]] = edges


def _reseal_health(row: dict[str, object]) -> None:
    payload = row["canonical_payload"]
    payload["snapshot_hash"] = _sha(
        {key: value for key, value in payload.items() if key != "snapshot_hash"}
    )
    row["snapshot_hash"] = payload["snapshot_hash"]


def test_two_natural_cycles_pass_with_rollback_and_narrow_claims() -> None:
    module = _load_module()
    connection = _Connection(module)

    result = _run(module, connection)

    assert result["status"] == "PASS", result
    assert result["cycle_count"] == 2
    assert result["claims"]["two_natural_cycles_observed"] is True
    assert result["claims"]["current_os_process_singleton_observed"] is True
    assert result["claims"]["cryptographic_process_session_binding_claimed"] is False
    assert result["claims"]["current_fit_claimed"] is False
    assert result["standing_defer"]["scope"] == (
        "latest_global_run_bound_to_both_post_restart_health_snapshots"
    )
    assert result["standing_defer"]["current_source_head_or_fit_claimed"] is False
    assert connection.set_session_calls == [
        {"readonly": True, "isolation_level": "REPEATABLE READ", "autocommit": False}
    ]
    assert connection.rollbacks == 1 and connection.closed is True
    assert "secret-not-output" not in json.dumps(result)


def test_one_natural_cycle_is_pending() -> None:
    module = _load_module()
    result = _run(module, _Connection(module, cycle_count=1))
    assert result["status"] == "PENDING"
    assert result["cycle_count"] == 1


def test_idle_heartbeat_is_skipped_and_never_counted_as_cycle() -> None:
    module = _load_module()
    connection = _Connection(module)
    connection.cycles[0]["details"]["rows_seen"] = 0
    connection.cycles[0]["rows_seen_value"] = 0
    result = _run(module, connection)
    assert result["status"] == "PENDING"
    assert result["cycle_count"] == 1
    assert result["claims"]["idle_heartbeat_counted_as_cycle"] is False


def test_fixed_trust_roots_private_dependency_path_and_cli_cannot_swap(capsys) -> None:
    module = _load_module()
    assert not hasattr(module, "ObserverConfig")
    assert module.APPLY_RECEIPT_PATH == Path(
        "/home/ncyu/BybitOpenClaw/srv/target/codex-context/"
        "p0b-alr-recovery-apply-receipt.json"
    )
    assert module.PSYCOPG_LIBS_PATH == Path(
        "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps/"
        "site-packages/psycopg2_binary.libs"
    )
    assert module.main(["--apply-receipt-json", "/tmp/attacker.json"]) == 5
    assert json.loads(capsys.readouterr().out)["reason_codes"] == [
        "cli_arguments_forbidden"
    ]


def test_non_isolated_invocation_is_rejected(capsys) -> None:
    module = _load_module()
    assert module.main([]) == 5
    assert json.loads(capsys.readouterr().out)["reason_codes"] == [
        "isolated_mode_required"
    ]


def test_source_surface_requires_isolated_no_bytecode_and_has_no_mutation_import() -> None:
    source = MODULE_PATH.read_text()
    assert "sys.flags.isolated != 1" in source
    assert "sys.dont_write_bytecode is not True" in source
    assert "ml_training.alr_event_consumer" not in source
    assert "subprocess" not in source
    assert ".commit(" not in source


def test_exact_receipt_and_recovery_loader_return_module(monkeypatch) -> None:
    module = _load_module()
    receipt = json.loads(
        (HERE.parents[1] / "tests/fixtures/p0b-alr-recovery-apply-receipt.json").read_text()
    )
    admitted = module._validate_apply_receipt(receipt)
    assert admitted["lower_bound_text"] == "2026-07-17T13:41:01.096052+00:00"

    bad_receipt = copy.deepcopy(receipt)
    bad_receipt["transaction_adapter"]["sha256"] = "0" * 64
    with pytest.raises(module.ObserverUnverified, match="apply_transaction_adapter_invalid"):
        module._validate_apply_receipt(bad_receipt)

    recovery_raw = b"class Runtime:\n    pass\n"
    monkeypatch.setattr(module, "_read_bound_file", lambda *_args, **_kwargs: (recovery_raw, {}))
    loaded = module.load_exact_recovery_module()
    assert loaded.__file__ == str(module.RECOVERY_V2_PATH)
    assert hasattr(loaded, "Runtime")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("duplicate_notification", "consumed_notifications_not_distinct"),
        ("notification_ts", "cycle_notification_source_timestamp_mismatch"),
        ("notification_before_session", "cycle_time_causality_invalid"),
        ("session_before_lower_bound", "current_open_session_invalid"),
        ("duplicate_decision", "decision_same_cursor_ambiguous"),
    ],
)
def test_cycle_session_and_decision_ambiguity_fail_closed(mutation: str, reason: str) -> None:
    module = _load_module()
    connection = _Connection(module)
    if mutation == "duplicate_notification":
        connection.cycles[1]["notification_event_id"] = connection.cycles[0][
            "notification_event_id"
        ]
    elif mutation == "notification_ts":
        connection.cycles[0]["notification_ts_ms"] += 1
    elif mutation == "notification_before_session":
        connection.cycles[0]["notification_recorded_at"] = _dt(
            "2026-07-17T13:41:01Z"
        )
    elif mutation == "session_before_lower_bound":
        connection.sessions[0]["started_at"] = _dt("2026-07-17T13:41:00Z")
    else:
        source_hash = str(connection.cycles[0]["source_hash"])
        connection.decisions[source_hash].append(
            copy.deepcopy(connection.decisions[source_hash][0])
        )
    result = _run(module, connection)
    assert result["status"] == "FAIL"
    assert result["reason_codes"] == [reason]


def test_source_payload_hash_and_decision_board_cursor_time_are_bound() -> None:
    module = _load_module()
    connection = _Connection(module)
    connection.cycles[0]["source_canonical_payload"]["config"] = {"tampered": True}
    result = _run(module, connection)
    assert result["reason_codes"] == ["cycle_source_payload_hash_mismatch"]

    for field, bad_value, expected_reason in (
        ("board_hash", "0" * 64, "decision_handoff_evidence_invalid"),
        ("evaluated_at", "2026-07-17T13:40:00Z", "decision_handoff_evidence_invalid"),
    ):
        connection = _Connection(module)
        source_hash = str(connection.cycles[0]["source_hash"])
        handoff = connection.decisions[source_hash][0]["canonical_payload"]["source_refs"]["handoff"]
        handoff["evidence"][field] = bad_value
        _reseal_decision(connection, source_hash)
        result = _run(module, connection)
        assert result["status"] == "FAIL"
        assert result["reason_codes"] == [expected_reason]


def test_health_targets_must_match_and_global_standing_must_bind_both() -> None:
    module = _load_module()
    connection = _Connection(module)
    second_hash = str(connection.cycles[1]["source_hash"])
    second_health = connection.health[second_hash]
    second_health["canonical_payload"]["target"]["run_hash"] = "8" * 64
    _reseal_health(second_health)
    result = _run(module, connection)
    assert result["reason_codes"] == ["health_targets_not_identical"]

    connection = _Connection(module)
    connection.standing["run_hash"] = "8" * 64
    connection.standing["bound_to_both_health_targets"] = False
    result = _run(module, connection)
    assert result["status"] == "FAIL"
    assert result["reason_codes"] == ["standing_latest_run_health_target_mismatch"]

    connection = _Connection(module)
    for field in (
        "feedback_status",
        "proof_packet_present",
        "reward_record_count",
        "rotate_next_target",
        "global_stop",
        "feedback_no_authority",
        "feedback_authority_counters",
    ):
        connection.standing[field] = None
    result = _run(module, connection)
    assert result["status"] == "PENDING"
    assert result["reason_codes"] == ["latest_global_run_feedback_pending"]


@pytest.mark.parametrize(
    ("section", "field", "reason"),
    [
        ("failure", "count", "health_failure_count_increased"),
        ("restart_recovery", "restart_count", "health_restart_count_increased"),
        ("restart_recovery", "unclean_recovery_count", "health_unclean_count_increased"),
        ("restart_recovery", "source_duplicate_key_count", "health_source_duplicate_count_increased"),
    ],
)
def test_health_bad_counters_cannot_increase(section: str, field: str, reason: str) -> None:
    module = _load_module()
    connection = _Connection(module)
    second_hash = str(connection.cycles[1]["source_hash"])
    payload = connection.health[second_hash]["canonical_payload"]
    payload[section][field] = 1
    _reseal_health(connection.health[second_hash])
    result = _run(module, connection)
    assert result["status"] == "FAIL"
    assert result["reason_codes"] == [reason]


def test_health_notification_duplicates_and_attempt_nonincrease_fail() -> None:
    module = _load_module()
    connection = _Connection(module)
    second_hash = str(connection.cycles[1]["source_hash"])
    payload = connection.health[second_hash]["canonical_payload"]
    payload["notifications"] = {"received": 2, "consumed": 2, "duplicate": 1, "invalid": 0}
    _reseal_health(connection.health[second_hash])
    result = _run(module, connection)
    assert result["reason_codes"] == ["health_notification_duplicate_count_increased"]

    connection = _Connection(module)
    second_hash = str(connection.cycles[1]["source_hash"])
    payload = connection.health[second_hash]["canonical_payload"]
    payload["write_metrics"]["health"]["attempts"] = 1
    payload["write_metrics"]["scope"]["through_completed_health_attempt"] = 1
    _reseal_health(connection.health[second_hash])
    result = _run(module, connection)
    assert result["reason_codes"] == ["health_attempts_not_increasing"]

    connection = _Connection(module)
    second_hash = str(connection.cycles[1]["source_hash"])
    payload = connection.health[second_hash]["canonical_payload"]
    payload["write_metrics"]["decision"]["attempts"] = 1
    _reseal_health(connection.health[second_hash])
    result = _run(module, connection)
    assert result["reason_codes"] == ["health_decision_attempts_not_increasing"]


def test_unit_pin_and_service_identity_after_drift_fail() -> None:
    module = _load_module()
    result = _run(module, _Connection(module), files=_RuntimeFiles(module, drift_after=True))
    assert result["reason_codes"] == ["unit_or_pin_changed_during_database_observation"]

    class DriftingRuntime(_Runtime):
        def __init__(self):
            self.calls = 0

        def alr_active_snapshot(self):
            self.calls += 1
            active = _active()
            if self.calls > 2:
                active["MainPID"] = "2002"
            return active

        def manager_loaded_alr_head(self, *, expected_head: str, require_active: bool):
            manager = _manager()
            if self.calls > 2:
                manager["main_pid"] = "2002"
            return manager

    def recovery_loader():
        recovery = _recovery_module()

        class Runtime(DriftingRuntime, recovery.base.RecoveryRuntime):
            pass

        recovery.Runtime = Runtime
        return recovery

    result = _run(module, _Connection(module), recovery_loader=recovery_loader)
    assert result["reason_codes"] == ["runtime_identity_changed_during_database_observation"]


@pytest.mark.parametrize(
    ("location", "field", "value"),
    [
        ("start", "statement_timeout", "0"),
        ("start", "txid_current_if_assigned", "42"),
        ("final", "tuples_inserted", 1),
        ("final", "txid_current_if_assigned", "42"),
    ],
)
def test_readonly_transaction_guards_fail_and_still_rollback(location: str, field: str, value: object) -> None:
    module = _load_module()
    connection = _Connection(module)
    getattr(connection, f"tx_{location}")[field] = value
    result = _run(module, connection)
    assert result["status"] == "FAIL"
    assert result["reason_codes"] == [
        "readonly_transaction_start_guard_failed"
        if location == "start"
        else "readonly_transaction_effect_guard_failed"
    ]
    assert connection.rollbacks == 1 and connection.closed is True


def test_dsn_ambient_environment_connect_options_and_sql_bounds(monkeypatch) -> None:
    module = _load_module()
    credential_key = "pass" + "word"
    credential_value = "fixture-value-not-a-credential"
    valid = " ".join((
        "host=127.0.0.1", "port=5432", "dbname=trading_ai",
        "user=alr_shadow", f"{credential_key}={credential_value}",
    ))
    assert set(module.parse_exact_dsn_text(valid)) == {"host", "port", "dbname", "user", "password"}
    for extra in (" options=-csearch_path=public", " passfile=/tmp/pw"):
        with pytest.raises(module.ObserverUnverified, match="dsn_invalid"):
            module.parse_exact_dsn_text(valid + extra)
    result = _run(module, _Connection(module), environment={"PGHOST": "attacker"})
    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["ambient_pg_environment_present"]

    calls = []
    fake = types.SimpleNamespace(connect=lambda **kwargs: calls.append(kwargs) or object())
    monkeypatch.setattr(module, "load_verified_psycopg2", lambda: (fake, "cursor", {}))
    module.connect_readonly(module.parse_exact_dsn_text(valid))
    assert calls == [{
        "host": "127.0.0.1", "port": 5432, "dbname": "trading_ai",
        "user": "alr_shadow", "password": credential_value, "sslmode": "disable",
        "application_name": module.PG_APPLICATION_NAME, "connect_timeout": 5,
        "options": module.PG_OPTIONS, "cursor_factory": "cursor",
    }]
    assert "default_transaction_read_only=on" in module.PG_OPTIONS
    assert "statement_timeout=15000" in module.PG_OPTIONS
    assert "idle_in_transaction_session_timeout=30000" in module.PG_OPTIONS
    assert "LIMIT 257" in module.CYCLES_SQL
    assert "LIMIT 4097" in module.EDGES_SQL
    assert "LIMIT 2" in module.DECISION_SQL and "LIMIT 2" in module.OPEN_SESSION_SQL
    assert "feedback_artifact_hash DESC" in module.STANDING_DEFER_SQL
    for sql in (
        module.TX_START_SQL, module.OPEN_SESSION_SQL, module.CYCLES_SQL,
        module.DECISION_SQL, module.EDGES_SQL, module.HEALTH_SQL,
        module.STANDING_DEFER_SQL, module.TX_FINAL_SQL,
    ):
        assert sql.lstrip().startswith(("SELECT", "WITH"))
        assert ";" not in sql


def test_private_bundle_mapping_is_fixed_to_psycopg2_binary_libs(monkeypatch) -> None:
    module = _load_module()
    extension = module.PSYCOPG_PACKAGE_PATH / module.PSYCOPG_EXTENSION_NAME
    private_lib = module.PSYCOPG_LIBS_PATH / next(iter(module.PSYCOPG_LIB_MANIFEST))
    monkeypatch.setattr(module, "_verify_root_owned_system_path", lambda _path: None)
    attestation = module._validate_mapped_dependencies(
        set(), {extension, private_lib, Path("/usr/lib/libc.so.6")}
    )
    assert attestation["extension_mapped"] is True
    assert module.PSYCOPG_LIBS_PATH.parent == module.PRIVATE_SITE_PACKAGES
    rogue = module.PRIVATE_DEPS_ROOT / "rogue.so"
    with pytest.raises(module.ObserverUnverified, match="unsealed_private_dependency_mapped"):
        module._validate_mapped_dependencies(set(), {extension, rogue})


def test_private_bundle_exact_file_sets_modes_and_hashes(monkeypatch, tmp_path) -> None:
    module = _load_module()
    root = tmp_path / "p0b-observer-deps"
    site = root / "site-packages"
    package = site / "psycopg2"
    libraries = site / "psycopg2_binary.libs"
    package.mkdir(parents=True)
    libraries.mkdir()
    for directory in (root, site, package, libraries):
        directory.chmod(0o700)
    package_names = [module.PSYCOPG_EXTENSION_NAME] + [
        f"sealed_{index}.py" for index in range(11)
    ]
    library_names = [f"libsealed{index}.so" for index in range(15)]
    package_manifest = {}
    lib_manifest = {}
    for name in package_names:
        raw = f"package:{name}".encode()
        path = package / name
        path.write_bytes(raw)
        path.chmod(0o700 if name == module.PSYCOPG_EXTENSION_NAME else 0o600)
        package_manifest[name] = hashlib.sha256(raw).hexdigest()
    for name in library_names:
        raw = f"library:{name}".encode()
        path = libraries / name
        path.write_bytes(raw)
        path.chmod(0o700)
        lib_manifest[name] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(module, "PRIVATE_DEPS_ROOT", root)
    monkeypatch.setattr(module, "PSYCOPG_PACKAGE_MANIFEST", package_manifest)
    monkeypatch.setattr(module, "PSYCOPG_LIB_MANIFEST", lib_manifest)
    monkeypatch.setattr(module, "EXPECTED_UID", os.getuid())
    monkeypatch.setattr(module, "EXPECTED_GID", os.getgid())
    monkeypatch.setattr(module, "_validate_owned_parent_chain", lambda *_args, **_kwargs: None)
    result = module.verify_private_psycopg_bundle()
    assert len(result["files"]) == 27

    (package / "__pycache__").mkdir()
    with pytest.raises(module.ObserverUnverified, match="psycopg_package_entry_set_invalid"):
        module.verify_private_psycopg_bundle()


def test_singleton_lock_requires_one_pid_fd_and_one_granted_write_flock(monkeypatch, tmp_path) -> None:
    module = _load_module()
    pid = 4321
    lock = tmp_path / "consumer.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    proc = tmp_path / "proc"
    fd_root = proc / str(pid) / "fd"
    fd_root.mkdir(parents=True)
    (fd_root / "3").symlink_to(lock)
    observed = lock.stat()
    device_inode = (
        f"{os.major(observed.st_dev):02x}:{os.minor(observed.st_dev):02x}:"
        f"{observed.st_ino}"
    )
    locks = proc / "locks"
    row = f"7: FLOCK ADVISORY WRITE {pid} {device_inode} 0 EOF\n"
    locks.write_text(row)
    monkeypatch.setattr(module, "SINGLETON_LOCK_PATH", lock)
    monkeypatch.setattr(module, "PROC_ROOT", proc)
    monkeypatch.setattr(module, "PROC_LOCKS_PATH", locks)
    monkeypatch.setattr(module, "EXPECTED_UID", os.getuid())
    monkeypatch.setattr(module, "EXPECTED_GID", os.getgid())
    evidence = module.observe_singleton_lock(pid)
    assert evidence["fd"] == 3
    assert evidence["granted_write_flock_count"] == 1

    locks.write_text(row + row.replace("7:", "8:"))
    with pytest.raises(module.ObserverFail, match="singleton_proc_lock_binding_invalid"):
        module.observe_singleton_lock(pid)


@pytest.mark.parametrize(("surface", "reason"), [
    ("edges", "decision_edge_row_limit_exceeded"),
])
def test_database_result_cardinality_overflow_is_unverified(surface: str, reason: str) -> None:
    module = _load_module()
    connection = _Connection(module)
    first_hash = str(connection.cycles[0]["source_hash"])
    artifact_hash = str(connection.decisions[first_hash][0]["artifact_hash"])
    connection.edges[artifact_hash] = [
        copy.deepcopy(connection.edges[artifact_hash][0]) for _ in range(4097)
    ]
    result = _run(module, connection)
    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == [reason]


def test_rollback_failure_is_unverified() -> None:
    module = _load_module()

    class RollbackFailure(_Connection):
        def rollback(self):
            raise RuntimeError("rollback failed")

    result = _run(module, RollbackFailure(module))
    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["readonly_transaction_rollback_unverified"]


def test_every_git_subprocess_overrides_local_stat_cache_and_redirect_surfaces() -> None:
    module = _load_module()
    calls = []
    base = types.SimpleNamespace(
        SYSTEM_ENV={
            "HOME": "/home/ncyu",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "USER": "ncyu",
            "LOGNAME": "ncyu",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        },
        REPO=Path("/home/ncyu/BybitOpenClaw/srv"),
    )

    class RecoveryRuntime:
        @staticmethod
        def run(argv, *, cwd=None, env=None, timeout=60):
            calls.append((list(argv), dict(env or {})))
            if "config" in argv:
                stdout = (
                    "core.repositoryformatversion\0remote.origin.url\0"
                    "core.trustctime\0core.ignorecase\0"
                )
            elif "--shared-index-path" in argv:
                stdout = ""
            elif "--stage" in argv:
                stdout = _clean_stage_inventory()
            elif "ls-files" in argv and "-v" in argv:
                stdout = _clean_index_inventory()
            elif "symbolic-ref" in argv:
                stdout = "main\n"
            elif "rev-parse" in argv:
                stdout = TARGET_HEAD + "\n"
            elif "status" in argv:
                stdout = ""
            else:
                raise AssertionError(argv)
            return types.SimpleNamespace(stdout=stdout)

        def git(self, *args):
            return self.run(
                ["/usr/bin/git", "-C", str(base.REPO), *args],
                env=base.SYSTEM_ENV,
            ).stdout.strip()

        def source_snapshot(self):
            return {
                "boot_id": "boot",
                "uid": 1000,
                "gid": 1000,
                "branch": self.git("symbolic-ref", "--short", "HEAD"),
                "head": self.git("rev-parse", "HEAD"),
                "clean": self.git(
                    "status", "--porcelain=v1", "--untracked-files=all"
                ) == "",
            }

    base.RecoveryRuntime = RecoveryRuntime

    class Runtime(RecoveryRuntime, _Runtime):
        pass

    recovery = types.SimpleNamespace(base=base, Runtime=Runtime)
    result = _run(module, _Connection(module), recovery_loader=lambda: recovery)
    assert result["status"] == "PASS", result
    assert len(calls) == 10
    expected_prefix = [
        "/usr/bin/git",
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "trace2.normalTarget=0",
        "-c",
        "trace2.perfTarget=0",
        "-c",
        "trace2.eventTarget=0",
        "-c",
        "core.ignoreStat=false",
        "-c",
        "core.fileMode=true",
        "-c",
        "core.checkStat=default",
        "-c",
        "core.symlinks=true",
        "-c",
        "core.trustctime=true",
        "-c",
        "core.ignoreCase=false",
        "-c",
        "core.attributesFile=/dev/null",
        "-c",
        "core.excludesFile=/dev/null",
        "--git-dir=/home/ncyu/BybitOpenClaw/srv/.git",
        "--work-tree=/home/ncyu/BybitOpenClaw/srv",
        "-C",
        "/home/ncyu/BybitOpenClaw/srv",
    ]
    assert len(expected_prefix) == 32
    assert calls[0][0][32:] == [
        "config",
        "--local",
        "--includes",
        "--null",
        "--name-only",
        "--list",
    ]
    assert calls[1][0][32:] == ["rev-parse", "--shared-index-path"]
    assert calls[2][0][32:] == ["ls-files", "-v", "-z"]
    assert calls[3][0][32:] == ["ls-files", "--stage", "-z"]
    assert [argv[32:] for argv, _env in calls[4:]] == [
        ["symbolic-ref", "--short", "HEAD"],
        ["rev-parse", "HEAD"],
        [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=all",
        ],
    ] * 2
    for argv, environment in calls:
        assert argv[:32] == expected_prefix
        assert environment["GIT_OPTIONAL_LOCKS"] == "0"
        assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
        assert environment["GIT_CONFIG_SYSTEM"] == "/dev/null"
        assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
        assert environment["GIT_TRACE2"] == "0"
        assert environment["GIT_TRACE2_PERF"] == "0"
        assert environment["GIT_TRACE2_EVENT"] == "0"
        assert environment["GIT_ATTR_NOSYSTEM"] == "1"
        assert environment["GIT_NO_LAZY_FETCH"] == "1"
        assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert environment["GIT_COMMON_DIR"] == (
            "/home/ncyu/BybitOpenClaw/srv/.git"
        )
    assert "remote.origin.url" not in json.dumps(result)


def test_positive_startup_catchup_without_notification_is_not_a_failed_cycle() -> None:
    module = _load_module()
    connection = _Connection(module)
    startup = _cycle(0)
    startup["notification_event_id"] = None
    startup["notification_recorded_at"] = None
    startup["notification_ts_ms"] = None
    connection.cycles.insert(0, startup)

    result = _run(module, connection)

    assert result["status"] == "PASS", result
    assert result["cycle_count"] == 2
    assert [cycle["notification"]["event_id"] for cycle in result["cycles"]] == [
        connection.cycles[1]["notification_event_id"],
        connection.cycles[2]["notification_event_id"],
    ]
    assert "JOIN LATERAL" in module.CYCLES_SQL
    assert "LEFT JOIN LATERAL" not in module.CYCLES_SQL
    assert "consumed.recorded_at <= lane.recorded_at" in module.CYCLES_SQL


@pytest.mark.parametrize("tamper", ["environment", "runtime_override"])
def test_recovery_git_hardening_seam_anomalies_fail_closed(tamper: str) -> None:
    module = _load_module()
    recovery = _recovery_module()
    if tamper == "environment":
        recovery.base.SYSTEM_ENV["GIT_CONFIG_COUNT"] = "1"
    else:
        recovery.Runtime.git = lambda self, *_args: "unsafe"

    result = _run(module, _Connection(module), recovery_loader=lambda: recovery)

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["recovery_git_hardening_seam_invalid"]


def test_millisecond_typed_cursor_uses_second_precision_only_for_decision_json() -> None:
    module = _load_module()
    connection = _Connection(module, source_microsecond=123000)

    result = _run(module, connection)

    assert result["status"] == "PASS", result
    assert result["cycles"][0]["cursor"]["source_ts"].endswith("00.123000Z")
    decision_params = [
        params for sql, params in connection.executed if sql == module.DECISION_SQL
    ]
    assert [params[2] for params in decision_params] == [
        "2026-07-17T13:42:00Z",
        "2026-07-17T13:43:00Z",
    ]


def test_latest_bounded_window_deduplicates_same_cursor_retries_and_still_passes() -> None:
    module = _load_module()
    connection = _Connection(module)
    first = connection.cycles[0]
    second = connection.cycles[1]
    retries = []
    for index in range(257):
        retry = copy.deepcopy(first)
        retry["lane_success_event_id"] = (
            f"30000000-0000-4000-8000-{index:012d}"
        )
        retry["notification_event_id"] = (
            f"40000000-0000-4000-8000-{index:012d}"
        )
        retries.append(retry)
    connection.cycles = retries + [second]

    result = _run(module, connection)

    assert result["status"] == "PASS", result
    assert result["cycle_count"] == 2
    assert result["cycle_window"] == {
        "scope": "latest_notification_backed_lane_success_rows_in_current_post_pin_session",
        "query_order": "source_ts_desc_scan_id_desc_event_id_desc",
        "probe_limit": 257,
        "evaluated_limit": 256,
        "observed_rows": 257,
        "evaluated_rows": 256,
        "truncated": True,
        "full_history_scan_claimed": False,
    }
    assert result["cycles"][0]["cursor"] != result["cycles"][1]["cursor"]
    assert "ORDER BY lane.source_ts DESC,lane.source_scan_id DESC," in module.CYCLES_SQL


def test_same_cursor_with_conflicting_source_hash_fails_closed() -> None:
    module = _load_module()
    connection = _Connection(module)
    conflict = copy.deepcopy(connection.cycles[0])
    conflict["lane_success_event_id"] = "50000000-0000-4000-8000-000000000001"
    conflict["notification_event_id"] = "60000000-0000-4000-8000-000000000001"
    conflict["source_canonical_payload"]["config"] = {"conflict": True}
    conflict_hash = _sha(conflict["source_canonical_payload"])
    conflict["source_hash"] = conflict_hash
    conflict["typed_source_hash"] = conflict_hash
    connection.cycles.insert(1, conflict)

    result = _run(module, connection)

    assert result["status"] == "FAIL"
    assert result["reason_codes"] == ["natural_cycle_cursor_identity_conflict"]


def test_window_reports_the_latest_two_complete_distinct_cycles() -> None:
    module = _load_module()
    connection = _Connection(module)
    third = _cycle(3)
    decision, edges = _decision(module, third)
    connection.cycles.append(third)
    connection.decisions[str(third["source_hash"])] = [decision]
    connection.edges[str(decision["artifact_hash"])] = edges
    connection.health[str(third["source_hash"])] = _health(third, decision, 3)

    result = _run(module, connection)

    assert result["status"] == "PASS", result
    assert [cycle["cursor"]["source_hash"] for cycle in result["cycles"]] == [
        connection.cycles[1]["source_hash"],
        connection.cycles[2]["source_hash"],
    ]


def test_health_accepts_producer_datetime_text_with_space_and_utc_offset() -> None:
    module = _load_module()
    connection = _Connection(module, source_microsecond=123000)
    for cycle in connection.cycles:
        health = connection.health[str(cycle["source_hash"])]
        producer_text = str(cycle["source_ts"])
        health["canonical_payload"]["watermark"]["source_ts"] = producer_text
        health["canonical_payload"]["ingestion"]["fresh_cursor_ts"] = producer_text
        _reseal_health(health)

    result = _run(module, connection)

    assert result["status"] == "PASS", result
    assert result["cycles"][0]["cursor"]["source_ts"].endswith("00.123000Z")


@pytest.mark.parametrize(
    "dangerous_key",
    [
        "filter.evil.process",
        "filter.evil.clean",
        "include.path",
        "includeif.gitdir:/tmp/.path",
        "core.attributesfile",
        "core.excludesfile",
        "core.sparsecheckout",
        "core.worktree",
        "extensions.worktreeconfig",
        "trace2.eventtarget",
    ],
)
def test_effectful_local_or_included_git_config_is_rejected_before_status(
    dangerous_key: str,
) -> None:
    module = _load_module()
    recovery = _recovery_module()
    calls = []

    def capture_inventory(argv, *, cwd=None, env=None, timeout=60):
        calls.append((list(argv), dict(env or {})))
        return types.SimpleNamespace(stdout=dangerous_key + "\0")

    recovery.base.RecoveryRuntime.run = staticmethod(capture_inventory)
    result = _run(module, _Connection(module), recovery_loader=lambda: recovery)

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["recovery_git_effectful_config_present"]
    assert len(calls) == 1
    assert calls[0][0][-6:] == [
        "config",
        "--local",
        "--includes",
        "--null",
        "--name-only",
        "--list",
    ]
    assert "status" not in calls[0][0]
    assert dangerous_key not in json.dumps(result)


@pytest.mark.parametrize("drift_label", ["info_exclude", "index"])
def test_git_metadata_drift_is_rejected_before_any_status(drift_label: str) -> None:
    module = _load_module()
    git_calls = []
    files = _RuntimeFiles(module, git_metadata_drift=drift_label)
    result = _run(
        module,
        _Connection(module),
        files=files,
        recovery_loader=lambda: _recovery_module(git_calls=git_calls),
    )

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["recovery_git_metadata_changed"]
    assert not any("status" in argv for argv, _environment in git_calls)


@pytest.mark.parametrize("drift_label", ["repo", "git"])
def test_repo_or_git_directory_drift_is_rejected_before_status(
    drift_label: str,
) -> None:
    module = _load_module()
    git_calls = []
    files = _RuntimeFiles(module, git_path_drift=drift_label)
    result = _run(
        module,
        _Connection(module),
        files=files,
        recovery_loader=lambda: _recovery_module(git_calls=git_calls),
    )

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["recovery_git_metadata_changed"]
    assert not any("status" in argv for argv, _environment in git_calls)


def test_git_info_attributes_presence_is_rejected_before_any_git_call() -> None:
    module = _load_module()
    git_calls = []
    files = _RuntimeFiles(module, git_attributes_present=True)
    result = _run(
        module,
        _Connection(module),
        files=files,
        recovery_loader=lambda: _recovery_module(git_calls=git_calls),
    )

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["recovery_git_info_attributes_present"]
    assert git_calls == []


def test_shared_index_path_is_rejected_before_any_clean_snapshot() -> None:
    module = _load_module()
    git_calls = []
    result = _run(
        module,
        _Connection(module),
        recovery_loader=lambda: _recovery_module(
            git_calls=git_calls,
            shared_index_stdout="/tmp/sharedindex.unsafe\n",
        ),
    )

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["recovery_git_shared_index_present"]
    assert len(git_calls) == 2
    assert not any("status" in argv for argv, _environment in git_calls)
    assert "sharedindex.unsafe" not in json.dumps(result)


@pytest.mark.parametrize(
    "stage_inventory",
    [
        _clean_stage_inventory(first_stage="1"),
        _clean_stage_inventory(first_mode="160000"),
        _clean_stage_inventory(tracked_gitmodules=True),
    ],
)
def test_non_stage0_gitlink_or_tracked_gitmodules_is_rejected_without_paths(
    stage_inventory: str,
) -> None:
    module = _load_module()
    git_calls = []
    result = _run(
        module,
        _Connection(module),
        recovery_loader=lambda: _recovery_module(
            git_calls=git_calls,
            stage_inventory=stage_inventory,
        ),
    )

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == [
        "recovery_git_stage_or_submodule_invalid"
    ]
    assert len(git_calls) == 4
    assert not any("status" in argv for argv, _environment in git_calls)
    assert "tracked/stage-file" not in json.dumps(result)
    assert ".gitmodules" not in json.dumps(result)


@pytest.mark.parametrize("unsafe_tag", ["S", "h"])
def test_skip_worktree_or_assume_unchanged_index_flag_is_rejected(
    unsafe_tag: str,
) -> None:
    module = _load_module()
    git_calls = []
    clean_inventory = _clean_index_inventory()
    unsafe_inventory = unsafe_tag + clean_inventory[1:]
    result = _run(
        module,
        _Connection(module),
        recovery_loader=lambda: _recovery_module(
            git_calls=git_calls,
            index_inventory=unsafe_inventory,
        ),
    )

    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == [
        "recovery_git_index_flag_or_path_invalid"
    ]
    assert len(git_calls) == 3
    assert not any("status" in argv for argv, _environment in git_calls)
    assert "tracked/file-00000" not in json.dumps(result)
