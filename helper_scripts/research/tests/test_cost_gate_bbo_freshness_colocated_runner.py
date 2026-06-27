from __future__ import annotations

import datetime as dt
import json
import sys

from cost_gate_learning_lane import bbo_freshness_colocated_runner as mod


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


def _repair(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_probe_bbo_freshness_repair_proposal_v1",
        "generated_at_utc": "2026-06-24T17:40:00+00:00",
        "status": "BBO_FRESHNESS_REPAIR_PROPOSAL_READY_NO_AUTHORITY",
        "repair_options": [
            {
                "option_id": "co_located_read_only_pg_snapshot_preview_runner",
                "rank": 1,
                "status": "RECOMMENDED_SOURCE_ONLY_DESIGN",
            },
            {
                "option_id": "direct_public_quote_capture_before_admission",
                "rank": 2,
                "status": "E3_BB_REVIEW_REQUIRED_BEFORE_ANY_CALL",
            },
        ],
        "answers": {
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "promotion_evidence": False,
        },
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
            "avg_net_bps": 73.5511,
            "current_cap_usdt": 10.0,
            "instrument_status": "Trading",
        },
        "answers": {
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _market(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_probe_candidate_market_snapshot_v1",
        "generated_at_utc": "2026-06-24T17:40:00+00:00",
        "pg_snapshot_timestamp": "2026-06-24T17:40:00+00:00",
        "source": "read_only_pg:market.market_tickers+market.symbol_universe_snapshots",
        "candidate": _candidate(),
        "risk_limits": {"cap_usdt": 10.0, "max_fresh_bbo_age_ms": 1000},
        "ticker": {
            "ts": "2026-06-24T17:39:59.500000+00:00",
            "symbol": "AVAXUSDT",
            "last_price": 6.045,
            "mark_price": 6.044,
            "best_bid": 6.044,
            "best_ask": 6.045,
            "spread_bps": 1.654,
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
        "repair_proposal": _repair(),
        "reroute_review": _reroute(),
        "market_snapshot": _market(),
        "demo_operational_authorization_available": True,
        "now_utc": NOW,
    }
    args.update(overrides)
    return mod.build_colocated_runner_packet(**args)


def test_supplied_market_ready_is_smoke_not_colocated_gate_closure() -> None:
    packet = _build()

    assert packet["schema_version"] == mod.COLOCATED_RUNNER_SCHEMA_VERSION
    assert packet["status"] == mod.SUPPLIED_SMOKE_READY_STATUS
    assert packet["construction_preview"]["status"] == mod.PREVIEW_READY_STATUS
    assert packet["construction_preview"]["construction"]["rounded_qty"] == 1.6
    assert (
        packet["next_blocker_id"]
        == "P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY"
    )
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["pg_write_performed"] is False
    assert packet["answers"]["pg_query_performed"] is False


def test_pg_readonly_mode_can_close_colocated_gate_when_preview_ready() -> None:
    packet = _build(pg_readonly_mode=True)

    assert packet["status"] == mod.READY_STATUS
    assert packet["answers"]["pg_query_performed"] is True
    assert (
        packet["next_blocker_id"]
        == "P0-BOUNDED-PROBE-REROUTE-DEMO-ORDER-ADMISSION-REVIEW"
    )


def test_stale_bbo_propagates_no_order_runner_status() -> None:
    stale_market = _market(
        ticker={**_market()["ticker"], "ts": "2026-06-24T17:39:58+00:00"}
    )

    packet = _build(market_snapshot=stale_market)

    assert packet["status"] == mod.BBO_STALE_RUNNER_STATUS
    assert packet["construction_preview"]["status"] == mod.BBO_STALE_STATUS
    assert "bbo_freshness" in packet["blocking_gates"]


def test_repair_proposal_must_select_colocated_runner_as_rank1() -> None:
    repair = _repair(
        repair_options=[
            {
                "option_id": "direct_public_quote_capture_before_admission",
                "rank": 1,
                "status": "E3_BB_REVIEW_REQUIRED_BEFORE_ANY_CALL",
            }
        ]
    )

    packet = _build(repair_proposal=repair)

    assert packet["status"] == mod.INPUT_REQUIRED_STATUS
    assert "rank1_co_located_runner_option_missing" in packet["blocking_gates"]


def test_authority_contamination_fails_closed() -> None:
    packet = _build(repair_proposal=_repair(runtime_probe_authority_found=True))

    assert packet["status"] == mod.AUTHORITY_VIOLATION_STATUS
    assert "runtime_probe_authority_found_contaminating" in packet[
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["order_submission_performed"] is False


def test_order_authority_enum_contamination_fails_closed() -> None:
    packet = _build(reroute_review=_reroute(order_authority="DEMO_LEARNING_PROBE_GRANTED"))

    assert packet["status"] == mod.AUTHORITY_VIOLATION_STATUS
    assert "order_authority_contaminating" in packet[
        "authority_contamination_reasons"
    ]


def test_explicit_mutation_and_cancel_flags_fail_closed() -> None:
    for key in [
        "order_cancel_performed",
        "order_cancel_modify_performed",
        "order_modify_performed",
        "crontab_mutation_performed",
        "config_mutation_performed",
        "env_mutation_performed",
        "runtime_env_mutation_performed",
        "risk_mutation_performed",
        "freshness_gate_lowering_recommended",
    ]:
        packet = _build(repair_proposal=_repair(**{key: True}))
        assert packet["status"] == mod.AUTHORITY_VIOLATION_STATUS
        assert f"{key}_contaminating" in packet["authority_contamination_reasons"]


def test_pg_query_true_is_allowed_only_for_market_snapshot() -> None:
    packet = _build(reroute_review=_reroute(pg_query_performed=True))

    assert packet["status"] == mod.AUTHORITY_VIOLATION_STATUS
    assert "pg_query_performed_contaminating" in packet[
        "authority_contamination_reasons"
    ]


def test_build_market_snapshot_from_rows_records_read_only_source_and_age() -> None:
    snapshot = mod.build_market_snapshot_from_rows(
        candidate=_candidate(),
        ticker={
            "ts": "2026-06-24T17:39:59+00:00",
            "symbol": "AVAXUSDT",
            "last_price": 6.045,
            "mark_price": 6.044,
            "best_bid": 6.044,
            "best_ask": 6.045,
            "spread_bps": 1.654,
        },
        instrument={
            "ts": "2026-06-24T17:35:00+00:00",
            "category": "linear",
            "symbol": "AVAXUSDT",
            "status": "Trading",
            "tick_size": 0.001,
            "qty_step": 0.1,
            "min_notional": 5.0,
        },
        pg_snapshot_timestamp=NOW,
        generated_at_utc=NOW,
        cap_usdt=955.24342626,
    )

    assert snapshot["source"] == mod.EXPECTED_SOURCE
    assert snapshot["risk_limits"]["cap_usdt"] == 955.24342626
    assert snapshot["derived"]["bbo_age_ms"] == 1000.0
    assert snapshot["answers"]["pg_query_performed"] is True
    assert snapshot["answers"]["pg_write_performed"] is False


def test_cli_supplied_mode_records_hashes(tmp_path, monkeypatch) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    repair_path = tmp_path / "repair.json"
    reroute_path = tmp_path / "reroute.json"
    market_path = tmp_path / "market.json"
    out_path = tmp_path / "runner.json"
    repair_path.write_text(json.dumps(_repair(generated_at_utc=now.isoformat())), encoding="utf-8")
    reroute_path.write_text(json.dumps(_reroute(generated_at_utc=now.isoformat())), encoding="utf-8")
    market = _market(
        generated_at_utc=now.isoformat(),
        pg_snapshot_timestamp=now.isoformat(),
        ticker={**_market()["ticker"], "ts": now.isoformat()},
        risk_limits={"cap_usdt": 10.0, "max_fresh_bbo_age_ms": 10000},
    )
    market_path.write_text(json.dumps(market), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bbo_freshness_colocated_runner",
            "--repair-proposal-json",
            str(repair_path),
            "--reroute-review-json",
            str(reroute_path),
            "--market-snapshot-json",
            str(market_path),
            "--json-output",
            str(out_path),
        ],
    )

    assert mod.main() == 0
    packet = json.loads(out_path.read_text(encoding="utf-8"))

    assert packet["status"] == mod.SUPPLIED_SMOKE_READY_STATUS
    assert packet["source_artifacts"]["repair_proposal"]["sha256"]
    assert packet["source_artifacts"]["market_snapshot"]["sha256"]
    assert packet["answers"]["pg_query_performed"] is False


def test_cli_pg_readonly_mode_uses_loader_and_writes_market_output(tmp_path, monkeypatch) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    repair_path = tmp_path / "repair.json"
    reroute_path = tmp_path / "reroute.json"
    market_out = tmp_path / "market.json"
    runner_out = tmp_path / "runner.json"
    repair_path.write_text(json.dumps(_repair(generated_at_utc=now.isoformat())), encoding="utf-8")
    reroute_path.write_text(json.dumps(_reroute(generated_at_utc=now.isoformat())), encoding="utf-8")

    def fake_loader(**kwargs):
        assert kwargs["candidate"]["symbol"] == "AVAXUSDT"
        return _market(
            generated_at_utc=now.isoformat(),
            pg_snapshot_timestamp=now.isoformat(),
            ticker={**_market()["ticker"], "ts": now.isoformat()},
            risk_limits={"cap_usdt": kwargs["cap_usdt"], "max_fresh_bbo_age_ms": 10000},
        )

    monkeypatch.setattr(mod, "load_pg_market_snapshot", fake_loader)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bbo_freshness_colocated_runner",
            "--repair-proposal-json",
            str(repair_path),
            "--reroute-review-json",
            str(reroute_path),
            "--pg-readonly",
            "--cap-usdt",
            "955.24342626",
            "--max-fresh-bbo-age-ms",
            "10000",
            "--market-snapshot-output",
            str(market_out),
            "--json-output",
            str(runner_out),
        ],
    )

    assert mod.main() == 0
    packet = json.loads(runner_out.read_text(encoding="utf-8"))

    assert market_out.exists()
    market = json.loads(market_out.read_text(encoding="utf-8"))
    assert market["risk_limits"]["cap_usdt"] == 955.24342626
    assert packet["mode"] == "pg_readonly"
    assert packet["answers"]["pg_query_performed"] is True
    assert packet["answers"]["pg_write_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_cli_requires_exactly_one_input_mode(tmp_path, monkeypatch) -> None:
    repair_path = tmp_path / "repair.json"
    reroute_path = tmp_path / "reroute.json"
    market_path = tmp_path / "market.json"
    repair_path.write_text(json.dumps(_repair()), encoding="utf-8")
    reroute_path.write_text(json.dumps(_reroute()), encoding="utf-8")
    market_path.write_text(json.dumps(_market()), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bbo_freshness_colocated_runner",
            "--repair-proposal-json",
            str(repair_path),
            "--reroute-review-json",
            str(reroute_path),
        ],
    )
    try:
        mod.main()
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("expected missing mode to exit non-zero")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bbo_freshness_colocated_runner",
            "--repair-proposal-json",
            str(repair_path),
            "--reroute-review-json",
            str(reroute_path),
            "--market-snapshot-json",
            str(market_path),
            "--pg-readonly",
        ],
    )
    try:
        mod.main()
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("expected both modes to exit non-zero")


def test_cli_pg_readonly_requires_market_snapshot_output(tmp_path, monkeypatch) -> None:
    repair_path = tmp_path / "repair.json"
    reroute_path = tmp_path / "reroute.json"
    repair_path.write_text(json.dumps(_repair()), encoding="utf-8")
    reroute_path.write_text(json.dumps(_reroute()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bbo_freshness_colocated_runner",
            "--repair-proposal-json",
            str(repair_path),
            "--reroute-review-json",
            str(reroute_path),
            "--pg-readonly",
        ],
    )

    try:
        mod.main()
    except SystemExit as exc:
        assert str(exc) == "--market-snapshot-output is required with --pg-readonly"
    else:
        raise AssertionError("expected pg-readonly without output to exit")


def test_cli_pg_readonly_requires_resolved_gui_cap(tmp_path, monkeypatch) -> None:
    repair_path = tmp_path / "repair.json"
    reroute_path = tmp_path / "reroute.json"
    market_out = tmp_path / "market.json"
    repair_path.write_text(json.dumps(_repair()), encoding="utf-8")
    reroute_path.write_text(json.dumps(_reroute()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bbo_freshness_colocated_runner",
            "--repair-proposal-json",
            str(repair_path),
            "--reroute-review-json",
            str(reroute_path),
            "--pg-readonly",
            "--market-snapshot-output",
            str(market_out),
        ],
    )

    try:
        mod.main()
    except SystemExit as exc:
        assert (
            str(exc)
            == "--cap-usdt resolved from GUI/Rust RiskConfig is required with --pg-readonly"
        )
    else:
        raise AssertionError("expected pg-readonly without GUI cap to exit")
