from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from ml_training.alr_scanner_statistical_experiment import (
    AlrScannerStatisticalExperimentError,
    build_candidate_aware_learning_projection,
    build_scanner_statistical_experiment,
    compute_scanner_statistical_experiment_hash,
    validate_scanner_statistical_experiment,
)
from ml_training.alr_operational_repository import (
    build_candidate_learning_projection_plan,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _cycle(
    ordinal: int,
    *,
    symbols: list[str],
    added: list[str],
) -> dict[str, object]:
    return {
        "source_hash": f"{ordinal:064x}",
        "source_key": f"scan-{ordinal}|2026-07-09T12:0{ordinal}:00Z",
        "source_ts": f"2026-07-09T12:0{ordinal}:00Z",
        "canonical_payload": {
            "ts": f"2026-07-09T12:0{ordinal}:00Z",
            "scan_id": f"scan-{ordinal}",
            "active_symbols": symbols,
            "added": added,
            "removed": [],
            "rejected_count": 0,
            "scan_duration_ms": 5,
            "candidates": [{"symbol": symbol, "final_score": ordinal} for symbol in symbols],
            "config": {"scanner_revision": "v1"},
        },
    }


def _cycles() -> list[dict[str, object]]:
    return [
        _cycle(1, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=["ALPHAUSDT"]),
        _cycle(2, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=[]),
        _cycle(3, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=[]),
        _cycle(4, symbols=["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"], added=[]),
    ]


def _candidate_policy() -> dict[str, object]:
    body: dict[str, object] = {
        "decision_ts_s": 1_783_684_800,
        "as_of_utc_date": "2026-07-10",
        "algorithm_version": "candidate_learning_arbiter_v2",
        "tie_break_version": "candidate_learning_tie_break_v1",
        "q18_scale": 18,
        "thresholds": {
            "e1_n_eff_min": 30,
            "e2_utc_days_min": 5,
            "e3_top_day_share_max": "0.5",
            "e4_censored_share_max": "0.3",
        },
        "row_budget": 10_000,
        "byte_budget": 1_000_000,
        "collection_window_days": 7,
        "max_new_entries_per_window": 70,
        "cooldown_seconds": 1_800,
        "unknown_portfolio_penalty": "1",
    }
    stable_config = {
        key: value
        for key, value in body.items()
        if key not in {"decision_ts_s", "as_of_utc_date"}
    }
    body["policy_config_hash"] = _sha(stable_config)
    return body


def _candidate_row(*, n_eff: int = 30) -> dict[str, object]:
    target_regime_context = {
        "label": "bull|high_vol|liquid",
        "utc_date": "2026-07-09",
        "point_in_time": "D-1",
        "source_complete": True,
        "source_hash": "7" * 64,
        "classifier_hash": "8" * 64,
    }
    target_regime = {
        **target_regime_context,
        "hash": _sha(target_regime_context),
    }
    daily_buckets = [
        {
            "utc_date": f"2026-07-{day:02d}",
            "scan_complete": True,
            "distinct_entries": 5,
        }
        for day in range(3, 10)
    ]
    resource_payload: dict[str, object] = {
        "daily_buckets": daily_buckets,
        "estimated_rows_scanned": 700,
        "predicted_canonical_bytes": 7_000,
        "zero_resource_attested": False,
    }
    resource = {
        **resource_payload,
        "resource_estimator_hash": hashlib.sha256(
            json.dumps(
                resource_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    regime_entry_counts = {
        f"{trend}|{volatility}|{liquidity}": 0
        for trend in ("bear", "neutral", "bull")
        for volatility in ("low_vol", "mid_vol", "high_vol")
        for liquidity in ("liquid", "thin")
    }
    regime_entry_counts["unknown"] = 0
    regime_entry_counts["bull|high_vol|liquid"] = n_eff
    candidate = {
        "schema_version": "alr_candidate_arbiter_input_v2",
        "identity": {
            "strategy_name": "grid_trading",
            "strategy_version": "7" * 40,
            "config_hash": "1" * 64,
            "symbol": "ALPHAUSDT",
            "side": "Buy",
            "horizon_minutes": 60,
            "target_regime": target_regime,
            "engine_mode": "shadow",
            "evidence_engine_mode": "demo",
            "venue": "bybit",
            "product": "linear_perpetual",
        },
        "context_hashes": {
            "data": "3" * 64,
            "evidence": "4" * 64,
            "cost": "5" * 64,
            "portfolio": "6" * 64,
        },
        "cost_evidence": {
            "schema_version": "alr_candidate_cost_evidence_v2",
            "basis": "expected_slippage_mean_abs_v1",
            "source_payload_sha256": "9" * 64,
            "source_asof_utc": "2026-07-10T11:00:00+00:00",
            "normalized_projection_sha256": "b" * 64,
            "max_age_hours": 48,
            "fee_floor_bps": 11.0,
            "mean_abs_source": {
                "scope": "GLOBAL",
                "symbol": None,
                "sample_count": 100,
                "mean_abs_bps": 2.0,
            },
            "tail_source": {
                "scope": "GLOBAL",
                "symbol": None,
                "sample_count": 100,
                "tail_bps": 8.0,
                "tail_metric": "cvar90",
            },
        },
        "quality": {
            "hash_ok": True,
            "integrity_ok": True,
            "freshness_ok": True,
            "censored_share": 0.1,
            "cost_recomputable_share": 1.0,
            "unknown_regime_share": 0.0,
            "replica_inconsistency_count": 0,
            "cluster_variance_clean": True,
            "hidden_oos_consumed": False,
            "legacy_optimistic_cost_present": False,
            "top_day_share": 0.4,
        },
        "evidence": {
            "n_eff": n_eff,
            "utc_day_count": 5,
            "mean_net_e": -10.0,
            "day_cluster_variance": 4.0,
            "cluster_se": 2.0,
            "cluster_count": 5,
            "proof_stage": 1,
            "completed_proof_stages": [0, 1],
            "next_gap": {
                "kind": "NONE" if n_eff >= 30 else "LOCAL_PASSIVE",
                "code": "DISTINCT_ENTRY_METRICS",
            },
            "raw_attempt_count": n_eff,
            "regime_entry_counts": regime_entry_counts,
        },
        "resource": resource,
        "portfolio": {
            "sector_exposure_share": "0.1",
            "strategy_active_target_share": "0.2",
            "beta_to_portfolio": "0.3",
        },
    }
    candidate["arbiter_input_hash"] = _sha(candidate)
    return candidate


def _rehash_arbiter_input(candidate: dict[str, object]) -> dict[str, object]:
    candidate["schema_version"] = "alr_candidate_arbiter_input_v2"
    candidate.pop("arbiter_input_hash", None)
    candidate["arbiter_input_hash"] = _sha(candidate)
    return candidate


def _board_row(candidate: dict[str, object] | None = None) -> dict[str, object]:
    typed = _rehash_arbiter_input(copy.deepcopy(candidate or _candidate_row()))
    identity = typed["identity"]
    target_regime = identity["target_regime"]
    raw_family_identity = {
        "strategy_name": identity["strategy_name"],
        "strategy_version": identity["strategy_version"],
        "strategy_config_hash": identity["config_hash"],
        "symbol": identity["symbol"],
        "side": identity["side"],
        "horizon_minutes": identity["horizon_minutes"],
        "venue": identity["venue"],
        "product": identity["product"],
        "evidence_engine_mode": identity["evidence_engine_mode"],
    }
    stable_projection = {
        "strategy_version": raw_family_identity["strategy_version"],
        "strategy_config_hash": raw_family_identity["strategy_config_hash"],
        "target_regime_context": {
            key: target_regime[key]
            for key in ("label", "utc_date", "point_in_time")
        },
        "target_regime_hash": target_regime["hash"],
        "venue": raw_family_identity["venue"],
        "product": raw_family_identity["product"],
        "evidence_engine_mode": raw_family_identity["evidence_engine_mode"],
        "context_hashes": typed["context_hashes"],
        "resource": typed["resource"],
        "portfolio": typed["portfolio"],
        "proof": {
            "proof_stage": typed["evidence"]["proof_stage"],
            "completed_proof_stages": typed["evidence"][
                "completed_proof_stages"
            ],
            "next_gap": typed["evidence"]["next_gap"],
        },
        "hidden_oos_consumed": typed["quality"]["hidden_oos_consumed"],
    }
    eligible = typed["evidence"]["n_eff"] >= 30
    blockers = [] if eligible else [
        "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT",
        "PROOF_GAP_OPEN",
    ]
    return {
        "schema_version": "cost_gate_learning_candidate_v2",
        "candidate_id": _sha(
            {
                "schema_version": "cost_gate_learning_candidate_v2",
                "identity": identity,
                "context_hashes": typed["context_hashes"],
            }
        ),
        "candidate_family_key": _sha(
            {
                "schema_version": "candidate_learning_family_v2",
                "identity": raw_family_identity,
            }
        ),
        "stable_cohort_hash": _sha(
            {
                "identity": raw_family_identity,
                "stable_projection": stable_projection,
            }
        ),
        "candidate_identity": {
            **raw_family_identity,
            "target_regime_context": {
                key: value
                for key, value in target_regime.items()
                if key != "hash"
            },
            "target_regime_hash": target_regime["hash"],
            "engine_mode": identity["engine_mode"],
        },
        "identity_complete": True,
        "arbiter_input": typed,
        "arbiter_input_complete": True,
        "selection_eligible": eligible,
        "blockers": blockers,
        "qualified_entry_ts_missing_row_count": 0,
        "qualified_invalid_outcome_row_count": 0,
        "data_integrity_suspect": False,
        "tail_cost_recomputable_share": 1.0,
        "invalid_lineage_exact_cohort_row_count": 0,
        "invalid_lineage_identity_family_row_count": 0,
        "duplicate_event_hash_outcome_conflict_row_count": 0,
        "duplicate_event_hash_cohort_conflict_row_count": 0,
        "lineage_blocker_reason_counts": {},
    }


_SELECTION_FIELDS = (
    "schema_version",
    "candidate_id",
    "candidate_family_key",
    "stable_cohort_hash",
    "candidate_identity",
    "identity_complete",
    "arbiter_input",
    "arbiter_input_complete",
    "selection_eligible",
    "blockers",
)


def _semantic_board_row(row: dict[str, object]) -> dict[str, object]:
    return {field: row[field] for field in _SELECTION_FIELDS}


def _evidence_snapshot(
    *,
    rows: list[dict[str, object]] | None = None,
    status: str = "READY",
) -> dict[str, object]:
    ready = status == "READY"
    candidate_rows = rows if rows is not None else ([_board_row()] if ready else [])
    semantic_rows = sorted(
        [_semantic_board_row(row) for row in candidate_rows],
        key=lambda row: (str(row["candidate_id"]), _sha(row)),
    )
    snapshot = {
        "schema_version": "alr_candidate_evidence_snapshot_v2",
        "source_status": status,
        "generated_at": "2026-07-10T11:59:00Z" if ready else None,
        "evaluated_at": "2026-07-10T12:00:00Z",
        "source_content_sha256": "7" * 64 if ready else None,
        "board_hash": "8" * 64 if ready else None,
        "audit_hash": "9" * 64 if ready else None,
        "selection_hash": _sha(
            {
                "schema_version": "cost_gate_learning_candidate_selection_v2",
                "candidate_rows": semantic_rows,
            }
        ) if ready else None,
        "candidate_set_hash": _sha(semantic_rows) if ready else None,
        "candidate_universe_complete": ready,
        "candidate_rows": candidate_rows,
        "selection_allowed": ready,
        "latest_alias_used": False,
    }
    snapshot["snapshot_hash"] = _sha(snapshot)
    return snapshot


def test_builds_pit_research_experiment_and_deferred_challenger() -> None:
    result = build_scanner_statistical_experiment(
        source_head="a" * 40,
        cycles=_cycles(),
    )

    validation = validate_scanner_statistical_experiment(result)
    assert validation.valid is True
    assert result["learning_target"]["selected_target"]["candidate_scope"]["symbol"] == "ALPHAUSDT"
    assert result["pit_dataset_manifest"]["verdict"] == "research_only"
    assert result["pit_dataset_manifest"]["point_in_time"] is True
    assert result["pit_dataset_manifest"]["future_data_allowed"] is False
    assert result["statistical_experiment"]["statistical_experiment_performed"] is True
    assert result["statistical_experiment"]["model_training_performed"] is False
    assert result["candidate_artifact"]["after_cost_evaluation"]["status"] == "DEFER_EVIDENCE"
    assert result["candidate_artifact"]["serving_ready"] is False
    assert result["candidate_artifact"]["promotion_ready"] is False
    assert result["experiment_hash"] == compute_scanner_statistical_experiment_hash(result)
    assert {item["artifact_kind"] for item in result["artifacts"]} == {
        "learning_target",
        "pit_dataset",
        "statistical_experiment",
        "candidate_artifact",
        "defer_evidence",
    }
    assert all(value is False for value in result["no_authority"].values())
    assert all(value == 0 for value in result["authority_counters"].values())


def test_is_deterministic_across_input_order() -> None:
    forward = build_scanner_statistical_experiment(source_head="b" * 40, cycles=_cycles())
    reverse = build_scanner_statistical_experiment(
        source_head="b" * 40,
        cycles=list(reversed(_cycles())),
    )

    assert forward["experiment_hash"] == reverse["experiment_hash"]
    assert forward["run"]["source_set_hash"] == reverse["run"]["source_set_hash"]


def test_defer_fingerprint_tracks_semantic_evidence_not_source_identity() -> None:
    first = build_scanner_statistical_experiment(
        source_head="b" * 40,
        cycles=_cycles(),
    )
    equivalent_cycles = copy.deepcopy(_cycles())
    for ordinal, cycle in enumerate(equivalent_cycles, start=11):
        cycle["source_hash"] = f"{ordinal:064x}"
        cycle["source_key"] = str(cycle["source_key"]).replace(
            "2026-07-09", "2026-07-10"
        )
        cycle["source_ts"] = str(cycle["source_ts"]).replace(
            "2026-07-09", "2026-07-10"
        )
        cycle["canonical_payload"]["ts"] = str(
            cycle["canonical_payload"]["ts"]
        ).replace("2026-07-09", "2026-07-10")
    equivalent = build_scanner_statistical_experiment(
        source_head="b" * 40,
        cycles=equivalent_cycles,
    )
    different_head = build_scanner_statistical_experiment(
        source_head="c" * 40,
        cycles=equivalent_cycles,
    )

    changed_cycles = copy.deepcopy(equivalent_cycles)
    changed_cycles[1]["canonical_payload"]["added"] = ["ALPHAUSDT"]
    changed = build_scanner_statistical_experiment(
        source_head="b" * 40,
        cycles=changed_cycles,
    )
    control_changed_cycles = copy.deepcopy(equivalent_cycles)
    control_changed_cycles[1]["canonical_payload"]["added"] = ["BETAUSDT"]
    control_changed = build_scanner_statistical_experiment(
        source_head="b" * 40,
        cycles=control_changed_cycles,
    )
    config_changed_cycles = copy.deepcopy(equivalent_cycles)
    config_changed_cycles[1]["canonical_payload"]["config"] = {
        "scanner_revision": "v2"
    }
    config_changed = build_scanner_statistical_experiment(
        source_head="b" * 40,
        cycles=config_changed_cycles,
    )

    fingerprint = first["candidate_artifact"]["decision_fingerprint"]
    assert equivalent["candidate_artifact"]["decision_fingerprint"] == fingerprint
    assert equivalent["defer_evidence"]["decision_fingerprint"] == fingerprint
    assert different_head["candidate_artifact"]["decision_fingerprint"] != fingerprint
    assert changed["candidate_artifact"]["decision_fingerprint"] != fingerprint
    assert (
        control_changed["candidate_artifact"]["decision_fingerprint"]
        != fingerprint
    )
    assert (
        config_changed["candidate_artifact"]["decision_fingerprint"]
        != fingerprint
    )
    components = first["candidate_artifact"]["decision_fingerprint_components"]
    assert components["candidate_identity"]["symbol"] == "ALPHAUSDT"
    assert components["regime_context"]["measurement"] == "recurrence_not_return"
    assert components["semantic_evidence"]["scanner_occurrences"] == 4
    assert components["blockers"]
    assert components["reevaluation_policy"]["max_suppression_seconds"] == 1800
    assert len(components["decision_policy_hash"]) == 64


def test_rejects_duplicate_sources_and_missing_candidates() -> None:
    duplicate = _cycles()
    duplicate.append(dict(duplicate[0]))
    with pytest.raises(AlrScannerStatisticalExperimentError, match="source_hash_duplicate"):
        build_scanner_statistical_experiment(source_head="c" * 40, cycles=duplicate)

    no_candidates = _cycles()
    no_candidates[0] = _cycle(1, symbols=[], added=[])
    with pytest.raises(AlrScannerStatisticalExperimentError, match="source_candidates_empty"):
        build_scanner_statistical_experiment(source_head="c" * 40, cycles=no_candidates)


def test_rejects_tampered_after_cost_or_authority_claim() -> None:
    result = build_scanner_statistical_experiment(source_head="d" * 40, cycles=_cycles())
    result["candidate_artifact"]["after_cost_evaluation"]["status"] = "EVIDENCE_READY"
    result["experiment_hash"] = compute_scanner_statistical_experiment_hash(result)

    validation = validate_scanner_statistical_experiment(result)
    assert validation.valid is False
    assert validation.reason == "after_cost_status_invalid"


def test_rejects_tampered_defer_decision_fingerprint() -> None:
    result = build_scanner_statistical_experiment(
        source_head="d" * 40,
        cycles=_cycles(),
    )
    result["candidate_artifact"]["decision_fingerprint_components"][
        "blockers"
    ] = []
    result["experiment_hash"] = compute_scanner_statistical_experiment_hash(result)

    validation = validate_scanner_statistical_experiment(result)

    assert validation.valid is False
    assert validation.reason == "decision_fingerprint_mismatch"


def test_source_is_pure_and_has_no_runtime_or_training_imports() -> None:
    source_path = Path(__file__).resolve().parents[1] / "alr_scanner_statistical_experiment.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_imports = {
        "os",
        "subprocess",
        "socket",
        "psycopg2",
        "psycopg",
        "requests",
        "httpx",
        "numpy",
        "sklearn",
        "torch",
    }
    forbidden_calls = {"connect", "request", "run", "Popen", "system", "remove", "unlink"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {alias.name for alias in node.names} & forbidden_imports
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls


def test_candidate_aware_bridge_selects_complete_identity_without_fake_run() -> None:
    projection = build_candidate_aware_learning_projection(
        source_head="a" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    plan = build_candidate_learning_projection_plan(projection)
    assert plan["decision_code"] == "QUALIFIED_CANDIDATE_SELECTED"
    assert projection["schema_version"] == "alr_candidate_learning_projection_v2"
    assert projection["decision"]["schema_version"] == (
        "alr_candidate_learning_decision_v2"
    )
    assert projection["artifact"]["canonical_payload"]["schema_version"] == (
        "alr_candidate_learning_projection_artifact_v2"
    )
    assert plan["artifact"]["artifact_kind"] == "learning_target"
    assert projection["decision"]["selected_candidate"] is not None
    assert projection["decision"]["selected_collection_target"] is None
    assert "run" not in projection
    assert "pit_dataset_manifest" not in projection
    assert "statistical_experiment" not in projection
    assert projection["artifact"]["canonical_payload"]["training_run_created"] is False
    assert all(value is False for value in projection["no_authority"].values())
    assert all(value == 0 for value in projection["authority_counters"].values())


def test_candidate_board_bridge_rejects_identity_unbound_from_typed_input() -> None:
    typed = _candidate_row()
    board_row = _board_row(typed)
    board_row["candidate_identity"] = {
        **board_row["candidate_identity"],
        "strategy_name": "must_not_be_used",
        "symbol": "WRONGUSDT",
    }

    projection = build_candidate_aware_learning_projection(
        source_head="a" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(rows=[board_row]),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert projection["decision"]["decision_code"] == (
        "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    )
    assert projection["decision"]["evidence_source_status"] == (
        "EVIDENCE_CANDIDATE_ROWS_INVALID"
    )
    assert projection["decision"]["candidate_count"] == 0


def test_declared_incomplete_typed_input_cannot_be_laundered_by_flat_fields() -> None:
    typed = _candidate_row()
    board_row = _board_row(typed)
    board_row["arbiter_input_complete"] = False
    board_row["selection_eligible"] = False

    projection = build_candidate_aware_learning_projection(
        source_head="a" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(rows=[board_row]),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert projection["decision"]["selected_candidate"] is None
    assert projection["decision"]["eligible_candidate_count"] == 0
    assert (
        projection["decision"]["decision_code"]
        == "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    )


def test_omitted_typed_seam_cannot_fall_back_to_complete_flat_fields() -> None:
    flat = {
        **_candidate_row(),
        "arbiter_input_complete": False,
        "selection_eligible": False,
    }

    snapshot = _evidence_snapshot()
    snapshot["candidate_rows"] = [flat]
    snapshot.pop("snapshot_hash")
    snapshot["snapshot_hash"] = _sha(snapshot)
    projection = build_candidate_aware_learning_projection(
        source_head="a" * 40,
        cycles=_cycles(),
        evidence_snapshot=snapshot,
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert projection["decision"]["selected_candidate"] is None
    assert projection["decision"]["eligible_candidate_count"] == 0
    assert (
        projection["decision"]["decision_code"]
        == "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    )


def test_scanner_novelty_alone_emits_durable_rotation_not_fake_candidate() -> None:
    projection = build_candidate_aware_learning_projection(
        source_head="b" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(rows=[]),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    plan = build_candidate_learning_projection_plan(projection)
    assert plan["decision_code"] == "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION"
    assert plan["artifact"]["artifact_kind"] == "target_rotation"
    assert projection["decision"]["candidate_count"] == 0
    assert projection["decision"]["selected_candidate"] is None
    assert projection["decision"]["selected_collection_target"] is None


def test_insufficient_evidence_rotates_passive_collection_without_order() -> None:
    projection = build_candidate_aware_learning_projection(
        source_head="c" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(rows=[_board_row(_candidate_row(n_eff=29))]),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert (
        projection["decision"]["decision_code"]
        == "NO_QUALIFIED_CANDIDATE_COLLECT_DISTINCT_ENTRIES"
    )
    assert projection["decision"]["selected_candidate"] is None
    target = projection["decision"]["selected_collection_target"]
    assert target["state"] == "COLLECT_DISTINCT_ENTRIES"
    assert projection["artifact"]["canonical_payload"]["order_or_probe_created"] is False


def test_tail_cost_incomplete_candidate_repairs_without_becoming_selected() -> None:
    row = _board_row()
    row["tail_cost_recomputable_share"] = 0.9
    row["blockers"] = ["TAIL_COST_NOT_FULLY_RECOMPUTABLE"]
    row["selection_eligible"] = False

    projection = build_candidate_aware_learning_projection(
        source_head="c" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(rows=[row]),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert projection["decision"]["decision_code"] == (
        "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    )
    assert projection["decision"]["selected_candidate"] is None
    assert projection["decision"]["candidate_count"] == 1
    assert projection["decision"]["eligible_candidate_count"] == 0


def test_missing_evidence_is_a_hash_bound_no_candidate_artifact() -> None:
    projection = build_candidate_aware_learning_projection(
        source_head="d" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(status="DIRECTORY_MISSING"),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    plan = build_candidate_learning_projection_plan(projection)
    refs = plan["artifact"]["canonical_payload"]["source_refs"]
    assert plan["decision_code"] == "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    assert projection["decision"]["evidence_source_status"] == "DIRECTORY_MISSING"
    assert {
        key: refs[key]
        for key in (
            "evidence_source_status",
            "evidence_selection_hash",
            "candidate_set_hash",
        )
    } == {
        "evidence_source_status": "DIRECTORY_MISSING",
        "evidence_selection_hash": None,
        "candidate_set_hash": None,
    }
    assert refs["handoff"]["schema_version"] == "alr_candidate_board_handoff_v1"
    assert refs["handoff"]["evidence"]["source_status"] == "DIRECTORY_MISSING"
    assert refs["handoff"]["source_head"] == "d" * 40
    assert refs["handoff"]["decision_time"] == "2026-07-10T12:00:00Z"
    assert len(refs["handoff"]["handoff_hash"]) == 64


def test_missing_candidate_policy_is_durable_repair_not_generic_rotation() -> None:
    projection = build_candidate_aware_learning_projection(
        source_head="d" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(rows=[]),
        prior_decisions=[],
        policy={},
    )

    assert (
        projection["decision"]["decision_code"]
        == "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    )
    assert projection["decision"]["policy_hash"] is None
    assert projection["decision"]["selected_candidate"] is None
    assert projection["decision"]["selected_collection_target"] is None
    assert projection["decision"]["evaluated_at"] == "2026-07-10T12:00:00Z"
    handoff = projection["artifact"]["canonical_payload"]["source_refs"]["handoff"]
    assert handoff["decision_time"] == "2026-07-10T12:00:00Z"


def test_candidate_ranking_is_deterministic_while_immutable_source_hash_stays_bound() -> None:
    second = copy.deepcopy(_candidate_row())
    second["identity"]["symbol"] = "BETAUSDT"
    second["identity"]["config_hash"] = "f" * 64
    forward = build_candidate_aware_learning_projection(
        source_head="e" * 40,
        cycles=_cycles(),
        evidence_snapshot=_evidence_snapshot(rows=[_board_row(), _board_row(second)]),
        prior_decisions=[],
        policy=_candidate_policy(),
    )
    reverse = build_candidate_aware_learning_projection(
        source_head="e" * 40,
        cycles=list(reversed(_cycles())),
        evidence_snapshot=_evidence_snapshot(rows=[_board_row(second), _board_row()]),
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert forward["source_set"]["source_set_hash"] == reverse["source_set"][
        "source_set_hash"
    ]
    assert forward["decision"]["selected_candidate"] == reverse["decision"][
        "selected_candidate"
    ]
    assert forward["decision"]["evaluated_candidates"] == reverse["decision"][
        "evaluated_candidates"
    ]
    assert forward == reverse


def test_path_only_evidence_mutation_is_stable_but_handoff_hash_delta_is_not() -> None:
    base = _evidence_snapshot()
    path_only = copy.deepcopy(base)
    path_only["source_file"] = "/different/immutable/file.json"
    path_only.pop("snapshot_hash")
    path_only["snapshot_hash"] = _sha(path_only)
    handoff_delta = copy.deepcopy(base)
    handoff_delta.update(
        {
            "source_content_sha256": "a" * 64,
            "board_hash": "b" * 64,
            "audit_hash": "c" * 64,
        }
    )
    handoff_delta.pop("snapshot_hash")
    handoff_delta["snapshot_hash"] = _sha(handoff_delta)
    changed_candidate = _candidate_row()
    changed_identity = dict(changed_candidate["identity"])
    changed_identity.update({"symbol": "BETAUSDT", "config_hash": "f" * 64})
    changed_candidate["identity"] = changed_identity
    selection_delta = _evidence_snapshot(rows=[_board_row(changed_candidate)])

    first = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=base,
        prior_decisions=[],
        policy=_candidate_policy(),
    )
    path_changed = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=path_only,
        prior_decisions=[],
        policy=_candidate_policy(),
    )
    handoff_changed = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=handoff_delta,
        prior_decisions=[],
        policy=_candidate_policy(),
    )
    selection_changed = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=selection_delta,
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert first == path_changed
    assert first["projection_hash"] != handoff_changed["projection_hash"]
    assert first["projection_hash"] != selection_changed["projection_hash"]
    assert set(first["artifact"]["canonical_payload"]["source_refs"]) == {
        "evidence_source_status",
        "evidence_selection_hash",
        "candidate_set_hash",
        "handoff",
    }


def test_projection_rejects_v1_snapshot_and_tampered_v2_arbiter_input() -> None:
    legacy = _evidence_snapshot()
    legacy["schema_version"] = "alr_candidate_evidence_snapshot_v1"
    legacy.pop("snapshot_hash")
    legacy["snapshot_hash"] = _sha(legacy)
    tampered_row = _board_row()
    tampered_row["arbiter_input"]["evidence"]["n_eff"] = 31
    tampered = _evidence_snapshot(rows=[tampered_row])
    forged_selection = _evidence_snapshot()
    forged_selection["selection_hash"] = "d" * 64
    forged_selection.pop("snapshot_hash")
    forged_selection["snapshot_hash"] = _sha(forged_selection)
    forged_candidate_set = _evidence_snapshot()
    forged_candidate_set["candidate_set_hash"] = "e" * 64
    forged_candidate_set.pop("snapshot_hash")
    forged_candidate_set["snapshot_hash"] = _sha(forged_candidate_set)

    legacy_projection = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=legacy,
        prior_decisions=[],
        policy=_candidate_policy(),
    )
    tampered_projection = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=tampered,
        prior_decisions=[],
        policy=_candidate_policy(),
    )
    forged_projection = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=forged_selection,
        prior_decisions=[],
        policy=_candidate_policy(),
    )
    forged_candidate_set_projection = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=forged_candidate_set,
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert legacy_projection["decision"]["decision_code"] == (
        "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    )
    assert legacy_projection["decision"]["evidence_source_status"] == (
        "EVIDENCE_SNAPSHOT_SCHEMA_INVALID"
    )
    assert tampered_projection["decision"]["selected_candidate"] is None
    assert tampered_projection["decision"]["decision_code"] == (
        "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    )
    assert forged_projection["decision"]["evidence_source_status"] == (
        "EVIDENCE_SELECTION_HASH_MISMATCH"
    )
    assert forged_candidate_set_projection["decision"][
        "evidence_source_status"
    ] == "CANDIDATE_SET_HASH_MISMATCH"


@pytest.mark.parametrize(
    ("mutation", "expected_status"),
    (
        ("duplicate_id", "EVIDENCE_CANDIDATE_ID_DUPLICATE"),
        ("malformed_blockers", "EVIDENCE_CANDIDATE_ROWS_INVALID"),
    ),
)
def test_projection_rejects_duplicate_ids_and_malformed_selection_rows(
    mutation: str,
    expected_status: str,
) -> None:
    row = _board_row()
    if mutation == "duplicate_id":
        rows = [row, copy.deepcopy(row)]
    else:
        row["blockers"] = "not-a-list"
        rows = [row]
    snapshot = _evidence_snapshot(rows=rows)

    projection = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=snapshot,
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert projection["decision"]["evidence_source_status"] == expected_status
    assert projection["decision"]["candidate_count"] == 0


@pytest.mark.parametrize("mutation", ("stable_cohort_hash", "nested_type"))
def test_projection_rejects_rehashed_noncanonical_candidate_contract(
    mutation: str,
) -> None:
    row = _board_row()
    if mutation == "stable_cohort_hash":
        row["stable_cohort_hash"] = "f" * 64
    else:
        row["arbiter_input"]["quality"]["censored_share"] = "0.1"
        _rehash_arbiter_input(row["arbiter_input"])
    snapshot = _evidence_snapshot(rows=[row])

    projection = build_candidate_aware_learning_projection(
        source_head="f" * 40,
        cycles=_cycles(),
        evidence_snapshot=snapshot,
        prior_decisions=[],
        policy=_candidate_policy(),
    )

    assert projection["decision"]["evidence_source_status"] == (
        "EVIDENCE_CANDIDATE_ROWS_INVALID"
    )
    assert projection["decision"]["candidate_count"] == 0
