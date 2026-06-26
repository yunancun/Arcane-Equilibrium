from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from cost_gate_learning_lane.atomic_quote_adapter_preview_design import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    STALE_ADAPTER_EVIDENCE_MISSING_STATUS,
    build_atomic_quote_adapter_preview_design,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 9, 45, tzinfo=dt.timezone.utc)


def _candidate() -> dict:
    return {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }


def _reviewed_packet(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_reviewed_public_quote_capture_packet_v1",
        "status": "REVIEWED_PUBLIC_QUOTE_CAPTURE_PACKET_READY_NO_CAPTURE_NO_AUTHORITY",
        "candidate": _candidate(),
        "summary": {
            "runtime_capture_allowed_by_this_packet": False,
            "public_quote_capture_performed": False,
            "network_call_performed": False,
            "request_count": 3,
        },
        "review_packet": {
            "future_capture_source": {
                "source_helper": (
                    "helper_scripts/research/cost_gate_learning_lane/"
                    "bbo_freshness_public_quote_capture.py"
                ),
                "requires_separate_pm_e3_bb_review_before_runtime_capture": True,
                "runtime_capture_allowed_by_this_packet": False,
            },
            "request_envelope_review": {
                "method": "GET",
                "auth_or_cookie_headers_allowed": False,
                "private_or_order_paths_allowed": False,
                "redirects_allowed": False,
                "additional_requests_allowed": False,
                "required_requests": [
                    {
                        "label": "server_time",
                        "method": "GET",
                        "path": "/v5/market/time",
                        "query": {},
                        "auth_or_cookie_headers_allowed": False,
                        "private_or_order_paths_allowed": False,
                        "capture_permitted_by_this_packet": False,
                    },
                    {
                        "label": "ticker",
                        "method": "GET",
                        "path": "/v5/market/tickers",
                        "query": {"category": "linear", "symbol": "AVAXUSDT"},
                        "auth_or_cookie_headers_allowed": False,
                        "private_or_order_paths_allowed": False,
                        "capture_permitted_by_this_packet": False,
                    },
                    {
                        "label": "instrument",
                        "method": "GET",
                        "path": "/v5/market/instruments-info",
                        "query": {"category": "linear", "symbol": "AVAXUSDT"},
                        "auth_or_cookie_headers_allowed": False,
                        "private_or_order_paths_allowed": False,
                        "capture_permitted_by_this_packet": False,
                    },
                ],
            },
            "freshness_and_market_data_gates": {
                "max_fresh_bbo_age_ms": 1000,
                "raw_public_quote_is_not_construction_input": True,
            },
            "handoff_contract": {
                "raw_quote_can_feed_order_construction_directly": False,
                "public_quote_to_snapshot_adapter": {
                    "source_helper": (
                        "helper_scripts/research/cost_gate_learning_lane/"
                        "public_quote_market_snapshot_adapter.py"
                    ),
                    "requires_public_quote_path_sha": True,
                    "requires_candidate_exact_match": True,
                },
                "snapshot_to_construction_preview": {
                    "source_helper": (
                        "helper_scripts/research/cost_gate_learning_lane/"
                        "bounded_probe_candidate_construction_preview.py"
                    ),
                    "requires_fresh_bbo": True,
                    "order_admission_ready_from_this_contract": False,
                },
            },
        },
        "answers": {
            "bybit_call_performed": False,
            "public_quote_capture_performed": False,
            "order_submission_performed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "main_cost_gate_adjustment": "NONE",
        },
    }
    payload.update(overrides)
    return payload


def _stale_session(**overrides) -> dict:
    payload = {
        "active_blocker_id": (
            "P1-AGGRESSIVE-ALPHA-QUOTE-TO-ADAPTER-FRESHNESS-REVIEW-NO-ORDER"
        ),
        "new_evidence_delta_found": (
            "Adapter CLI failed closed with public_quote_stale_at_adapter_generation; "
            "no market snapshot or construction preview was emitted."
        ),
        "anti_repeat_decision": "PROCEED_SOURCE_ONLY_FRESHNESS_REVIEW_NO_SECOND_CAPTURE",
        "next_blocker_id": (
            "P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-DESIGN-NO-CAPTURE"
        ),
        "artifact_mtimes": {
            "local_public_quote_capture": {
                "status": "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER",
                "sha256": "a" * 64,
                "max_fresh_bbo_age_ms": 1000,
            },
            "adapter_cli_attempt": {
                "command_exit_code": 1,
                "fail_closed_reason": "public_quote_stale_at_adapter_generation",
                "json_output_exists": False,
                "markdown_output_exists": False,
                "market_snapshot_emitted": False,
                "construction_preview_emitted": False,
            }
        },
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_atomic_design_ready_no_capture(tmp_path: Path) -> None:
    reviewed = _reviewed_packet()
    stale = _stale_session()
    reviewed_path = tmp_path / "reviewed.json"
    stale_path = tmp_path / "stale.json"
    _write_json(reviewed_path, reviewed)
    _write_json(stale_path, stale)

    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=reviewed,
        stale_adapter_review_session=stale,
        reviewed_public_quote_packet_path=reviewed_path,
        stale_adapter_review_session_path=stale_path,
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["summary"]["capture_performed_by_this_packet"] is False
    assert packet["summary"]["adapter_performed_by_this_packet"] is False
    assert packet["summary"]["construction_preview_performed_by_this_packet"] is False
    assert packet["summary"]["pm_e3_bb_required_before_future_capture"] is True
    assert packet["summary"]["max_fresh_bbo_age_ms"] == 1000

    design = packet["design"]
    steps = design["atomic_flow_steps"]
    assert [step["name"] for step in steps] == [
        "public_quote_capture",
        "immediate_public_quote_to_market_snapshot_adapter",
        "immediate_no_order_construction_preview",
        "atomic_summary_packet",
    ]
    assert steps[0]["requires_pm_e3_bb_review"] is True
    assert "--skip-instruments-info" in steps[0]["forbidden_flags"]
    assert steps[1]["generated_at_override_allowed"] is False
    assert steps[1]["max_fresh_bbo_age_ms"] == 1000
    assert steps[2]["order_submission_allowed"] is False
    assert steps[2]["requires_market_snapshot_schema_version"] == (
        "bounded_probe_candidate_market_snapshot_v1"
    )
    assert steps[2]["requires_adapter_status"] == (
        "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER"
    )
    assert steps[2]["requires_adapter_public_quote_path_sha256"] is True
    assert steps[2]["requires_adapter_reroute_review_path_sha256"] is True
    assert design["freshness_contract"]["must_not_lower_or_widen_freshness_gate"] is True
    assert design["freshness_contract"]["raw_public_quote_may_not_feed_construction_directly"] is True
    assert "public_quote_capture" in design["proof_exclusions"]
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert "Atomic Quote Adapter Preview Design No-Capture" in markdown


def test_missing_stale_adapter_evidence_fails_closed() -> None:
    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=_reviewed_packet(),
        stale_adapter_review_session=_stale_session(new_evidence_delta_found="no failure"),
        now_utc=NOW,
    )

    assert packet["status"] == STALE_ADAPTER_EVIDENCE_MISSING_STATUS
    assert packet["design"] == {}
    assert "stale_adapter_failure_reason_missing" in packet["readiness"]["blocking_reasons"]
    assert packet["answers"]["public_quote_capture_performed"] is False


def test_missing_structured_stale_quote_artifact_fails_closed() -> None:
    stale = _stale_session()
    stale["artifact_mtimes"] = {}

    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=_reviewed_packet(),
        stale_adapter_review_session=stale,
        now_utc=NOW,
    )

    assert packet["status"] == STALE_ADAPTER_EVIDENCE_MISSING_STATUS
    assert "stale_review_quote_capture_status_missing" in packet["readiness"]["blocking_reasons"]
    assert "stale_review_quote_capture_sha_missing" in packet["readiness"]["blocking_reasons"]


def test_missing_structured_adapter_cli_attempt_fails_closed() -> None:
    stale = _stale_session()
    stale["artifact_mtimes"].pop("adapter_cli_attempt")

    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=_reviewed_packet(),
        stale_adapter_review_session=stale,
        now_utc=NOW,
    )

    assert packet["status"] == STALE_ADAPTER_EVIDENCE_MISSING_STATUS
    assert "adapter_cli_attempt_nonzero_exit_missing" in packet["readiness"]["blocking_reasons"]
    assert "adapter_cli_attempt_fail_closed_reason_missing" in packet["readiness"]["blocking_reasons"]


def test_authority_contamination_fails_closed() -> None:
    reviewed = _reviewed_packet()
    reviewed["answers"]["order_authority_granted"] = True

    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=reviewed,
        stale_adapter_review_session=_stale_session(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["design"] == {}
    assert "order_authority_granted_contaminating" in packet["readiness"]["blocking_reasons"]
    assert packet["answers"]["order_authority_granted"] is False


def test_semantic_authority_text_fails_closed() -> None:
    cases = [
        ("allowed_actions", ["submit_order"], "allowed_actions_semantic_value_contaminating"),
        (
            "operator_response",
            "you may submit orders now",
            "operator_response_semantic_value_contaminating",
        ),
        (
            "reason",
            "operator says order authority granted",
            "reason_semantic_value_contaminating",
        ),
    ]
    for key, value, expected in cases:
        stale = _stale_session(**{key: value})

        packet = build_atomic_quote_adapter_preview_design(
            reviewed_public_quote_packet=_reviewed_packet(),
            stale_adapter_review_session=stale,
            now_utc=NOW,
        )

        assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
        assert expected in packet["readiness"]["blocking_reasons"]
        assert packet["design"] == {}


def test_wide_freshness_gate_fails_closed() -> None:
    reviewed = _reviewed_packet()
    reviewed["review_packet"]["freshness_and_market_data_gates"][
        "max_fresh_bbo_age_ms"
    ] = 1500

    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=reviewed,
        stale_adapter_review_session=_stale_session(),
        now_utc=NOW,
    )

    assert packet["status"] == "REVIEWED_PUBLIC_QUOTE_PACKET_NOT_READY"
    assert "freshness_gate_wider_than_canonical" in packet["readiness"]["blocking_reasons"]
    assert packet["answers"]["freshness_gate_lowering_recommended"] is False


def test_reviewed_packet_request_envelope_mismatch_fails_closed() -> None:
    reviewed = _reviewed_packet()
    reviewed["review_packet"]["request_envelope_review"]["required_requests"][1][
        "query"
    ] = {"category": "linear", "symbol": "ETHUSDT"}

    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=reviewed,
        stale_adapter_review_session=_stale_session(),
        now_utc=NOW,
    )

    assert packet["status"] == "REVIEWED_PUBLIC_QUOTE_PACKET_NOT_READY"
    assert "ticker_query_mismatch" in packet["readiness"]["blocking_reasons"]
    assert packet["answers"]["network_call_performed"] is False


def test_cli_rejects_latest_output_and_returns_nonzero_on_fail_closed(tmp_path: Path) -> None:
    reviewed = _reviewed_packet()
    stale = _stale_session(new_evidence_delta_found="no failure")
    reviewed_path = tmp_path / "reviewed.json"
    stale_path = tmp_path / "stale.json"
    _write_json(reviewed_path, reviewed)
    _write_json(stale_path, stale)

    latest = tmp_path / "atomic_design_latest.json"
    latest_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cost_gate_learning_lane.atomic_quote_adapter_preview_design",
            "--reviewed-public-quote-packet-json",
            str(reviewed_path),
            "--stale-adapter-review-session-json",
            str(stale_path),
            "--json-output",
            str(latest),
        ],
        cwd=Path.cwd(),
        env={"PYTHONPATH": "helper_scripts/research"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert latest_result.returncode != 0
    assert "output_path_latest_overwrite_forbidden" in latest_result.stderr

    runtime_path_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cost_gate_learning_lane.atomic_quote_adapter_preview_design",
            "--reviewed-public-quote-packet-json",
            str(reviewed_path),
            "--stale-adapter-review-session-json",
            str(stale_path),
            "--json-output",
            "/tmp/openclaw/cost_gate_learning_lane/../cost_gate_learning_lane/foo.json",
        ],
        cwd=Path.cwd(),
        env={"PYTHONPATH": "helper_scripts/research"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert runtime_path_result.returncode != 0
    assert "canonical_runtime_artifact_path_forbidden" in runtime_path_result.stderr

    fail_output = tmp_path / "fail.json"
    fail_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cost_gate_learning_lane.atomic_quote_adapter_preview_design",
            "--reviewed-public-quote-packet-json",
            str(reviewed_path),
            "--stale-adapter-review-session-json",
            str(stale_path),
            "--json-output",
            str(fail_output),
        ],
        cwd=Path.cwd(),
        env={"PYTHONPATH": "helper_scripts/research"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert fail_result.returncode == 2
    assert json.loads(fail_output.read_text(encoding="utf-8"))["status"] == (
        STALE_ADAPTER_EVIDENCE_MISSING_STATUS
    )


def test_static_no_network_db_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "atomic_quote_adapter_preview_design.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "import requests",
        "urllib",
        "ccxt",
        "pybit",
        "subprocess",
        "urlopen",
        "create_order",
        "cancel_order",
        "place_order",
    ]
    for needle in forbidden:
        assert needle not in source
