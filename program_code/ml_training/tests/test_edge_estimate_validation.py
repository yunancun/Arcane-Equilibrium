from __future__ import annotations

from datetime import datetime, timedelta, timezone

from program_code.ml_training.edge_estimate_validation import (
    ValidationConfig,
    validate_edge_stats,
)
from program_code.ml_training.realized_edge_stats import EdgeStats, RoundTripRecord


def _record(day: int, net_bps: float) -> RoundTripRecord:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    return RoundTripRecord(
        strategy_name="grid_trading",
        symbol="BTCUSDT",
        gross_pnl_bps=net_bps,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        net_pnl_bps=net_bps,
        entry_ts=ts - timedelta(minutes=5),
        exit_ts=ts,
        notional_usd=100.0,
    )


def _stats(records: list[RoundTripRecord]) -> EdgeStats:
    values = [r.net_pnl_bps for r in records]
    mean = sum(values) / len(values)
    return EdgeStats(
        strategy_name="grid_trading",
        symbol="BTCUSDT",
        n=len(records),
        mean_net_bps=mean,
        std_net_bps=1.0,
        mean_gross_bps=mean,
        mean_fee_bps=0.0,
        raw_bps_list=values,
        raw_records=records,
    )


def test_validation_rejects_insufficient_total_samples():
    records = [_record(0, 5.0), _record(1, 6.0), _record(2, 7.0)]
    verdicts, summary = validate_edge_stats(
        {("grid_trading", "BTCUSDT"): _stats(records)},
        ValidationConfig(min_trust_n=4),
    )

    verdict = verdicts[("grid_trading", "BTCUSDT")]
    assert not verdict.validation_passed
    assert verdict.validation_reason == "insufficient_total_samples"
    assert summary["insufficient_cells"] == 1


def test_validation_passes_positive_walk_forward_oos_samples():
    records = [
        _record(0, 4.0),
        _record(2, 5.0),
        _record(5, 6.0),
        _record(12, 5.0),
        _record(13, 6.0),
    ]
    config = ValidationConfig(
        wf_train_days=10,
        wf_test_days=5,
        wf_step_days=5,
        min_trust_n=5,
        min_oos_n=2,
        min_wf_windows=1,
        psr_min=0.50,
        dsr_min=0.50,
        bonferroni_alpha_family=1.0,
    )
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)

    verdicts, summary = validate_edge_stats(
        {("grid_trading", "BTCUSDT"): _stats(records)},
        config,
        now=now,
    )

    verdict = verdicts[("grid_trading", "BTCUSDT")]
    assert verdict.validation_passed
    assert verdict.wf_windows == 1
    assert verdict.oos_n == 2
    assert verdict.oos_mean_bps > 0
    assert summary["eligible_cells"] == 1

