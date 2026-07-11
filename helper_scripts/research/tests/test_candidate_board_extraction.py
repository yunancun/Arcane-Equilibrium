"""Candidate-board Module extraction characterization tests."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from helper_scripts.research.tests.candidate_lineage_v2_test_support import (
    attach_candidate_lineage_v2,
)
from cost_gate_learning_lane import candidate_board
from cost_gate_learning_lane import candidate_board_validation
from cost_gate_learning_lane import outcome_review
from cost_gate_learning_lane.slippage_quantile_artifact import (
    build_slippage_quantile_artifact,
)


AS_OF_DATE = dt.date(2026, 7, 4)


def _legacy_row(*, attempt_id: str = "legacy-1") -> dict[str, object]:
    return {
        "record_type": "blocked_signal_outcome",
        "attempt_id": attempt_id,
        "side_cell_key": "strat|BTCUSDT|Buy",
        "strategy_name": "strat",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "horizon_minutes": 60,
        "entry_ts_ms": 1_782_000_000_000,
        "gross_bps": 12.0,
        "realized_net_bps": 8.0,
        "net_bps_optimistic": 8.0,
        "cost_bps": 4.0,
    }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _typed_row(
    *,
    attempt_id: str,
    entry_ts_ms: int,
    realized_net_bps: float,
    regime_label: str,
    hidden_oos_consumed: bool = False,
) -> dict[str, object]:
    row = _legacy_row(attempt_id=attempt_id)
    row.update(
        {
            "entry_ts_ms": entry_ts_ms,
            "gross_bps": realized_net_bps + 12.0,
            "realized_net_bps": realized_net_bps,
            "net_bps_optimistic": realized_net_bps + 8.0,
            "cost_bps": 12.0,
            "cost_model_version": "conservative_v1",
        }
    )
    overrides = None
    if hidden_oos_consumed:
        overrides = {
            "hidden_oos_state": {
                "state": "consumed",
                "open_count": 1,
                "opened_for_iteration": True,
                "consumed": True,
            },
            "context_hashes": {"data": "8" * 64},
        }
    return attach_candidate_lineage_v2(
        row,
        context_id=attempt_id,
        captured_at_ms=entry_ts_ms,
        strategy_name="strat",
        symbol="BTCUSDT",
        side="Buy",
        horizon_minutes=60,
        as_of_utc_date=AS_OF_DATE.isoformat(),
        evidence_regime_label=regime_label,
        evidence_engine_mode="demo",
        stable_projection_overrides=overrides,
    )


def _build_extracted_board(rows: list[dict[str, object]]) -> dict[str, object]:
    return candidate_board.build_learning_candidate_board(
        rows,
        cfg=outcome_review.BlockedOutcomeReviewConfig(),
        overlay={},
        edge_estimates={},
        expected_slippage=None,
        as_of_date=AS_OF_DATE,
        cohort_evaluator=outcome_review._evaluate_candidate_cohort,
    )


def test_exact_board_comparators_distinguish_signed_zero() -> None:
    assert candidate_board._exact_value_equal(0.0, -0.0) is False
    assert candidate_board._exact_value_equal(-0.0, -0.0) is True
    assert candidate_board_validation._exact_value_equal(0.0, -0.0) is False
    assert candidate_board_validation._exact_value_equal(-0.0, -0.0) is True


def test_facade_and_extracted_module_emit_byte_identical_board_and_hash() -> None:
    rows = [_legacy_row()]
    cfg = outcome_review.BlockedOutcomeReviewConfig()

    facade = outcome_review._build_learning_candidate_board(
        rows,
        cfg=cfg,
        overlay={},
        edge_estimates={},
        expected_slippage=None,
        as_of_date=AS_OF_DATE,
    )
    extracted = candidate_board.build_learning_candidate_board(
        rows,
        cfg=cfg,
        overlay={},
        edge_estimates={},
        expected_slippage=None,
        as_of_date=AS_OF_DATE,
        cohort_evaluator=outcome_review._evaluate_candidate_cohort,
    )

    assert facade == extracted
    assert extracted["as_of_utc_date"] == AS_OF_DATE.isoformat()
    assert facade["board_hash"] == extracted["board_hash"]
    assert _canonical_bytes(facade) == _canonical_bytes(extracted)


def test_expected_cost_provenance_is_typed_inside_arbiter_input() -> None:
    """Expected-cost basis must travel as typed, hash-bound evidence beside context cost."""
    now = dt.datetime.combine(AS_OF_DATE, dt.time(12), tzinfo=dt.timezone.utc)
    artifact = build_slippage_quantile_artifact(
        [
            {
                "symbol": None,
                "n": 200,
                "mean_abs": 1.5,
                "mean_signed": 0.5,
                "q50": 1.0,
                "q75": 3.0,
                "q90": 6.0,
                "cvar90": 7.0,
            },
            {
                "symbol": "BTCUSDT",
                "n": 200,
                "mean_abs": 1.5,
                "mean_signed": 0.25,
                "q50": 0.75,
                "q75": 2.5,
                "q90": 5.0,
                "cvar90": 6.0,
            },
        ],
        now_utc=now,
    )
    expected = outcome_review._load_expected_slippage(artifact, now=now)
    assert expected is not None
    row = _typed_row(
        attempt_id="typed-cost-evidence",
        entry_ts_ms=int(
            dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
        ),
        realized_net_bps=1.0,
        regime_label="neutral|low_vol|liquid",
    )

    board = candidate_board.build_learning_candidate_board(
        [row],
        cfg=outcome_review.BlockedOutcomeReviewConfig(),
        overlay={},
        edge_estimates={},
        expected_slippage=expected,
        as_of_date=AS_OF_DATE,
        cohort_evaluator=outcome_review._evaluate_candidate_cohort,
    )

    arbiter_input = board["candidate_rows"][0]["arbiter_input"]
    context_cost_hash = arbiter_input["context_hashes"]["cost"]
    assert arbiter_input["cost_evidence"] == {
        "schema_version": "alr_candidate_cost_evidence_v2",
        "basis": "expected_slippage_mean_abs_v1",
        "source_asof_utc": now.isoformat(),
        "source_payload_sha256": expected["source_payload_sha256"],
        "normalized_projection_sha256": expected["normalized_projection_sha256"],
        "max_age_hours": 48,
        "fee_floor_bps": 11.0,
        "mean_abs_source": {
            "scope": "SYMBOL",
            "symbol": "BTCUSDT",
            "sample_count": 200,
            "mean_abs_bps": 1.5,
        },
        "tail_source": {
            "scope": "SYMBOL",
            "symbol": "BTCUSDT",
            "sample_count": 200,
            "tail_bps": 6.0,
            "tail_metric": "cvar90",
        },
    }
    assert arbiter_input["context_hashes"]["cost"] == context_cost_hash


def test_candidate_board_import_order_has_no_cycle() -> None:
    research_root = Path(__file__).resolve().parents[1]
    script = f"""
import sys
sys.path.insert(0, {str(research_root)!r})
import cost_gate_learning_lane.candidate_board_validation as validation
assert 'cost_gate_learning_lane.candidate_board' not in sys.modules
import cost_gate_learning_lane.candidate_board as candidate_board
assert candidate_board.validate_learning_candidate_board_v2 is validation.validate_learning_candidate_board_v2
assert 'cost_gate_learning_lane.outcome_review' not in sys.modules
import cost_gate_learning_lane.outcome_review as outcome_review
assert outcome_review.build_learning_candidate_board is candidate_board.build_learning_candidate_board
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_candidate_board_validation_contract_is_extracted_behind_compatible_facade() -> None:
    validation = importlib.import_module(
        "cost_gate_learning_lane.candidate_board_validation"
    )

    assert candidate_board.validate_learning_candidate_board_v2 is (
        validation.validate_learning_candidate_board_v2
    )
    assert candidate_board.LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION == (
        validation.LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION
    )
    source_lines = Path(candidate_board.__file__).read_text(encoding="utf-8").splitlines()
    assert len(source_lines) < 1_500
    assert not any(
        line.startswith("def _validate_") or line.startswith("def validate_learning_")
        for line in source_lines
    )


def test_candidate_board_fake_cohort_evaluator_contract_is_strict() -> None:
    rows = [
        _typed_row(
            attempt_id="typed-evaluator",
            entry_ts_ms=int(
                dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
            ),
            realized_net_bps=1.0,
            regime_label="neutral|low_vol|liquid",
        )
    ]
    cfg = outcome_review.BlockedOutcomeReviewConfig()
    calls: list[tuple[str, list[dict[str, object]]]] = []

    def fake_evaluator(
        side_cell_key,
        cohort_rows,
        *,
        cfg,
        overlay,
        edge_estimates,
        expected_slippage,
    ):
        calls.append((side_cell_key, cohort_rows))
        return outcome_review._evaluate_candidate_cohort(
            side_cell_key,
            cohort_rows,
            cfg=cfg,
            overlay=overlay,
            edge_estimates=edge_estimates,
            expected_slippage=expected_slippage,
        )

    board = candidate_board.build_learning_candidate_board(
        rows,
        cfg=cfg,
        overlay={},
        edge_estimates={},
        expected_slippage=None,
        as_of_date=AS_OF_DATE,
        cohort_evaluator=fake_evaluator,
    )

    assert calls == [("strat|BTCUSDT|Buy", rows)]
    assert board == outcome_review._build_learning_candidate_board(
        rows,
        cfg=cfg,
        overlay={},
        edge_estimates={},
        expected_slippage=None,
        as_of_date=AS_OF_DATE,
    )

    def incomplete_evaluator(*args, **kwargs):
        evaluation = fake_evaluator(*args, **kwargs)
        evaluation.pop("entries")
        return evaluation

    with pytest.raises(KeyError, match="entries"):
        candidate_board.build_learning_candidate_board(
            rows,
            cfg=cfg,
            overlay={},
            edge_estimates={},
            expected_slippage=None,
            as_of_date=AS_OF_DATE,
            cohort_evaluator=incomplete_evaluator,
        )


def test_public_outcome_review_symbols_remain_importable() -> None:
    assert outcome_review.LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION == (
        "cost_gate_learning_candidate_board_v2"
    )
    assert outcome_review.ARBITER_INPUT_SCHEMA_VERSION == (
        "alr_candidate_arbiter_input_v2"
    )
    assert callable(outcome_review.build_blocked_signal_outcome_review)
    assert callable(outcome_review._build_learning_candidate_board)
    assert outcome_review._candidate_learning_context is (
        candidate_board.candidate_learning_context
    )


def test_candidate_board_hash_is_stable_for_empty_legacy_conflict_and_multi_regime_fixtures() -> None:
    entry_base = int(
        dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
    )
    conflict_rows = [
        _typed_row(
            attempt_id="conflict-false",
            entry_ts_ms=entry_base,
            realized_net_bps=1.0,
            regime_label="neutral|low_vol|liquid",
            hidden_oos_consumed=False,
        ),
        _typed_row(
            attempt_id="conflict-true",
            entry_ts_ms=entry_base + 86_400_000,
            realized_net_bps=2.0,
            regime_label="neutral|low_vol|liquid",
            hidden_oos_consumed=True,
        ),
    ]
    multi_regime_rows = [
        _typed_row(
            attempt_id="regime-bear",
            entry_ts_ms=entry_base,
            realized_net_bps=1.0,
            regime_label="bear|low_vol|liquid",
        ),
        _typed_row(
            attempt_id="regime-bull",
            entry_ts_ms=entry_base + 86_400_000,
            realized_net_bps=2.0,
            regime_label="bull|high_vol|thin",
        ),
    ]
    fixtures = {
        "empty": [],
        "legacy": [_legacy_row()],
        "conflict": conflict_rows,
        "multi_regime": multi_regime_rows,
    }
    observed_hashes: dict[str, str] = {}
    for name, rows in fixtures.items():
        forward = _build_extracted_board(rows)
        reverse = _build_extracted_board(list(reversed(rows)))
        assert forward == reverse
        assert _canonical_bytes(forward) == _canonical_bytes(reverse)
        board_hash = forward["board_hash"]
        assert isinstance(board_hash, str)
        assert len(board_hash) == 64
        assert all(character in "0123456789abcdef" for character in board_hash)
        observed_hashes[name] = board_hash

    assert len(set(observed_hashes.values())) == len(fixtures)
