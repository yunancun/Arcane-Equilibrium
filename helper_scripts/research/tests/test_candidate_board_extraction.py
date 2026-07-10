"""Candidate-board Module extraction characterization tests."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cost_gate_learning_lane import candidate_board
from cost_gate_learning_lane import outcome_review


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
    resource_payload = {
        "daily_buckets": [
            {
                "utc_date": (AS_OF_DATE - dt.timedelta(days=offset)).isoformat(),
                "scan_complete": True,
                "distinct_entries": 1,
            }
            for offset in range(7, 0, -1)
        ],
        "estimated_rows_scanned": 7,
        "predicted_canonical_bytes": 700,
        "zero_resource_attested": False,
    }
    resource = dict(resource_payload)
    resource["resource_estimator_hash"] = hashlib.sha256(
        _canonical_bytes(resource_payload)
    ).hexdigest()
    context = {
        "strategy_version": "v1",
        "strategy_config_hash": "1" * 64,
        "target_regime_context": {
            "label": "range_low_vol",
            "utc_date": (AS_OF_DATE - dt.timedelta(days=1)).isoformat(),
            "point_in_time": "D-1",
        },
        "target_regime_hash": "2" * 64,
        "venue": "bybit",
        "product": "linear_perpetual",
        "evidence_engine_mode": "demo",
        "evidence_regime_label": regime_label,
        "hidden_oos_consumed": hidden_oos_consumed,
        "context_hashes": {
            "data": "3" * 64,
            "evidence": "4" * 64,
            "cost": "5" * 64,
            "portfolio": "6" * 64,
        },
        "resource": resource,
        "portfolio": {
            "sector_exposure_share": "0.10",
            "strategy_active_target_share": "0.20",
            "beta_to_portfolio": "0.30",
        },
        "proof": {
            "proof_stage": 1,
            "completed_proof_stages": [0, 1],
            "next_gap": {"kind": "NONE", "code": "DATA_GATES_READY"},
        },
    }
    row = _legacy_row(attempt_id=attempt_id)
    row.update(
        {
            "entry_ts_ms": entry_ts_ms,
            "gross_bps": realized_net_bps + 12.0,
            "realized_net_bps": realized_net_bps,
            "net_bps_optimistic": realized_net_bps + 8.0,
            "cost_bps": 12.0,
            "cost_model_version": "conservative_v1",
            "candidate_summary": {"candidate_learning_context": context},
        }
    )
    return row


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
    assert facade["board_hash"] == extracted["board_hash"]
    assert _canonical_bytes(facade) == _canonical_bytes(extracted)


def test_candidate_board_import_order_has_no_cycle() -> None:
    research_root = Path(__file__).resolve().parents[1]
    script = f"""
import sys
sys.path.insert(0, {str(research_root)!r})
import cost_gate_learning_lane.candidate_board as candidate_board
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


def test_candidate_board_fake_cohort_evaluator_contract_is_strict() -> None:
    rows = [_legacy_row()]
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
        "cost_gate_learning_candidate_board_v1"
    )
    assert outcome_review.ARBITER_INPUT_SCHEMA_VERSION == (
        "alr_candidate_arbiter_input_v1"
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
    expected_hashes = {
        "empty": "e7ecd241f13ffe2f962404bced28a4abbf9adffc828479bcd048a3931ea619d0",
        "legacy": "f35f0e3f5b6bfe6983983f0095dc39d9d4d974cccecc8f5deb8dcd0beb10983d",
        "conflict": "9bc1606b73bbef205312b31946925dcab7d197f09e9cd4254f3dd587dca3b124",
        "multi_regime": "33e432a5bcaca7ca16cbc4a497721ef7fa402790a53e710aab2abfbd639d48e4",
    }

    for name, rows in fixtures.items():
        forward = _build_extracted_board(rows)
        reverse = _build_extracted_board(list(reversed(rows)))
        assert forward == reverse
        assert _canonical_bytes(forward) == _canonical_bytes(reverse)
        assert forward["board_hash"] == expected_hashes[name]
