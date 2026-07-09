from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

from ml_training.alr_controller_contracts import (
    BOUNDARY_LABEL,
    build_alr_work_item,
    compute_alr_loop_state_packet_hash,
    compute_alr_work_item_hash,
    validate_alr_loop_state_packet,
)
from ml_training.alr_local_runner import (
    INPUT_SCHEMA_VERSION,
    LEARNING_TARGET_FILENAME,
    OUTCOME_BRIDGE_FILENAME,
    REPORT_FILENAME,
    RETENTION_DRY_RUN_FILENAME,
    STATE_PACKET_FILENAME,
    compute_runner_manifest_hash,
    compute_runner_report_hash,
    main,
)
from ml_training.alr_retention_guardian_dry_run import (
    INPUT_SCHEMA_VERSION as RETENTION_INPUT_SCHEMA_VERSION,
    STATE_PROOF_OR_AUDIT_PROTECTED,
    STATE_REBUILDABLE_SCRATCH_CANDIDATE,
    compute_artifact_manifest_hash,
)
from ml_training.learning_target_arbiter import (
    INPUT_SCHEMA_VERSION as TARGET_INPUT_SCHEMA_VERSION,
    OBJECTIVE,
    compute_manifest_hash as compute_target_manifest_hash,
)


_EFFECT_REVIEW_TEST_PATH = Path(__file__).with_name("test_learning_effect_review.py")
_EFFECT_REVIEW_SPEC = importlib.util.spec_from_file_location(
    "_alr_local_runner_effect_review_fixtures",
    _EFFECT_REVIEW_TEST_PATH,
)
assert _EFFECT_REVIEW_SPEC is not None
_effect_review_fixtures = importlib.util.module_from_spec(_EFFECT_REVIEW_SPEC)
assert _EFFECT_REVIEW_SPEC.loader is not None
_EFFECT_REVIEW_SPEC.loader.exec_module(_effect_review_fixtures)
_effect_record = _effect_review_fixtures._record
_effect_loss_limits = _effect_review_fixtures._loss_limits


def _work_item(**overrides) -> dict:
    item = build_alr_work_item(
        work_item_id="P1-AIML-ALR-LOCAL-RUNNER",
        row_id="todo:P1-AIML-ALR-LOCAL-RUNNER",
        title="ALR local runner",
        source_refs={"boundary": BOUNDARY_LABEL},
    )
    item.update(overrides)
    item["work_item_hash"] = compute_alr_work_item_hash(item)
    return item


def _runner_manifest(**overrides) -> dict:
    manifest = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "created_at": "2026-07-09T00:00:00Z",
        "run_id": "alr-local-runner-unit",
        "source_head": "a" * 40,
        "latest_alias_used": False,
        "requested_step": "state_only",
        "max_steps": 1,
        "previous_state_packet_path": "",
        "work_items": [_work_item()],
        "inputs": {},
        "expected_previous_artifact_hashes": [],
        "no_authority": {
            "runtime": False,
            "pg": False,
            "ipc": False,
            "decision_lease": False,
            "adapter_writer": False,
            "bybit": False,
            "official_mcp": False,
            "order_or_probe": False,
            "cost_gate": False,
            "latest": False,
            "serving_or_promotion": False,
            "live_or_mainnet": False,
            "scheduler": False,
        },
    }
    manifest.update(overrides)
    manifest["manifest_hash"] = compute_runner_manifest_hash(manifest)
    return manifest


def _write_json(path: Path, value: dict | list) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def _run(manifest: dict, out_dir: Path, tmp_path: Path) -> int:
    manifest_path = _write_json(tmp_path / f"{manifest['run_id']}.json", manifest)
    return main(["--manifest", str(manifest_path), "--out-dir", str(out_dir)])


def _report(out_dir: Path) -> dict:
    return json.loads((out_dir / REPORT_FILENAME).read_text(encoding="utf-8"))


def _state_packet(out_dir: Path) -> dict:
    return json.loads((out_dir / STATE_PACKET_FILENAME).read_text(encoding="utf-8"))


def _assert_state_matches_report(out_dir: Path, *, reason_empty: bool = False) -> None:
    report = _report(out_dir)
    state = _state_packet(out_dir)
    validation = validate_alr_loop_state_packet(state)
    assert validation.valid is True, validation.reasons
    assert state["selected_work_item"] == report["selected_work_item"]
    assert state["component"]["name"] == report["component_status"]["component"]
    assert state["component"]["status"] == report["component_status"]["status"]
    assert state["component"]["stop_state"] == report["stop_state"]
    assert report["component_status"]["component"] in state["next_action"]
    assert state["stop_reason"] == ("" if reason_empty else report["stop_reason"])
    assert state["repo_head_before"] == report["source_head"]
    assert state["repo_head_after"] == report["source_head"]
    assert state["selection_reason"]
    assert state["owned_files"] == [
        "program_code/ml_training/alr_local_runner.py",
        "program_code/ml_training/tests/test_alr_local_runner.py",
    ]
    assert len(state["verification_commands"]) == 3
    assert state["candidate_matched_fills_count"] >= 0
    assert state["proof_packet_ready_count"] >= 0
    assert state["reward_ledger_ready_count"] >= 0
    assert isinstance(state["effect_review_ready"], bool)
    for field in (
        "model_training_performed",
        "serving_authority_granted",
        "llm_authority",
        "runtime_authority",
        "exchange_authority",
        "trading_authority",
    ):
        assert state[field] is False
    assert state["boundary_escalation_required"] is (
        report["stop_state"] == "BLOCKED_BOUNDARY"
    )
    assert state["dispatch_tooling_available"] is True
    assert state["dispatch_blocker"] == ""
    assert all(value == 0 for value in state["authority_counters"].values())
    assert all(value is False for value in state["no_authority"].values())
    assert state["packet_hash"] == compute_alr_loop_state_packet_hash(state)


def _target_manifest(**overrides) -> dict:
    target = {
        "target_id": "target-alpha",
        "candidate_scope": {"candidate_id": "grid_trading|ETHUSDT|Buy"},
        "learning_question": "next source-only label budget",
        "evidence_source_tier": "candidate_matched_fill",
        "expected_information_gain": 3.0,
        "uncertainty_reduction": 2.0,
        "cost_estimate": 1.0,
        "risk_penalty": 0.5,
        "staleness_penalty": 0.25,
        "eligibility": True,
    }
    manifest = {
        "schema_version": TARGET_INPUT_SCHEMA_VERSION,
        "created_at": "2026-07-09T00:00:00Z",
        "source_head": "a" * 40,
        "snapshot_id": "snapshot-alpha",
        "snapshot_kind": "source_only_offline_candidate_learning_targets",
        "objective": OBJECTIVE,
        "latest_alias_used": False,
        "targets": [target],
        "proof_exclusion": {
            "scanner_evidence_is_proof": False,
            "no_order_evidence_is_reward": False,
            "artifact_count_evidence_is_edge": False,
        },
        "no_authority": {"runtime": False, "pg": False, "order_or_probe": False},
    }
    manifest.update(overrides)
    manifest["manifest_hash"] = compute_target_manifest_hash(manifest)
    return manifest


def _retention_artifact(tmp_path: Path, artifact_id: str, **overrides) -> dict:
    body = f"{artifact_id}\n".encode("utf-8")
    path = tmp_path / f"{artifact_id}.json"
    path.write_bytes(body)
    stat = path.stat()
    artifact = {
        "artifact_id": artifact_id,
        "canonical_path": str(path),
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "producer": "unit_test",
        "schema_version": "scratch_artifact_v1",
        "candidate_identity": {},
        "source_hash": "",
        "input_hashes": [],
        "order_ids": [],
        "fill_ids": [],
        "context_ids": [],
        "outbound_refs": [],
        "inbound_refs": [],
        "report_refs": [],
        "todo_refs": [],
        "adr_refs": [],
        "amd_refs": [],
        "_latest_refs": [],
        "classification_reason": "ordinary scratch",
        "retention_state": STATE_REBUILDABLE_SCRATCH_CANDIDATE,
        "blockers": [],
        "rebuild_or_disposable_proof": {"rebuildable": True},
        "proposed_action": "NONE",
    }
    artifact.update(overrides)
    return artifact


def _retention_manifest(artifacts: list[dict]) -> dict:
    manifest = {
        "schema_version": RETENTION_INPUT_SCHEMA_VERSION,
        "boundary_label": BOUNDARY_LABEL,
        "created_at": "2026-07-09T00:00:00Z",
        "source_head": "a" * 40,
        "latest_alias_used": False,
        "no_authority": {"runtime": False, "pg": False, "order_or_probe": False},
        "artifacts": artifacts,
    }
    manifest["manifest_hash"] = compute_artifact_manifest_hash(manifest)
    return manifest


def test_learning_target_writes_exact_component_state_report_and_hashes(tmp_path: Path) -> None:
    snapshot = _write_json(tmp_path / "target_manifest.json", _target_manifest())
    out_dir = tmp_path / "run_target"
    manifest = _runner_manifest(
        requested_step="learning_target",
        inputs={"learning_target_snapshot_path": str(snapshot)},
    )

    assert _run(manifest, out_dir, tmp_path) == 0

    assert {path.name for path in out_dir.iterdir()} == {
        LEARNING_TARGET_FILENAME,
        REPORT_FILENAME,
        STATE_PACKET_FILENAME,
    }
    report = _report(out_dir)
    assert report["stop_state"] == "ADVANCED"
    assert report["component_status"]["component"] == "learning_target"
    assert report["report_hash"] == compute_runner_report_hash(report)
    assert all(value == 0 for value in report["authority_counters"].values())
    assert all(value is False for value in report["no_authority"].values())
    _assert_state_matches_report(out_dir, reason_empty=True)


def test_outcome_bridge_missing_evidence_defers_and_writes_component(tmp_path: Path) -> None:
    out_dir = tmp_path / "run_bridge"
    manifest = _runner_manifest(requested_step="outcome_bridge")

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    assert {path.name for path in out_dir.iterdir()} == {
        OUTCOME_BRIDGE_FILENAME,
        REPORT_FILENAME,
        STATE_PACKET_FILENAME,
    }
    assert report["stop_state"] == "DEFER_EVIDENCE"
    assert report["stop_state"] != "STOP_NO_EDGE"
    bridge = json.loads((out_dir / OUTCOME_BRIDGE_FILENAME).read_text(encoding="utf-8"))
    assert bridge["bridge_status"] == "DEFER_EVIDENCE"
    _assert_state_matches_report(out_dir)


def test_retention_dry_run_unreferenced_scratch_advances(tmp_path: Path) -> None:
    retention_path = _write_json(
        tmp_path / "retention_manifest.json",
        _retention_manifest([_retention_artifact(tmp_path, "scratch")]),
    )
    out_dir = tmp_path / "run_retention"
    manifest = _runner_manifest(
        requested_step="retention_dry_run",
        inputs={"retention_artifact_manifest_path": str(retention_path)},
    )

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    assert {path.name for path in out_dir.iterdir()} == {
        REPORT_FILENAME,
        RETENTION_DRY_RUN_FILENAME,
        STATE_PACKET_FILENAME,
    }
    assert report["stop_state"] == "ADVANCED"
    _assert_state_matches_report(out_dir, reason_empty=True)


def test_state_only_writes_state_and_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "run_state"
    manifest = _runner_manifest(requested_step="state_only")

    assert _run(manifest, out_dir, tmp_path) == 0

    assert {path.name for path in out_dir.iterdir()} == {
        REPORT_FILENAME,
        STATE_PACKET_FILENAME,
    }
    assert _report(out_dir)["stop_state"] == "DONE"


def test_selector_skips_done_rows_and_allows_default_max_steps(tmp_path: Path) -> None:
    out_dir = tmp_path / "run_selector"
    done_item = _work_item(
        work_item_id="P0-DONE",
        row_id="todo:P0-DONE",
        title="done row",
        state="DONE",
        status="DONE",
    )
    ready_item = _work_item(
        work_item_id="P1-READY",
        row_id="todo:P1-READY",
        title="ready row",
    )
    manifest = _runner_manifest(
        requested_step="state_only",
        work_items=[done_item, ready_item],
    )
    manifest.pop("max_steps")
    manifest["manifest_hash"] = compute_runner_manifest_hash(manifest)

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    state = _state_packet(out_dir)
    assert report["selected_work_item"]["work_item_id"] == "P1-READY"
    assert state["selected_work_item"]["work_item_id"] == "P1-READY"
    _assert_state_matches_report(out_dir, reason_empty=True)


def test_all_done_queue_keeps_empty_selection_consistent(tmp_path: Path) -> None:
    out_dir = tmp_path / "run_all_done"
    done_item = _work_item(
        work_item_id="P0-DONE",
        row_id="todo:P0-DONE",
        title="done row",
        state="DONE",
        status="DONE",
    )
    manifest = _runner_manifest(requested_step="state_only", work_items=[done_item])

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    state = _state_packet(out_dir)
    validation = validate_alr_loop_state_packet(state)
    assert validation.valid is True, validation.reasons
    assert report["selected_work_item"] == {}
    assert state["selected_work_item"] == {}
    assert state["selection_reason"] == "queue_empty"
    assert state["decision_reasons"] == ["queue_empty"]
    assert state["outcome"] == "DEFER_EVIDENCE"


def test_auto_selects_next_artifact_from_previous_state(tmp_path: Path) -> None:
    previous = {
        "schema_version": "previous_state_v1",
        "emitted_artifact_refs": [
            {
                "filename": LEARNING_TARGET_FILENAME,
                "schema_version": "learning_target_runtime_v1",
                "sha256": "a" * 64,
            }
        ],
    }
    previous_path = _write_json(tmp_path / "previous_state.json", previous)
    out_dir = tmp_path / "run_auto"
    manifest = _runner_manifest(requested_step="auto", previous_state_packet_path=str(previous_path))

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    assert report["planned_step"] == "outcome_bridge"
    assert report["component_status"]["component"] == "outcome_bridge"
    assert report["stop_state"] == "DEFER_EVIDENCE"
    _assert_state_matches_report(out_dir)


def test_latest_input_output_and_expected_ref_rejected_before_write(tmp_path: Path) -> None:
    latest_input = _write_json(tmp_path / "target_latest.json", _target_manifest())
    out_dir = tmp_path / "run_latest_input"
    manifest = _runner_manifest(
        requested_step="learning_target",
        inputs={"learning_target_snapshot_path": str(latest_input)},
    )
    assert _run(manifest, out_dir, tmp_path) == 2
    assert not out_dir.exists()

    clean_input = _write_json(tmp_path / "target_clean.json", _target_manifest())
    latest_out = tmp_path / "run_latest_out"
    manifest = _runner_manifest(
        requested_step="learning_target",
        inputs={"learning_target_snapshot_path": str(clean_input)},
    )
    assert _run(manifest, latest_out, tmp_path) == 2
    assert not latest_out.exists()

    latest_ref = tmp_path / "previous_latest.json"
    latest_ref.write_text("{}", encoding="utf-8")
    out_ref = tmp_path / "run_latest_ref"
    manifest = _runner_manifest(
        expected_previous_artifact_hashes=[
            {"path": str(latest_ref), "sha256": "a" * 64}
        ]
    )
    assert _run(manifest, out_ref, tmp_path) == 2
    assert not out_ref.exists()


def test_truthy_authority_flags_rejected_before_write(tmp_path: Path) -> None:
    out_dir = tmp_path / "run_auth"
    manifest = _runner_manifest(no_authority={"runtime": False, "order_or_probe": True})

    assert _run(manifest, out_dir, tmp_path) == 2

    assert not out_dir.exists()


def test_missing_control_and_oos_effect_review_defers_not_no_edge(tmp_path: Path) -> None:
    reward_path = _write_json(tmp_path / "reward.json", _effect_record(1))
    out_dir = tmp_path / "run_effect"
    manifest = _runner_manifest(
        requested_step="effect_review",
        inputs={
            "reward_ledger_paths": [str(reward_path)],
            "loss_limits": _effect_loss_limits(),
            "controls": {"matched_control_required": True, "oos_required": True},
            "oos_repeat_tags": {"oos": False, "repeat": False},
            "review_policy": {"min_sample_count": 1},
        },
    )

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    assert report["stop_state"] == "DEFER_EVIDENCE"
    assert report["stop_state"] != "STOP_NO_EDGE"
    _assert_state_matches_report(out_dir)


def test_retention_protected_or_unknown_refs_stop_retention_risk(tmp_path: Path) -> None:
    retention_path = _write_json(
        tmp_path / "retention_protected_manifest.json",
        _retention_manifest(
            [
                _retention_artifact(
                    tmp_path,
                    "protected",
                    retention_state=STATE_PROOF_OR_AUDIT_PROTECTED,
                    order_ids=["order-1"],
                )
            ]
        ),
    )
    out_dir = tmp_path / "run_retention_risk"
    manifest = _runner_manifest(
        requested_step="retention_dry_run",
        inputs={"retention_artifact_manifest_path": str(retention_path)},
    )

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    assert report["stop_state"] == "STOP_RETENTION_RISK"
    _assert_state_matches_report(out_dir)


def test_expected_previous_artifact_hash_mismatch_returns_rotated(tmp_path: Path) -> None:
    artifact = tmp_path / "previous.json"
    artifact.write_text("previous\n", encoding="utf-8")
    out_dir = tmp_path / "run_rotated"
    manifest = _runner_manifest(
        expected_previous_artifact_hashes=[
            {"path": str(artifact), "sha256": "0" * 64}
        ]
    )

    assert _run(manifest, out_dir, tmp_path) == 0

    report = _report(out_dir)
    assert report["stop_state"] == "ROTATED"
    assert not (out_dir / OUTCOME_BRIDGE_FILENAME).exists()
    _assert_state_matches_report(out_dir)


def test_non_empty_or_symlinked_output_dir_rejected(tmp_path: Path) -> None:
    non_empty = tmp_path / "non_empty"
    non_empty.mkdir()
    (non_empty / "existing.json").write_text("{}", encoding="utf-8")
    manifest = _runner_manifest()

    assert _run(manifest, non_empty, tmp_path) == 2

    target = tmp_path / "real_dir"
    target.mkdir()
    symlink = tmp_path / "symlink_dir"
    symlink.symlink_to(target, target_is_directory=True)

    assert _run(manifest, symlink, tmp_path) == 2


def test_existing_empty_output_dir_is_accepted(tmp_path: Path) -> None:
    out_dir = tmp_path / "existing_empty"
    out_dir.mkdir()
    manifest = _runner_manifest(requested_step="state_only")

    assert _run(manifest, out_dir, tmp_path) == 0

    assert sorted(path.name for path in out_dir.iterdir()) == [
        REPORT_FILENAME,
        STATE_PACKET_FILENAME,
    ]
    _assert_state_matches_report(out_dir, reason_empty=True)


def test_static_guard_no_forbidden_runtime_surfaces() -> None:
    source_path = Path(__file__).resolve().parents[1] / "alr_local_runner.py"
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()
    for term in (
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "psycopg",
        "asyncpg",
        "sqlalchemy",
        "os.environ",
        "sleep",
        "while true",
        "cron",
        "launchd",
        "systemd",
    ):
        assert term not in lowered

    tree = ast.parse(source)
    forbidden_calls = {"delete", "apply", "prune"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in forbidden_calls
            elif isinstance(func, ast.Attribute):
                assert func.attr not in forbidden_calls
