from __future__ import annotations

import datetime as dt
import json
import sys

from cost_gate_learning_lane.bounded_probe_candidate_construction_preview import (
    CONSTRUCTION_PREVIEW_SCHEMA_VERSION,
    READY_STATUS,
    build_candidate_construction_preview,
    main,
)


NOW = dt.datetime(2026, 6, 24, 17, 40, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _reroute(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_lower_price_reroute_review_v1",
        "generated_at_utc": "2026-06-24T17:40:00+00:00",
        "status": "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW",
        "selected_candidate": {
            **(candidate or _candidate()),
            "false_negative_rank": 1,
            "friction_rank": 1,
            "avg_net_bps": 73.5511,
            "net_positive_pct": 100.0,
            "outcome_count": 48,
            "current_cap_usdt": 10.0,
            "minimum_required_demo_notional_usdt_per_order": 5.0,
            "instrument_status": "Trading",
        },
        "answers": {
            "order_submission_performed": False,
            "bybit_call_performed": False,
            "pg_write_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _market(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_probe_candidate_market_snapshot_v1",
        "generated_at_utc": "2026-06-24T17:40:00+00:00",
        "pg_snapshot_timestamp": "2026-06-24T17:40:00+00:00",
        "source": "read_only_pg:market.market_tickers+market.symbol_universe_snapshots",
        "candidate": candidate or _candidate(),
        "risk_limits": {
            "cap_usdt": 10.0,
            "max_fresh_bbo_age_ms": 1000,
        },
        "ticker": {
            "ts": "2026-06-24T17:39:59.500000+00:00",
            "symbol": "AVAXUSDT",
            "last_price": 6.045,
            "mark_price": 6.044,
            "best_bid": 6.044,
            "best_ask": 6.045,
            "spread_bps": 1.654,
            "funding_rate": 0.0001,
        },
        "instrument": {
            "ts": "2026-06-24T17:35:00+00:00",
            "category": "linear",
            "symbol": "AVAXUSDT",
            "status": "Trading",
            "tick_size": 0.001,
            "qty_step": 0.1,
            "min_notional": 5.0,
        },
        "derived": {
            "bbo_age_ms": 500.0,
            "instrument_status": "Trading",
            "best_bid": 6.044,
            "best_ask": 6.045,
            "spread_bps": 1.654,
            "tick_size": 0.001,
            "qty_step": 0.1,
            "min_notional": 5.0,
        },
        "answers": {
            "pg_query_performed": True,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _build(**overrides) -> dict:
    args = {
        "reroute_review": _reroute(),
        "market_snapshot": _market(),
        "demo_operational_authorization_available": True,
        "now_utc": NOW,
    }
    args.update(overrides)
    return build_candidate_construction_preview(**args)


def test_avax_sell_feasible_under_10_usdt_cap_returns_ready_no_order() -> None:
    packet = _build()

    assert packet["schema_version"] == CONSTRUCTION_PREVIEW_SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == SIDE_CELL
    assert packet["construction"]["limit_price"] == 6.045
    assert packet["construction"]["rounded_qty"] == 1.6
    assert packet["construction"]["rounded_notional_usdt"] == 9.672
    assert packet["construction"]["min_positive_qty_notional_usdt"] == 0.6045
    assert packet["construction"]["passive_against_touch"] is True
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["pg_write_performed"] is False
    assert packet["answers"]["pg_query_performed"] is False


def test_stale_bbo_fails_closed_before_order_admission() -> None:
    packet = _build(
        market_snapshot=_market(
            ticker={**_market()["ticker"], "ts": "2026-06-24T17:39:58+00:00"},
            derived={**_market()["derived"], "bbo_age_ms": 500.0},
        )
    )

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_BBO_STALE"
    assert "bbo_freshness" in packet["blocking_gates"]
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["market_inputs"]["effective_bbo_age_ms"] == 2000.0


def test_future_ticker_ts_fails_closed_as_not_fresh() -> None:
    packet = _build(
        market_snapshot=_market(
            ticker={**_market()["ticker"], "ts": "2026-06-24T17:40:02+00:00"},
        )
    )

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_BBO_STALE"
    assert packet["market_inputs"]["effective_bbo_age_ms"] is None


def test_min_positive_qty_notional_above_cap_fails_closed() -> None:
    candidate = {
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    btc_market = _market(
        candidate=candidate,
        ticker={
            "ts": "2026-06-24T17:39:59.500000+00:00",
            "symbol": "BTCUSDT",
            "last_price": 60040.0,
            "mark_price": 60040.0,
            "best_bid": 60040.0,
            "best_ask": 60040.1,
            "spread_bps": 0.02,
        },
        instrument={
            "ts": "2026-06-24T17:35:00+00:00",
            "category": "linear",
            "symbol": "BTCUSDT",
            "status": "Trading",
            "tick_size": 0.1,
            "qty_step": 0.001,
            "min_notional": 5.0,
        },
        derived={
            "bbo_age_ms": 500.0,
            "instrument_status": "Trading",
            "best_bid": 60040.0,
            "best_ask": 60040.1,
            "spread_bps": 0.02,
            "tick_size": 0.1,
            "qty_step": 0.001,
            "min_notional": 5.0,
        },
    )

    packet = _build(
        reroute_review=_reroute(candidate=candidate),
        market_snapshot=btc_market,
    )

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP"
    assert "min_positive_qty_notional_exceeds_cap" in packet["blocking_gates"]
    assert packet["construction"]["min_positive_qty_notional_usdt"] == 60.0401


def test_candidate_mismatch_fails_closed() -> None:
    packet = _build(
        market_snapshot=_market(
            candidate=_candidate(side_cell_key="grid_trading|ETCUSDT|Sell", symbol="ETCUSDT")
        )
    )

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_CANDIDATE_MISMATCH"
    assert "candidate_exact_match" in packet["blocking_gates"]


def test_nested_market_symbol_mismatch_fails_closed() -> None:
    packet = _build(
        market_snapshot=_market(
            ticker={**_market()["ticker"], "symbol": "DOGEUSDT"},
            instrument={**_market()["instrument"], "symbol": "DOGEUSDT"},
        )
    )

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_CANDIDATE_MISMATCH"
    assert "market_data_symbol_match" in packet["blocking_gates"]


def test_non_read_only_market_snapshot_source_is_input_required() -> None:
    packet = _build(market_snapshot=_market(source="manual_or_exchange_wrapped"))

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "market_snapshot_read_only_source" in packet["blocking_gates"]


def test_non_trading_instrument_fails_closed() -> None:
    market = _market(
        instrument={**_market()["instrument"], "status": "PreLaunch"},
        derived={**_market()["derived"], "instrument_status": "PreLaunch"},
    )

    packet = _build(market_snapshot=market)

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP"
    assert "instrument_status_trading" in packet["blocking_gates"]


def test_raw_non_trading_instrument_cannot_be_overridden_by_derived_trading() -> None:
    market = _market(instrument={**_market()["instrument"], "status": "PreLaunch"})

    packet = _build(market_snapshot=market)

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "market_snapshot_internal_consistency" in packet["blocking_gates"]
    assert (
        "derived_instrument_status_disagrees_with_raw_instrument"
        in packet["blocking_gates"]
    )


def test_raw_and_derived_bbo_disagreement_fails_closed() -> None:
    market = _market(
        ticker={**_market()["ticker"], "best_bid": 1.0, "best_ask": 1.001}
    )

    packet = _build(market_snapshot=market)

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "market_snapshot_internal_consistency" in packet["blocking_gates"]
    assert "derived_best_bid_disagrees_with_raw_best_bid" in packet["blocking_gates"]
    assert "derived_best_ask_disagrees_with_raw_best_ask" in packet["blocking_gates"]


def test_malformed_present_derived_numeric_field_fails_closed() -> None:
    market = _market(derived={**_market()["derived"], "best_bid": "not-a-number"})

    packet = _build(market_snapshot=market)

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "market_snapshot_internal_consistency" in packet["blocking_gates"]
    assert "derived_best_bid_disagrees_with_raw_best_bid" in packet["blocking_gates"]


def test_authority_contamination_fails_closed() -> None:
    packet = _build(
        reroute_review=_reroute(
            answers={
                "order_submission_performed": "true",
                "global_cost_gate_lowering_recommended": False,
            }
        )
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "order_submission_performed_contaminating" in packet[
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["order_submission_performed"] is False


def test_order_authority_enum_contamination_fails_closed() -> None:
    packet = _build(reroute_review=_reroute(order_authority="DEMO_LEARNING_PROBE_GRANTED"))

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "order_authority_contaminating" in packet[
        "authority_contamination_reasons"
    ]


def test_explicit_cancel_modify_and_gate_mutation_flags_fail_closed() -> None:
    for key in [
        "order_cancel_performed",
        "order_cancel_modify_performed",
        "order_modify_performed",
        "config_mutation_performed",
        "crontab_mutation_performed",
        "runtime_env_mutation_performed",
        "risk_mutation_performed",
        "freshness_gate_lowering_recommended",
    ]:
        packet = _build(reroute_review=_reroute(**{key: True}))
        assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
        assert f"{key}_contaminating" in packet[
            "authority_contamination_reasons"
        ]


def test_runtime_authority_found_contamination_fails_closed() -> None:
    packet = _build(reroute_review=_reroute(runtime_probe_authority_found=True))

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "runtime_probe_authority_found_contaminating" in packet[
        "authority_contamination_reasons"
    ]


def test_schema_mismatch_fails_input_required() -> None:
    packet = _build(market_snapshot=_market(schema_version="wrong_schema"))

    assert packet["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "market_snapshot_ready" in packet["blocking_gates"]


def test_cli_records_input_hashes_and_demo_auth_flag(tmp_path, monkeypatch) -> None:
    reroute_path = tmp_path / "reroute.json"
    market_path = tmp_path / "market.json"
    out_path = tmp_path / "out.json"
    now = dt.datetime.now(dt.timezone.utc)
    reroute_path.write_text(
        json.dumps(_reroute(generated_at_utc=now.isoformat())),
        encoding="utf-8",
    )
    fresh_market = _market(
        generated_at_utc=now.isoformat(),
        pg_snapshot_timestamp=now.isoformat(),
        ticker={**_market()["ticker"], "ts": now.isoformat()},
        risk_limits={"cap_usdt": 10.0, "max_fresh_bbo_age_ms": 10000},
    )
    market_path.write_text(json.dumps(fresh_market), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bounded_probe_candidate_construction_preview",
            "--reroute-review-json",
            str(reroute_path),
            "--market-snapshot-json",
            str(market_path),
            "--demo-operational-authorization-available",
            "--json-output",
            str(out_path),
        ],
    )

    assert main() == 0
    packet = json.loads(out_path.read_text(encoding="utf-8"))

    assert packet["status"] == READY_STATUS
    assert packet["artifacts"]["reroute_review"]["sha256"]
    assert packet["artifacts"]["market_snapshot"]["sha256"]
    assert packet["answers"]["demo_operational_authorization_available_from_thread"] is True
