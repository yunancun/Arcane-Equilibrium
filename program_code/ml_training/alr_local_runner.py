"""Source-only ALR local runner with explicit one-run-directory JSON outputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .alr_controller_contracts import (
    ALR_LOOP_STATE_PACKET_SCHEMA_VERSION,
    ALR_WORK_ITEM_SCHEMA_VERSION,
    BOUNDARY_LABEL,
    compute_alr_loop_state_packet_hash,
    compute_alr_work_item_hash,
    select_first_unblocked_alr_row,
    validate_alr_loop_state_packet,
    validate_alr_work_item,
)
from .alr_outcome_bridge import (
    ALR_OUTCOME_BRIDGE_SCHEMA_VERSION,
    build_alr_outcome_bridge_packet,
    load_proof_packet,
    load_reward_records,
    validate_alr_outcome_bridge_packet,
)
from .alr_retention_guardian_dry_run import (
    OUTPUT_SCHEMA_VERSION as RETENTION_OUTPUT_SCHEMA_VERSION,
    STOP_RETENTION_RISK as RETENTION_STOP_RISK,
    build_retention_guardian_dry_run,
    validate_retention_guardian_dry_run,
)
from .learning_effect_review import (
    LEARNING_EFFECT_REVIEW_SCHEMA_VERSION,
    LearningEffectReviewError,
    build_learning_effect_review_packet,
    validate_learning_effect_review,
)
from .learning_target_arbiter import (
    OUTPUT_SCHEMA_VERSION as LEARNING_TARGET_OUTPUT_SCHEMA_VERSION,
    build_learning_target_runtime,
    load_snapshot,
)


INPUT_SCHEMA_VERSION = "alr_local_runner_manifest_v1"
OUTPUT_SCHEMA_VERSION = "alr_local_runner_report_v1"

REPORT_FILENAME = "alr_local_runner_report_v1.json"
LEARNING_TARGET_FILENAME = "learning_target_runtime_v1.json"
OUTCOME_BRIDGE_FILENAME = "alr_outcome_bridge_v1.json"
RETENTION_DRY_RUN_FILENAME = "retention_guardian_dry_run_v1.json"
STATE_PACKET_FILENAME = "alr_loop_state_packet_v1.json"
EFFECT_REVIEW_FILENAME = "learning_effect_review_v1.json"

STOP_ADVANCED = "ADVANCED"
STOP_DONE = "DONE"
STOP_DEFER_EVIDENCE = "DEFER_EVIDENCE"
STOP_ROTATED = "ROTATED"
STOP_NO_EDGE = "STOP_NO_EDGE"
STOP_RETENTION_RISK = "STOP_RETENTION_RISK"
STOP_BLOCKED_BOUNDARY = "BLOCKED_BOUNDARY"

_REQUESTED_STEPS = {"auto", "learning_target", "outcome_bridge", "retention_dry_run", "effect_review", "state_only"}
_RUN_SEQUENCE = ("learning_target", "outcome_bridge", "retention_dry_run", "effect_review")
_MANIFEST_REQUIRED_FIELDS = set(
    "schema_version boundary_label created_at run_id source_head latest_alias_used "
    "requested_step work_items inputs no_authority manifest_hash".split()
)
_AUTHORITY_COUNTER_KEYS = tuple(
    "runtime_ssh_count service_change_count pg_contact_count ipc_contact_count "
    "decision_lease_count adapter_writer_count exchange_contact_count order_action_count "
    "cost_gate_change_count serving_or_promotion_count scheduler_change_count".split()
)
_NO_AUTHORITY_KEYS = tuple(
    "runtime db pg ipc bybit mcp scheduler service env latest proof promotion delete "
    "apply cost_gate order probe live mainnet exchange_contact private_read "
    "runtime_mutation db_read db_write db_migration env_mutation service_restart "
    "order_or_probe live_or_mainnet".split()
)
_OWNED_FILES = (
    "program_code/ml_training/alr_local_runner.py",
    "program_code/ml_training/tests/test_alr_local_runner.py",
)
_VERIFICATION_COMMANDS = (
    "PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile "
    "program_code/ml_training/alr_local_runner.py "
    "program_code/ml_training/tests/test_alr_local_runner.py",
    "PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q "
    "program_code/ml_training/tests/test_alr_local_runner.py -p no:cacheprovider",
    "git diff --check -- program_code/ml_training/alr_local_runner.py "
    "program_code/ml_training/tests/test_alr_local_runner.py",
)


class AlrLocalRunnerError(ValueError):
    """Raised before artifacts can be safely emitted."""


@dataclass(frozen=True)
class _StepResult:
    name: str
    status: str
    stop_state: str
    stop_reason: str
    artifact: dict[str, Any] | None = None


def compute_runner_manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(manifest))
    payload.pop("manifest_hash", None)
    return _stable_sha256_json(payload)


def compute_runner_report_hash(report: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(report))
    payload.pop("report_hash", None)
    return _stable_sha256_json(payload)


def load_runner_manifest(path: Path | str) -> dict[str, Any]:
    manifest_path = Path(path)
    _reject_latest_path(manifest_path, "manifest")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AlrLocalRunnerError(f"manifest_read_failed:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise AlrLocalRunnerError(f"manifest_json_invalid:{exc.msg}") from exc
    if not isinstance(raw, dict):
        raise AlrLocalRunnerError("manifest_not_mapping")
    _validate_manifest(raw)
    return raw


def run_local_runner(manifest: Mapping[str, Any], out_dir: Path | str) -> dict[str, Any]:
    manifest_copy = copy.deepcopy(dict(manifest))
    _validate_manifest(manifest_copy)
    run_dir = Path(out_dir)
    _validate_output_dir(run_dir)

    rotated_reason = _previous_hash_rotation_reason(
        manifest_copy.get("expected_previous_artifact_hashes")
    )
    selected_work_item = _select_work_item(manifest_copy)
    requested_step = _select_step(manifest_copy)
    if rotated_reason:
        requested_step = "state_only"

    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AlrLocalRunnerError(f"out_dir_create_failed:{exc}") from exc
    _validate_output_dir(run_dir)
    emitted_refs: list[dict[str, Any]] = []
    if rotated_reason:
        step_result = _StepResult(
            name="state_only",
            status=STOP_ROTATED,
            stop_state=STOP_ROTATED,
            stop_reason=rotated_reason,
        )
    else:
        step_result = _run_step(requested_step, manifest_copy)
        if step_result.artifact is not None:
            artifact_path = run_dir / _component_filename(requested_step)
            _write_json_exclusive(artifact_path, step_result.artifact)
            emitted_refs.append(_artifact_ref(artifact_path, step_result.artifact))

    state_packet = _build_state_packet(
        manifest_copy,
        selected_work_item=selected_work_item,
        step_result=step_result,
    )
    state_path = run_dir / STATE_PACKET_FILENAME
    _write_json_exclusive(state_path, state_packet)
    emitted_refs.append(_artifact_ref(state_path, state_packet))

    report = _build_report(
        manifest_copy,
        selected_work_item=selected_work_item,
        requested_step=requested_step,
        step_result=step_result,
        emitted_refs=emitted_refs,
        state_packet=state_packet,
    )
    report_path = run_dir / REPORT_FILENAME
    _write_json_exclusive(report_path, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-only ALR local runner")
    parser.add_argument("--manifest", required=True, help="Runner manifest JSON path")
    parser.add_argument("--out-dir", required=True, help="Explicit new run directory")
    args = parser.parse_args(argv)

    try:
        manifest = load_runner_manifest(args.manifest)
        run_local_runner(manifest, args.out_dir)
    except AlrLocalRunnerError as exc:
        print(f"alr_local_runner_error:{exc}", file=sys.stderr)
        return 2
    return 0


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    missing = sorted(_MANIFEST_REQUIRED_FIELDS - set(manifest))
    if missing:
        raise AlrLocalRunnerError(f"manifest_missing_fields:{','.join(missing)}")
    if manifest.get("schema_version") != INPUT_SCHEMA_VERSION:
        raise AlrLocalRunnerError("schema_version_invalid")
    if manifest.get("boundary_label") != BOUNDARY_LABEL:
        raise AlrLocalRunnerError("boundary_label_invalid")
    if manifest.get("latest_alias_used") is not False:
        raise AlrLocalRunnerError("latest_alias_used_rejected")
    requested_step = _text(manifest.get("requested_step"))
    if requested_step not in _REQUESTED_STEPS:
        raise AlrLocalRunnerError("requested_step_invalid")
    max_steps = manifest.get("max_steps", 1)
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or not 1 <= max_steps <= 1:
        raise AlrLocalRunnerError("max_steps_invalid")
    if not isinstance(manifest.get("inputs"), Mapping):
        raise AlrLocalRunnerError("inputs_not_mapping")
    _validate_no_authority(manifest.get("no_authority"))
    _reject_latest_refs(manifest)
    _validate_work_items(manifest.get("work_items"))
    manifest_hash = _text(manifest.get("manifest_hash"))
    if not _is_hex64(manifest_hash):
        raise AlrLocalRunnerError("manifest_hash_malformed")
    if manifest_hash != compute_runner_manifest_hash(manifest):
        raise AlrLocalRunnerError("manifest_hash_mismatch")


def _validate_work_items(value: Any) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AlrLocalRunnerError("work_items_not_sequence")
    if not value:
        raise AlrLocalRunnerError("work_items_empty")
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise AlrLocalRunnerError(f"work_items_not_mapping:{index}")
        if item.get("schema_version") != ALR_WORK_ITEM_SCHEMA_VERSION:
            raise AlrLocalRunnerError(f"work_item_schema_invalid:{index}")
        validation = validate_alr_work_item(item)
        if not validation.valid:
            raise AlrLocalRunnerError(f"work_item_invalid:{index}:{validation.reason}")


def _validate_output_dir(out_dir: Path) -> None:
    _reject_latest_path(out_dir, "out_dir")
    _reject_symlinked_existing_path(out_dir, "out_dir")
    if out_dir.exists():
        if out_dir.is_symlink():
            raise AlrLocalRunnerError("out_dir_symlink_rejected")
        if not out_dir.is_dir():
            raise AlrLocalRunnerError("out_dir_not_directory")
        if any(out_dir.iterdir()):
            raise AlrLocalRunnerError("out_dir_not_empty")


def _run_step(step: str, manifest: Mapping[str, Any]) -> _StepResult:
    if step == "learning_target":
        return _run_learning_target(manifest)
    if step == "outcome_bridge":
        return _run_outcome_bridge(manifest)
    if step == "retention_dry_run":
        return _run_retention_dry_run(manifest)
    if step == "effect_review":
        return _run_effect_review(manifest)
    if step == "state_only":
        return _StepResult(
            name="state_only",
            status=STOP_DONE,
            stop_state=STOP_DONE,
            stop_reason="state_only_requested",
        )
    raise AlrLocalRunnerError(f"step_unknown:{step}")


def _run_learning_target(manifest: Mapping[str, Any]) -> _StepResult:
    path = _optional_path(manifest, "learning_target_snapshot_path")
    if path is None:
        return _defer("learning_target", "learning_target_snapshot_path_missing")
    try:
        runtime = build_learning_target_runtime(load_snapshot(path))
    except Exception as exc:
        return _defer("learning_target", f"learning_target_deferred:{exc}")
    if runtime.get("decision") == "DEFER_EVIDENCE":
        return _StepResult(
            "learning_target",
            "DEFER_EVIDENCE",
            STOP_DEFER_EVIDENCE,
            "learning_target_deferred",
            runtime,
        )
    return _StepResult("learning_target", "ADVANCED", STOP_ADVANCED, "ok", runtime)


def _run_outcome_bridge(manifest: Mapping[str, Any]) -> _StepResult:
    inputs = _mapping(manifest.get("inputs"))
    proof_path = _path_from_inputs(inputs, "proof_packet_path")
    reward_paths = _path_list_from_inputs(inputs, "reward_ledger_paths")
    try:
        proof_packet = load_proof_packet(proof_path) if proof_path is not None else {}
        reward_records: list[Mapping[str, Any]] = []
        for reward_path in reward_paths:
            reward_records.extend(load_reward_records(reward_path))
        packet = build_alr_outcome_bridge_packet(
            proof_packet=proof_packet,
            reward_records=reward_records,
        )
        validation = validate_alr_outcome_bridge_packet(packet)
    except Exception as exc:
        return _defer("outcome_bridge", f"outcome_bridge_deferred:{exc}")
    if validation.authority_boundary_violation:
        return _StepResult(
            "outcome_bridge",
            "BLOCKED_BOUNDARY",
            STOP_BLOCKED_BOUNDARY,
            validation.reason,
            packet,
        )
    if packet.get("schema_version") != ALR_OUTCOME_BRIDGE_SCHEMA_VERSION:
        return _defer("outcome_bridge", "outcome_bridge_schema_invalid")
    if packet.get("bridge_status") == "DEFER_EVIDENCE":
        return _StepResult(
            "outcome_bridge",
            "DEFER_EVIDENCE",
            STOP_DEFER_EVIDENCE,
            validation.reason,
            packet,
        )
    return _StepResult("outcome_bridge", "ADVANCED", STOP_ADVANCED, validation.reason, packet)


def _run_retention_dry_run(manifest: Mapping[str, Any]) -> _StepResult:
    path = _optional_path(manifest, "retention_artifact_manifest_path")
    if path is None:
        return _defer("retention_dry_run", "retention_artifact_manifest_path_missing")
    try:
        raw = _read_json_mapping(path, "retention_artifact_manifest")
        packet = build_retention_guardian_dry_run(raw)
        validation = validate_retention_guardian_dry_run(packet)
    except Exception as exc:
        return _defer("retention_dry_run", f"retention_dry_run_deferred:{exc}")
    if packet.get("schema_version") != RETENTION_OUTPUT_SCHEMA_VERSION:
        return _defer("retention_dry_run", "retention_schema_invalid")
    if not validation.valid:
        return _StepResult(
            "retention_dry_run",
            "STOP_RETENTION_RISK",
            STOP_RETENTION_RISK,
            validation.reason,
            packet,
        )
    if validation.stop_retention_risk_count:
        return _StepResult(
            "retention_dry_run",
            RETENTION_STOP_RISK,
            STOP_RETENTION_RISK,
            "retention_guardian_protected_refs",
            packet,
        )
    return _StepResult("retention_dry_run", "ADVANCED", STOP_ADVANCED, "ok", packet)


def _run_effect_review(manifest: Mapping[str, Any]) -> _StepResult:
    inputs = _mapping(manifest.get("inputs"))
    reward_paths = _path_list_from_inputs(inputs, "reward_ledger_paths")
    try:
        reward_records: list[Mapping[str, Any]] = []
        for reward_path in reward_paths:
            reward_records.extend(load_reward_records(reward_path))
        packet = build_learning_effect_review_packet(
            reward_records=reward_records,
            loss_limits=_mapping(inputs.get("loss_limits")),
            controls=_mapping(inputs.get("controls")),
            oos_repeat_tags=_mapping(inputs.get("oos_repeat_tags")),
            acceptance_report_refs=_sequence_of_mappings(inputs.get("acceptance_report_refs")),
            review_policy=_mapping(inputs.get("review_policy")),
        )
        validation = validate_learning_effect_review(packet)
    except (LearningEffectReviewError, AlrLocalRunnerError) as exc:
        return _defer("effect_review", f"effect_review_deferred:{exc}")
    if validation.authority_boundary_violation:
        return _StepResult(
            "effect_review",
            "BLOCKED_BOUNDARY",
            STOP_BLOCKED_BOUNDARY,
            validation.reason,
            packet,
        )
    if packet.get("schema_version") != LEARNING_EFFECT_REVIEW_SCHEMA_VERSION:
        return _defer("effect_review", "effect_review_schema_invalid")
    if validation.decision == "stop_loss_control":
        stop_state = STOP_RETENTION_RISK
    elif validation.decision == "stop_no_edge":
        stop_state = STOP_NO_EDGE
    elif validation.decision == "stop_evidence":
        stop_state = STOP_DEFER_EVIDENCE
    elif validation.decision == "rotate_candidate":
        stop_state = STOP_ROTATED
    else:
        stop_state = STOP_ADVANCED
    return _StepResult("effect_review", validation.decision, stop_state, validation.reason, packet)


def _build_state_packet(
    manifest: Mapping[str, Any],
    *,
    selected_work_item: Mapping[str, Any] | None,
    step_result: _StepResult,
) -> dict[str, Any]:
    stop_reason = "" if step_result.stop_state in {STOP_ADVANCED, STOP_DONE} else step_result.stop_reason
    artifact = _mapping(step_result.artifact)
    work_items = _state_work_items(manifest, selected_work_item, step_result)
    state_selected, outcome, decision_reasons = select_first_unblocked_alr_row(work_items)
    packet: dict[str, Any] = {
        "schema": ALR_LOOP_STATE_PACKET_SCHEMA_VERSION,
        "schema_version": ALR_LOOP_STATE_PACKET_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "loop_id": _text(manifest.get("run_id")),
        "selector": "first_ready_without_blockers",
        "created_at": _text(manifest.get("created_at")),
        "source_head": _text(manifest.get("source_head")),
        "repo_head_before": _text(manifest.get("source_head")),
        "repo_head_after": _text(manifest.get("source_head")),
        "work_items": work_items,
        "selected_work_item": _selected_work_item_ref(state_selected),
        "selection_reason": decision_reasons[0] if decision_reasons else "",
        "component": {"name": step_result.name, "status": step_result.status, "stop_state": step_result.stop_state},
        "state": _queue_state_for_stop(step_result.stop_state),
        "next_state": _queue_next_state_for_stop(step_result.stop_state),
        "next_action": f"source-only local runner completed {step_result.name} with {step_result.stop_state}",
        "stop_reason": stop_reason,
        "outcome": outcome,
        "decision_reasons": list(decision_reasons),
        "owned_files": list(_OWNED_FILES),
        "verification_commands": list(_VERIFICATION_COMMANDS),
        "candidate_matched_fills_count": int(artifact.get("candidate_matched_fills_count") or 0),
        "proof_packet_ready_count": int(artifact.get("proof_packet_ready_count") or 0),
        "reward_ledger_ready_count": int(artifact.get("reward_ledger_ready_count") or 0),
        "effect_review_ready": step_result.name == "effect_review" and step_result.stop_state == STOP_ADVANCED,
        "model_training_performed": False,
        "serving_authority_granted": False,
        "llm_authority": False,
        "runtime_authority": False,
        "exchange_authority": False,
        "trading_authority": False,
        "boundary_escalation_required": step_result.stop_state == STOP_BLOCKED_BOUNDARY,
        "dispatch_tooling_available": True,
        "dispatch_blocker": "",
        "authority_counters": _zero_authority_counters(),
        "no_authority": _false_no_authority(),
    }
    packet["packet_hash"] = compute_alr_loop_state_packet_hash(packet)
    validation = validate_alr_loop_state_packet(packet)
    if not validation.valid:
        raise AlrLocalRunnerError(f"state_packet_invalid:{validation.reason}")
    return packet


def _build_report(
    manifest: Mapping[str, Any],
    *,
    selected_work_item: Mapping[str, Any] | None,
    requested_step: str,
    step_result: _StepResult,
    emitted_refs: Sequence[Mapping[str, Any]],
    state_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    selected_ref = _mapping(_mapping(state_packet).get("selected_work_item"))
    if not selected_ref:
        selected_ref = _selected_work_item_ref(selected_work_item)
    report: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "state_machine": [
            "LOAD_MANIFEST", "VALIDATE_BOUNDARY", "RECOVER_PREVIOUS_STATE",
            "SELECT_WORK_ITEM", "PLAN_STEP", "RUN_ONE_BOUNDED_STEP",
            "EMIT_REPORT_AND_STATE", "EXIT",
        ],
        "run_id": _text(manifest.get("run_id")),
        "source_head": _text(manifest.get("source_head")),
        "requested_step": _text(manifest.get("requested_step")),
        "planned_step": requested_step,
        "selected_work_item": selected_ref,
        "emitted_artifact_refs": [dict(ref) for ref in emitted_refs],
        "component_status": {
            "component": step_result.name,
            "status": step_result.status,
            "stop_reason": step_result.stop_reason,
        },
        "stop_state": step_result.stop_state,
        "stop_reason": step_result.stop_reason,
        "authority_counters": _zero_authority_counters(),
        "no_authority": _false_no_authority(),
    }
    report["report_hash"] = compute_runner_report_hash(report)
    return report


def _select_work_item(manifest: Mapping[str, Any]) -> Mapping[str, Any] | None:
    work_items = [dict(item) for item in manifest.get("work_items", ()) if isinstance(item, Mapping)]
    selected, _, _ = select_first_unblocked_alr_row(work_items)
    return selected


def _select_step(manifest: Mapping[str, Any]) -> str:
    requested = _text(manifest.get("requested_step"))
    if requested != "auto":
        return requested
    completed = _completed_schemas(manifest)
    for step in _RUN_SEQUENCE:
        if _step_schema(step) not in completed:
            return step
    return "state_only"


def _state_work_items(
    manifest: Mapping[str, Any],
    selected_work_item: Mapping[str, Any] | None,
    step_result: _StepResult,
) -> list[Mapping[str, Any]]:
    items = [copy.deepcopy(dict(item)) for item in manifest.get("work_items", ())]
    selected_id = _text(_mapping(selected_work_item).get("work_item_id"))
    if not selected_id:
        return items
    for index, item in enumerate(items):
        if _text(item.get("work_item_id")) == selected_id:
            item.update(_work_item_queue_fields_for_stop(step_result.stop_state))
            item["work_item_hash"] = compute_alr_work_item_hash(item)
            break
    return items


def _work_item_queue_fields_for_stop(stop_state: str) -> dict[str, Any]:
    if stop_state in {STOP_ADVANCED, STOP_DONE}:
        return {"state": "ACTIVE", "status": "READY", "blockers": []}
    if stop_state == STOP_ROTATED:
        return {"state": "ROTATED", "status": "ROTATED", "blockers": ["rotated"]}
    if stop_state == STOP_NO_EDGE:
        return {"state": "BLOCKED", "status": "NO_EDGE", "blockers": ["no_edge"]}
    if stop_state == STOP_RETENTION_RISK:
        return {"state": "BLOCKED", "status": "RETENTION_RISK", "blockers": ["stop_retention_risk"]}
    return {"state": "DEFERRED", "status": "DEFER_EVIDENCE", "blockers": ["defer_evidence"]}


def _queue_state_for_stop(stop_state: str) -> str:
    return {
        STOP_ADVANCED: "ACTIVE",
        STOP_DONE: "DONE",
        STOP_DEFER_EVIDENCE: "DEFERRED",
        STOP_ROTATED: "ROTATED",
        STOP_NO_EDGE: "BLOCKED",
        STOP_RETENTION_RISK: "BLOCKED",
        STOP_BLOCKED_BOUNDARY: "BLOCKED",
    }.get(stop_state, "DEFERRED")


def _queue_next_state_for_stop(stop_state: str) -> str:
    if stop_state in {STOP_ADVANCED, STOP_DONE}:
        return "READY_FOR_NEXT_SOURCE_ONLY_ROW"
    if stop_state == STOP_ROTATED:
        return "ROTATED"
    if stop_state == STOP_BLOCKED_BOUNDARY:
        return "BLOCKED_BOUNDARY"
    if stop_state in {STOP_NO_EDGE, STOP_RETENTION_RISK}:
        return "STOPPED"
    return "DEFERRED_EVIDENCE"


def _completed_schemas(manifest: Mapping[str, Any]) -> set[str]:
    schemas: set[str] = set()
    previous_path = _previous_state_packet_path(manifest)
    previous_packet = None
    if previous_path is not None:
        try:
            previous_packet = _read_json_mapping(previous_path, "previous_state_packet")
        except AlrLocalRunnerError:
            previous_packet = None
    for source in (previous_packet, _mapping(manifest.get("inputs"))):
        if not isinstance(source, Mapping):
            continue
        for ref in _artifact_refs_from(source):
            schema = _text(ref.get("schema_version"))
            if schema:
                schemas.add(schema)
    return schemas


def _previous_state_packet_path(manifest: Mapping[str, Any]) -> Path | None:
    value = manifest.get("previous_state_packet_path")
    if value not in (None, ""):
        if not isinstance(value, str):
            raise AlrLocalRunnerError("previous_state_packet_path_not_string")
        path = Path(value)
        _reject_latest_path(path, "previous_state_packet_path")
        return path
    return _optional_path(manifest, "previous_state_packet_path")


def _artifact_refs_from(value: Any) -> list[Mapping[str, Any]]:
    refs: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"emitted_artifact_refs", "artifact_refs", "completed_artifact_refs"}:
                if isinstance(child, Sequence) and not isinstance(child, (str, bytes, bytearray)):
                    refs.extend(item for item in child if isinstance(item, Mapping))
            refs.extend(_artifact_refs_from(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_artifact_refs_from(child))
    return refs


def _previous_hash_rotation_reason(value: Any) -> str:
    refs = _expected_hash_refs(value)
    for index, ref in enumerate(refs):
        path_text = _text(ref.get("path") or ref.get("artifact_path") or ref.get("ref"))
        expected_hash = _strip_sha(_text(ref.get("sha256") or ref.get("hash")))
        if not path_text or not _is_hex64(expected_hash):
            return f"expected_previous_artifact_hash_ref_invalid:{index}"
        path = Path(path_text)
        _reject_latest_path(path, "expected_previous_artifact")
        try:
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return f"expected_previous_artifact_unreadable:{index}"
        if actual_hash != expected_hash:
            return f"expected_previous_artifact_hash_mismatch:{index}"
    return ""


def _expected_hash_refs(value: Any) -> list[Mapping[str, Any]]:
    if value in (None, {}, []):
        return []
    if isinstance(value, Mapping):
        if any(key in value for key in ("path", "artifact_path", "ref")):
            return [value]
        refs: list[Mapping[str, Any]] = []
        for path_text, digest in value.items():
            refs.append({"path": str(path_text), "sha256": str(digest)})
        return refs
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return [{"path": "", "sha256": ""}]


def _component_filename(step: str) -> str:
    return {
        "learning_target": LEARNING_TARGET_FILENAME,
        "outcome_bridge": OUTCOME_BRIDGE_FILENAME,
        "retention_dry_run": RETENTION_DRY_RUN_FILENAME,
        "effect_review": EFFECT_REVIEW_FILENAME,
    }[step]


def _step_schema(step: str) -> str:
    return {
        "learning_target": LEARNING_TARGET_OUTPUT_SCHEMA_VERSION,
        "outcome_bridge": ALR_OUTCOME_BRIDGE_SCHEMA_VERSION,
        "retention_dry_run": RETENTION_OUTPUT_SCHEMA_VERSION,
        "effect_review": LEARNING_EFFECT_REVIEW_SCHEMA_VERSION,
    }[step]


def _defer(name: str, reason: str) -> _StepResult:
    return _StepResult(name, "DEFER_EVIDENCE", STOP_DEFER_EVIDENCE, reason)


def _artifact_ref(path: Path, artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "filename": path.name,
        "path": str(path),
        "schema_version": _text(artifact.get("schema_version")),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise AlrLocalRunnerError(f"output_exists:{path.name}")
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    except FileExistsError as exc:
        raise AlrLocalRunnerError(f"output_exists:{path.name}") from exc
    except OSError as exc:
        raise AlrLocalRunnerError(f"output_write_failed:{path.name}:{exc}") from exc


def _read_json_mapping(path: Path, label: str) -> dict[str, Any]:
    _reject_latest_path(path, label)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AlrLocalRunnerError(f"{label}_read_failed:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise AlrLocalRunnerError(f"{label}_json_invalid:{exc.msg}") from exc
    if not isinstance(raw, dict):
        raise AlrLocalRunnerError(f"{label}_not_mapping")
    return raw


def _optional_path(manifest: Mapping[str, Any], key: str) -> Path | None:
    return _path_from_inputs(_mapping(manifest.get("inputs")), key)


def _path_from_inputs(inputs: Mapping[str, Any], key: str) -> Path | None:
    value = inputs.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise AlrLocalRunnerError(f"{key}_not_string")
    path = Path(value)
    _reject_latest_path(path, key)
    return path


def _path_list_from_inputs(inputs: Mapping[str, Any], key: str) -> list[Path]:
    value = inputs.get(key)
    if value in (None, ""):
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AlrLocalRunnerError(f"{key}_not_sequence")
    paths = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise AlrLocalRunnerError(f"{key}_item_not_string:{index}")
        path = Path(item)
        _reject_latest_path(path, key)
        paths.append(path)
    return paths


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AlrLocalRunnerError("acceptance_report_refs_not_sequence")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise AlrLocalRunnerError(f"acceptance_report_ref_not_mapping:{index}")
        result.append(dict(item))
    return result


def _reject_latest_refs(value: Any) -> None:
    latest_path = _find_latest_ref(value)
    if latest_path:
        raise AlrLocalRunnerError(f"latest_ref_rejected:{latest_path}")
    for ref in _expected_hash_refs(
        value.get("expected_previous_artifact_hashes") if isinstance(value, Mapping) else None
    ):
        path_text = _text(ref.get("path") or ref.get("artifact_path") or ref.get("ref"))
        if path_text:
            _reject_latest_path(Path(path_text), "expected_previous_artifact")


def _find_latest_ref(value: Any, path: str = "$") -> str:
    if isinstance(value, Mapping):
        for key, child in value.items():
            found = _find_latest_ref(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_latest_ref(child, f"{path}[{index}]")
            if found:
                return found
    elif isinstance(value, str) and "_latest" in value.lower():
        return path
    return ""


def _reject_latest_path(path: Path, label: str) -> None:
    if any("_latest" in part.lower() for part in path.parts):
        raise AlrLocalRunnerError(f"{label}_path_latest_rejected")


def _reject_symlinked_existing_path(path: Path, label: str) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current = current / part
        try:
            current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise AlrLocalRunnerError(f"{label}_path_lstat_failed:{exc}") from exc
        if current.is_symlink():
            raise AlrLocalRunnerError(f"{label}_path_symlink_rejected")


def _validate_no_authority(value: Any) -> None:
    if not isinstance(value, Mapping) or not value:
        raise AlrLocalRunnerError("no_authority_invalid")
    bad_path = _first_not_false_leaf(value, "no_authority")
    if bad_path:
        raise AlrLocalRunnerError(f"no_authority_not_false:{bad_path}")


def _first_not_false_leaf(value: Any, path: str) -> str:
    if isinstance(value, Mapping):
        for key, child in value.items():
            found = _first_not_false_leaf(child, f"{path}.{key}")
            if found:
                return found
        return ""
    if isinstance(value, list):
        for index, child in enumerate(value):
            found = _first_not_false_leaf(child, f"{path}[{index}]")
            if found:
                return found
        return ""
    return "" if value is False else path


def _selected_work_item_ref(item: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        return {}
    return {"work_item_id": _text(item.get("work_item_id")), "row_id": _text(item.get("row_id")), "work_item_hash": _text(item.get("work_item_hash"))}


def _zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in _AUTHORITY_COUNTER_KEYS}


def _false_no_authority() -> dict[str, bool]:
    return {key: False for key in _NO_AUTHORITY_KEYS}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _strip_sha(value: str) -> str:
    return value[7:] if value.startswith("sha256:") else value


def _is_hex64(value: str) -> bool:
    stripped = _strip_sha(value)
    return len(stripped) == 64 and all(char in "0123456789abcdef" for char in stripped)


def _stable_sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
