from __future__ import annotations

"""MAG-021 scanner advisory contract serialization tests."""

import os
import sys

import pytest
from pydantic import ValidationError

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.scanner_advisory_contracts import (  # noqa: E402
    OpportunityCandidate,
    OpportunityDecay,
)


def test_opportunity_candidate_json_round_trip() -> None:
    candidate = OpportunityCandidate(
        candidate_id="oppcand:scan-1:BTCUSDT:grid_trading",
        scan_id="scan-1",
        scan_ts_ms=1_778_100_000_000,
        symbol="BTCUSDT",
        strategy="grid_trading",
        authority_mode="advisory_shadow",
        final_score=72.5,
        raw_score=68.0,
        opportunity_score=61.0,
        opportunity_lcb_bps=5.25,
        admission_hint="opportunity_positive",
        route_mode="main",
        market_status="compatible",
        route_reason="range_compatible",
        data_quality_score=0.91,
        edge_bps=3.2,
        edge_n=42,
        evidence={"source": "scanner_snapshot"},
    )

    payload = candidate.model_dump(mode="json")
    restored = OpportunityCandidate.model_validate(payload)

    assert restored == candidate
    assert payload["authority_mode"] == "advisory_shadow"
    assert payload["evidence"]["source"] == "scanner_snapshot"


def test_opportunity_decay_json_round_trip_preserves_no_auto_close() -> None:
    decay = OpportunityDecay(
        decay_id="oppdecay:scan-2:BTCUSDT",
        candidate_id="oppcand:scan-1:BTCUSDT:grid_trading",
        scan_id="scan-2",
        decay_ts_ms=1_778_100_300_000,
        symbol="BTCUSDT",
        strategy="grid_trading",
        authority_mode="advisory_enforced",
        reason="exited_top_set",
        previous_score=72.5,
        current_score=31.0,
        previous_rank=3,
        current_rank=None,
        has_open_position=True,
        position_review_required=True,
        auto_close_allowed=False,
        evidence={"displaced_by": ["ETHUSDT", "SOLUSDT"]},
    )

    payload = decay.model_dump(mode="json")
    restored = OpportunityDecay.model_validate(payload)

    assert restored == decay
    assert payload["reason"] == "exited_top_set"
    assert payload["position_review_required"] is True
    assert payload["auto_close_allowed"] is False


def test_invalid_authority_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        OpportunityCandidate(
            candidate_id="oppcand:scan-1:BTCUSDT:grid_trading",
            scan_id="scan-1",
            scan_ts_ms=1_778_100_000_000,
            symbol="BTCUSDT",
            strategy="grid_trading",
            authority_mode="unused_mode",
            final_score=72.5,
            raw_score=68.0,
            route_mode="main",
            market_status="compatible",
            route_reason="range_compatible",
        )
