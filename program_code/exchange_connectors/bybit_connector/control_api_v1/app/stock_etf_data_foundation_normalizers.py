from __future__ import annotations

"""Data-foundation status normalizers for the Stock/ETF display-only surface."""

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _SAFETY_FALSE_FIELDS,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
)

_INSTRUMENT_IDENTITY_CONTRACT_ID = "instrument_identity_contract_v1"
_REFERENCE_DATA_SOURCES_CONTRACT_ID = "stock_etf_reference_data_sources_v1"


def _instrument_identity_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _INSTRUMENT_IDENTITY_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "symbol": "",
        "instrument_kind": "stock",
        "listing_venue": "unknown_denied",
        "primary_exchange": "unknown_denied",
        "currency": "unknown_denied",
        "tradability_status": "unknown_denied",
        "priips_kid_status": "unknown_denied",
        "fractional_policy_recorded": False,
        "point_in_time_asof_ms": 0,
        "market_calendar_id_present": False,
        "market_calendar_hash_present": False,
        "broker_contract_details_hash_present": False,
        "instrument_identity_hash_present": False,
        "corporate_action_adjustment_version_hash_present": False,
        "source_artifact_hash_present": False,
        "bybit_live_execution_unchanged": True,
        "ibkr_live_denied": True,
        "margin_short_denied": True,
        "options_cfd_denied": True,
        "ibkr_contact_performed": False,
        "secret_content_serialized": False,
    }


def _reference_sources_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _REFERENCE_DATA_SOURCES_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "environment": "paper",
        "frozen_for_evidence_clock": False,
        "corporate_action_source_name": "",
        "corporate_action_asof_ms": 0,
        "corporate_action_raw_hash_present": False,
        "corporate_action_adjustment_version_hash_present": False,
        "corporate_action_policy_hash_present": False,
        "dividend_treatment_hash_present": False,
        "fx_rate_source_name": "",
        "fx_rate_asof_ms": 0,
        "base_currency": "unknown_denied",
        "quote_currency": "unknown_denied",
        "fx_rate_snapshot_hash_present": False,
        "fx_drag_model_hash_present": False,
        "fee_schedule_source_name": "",
        "fee_schedule_asof_ms": 0,
        "commission_schedule_hash_present": False,
        "exchange_regulatory_fee_hash_present": False,
        "tax_ftt_placeholder_hash_present": False,
        "withholding_tax_treatment_hash_present": False,
        "source_artifact_hash_present": False,
        "bybit_live_execution_unchanged": True,
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "secret_content_serialized": False,
        "live_or_tiny_live_authorized": False,
    }


def _normalize_instrument_identity(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _instrument_identity_fail_closed(reason or "missing_instrument_identity")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _INSTRUMENT_IDENTITY_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "symbol": _as_str(source.get("symbol"), ""),
        "instrument_kind": _as_str(source.get("instrument_kind"), "stock"),
        "listing_venue": _as_str(source.get("listing_venue"), "unknown_denied"),
        "primary_exchange": _as_str(source.get("primary_exchange"), "unknown_denied"),
        "currency": _as_str(source.get("currency"), "unknown_denied"),
        "tradability_status": _as_str(
            source.get("tradability_status"),
            "unknown_denied",
        ),
        "priips_kid_status": _as_str(
            source.get("priips_kid_status"),
            "unknown_denied",
        ),
        "fractional_policy_recorded": _as_bool(
            source.get("fractional_policy_recorded")
        ),
        "point_in_time_asof_ms": _as_int(source.get("point_in_time_asof_ms")),
        "market_calendar_id_present": _as_bool(
            source.get("market_calendar_id_present")
        ),
        "market_calendar_hash_present": _as_bool(
            source.get("market_calendar_hash_present")
        ),
        "broker_contract_details_hash_present": _as_bool(
            source.get("broker_contract_details_hash_present")
        ),
        "instrument_identity_hash_present": _as_bool(
            source.get("instrument_identity_hash_present")
        ),
        "corporate_action_adjustment_version_hash_present": _as_bool(
            source.get("corporate_action_adjustment_version_hash_present")
        ),
        "source_artifact_hash_present": _as_bool(
            source.get("source_artifact_hash_present")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "ibkr_live_denied": source.get("ibkr_live_denied") is not False,
        "margin_short_denied": source.get("margin_short_denied") is not False,
        "options_cfd_denied": source.get("options_cfd_denied") is not False,
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
    }


def _normalize_reference_sources(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _reference_sources_fail_closed(reason or "missing_reference_sources")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _REFERENCE_DATA_SOURCES_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "environment": _as_str(source.get("environment"), "paper"),
        "frozen_for_evidence_clock": _as_bool(
            source.get("frozen_for_evidence_clock")
        ),
        "corporate_action_source_name": _as_str(
            source.get("corporate_action_source_name"),
            "",
        ),
        "corporate_action_asof_ms": _as_int(
            source.get("corporate_action_asof_ms")
        ),
        "corporate_action_raw_hash_present": _as_bool(
            source.get("corporate_action_raw_hash_present")
        ),
        "corporate_action_adjustment_version_hash_present": _as_bool(
            source.get("corporate_action_adjustment_version_hash_present")
        ),
        "corporate_action_policy_hash_present": _as_bool(
            source.get("corporate_action_policy_hash_present")
        ),
        "dividend_treatment_hash_present": _as_bool(
            source.get("dividend_treatment_hash_present")
        ),
        "fx_rate_source_name": _as_str(source.get("fx_rate_source_name"), ""),
        "fx_rate_asof_ms": _as_int(source.get("fx_rate_asof_ms")),
        "base_currency": _as_str(source.get("base_currency"), "unknown_denied"),
        "quote_currency": _as_str(source.get("quote_currency"), "unknown_denied"),
        "fx_rate_snapshot_hash_present": _as_bool(
            source.get("fx_rate_snapshot_hash_present")
        ),
        "fx_drag_model_hash_present": _as_bool(
            source.get("fx_drag_model_hash_present")
        ),
        "fee_schedule_source_name": _as_str(
            source.get("fee_schedule_source_name"),
            "",
        ),
        "fee_schedule_asof_ms": _as_int(source.get("fee_schedule_asof_ms")),
        "commission_schedule_hash_present": _as_bool(
            source.get("commission_schedule_hash_present")
        ),
        "exchange_regulatory_fee_hash_present": _as_bool(
            source.get("exchange_regulatory_fee_hash_present")
        ),
        "tax_ftt_placeholder_hash_present": _as_bool(
            source.get("tax_ftt_placeholder_hash_present")
        ),
        "withholding_tax_treatment_hash_present": _as_bool(
            source.get("withholding_tax_treatment_hash_present")
        ),
        "source_artifact_hash_present": _as_bool(
            source.get("source_artifact_hash_present")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(
            source.get("connector_runtime_started")
        ),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
    }


def _identity_has_required_source_proofs(identity: dict[str, Any]) -> bool:
    required_booleans = (
        "fractional_policy_recorded",
        "market_calendar_id_present",
        "market_calendar_hash_present",
        "broker_contract_details_hash_present",
        "instrument_identity_hash_present",
        "corporate_action_adjustment_version_hash_present",
        "source_artifact_hash_present",
        "bybit_live_execution_unchanged",
        "ibkr_live_denied",
        "margin_short_denied",
        "options_cfd_denied",
    )
    return (
        _as_str(identity.get("contract_id"), "") == _INSTRUMENT_IDENTITY_CONTRACT_ID
        and _as_int(identity.get("source_version")) == 1
        and _as_int(identity.get("point_in_time_asof_ms")) > 0
        and _as_str(identity.get("symbol"), "") != ""
        and all(_as_bool(identity.get(key)) for key in required_booleans)
    )


def _reference_has_required_source_proofs(reference: dict[str, Any]) -> bool:
    required_booleans = (
        "frozen_for_evidence_clock",
        "corporate_action_raw_hash_present",
        "corporate_action_adjustment_version_hash_present",
        "corporate_action_policy_hash_present",
        "dividend_treatment_hash_present",
        "fx_rate_snapshot_hash_present",
        "fx_drag_model_hash_present",
        "commission_schedule_hash_present",
        "exchange_regulatory_fee_hash_present",
        "tax_ftt_placeholder_hash_present",
        "withholding_tax_treatment_hash_present",
        "source_artifact_hash_present",
        "bybit_live_execution_unchanged",
    )
    required_strings = (
        "corporate_action_source_name",
        "fx_rate_source_name",
        "fee_schedule_source_name",
    )
    return (
        _as_str(reference.get("contract_id"), "") == _REFERENCE_DATA_SOURCES_CONTRACT_ID
        and _as_int(reference.get("source_version")) == 1
        and _as_int(reference.get("corporate_action_asof_ms")) > 0
        and _as_int(reference.get("fx_rate_asof_ms")) > 0
        and _as_int(reference.get("fee_schedule_asof_ms")) > 0
        and all(_as_bool(reference.get(key)) for key in required_booleans)
        and all(_as_str(reference.get(key), "") != "" for key in required_strings)
    )


def _data_foundation_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    identity: dict[str, Any],
    reference: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    for key in (
        "phase2_started",
        "phase3_started",
        "contract_details_request_started",
        "reference_data_collection_started",
        "collector_started",
        "market_data_ingestion_started",
        "connector_runtime_started",
        "db_apply_performed",
        "evidence_clock_started",
        "scorecard_writer_started",
    ):
        if _as_bool(source.get(key)):
            violations.append(key)
    if reason is not None:
        return violations
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper") != "paper":
        violations.append("environment_mismatch")
    if (
        _as_str(identity.get("expected_contract_id"), "")
        != _INSTRUMENT_IDENTITY_CONTRACT_ID
    ):
        violations.append("instrument_expected_contract_id_mismatch")
    if (
        _as_str(reference.get("expected_contract_id"), "")
        != _REFERENCE_DATA_SOURCES_CONTRACT_ID
    ):
        violations.append("reference_expected_contract_id_mismatch")
    if _as_bool(identity.get("ibkr_contact_performed")):
        violations.append("instrument_ibkr_contact_performed")
    if _as_bool(identity.get("secret_content_serialized")):
        violations.append("instrument_secret_content_serialized")
    if not _as_bool(identity.get("bybit_live_execution_unchanged")):
        violations.append("instrument_bybit_live_not_protected")
    if not _as_bool(identity.get("ibkr_live_denied")):
        violations.append("instrument_ibkr_live_not_denied")
    if not _as_bool(identity.get("margin_short_denied")):
        violations.append("instrument_margin_short_not_denied")
    if not _as_bool(identity.get("options_cfd_denied")):
        violations.append("instrument_options_cfd_not_denied")
    if _as_bool(identity.get("accepted")) and not _identity_has_required_source_proofs(
        identity
    ):
        violations.append("instrument_accepted_without_source_proofs")
    if _as_bool(reference.get("ibkr_contact_performed")):
        violations.append("reference_ibkr_contact_performed")
    if _as_bool(reference.get("connector_runtime_started")):
        violations.append("reference_connector_runtime_started")
    if _as_bool(reference.get("secret_content_serialized")):
        violations.append("reference_secret_content_serialized")
    if _as_bool(reference.get("live_or_tiny_live_authorized")):
        violations.append("reference_live_or_tiny_live_authorized")
    if not _as_bool(reference.get("bybit_live_execution_unchanged")):
        violations.append("reference_bybit_live_not_protected")
    if _as_bool(reference.get("accepted")) and not _reference_has_required_source_proofs(
        reference
    ):
        violations.append("reference_accepted_without_source_proofs")
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_data_foundation_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    identity = _normalize_instrument_identity(
        source.get("instrument_identity"),
        reason,
    )
    reference = _normalize_reference_sources(
        source.get("reference_data_sources"),
        reason,
    )

    contract_violations = _data_foundation_status_contract_violations(
        source,
        phase2,
        identity,
        reference,
        reason,
    )
    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    status_state = "blocked"
    if contract_violations:
        status_state = "contract_violation_blocked"
    elif reason is not None:
        status_state = "degraded"
    elif _as_bool(identity.get("accepted")) and _as_bool(reference.get("accepted")):
        status_state = "source_ready"

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "gui_authority": "display_only",
        "data_foundation_status_state": status_state,
        "phase": _as_str(
            source.get("phase"),
            "phase2_data_foundation_status_source_fixture",
        ),
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": _as_bool(
            phase2.get("first_ibkr_contact_allowed")
        ),
        "immutable_pass_artifact_present": _as_bool(
            phase2.get("immutable_pass_artifact_present")
        ),
        "connector_enabled": _as_bool(phase2.get("connector_enabled")),
        "instrument_identity": identity,
        "reference_data_sources": reference,
        "phase2_started": False,
        "phase3_started": False,
        "contract_details_request_started": False,
        "reference_data_collection_started": False,
        "collector_started": False,
        "market_data_ingestion_started": False,
        "connector_runtime_started": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "scorecard_writer_started": False,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_data_foundation_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
