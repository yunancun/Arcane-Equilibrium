"""Candidate board v2 prospective-lineage 與審計分離攻擊測試。

MODULE_NOTE
模塊用途：驗證 blocked outcome 必須先通過 immutable raw/evaluation lineage，
才可進入 cohort 統計與 arbiter selection；legacy/invalid rows 僅能影響審計面。
主要接口：``build_blocked_signal_outcome_review``。
依賴：``candidate_lineage_v2_test_support`` 公開 fixture factory。
硬邊界：測試不得從目前 config/HEAD 回填 lineage，也不得把 audit volume 洗入 n_eff。
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest

from helper_scripts.research.tests.candidate_lineage_v2_test_support import (
    attach_candidate_lineage_v2,
)
from cost_gate_learning_lane import candidate_board as candidate_board_module
from cost_gate_learning_lane.outcome_review import (
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.candidate_board_validation import (
    validate_learning_candidate_board_v2,
)


NOW = dt.datetime(2026, 7, 10, 18, tzinfo=dt.timezone.utc)


def _outcome(*, attempt_id: str, realized_net_bps: float = -1.0) -> dict[str, object]:
    return {
        "record_type": "blocked_signal_outcome",
        "attempt_id": attempt_id,
        "side_cell_key": "ma_crossover|BTCUSDT|Buy",
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "horizon_minutes": 60,
        "entry_ts_ms": int(
            dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        "gross_bps": realized_net_bps + 12.0,
        "realized_net_bps": realized_net_bps,
        "net_bps_optimistic": realized_net_bps + 8.0,
        "cost_bps": 12.0,
        "cost_model_version": "conservative_v1",
    }


def _qualified(
    *, context_id: str = "ctx-board-v2-001", **kwargs: object
) -> dict[str, object]:
    outcome = _outcome(attempt_id=context_id)
    if "captured_at_ms" in kwargs:
        outcome["entry_ts_ms"] = kwargs["captured_at_ms"]
    return attach_candidate_lineage_v2(
        outcome,
        context_id=context_id,
        as_of_utc_date=NOW.date().isoformat(),
        **kwargs,
    )


def _board(rows: list[dict[str, object]]) -> dict[str, object]:
    return build_blocked_signal_outcome_review(rows, now_utc=NOW)[
        "learning_candidate_board"
    ]


def test_legacy_rows_are_audit_only_and_cannot_change_qualified_selection() -> None:
    qualified = _qualified()
    baseline = _board([qualified])
    legacy = _outcome(attempt_id="legacy-no-prospective-lineage")

    attacked = _board([legacy, qualified])

    assert attacked["schema_version"] == "cost_gate_learning_candidate_board_v2"
    assert attacked["raw_blocked_outcome_row_count"] == 2
    assert attacked["qualified_lineage_outcome_row_count"] == 1
    assert attacked["unqualified_lineage_outcome_row_count"] == 1
    assert attacked["invalid_lineage_outcome_row_count"] == 0
    assert attacked["lineage_partition_complete"] is True
    assert attacked["candidate_rows"] == baseline["candidate_rows"]
    assert attacked["selection_hash"] == baseline["selection_hash"]
    assert attacked["audit_hash"] != baseline["audit_hash"]
    assert attacked["board_hash"] != baseline["board_hash"]


def test_raw_valid_missing_evaluation_and_outside_window_are_unqualified() -> None:
    raw_only = _qualified(context_id="ctx-raw-only")
    raw_summary = copy.deepcopy(raw_only["candidate_summary"])
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_summary.pop(field)
    raw_only["candidate_summary"] = raw_summary
    outside_ts = int(
        dt.datetime(2026, 7, 2, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    outside = attach_candidate_lineage_v2(
        _outcome(attempt_id="ctx-outside-window"),
        context_id="ctx-outside-window",
        captured_at_ms=outside_ts,
        as_of_utc_date=NOW.date().isoformat(),
        require_event_in_window=False,
    )

    board = _board([outside, raw_only])

    assert board["candidate_rows"] == []
    assert board["raw_blocked_outcome_row_count"] == 2
    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["unqualified_lineage_outcome_row_count"] == 2
    assert board["invalid_lineage_outcome_row_count"] == 0
    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["unqualified_event_outside_evaluation_window_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW": 1,
        "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING": 1,
    }


def test_stale_invalid_exact_only_row_is_audit_only_and_board_validates() -> None:
    event_ts_ms = int(
        dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    stale = attach_candidate_lineage_v2(
        _outcome(attempt_id="ctx-stale-invalid-exact-only"),
        context_id="ctx-stale-invalid-exact-only",
        captured_at_ms=event_ts_ms,
        as_of_utc_date="2026-07-17",
        require_event_in_window=False,
    )
    stale["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"

    board = _board([stale])

    assert board["candidate_rows"] == []
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    assert validate_learning_candidate_board_v2(board) == board


def test_stale_qualified_lineage_is_demoted_to_audit_only_exact_invalid() -> None:
    event_ts_ms = int(
        dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    stale = attach_candidate_lineage_v2(
        _outcome(attempt_id="ctx-stale-qualified-lineage"),
        context_id="ctx-stale-qualified-lineage",
        captured_at_ms=event_ts_ms,
        as_of_utc_date="2026-07-09",
    )

    board = _board([stale])

    assert board["candidate_rows"] == []
    assert board["qualified_lineage_outcome_row_count"] == 0
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_EXACT_COHORT": 1
    }
    assert validate_learning_candidate_board_v2(board) == board


def test_stale_invalid_exact_hash_quarantines_addressable_current_cohort() -> None:
    context_id = "ctx-stale-invalid-exact-addressable"
    event_ts_ms = int(
        dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    qualified = _qualified(context_id=context_id, captured_at_ms=event_ts_ms)
    stale = attach_candidate_lineage_v2(
        _outcome(attempt_id=context_id),
        context_id=context_id,
        captured_at_ms=event_ts_ms,
        as_of_utc_date="2026-07-17",
        require_event_in_window=False,
    )
    stale["side_cell_key"] = "ma_crossover|BTCUSDT|Sell"

    board = _board([stale, qualified])

    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert len(board["candidate_rows"]) == 1
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["invalid_lineage_exact_cohort_row_count"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2
    assert "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT" in candidate["blockers"]
    assert validate_learning_candidate_board_v2(board) == board


def test_raw_valid_unqualified_outcome_conflict_quarantines_qualified_copy() -> None:
    qualified = _qualified(context_id="ctx-qualified-raw-only-conflict")
    raw_only = copy.deepcopy(qualified)
    raw_only["realized_net_bps"] = qualified["realized_net_bps"] + 1.0
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)

    board = _board([qualified, raw_only])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert board["conflicting_duplicate_event_hash_attribution_row_count"] == 2
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 1
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["n_eff"] == 0
    assert candidate["conflicting_event_hash_row_count"] == 2
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2
    assert candidate["lineage_blocker_reason_counts"] == {
        "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT": 2
    }
    assert "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT" in candidate["blockers"]


def test_outside_window_unqualified_conflict_maps_to_existing_finite_window() -> None:
    captured_at_ms = int(
        dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    context_id = "ctx-qualified-outside-window-conflict"
    qualified = _qualified(
        context_id=context_id,
        captured_at_ms=captured_at_ms,
    )
    outside = attach_candidate_lineage_v2(
        _outcome(attempt_id=context_id),
        context_id=context_id,
        captured_at_ms=captured_at_ms,
        as_of_utc_date="2026-07-17",
        require_event_in_window=False,
    )
    outside["realized_net_bps"] = qualified["realized_net_bps"] + 2.0

    board = _board([outside, qualified])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["unqualified_event_outside_evaluation_window_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert board["conflicting_duplicate_event_hash_attribution_row_count"] == 2
    assert len(board["candidate_rows"]) == 1
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 1
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["n_eff"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2


def test_consistent_raw_only_unqualified_copy_does_not_poison_denominator() -> None:
    qualified = _qualified(context_id="ctx-qualified-raw-only-consistent")
    raw_only = copy.deepcopy(qualified)
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)

    baseline = _board([qualified])
    board = _board([raw_only, qualified])

    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 0
    assert board["consistent_duplicate_event_hash_extra_row_count"] == 0
    assert board["candidate_rows"] == baseline["candidate_rows"]
    assert board["candidate_rows"][0]["qualified_evaluator_input_count"] == 1
    assert board["candidate_rows"][0]["n_eff"] == 1


def test_missing_raw_status_has_one_exact_unqualified_exception() -> None:
    absent = _outcome(attempt_id="ctx-raw-absent")
    explicit_missing = {
        **_outcome(attempt_id="ctx-raw-explicit-missing"),
        "candidate_summary": {
            "candidate_event_context_status": "UNQUALIFIED_CONTEXT_MISSING"
        },
    }
    legacy_only = {
        **_outcome(attempt_id="ctx-legacy-only"),
        "candidate_summary": {"candidate_learning_context": {"legacy": True}},
    }
    invalid_valid_status = {
        **_outcome(attempt_id="ctx-raw-status-valid-without-payload"),
        "candidate_summary": {"candidate_event_context_status": "VALID"},
    }
    invalid_other_status = {
        **_outcome(attempt_id="ctx-raw-status-other-without-payload"),
        "candidate_summary": {"candidate_event_context_status": "BROKEN"},
    }

    board = _board(
        [
            invalid_other_status,
            legacy_only,
            explicit_missing,
            invalid_valid_status,
            absent,
        ]
    )

    assert board["candidate_rows"] == []
    assert board["raw_blocked_outcome_row_count"] == 5
    assert board["unqualified_lineage_outcome_row_count"] == 3
    assert board["invalid_lineage_outcome_row_count"] == 2
    assert board["unassigned_invalid_lineage_outcome_row_count"] == 2
    assert board["lineage_exclusion_reason_counts"] == {
        "INVALID_LINEAGE_RAW_CONTEXT_INVALID": 2,
        "UNQUALIFIED_CONTEXT_MISSING": 2,
        "UNQUALIFIED_LEGACY_PROJECTION_ONLY": 1,
    }


def test_unassigned_invalid_changes_only_audit_and_full_board_hash() -> None:
    qualified = _qualified(context_id="ctx-unassigned-baseline")
    poison = {
        **_outcome(attempt_id="ctx-unassigned-invalid"),
        "candidate_summary": {
            "candidate_event_context_status": "VALID",
            "candidate_evaluation_context_status": "VALID",
        },
    }

    baseline = _board([qualified])
    attacked = _board([poison, qualified])
    reversed_board = _board([qualified, poison])

    assert attacked == reversed_board
    assert attacked["candidate_rows"] == baseline["candidate_rows"]
    assert attacked["selection_hash"] == baseline["selection_hash"]
    assert attacked["audit_hash"] != baseline["audit_hash"]
    assert attacked["board_hash"] != baseline["board_hash"]
    assert attacked["invalid_lineage_outcome_row_count"] == 1
    assert attacked["unassigned_invalid_lineage_outcome_row_count"] == 1
    assert attacked["invalid_exact_cohort_row_count"] == 0
    assert attacked["invalid_identity_family_row_count"] == 0
    assert (
        attacked["raw_blocked_outcome_row_count"]
        == attacked["qualified_lineage_outcome_row_count"]
        + attacked["unqualified_lineage_outcome_row_count"]
        + attacked["invalid_lineage_outcome_row_count"]
    )


def test_per_event_hash_and_regime_label_churn_do_not_split_stable_cohort() -> None:
    first = _qualified(
        context_id="ctx-regime-bear",
        captured_at_ms=int(
            dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        evidence_regime_label="bear|low_vol|liquid",
    )
    second = _qualified(
        context_id="ctx-regime-bull",
        captured_at_ms=int(
            dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        evidence_regime_label="bull|high_vol|thin",
    )

    board = _board([second, first])

    assert len(board["candidate_rows"]) == 1
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 2
    assert candidate["regime_entry_counts"]["bear|low_vol|liquid"] == 1
    assert candidate["regime_entry_counts"]["bull|high_vol|thin"] == 1
    assert candidate["n_eff"] == 2


def test_stable_projection_split_requires_unique_candidate_id_context_hash() -> None:
    baseline = _qualified(context_id="ctx-stable-a")
    collision = _qualified(
        context_id="ctx-stable-b",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
        },
    )

    with pytest.raises(ValueError, match="CANDIDATE_ID_COLLISION"):
        _board([baseline, collision])

    separated = _qualified(
        context_id="ctx-stable-c",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )
    board = _board([baseline, separated])
    assert len(board["candidate_rows"]) == 2
    assert len({row["stable_cohort_hash"] for row in board["candidate_rows"]}) == 2
    assert len({row["candidate_id"] for row in board["candidate_rows"]}) == 2


@pytest.mark.parametrize(
    ("field", "poison"),
    (
        ("strategy_name", "other_strategy"),
        ("symbol", "ETHUSDT"),
        ("side", "Sell"),
        ("horizon_minutes", 60.0),
        ("event_ts_ms", 1.0),
        ("attempt_id", "grafted-attempt"),
        ("side_cell_key", "ma_crossover|BTCUSDT|Sell"),
    ),
)
def test_every_outer_identity_graft_is_exact_cohort_invalid(
    field: str, poison: object
) -> None:
    valid = _qualified(context_id="ctx-outer-valid")
    grafted = _qualified(
        context_id=f"ctx-outer-graft-{field}",
        captured_at_ms=int(
            dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    grafted[field] = poison

    board = _board([valid, grafted])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["invalid_lineage_outcome_row_count"] == 1
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["invalid_identity_family_row_count"] == 0
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 1
    assert candidate["invalid_lineage_exact_cohort_row_count"] == 1
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" in candidate["blockers"]
    assert candidate["arbiter_input_complete"] is False
    assert candidate["selection_eligible"] is False
    assert candidate["qualified_metrics_actionable"] is False
    assert candidate["metrics_scope"] == "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"


def test_exact_and_family_invalid_rows_block_only_addressable_cohorts() -> None:
    baseline = _qualified(
        context_id="ctx-attribution-base",
        captured_at_ms=int(
            dt.datetime(2026, 7, 7, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    other_regime = _qualified(
        context_id="ctx-attribution-other-regime",
        captured_at_ms=int(
            dt.datetime(2026, 7, 8, 12, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
        stable_projection_overrides={
            "target_regime_context": {"label": "bull|high_vol|thin"},
        },
    )
    exact_invalid = _qualified(
        context_id="ctx-attribution-exact-invalid",
        captured_at_ms=int(
            dt.datetime(2026, 7, 9, 10, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    exact_summary = copy.deepcopy(exact_invalid["candidate_summary"])
    exact_summary["candidate_learning_context_projection"]["portfolio"][
        "beta_to_portfolio"
    ] = "0.9"
    exact_invalid["candidate_summary"] = exact_summary

    family_invalid = _qualified(
        context_id="ctx-attribution-family-invalid",
        captured_at_ms=int(
            dt.datetime(2026, 7, 9, 14, tzinfo=dt.timezone.utc).timestamp()
            * 1_000
        ),
    )
    family_summary = copy.deepcopy(family_invalid["candidate_summary"])
    family_summary.pop("candidate_evaluation_context")
    family_invalid["candidate_summary"] = family_summary

    board = _board([other_regime, exact_invalid, family_invalid, baseline])

    assert board["qualified_lineage_outcome_row_count"] == 2
    assert board["invalid_lineage_outcome_row_count"] == 2
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["invalid_identity_family_row_count"] == 1
    assert board["unassigned_invalid_lineage_outcome_row_count"] == 0
    assert board["conflicting_duplicate_event_hash_row_count"] == 0
    assert len(board["candidate_rows"]) == 2
    exact_scoped = next(
        row
        for row in board["candidate_rows"]
        if row["invalid_lineage_exact_cohort_row_count"] == 1
    )
    family_only = next(
        row
        for row in board["candidate_rows"]
        if row["invalid_lineage_exact_cohort_row_count"] == 0
    )
    assert exact_scoped["invalid_lineage_identity_family_row_count"] == 1
    assert family_only["invalid_lineage_identity_family_row_count"] == 1
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" in exact_scoped["blockers"]
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" not in family_only["blockers"]
    assert all(
        "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT" in row["blockers"]
        for row in board["candidate_rows"]
    )
    assert all(
        row["conflicting_event_hash_row_count"] == 0
        for row in board["candidate_rows"]
    )


def test_consistent_duplicate_event_hash_is_audit_only_and_permutation_stable() -> None:
    first = _qualified(context_id="ctx-duplicate-consistent")
    second = copy.deepcopy(first)
    first["generated_at_utc"] = "2026-07-10T12:00:00Z"
    second["generated_at_utc"] = "2026-07-10T12:01:00Z"

    forward = _board([first, second])
    reverse = _board([second, first])
    baseline = _board([first])

    assert forward == reverse
    assert forward["selection_hash"] == baseline["selection_hash"]
    assert forward["audit_hash"] != baseline["audit_hash"]
    assert forward["consistent_duplicate_event_hash_extra_row_count"] == 1
    assert forward["conflicting_duplicate_event_hash_row_count"] == 0
    candidate = forward["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 2
    assert candidate["qualified_evaluator_input_count"] == 1
    assert candidate["consistent_duplicate_event_hash_extra_row_count"] == 1
    assert candidate["conflicting_event_hash_row_count"] == 0
    assert candidate["n_eff"] == baseline["candidate_rows"][0]["n_eff"] == 1


def test_duplicate_event_hash_tolerance_chain_is_permutation_stable() -> None:
    """Pairwise tolerance must not let input order choose conflict vs denominator."""
    baseline = _qualified(context_id="ctx-duplicate-tolerance-chain")
    rows = []
    for delta in (0.0, 0.75e-9, 1.5e-9):
        row = copy.deepcopy(baseline)
        row["realized_net_bps"] = float(row["realized_net_bps"]) + delta
        rows.append(row)

    low_first = _board(rows)
    middle_first = _board([rows[1], rows[0], rows[2]])

    assert low_first == middle_first
    assert low_first["conflicting_duplicate_event_hash_row_count"] == 3
    assert low_first["consistent_duplicate_event_hash_extra_row_count"] == 0
    candidate = low_first["candidate_rows"][0]
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 3


def test_duplicate_event_hash_group_comparison_is_linear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _qualified(context_id="ctx-duplicate-linear-group")
    rows = [copy.deepcopy(baseline) for _ in range(1_000)]
    original = candidate_board_module._duplicate_semantics_equal
    calls = 0

    def counted(left: object, right: object) -> bool:
        nonlocal calls
        calls += 1
        if calls > 2_000:
            raise AssertionError("duplicate group comparison exceeded linear budget")
        return original(left, right)

    monkeypatch.setattr(
        candidate_board_module,
        "_duplicate_semantics_equal",
        counted,
    )

    board = _board(rows)

    assert calls <= len(rows)
    assert board["consistent_duplicate_event_hash_extra_row_count"] == 999
    assert board["conflicting_duplicate_event_hash_row_count"] == 0


def test_multi_cohort_duplicate_attribution_is_linear_and_permutation_stable() -> None:
    class CountedCohort(str):
        comparisons = 0

        def __eq__(self, other: object) -> bool:
            type(self).comparisons += 1
            return super().__eq__(other)

        __hash__ = str.__hash__

    cohort_count = 512
    qualified = [
        {
            "event_hash": "e" * 64,
            "stable_cohort_hash": CountedCohort(f"{index:064x}"),
            "row": {},
        }
        for index in range(cohort_count)
    ]

    CountedCohort.comparisons = 0
    forward = candidate_board_module._gate_duplicate_event_hashes(qualified, [])
    forward_comparisons = CountedCohort.comparisons
    CountedCohort.comparisons = 0
    reverse = candidate_board_module._gate_duplicate_event_hashes(
        list(reversed(qualified)),
        [],
    )
    reverse_comparisons = CountedCohort.comparisons

    assert forward == reverse
    assert forward[3] == cohort_count
    assert forward_comparisons <= cohort_count * 8
    assert reverse_comparisons <= cohort_count * 8


def test_qualified_and_unqualified_duplicate_extremes_share_one_range() -> None:
    qualified = _qualified(context_id="ctx-duplicate-mixed-range")
    raw_only_low = copy.deepcopy(qualified)
    raw_only_high = copy.deepcopy(qualified)
    for row in (raw_only_low, raw_only_high):
        for field in (
            "candidate_evaluation_context",
            "candidate_evaluation_context_status",
            "candidate_learning_context_projection",
        ):
            row["candidate_summary"].pop(field)
    raw_only_low["realized_net_bps"] = float(qualified["realized_net_bps"]) - 0.75e-9
    raw_only_high["realized_net_bps"] = float(qualified["realized_net_bps"]) + 0.75e-9

    forward = _board([raw_only_low, qualified, raw_only_high])
    reverse = _board([raw_only_high, qualified, raw_only_low])

    assert forward == reverse
    assert forward["conflicting_duplicate_event_hash_row_count"] == 3
    candidate = forward["candidate_rows"][0]
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 3


def test_censored_duplicate_event_hash_does_not_inflate_censoring_share() -> None:
    first = _qualified(context_id="ctx-duplicate-censored")
    first.update(
        {
            "censored": True,
            "censor_reason": "price_observation_missing",
            "gross_bps": None,
            "cost_bps": None,
            "realized_net_bps": None,
            "net_bps_optimistic": None,
        }
    )
    second = copy.deepcopy(first)

    single = _board([first])["candidate_rows"][0]
    duplicate = _board([second, first])["candidate_rows"][0]

    assert duplicate["qualified_raw_outcome_count"] == 2
    assert duplicate["qualified_evaluator_input_count"] == 1
    assert duplicate["qualified_censored_outcome_count"] == 1
    assert duplicate["qualified_uncensored_outcome_count"] == 0
    assert duplicate["censored_share"] == single["censored_share"] == 1.0
    assert duplicate["consistent_duplicate_event_hash_extra_row_count"] == 1


def test_duplicate_event_outcome_conflict_quarantines_every_copy() -> None:
    first = _qualified(context_id="ctx-duplicate-outcome-conflict")
    second = copy.deepcopy(first)
    second["realized_net_bps"] = first["realized_net_bps"] + 1.0

    forward = _board([first, second])
    reverse = _board([second, first])

    assert forward == reverse
    assert forward["conflicting_duplicate_event_hash_row_count"] == 2
    assert forward[
        "conflicting_duplicate_event_hash_attribution_row_count"
    ] == sum(
        row["conflicting_event_hash_row_count"]
        for row in forward["candidate_rows"]
    )
    candidate = forward["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 2
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["conflicting_event_hash_row_count"] == 2
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2
    assert candidate["n_eff"] == 0
    assert "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT" in candidate["blockers"]
    assert candidate["arbiter_input_complete"] is False
    assert candidate["selection_eligible"] is False


def test_duplicate_event_hash_across_stable_cohorts_blocks_each_cohort() -> None:
    first = _qualified(context_id="ctx-duplicate-cross-cohort")
    second = _qualified(
        context_id="ctx-duplicate-cross-cohort",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )

    board = _board([second, first])

    assert board["qualified_lineage_outcome_row_count"] == 2
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    assert len(board["candidate_rows"]) == 2
    for candidate in board["candidate_rows"]:
        assert candidate["qualified_evaluator_input_count"] == 0
        assert candidate["duplicate_event_hash_cohort_conflict_row_count"] == 1
        assert "DUPLICATE_EVENT_HASH_COHORT_CONFLICT" in candidate["blockers"]


def test_multi_cohort_unqualified_attribution_can_exceed_unique_conflict_count() -> None:
    first = _qualified(context_id="ctx-duplicate-cross-cohort-unqualified")
    second = _qualified(
        context_id="ctx-duplicate-cross-cohort-unqualified",
        stable_projection_overrides={
            "portfolio": {"beta_to_portfolio": "0.75"},
            "context_hashes": {"portfolio": "7" * 64},
        },
    )
    raw_only = copy.deepcopy(first)
    for field in (
        "candidate_evaluation_context",
        "candidate_evaluation_context_status",
        "candidate_learning_context_projection",
    ):
        raw_only["candidate_summary"].pop(field)

    board = _board([raw_only, second, first])

    assert board["qualified_lineage_outcome_row_count"] == 2
    assert board["unqualified_raw_valid_evaluation_missing_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 3
    assert board["conflicting_duplicate_event_hash_attribution_row_count"] == 4
    assert len(board["candidate_rows"]) == 2
    for candidate in board["candidate_rows"]:
        assert candidate["qualified_raw_outcome_count"] == 1
        assert candidate["qualified_evaluator_input_count"] == 0
        assert candidate["conflicting_event_hash_row_count"] == 2
        assert candidate["duplicate_event_hash_cohort_conflict_row_count"] == 2


def test_addressable_invalid_copy_participates_in_event_hash_conflict_gate() -> None:
    valid = _qualified(context_id="ctx-duplicate-invalid-copy")
    invalid = copy.deepcopy(valid)
    invalid["candidate_summary"]["candidate_learning_context_projection"]["proof"][
        "proof_stage"
    ] = 0

    board = _board([valid, invalid])

    assert board["qualified_lineage_outcome_row_count"] == 1
    assert board["invalid_exact_cohort_row_count"] == 1
    assert board["conflicting_duplicate_event_hash_row_count"] == 2
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_evaluator_input_count"] == 0
    assert candidate["duplicate_event_hash_outcome_conflict_row_count"] == 2
    assert "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT" in candidate["blockers"]
    assert "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT" in candidate["blockers"]


def test_invalid_outcome_stays_qualified_and_censoring_uses_c_plus_u() -> None:
    rows = []
    base_ts = int(
        dt.datetime(2026, 7, 8, 0, tzinfo=dt.timezone.utc).timestamp() * 1_000
    )
    for index in range(10):
        row = _qualified(
            context_id=f"ctx-denominator-{index}",
            captured_at_ms=base_ts + index * 2 * 3_600_000,
        )
        if index < 3:
            row.update(
                {
                    "censored": True,
                    "censor_reason": "price_observation_missing",
                    "gross_bps": None,
                    "cost_bps": None,
                    "realized_net_bps": None,
                    "net_bps_optimistic": None,
                }
            )
        elif index == 3:
            row["realized_net_bps"] = None
        rows.append(row)

    board = _board(list(reversed(rows)))

    assert board["qualified_lineage_outcome_row_count"] == 10
    assert board["invalid_lineage_outcome_row_count"] == 0
    candidate = board["candidate_rows"][0]
    assert candidate["qualified_raw_outcome_count"] == 10
    assert candidate["qualified_evaluator_input_count"] == 10
    assert candidate["qualified_censored_outcome_count"] == 3
    assert candidate["qualified_uncensored_outcome_count"] == 7
    assert candidate["qualified_valid_uncensored_outcome_count"] == 6
    assert candidate["qualified_invalid_outcome_row_count"] == 1
    assert candidate["censored_share"] == pytest.approx(3.0 / 10.0)
    assert "INVALID_OUTCOME_ROWS_PRESENT" in candidate["blockers"]
    assert candidate["qualified_metrics_actionable"] is False
    assert candidate["selection_eligible"] is False
