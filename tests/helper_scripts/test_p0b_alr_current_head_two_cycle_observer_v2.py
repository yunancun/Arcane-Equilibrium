from __future__ import annotations

import importlib.util
import copy
import hashlib
import json
import os
from pathlib import Path
import ast
from datetime import datetime, timezone

import pytest


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE.parents[1] / "helper_scripts/maintenance_scripts/p0b_alr_current_head_two_cycle_observer_v2.py"
TARGET_HEAD = "211f26c8e865757633076bc137c743f48fed80b6"
AUTH_NOW = datetime(2026, 7, 18, 0, 4, tzinfo=timezone.utc)
GOVERNANCE_CUTOVER_HARD_STOPS = [
    "phase-scoped P0-B ALR effect only",
    "no live/mainnet authority expansion",
    "no order/broker/decision-lease effect",
    "no unrelated service or user-manager mutation",
    "no ambient environment or secret inheritance",
    (
        "only fresh public Git origin read, normal-lane readonly PG, and existing "
        "fixed-path credential load are allowed"
    ),
    (
        "no broker/private external contact, package installation, or adapter "
        "credential-content read"
    ),
    "fail closed; never restore the old generation after cutover begins",
    "cutover finalizes only after OBSERVER_V2_EXACT_POSTCHECK_PASS",
]


def _load_module():
    spec = importlib.util.spec_from_file_location("p0b_current_observer_v2", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _binding(path: str, digest: str = "a" * 64) -> dict[str, str]:
    return {"path": path, "sha256": digest}


def _prefixed_canonical(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _runtime_bindings(
    config: dict[str, object],
    authorization: dict[str, object],
    *,
    phase: str,
    phase1: dict[str, object] | None = None,
    phase1_closure: dict[str, str] | None = None,
    sealed_lineage_bundle: dict[str, str] | None = None,
) -> dict[str, object]:
    private = config["private_deps"]
    board = config["admitted_board"]
    source = {
        "source": {
            "head": config["target_head"],
            "origin_main": config["target_head"],
            "remote_origin_main": config["target_head"],
        },
        "execution_tree": {"tree": "sealed-source-tree"},
        "source_tree_digest": _prefixed_canonical({"tree": "sealed-source-tree"}),
    }
    runtime_identity = {
        "schema_version": "p0b_alr_runtime_identity_v1",
        "target_host": "trade-core",
        "target_user_unit": "openclaw-alr-shadow.service",
        "source_head": "0" * 40,
        "invocation_id": "0" * 32,
        "main_pid": "1000",
        "main_pid_start_ticks": "2000",
        "control_group": "/user.slice/alr",
        "unit_fragment_path": "/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service",
        "unit_file_sha256": "1" * 64,
        "pin_path": "/home/ncyu/BybitOpenClaw/var/openclaw/runtime_generation/expected_source_head.json",
        "pin_sha256": "8" * 64,
        "cost_pin_lock_path": "/locks/cost",
        "alpha_pin_lock_path": "/locks/alpha",
        "nrestarts": 0,
        "active_state": "active",
        "sub_state": "running",
        "observed_at": "2026-07-17T23:30:00Z",
    }
    protected = {
        "service_baseline": {
            "unit_sha256": "1" * 64,
            "pin_sha256": "8" * 64,
            "unit_head": "0" * 40,
            "pin_head": "0" * 40,
            "active_identity": {"InvocationID": "0" * 32},
            "unit_identity": {"sha256": "1" * 64},
            "pin_identity": {"sha256": "8" * 64},
            "unit_lock_identity": {"ino": 1},
            "cost_lock_identity": {"ino": 2},
            "alpha_lock_identity": {"ino": 3},
        },
        "protected": {"scope": "old-runtime"},
        "protected_digest": _prefixed_canonical({"scope": "old-runtime"}),
        "pin_consumer_inventory": {"consumers": []},
        "pin_consumer_inventory_digest": _prefixed_canonical({"consumers": []}),
        "runtime_identity": runtime_identity,
        "runtime_identity_digest": _prefixed_canonical(runtime_identity),
    }
    inventories = {
        "live_inventory": {"live": []},
        "completion_inventory": {"completion": []},
        "producer_inventory": {"producer": []},
        "ledger_inventory": {"ledger": []},
        "lane_effective_config": {"lane": "alr"},
    }
    for value, digest in (
        ("live_inventory", "live_inventory_digest"),
        ("completion_inventory", "completion_inventory_digest"),
        ("producer_inventory", "producer_inventory_digest"),
        ("ledger_inventory", "ledger_inventory_digest"),
        ("lane_effective_config", "lane_effective_config_digest"),
    ):
        inventories[digest] = _prefixed_canonical(inventories[value])
    root = "/home/ncyu/BybitOpenClaw/var/openclaw/runtime_recovery/alr-current-head-rollforward"
    intent = authorization["intent_id"]
    if phase == "stage":
        staging = f"{root}/staging/{intent}"
        paths = {
            "staging_root": staging,
            "cron_destination": f"{staging}/cron-scratch",
            "sealed_destination": f"{staging}/sealed",
            "publisher_receipt_path": f"{staging}/staging-publisher-result.json",
            "private_deps_receipt_path": f"{staging}/private-deps-receipt.json",
            "private_deps_destination": private["destination"],
            "phase1_receipt_path": f"{root}/{intent}.phase1.json",
            "phase1_closure_path": f"{root}/{intent}.phase1.closure.json",
        }
        lineage = {
            "p0a_completed_board_input": _binding("/evidence/p0a.json", "5" * 64),
            "private_bundle_destination_absent": {
                "destination": private["destination"],
                "absent": True,
            },
        }
        authorization["claim_bindings"]["p0b_p0a_completed_board_input"] = (
            "sha256:" + lineage["p0a_completed_board_input"]["sha256"]
        )
        authorization["claim_bindings"][
            "p0b_private_bundle_destination_absent_attestation"
        ] = _prefixed_canonical(lineage["private_bundle_destination_absent"])
    else:
        assert phase1 is not None
        assert phase1_closure is not None
        assert sealed_lineage_bundle is not None
        paths = {
            "phase1_receipt_path": "/evidence/phase1.json",
            "phase1_closure_path": "/evidence/phase1-closure.json",
            "live_destination": "/home/ncyu/.local/share/openclaw/alr-candidate-evidence",
            "provisional_cutover_path": f"{root}/{intent}.phase2.provisional.json",
            "observer_input_path": f"{root}/{intent}.phase2.observer-input.json",
        }
        lineage = {
            "phase1_receipt": copy.deepcopy(config["phase1_receipt"]),
            "phase1_closure": copy.deepcopy(phase1_closure),
            "sealed_lineage_bundle": copy.deepcopy(sealed_lineage_bundle),
            "completion": _binding("/evidence/completion.json", "7" * 64),
            "producer_board": _binding("/evidence/producer.json", "8" * 64),
            "staged_board": {
                "path": board["staged_path"],
                "sha256": board["source_content_sha256"],
            },
            "staging_publisher_receipt": _binding("/evidence/publisher.json", "9" * 64),
            "private_deps_receipt": copy.deepcopy(private["receipt"]),
            "token": "a" * 32,
            "max_age_seconds": 3600,
            "proposed_unit_sha256": config["runtime_files"]["unit"]["sha256"],
            "private_deps_destination": private["destination"],
            "private_deps_manifest_sha256": private["manifest_sha256"],
            "completion_inventory_digest": inventories["completion_inventory_digest"],
            "producer_inventory_digest": inventories["producer_inventory_digest"],
            "ledger_pre_inventory_digest": "sha256:" + "c" * 64,
            "ledger_post_inventory_digest": inventories["ledger_inventory_digest"],
            "lane_effective_config_digest": inventories["lane_effective_config_digest"],
        }
    artifact = {
        "schema_version": "phase_runtime_bindings_v1",
        "phase": phase,
        "intent_id": intent,
        "target_head": config["target_head"],
        "source_attestation": source,
        "protected_runtime_baseline": protected,
        "phase_paths": paths,
        "inventories": inventories,
        "lineage": lineage,
        "section_claims": {},
        "observed_at": "2026-07-17T23:41:00Z" if phase == "stage" else "2026-07-18T00:01:00Z",
        "expires_at": "2026-07-17T23:54:00Z" if phase == "stage" else "2026-07-18T00:08:00Z",
    }
    sections = {
        "source_attestation": "p0b_runtime_source_binding",
        "protected_runtime_baseline": "p0b_runtime_protected_binding",
        "phase_paths": "p0b_runtime_paths_binding",
        "inventories": "p0b_runtime_inventories_binding",
        "lineage": "p0b_runtime_lineage_binding",
    }
    for section, claim in sections.items():
        digest = _prefixed_canonical(artifact[section])
        artifact["section_claims"][section] = {"claim": claim, "digest": digest}
        authorization["claim_bindings"][claim] = digest
    artifact["artifact_digest"] = _prefixed_canonical(artifact)
    authorization["claim_bindings"]["p0b_phase_runtime_bindings"] = artifact[
        "artifact_digest"
    ]
    authorization["claim_bindings"]["p0b_target_source_attestation"] = (
        _prefixed_canonical(source)
    )
    authorization["claim_bindings"]["p0b_protected_runtime_baseline"] = protected[
        "protected_digest"
    ]
    authorization["governance_bindings"]["protected_baseline_digest"] = protected[
        "protected_digest"
    ]
    authorization["claim_bindings"]["p0b_live_inventory"] = inventories[
        "live_inventory_digest"
    ]
    authorization["claim_bindings"]["p0b_completion_inventory"] = inventories[
        "completion_inventory_digest"
    ]
    authorization["claim_bindings"]["p0b_producer_inventory"] = inventories[
        "producer_inventory_digest"
    ]
    authorization["expected_source_tree_digest"] = source["source_tree_digest"]
    authorization["expected_old_runtime_source_head"] = "0" * 40
    authorization["expected_old_pin_digest"] = "sha256:" + "8" * 64
    authorization["expected_pin_consumer_inventory_digest"] = protected[
        "pin_consumer_inventory_digest"
    ]
    authorization["expected_runtime_identity_digest"] = protected[
        "runtime_identity_digest"
    ]
    path = f"/evidence/{phase}-runtime-bindings.json"
    authorization["governance_bindings"]["phase_runtime_bindings_path"] = path
    authorization["governance_bindings"][
        "phase_runtime_bindings_artifact_digest"
    ] = artifact["artifact_digest"]
    return artifact


def _payload() -> dict[str, object]:
    return {
        "schema_version": "p0b_alr_current_head_observer_input_v2",
        "target_head": TARGET_HEAD,
        "observer_not_before_utc": "2026-07-18T00:00:00Z",
        "active_identity": {
            "MainPID": "2001",
            "ProcessStartTicks": "9000000",
            "InvocationID": "b" * 32,
            "ExecMainStartTimestampMonotonic": "9000001",
            "NRestarts": "0",
            "ALRSourceHead": TARGET_HEAD,
        },
        "phase1_receipt": _binding("/evidence/phase1.json", "1" * 64),
        "cutover_authorization": _binding(
            "/evidence/cutover-authorization.json", "2" * 64
        ),
        "provisional_cutover": _binding("/evidence/provisional-cutover.json", "3" * 64),
        "admitted_board": {
            "staged_path": "/evidence/sealed/board.json",
            "live_path": "/home/ncyu/.local/share/openclaw/alr-candidate-evidence/board.json",
            "source_content_sha256": "4" * 64,
            "generated_at_utc": "2026-07-17T23:59:00Z",
            "board_hash": "5" * 64,
            "audit_hash": "6" * 64,
            "selection_hash": "7" * 64,
            "candidate_set_hash": "8" * 64,
        },
        "runtime_files": {
            "unit": _binding(
                "/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service",
                "9" * 64,
            ),
            "pin": _binding(
                "/home/ncyu/BybitOpenClaw/var/openclaw/runtime_generation/expected_source_head.json",
                "a" * 64,
            ),
            "pin_derived_at_utc": "2026-07-18T00:00:01Z",
        },
        "consumer_source": {
            "path": "/home/ncyu/BybitOpenClaw/srv/program_code/ml_training/alr_event_consumer.py",
            "sha256": "01f51e7248411ae589169dab8dade9b7014ba7819f261817e80d4045adece9a9",
            "blob_sha1": "9abd818c3a12a247f5b567af8faf3b41c3eede41",
            "ml_training_tree_sha1": "ea3fb4e3cc88de27b2012af1eec727523cf173eb",
        },
        "git_seals": {
            "origin_main_head": TARGET_HEAD,
            "tracked_file_count": 8784,
            "git_index_sha256": "d" * 64,
            "git_index_size": 1322183,
            "git_stage_inventory_sha256": "e" * 64,
            "git_stage_inventory_size": 1166201,
        },
        "private_deps": {
            "receipt": _binding("/evidence/private-deps.json", "b" * 64),
            "destination": "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps",
            "manifest_sha256": "c" * 64,
        },
        "no_authority": {
            "order": False,
            "probe": False,
            "promotion": False,
            "runtime": False,
        },
    }


def test_exact_current_head_input_contract_accepts_bound_values() -> None:
    module = _load_module()

    validated = module.validate_observer_input_payload(_payload())

    assert validated["target_head"] == TARGET_HEAD
    assert validated["active_identity"]["InvocationID"] == "b" * 32
    assert validated["admitted_board"]["source_content_sha256"] == "4" * 64


def _valid_nonempty_board_outer(module: object) -> dict[str, object]:
    """Build one self-contained exact-field canonical candidate board."""

    row = {field: 0 for field in module.CANDIDATE_ROW_FIELDS}
    identity = {
        "strategy_name": "ma_crossover",
        "strategy_version": "v2",
        "strategy_config_hash": "1" * 64,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "horizon_minutes": 60,
        "target_regime_hash": "2" * 64,
        "venue": "bybit",
        "product": "linear_perpetual",
        "engine_mode": "shadow",
    }
    row.update(
        {
            "schema_version": "cost_gate_learning_candidate_v2",
            "candidate_id": "candidate-nonempty-1",
            "candidate_family_key": "3" * 64,
            "stable_cohort_hash": "4" * 64,
            "candidate_identity": identity,
            "identity_complete": True,
            "arbiter_input": {
                "schema_version": "alr_candidate_arbiter_input_v2",
                "identity": {"symbol": "BTCUSDT"},
            },
            "arbiter_input_complete": True,
            "selection_eligible": True,
            "blockers": [],
            "qualified_metrics_actionable": True,
            "metrics_scope": "QUALIFIED_SUBSET_ACTIONABLE",
            "side_cell_key": "ma_crossover|BTCUSDT|Buy",
            "horizon_minutes": 60,
            "qualified_raw_outcome_count": 1,
            "qualified_evaluator_input_count": 1,
            "qualified_uncensored_outcome_count": 1,
            "qualified_valid_uncensored_outcome_count": 1,
            "qualified_invalid_outcome_row_count": 0,
            "qualified_censored_outcome_count": 0,
            "lineage_blocker_reason_counts": {},
            "qualified_distinct_entry_observation_count": 1,
            "n_eff": 1,
            "distinct_entry_utc_days": 1,
            "entry_day_counts": {"2026-07-17": 1},
            "top_entry_utc_day": "2026-07-17",
            "regime_entry_counts": {"neutral|mid_vol|liquid": 1},
            "regime_coverage_inputs": [],
            "cost_basis_main": "expected_slippage_mean_abs_v1",
            "tail_metric": "cvar90",
            "hidden_oos_consumed": False,
        }
    )
    semantic_rows = [
        {field: row[field] for field in module.CANDIDATE_SELECTION_FIELDS}
    ]
    board = {
        "schema_version": "cost_gate_learning_candidate_board_v2",
        "as_of_utc_date": "2026-07-17",
        "candidate_universe_complete": True,
        "lineage_partition_complete": True,
        "raw_blocked_outcome_row_count": 1,
        "qualified_lineage_outcome_row_count": 1,
        "unqualified_lineage_outcome_row_count": 0,
        "invalid_lineage_outcome_row_count": 0,
        "invalid_exact_cohort_row_count": 0,
        "invalid_identity_family_row_count": 0,
        "unassigned_invalid_lineage_outcome_row_count": 0,
        "unqualified_raw_valid_evaluation_missing_row_count": 0,
        "unqualified_event_outside_evaluation_window_row_count": 0,
        "consistent_duplicate_event_hash_extra_row_count": 0,
        "conflicting_duplicate_event_hash_row_count": 0,
        "conflicting_duplicate_event_hash_attribution_row_count": 0,
        "lineage_exclusion_reason_counts": {},
        "candidate_rows": [row],
        "selection_hash": module.canonical_sha256(
            {
                "schema_version": "cost_gate_learning_candidate_selection_v2",
                "candidate_rows": semantic_rows,
            }
        ),
    }
    board["audit_hash"] = module.canonical_sha256(
        {
            "schema_version": "cost_gate_learning_candidate_audit_v2",
            **{
                field: board[field]
                for field in module.CANDIDATE_BOARD_AUDIT_FIELDS
            },
            "candidate_audit_rows": module.candidate_audit_rows([row]),
        }
    )
    board["board_hash"] = module.canonical_sha256(board)
    return {
        "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v6",
        "candidate_board_generation_state": "COMPLETE",
        "ledger_scan_status": "COMPLETE",
        "latest_alias_used": False,
        "generated_at_utc": "2026-07-17T23:59:00Z",
        "learning_candidate_board": board,
    }


def _bind_config_to_board(
    module: object,
    outer: dict[str, object],
) -> dict[str, object]:
    config = _payload()
    board = outer["learning_candidate_board"]
    assert isinstance(board, dict)
    semantic_rows = [
        {field: row[field] for field in module.CANDIDATE_SELECTION_FIELDS}
        for row in board["candidate_rows"]
    ]
    semantic_rows.sort(
        key=lambda row: (row["candidate_id"], module.canonical_sha256(row))
    )
    config["admitted_board"].update(
        {
            "generated_at_utc": outer["generated_at_utc"],
            "board_hash": board["board_hash"],
            "audit_hash": board["audit_hash"],
            "selection_hash": board["selection_hash"],
            "candidate_set_hash": module.canonical_sha256(semantic_rows),
        }
    )
    return module.validate_observer_input_payload(config)


def test_dynamic_board_accepts_valid_nonempty_exact_candidate_rows() -> None:
    module = _load_module()
    outer = _valid_nonempty_board_outer(module)
    config = _bind_config_to_board(module, outer)

    result = module.validate_dynamic_candidate_board(config, outer)

    assert result["candidate_count"] == 1
    assert result["qualified_lineage_outcome_row_count"] == 1
    assert result["candidate_rows"] == outer["learning_candidate_board"][
        "candidate_rows"
    ]
    assert result["candidate_set_hash"] == config["admitted_board"][
        "candidate_set_hash"
    ]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("qualified_count", "board_candidate_totals_invalid"),
        ("board_hash", "board_hash_mismatch"),
        ("selection_hash", "board_selection_hash_mismatch"),
        ("audit_hash", "board_audit_hash_mismatch"),
        ("candidate_set_hash", "board_candidate_set_hash_mismatch"),
    ),
)
def test_dynamic_board_rejects_forged_count_or_hash(
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    outer = _valid_nonempty_board_outer(module)
    config = _bind_config_to_board(module, outer)
    board = outer["learning_candidate_board"]
    assert isinstance(board, dict)
    if mutation == "qualified_count":
        board["qualified_lineage_outcome_row_count"] += 1
        board["raw_blocked_outcome_row_count"] += 1
        board["audit_hash"] = module.canonical_sha256(
            {
                "schema_version": "cost_gate_learning_candidate_audit_v2",
                **{
                    field: board[field]
                    for field in module.CANDIDATE_BOARD_AUDIT_FIELDS
                },
                "candidate_audit_rows": module.candidate_audit_rows(
                    board["candidate_rows"]
                ),
            }
        )
        board["board_hash"] = module.canonical_sha256(
            {key: value for key, value in board.items() if key != "board_hash"}
        )
        config["admitted_board"]["audit_hash"] = board["audit_hash"]
        config["admitted_board"]["board_hash"] = board["board_hash"]
    elif mutation == "candidate_set_hash":
        config["admitted_board"]["candidate_set_hash"] = "f" * 64
    else:
        board[mutation] = "f" * 64
        config["admitted_board"][mutation] = "f" * 64

    with pytest.raises(module.ObserverInputError, match=reason):
        module.validate_dynamic_candidate_board(config, outer)


def _decision_ready_assessment() -> dict[str, object]:
    metrics = {
        field: "1.000000000000000000"
        for field in (
            "n_eff",
            "median_distinct_entries_7d",
            "expected_new_entries",
            "information_gain",
            "gate_progress",
            "ambiguity",
            "quality",
            "compute",
            "storage",
            "resource",
            "portfolio_redundancy",
            "day_coverage",
            "day_deficit",
            "regime_coverage",
            "regime_deficit",
            "bull_share",
            "evi",
        )
    }
    return {
        "family_key": "1" * 64,
        "evaluation_id": "2" * 64,
        "material_fingerprint": "3" * 64,
        "identity": {"symbol": "BTCUSDT"},
        "context_hashes": {"data": "4" * 64},
        "proof_stage": 1,
        "next_gap": {"kind": "proof", "code": "E2"},
        "learning_only": True,
        "state": "DECISION_READY",
        "eligible": True,
        "blocker_codes": [],
        "portfolio_assumption": "UNKNOWN_PENALIZED",
        "scanner_context": {
            "novelty": "1.000000000000000000",
            "recurrence": "1.000000000000000000",
        },
        "metrics": metrics,
        "rank": 1,
    }


def _dynamic_decision(
    module: object,
    board_result: dict[str, object],
    *,
    nonempty: bool,
) -> dict[str, object]:
    assessments = [_decision_ready_assessment()] if nonempty else []
    selected = (
        module.candidate_selection_view(assessments[0]) if nonempty else None
    )
    return {
        "decision_code": (
            "QUALIFIED_CANDIDATE_SELECTED"
            if nonempty
            else "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION"
        ),
        "evidence_source_status": "READY",
        "evidence_selection_hash": board_result["selection_hash"],
        "candidate_set_hash": board_result["candidate_set_hash"],
        "policy_hash": "5" * 64,
        "selected_candidate": selected,
        "selected_collection_target": None,
        "candidate_count": len(assessments),
        "eligible_candidate_count": len(assessments),
        "evaluated_candidates": assessments,
    }


@pytest.mark.parametrize("nonempty", (False, True))
def test_dynamic_decision_semantics_accept_empty_and_nonempty_board(
    nonempty: bool,
) -> None:
    module = _load_module()
    outer = _valid_nonempty_board_outer(module)
    config = _bind_config_to_board(module, outer)
    board_result = module.validate_dynamic_candidate_board(config, outer)
    if not nonempty:
        empty_rows = []
        empty_board = copy.deepcopy(outer)
        board = empty_board["learning_candidate_board"]
        board["raw_blocked_outcome_row_count"] = 0
        board["qualified_lineage_outcome_row_count"] = 0
        board["candidate_rows"] = empty_rows
        board["selection_hash"] = module.canonical_sha256(
            {
                "schema_version": "cost_gate_learning_candidate_selection_v2",
                "candidate_rows": [],
            }
        )
        board["audit_hash"] = module.canonical_sha256(
            {
                "schema_version": "cost_gate_learning_candidate_audit_v2",
                **{
                    field: board[field]
                    for field in module.CANDIDATE_BOARD_AUDIT_FIELDS
                },
                "candidate_audit_rows": [],
            }
        )
        board["board_hash"] = module.canonical_sha256(
            {key: value for key, value in board.items() if key != "board_hash"}
        )
        config["admitted_board"].update(
            {
                "board_hash": board["board_hash"],
                "audit_hash": board["audit_hash"],
                "selection_hash": board["selection_hash"],
                "candidate_set_hash": module.canonical_sha256([]),
            }
        )
        board_result = module.validate_dynamic_candidate_board(config, empty_board)

    result = module.validate_dynamic_decision_semantics(
        _dynamic_decision(module, board_result, nonempty=nonempty),
        board_result,
    )

    assert result["decision_code"] == (
        "QUALIFIED_CANDIDATE_SELECTED"
        if nonempty
        else "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION"
    )
    assert result["candidate_count"] == int(nonempty)


@pytest.mark.parametrize("mutation", ("count", "selected", "selection_hash"))
def test_dynamic_decision_semantics_reject_forged_nonempty_binding(
    mutation: str,
) -> None:
    module = _load_module()
    outer = _valid_nonempty_board_outer(module)
    config = _bind_config_to_board(module, outer)
    board_result = module.validate_dynamic_candidate_board(config, outer)
    decision = _dynamic_decision(module, board_result, nonempty=True)
    if mutation == "count":
        decision["candidate_count"] = 0
    elif mutation == "selected":
        decision["selected_candidate"]["evaluation_id"] = "f" * 64
    else:
        decision["evidence_selection_hash"] = "f" * 64

    with pytest.raises(module.ObserverInputError, match="dynamic_decision_semantics_invalid"):
        module.validate_dynamic_decision_semantics(decision, board_result)


def test_o_excl_private_input_is_read_once_and_exact_hash_bound(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "observer-input.json"
    raw = json.dumps(_payload(), sort_keys=True, separators=(",", ":")).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        assert os.write(descriptor, raw) == len(raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    loaded, identity = module.load_observer_input(
        path,
        hashlib.sha256(raw).hexdigest(),
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert loaded == module.validate_observer_input_payload(_payload())
    assert identity["sha256"] == hashlib.sha256(raw).hexdigest()
    assert identity["mode"] == "0600"


def test_separate_lineage_artifacts_use_hardened_exact_reader(tmp_path: Path) -> None:
    module = _load_module()
    raw = b'{"schema_version":"sealed-test"}'
    path = tmp_path / "sealed-lineage.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    digest = hashlib.sha256(raw).hexdigest()

    loaded, identity = module.read_bound_regular(
        path,
        digest,
        mode=0o600,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )

    assert loaded == raw
    assert identity["sha256"] == digest
    symlink = tmp_path / "sealed-link.json"
    symlink.symlink_to(path)
    with pytest.raises(module.ObserverInputError, match="bound_artifact_identity_invalid"):
        module.read_bound_regular(
            symlink,
            digest,
            mode=0o600,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )
    with pytest.raises(module.ObserverInputError, match="identity_or_hash_drift"):
        module.read_bound_regular(
            path,
            "f" * 64,
            mode=0o600,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        )

    source = MODULE_PATH.read_text()
    tree = ast.parse(source)
    load_bound = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "load_bound_trust"
    )
    load_source = ast.get_source_segment(source, load_bound)
    reader_source = ast.get_source_segment(
        source,
        next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "read_bound_regular"
        ),
    )
    assert load_source is not None
    assert 'for label in ("phase1_closure", "sealed_lineage_bundle")' in load_source
    assert 'mode=0o600' in load_source
    assert reader_source is not None and "O_NOFOLLOW" in reader_source


def test_arbitrary_authorized_target_head_is_accepted_without_self_reference() -> None:
    module = _load_module()
    payload = _payload()
    payload["target_head"] = "d" * 40
    payload["active_identity"]["ALRSourceHead"] = "d" * 40
    payload["git_seals"]["origin_main_head"] = "d" * 40

    result = module.validate_observer_input_payload(payload)

    assert result["target_head"] == "d" * 40


@pytest.mark.parametrize("mutation", ["active_head", "origin_main"])
def test_authorized_target_head_binding_drift_is_rejected(mutation: str) -> None:
    module = _load_module()
    payload = _payload()
    if mutation == "active_head":
        payload["active_identity"]["ALRSourceHead"] = "d" * 40
    else:
        payload["git_seals"]["origin_main_head"] = "d" * 40

    with pytest.raises(module.ObserverInputError):
        module.validate_observer_input_payload(payload)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("index", "target_git_index_seal_mismatch"),
        ("stage", "target_git_stage_inventory_seal_mismatch"),
        ("count", "target_git_tracked_count_mismatch"),
    ],
)
def test_dynamic_git_index_and_stage_seal_drift_is_rejected(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    index_raw = b"sealed-index-bytes"
    index_path = tmp_path / "index"
    index_path.write_bytes(index_raw)
    stage = "100644 " + "a" * 40 + " 0\tprogram.py\x00"
    payload = _payload()
    payload["git_seals"] = {
        "origin_main_head": payload["target_head"],
        "tracked_file_count": 1,
        "git_index_sha256": hashlib.sha256(index_raw).hexdigest(),
        "git_index_size": len(index_raw),
        "git_stage_inventory_sha256": hashlib.sha256(stage.encode()).hexdigest(),
        "git_stage_inventory_size": len(stage.encode()),
    }
    if mutation == "index":
        payload["git_seals"]["git_index_sha256"] = "f" * 64
    elif mutation == "stage":
        payload["git_seals"]["git_stage_inventory_sha256"] = "f" * 64
    else:
        payload["git_seals"]["tracked_file_count"] = 2
    config = module.validate_observer_input_payload(payload)

    class Runtime:
        @staticmethod
        def run(_argv, **_kwargs):
            return module.types.SimpleNamespace(stdout=stage)

    base = module.types.SimpleNamespace(
        RECOVERY_GIT_INDEX_PATH=index_path,
        MAX_GIT_INDEX_INVENTORY_BYTES=1024,
        RECOVERY_GIT_COMMAND_PREFIX=("/usr/bin/git",),
        RECOVERY_HARDENED_GIT_ENV={},
    )
    recovery = module.types.SimpleNamespace(
        base=module.types.SimpleNamespace(RecoveryRuntime=Runtime)
    )

    with pytest.raises(module.ObserverInputError, match=reason):
        module.prepare_current_git_seals(base, recovery, config)


def _lineage_payloads(config: dict[str, object]) -> dict[str, dict[str, object]]:
    board = config["admitted_board"]
    active = config["active_identity"]
    runtime = config["runtime_files"]
    private = config["private_deps"]
    authorized_runtime = {
        "expected_old_runtime_source_head": "0" * 40,
        "expected_old_pin_digest": "sha256:" + "8" * 64,
        "expected_source_tree_digest": "sha256:" + "9" * 64,
        "expected_pin_consumer_inventory_digest": "sha256:" + "a" * 64,
        "expected_runtime_identity_digest": "sha256:" + "5" * 64,
    }
    phase1 = {
        "schema_version": "p0b_alr_current_head_rollforward_v1",
        "phase": 1,
        "status": "PHASE1_STAGING_APPLIED_PASS",
        "target_head": config["target_head"],
        "old_alr_retained_running": True,
        "sealed_lineage": {
            "staged_board": {
                "path": board["staged_path"],
                "sha256": board["source_content_sha256"],
            },
            "completion_inventory_sha256": "sha256:" + "d" * 64,
            "producer_inventory_sha256": "sha256:" + "e" * 64,
            "ledger_post_inventory_sha256": "sha256:" + "f" * 64,
            "lane_effective_config_sha256": "sha256:" + "0" * 64,
        },
    }
    stage_claim_keys = {
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
    stage_governance = {
        key: "sha256:" + format(index, "064x")[-64:]
        for index, key in enumerate(
            (
                "compiled_route_digest", "route_dag_digest",
                "pm_context_artifact_digest", "pa_context_artifact_digest",
                "e3_context_artifact_digest", "ops_preflight_context_artifact_digest",
                "pa_role_fragment_digest", "pa_command_capture_digest",
                "e3_role_fragment_digest", "e3_command_capture_digest",
                "ops_preflight_role_fragment_digest",
                "ops_preflight_command_capture_digest",
                "ops_preflight_attestation_digest", "pm_approval_artifact_digest",
                "authorized_argv_digest", "protected_baseline_digest",
            ),
            100,
        )
    }
    stage_governance.update(
        {
            "compiled_route_schema": "hybrid_execution_dag_v1",
            "context_artifact_schema": "context_artifact_v1",
            "ops_preflight_observed_at": "2026-07-17T23:39:00Z",
            "ops_preflight_expires_at": "2026-07-17T23:54:00Z",
            "protected_baseline_digest": "sha256:" + "b" * 64,
            "phase_runtime_bindings_artifact_digest": "sha256:" + "c" * 64,
            "phase_runtime_bindings_path": "/evidence/stage-runtime-bindings.json",
            "authorization_path": "/evidence/stage-authorization.json",
        }
    )
    stage_authorization = {
        "schema_version": "p0b_alr_runtime_authorization_v1",
        "adapter_id": "p0b_alr_rollforward_adapter_v1",
        "phase": "stage",
        "intent_id": "p0b-stage-intent-0001",
        "intent_digest": "sha256:" + "1" * 64,
        "task_contract_digest": "sha256:" + "2" * 64,
        "context_artifact_digest": "sha256:" + "3" * 64,
        "governance_bindings": stage_governance,
        "claim_bindings": {key: "sha256:" + "4" * 64 for key in stage_claim_keys},
        "expected_source_head": config["target_head"],
        "expected_origin_main_head": config["target_head"],
        **authorized_runtime,
        "target_host": "trade-core",
        "target_environment": "trade_core_alr",
        "target_user_unit": "openclaw-alr-shadow.service",
        "require_clean_tree": True,
        "require_fresh_origin_main": True,
        "phase1_effect_receipt_digest": None,
        "phase1_closure_digest": None,
        "sealed_lineage_bundle_digest": None,
        "private_bundle_destination": private["destination"],
        "observer_requirement": "NOT_APPLICABLE",
        "approved_by": "PM",
        "approved_at": "2026-07-17T23:40:00Z",
        "expires_at": "2026-07-17T23:55:00Z",
        "typed_confirm": (
            f"p0b-alr-rollforward:stage:trade-core:{config['target_head']}:"
            "p0b-stage-intent-0001"
        ),
        "hard_stops": [f"stage-hard-stop-{index}" for index in range(8)],
    }
    stage_runtime_bindings = _runtime_bindings(
        config, stage_authorization, phase="stage"
    )
    authorized_runtime = {
        key: stage_authorization[key]
        for key in authorized_runtime
    }
    phase1["sealed_lineage"].update(
        {
            "completion_inventory_sha256": stage_runtime_bindings["inventories"][
                "completion_inventory_digest"
            ],
            "producer_inventory_sha256": stage_runtime_bindings["inventories"][
                "producer_inventory_digest"
            ],
            "ledger_post_inventory_sha256": stage_runtime_bindings["inventories"][
                "ledger_inventory_digest"
            ],
            "lane_effective_config_sha256": stage_runtime_bindings["inventories"][
                "lane_effective_config_digest"
            ],
        }
    )
    _resign_authorization(stage_authorization)
    stage_authorization_sha = hashlib.sha256(
        json.dumps(stage_authorization, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    phase1.update(
        {
            "old_head": authorized_runtime["expected_old_runtime_source_head"],
            "authorization_digest": stage_authorization["authorization_digest"],
            "stage_authorization": _binding(
                "/evidence/stage-authorization.json", stage_authorization_sha
            ),
            "stage_authorization_digest": stage_authorization[
                "authorization_digest"
            ],
            "stage_authorized_runtime": copy.deepcopy(authorized_runtime),
            "stage_runtime_bindings": _binding(
                "/evidence/stage-runtime-bindings.json",
                hashlib.sha256(
                    json.dumps(
                        stage_runtime_bindings,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            ),
            "stage_runtime_bindings_artifact_digest": stage_runtime_bindings[
                "artifact_digest"
            ],
            "completed_at_utc": "2026-07-17T23:50:00Z",
        }
    )
    phase1["sealed_lineage"].update(
        {
            "private_deps_receipt": copy.deepcopy(private["receipt"]),
            "private_deps_destination": private["destination"],
            "private_deps_manifest_sha256": private["manifest_sha256"],
        }
    )
    phase1_receipt_digest = "sha256:" + config["phase1_receipt"]["sha256"]
    phase_result_digest = _prefixed_canonical(phase1)
    ops_postcheck = {
        "schema_version": "ops_p0b_alr_postcheck_v1",
        "adapter_id": "p0b_alr_rollforward_adapter_v1",
        "phase": "stage",
        "intent_id": stage_authorization["intent_id"],
        "intent_digest": stage_authorization["intent_digest"],
        "task_contract_digest": stage_authorization["task_contract_digest"],
        "context_artifact_digest": stage_authorization["context_artifact_digest"],
        "compiled_route_digest": stage_authorization["governance_bindings"][
            "compiled_route_digest"
        ],
        "source_head": config["target_head"],
        "target_host": "trade-core",
        "target_user_unit": "openclaw-alr-shadow.service",
        "effect_receipt_digest": phase1_receipt_digest,
        "phase_result_digest": phase_result_digest,
        "observer_receipt_digest": None,
        "observed_at": "2026-07-17T23:51:00Z",
        "expires_at": "2026-07-17T23:54:00Z",
        "verified": True,
    }
    ops_postcheck["operation_digest"] = _prefixed_canonical(ops_postcheck)
    phase1_closure = {
        "schema_version": "p0b_alr_phase1_governance_closure_v1",
        "status": "PHASE1_GOVERNANCE_CLOSURE_PASS",
        "phase": "stage",
        "intent_id": stage_authorization["intent_id"],
        "intent_digest": stage_authorization["intent_digest"],
        "task_contract_digest": stage_authorization["task_contract_digest"],
        "compiled_route_digest": stage_authorization["governance_bindings"][
            "compiled_route_digest"
        ],
        "context_artifact_digest": stage_authorization["context_artifact_digest"],
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings_artifact_digest": stage_runtime_bindings[
            "artifact_digest"
        ],
        "phase1_effect_receipt_digest": phase1_receipt_digest,
        "phase_result_digest": phase_result_digest,
        "ops_postcheck": ops_postcheck,
        "ops_postcheck_digest": ops_postcheck["operation_digest"],
        "closed_at_utc": "2026-07-17T23:52:00Z",
    }
    phase1_closure["closure_digest"] = _prefixed_canonical(phase1_closure)
    phase1_closure_binding = _binding(
        "/evidence/phase1-closure.json",
        hashlib.sha256(
            json.dumps(
                phase1_closure, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
    )
    sealed_lineage_bundle = {
        "schema_version": "p0b_alr_phase1_sealed_lineage_bundle_v1",
        "target_head": config["target_head"],
        "intent_id": stage_authorization["intent_id"],
        "intent_digest": stage_authorization["intent_digest"],
        "task_contract_digest": stage_authorization["task_contract_digest"],
        "compiled_route_digest": stage_authorization["governance_bindings"][
            "compiled_route_digest"
        ],
        "context_artifact_digest": stage_authorization["context_artifact_digest"],
        "stage_authorization": copy.deepcopy(phase1["stage_authorization"]),
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings": copy.deepcopy(phase1["stage_runtime_bindings"]),
        "stage_runtime_bindings_artifact_digest": stage_runtime_bindings[
            "artifact_digest"
        ],
        "phase1_effect_receipt": copy.deepcopy(config["phase1_receipt"]),
        "phase1_effect_receipt_digest": phase1_receipt_digest,
        "phase1_closure": copy.deepcopy(phase1_closure_binding),
        "phase1_closure_digest": "sha256:" + phase1_closure_binding["sha256"],
        "private_deps_receipt": copy.deepcopy(private["receipt"]),
        "private_deps_destination": private["destination"],
        "private_deps_manifest_sha256": private["manifest_sha256"],
        "staged_board": copy.deepcopy(phase1["sealed_lineage"]["staged_board"]),
    }
    sealed_lineage_bundle["bundle_digest"] = _prefixed_canonical(
        sealed_lineage_bundle
    )
    sealed_lineage_bundle_binding = _binding(
        "/evidence/sealed-lineage.json",
        hashlib.sha256(
            json.dumps(
                sealed_lineage_bundle, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
    )
    claim_keys = {
        "p0b_effect_adapter_selection", "p0b_adapter_source", "p0b_adapter_tests",
        "p0b_base_adapter_source", "p0b_generation_apply_source", "p0b_observer_source",
        "p0b_observer_tests", "p0b_observer_dependency_source", "p0b_phase1_task_contract",
        "p0b_phase1_route", "p0b_phase1_context_artifact", "p0b_phase1_intent",
        "p0b_phase1_receipt", "p0b_phase1_closure", "p0b_sealed_lineage_bundle",
        "p0b_private_bundle_receipt", "p0b_private_bundle_destination",
        "p0b_target_source_attestation", "p0b_completion_inventory",
        "p0b_producer_inventory", "p0b_live_inventory", "p0b_protected_runtime_baseline",
        "p0b_staged_candidate_board",
        "p0b_phase_runtime_bindings", "p0b_runtime_source_binding",
        "p0b_runtime_protected_binding", "p0b_runtime_paths_binding",
        "p0b_runtime_inventories_binding", "p0b_runtime_lineage_binding",
    }
    authorization = {
        "schema_version": "p0b_alr_runtime_authorization_v1",
        "adapter_id": "p0b_alr_rollforward_adapter_v1",
        "phase": "cutover",
        "intent_id": "p0b-cutover-intent-0001",
        "intent_digest": "sha256:" + "1" * 64,
        "task_contract_digest": "sha256:" + "2" * 64,
        "context_artifact_digest": "sha256:" + "3" * 64,
        "governance_bindings": {
            key: "sha256:" + format(index, "064x")[-64:]
            for index, key in enumerate(
                (
                    "compiled_route_digest", "route_dag_digest", "pm_context_artifact_digest",
                    "pa_context_artifact_digest", "e3_context_artifact_digest",
                    "ops_preflight_context_artifact_digest", "pa_role_fragment_digest",
                    "pa_command_capture_digest", "e3_role_fragment_digest",
                    "e3_command_capture_digest", "ops_preflight_role_fragment_digest",
                    "ops_preflight_command_capture_digest", "ops_preflight_attestation_digest",
                    "pm_approval_artifact_digest", "authorized_argv_digest",
                    "protected_baseline_digest",
                ), 10
            )
        },
        "claim_bindings": {key: "sha256:" + "4" * 64 for key in claim_keys},
        "expected_source_head": config["target_head"],
        "expected_origin_main_head": config["target_head"],
        **authorized_runtime,
        "target_host": "trade-core",
        "target_environment": "trade_core_alr",
        "target_user_unit": "openclaw-alr-shadow.service",
        "require_clean_tree": True,
        "require_fresh_origin_main": True,
        "phase1_effect_receipt_digest": "sha256:" + config["phase1_receipt"]["sha256"],
        "phase1_closure_digest": "sha256:" + phase1_closure_binding["sha256"],
        "sealed_lineage_bundle_digest": (
            "sha256:" + sealed_lineage_bundle_binding["sha256"]
        ),
        "private_bundle_destination": config["private_deps"]["destination"],
        "observer_requirement": "REQUIRED_PASS",
        "approved_by": "PM",
        "approved_at": "2026-07-17T23:59:00Z",
        "expires_at": "2026-07-18T00:10:00Z",
        "typed_confirm": (
            f"p0b-alr-rollforward:cutover:trade-core:{config['target_head']}:"
            "p0b-cutover-intent-0001"
        ),
        "hard_stops": list(GOVERNANCE_CUTOVER_HARD_STOPS),
    }
    authorization["governance_bindings"].update(
        {
            "compiled_route_schema": "hybrid_execution_dag_v1",
            "context_artifact_schema": "context_artifact_v1",
            "protected_baseline_digest": stage_governance[
                "protected_baseline_digest"
            ],
            "phase_runtime_bindings_artifact_digest": "sha256:" + "c" * 64,
            "phase_runtime_bindings_path": "/evidence/cutover-runtime-bindings.json",
            "authorization_path": "/evidence/cutover-authorization.json",
        }
    )
    authorization["claim_bindings"].update(
        {
            "p0b_phase1_receipt": "sha256:" + config["phase1_receipt"]["sha256"],
            "p0b_staged_candidate_board": "sha256:" + board["source_content_sha256"],
            "p0b_private_bundle_receipt": "sha256:" + private["receipt"]["sha256"],
            "p0b_sealed_lineage_bundle": authorization[
                "sealed_lineage_bundle_digest"
            ],
            "p0b_phase1_closure": authorization["phase1_closure_digest"],
            "p0b_private_bundle_destination": "sha256:" + hashlib.sha256(
                private["destination"].encode("utf-8")
            ).hexdigest(),
            "p0b_protected_runtime_baseline": authorization[
                "governance_bindings"
            ]["protected_baseline_digest"],
            "p0b_completion_inventory": phase1["sealed_lineage"][
                "completion_inventory_sha256"
            ],
            "p0b_producer_inventory": phase1["sealed_lineage"][
                "producer_inventory_sha256"
            ],
            "p0b_live_inventory": phase1["sealed_lineage"][
                "ledger_post_inventory_sha256"
            ],
        }
    )
    authorization["governance_bindings"]["ops_preflight_observed_at"] = (
        "2026-07-17T23:58:00Z"
    )
    authorization["governance_bindings"]["ops_preflight_expires_at"] = (
        "2026-07-18T00:08:00Z"
    )
    cutover_runtime_bindings = _runtime_bindings(
        config,
        authorization,
        phase="cutover",
        phase1=phase1,
        phase1_closure=phase1_closure_binding,
        sealed_lineage_bundle=sealed_lineage_bundle_binding,
    )
    authorization["authorization_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(authorization, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    contract_projection = {
        key: value for key, value in config.items() if key != "provisional_cutover"
    }
    provisional = {
        "schema_version": "p0b_alr_current_head_rollforward_provisional_cutover_v1",
        "status": "PHASE2_PROVISIONAL_CUTOVER_READY",
        "target_head": config["target_head"],
        "phase1_receipt": copy.deepcopy(config["phase1_receipt"]),
        "cutover_authorization": copy.deepcopy(config["cutover_authorization"]),
        "cutover_authorization_digest": authorization["authorization_digest"],
        "live_board": {
            "path": board["live_path"],
            "sha256": board["source_content_sha256"],
        },
        "unit": copy.deepcopy(runtime["unit"]),
        "pin": copy.deepcopy(runtime["pin"]),
        "private_deps_receipt": copy.deepcopy(private["receipt"]),
        "private_deps_destination": private["destination"],
        "private_deps_manifest_sha256": private["manifest_sha256"],
        "active_identity": copy.deepcopy(active),
        "generation_fence": {
            key: phase1["sealed_lineage"][key]
            for key in (
                "completion_inventory_sha256",
                "producer_inventory_sha256",
                "ledger_post_inventory_sha256",
                "lane_effective_config_sha256",
            )
        },
        "observer_input_contract_sha256": hashlib.sha256(
            json.dumps(contract_projection, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    private_receipt = {
        "schema_version": "p0b_psycopg_private_bundle_stage_v1",
        "status": "APPLIED_POSTCHECK_PASS",
        "destination": private["destination"],
        "source_manifest_sha256": private["manifest_sha256"],
        "destination_manifest_sha256": private["manifest_sha256"],
        "mutation_performed": True,
        "boundaries": {
            "service_mutation": False,
            "database_access": False,
            "broker_contact": False,
            "credential_access": False,
            "subprocess_spawned": False,
            "source_repository_mutation": False,
        },
    }
    return {
        "phase1_receipt": phase1,
        "stage_authorization": stage_authorization,
        "stage_runtime_bindings": stage_runtime_bindings,
        "cutover_authorization": authorization,
        "cutover_runtime_bindings": cutover_runtime_bindings,
        "provisional_cutover": provisional,
        "private_deps_receipt": private_receipt,
        "phase1_closure": phase1_closure,
        "sealed_lineage_bundle": sealed_lineage_bundle,
    }


def test_phase_lineage_cross_binds_new_identity_board_and_private_deps() -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())

    result = module.validate_lineage_payloads(
        config, _lineage_payloads(config), now=AUTH_NOW
    )

    assert result["phase2_identity"] == config["active_identity"]
    assert result["live_board_sha256"] == config["admitted_board"]["source_content_sha256"]
    assert result["private_deps_manifest_sha256"] == config["private_deps"]["manifest_sha256"]


def test_cutover_authorization_rejects_stale_network_hard_stop_contract() -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    authorization = payloads["cutover_authorization"]
    authorization["hard_stops"] = [
        "phase-scoped P0-B ALR effect only",
        "no live/mainnet authority expansion",
        "no order/broker/decision-lease effect",
        "no unrelated service or user-manager mutation",
        "no ambient environment or secret inheritance",
        "no network, package installation, or credential read",
        "fail closed; never restore the old generation after cutover begins",
        "cutover finalizes only after OBSERVER_V2_EXACT_POSTCHECK_PASS",
    ]
    _resign_authorization(authorization)

    with pytest.raises(
        module.ObserverInputError, match="cutover_authorization_binding_invalid"
    ):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)


def test_cutover_authorization_rejects_relaxed_private_contact_contract() -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    authorization = payloads["cutover_authorization"]
    authorization["hard_stops"] = [
        item
        for item in GOVERNANCE_CUTOVER_HARD_STOPS
        if not item.startswith("no broker/private external contact")
    ]
    _resign_authorization(authorization)

    with pytest.raises(
        module.ObserverInputError, match="cutover_authorization_binding_invalid"
    ):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("closure_digest", "phase1_closure_semantics_invalid"),
        ("closure_extra", "phase1_closure_fields_invalid"),
        ("bundle_target", "sealed_lineage_bundle_semantics_invalid"),
        ("bundle_extra", "sealed_lineage_bundle_fields_invalid"),
    ),
)
def test_separate_phase1_closure_and_bundle_semantics_fail_closed(
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    if mutation == "closure_digest":
        payloads["phase1_closure"]["closure_digest"] = "sha256:" + "f" * 64
    elif mutation == "closure_extra":
        payloads["phase1_closure"]["unexpected"] = True
    elif mutation == "bundle_target":
        bundle = payloads["sealed_lineage_bundle"]
        bundle["target_head"] = "f" * 40
        bundle["bundle_digest"] = _prefixed_canonical(
            {key: value for key, value in bundle.items() if key != "bundle_digest"}
        )
    else:
        payloads["sealed_lineage_bundle"]["unexpected"] = True

    with pytest.raises(module.ObserverInputError, match=reason):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)


def test_sealed_lineage_claim_cannot_use_embedded_canonical_digest() -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    authorization = payloads["cutover_authorization"]
    embedded_digest = _prefixed_canonical(
        payloads["phase1_receipt"]["sealed_lineage"]
    )
    assert embedded_digest != authorization["sealed_lineage_bundle_digest"]
    authorization["sealed_lineage_bundle_digest"] = embedded_digest
    authorization["claim_bindings"]["p0b_sealed_lineage_bundle"] = embedded_digest
    _resign_authorization(authorization)

    with pytest.raises(
        module.ObserverInputError,
        match="runtime_bindings_cutover_lineage_invalid",
    ):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)


def test_full_lineage_accepts_arbitrary_authorized_target_head() -> None:
    module = _load_module()
    payload = _payload()
    payload["target_head"] = "d" * 40
    payload["active_identity"]["ALRSourceHead"] = "d" * 40
    payload["git_seals"]["origin_main_head"] = "d" * 40
    config = module.validate_observer_input_payload(payload)

    result = module.validate_lineage_payloads(
        config, _lineage_payloads(config), now=AUTH_NOW
    )

    assert result["phase2_identity"]["ALRSourceHead"] == "d" * 40


def _resign_authorization(authorization: dict[str, object]) -> None:
    authorization.pop("authorization_digest", None)
    authorization["authorization_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(authorization, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("old_root", "lineage_payload_set_invalid"),
        ("old_schema", "cutover_authorization_binding_invalid"),
        ("generic_context_plan", "cutover_authorization_fields_invalid"),
        ("self_digest_drift", "cutover_authorization_binding_invalid"),
        ("ops_expired", "cutover_authorization_binding_invalid"),
        ("ops_ttl_too_long", "cutover_authorization_binding_invalid"),
        ("phase1_claim_drift", "cutover_authorization_claim_binding_mismatch"),
    ],
)
def test_cutover_authorization_ambiguity_fails_closed(
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    authorization = payloads["cutover_authorization"]
    observed_now = AUTH_NOW
    if mutation == "old_root":
        payloads["phase2_approval"] = payloads.pop("cutover_authorization")
    elif mutation == "old_schema":
        authorization["schema_version"] = "p0b_alr_current_head_rollforward_approval_v1"
        _resign_authorization(authorization)
    elif mutation == "generic_context_plan":
        authorization["context_plan"] = {"approved": True}
        _resign_authorization(authorization)
    elif mutation == "self_digest_drift":
        authorization["authorization_digest"] = "sha256:" + "f" * 64
    elif mutation == "ops_expired":
        observed_now = datetime(2026, 7, 18, 0, 9, tzinfo=timezone.utc)
    elif mutation == "ops_ttl_too_long":
        authorization["governance_bindings"]["ops_preflight_expires_at"] = (
            "2026-07-18T00:20:00Z"
        )
        authorization["expires_at"] = "2026-07-18T00:20:00Z"
        _resign_authorization(authorization)
    else:
        authorization["claim_bindings"]["p0b_phase1_receipt"] = (
            "sha256:" + "f" * 64
        )
        _resign_authorization(authorization)

    with pytest.raises(module.ObserverInputError, match=reason):
        module.validate_lineage_payloads(config, payloads, now=observed_now)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("stage_binding_hash", "phase1_receipt_lineage_mismatch"),
        ("stage_projection", "phase1_receipt_lineage_mismatch"),
        ("stage_self_digest", "stage_authorization_binding_invalid"),
        ("cutover_old_pin", "runtime_bindings_protected_invalid"),
        ("cutover_source_tree", "runtime_bindings_source_invalid"),
        ("cutover_source_attestation", "runtime_bindings_source_invalid"),
        ("cutover_protected_baseline", "runtime_bindings_protected_invalid"),
    ],
)
def test_stage_to_cutover_authorization_drift_fails_closed(
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    phase1 = payloads["phase1_receipt"]
    stage = payloads["stage_authorization"]
    cutover = payloads["cutover_authorization"]
    if mutation == "stage_binding_hash":
        phase1["stage_authorization"]["sha256"] = "f" * 64
    elif mutation == "stage_projection":
        phase1["stage_authorized_runtime"]["expected_old_pin_digest"] = (
            "sha256:" + "f" * 64
        )
    elif mutation == "stage_self_digest":
        stage["authorization_digest"] = "sha256:" + "f" * 64
    elif mutation == "cutover_old_pin":
        cutover["expected_old_pin_digest"] = "sha256:" + "f" * 64
        _resign_authorization(cutover)
    elif mutation == "cutover_source_tree":
        cutover["expected_source_tree_digest"] = "sha256:" + "f" * 64
        _resign_authorization(cutover)
    elif mutation == "cutover_source_attestation":
        cutover["claim_bindings"]["p0b_target_source_attestation"] = (
            "sha256:" + "f" * 64
        )
        _resign_authorization(cutover)
    else:
        cutover["governance_bindings"]["protected_baseline_digest"] = (
            "sha256:" + "f" * 64
        )
        cutover["claim_bindings"]["p0b_protected_runtime_baseline"] = (
            "sha256:" + "f" * 64
        )
        _resign_authorization(cutover)

    with pytest.raises(module.ObserverInputError, match=reason):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("phase", "runtime_bindings_authority_mismatch"),
        ("expired", "runtime_bindings_time_invalid"),
        ("artifact_digest", "runtime_bindings_artifact_digest_invalid"),
        ("section_digest", "runtime_bindings_section_claim_invalid"),
        ("remote_origin", "runtime_bindings_source_invalid"),
    ],
)
def test_cutover_runtime_binding_ambiguity_fails_closed(
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    runtime = payloads["cutover_runtime_bindings"]
    if mutation == "phase":
        runtime["phase"] = "stage"
    elif mutation == "expired":
        runtime["expires_at"] = "2026-07-18T00:03:00Z"
    elif mutation == "artifact_digest":
        runtime["artifact_digest"] = "sha256:" + "f" * 64
    elif mutation == "section_digest":
        runtime["section_claims"]["source_attestation"]["digest"] = (
            "sha256:" + "f" * 64
        )
        runtime["artifact_digest"] = _prefixed_canonical(
            {key: value for key, value in runtime.items() if key != "artifact_digest"}
        )
        payloads["cutover_authorization"]["governance_bindings"][
            "phase_runtime_bindings_artifact_digest"
        ] = runtime["artifact_digest"]
        payloads["cutover_authorization"]["claim_bindings"][
            "p0b_phase_runtime_bindings"
        ] = runtime["artifact_digest"]
        _resign_authorization(payloads["cutover_authorization"])
    else:
        runtime["source_attestation"]["source"]["remote_origin_main"] = "f" * 40
        source_digest = _prefixed_canonical(runtime["source_attestation"])
        runtime["section_claims"]["source_attestation"]["digest"] = source_digest
        auth = payloads["cutover_authorization"]
        auth["claim_bindings"]["p0b_runtime_source_binding"] = source_digest
        runtime["artifact_digest"] = _prefixed_canonical(
            {key: value for key, value in runtime.items() if key != "artifact_digest"}
        )
        auth["governance_bindings"]["phase_runtime_bindings_artifact_digest"] = (
            runtime["artifact_digest"]
        )
        auth["claim_bindings"]["p0b_phase_runtime_bindings"] = runtime[
            "artifact_digest"
        ]
        _resign_authorization(auth)

    with pytest.raises(module.ObserverInputError, match=reason):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)


def _base_pass_result(config: dict[str, object]) -> dict[str, object]:
    board = config["admitted_board"]
    cycles = []
    for index in (1, 2):
        cycles.append(
            {
                "lane_success_event_id": f"00000000-0000-4000-8000-{index:012d}",
                "lane_success_recorded_at": f"2026-07-18T00:0{index}:10Z",
                "cursor": {
                    "source_ts": f"2026-07-18T00:0{index}:00Z",
                    "source_scan_id": f"scan-{index}",
                    "source_hash": str(index) * 64,
                    "source_key": f"scan-{index}|2026-07-18T00:0{index}:00Z",
                },
                "notification": {
                    "event_id": f"10000000-0000-4000-8000-{index:012d}",
                    "recorded_at": f"2026-07-18T00:0{index}:05Z",
                    "notification_ts_ms": 1784332800000 + index,
                },
                "decision": {"artifact_hash": chr(96 + index) * 64},
                "health": {"snapshot_hash": chr(98 + index) * 64},
            }
        )
    return {
        "schema_version": "p0b_alr_two_natural_cycle_observer_v1",
        "status": "PASS",
        "reason_codes": [],
        "target_head": TARGET_HEAD,
        "trust_root": {
            "board_source_content_sha256": board["source_content_sha256"],
            "board_hash": board["board_hash"],
            "board_audit_hash": board["audit_hash"],
            "selection_hash": board["selection_hash"],
            "candidate_set_hash": board["candidate_set_hash"],
        },
        "runtime": {
            "source_head": TARGET_HEAD,
            "identity": copy.deepcopy(config["active_identity"]),
            "nrestarts": 0,
        },
        "session": {
            "session_id": "11111111-1111-4111-8111-111111111111",
            "started_at_utc": "2026-07-18T00:00:01Z",
            "post_pin_unique_open_session": True,
        },
        "transaction": {
            "start": {
                "transaction_read_only": "on",
                "transaction_isolation": "repeatable read",
                "xid_assigned": False,
            },
            "final": {
                "tuples_inserted": 0,
                "tuples_updated": 0,
                "tuples_deleted": 0,
                "xid_assigned": False,
            },
            "rolled_back": True,
        },
        "cycle_count": 2,
        "cycles": cycles,
        "claims": {
            "two_natural_cycles_observed": True,
            "trading_or_order_authority_claimed": False,
            "serving_or_promotion_claimed": False,
        },
        "boundaries": {
            "pg_readonly_effect_guard_passed": True,
            "pg_tuple_write_observed": False,
            "credential_content_output": False,
        },
    }


def test_final_projection_accepts_exactly_two_post_not_before_notification_cycles() -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())

    result = module.validate_base_pass_result(config, _base_pass_result(config))

    assert result["cycle_count"] == 2
    assert result["cycles_distinct"] is True
    assert result["all_cycles_post_observer_not_before"] is True
    assert result["runtime_identity"] == config["active_identity"]


def _startup_proof(config: dict[str, object]) -> dict[str, object]:
    board = config["admitted_board"]
    return {
        "schema_version": "p0b_alr_startup_reconciliation_temporal_v1",
        "session_id": "11111111-1111-4111-8111-111111111111",
        "session_started_at_utc": "2026-07-18T00:00:01Z",
        "decision_row_count": 1,
        "decision": {
            "artifact_hash": "d" * 64,
            "created_at_utc": "2026-07-18T00:00:02Z",
            "board_generated_at_utc": board["generated_at_utc"],
            "source_head": TARGET_HEAD,
            "source_content_sha256": board["source_content_sha256"],
            "board_hash": board["board_hash"],
            "audit_hash": board["audit_hash"],
            "selection_hash": board["selection_hash"],
            "candidate_set_hash": board["candidate_set_hash"],
            "no_authority": True,
        },
        "first_notification_received_row_count": 1,
        "first_notification_received": {
            "event_id": "20000000-0000-4000-8000-000000000001",
            "recorded_at_utc": "2026-07-18T00:00:03Z",
        },
        "same_session": True,
        "pg_explicit_trigger_claimed": False,
    }


def test_startup_reconciliation_combines_exact_source_order_and_temporal_row() -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    source = (HERE.parent.parent / "program_code/ml_training/alr_event_consumer.py").read_bytes()

    result = module.validate_startup_reconciliation_proof(
        config,
        source,
        _startup_proof(config),
    )

    assert result["startup_reconciliation_proof_basis"] == (
        "SOURCE_ORDER_PLUS_SESSION_TEMPORAL_ATTESTATION"
    )
    assert result["pg_explicit_trigger_claimed"] is False
    assert result["decision_strictly_before_first_notification_received"] is True


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("old_phase1", "stage_authorization_binding_invalid"),
        ("wrong_board", "provisional_cutover_lineage_mismatch"),
        ("old_private_receipt", "private_deps_receipt_lineage_mismatch"),
    ],
)
def test_old_receipt_or_wrong_board_lineage_fails_closed(
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    if mutation == "old_phase1":
        payloads["phase1_receipt"]["target_head"] = "275901baa09656e842f14b11e94c00f9bfe0c380"
    elif mutation == "wrong_board":
        payloads["provisional_cutover"]["live_board"]["sha256"] = "f" * 64
    else:
        payloads["private_deps_receipt"]["destination_manifest_sha256"] = "f" * 64

    with pytest.raises(module.ObserverInputError, match=reason):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("startup_as_cycle", "base_cycle_notification_required"),
        ("duplicate_cycle", "base_cycles_not_distinct"),
        ("pre_invocation", "base_cycle_before_observer_bound"),
        ("authority", "observer_authority_grant_present"),
        ("service_identity_drift", "base_runtime_identity_drift"),
        ("pg_timeout", "base_observation_not_pass"),
        ("pg_reconnect", "base_observation_not_pass"),
    ],
)
def test_cycle_authority_service_and_pg_ambiguity_fail_closed(
    mutation: str,
    reason: str,
) -> None:
    module = _load_module()
    payload = _payload()
    if mutation == "authority":
        payload["no_authority"]["order"] = True
        with pytest.raises(module.ObserverInputError, match=reason):
            module.validate_observer_input_payload(payload)
        return
    config = module.validate_observer_input_payload(payload)
    result = _base_pass_result(config)
    if mutation == "startup_as_cycle":
        result["cycles"][0]["notification"] = None
    elif mutation == "duplicate_cycle":
        result["cycles"][1] = copy.deepcopy(result["cycles"][0])
    elif mutation == "pre_invocation":
        result["cycles"][0]["cursor"]["source_ts"] = "2026-07-17T23:59:59Z"
    elif mutation == "service_identity_drift":
        result["runtime"]["identity"]["InvocationID"] = "e" * 32
    elif mutation == "pg_timeout":
        result["status"] = "UNVERIFIED"
        result["reason_codes"] = ["readonly_transaction_unavailable"]
    else:
        result["status"] = "UNVERIFIED"
        result["reason_codes"] = ["pg_reconnect_attempt_forbidden"]

    with pytest.raises(module.ObserverInputError, match=reason):
        module.validate_base_pass_result(config, result)


@pytest.mark.parametrize("mutation", ["equal_time", "wrong_source", "explicit_pg_trigger"])
def test_startup_temporal_or_source_ambiguity_fails_closed(mutation: str) -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    source = (HERE.parent.parent / "program_code/ml_training/alr_event_consumer.py").read_bytes()
    proof = _startup_proof(config)
    if mutation == "equal_time":
        proof["decision"]["created_at_utc"] = proof["first_notification_received"][
            "recorded_at_utc"
        ]
    elif mutation == "wrong_source":
        source += b"\n"
    else:
        proof["pg_explicit_trigger_claimed"] = True

    with pytest.raises(module.ObserverInputError):
        module.validate_startup_reconciliation_proof(config, source, proof)


def test_exact_hash_pinned_base_observer_loads_without_import_path_trust() -> None:
    module = _load_module()

    base = module.load_exact_base_observer()

    assert base.TARGET_HEAD == "275901baa09656e842f14b11e94c00f9bfe0c380"
    assert callable(base.run_observation)


def test_startup_sql_is_bounded_read_only_and_requires_pre_notification_decision() -> None:
    module = _load_module()
    sql = module.STARTUP_RECONCILIATION_SQL

    assert "LIMIT 2" in sql
    assert "LIMIT 1" in sql
    assert "event_kind='NOTIFICATION_RECEIVED'" in sql
    assert "artifact.created_at < notification.recorded_at" in sql
    assert all(token not in sql.upper() for token in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP "))


def test_static_surface_has_no_runtime_mutation_or_credential_output() -> None:
    source = MODULE_PATH.read_text()
    tree = ast.parse(source)
    subprocess_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]

    assert len(subprocess_calls) == 1
    assert subprocess_calls[0].func.attr == "run"
    assert "p0b_alr_recovery_transaction_v2.py" not in source
    assert "load_exact_recovery_module" not in source
    assert "target/codex-context" not in source
    assert "daemon-reload" not in source
    assert "reset-failed" not in source
    assert "subprocess.Popen" not in source
    assert "os.system" not in source
    assert ".commit(" not in source
    assert "password" not in source.lower()
    assert "PG_EXPLICIT_TRIGGER" not in source


def test_readonly_runtime_shim_rejects_git_and_systemd_effect_commands(
    monkeypatch,
) -> None:
    module = _load_module()

    class ObserverUnverified(Exception):
        pass

    class ObserverFail(Exception):
        pass

    git_prefix = (
        "/usr/bin/git",
        "-C",
        "/home/ncyu/BybitOpenClaw/srv",
        "--no-optional-locks",
    )
    fake_base = module.types.SimpleNamespace(
        RECOVERY_BASE_SYSTEM_ENV={"PATH": "/usr/bin:/bin"},
        RECOVERY_REPO_PATH=Path("/home/ncyu/BybitOpenClaw/srv"),
        RECOVERY_GIT_COMMAND_PREFIX=git_prefix,
        RECOVERY_GIT_CONFIG_INVENTORY_ARGS=("config", "--local", "--list"),
        RECOVERY_HARDENED_GIT_ENV={"PATH": "/usr/bin:/bin"},
        ObserverUnverified=ObserverUnverified,
        ObserverFail=ObserverFail,
    )
    observed: list[list[str]] = []

    def fake_run(command, **_kwargs):
        observed.append(list(command))
        return module.subprocess.CompletedProcess(command, 0, "abc\n", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    recovery = module.build_readonly_runtime_module(fake_base, "d" * 40)

    allowed = recovery.base.RecoveryRuntime.run(
        [*git_prefix, "rev-parse", "origin/main"]
    )
    assert allowed.stdout == "abc\n"
    with pytest.raises(ObserverUnverified, match="not_allowlisted"):
        recovery.base.RecoveryRuntime.run([*git_prefix, "fetch", "origin"])
    with pytest.raises(ObserverUnverified, match="not_allowlisted"):
        recovery.base.RecoveryRuntime.run(
            [module.SYSTEMD, "--user", "restart", module.UNIT_NAME]
        )
    assert observed == [[*git_prefix, "rev-parse", "origin/main"]]


def test_cli_requires_isolated_no_bytecode_and_exact_argument_order(capsys) -> None:
    module = _load_module()

    assert module.main([]) == 5

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "UNVERIFIED"
    assert result["reason_codes"] == ["isolated_no_bytecode_runtime_required"]


def test_final_phase2_receipt_input_is_forbidden_to_prevent_circular_pass() -> None:
    module = _load_module()
    payload = _payload()
    payload["phase2_receipt"] = payload.pop("provisional_cutover")

    with pytest.raises(module.ObserverInputError, match="observer_input_fields_invalid"):
        module.validate_observer_input_payload(payload)


def test_provisional_binds_projection_without_hash_cycle() -> None:
    module = _load_module()
    first = module.validate_observer_input_payload(_payload())
    second_payload = _payload()
    second_payload["provisional_cutover"]["sha256"] = "e" * 64
    second = module.validate_observer_input_payload(second_payload)

    assert module.observer_input_contract_sha256(first) == (
        module.observer_input_contract_sha256(second)
    )
    assert first["provisional_cutover"]["sha256"] != second["provisional_cutover"]["sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "final_status",
        "fence_drift",
        "input_contract_drift",
        "authorization_digest_drift",
        "authorization_binding_drift",
    ],
)
def test_provisional_cutover_ambiguity_fails_closed(mutation: str) -> None:
    module = _load_module()
    config = module.validate_observer_input_payload(_payload())
    payloads = _lineage_payloads(config)
    provisional = payloads["provisional_cutover"]
    if mutation == "final_status":
        provisional["status"] = "PHASE2_APPLIED_POSTCHECK_PASS"
    elif mutation == "fence_drift":
        provisional["generation_fence"]["ledger_post_inventory_sha256"] = (
            "sha256:" + "1" * 64
        )
    elif mutation == "input_contract_drift":
        provisional["observer_input_contract_sha256"] = "1" * 64
    elif mutation == "authorization_digest_drift":
        provisional["cutover_authorization_digest"] = "sha256:" + "1" * 64
    else:
        provisional["cutover_authorization"]["sha256"] = "1" * 64

    with pytest.raises(module.ObserverInputError, match="provisional_cutover_lineage_mismatch"):
        module.validate_lineage_payloads(config, payloads, now=AUTH_NOW)
