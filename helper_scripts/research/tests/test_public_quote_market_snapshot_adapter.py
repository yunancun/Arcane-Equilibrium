from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cost_gate_learning_lane.bounded_probe_candidate_construction_preview import (
    READY_STATUS,
    build_candidate_construction_preview,
)
from cost_gate_learning_lane import public_quote_market_snapshot_adapter as adapter
from cost_gate_learning_lane.public_quote_market_snapshot_adapter import (
    PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE,
    build_market_snapshot_from_public_quote,
    main,
)


NOW = dt.datetime(2026, 6, 24, 20, 5, tzinfo=dt.timezone.utc)
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
        "generated_at_utc": NOW.isoformat(),
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


def _public_quote(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_probe_bbo_freshness_public_quote_capture_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER",
        "candidate": candidate or _candidate(),
        "parsed": {
            "ticker": {
                "symbol": "AVAXUSDT",
                "bid1Price": 6.174,
                "ask1Price": 6.175,
                "bid1Size": 726.5,
                "ask1Size": 71.4,
                "lastPrice": 6.174,
                "markPrice": 6.175,
                "spread_bps": 1.619564,
                "bybit_response_time_utc": (
                    NOW - dt.timedelta(milliseconds=300)
                ).isoformat(),
            },
            "instrument": {
                "category": "linear",
                "symbol": "AVAXUSDT",
                "status": "Trading",
                "tick_size": 0.001,
                "qty_step": 0.1,
                "min_notional": 5.0,
                "bybit_response_time_utc": (
                    NOW - dt.timedelta(milliseconds=250)
                ).isoformat(),
            },
        },
        "derived": {
            "freshness": {
                "bbo_fresh": True,
                "effective_bbo_age_ms": 300.0,
                "max_fresh_bbo_age_ms": 1000,
            }
        },
        "requests": [{}, {}, {}],
        "artifact_self_hash_sha256": "a" * 64,
        "answers": {
            "bybit_call_performed": True,
            "bybit_public_market_data_call_performed": True,
            "bybit_private_call_performed": False,
            "auth_headers_present": False,
            "pg_write_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "runtime_env_mutation_performed": False,
            "service_restart_performed": False,
            "crontab_mutation_performed": False,
            "config_mutation_performed": False,
            "risk_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _snapshot_from_quote(tmp_path, public_quote=None, reroute=None, **kwargs) -> dict:
    public_quote = public_quote or _public_quote()
    reroute = reroute or _reroute()
    quote_path = tmp_path / "quote.json"
    reroute_path = tmp_path / "reroute.json"
    _write_json(quote_path, public_quote)
    _write_json(reroute_path, reroute)
    return build_market_snapshot_from_public_quote(
        public_quote=public_quote,
        reroute_review=reroute,
        public_quote_path=quote_path,
        reroute_review_path=reroute_path,
        generated_at_utc=NOW,
        **kwargs,
    )


def test_public_quote_snapshot_adapter_enables_no_order_construction_preview(tmp_path) -> None:
    snapshot = _snapshot_from_quote(tmp_path)

    assert snapshot["source"] == PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE
    assert snapshot["adapter"]["status"] == "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER"
    assert snapshot["answers"]["bybit_call_performed"] is False
    assert snapshot["answers"]["bybit_public_market_data_call_reused_from_artifact"] is True
    assert snapshot["public_quote_artifact"]["request_count"] == 3
    assert snapshot["public_quote_artifact"]["sha256"] is not None
    assert snapshot["reroute_review_artifact"]["sha256"] is not None

    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=snapshot,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )

    assert preview["status"] == READY_STATUS
    assert preview["readiness"]["market_snapshot_ready"] is True
    assert preview["readiness"]["bbo_fresh"] is True
    assert preview["construction"]["limit_price"] == 6.175
    assert preview["construction"]["rounded_qty"] == 1.6
    assert preview["construction"]["rounded_notional_usdt"] == 9.88
    assert preview["answers"]["order_submission_performed"] is False
    assert preview["answers"]["probe_authority_granted"] is False
    assert preview["answers"]["main_cost_gate_adjustment"] == "NONE"


def test_public_quote_snapshot_adapter_rejects_mismatch_and_authority(tmp_path) -> None:
    with pytest.raises(ValueError, match="candidate_identity_mismatch"):
        _snapshot_from_quote(
            tmp_path,
            public_quote=_public_quote(candidate=_candidate(symbol="ETHUSDT")),
        )

    with pytest.raises(ValueError, match="cap_usdt_mismatch_reviewed_candidate_cap"):
        _snapshot_from_quote(tmp_path, cap_usdt=20.0)

    quote_path = tmp_path / "quote_mismatch.json"
    reroute_path = tmp_path / "reroute_mismatch.json"
    quote = _public_quote()
    reroute = _reroute()
    _write_json(quote_path, quote)
    _write_json(reroute_path, reroute)
    quote["candidate"]["symbol"] = "ETHUSDT"
    with pytest.raises(ValueError, match="public_quote_path_payload_mismatch"):
        build_market_snapshot_from_public_quote(
            public_quote=quote,
            reroute_review=reroute,
            public_quote_path=quote_path,
            reroute_review_path=reroute_path,
            generated_at_utc=NOW,
        )

    contaminated = _public_quote()
    contaminated["answers"]["order_submission_performed"] = True
    with pytest.raises(ValueError, match="order_submission_not_false"):
        _snapshot_from_quote(tmp_path, public_quote=contaminated)


def test_public_quote_snapshot_adapter_rejects_recursive_contamination(tmp_path) -> None:
    quote_cases = [
        ("private_endpoint_called", True, "public_quote_private_endpoint_called_contaminating"),
        ("cookie_headers_present", True, "public_quote_cookie_headers_present_contaminating"),
        ("pg_query_performed", True, "public_quote_pg_query_performed_contaminating"),
        ("order_cancel_modify_performed", True, "public_quote_order_cancel_modify_performed_contaminating"),
        ("writer_enabled", True, "public_quote_writer_enabled_contaminating"),
        ("runtime_probe_authority_found", True, "public_quote_runtime_probe_authority_found_contaminating"),
        ("freshness_gate_lowering_recommended", True, "public_quote_freshness_gate_lowering_recommended_contaminating"),
        ("main_cost_gate_adjustment", "LOWER", "main_cost_gate_adjustment_not_none"),
    ]
    for key, value, expected in quote_cases:
        contaminated = _public_quote()
        contaminated["answers"][key] = value
        with pytest.raises(ValueError, match=expected):
            _snapshot_from_quote(tmp_path, public_quote=contaminated)

    reroute_cases = [
        ("order_submission_performed", True, "reroute_review_order_submission_performed_contaminating"),
        ("runtime_probe_authority_found", True, "reroute_review_runtime_probe_authority_found_contaminating"),
        ("order_cancel_modify_performed", True, "reroute_review_order_cancel_modify_performed_contaminating"),
        ("main_cost_gate_adjustment", "LOWER", "reroute_review_main_cost_gate_adjustment_not_none"),
    ]
    for key, value, expected in reroute_cases:
        contaminated = _reroute()
        contaminated["answers"][key] = value
        with pytest.raises(ValueError, match=expected):
            _snapshot_from_quote(tmp_path, reroute=contaminated)


def test_public_quote_snapshot_adapter_rejects_stale_bad_instrument_and_wide_gate(tmp_path) -> None:
    stale = _public_quote()
    stale["parsed"]["ticker"]["bybit_response_time_utc"] = (
        NOW - dt.timedelta(seconds=3)
    ).isoformat()
    with pytest.raises(ValueError, match="public_quote_stale_at_adapter_generation"):
        _snapshot_from_quote(tmp_path, public_quote=stale)

    non_trading = _public_quote()
    non_trading["parsed"]["instrument"]["status"] = "PreLaunch"
    with pytest.raises(ValueError, match="instrument_not_trading"):
        _snapshot_from_quote(tmp_path, public_quote=non_trading)

    wide_gate = _public_quote()
    wide_gate["derived"]["freshness"]["max_fresh_bbo_age_ms"] = 2000
    with pytest.raises(ValueError, match="public_quote_freshness_gate_wider_than_canonical"):
        _snapshot_from_quote(tmp_path, public_quote=wide_gate, max_fresh_bbo_age_ms=1000)

    with pytest.raises(ValueError, match="max_fresh_bbo_age_ms_wider_than_canonical"):
        _snapshot_from_quote(tmp_path, max_fresh_bbo_age_ms=2000)

    strict_source_gate = _public_quote()
    strict_source_gate["derived"]["freshness"]["max_fresh_bbo_age_ms"] = 500
    with pytest.raises(
        ValueError,
        match="max_fresh_bbo_age_ms_mismatch_public_quote_gate",
    ):
        _snapshot_from_quote(
            tmp_path,
            public_quote=strict_source_gate,
            max_fresh_bbo_age_ms=1000,
        )

    missing_gate = _public_quote()
    missing_gate["derived"]["freshness"].pop("max_fresh_bbo_age_ms")
    with pytest.raises(
        ValueError,
        match="public_quote_freshness_gate_missing_or_invalid",
    ):
        _snapshot_from_quote(tmp_path, public_quote=missing_gate)

    missing_self_hash = _public_quote()
    missing_self_hash.pop("artifact_self_hash_sha256")
    with pytest.raises(ValueError, match="public_quote_self_hash_missing_or_invalid"):
        _snapshot_from_quote(tmp_path, public_quote=missing_self_hash)

    missing_requests = _public_quote()
    missing_requests["requests"] = []
    with pytest.raises(ValueError, match="public_quote_request_count_missing"):
        _snapshot_from_quote(tmp_path, public_quote=missing_requests)


def test_forged_public_quote_snapshot_source_is_not_enough_for_construction_preview(tmp_path) -> None:
    snapshot = _snapshot_from_quote(tmp_path)
    snapshot.pop("adapter")
    snapshot["public_quote_artifact"].pop("sha256")

    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=snapshot,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )

    assert preview["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "market_snapshot_read_only_source" in preview["blocking_gates"]
    assert "public_quote_adapter_status" in preview["blocking_gates"]
    assert "public_quote_provenance_path_sha" in preview["blocking_gates"]

    forged = _snapshot_from_quote(tmp_path)
    forged["adapter"]["public_quote_path"] = "/tmp/wrong-quote.json"
    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=forged,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )
    assert preview["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "public_quote_adapter_path_mismatch" in preview["blocking_gates"]

    forged = _snapshot_from_quote(tmp_path)
    forged["risk_limits"]["cap_usdt"] = 20.0
    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=forged,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )
    assert preview["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "public_quote_adapter_cap_provenance" in preview["blocking_gates"]
    assert (
        "public_quote_adapter_cap_mismatch_reroute_candidate"
        in preview["blocking_gates"]
    )

    strict_source_gate = _public_quote()
    strict_source_gate["derived"]["freshness"]["max_fresh_bbo_age_ms"] = 500
    forged = _snapshot_from_quote(tmp_path, public_quote=strict_source_gate)
    forged["risk_limits"]["max_fresh_bbo_age_ms"] = 1000
    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=forged,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )
    assert preview["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "public_quote_adapter_freshness_gate_mismatch" in preview["blocking_gates"]

    forged = _snapshot_from_quote(tmp_path)
    forged["public_quote_artifact"]["sha256"] = "not-a-sha"
    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=forged,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )
    assert preview["status"] == "CANDIDATE_CONSTRUCTION_INPUT_REQUIRED"
    assert "public_quote_provenance_path_sha" in preview["blocking_gates"]

    forged = _snapshot_from_quote(tmp_path)
    forged["answers"]["bybit_call_performed"] = True
    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=forged,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )

    assert preview["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "bybit_call_performed_contaminating" in preview[
        "authority_contamination_reasons"
    ]

    forged = _snapshot_from_quote(tmp_path)
    forged["private_endpoint_called"] = True
    preview = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=forged,
        demo_operational_authorization_available=True,
        now_utc=NOW,
    )

    assert preview["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "private_endpoint_called_contaminating" in preview[
        "authority_contamination_reasons"
    ]


def test_public_quote_snapshot_adapter_cli_writes_market_snapshot(tmp_path, monkeypatch) -> None:
    quote_path = tmp_path / "quote.json"
    reroute_path = tmp_path / "reroute.json"
    out_path = tmp_path / "snapshot.json"
    quote_path.write_text(json.dumps(_public_quote()), encoding="utf-8")
    reroute_path.write_text(json.dumps(_reroute()), encoding="utf-8")
    monkeypatch.setattr(adapter, "_utc_now", lambda: NOW)
    monkeypatch.setattr(
        "sys.argv",
        [
            "public_quote_market_snapshot_adapter",
            "--public-quote-json",
            str(quote_path),
            "--reroute-review-json",
            str(reroute_path),
            "--json-output",
            str(out_path),
        ],
    )

    assert main() == 0
    snapshot = json.loads(out_path.read_text(encoding="utf-8"))
    assert snapshot["schema_version"] == "bounded_probe_candidate_market_snapshot_v1"
    assert snapshot["public_quote_artifact"]["sha256"] is not None


def test_public_quote_snapshot_adapter_direct_script_help() -> None:
    research_root = Path(__file__).resolve().parents[1]
    script = (
        research_root
        / "cost_gate_learning_lane"
        / "public_quote_market_snapshot_adapter.py"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(research_root)
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] += os.pathsep + os.environ["PYTHONPATH"]

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=research_root.parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--public-quote-json" in result.stdout
