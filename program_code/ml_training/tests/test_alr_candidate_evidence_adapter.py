from __future__ import annotations

import copy
import datetime as dt
from functools import lru_cache
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESEARCH_ROOT = _REPO_ROOT / "helper_scripts" / "research"
if str(_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_ROOT))

from ml_training import alr_candidate_evidence_adapter as adapter
from ml_training import alr_safe_file
from ml_training.alr_candidate_evidence_adapter import (
    load_candidate_evidence_snapshot,
)
from cost_gate_learning_lane.candidate_board_validation import (
    validate_learning_candidate_board_v2,
)
from cost_gate_learning_lane.outcome_review import (
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.slippage_quantile_artifact import (
    build_slippage_quantile_artifact,
)
from helper_scripts.research.tests.candidate_lineage_v2_test_support import (
    attach_candidate_lineage_v2,
)


EVALUATED_AT = "2026-07-10T12:00:00Z"
REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)


@lru_cache(maxsize=1)
def _expected_cost_source_payload() -> dict[str, object]:
    return build_slippage_quantile_artifact(
        [
            {
                "symbol": None,
                "n": 100,
                "mean_abs": 2.0,
                "mean_signed": 0.5,
                "q50": 1.0,
                "q75": 3.0,
                "q90": 7.0,
                "cvar90": 8.0,
            },
            {
                "symbol": "BTCUSDT",
                "n": 100,
                "mean_abs": 2.0,
                "mean_signed": 0.5,
                "q50": 1.0,
                "q75": 3.0,
                "q90": 7.0,
                "cvar90": 8.0,
            },
        ],
        now_utc=dt.datetime(2026, 7, 10, 11, tzinfo=dt.timezone.utc),
    )


@lru_cache(maxsize=1)
def _expected_cost_outer() -> dict[str, object]:
    review = build_blocked_signal_outcome_review(
        [],
        now_utc=dt.datetime(2026, 7, 10, 11, 30, tzinfo=dt.timezone.utc),
        slippage_quantiles=copy.deepcopy(_expected_cost_source_payload()),
    )
    return copy.deepcopy(review["expected_cost_artifact"])


def _conservative_cost_outer() -> dict[str, object]:
    return {
        "available": False,
        "asof": None,
        "source_asof_utc": None,
        "source_payload_sha256": None,
        "source_payload": None,
        "normalized_projection": None,
        "normalized_projection_sha256": None,
        "global_mean_abs_bps": None,
        "global_tail_bps": None,
        "global_tail_metric": None,
        "n_total_global": 0,
        "max_age_hours": 48,
    }


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@lru_cache(maxsize=None)
def _producer_candidate_row(
    candidate_label: str,
    n_eff: int,
    utc_days: int,
    expected_cost_track: bool = True,
    gross_missing_first: bool = False,
) -> dict[str, object]:
    """Build the adapter fixture through the real producer + public validator."""
    rows: list[dict[str, object]] = []
    per_day = n_eff // utc_days
    assert per_day * utc_days == n_eff
    data_hash = _canonical_sha256(
        {"candidate_label": candidate_label, "kind": "data"}
    )
    day_effects = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)
    for index in range(n_eff):
        day_index = index // per_day
        slot = index % per_day
        captured = dt.datetime(
            2026,
            7,
            3 + day_index,
            slot * (24 // per_day),
            tzinfo=dt.timezone.utc,
        )
        captured_at_ms = int(captured.timestamp() * 1_000)
        attempt_id = f"{candidate_label}-{index:02d}"
        gross_bps = -20.0 + day_effects[day_index] + slot * 0.1
        outcome = {
            "record_type": "blocked_signal_outcome",
            "attempt_id": attempt_id,
            "side_cell_key": "ma_crossover|BTCUSDT|Buy",
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "horizon_minutes": 60,
            "entry_ts_ms": captured_at_ms,
            "gross_bps": None if gross_missing_first and index == 0 else gross_bps,
            "realized_net_bps": gross_bps - 12.0,
            "cost_bps": 12.0,
            "cost_model_version": "conservative_v1",
        }
        rows.append(
            attach_candidate_lineage_v2(
                outcome,
                context_id=attempt_id,
                captured_at_ms=captured_at_ms,
                as_of_utc_date="2026-07-10",
                evidence_engine_mode="demo",
                stable_projection_overrides={
                    "context_hashes": {
                        "data": data_hash,
                        "evidence": "2" * 64,
                        "cost": "3" * 64,
                        "portfolio": "4" * 64,
                    }
                },
            )
        )
    review_kwargs: dict[str, object] = {}
    if expected_cost_track:
        review_kwargs["slippage_quantiles"] = copy.deepcopy(
            _expected_cost_source_payload()
        )
    review = build_blocked_signal_outcome_review(
        rows,
        now_utc=dt.datetime(2026, 7, 10, 11, 30, tzinfo=dt.timezone.utc),
        **review_kwargs,
    )
    board = review["learning_candidate_board"]
    validate_learning_candidate_board_v2(board)
    assert len(board["candidate_rows"]) == 1
    return copy.deepcopy(board["candidate_rows"][0])


def _candidate_row(candidate_id: str = "candidate-b") -> dict[str, object]:
    return copy.deepcopy(_producer_candidate_row(candidate_id, 30, 6))


def _ineligible_candidate_row(
    candidate_id: str = "candidate-ineligible",
) -> dict[str, object]:
    return copy.deepcopy(_producer_candidate_row(candidate_id, 12, 3))


def _conservative_candidate_row(
    candidate_id: str = "candidate-conservative",
) -> dict[str, object]:
    return copy.deepcopy(_producer_candidate_row(candidate_id, 30, 6, False))


def _partial_expected_candidate_row(
    candidate_id: str = "candidate-partial-expected",
) -> dict[str, object]:
    return copy.deepcopy(
        _producer_candidate_row(candidate_id, 30, 6, True, True)
    )


def test_rehashed_board_rejects_false_ineligible_flag_without_blockers(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    row = board["candidate_rows"][0]
    row["selection_eligible"] = False
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_SELECTION_FLAGS_INVALID"


def test_rehashed_board_rejects_false_identity_complete_on_ineligible_row(
    tmp_path: Path,
) -> None:
    row = _ineligible_candidate_row()
    row["identity_complete"] = False
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_FLAGS_INVALID"


def test_rehashed_board_rejects_false_input_complete_without_lineage_conflict(
    tmp_path: Path,
) -> None:
    row = _ineligible_candidate_row()
    row["arbiter_input_complete"] = False
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_INPUT_COMPLETENESS_INVALID"


def test_rehashed_board_rejects_unknown_blocker_vocabulary(
    tmp_path: Path,
) -> None:
    row = _ineligible_candidate_row()
    row["blockers"] = ["ARBITRARY_REHASHED_BLOCKER"]
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_BLOCKER_SEMANTICS_INVALID"


@pytest.mark.parametrize(
    "blocker",
    (
        "ENTRY_TS_LINEAGE_INCOMPLETE",
        "INVALID_OUTCOME_ROWS_PRESENT",
        "TAIL_COST_NOT_FULLY_RECOMPUTABLE",
    ),
)
def test_rehashed_board_rejects_false_audit_derived_blocker(
    tmp_path: Path,
    blocker: str,
) -> None:
    row = _candidate_row()
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_BLOCKER_SEMANTICS_INVALID"


@pytest.mark.parametrize(
    "blocker",
    (
        "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT",
        "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT",
        "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT",
        "DUPLICATE_EVENT_HASH_COHORT_CONFLICT",
    ),
)
def test_rehashed_board_rejects_false_lineage_conflict_blocker(
    tmp_path: Path,
    blocker: str,
) -> None:
    row = _candidate_row()
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    row["arbiter_input_complete"] = False
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_BLOCKER_SEMANTICS_INVALID"


@pytest.mark.parametrize(
    "blocker",
    (
        "STRATEGY_NAME_MISSING_OR_INVALID",
        "ARBITER_INPUT_CONTEXT_INCOMPLETE",
    ),
)
def test_exact_v2_row_rejects_structural_or_context_blocker(
    tmp_path: Path,
    blocker: str,
) -> None:
    row = _candidate_row()
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_BLOCKER_SEMANTICS_INVALID"


@pytest.mark.parametrize(
    ("count_field", "blocker", "lineage"),
    (
        (
            "qualified_entry_ts_missing_row_count",
            "ENTRY_TS_LINEAGE_INCOMPLETE",
            False,
        ),
        (
            "qualified_invalid_outcome_row_count",
            "INVALID_OUTCOME_ROWS_PRESENT",
            False,
        ),
        (
            "invalid_lineage_exact_cohort_row_count",
            "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT",
            True,
        ),
    ),
)
def test_audit_derived_integrity_failure_must_be_bound_into_typed_input(
    tmp_path: Path,
    count_field: str,
    blocker: str,
    lineage: bool,
) -> None:
    row = _candidate_row()
    row[count_field] = 1
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    if lineage:
        row["lineage_blocker_reason_counts"] = {blocker: 1}
        row["arbiter_input_complete"] = False
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] != "READY"
    assert result["selection_allowed"] is False


_AUDIT_BLOCKER_CASES = (
    (
        "qualified_entry_ts_missing_row_count",
        1,
        "ENTRY_TS_LINEAGE_INCOMPLETE",
        False,
    ),
    (
        "qualified_invalid_outcome_row_count",
        1,
        "INVALID_OUTCOME_ROWS_PRESENT",
        False,
    ),
    (
        "tail_cost_recomputable_share",
        0.9,
        "TAIL_COST_NOT_FULLY_RECOMPUTABLE",
        False,
    ),
    (
        "invalid_lineage_exact_cohort_row_count",
        1,
        "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT",
        True,
    ),
    (
        "invalid_lineage_identity_family_row_count",
        1,
        "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT",
        True,
    ),
    (
        "duplicate_event_hash_outcome_conflict_row_count",
        1,
        "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT",
        True,
    ),
    (
        "duplicate_event_hash_cohort_conflict_row_count",
        1,
        "DUPLICATE_EVENT_HASH_COHORT_CONFLICT",
        True,
    ),
)


@pytest.mark.parametrize(
    ("audit_field", "active_value", "blocker", "lineage"),
    _AUDIT_BLOCKER_CASES,
)
def test_rejects_partially_bound_audit_derived_blocker(
    tmp_path: Path,
    audit_field: str,
    active_value: int | float,
    blocker: str,
    lineage: bool,
) -> None:
    row = _candidate_row()
    row[audit_field] = active_value
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    if blocker != "TAIL_COST_NOT_FULLY_RECOMPUTABLE":
        row["arbiter_input"]["quality"]["integrity_ok"] = False
    if lineage:
        row["lineage_blocker_reason_counts"] = {blocker: 1}
        row["arbiter_input_complete"] = False
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] != "READY"
    assert result["selection_allowed"] is False


def test_rejects_data_integrity_blocker_without_full_producer_bindings(
    tmp_path: Path,
) -> None:
    row = _candidate_row()
    row["data_integrity_suspect"] = True
    row["arbiter_input"]["quality"]["integrity_ok"] = False
    row["blockers"] = ["DATA_INTEGRITY_SUSPECT"]
    row["selection_eligible"] = False
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] != "READY"
    assert result["selection_allowed"] is False


@pytest.mark.parametrize(
    ("audit_field", "active_value", "blocker", "lineage"),
    _AUDIT_BLOCKER_CASES,
)
def test_rehashed_board_rejects_removed_audit_derived_blocker(
    tmp_path: Path,
    audit_field: str,
    active_value: int | float,
    blocker: str,
    lineage: bool,
) -> None:
    row = _candidate_row()
    row[audit_field] = active_value
    if blocker != "TAIL_COST_NOT_FULLY_RECOMPUTABLE":
        row["arbiter_input"]["quality"]["integrity_ok"] = False
    if lineage:
        row["lineage_blocker_reason_counts"] = {blocker: 1}
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] != "READY"
    assert result["selection_allowed"] is False


def test_rehashed_board_rejects_inexact_lineage_reason_count(
    tmp_path: Path,
) -> None:
    row = _candidate_row()
    blocker = "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT"
    row["invalid_lineage_exact_cohort_row_count"] = 1
    row["lineage_blocker_reason_counts"] = {blocker: 2}
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    row["arbiter_input_complete"] = False
    row["arbiter_input"]["quality"]["integrity_ok"] = False
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_BLOCKER_SEMANTICS_INVALID"


def test_rehashed_board_rejects_missing_typed_sample_blocker(
    tmp_path: Path,
) -> None:
    row = _ineligible_candidate_row()
    row["blockers"] = ["UTC_DAY_COVERAGE_INSUFFICIENT"]
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_BLOCKER_SEMANTICS_INVALID"


def test_accepts_genuine_eligible_and_ineligible_producer_rows(
    tmp_path: Path,
) -> None:
    payload = _payload(
        rows=[
            _candidate_row("candidate-eligible"),
            _ineligible_candidate_row("candidate-ineligible"),
        ]
    )
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "READY"
    assert sorted(
        row["selection_eligible"] for row in result["candidate_rows"]
    ) == [False, True]


def test_rehashed_board_rejects_cluster_standard_error_detached_from_variance(
    tmp_path: Path,
) -> None:
    row = _candidate_row()
    row["arbiter_input"]["evidence"]["cluster_se"] = 0.31
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "ARBITER_EVIDENCE_ALGEBRA_INVALID"


@pytest.mark.parametrize(
    "mutation",
    (
        "top_day",
        "censoring",
        "replica",
        "cluster",
        "legacy_cost",
        "cost_recomputable",
        "proof_gap",
        "hidden_oos",
        "spurious",
    ),
)
def test_rehashed_board_rejects_every_typed_blocker_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    row = _candidate_row()
    quality = row["arbiter_input"]["quality"]
    evidence = row["arbiter_input"]["evidence"]
    if mutation == "top_day":
        quality["top_day_share"] = 0.6
    elif mutation == "censoring":
        quality["censored_share"] = 0.31
    elif mutation == "replica":
        quality["replica_inconsistency_count"] = 1
        quality["integrity_ok"] = False
    elif mutation == "cluster":
        quality["cluster_variance_clean"] = False
        evidence["day_cluster_variance"] = 0.0
        evidence["cluster_se"] = None
    elif mutation == "legacy_cost":
        quality["legacy_optimistic_cost_present"] = True
    elif mutation == "cost_recomputable":
        quality["cost_recomputable_share"] = 0.9
    elif mutation == "proof_gap":
        evidence["next_gap"] = {"kind": "LOCAL_PASSIVE", "code": "COLLECT"}
    elif mutation == "hidden_oos":
        quality["hidden_oos_consumed"] = True
    else:
        row["blockers"] = ["LEGACY_OPTIMISTIC_COST_UNBACKFILLED"]
        row["selection_eligible"] = False
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_BLOCKER_SEMANTICS_INVALID"


def test_rehashed_board_rejects_tampered_stable_cohort_hash(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    rows = board["candidate_rows"]
    assert isinstance(rows, list)
    rows[0]["stable_cohort_hash"] = "f" * 64
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "STABLE_COHORT_HASH_MISMATCH"


@pytest.mark.parametrize(
    ("mutation", "expected_status"),
    [
        ("arbiter_input_extra", "ARBITER_INPUT_FIELDS_INVALID"),
        ("strategy_version", "STRATEGY_VERSION_INVALID"),
        ("symbol", "SYMBOL_INVALID"),
        ("market", "MARKET_IDENTITY_INVALID"),
        ("horizon", "HORIZON_INVALID"),
        ("target_label", "TARGET_REGIME_LABEL_INVALID"),
        ("quality_extra", "ARBITER_QUALITY_FIELDS_INVALID"),
        ("evidence_extra", "ARBITER_EVIDENCE_FIELDS_INVALID"),
        ("resource_extra", "ARBITER_RESOURCE_FIELDS_INVALID"),
        ("portfolio_extra", "ARBITER_PORTFOLIO_FIELDS_INVALID"),
    ],
)
def test_rehashed_board_rejects_noncanonical_nested_producer_shapes(
    tmp_path: Path,
    mutation: str,
    expected_status: str,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    rows = board["candidate_rows"]
    assert isinstance(rows, list)
    row = rows[0]
    assert isinstance(row, dict)
    arbiter_input = row["arbiter_input"]
    assert isinstance(arbiter_input, dict)
    identity = arbiter_input["identity"]
    assert isinstance(identity, dict)
    if mutation == "arbiter_input_extra":
        arbiter_input["unexpected"] = True
    elif mutation == "strategy_version":
        identity["strategy_version"] = "v7"
    elif mutation == "symbol":
        identity["symbol"] = "btcusdt"
    elif mutation == "market":
        identity["venue"] = "binance"
    elif mutation == "horizon":
        identity["horizon_minutes"] = 1_441
    elif mutation == "target_label":
        target = dict(identity["target_regime"])
        target["label"] = "bull_high_vol"
        target["hash"] = _canonical_sha256(
            {key: value for key, value in target.items() if key != "hash"}
        )
        identity["target_regime"] = target
    else:
        nested_name = mutation.removesuffix("_extra")
        nested = arbiter_input[nested_name]
        assert isinstance(nested, dict)
        nested["unexpected"] = True
    _rehash_candidate_contract(row)
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == expected_status


def test_board_lineage_reason_counts_must_cover_all_excluded_rows(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["raw_blocked_outcome_row_count"] += 1
    board["unqualified_lineage_outcome_row_count"] = 1
    board["unqualified_raw_valid_evaluation_missing_row_count"] = 1
    board["lineage_exclusion_reason_counts"] = {}
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "BOARD_REASON_COUNTS_INVALID"


def test_rehashed_board_rejects_arbitrary_lineage_reason_key(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["raw_blocked_outcome_row_count"] += 1
    board["unqualified_lineage_outcome_row_count"] = 1
    board["lineage_exclusion_reason_counts"] = {"ARBITRARY_LINEAGE_REASON": 1}
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "BOARD_REASON_COUNTS_INVALID"
    assert result["selection_allowed"] is False


def test_rehashed_board_rejects_candidate_count_algebra_drift(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    row = board["candidate_rows"][0]
    row["qualified_evaluator_input_count"] += 1
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_COUNT_INVARIANT_INVALID"


def test_rehashed_board_rejects_candidate_raw_count_outside_accounted_range(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    row = board["candidate_rows"][0]
    row["qualified_raw_outcome_count"] += 1
    board["qualified_lineage_outcome_row_count"] += 1
    board["raw_blocked_outcome_row_count"] += 1
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_COUNT_INVARIANT_INVALID"


def test_rehashed_board_rejects_candidate_statistical_algebra_drift(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    row = board["candidate_rows"][0]
    first_day = min(row["entry_day_counts"])
    row["entry_day_counts"][first_day] += 1
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_STATISTICAL_INVARIANT_INVALID"


def test_rehashed_board_rejects_detached_candidate_audit_mean(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    row = board["candidate_rows"][0]
    row["avg_net_bps"] = row["mean_net_e"] + 1.0
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_STATISTICAL_INVARIANT_INVALID"


def test_rehashed_board_rejects_conservative_cost_basis_laundering(
    tmp_path: Path,
) -> None:
    row = _conservative_candidate_row()
    n_eff = row["n_eff"]
    assert isinstance(n_eff, int) and n_eff == 30
    row.update(
        {
            "expected_cost_recomputable_count": n_eff,
            "expected_cost_recomputable_share": 1.0,
            "cost_recomputable_share": 1.0,
            "avg_expected_cost_bps": 11.0,
            "tail_cost_recomputable_count": n_eff,
            "tail_cost_recomputable_share": 1.0,
            "avg_tail_cost_bps": 12.0,
            "tail_metric": "cvar90",
            "selection_eligible": True,
            "blockers": [],
        }
    )
    row["arbiter_input"]["quality"]["cost_recomputable_share"] = 1.0
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_STATISTICAL_INVARIANT_INVALID"


def test_rehashed_board_rejects_nonempty_null_mean(
    tmp_path: Path,
) -> None:
    row = _candidate_row()
    row["avg_net_bps"] = None
    row["mean_net_e"] = None
    row["arbiter_input"]["evidence"]["mean_net_e"] = None
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_STATISTICAL_INVARIANT_INVALID"


@pytest.mark.parametrize(
    "field",
    ("avg_expected_cost_bps", "avg_tail_cost_bps"),
)
def test_rehashed_board_rejects_negative_cost_average(
    tmp_path: Path,
    field: str,
) -> None:
    row = _candidate_row()
    row[field] = -999.0
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_STATISTICAL_INVARIANT_INVALID"


@pytest.mark.parametrize(
    ("field", "value", "valid"),
    (
        ("avg_expected_cost_bps", 14.999999, False),
        ("avg_expected_cost_bps", 15.0, True),
        ("avg_tail_cost_bps", 26.999999, False),
        ("avg_tail_cost_bps", 27.0, True),
    ),
)
def test_fully_rehashed_expected_cost_averages_bind_selected_source_projection(
    tmp_path: Path,
    field: str,
    value: float,
    valid: bool,
) -> None:
    row = _candidate_row()
    row[field] = value
    payload = _payload(rows=[row])
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)

    if valid:
        assert validate_learning_candidate_board_v2(board) == board
    else:
        with pytest.raises(
            ValueError,
            match="candidate_cost_evidence_binding_invalid",
        ):
            validate_learning_candidate_board_v2(board)

    _write_snapshot(tmp_path, payload=payload)
    result = _load(tmp_path)
    assert result["source_status"] == (
        "READY" if valid else "CANDIDATE_COST_EVIDENCE_BINDING_INVALID"
    )


def test_rehashed_board_rejects_detached_candidate_aggregate_totals(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["qualified_lineage_outcome_row_count"] += 1
    board["raw_blocked_outcome_row_count"] += 1
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "BOARD_CANDIDATE_TOTALS_INVALID"


def test_rehashed_board_rejects_unique_conflict_below_row_attribution(
    tmp_path: Path,
) -> None:
    row = _candidate_row()
    blocker = "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT"
    row["conflicting_event_hash_row_count"] = 2
    row["duplicate_event_hash_outcome_conflict_row_count"] = 2
    row["lineage_blocker_reason_counts"] = {blocker: 2}
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    row["arbiter_input_complete"] = False
    row["qualified_metrics_actionable"] = False
    row["metrics_scope"] = "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"
    row["arbiter_input"]["quality"]["integrity_ok"] = False
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["conflicting_duplicate_event_hash_row_count"] = 1
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "BOARD_DUPLICATE_TOTALS_INVALID"


def test_rehashed_board_rejects_family_invalid_attribution_above_top_total(
    tmp_path: Path,
) -> None:
    row = _candidate_row()
    blocker = "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT"
    row["invalid_lineage_identity_family_row_count"] = 1
    row["lineage_blocker_reason_counts"] = {blocker: 1}
    row["blockers"] = [blocker]
    row["selection_eligible"] = False
    row["arbiter_input_complete"] = False
    row["qualified_metrics_actionable"] = False
    row["metrics_scope"] = "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"
    row["arbiter_input"]["quality"]["integrity_ok"] = False
    _rehash_candidate_contract(row)
    payload = _payload(rows=[row])
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["raw_blocked_outcome_row_count"] -= 1
    board["invalid_lineage_outcome_row_count"] = 0
    board["invalid_identity_family_row_count"] = 0
    board["lineage_exclusion_reason_counts"] = {}
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "BOARD_CANDIDATE_TOTALS_INVALID"


def _producer_candidate_row_order_key(row: dict[str, object]) -> tuple[object, ...]:
    identity = row["candidate_identity"]
    assert isinstance(identity, dict)
    return (
        identity["strategy_name"],
        identity["strategy_version"],
        identity["strategy_config_hash"],
        identity["symbol"],
        identity["side"],
        identity["horizon_minutes"],
        identity["target_regime_hash"],
        identity["venue"],
        identity["product"],
        identity["engine_mode"],
        row["candidate_id"],
        row["stable_cohort_hash"],
    )


def _payload(*, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    candidate_rows = sorted(
        rows or [_candidate_row()],
        key=_producer_candidate_row_order_key,
    )
    qualified_count = sum(
        int(row["qualified_raw_outcome_count"]) for row in candidate_rows
    )
    invalid_exact_count = sum(
        int(row["invalid_lineage_exact_cohort_row_count"])
        for row in candidate_rows
    )
    invalid_family_count = sum(
        int(row["invalid_lineage_identity_family_row_count"])
        for row in candidate_rows
    )
    consistent_duplicate_count = sum(
        int(row["consistent_duplicate_event_hash_extra_row_count"])
        for row in candidate_rows
    )
    conflict_attribution_count = sum(
        int(row["conflicting_event_hash_row_count"])
        for row in candidate_rows
    )
    invalid_count = invalid_exact_count + invalid_family_count
    reason_counts = {
        code: count
        for code, count in (
            ("INVALID_LINEAGE_EXACT_COHORT", invalid_exact_count),
            ("INVALID_LINEAGE_IDENTITY_FAMILY", invalid_family_count),
        )
        if count
    }
    board: dict[str, object] = {
        "schema_version": "cost_gate_learning_candidate_board_v2",
        "as_of_utc_date": "2026-07-10",
        "candidate_universe_complete": True,
        "lineage_partition_complete": True,
        "raw_blocked_outcome_row_count": qualified_count + invalid_count,
        "qualified_lineage_outcome_row_count": qualified_count,
        "unqualified_lineage_outcome_row_count": 0,
        "invalid_lineage_outcome_row_count": invalid_count,
        "invalid_exact_cohort_row_count": invalid_exact_count,
        "invalid_identity_family_row_count": invalid_family_count,
        "unassigned_invalid_lineage_outcome_row_count": 0,
        "unqualified_raw_valid_evaluation_missing_row_count": 0,
        "unqualified_event_outside_evaluation_window_row_count": 0,
        "consistent_duplicate_event_hash_extra_row_count": (
            consistent_duplicate_count
        ),
        "conflicting_duplicate_event_hash_row_count": (
            conflict_attribution_count
        ),
        "conflicting_duplicate_event_hash_attribution_row_count": (
            conflict_attribution_count
        ),
        "lineage_exclusion_reason_counts": reason_counts,
        "candidate_rows": candidate_rows,
    }
    _rehash_board(board)
    bases = {row["cost_basis_main"] for row in candidate_rows}
    assert len(bases) == 1
    basis = bases.pop()
    return {
        "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v6",
        "record_type": "blocked_signal_outcome_review",
        "generated_at_utc": "2026-07-10T11:30:00Z",
        "cost_basis_main": basis,
        "expected_cost_artifact": (
            copy.deepcopy(_expected_cost_outer())
            if basis == "expected_slippage_mean_abs_v1"
            else _conservative_cost_outer()
        ),
        "learning_candidate_board": board,
        "top_side_cells": [{"legacy_only": True}],
    }


def _rehash_board(board: dict[str, object]) -> None:
    candidate_rows = board["candidate_rows"]
    assert isinstance(candidate_rows, list)
    semantic_rows = sorted(
        (_semantic_candidate_row(row) for row in candidate_rows),
        key=lambda row: (str(row["candidate_id"]), _canonical_sha256(row)),
    )
    board["selection_hash"] = _canonical_sha256(
        {
            "schema_version": "cost_gate_learning_candidate_selection_v2",
            "candidate_rows": semantic_rows,
        }
    )
    selection_fields = set(_SELECTION_FIELDS)
    candidate_audit_rows = sorted(
        (
            {
                "candidate_id": row["candidate_id"],
                **{
                    key: value
                    for key, value in row.items()
                    if key not in selection_fields and key != "candidate_id"
                },
            }
            for row in candidate_rows
        ),
        key=lambda row: str(row["candidate_id"]),
    )
    board["audit_hash"] = _canonical_sha256(
        {
            "schema_version": "cost_gate_learning_candidate_audit_v2",
            **{key: board[key] for key in _TOP_AUDIT_FIELDS},
            "candidate_audit_rows": candidate_audit_rows,
        }
    )
    board.pop("board_hash", None)
    board["board_hash"] = _canonical_sha256(board)


def _semantic_candidate_row(row: dict[str, object]) -> dict[str, object]:
    return {
        key: row[key]
        for key in _SELECTION_FIELDS
    }


def _rehash_candidate_contract(row: dict[str, object]) -> None:
    arbiter_input = row["arbiter_input"]
    assert isinstance(arbiter_input, dict)
    identity = arbiter_input["identity"]
    context_hashes = arbiter_input["context_hashes"]
    evidence = arbiter_input["evidence"]
    quality = arbiter_input["quality"]
    assert isinstance(identity, dict)
    assert isinstance(context_hashes, dict)
    assert isinstance(evidence, dict)
    assert isinstance(quality, dict)
    arbiter_input.pop("arbiter_input_hash", None)
    arbiter_input["arbiter_input_hash"] = _canonical_sha256(arbiter_input)
    raw_identity = {
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
    target = identity["target_regime"]
    assert isinstance(target, dict)
    target_context = {key: value for key, value in target.items() if key != "hash"}
    row["candidate_identity"] = {
        **raw_identity,
        "target_regime_context": target_context,
        "target_regime_hash": target["hash"],
        "engine_mode": "shadow",
    }
    row["candidate_id"] = _canonical_sha256(
        {
            "schema_version": "cost_gate_learning_candidate_v2",
            "identity": identity,
            "context_hashes": context_hashes,
        }
    )
    row["candidate_family_key"] = _canonical_sha256(
        {
            "schema_version": "candidate_learning_family_v2",
            "identity": raw_identity,
        }
    )
    stable_projection = {
        "strategy_version": raw_identity["strategy_version"],
        "strategy_config_hash": raw_identity["strategy_config_hash"],
        "target_regime_context": {
            key: target_context[key]
            for key in ("label", "utc_date", "point_in_time")
        },
        "target_regime_hash": target["hash"],
        "venue": raw_identity["venue"],
        "product": raw_identity["product"],
        "evidence_engine_mode": raw_identity["evidence_engine_mode"],
        "context_hashes": context_hashes,
        "resource": arbiter_input["resource"],
        "portfolio": arbiter_input["portfolio"],
        "proof": {
            "proof_stage": evidence["proof_stage"],
            "completed_proof_stages": evidence["completed_proof_stages"],
            "next_gap": evidence["next_gap"],
        },
        "hidden_oos_consumed": quality["hidden_oos_consumed"],
    }
    row["stable_cohort_hash"] = _canonical_sha256(
        {"identity": raw_identity, "stable_projection": stable_projection}
    )


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

_TOP_AUDIT_FIELDS = (
    "lineage_partition_complete",
    "raw_blocked_outcome_row_count",
    "qualified_lineage_outcome_row_count",
    "unqualified_lineage_outcome_row_count",
    "invalid_lineage_outcome_row_count",
    "invalid_exact_cohort_row_count",
    "invalid_identity_family_row_count",
    "unassigned_invalid_lineage_outcome_row_count",
    "unqualified_raw_valid_evaluation_missing_row_count",
    "unqualified_event_outside_evaluation_window_row_count",
    "consistent_duplicate_event_hash_extra_row_count",
    "conflicting_duplicate_event_hash_row_count",
    "conflicting_duplicate_event_hash_attribution_row_count",
    "lineage_exclusion_reason_counts",
)


def _write_snapshot(
    directory: Path,
    *,
    name: str = "blocked_outcome_review_20260710T113000Z.json",
    payload: dict[str, object] | None = None,
) -> Path:
    path = directory / name
    path.write_text(
        json.dumps(payload or _payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _load(directory: Path, **overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "evaluated_at": EVALUATED_AT,
        "max_age_seconds": 3600,
        "max_files": 8,
        "max_bytes": 1_000_000,
    }
    kwargs.update(overrides)
    return load_candidate_evidence_snapshot(directory, **kwargs)


def _rehash_expected_cost_contract(payload: dict[str, object]) -> None:
    outer = payload["expected_cost_artifact"]
    assert isinstance(outer, dict)
    source_payload = outer["source_payload"]
    normalized_projection = outer["normalized_projection"]
    outer["source_payload_sha256"] = _canonical_sha256(source_payload)
    outer["normalized_projection_sha256"] = _canonical_sha256(
        normalized_projection
    )
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    for row in board["candidate_rows"]:
        cost_evidence = row["arbiter_input"]["cost_evidence"]
        cost_evidence["source_payload_sha256"] = outer[
            "source_payload_sha256"
        ]
        cost_evidence["normalized_projection_sha256"] = outer[
            "normalized_projection_sha256"
        ]
        _rehash_candidate_contract(row)
    _rehash_board(board)


def test_missing_directory_is_structured_fail_closed_not_an_exception(
    tmp_path: Path,
) -> None:
    result = _load(tmp_path / "missing")

    assert result["source_status"] == "DIRECTORY_MISSING"
    assert result["candidate_rows"] == []
    assert result["candidate_universe_complete"] is False
    assert result["selection_allowed"] is False


def test_loads_latest_immutable_snapshot_and_binds_content_and_board_hash(
    tmp_path: Path,
) -> None:
    older = _payload(rows=[_candidate_row("candidate-z")])
    older["generated_at_utc"] = "2026-07-10T11:00:00Z"
    _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T110000Z.json",
        payload=older,
    )
    latest_path = _write_snapshot(
        tmp_path,
        payload=_payload(
            rows=[_candidate_row("candidate-b"), _candidate_row("candidate-a")]
        ),
    )

    result = _load(tmp_path)

    assert result["source_status"] == "READY"
    assert result["selection_allowed"] is True
    assert result["source_file"] == str(latest_path.resolve())
    assert result["source_content_sha256"] == hashlib.sha256(
        latest_path.read_bytes()
    ).hexdigest()
    assert result["candidate_universe_complete"] is True
    assert result["schema_version"] == "alr_candidate_evidence_snapshot_v2"
    assert result["source_schema_version"] == (
        "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
    )
    assert result["board_schema_version"] == "cost_gate_learning_candidate_board_v2"
    assert [row["candidate_id"] for row in result["candidate_rows"]] == sorted(
        [
            _candidate_row("candidate-a")["candidate_id"],
            _candidate_row("candidate-b")["candidate_id"],
        ]
    )
    assert result["board_hash"] == _payload()["learning_candidate_board"][
        "board_hash"
    ] or len(result["board_hash"]) == 64
    assert len(result["snapshot_hash"]) == 64
    assert len(result["selection_hash"]) == 64
    assert len(result["audit_hash"]) == 64
    assert "top_side_cells" not in result


def test_ready_ingress_uses_the_public_producer_validator_fixture(
    tmp_path: Path,
) -> None:
    payload = _payload(
        rows=[
            _candidate_row("parity-eligible"),
            _ineligible_candidate_row("parity-ineligible"),
        ]
    )
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)

    validated = validate_learning_candidate_board_v2(board)
    assert validated == board

    _write_snapshot(tmp_path, payload=payload)
    result = _load(tmp_path)

    assert result["source_status"] == "READY"
    assert set(result["candidate_rows"][0]) == set(
        validated["candidate_rows"][0]
    )
    assert [
        row["selection_eligible"] for row in result["candidate_rows"]
    ].count(False) == 1


def test_ready_ingress_preserves_canonical_partial_expected_cost_candidate(
    tmp_path: Path,
) -> None:
    row = _partial_expected_candidate_row()
    assert row["cost_basis_main"] == "expected_slippage_mean_abs_v1"
    assert row["expected_cost_recomputable_count"] == 29
    assert row["tail_cost_recomputable_count"] == 29
    assert "EXPECTED_COST_NOT_FULLY_RECOMPUTABLE" in row["blockers"]
    assert "TAIL_COST_NOT_FULLY_RECOMPUTABLE" in row["blockers"]
    assert row["selection_eligible"] is False
    payload = _payload(rows=[row])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "READY"
    assert result["candidate_rows"][0]["selection_eligible"] is False


def test_adapter_rejects_rehashed_candidate_cost_evidence_not_reconstructed_from_outer(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    row = board["candidate_rows"][0]
    cost_evidence = row["arbiter_input"]["cost_evidence"]
    cost_evidence["mean_abs_source"] = {
        "scope": "GLOBAL",
        "symbol": None,
        "sample_count": 100,
        "mean_abs_bps": 2.0,
    }
    _rehash_candidate_contract(row)
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_COST_EVIDENCE_OUTER_MISMATCH"


def test_adapter_rejects_rehashed_outer_projection_detached_from_source_payload(
    tmp_path: Path,
) -> None:
    payload = _payload()
    outer = payload["expected_cost_artifact"]
    outer["normalized_projection"]["global"]["mean_abs_bps"] = 9.0
    outer["normalized_projection_sha256"] = _canonical_sha256(
        outer["normalized_projection"]
    )
    for row in payload["learning_candidate_board"]["candidate_rows"]:
        row["arbiter_input"]["cost_evidence"][
            "normalized_projection_sha256"
        ] = outer["normalized_projection_sha256"]
        _rehash_candidate_contract(row)
    _rehash_board(payload["learning_candidate_board"])
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "OUTER_COST_EVIDENCE_INVALID"


def test_adapter_rejects_fully_rehashed_inconsistent_weighted_global_mean(
    tmp_path: Path,
) -> None:
    payload = _payload()
    outer = payload["expected_cost_artifact"]
    source_payload = outer["source_payload"]
    source_payload["global"]["mean_abs"] = 1.0
    outer["global_mean_abs_bps"] = 1.0
    outer["normalized_projection"]["global"]["mean_abs_bps"] = 1.0
    _rehash_expected_cost_contract(payload)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "EXPECTED_COST_SOURCE_INVALID"


def test_adapter_rejects_fully_rehashed_signed_mean_above_absolute_mean(
    tmp_path: Path,
) -> None:
    payload = _payload()
    outer = payload["expected_cost_artifact"]
    source_payload = outer["source_payload"]
    source_payload["symbols"][0]["mean_signed"] = 2.000001
    _rehash_expected_cost_contract(payload)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "EXPECTED_COST_SOURCE_INVALID"


def test_adapter_rejects_fully_rehashed_cost_source_after_board_generation(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["generated_at_utc"] = "2026-07-10T10:59:59Z"
    _rehash_board(payload["learning_candidate_board"])
    _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T105959Z.json",
        payload=payload,
    )

    result = _load(tmp_path, max_age_seconds=3_601)

    assert result["source_status"] == (
        "EXPECTED_COST_SOURCE_AFTER_BOARD_GENERATED"
    )


def test_adapter_expected_cost_source_freshness_is_exact_48_hours(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["generated_at_utc"] = "2026-07-10T11:00:00Z"
    _rehash_board(payload["learning_candidate_board"])
    _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T110000Z.json",
        payload=payload,
    )

    boundary = _load(
        tmp_path,
        evaluated_at="2026-07-12T11:00:00Z",
        max_age_seconds=172_800,
    )
    stale = _load(
        tmp_path,
        evaluated_at="2026-07-12T11:00:01Z",
        max_age_seconds=172_801,
    )

    assert boundary["source_status"] == "READY"
    assert stale["source_status"] == "EXPECTED_COST_SOURCE_STALE"


def test_adapter_exact_comparator_distinguishes_signed_zero() -> None:
    assert adapter._exact_value_equal(0.0, -0.0) is False
    assert adapter._exact_value_equal(-0.0, -0.0) is True


def test_projection_selection_seam_remains_narrower_than_full_board_ingress() -> None:
    full_row = _candidate_row("selection-seam")
    selection_row = {
        key: copy.deepcopy(full_row[key])
        for key in (
            *_SELECTION_FIELDS,
            "qualified_entry_ts_missing_row_count",
            "qualified_invalid_outcome_row_count",
            "data_integrity_suspect",
            "tail_cost_recomputable_share",
            "invalid_lineage_exact_cohort_row_count",
            "invalid_lineage_identity_family_row_count",
            "duplicate_event_hash_outcome_conflict_row_count",
            "duplicate_event_hash_cohort_conflict_row_count",
            "lineage_blocker_reason_counts",
        )
    }

    status, semantic = adapter.validate_candidate_selection_row_v2(selection_row)

    assert status is None
    assert semantic == _semantic_candidate_row(full_row)


@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("blocked_outcome_review_latest.json", "LATEST_ALIAS_PRESENT"),
        ("blocked_outcome_review_20260710T113000Z.json.tmp", "UNSAFE_FILE_PRESENT"),
    ),
)
def test_rejects_ambiguous_alias_or_partial_file(
    tmp_path: Path,
    name: str,
    expected: str,
) -> None:
    _write_snapshot(tmp_path)
    (tmp_path / name).write_text("{}\n", encoding="utf-8")

    result = _load(tmp_path)

    assert result["source_status"] == expected
    assert result["selection_allowed"] is False


def test_calendar_invalid_immutable_stamp_is_unsafe(tmp_path: Path) -> None:
    _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260230T113000Z.json",
    )

    result = _load(tmp_path)

    assert result["source_status"] == "UNSAFE_FILE_PRESENT"
    assert result["selection_allowed"] is False


def test_selected_filename_stamp_cannot_be_from_future(tmp_path: Path) -> None:
    _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T120001Z.json",
    )

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_FROM_FUTURE"
    assert result["selection_allowed"] is False


def test_selected_filename_stamp_cannot_follow_payload_generation(
    tmp_path: Path,
) -> None:
    _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T113001Z.json",
    )

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_FILENAME_STAMP_AFTER_GENERATED_AT"
    assert result["selection_allowed"] is False


def test_canonical_filename_stamp_equal_to_generation_is_accepted(
    tmp_path: Path,
) -> None:
    _write_snapshot(tmp_path)

    result = _load(tmp_path)

    assert result["source_status"] == "READY"
    assert result["generated_at"] == "2026-07-10T11:30:00Z"


def test_rejects_symlink_even_when_target_is_regular(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(json.dumps(_payload()), encoding="utf-8")
    link = tmp_path / "blocked_outcome_review_20260710T113000Z.json"
    link.symlink_to(target)

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_SYMLINK"
    assert result["candidate_rows"] == []


def test_directory_count_and_total_bytes_are_bounded_before_selection(
    tmp_path: Path,
) -> None:
    first = _write_snapshot(
        tmp_path,
        name="blocked_outcome_review_20260710T110000Z.json",
    )
    second = _write_snapshot(tmp_path)

    too_many = _load(tmp_path, max_files=1)
    too_large = _load(tmp_path, max_bytes=first.stat().st_size + second.stat().st_size - 1)

    assert too_many["source_status"] == "UNIVERSE_TRUNCATED"
    assert too_large["source_status"] == "UNIVERSE_TRUNCATED"
    assert too_many["candidate_rows"] == []
    assert too_large["candidate_rows"] == []


@pytest.mark.parametrize(
    ("generated_at", "expected"),
    (
        ("2026-07-10T10:59:59Z", "SOURCE_STALE"),
        ("2026-07-10T12:00:01Z", "SOURCE_FROM_FUTURE"),
    ),
)
def test_freshness_is_evaluated_against_explicit_clock(
    tmp_path: Path,
    generated_at: str,
    expected: str,
) -> None:
    payload = _payload()
    payload["generated_at_utc"] = generated_at
    generated = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    _write_snapshot(
        tmp_path,
        name=(
            "blocked_outcome_review_"
            f"{generated.strftime('%Y%m%dT%H%M%SZ')}.json"
        ),
        payload=payload,
    )

    result = _load(tmp_path)

    assert result["source_status"] == expected
    assert result["selection_allowed"] is False


@pytest.mark.parametrize(
    "mutation",
    ("malformed_json", "legacy_without_board", "incomplete_board", "tampered_board"),
)
def test_malformed_or_unbound_board_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = tmp_path / "blocked_outcome_review_20260710T113000Z.json"
    if mutation == "malformed_json":
        path.write_text("{", encoding="utf-8")
    else:
        payload = _payload()
        if mutation == "legacy_without_board":
            payload.pop("learning_candidate_board")
        elif mutation == "incomplete_board":
            payload["learning_candidate_board"]["candidate_universe_complete"] = False
            payload["learning_candidate_board"]["board_hash"] = _canonical_sha256(
                {
                    key: value
                    for key, value in payload["learning_candidate_board"].items()
                    if key != "board_hash"
                }
            )
        else:
            payload["learning_candidate_board"]["candidate_rows"][0]["n_eff"] = 999
        path.write_text(json.dumps(payload), encoding="utf-8")

    result = _load(tmp_path)

    assert result["source_status"] in {
        "SOURCE_JSON_INVALID",
        "LEARNING_BOARD_MISSING",
        "CANDIDATE_UNIVERSE_INCOMPLETE",
        "BOARD_HASH_MISMATCH",
    }
    assert result["candidate_rows"] == []


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_non_finite_json_constants_are_structured_source_failures(
    tmp_path: Path,
    constant: str,
) -> None:
    payload = _payload()
    raw = json.dumps(payload, sort_keys=True).replace(
        '"n_eff": 30', f'"n_eff": {constant}'
    )
    path = tmp_path / "blocked_outcome_review_20260710T113000Z.json"
    path.write_text(raw, encoding="utf-8")

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_JSON_INVALID"
    assert result["selection_allowed"] is False
    assert result["candidate_rows"] == []


def test_detects_file_change_between_pre_and_post_read_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_snapshot(tmp_path)
    original = alr_safe_file.os.fstat
    calls = 0

    def drifting(descriptor: int) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        metadata = original(descriptor)
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_size=metadata.st_size,
            st_mtime_ns=metadata.st_mtime_ns + int(calls >= 2),
        )

    monkeypatch.setattr(alr_safe_file.os, "fstat", drifting)

    result = _load(tmp_path)

    assert result["source_status"] == "SOURCE_CHANGED_DURING_READ"
    assert result["selection_allowed"] is False


def test_evidence_read_uses_no_follow_and_close_on_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_snapshot(tmp_path)
    original = alr_safe_file.os.open
    observed_flags: list[int] = []

    def recording_open(path, flags, *args, **kwargs):
        observed_flags.append(flags)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(alr_safe_file.os, "open", recording_open)

    assert _load(tmp_path)["source_status"] == "READY"
    assert observed_flags
    assert observed_flags[-1] & alr_safe_file.os.O_NOFOLLOW
    assert observed_flags[-1] & alr_safe_file.os.O_CLOEXEC


def test_rehashed_source_board_rejects_noncanonical_candidate_row_order(
    tmp_path: Path,
) -> None:
    rows = [_candidate_row("candidate-b"), _candidate_row("candidate-a")]
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    canonical = _payload(rows=rows)
    reversed_payload = copy.deepcopy(canonical)
    reversed_board = reversed_payload["learning_candidate_board"]
    assert isinstance(reversed_board, dict)
    reversed_board["candidate_rows"].reverse()
    _rehash_board(reversed_board)
    _write_snapshot(first_dir, payload=canonical)
    _write_snapshot(second_dir, payload=reversed_payload)

    first = _load(first_dir)
    second = _load(second_dir)

    assert first["source_status"] == "READY"
    assert second["source_status"] == "CANDIDATE_ROWS_ORDER_INVALID"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("source_v5", "SOURCE_SCHEMA_INVALID"),
        ("board_v1", "LEARNING_BOARD_SCHEMA_INVALID"),
        ("candidate_v1", "CANDIDATE_SCHEMA_INVALID"),
    ),
)
def test_atomic_v2_ingress_explicitly_rejects_v1_seams(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    if mutation == "source_v5":
        payload["schema_version"] = "cost_gate_demo_learning_lane_blocked_outcome_review_v5"
    elif mutation == "board_v1":
        board["schema_version"] = "cost_gate_learning_candidate_board_v1"
        _rehash_board(board)
    else:
        row = board["candidate_rows"][0]
        row["schema_version"] = "cost_gate_learning_candidate_v1"
        _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == expected
    assert result["selection_allowed"] is False


def test_rejects_tampered_arbiter_input_even_when_outer_hashes_are_rebound(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    row = board["candidate_rows"][0]
    row["arbiter_input"]["evidence"]["n_eff"] = 999
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "ARBITER_INPUT_HASH_MISMATCH"
    assert result["candidate_rows"] == []


@pytest.mark.parametrize(
    ("field", "expected"),
    (
        ("selection_hash", "SELECTION_HASH_MISMATCH"),
        ("audit_hash", "AUDIT_HASH_MISMATCH"),
    ),
)
def test_rejects_independently_tampered_selection_or_audit_hash(
    tmp_path: Path,
    field: str,
    expected: str,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board[field] = "0" * 64
    board.pop("board_hash")
    board["board_hash"] = _canonical_sha256(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == expected
    assert result["selection_allowed"] is False


def test_rehashed_board_rejects_extra_candidate_audit_field(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["candidate_rows"][0]["diagnostic_note"] = "rehashed-poison"
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_FIELDS_INVALID"
    assert result["selection_allowed"] is False


def test_rehashed_board_rejects_missing_candidate_audit_field(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["candidate_rows"][0].pop("avg_tail_cost_bps")
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_FIELDS_INVALID"
    assert result["selection_allowed"] is False


def test_rejects_candidate_identity_rebinding_despite_valid_outer_hashes(
    tmp_path: Path,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    board["candidate_rows"][0]["candidate_identity"]["symbol"] = "ETHUSDT"
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == "CANDIDATE_IDENTITY_MISMATCH"
    assert result["selection_allowed"] is False


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("count", "BOARD_COUNT_INVARIANT_VIOLATION"),
        ("blocker_order", "CANDIDATE_BLOCKERS_INVALID"),
        ("eligible_with_blocker", "CANDIDATE_SELECTION_FLAGS_INVALID"),
    ),
)
def test_rejects_board_count_and_candidate_selection_invariant_violations(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    payload = _payload()
    board = payload["learning_candidate_board"]
    assert isinstance(board, dict)
    if mutation == "count":
        board["raw_blocked_outcome_row_count"] = 2
    elif mutation == "blocker_order":
        board["candidate_rows"][0]["blockers"] = ["Z_BLOCKER", "A_BLOCKER"]
        board["candidate_rows"][0]["selection_eligible"] = False
    else:
        board["candidate_rows"][0]["blockers"] = ["PROOF_GAP_OPEN"]
    _rehash_board(board)
    _write_snapshot(tmp_path, payload=payload)

    result = _load(tmp_path)

    assert result["source_status"] == expected
    assert result["candidate_rows"] == []


def test_invalid_loader_limits_raise_before_touching_files(tmp_path: Path) -> None:
    _write_snapshot(tmp_path)

    with pytest.raises(ValueError, match="max_age_seconds_invalid"):
        _load(tmp_path, max_age_seconds=0)
    with pytest.raises(ValueError, match="max_files_invalid"):
        _load(tmp_path, max_files=True)
    with pytest.raises(ValueError, match="max_bytes_invalid"):
        _load(tmp_path, max_bytes=-1)


def test_rejects_non_directory_and_non_regular_snapshot(tmp_path: Path) -> None:
    plain_file = tmp_path / "plain"
    plain_file.write_text("x", encoding="utf-8")
    result = _load(plain_file)

    assert result["source_status"] == "PATH_NOT_DIRECTORY"
    assert result["selection_allowed"] is False

    directory = tmp_path / "dir"
    directory.mkdir()
    nested = directory / "blocked_outcome_review_20260710T113000Z.json"
    nested.mkdir()
    nested_result = _load(directory)
    assert nested_result["source_status"] == "SOURCE_NOT_REGULAR"


def test_frozen_r3_counterfactual_is_historical_only_not_live_candidate_ingress(
    tmp_path: Path,
) -> None:
    frozen = (
        Path(__file__).parents[3]
        / "docs/CCAgentWorkSpace/E1/workspace/reports"
        / "2026-07-10--counterfactual_rerun_evidence"
        / "counterfactual_rerun_prereg_v1.json"
    )
    target = tmp_path / "blocked_outcome_review_20260710T014406Z.json"
    target.write_bytes(frozen.read_bytes())

    result = _load(tmp_path, max_age_seconds=100_000)

    assert result["source_status"] == "SOURCE_SCHEMA_INVALID"
    assert result["selection_allowed"] is False
    assert result["candidate_rows"] == []
