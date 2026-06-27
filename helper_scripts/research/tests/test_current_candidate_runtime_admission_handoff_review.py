from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import current_candidate_runtime_admission_handoff_review as mod


NOW = dt.datetime(2026, 6, 27, 2, 30, tzinfo=dt.timezone.utc)
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


def _answers(**overrides) -> dict:
    payload = {
        "source_only_research_artifact": True,
        "public_market_data_only": True,
        "bybit_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "bybit_private_call_performed": False,
        "private_endpoint_called": False,
        "order_submission_performed": False,
        "order_admission_ready": False,
        "order_authority_granted": False,
        "probe_authority_granted": False,
        "live_authority_granted": False,
        "runtime_mutation_performed": False,
        "pg_write_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "bounded_probe_local_10_usdt_cap_is_authority": False,
    }
    payload.update(overrides)
    return payload


def _current_envelope(**overrides) -> dict:
    payload = {
        "schema_version": mod.CURRENT_ENVELOPE_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.CURRENT_ENVELOPE_READY_STATUS,
        "candidate": _candidate(),
        "cap_resolution": {
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "account_equity_usdt": 9552.43426257,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "resolved_cap_usdt": 955.24342626,
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "answers": _answers(
            public_market_data_only=False,
            current_candidate_no_order_refresh_envelope_ready=True,
        ),
    }
    payload.update(overrides)
    return payload


def _request(label: str, path: str, query: dict | None = None) -> dict:
    return {
        "label": label,
        "request_envelope_ok": True,
        "request_envelope": {
            "method": "GET",
            "path": path,
            "query": query or {},
        },
    }


def _public_quote(**overrides) -> dict:
    payload = {
        "schema_version": mod.PUBLIC_QUOTE_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.PUBLIC_QUOTE_READY_STATUS,
        "candidate": _candidate(),
        "endpoint_allowlist": {
            "methods": ["GET"],
            "private_or_order_paths_allowed": False,
            "auth_or_cookie_headers_allowed": False,
        },
        "requests": [
            _request("server_time", "/v5/market/time"),
            _request(
                "ticker",
                "/v5/market/tickers",
                {"category": "linear", "symbol": "AVAXUSDT"},
            ),
            _request(
                "instrument",
                "/v5/market/instruments-info",
                {"category": "linear", "symbol": "AVAXUSDT"},
            ),
        ],
        "derived": {
            "bbo_fresh": True,
            "effective_bbo_age_ms": 497.462,
        },
        "answers": _answers(
            bybit_call_performed=True,
            bybit_public_market_data_call_performed=True,
        ),
    }
    payload.update(overrides)
    return payload


def _market_snapshot(**overrides) -> dict:
    payload = {
        "schema_version": mod.MARKET_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.MARKET_SNAPSHOT_READY_STATUS,
        "candidate": _candidate(),
        "risk_limits": {
            "cap_usdt": 955.24342626,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "gui_risk_config_is_source_of_truth": True,
            "bounded_probe_local_10_usdt_cap_is_authority": False,
        },
        "answers": _answers(
            bybit_call_performed=True,
            bybit_public_market_data_call_performed=True,
        ),
    }
    payload.update(overrides)
    return payload


def _construction_preview(**overrides) -> dict:
    payload = {
        "schema_version": mod.CONSTRUCTION_PREVIEW_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.CONSTRUCTION_READY_STATUS,
        "candidate": _candidate(),
        "construction": {
            "constructible": True,
            "cap_usdt": 955.24342626,
            "limit_price": 6.552,
            "rounded_qty": 145.7,
            "rounded_notional_usdt": 954.6264,
            "placement_mode": "sell_near_touch_post_only_at_or_above_best_ask",
            "best_bid": 6.551,
            "best_ask": 6.552,
        },
        "risk_limits": {
            "cap_usdt": 955.24342626,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "per_trade_risk_pct_display": 10.0,
            "account_equity_usdt": 9552.43426257,
            "bounded_probe_local_10_usdt_cap_is_authority": False,
        },
        "answers": _answers(
            bybit_call_performed=True,
            bybit_public_market_data_call_performed=True,
        ),
    }
    payload.update(overrides)
    return payload


def _refresh(**overrides) -> dict:
    quote = _public_quote()
    snapshot = _market_snapshot()
    preview = _construction_preview()
    envelope = _current_envelope()
    payload = {
        "schema_version": mod.REFRESH_SCHEMA_VERSION,
        "generated_at_utc": NOW.isoformat(),
        "status": mod.REFRESH_READY_STATUS,
        "candidate": _candidate(),
        "cap_resolution": envelope["cap_resolution"],
        "public_quote": quote,
        "market_snapshot": snapshot,
        "construction_preview": preview,
        "summary": {
            "current_candidate_public_quote_construction_refresh_ready": True,
            "request_count": 3,
            "resolved_cap_usdt": 955.24342626,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "gui_risk_config_is_source_of_truth": True,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "construction_constructible": True,
            "order_admission_ready": False,
            "order_or_probe_authority_granted": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "bybit_private_call_performed": False,
        },
        "answers": _answers(
            bybit_call_performed=True,
            bybit_public_market_data_call_performed=True,
        ),
    }
    payload.update(overrides)
    return payload


def _review(**overrides) -> dict:
    kwargs = {
        "refresh": _refresh(),
        "public_quote": _public_quote(),
        "market_snapshot": _market_snapshot(),
        "construction_preview": _construction_preview(),
        "current_envelope": _current_envelope(),
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_runtime_admission_handoff_review(**kwargs)


def test_ready_handoff_preserves_gui_cap_but_not_order_admission() -> None:
    review = _review()

    assert review["schema_version"] == mod.SCHEMA_VERSION
    assert review["status"] == mod.READY_STATUS
    assert review["gates"]["handoff_ready_no_order"] is True
    assert review["gates"]["runtime_admission_ready"] is False
    assert review["gates"]["order_admission_ready"] is False
    assert review["answers"]["order_submission_performed"] is False
    assert review["answers"]["bybit_call_performed"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    sizing = review["admission_envelope_preview"]["sizing"]
    assert sizing["cap_usdt"] == 955.24342626
    assert sizing["rounded_notional_usdt"] == 954.6264
    assert "decision_lease_required" in review["runtime_admission_blockers"]


def test_local_ten_usdt_as_authority_blocks_handoff() -> None:
    envelope = _current_envelope()
    envelope["cap_resolution"]["bounded_probe_local_cap_usdt_is_authority"] = True
    review = _review(current_envelope=envelope)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "bounded_probe_local_cap_marked_authority" in review["blocking_gates"]
    assert review["answers"]["order_admission_ready"] is False


def test_authority_contamination_blocks_before_handoff() -> None:
    preview = _construction_preview(answers=_answers(order_authority_granted=True))
    review = _review(construction_preview=preview)

    assert review["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        gate.endswith("answers.order_authority_granted_true")
        for gate in review["blocking_gates"]
    )
    assert review["gates"]["handoff_ready_no_order"] is False


def test_stale_public_quote_blocks_handoff() -> None:
    old = (NOW - dt.timedelta(hours=2)).isoformat()
    quote = _public_quote(generated_at_utc=old)
    review = _review(public_quote=quote)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "public_quote_artifact_not_fresh" in review["blocking_gates"]
    assert review["answers"]["order_submission_performed"] is False


def test_candidate_mismatch_blocks_handoff() -> None:
    quote = _public_quote(candidate=_candidate(symbol="ETHUSDT", side="Buy"))
    review = _review(public_quote=quote)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "candidate_identity_alignment_failed" in review["blocking_gates"]
    assert review["admission_envelope_preview"]["order_admission_ready"] is False


def test_private_or_order_path_blocks_public_only_gate() -> None:
    quote = _public_quote(
        requests=[
            _request("server_time", "/v5/market/time"),
            _request("ticker", "/v5/order/create"),
            _request("instrument", "/v5/market/instruments-info"),
        ]
    )
    review = _review(public_quote=quote)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "public_quote_private_or_order_path_present" in review["blocking_gates"]
    assert review["gates"]["public_quote_public_only"] is False
