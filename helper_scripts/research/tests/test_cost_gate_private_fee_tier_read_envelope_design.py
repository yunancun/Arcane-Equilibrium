from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane.private_fee_tier_read_envelope_design import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    CANDIDATE_MISSING_STATUS,
    EVIDENCE_DESIGN_NOT_READY_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_private_fee_tier_read_envelope_design,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 13, 0, tzinfo=dt.timezone.utc)


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _answers(**overrides) -> dict:
    payload = {
        "private_fee_read_performed": False,
        "private_fee_tier_read_performed": False,
        "bybit_call_performed": False,
        "bybit_private_call_performed": False,
        "credential_load_performed": False,
        "network_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "live_authority_granted": False,
        "order_admission_ready": False,
        "promotion_proof": False,
        "main_cost_gate_adjustment": "NONE",
    }
    payload.update(overrides)
    return payload


def _fee_tier_maker_ratio_design(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_fee_tier_maker_ratio_evidence_design_v1",
        "status": "FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_READY_NO_ORDER",
        "candidate": _candidate(),
        "summary": {
            "fee_tier_maker_ratio_evidence_design_ready": True,
            "fee_tier_private_read_performed": False,
            "maker_ratio_proof_available_now": False,
            "order_admission_ready": False,
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def test_private_fee_tier_read_envelope_ready_without_read_or_authority() -> None:
    packet = build_private_fee_tier_read_envelope_design(
        fee_tier_maker_ratio_design=_fee_tier_maker_ratio_design(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["summary"]["private_fee_read_performed"] is False
    assert packet["summary"]["bybit_private_call_performed"] is False
    assert packet["answers"]["private_fee_read_allowed_by_this_packet"] is False
    assert packet["answers"]["private_signed_request_performed"] is False
    assert packet["answers"]["credential_load_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_proof"] is False

    scope = packet["envelope"]["future_read_scope"]
    assert scope["allowed_method"] == "GET"
    assert scope["allowed_path"] == "/v5/account/fee-rate"
    assert scope["allowed_query"] == {"category": "linear", "symbol": "AVAXUSDT"}
    assert scope["query_must_be_symbol_minimized"] is True
    assert scope["private_read_allowed_by_this_packet"] is False
    assert scope["requires_separate_runtime_review_before_execution"] is True

    response_policy = packet["envelope"]["response_validation_policy"]
    assert response_policy["candidate_symbol_exact_match_required"] == "AVAXUSDT"
    assert response_policy["numeric_fee_rates_required"] is True
    assert response_policy["strict_candidate_row_parser_required"] is True
    assert response_policy["missing_or_malformed_fee_rate_policy"].startswith(
        "fail_closed_no_fee_proof"
    )
    assert "zero_or_negative_maker_fee_policy" in response_policy
    assert response_policy["freshness_window_required_for_future_proof"] is True
    assert response_policy["demo_unsupported_endpoint_policy"].startswith(
        "record unsupported/no-proof status"
    )
    cache_policy = packet["envelope"]["runtime_cache_policy"]
    assert cache_policy["standalone_fee_proof_artifact_only"] is True
    assert cache_policy["may_replace_account_manager_fee_cache"] is False
    assert cache_policy["may_satisfy_live_fee_rate_count_assertion"] is False
    assert cache_policy["broad_category_refresh_requires_separate_review"] is True
    redaction_policy = packet["envelope"]["artifact_redaction_policy"]
    assert redaction_policy["store_ret_code_ret_msg_and_exact_candidate_fee_row"] is True
    assert redaction_policy["persist_cross_symbol_fee_rows_allowed"] is False
    proof_policy = packet["envelope"]["proof_attachment_policy"]
    assert (
        proof_policy["cross_symbol_fee_rows_are_context_only_and_not_persisted"] is True
    )
    assert "fee_schedule_observed_at_utc" in packet["envelope"][
        "future_capture_required_fields"
    ]
    assert "fee_schedule_effective_at_utc_if_exchange_provided" in packet["envelope"][
        "future_capture_required_fields"
    ]
    assert "Private Fee-Tier Read Envelope Design" in markdown


def test_authority_or_private_read_input_fails_closed() -> None:
    design = _fee_tier_maker_ratio_design()
    design["answers"]["private_fee_read_performed"] = True

    packet = build_private_fee_tier_read_envelope_design(
        fee_tier_maker_ratio_design=design,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["envelope"] == {}
    assert "private_fee_read_performed_true" in packet["source_inputs"][
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["private_fee_read_performed"] is False


def test_private_read_aliases_fail_closed() -> None:
    contaminated_inputs = []

    summary_alias = _fee_tier_maker_ratio_design()
    summary_alias["summary"]["fee_tier_private_read_performed"] = True
    contaminated_inputs.append((summary_alias, "fee_tier_private_read_performed_true"))

    permission_alias = _fee_tier_maker_ratio_design()
    permission_alias["summary"]["private_read_allowed_by_this_packet"] = True
    contaminated_inputs.append((permission_alias, "private_read_allowed_by_this_packet_true"))

    typed_confirm_alias = _fee_tier_maker_ratio_design()
    typed_confirm_alias["source_inputs"] = {
        "auth_packet_authorization_id": "auth-123",
    }
    contaminated_inputs.append((typed_confirm_alias, "auth_packet_authorization_id_true"))

    typed_match_alias = _fee_tier_maker_ratio_design()
    typed_match_alias["source_inputs"] = {"typed_confirm_matches": "true"}
    contaminated_inputs.append((typed_match_alias, "typed_confirm_matches_true"))

    for design, expected_reason in contaminated_inputs:
        packet = build_private_fee_tier_read_envelope_design(
            fee_tier_maker_ratio_design=design,
            now_utc=NOW,
        )

        assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
        assert packet["envelope"] == {}
        assert expected_reason in packet["source_inputs"][
            "authority_contamination_reasons"
        ]


def test_security_alias_vocabulary_fails_closed() -> None:
    contaminated_inputs = []

    for key, value in (
        ("private_read_performed", True),
        ("read_authority_granted", True),
        ("credential_material_loaded", True),
        ("cost_gate_lowering_performed", True),
        ("order_authority", "GRANTED"),
        ("authorizationId", "auth-123"),
        ("auth_id", "auth-123"),
        ("typedConfirmExpected", "authorize_bounded_demo_probe:..."),
        ("operator_auth_object", {"id": "auth-123"}),
    ):
        design = _fee_tier_maker_ratio_design()
        design["nested_security_alias"] = {key: value}
        contaminated_inputs.append(design)

    for design in contaminated_inputs:
        packet = build_private_fee_tier_read_envelope_design(
            fee_tier_maker_ratio_design=design,
            now_utc=NOW,
        )

        assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
        assert packet["envelope"] == {}


def test_direct_auth_fields_fail_closed() -> None:
    packet = build_private_fee_tier_read_envelope_design(
        fee_tier_maker_ratio_design=_fee_tier_maker_ratio_design(
            authorization_id="auth-123",
            typed_confirm_expected=(
                "authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:1:auth-123"
            ),
        ),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["envelope"] == {}
    reasons = packet["source_inputs"]["authority_contamination_reasons"]
    assert "authorization_id_present" in reasons
    assert "typed_confirm_expected_present" in reasons


def test_source_input_path_is_minimized(tmp_path: Path) -> None:
    input_dir = tmp_path / "secret_token_dir"
    input_dir.mkdir()
    input_path = input_dir / "fee_tier_maker_ratio_design.json"
    input_path.write_text(
        json.dumps(_fee_tier_maker_ratio_design(), sort_keys=True),
        encoding="utf-8",
    )

    packet = build_private_fee_tier_read_envelope_design(
        fee_tier_maker_ratio_design=_fee_tier_maker_ratio_design(),
        fee_tier_maker_ratio_design_path=input_path,
        now_utc=NOW,
    )

    source_inputs = packet["source_inputs"]
    assert "fee_tier_maker_ratio_design_path" not in source_inputs
    assert (
        source_inputs["fee_tier_maker_ratio_design_path_basename"]
        == "fee_tier_maker_ratio_design.json"
    )
    assert len(source_inputs["fee_tier_maker_ratio_design_sha256"]) == 64
    assert "secret_token_dir" not in json.dumps(source_inputs)


def test_non_object_json_error_uses_basename_only(tmp_path: Path) -> None:
    input_dir = tmp_path / "secret_token_dir"
    input_dir.mkdir()
    input_path = input_dir / "bad.json"
    input_path.write_text("[]", encoding="utf-8")

    from cost_gate_learning_lane.private_fee_tier_read_envelope_design import _read_json

    try:
        _read_json(input_path)
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive clarity for the assertion below
        raise AssertionError("_read_json should reject non-object JSON")

    assert "bad.json did not contain a JSON object" == message
    assert "secret_token_dir" not in message


def test_not_ready_evidence_design_fails_closed() -> None:
    packet = build_private_fee_tier_read_envelope_design(
        fee_tier_maker_ratio_design=_fee_tier_maker_ratio_design(
            status="FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_NOT_READY"
        ),
        now_utc=NOW,
    )

    assert packet["status"] == EVIDENCE_DESIGN_NOT_READY_STATUS
    assert packet["envelope"] == {}
    assert packet["answers"]["private_fee_read_allowed_by_this_packet"] is False


def test_missing_candidate_fails_closed() -> None:
    packet = build_private_fee_tier_read_envelope_design(
        fee_tier_maker_ratio_design=_fee_tier_maker_ratio_design(candidate={}),
        now_utc=NOW,
    )

    assert packet["status"] == CANDIDATE_MISSING_STATUS
    assert packet["envelope"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "private_fee_tier_read_envelope_design.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "requests",
        "urllib",
        "ccxt",
        "pybit",
        "subprocess",
        "create_order",
        "cancel_order",
        "place_order",
    ]
    for needle in forbidden:
        assert needle not in source
