from __future__ import annotations

import sys
from pathlib import Path


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from replay import report_analytics  # noqa: E402


def test_replay_report_analytics_computes_fee_net_bps_and_ghost_counts() -> None:
    payload = {
        "result": {
            "fills": [
                {
                    "ts_ms": 1,
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "qty": 1.0,
                    "price": 100.0,
                    "fee": 0.05,
                    "slippage_bps": 5.0,
                    "liquidity_role": "taker",
                },
                {
                    "ts_ms": 2,
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "qty": 0.0,
                    "price": 100.0,
                    "fee": 0.0,
                    "slippage_bps": 0.0,
                    "liquidity_role": "maker",
                },
            ],
            "pnl_summary": {
                "starting_balance": 10_000.0,
                "ending_balance": 10_010.0,
                "net_pnl": 10.0,
            },
            "diagnostics": {"abort_reason": None},
        },
    }

    analytics = report_analytics.build_replay_result_analytics(payload)

    assert analytics["verdict"] == "development_sandbox_pass"
    assert analytics["net_bps_after_fee"] == 10.0
    assert analytics["fill_count"] == 1
    assert analytics["ghost_fill_count"] == 1
    assert analytics["maker_miss_count"] == 1
    assert analytics["risk_reject_count"] == 0
    assert analytics["baseline_comparison_status"] == "not_configured"
    assert analytics["drawdown_status"] == "computed_from_fill_sequence"
    assert analytics["balance_curve_point_count"] == 2
    assert abs(analytics["max_drawdown_bps"] - 0.05) < 1e-9
    assert analytics["run_band_status"] == "insufficient_samples_for_block_bootstrap"


def test_replay_report_analytics_overlay_writes_payload_and_result() -> None:
    artifact = {
        "payload": {
            "result": {
                "fills": [],
                "pnl_summary": {"starting_balance": 10_000.0, "net_pnl": None},
                "diagnostics": {"abort_reason": "fixture_missing"},
            }
        }
    }

    report_analytics.overlay_artifact_payload_analytics(artifact)

    payload_analytics = artifact["payload"]["replay_result_analytics"]
    result_analytics = artifact["payload"]["result"]["replay_result_analytics"]
    assert payload_analytics == result_analytics
    assert payload_analytics["verdict"] == "needs_more_data"
    assert "replay_aborted" in payload_analytics["reason_codes"]


def test_replay_report_analytics_builds_balance_curve_and_block_bands() -> None:
    fills = []
    for idx in range(12):
        fills.append({
            "ts_ms": idx * 2 + 1,
            "symbol": "BTCUSDT",
            "side": "long",
            "qty": 1.0,
            "price": 100.0,
            "fee": 0.01,
            "liquidity_role": "taker",
        })
        fills.append({
            "ts_ms": idx * 2 + 2,
            "symbol": "BTCUSDT",
            "side": "short",
            "qty": 1.0,
            "price": 101.0,
            "fee": 0.01,
            "liquidity_role": "taker",
        })
    analytics = report_analytics.build_replay_result_analytics({
        "result": {
            "fills": fills,
            "pnl_summary": {
                "starting_balance": 10_000.0,
                "ending_balance": 10_011.76,
                "net_pnl": 11.76,
            },
        }
    })

    assert analytics["drawdown_status"] == "computed_from_fill_sequence"
    assert analytics["balance_curve_point_count"] == 25
    assert analytics["run_band_status"] == "stationary_block_bootstrap"
    assert analytics["run_bands_bps"]["method"] == "stationary_block_bootstrap"
    assert analytics["run_bands_bps"]["sample_count"] == 24


def test_replay_report_analytics_compares_baseline_candidate() -> None:
    baseline = {
        "net_bps_after_fee": 5.0,
        "max_drawdown_bps": 30.0,
        "fill_count": 10,
        "reject_or_miss_rate": 0.10,
    }
    candidate = {
        "net_bps_after_fee": 14.0,
        "max_drawdown_bps": 40.0,
        "fill_count": 12,
        "reject_or_miss_rate": 0.05,
    }

    comparison = report_analytics.compare_replay_analytics(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison["status"] == "computed"
    assert comparison["verdict"] == "candidate_better"
    assert comparison["delta_net_bps_after_fee"] == 9.0
    assert comparison["delta_max_drawdown_bps"] == 10.0
