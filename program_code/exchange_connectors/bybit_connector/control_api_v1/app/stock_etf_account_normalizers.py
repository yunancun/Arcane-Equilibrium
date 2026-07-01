"""Account/connector status normalizers for the Stock/ETF display-only surface."""

from __future__ import annotations

from typing import Any

from .stock_etf_status_common import (
    _ACCOUNT_CASH_LEDGER_CONTRACT_ID,
    _DENIED_OPERATIONS,
    _PAPER_ATTESTATION_CONTRACT_ID,
    _SAFETY_FALSE_FIELDS,
    _SESSION_ATTESTATION_CONTRACT_ID,
    _account_snapshot_fail_closed,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _paper_attestation_policy_fail_closed,
    _phase2_fail_closed,
    _session_attestation_fail_closed,
)


def _normalize_account_snapshot(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _account_snapshot_fail_closed(reason or "missing_account_snapshot")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _ACCOUNT_CASH_LEDGER_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "account_fingerprint_hash_present": _as_bool(
            source.get("account_fingerprint_hash_present")
        ),
        "account_snapshot_hash_present": _as_bool(
            source.get("account_snapshot_hash_present")
        ),
        "portfolio_positions_hash_present": _as_bool(
            source.get("portfolio_positions_hash_present")
        ),
        "currency": _as_str(source.get("currency"), ""),
        "cash_balance_minor_units": _as_int(source.get("cash_balance_minor_units")),
        "buying_power_minor_units": _as_int(
            source.get("buying_power_minor_units")
        ),
        "as_of_ms": _as_int(source.get("as_of_ms")),
        "source_report_hash_present": _as_bool(
            source.get("source_report_hash_present")
        ),
    }


def _normalize_session_attestation(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _session_attestation_fail_closed(
        reason or "missing_session_attestation"
    )
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _SESSION_ATTESTATION_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "status": _as_str(source.get("status"), "BLOCKED"),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "account_fingerprint_present": _as_bool(
            source.get("account_fingerprint_present")
        ),
        "account_fingerprint_is_live": _as_bool(
            source.get("account_fingerprint_is_live")
        ),
        "environment": _as_str(source.get("environment"), "read_only"),
        "host": _as_str(source.get("host"), ""),
        "port": _as_int(source.get("port")),
        "process_identity_present": _as_bool(
            source.get("process_identity_present")
        ),
        "gateway_mode": _as_str(source.get("gateway_mode"), "unknown"),
        "secret_slot_fingerprint_present": _as_bool(
            source.get("secret_slot_fingerprint_present")
        ),
        "secret_slot_mode": _as_str(source.get("secret_slot_mode"), "unknown"),
        "secret_world_readable": _as_bool(source.get("secret_world_readable")),
        "live_secret_absent_or_empty": _as_bool(
            source.get("live_secret_absent_or_empty")
        ),
        "env_var_credential_fallback_used": _as_bool(
            source.get("env_var_credential_fallback_used")
        ),
        "api_server_version_present": _as_bool(
            source.get("api_server_version_present")
        ),
        "data_tier": _as_str(source.get("data_tier"), "unknown"),
        "entitlements_fingerprint_present": _as_bool(
            source.get("entitlements_fingerprint_present")
        ),
        "market_data_entitlement_purchase_denied": _as_bool(
            source.get("market_data_entitlement_purchase_denied")
        ),
        "gateway_started_at_ms": _as_int(source.get("gateway_started_at_ms")),
        "attested_at_ms": _as_int(source.get("attested_at_ms")),
        "expires_at_ms": _as_int(source.get("expires_at_ms")),
        "raw_artifact_hash_present": _as_bool(
            source.get("raw_artifact_hash_present")
        ),
    }


def _normalize_paper_attestation_policy(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _paper_attestation_policy_fail_closed(
        reason or "missing_paper_attestation_policy"
    )
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _PAPER_ATTESTATION_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "external_surface_gate_required": _as_bool(
            source.get("external_surface_gate_required")
        ),
        "session_attestation_required": _as_bool(
            source.get("session_attestation_required")
        ),
        "rust_lane_scoped_ipc_required": _as_bool(
            source.get("rust_lane_scoped_ipc_required")
        ),
        "decision_lease_required": _as_bool(source.get("decision_lease_required")),
        "guardian_required": _as_bool(source.get("guardian_required")),
        "paper_environment_only": _as_bool(source.get("paper_environment_only")),
        "live_account_fingerprint_denied": _as_bool(
            source.get("live_account_fingerprint_denied")
        ),
        "margin_short_options_cfd_denied": _as_bool(
            source.get("margin_short_options_cfd_denied")
        ),
    }


def _account_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    account_snapshot: dict[str, Any],
    session_attestation: dict[str, Any],
    paper_attestation_policy: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_bool(source.get("db_apply_performed")):
        violations.append("db_apply_performed")
    if reason is not None:
        return violations
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper_readonly") != "paper_readonly":
        violations.append("environment_mismatch")
    for key in (
        "phase2_started",
        "readonly_account_snapshot_started",
        "paper_account_snapshot_started",
        "account_snapshot_present",
        "portfolio_positions_snapshot_present",
        "cash_ledger_present",
        "paper_account_attestation_present",
        "session_attestation_present",
        "connector_runtime_started",
        "gateway_socket_open",
    ):
        if _as_bool(source.get(key)):
            violations.append(key)
    if (
        _as_str(account_snapshot.get("expected_contract_id"), "")
        != _ACCOUNT_CASH_LEDGER_CONTRACT_ID
    ):
        violations.append("account_snapshot_expected_contract_id_mismatch")
    if _as_bool(account_snapshot.get("accepted")):
        violations.append("account_snapshot_accepted_before_gate")
    for key in (
        "account_fingerprint_hash_present",
        "account_snapshot_hash_present",
        "portfolio_positions_hash_present",
        "source_report_hash_present",
    ):
        if _as_bool(account_snapshot.get(key)):
            violations.append(f"account_snapshot_{key}")
    if _as_int(account_snapshot.get("as_of_ms")) != 0:
        violations.append("account_snapshot_as_of_present")
    if (
        _as_str(session_attestation.get("expected_contract_id"), "")
        != _SESSION_ATTESTATION_CONTRACT_ID
    ):
        violations.append("session_attestation_expected_contract_id_mismatch")
    if _as_bool(session_attestation.get("accepted")):
        violations.append("session_attestation_accepted_before_gate")
    for key in (
        "account_fingerprint_present",
        "account_fingerprint_is_live",
        "process_identity_present",
        "secret_slot_fingerprint_present",
        "secret_world_readable",
        "live_secret_absent_or_empty",
        "env_var_credential_fallback_used",
        "api_server_version_present",
        "entitlements_fingerprint_present",
        "market_data_entitlement_purchase_denied",
        "raw_artifact_hash_present",
    ):
        if _as_bool(session_attestation.get(key)):
            violations.append(f"session_attestation_{key}")
    if _as_str(session_attestation.get("data_tier"), "unknown") != "unknown":
        violations.append("session_attestation_data_tier_present")
    if _as_int(session_attestation.get("gateway_started_at_ms")) != 0:
        violations.append("session_attestation_gateway_started_at_present")
    if _as_int(session_attestation.get("port")) != 0:
        violations.append("session_attestation_port_present")
    if _as_int(session_attestation.get("attested_at_ms")) != 0:
        violations.append("session_attestation_attested_at_present")
    if _as_int(session_attestation.get("expires_at_ms")) != 0:
        violations.append("session_attestation_expires_at_present")
    if (
        _as_str(paper_attestation_policy.get("expected_contract_id"), "")
        != _PAPER_ATTESTATION_CONTRACT_ID
    ):
        violations.append("paper_attestation_expected_contract_id_mismatch")
    if not _as_bool(paper_attestation_policy.get("paper_environment_only")):
        violations.append("paper_attestation_policy_not_paper_only")
    if not _as_bool(paper_attestation_policy.get("live_account_fingerprint_denied")):
        violations.append("paper_attestation_live_account_not_denied")
    if not _as_bool(paper_attestation_policy.get("margin_short_options_cfd_denied")):
        violations.append("paper_attestation_margin_short_options_cfd_not_denied")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_account_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    account_snapshot = _normalize_account_snapshot(
        source.get("account_snapshot"),
        reason,
    )
    session_attestation = _normalize_session_attestation(
        source.get("session_attestation"),
        reason,
    )
    paper_attestation_policy = _normalize_paper_attestation_policy(
        source.get("paper_attestation_policy"),
        reason,
    )

    contract_violations = _account_status_contract_violations(
        source,
        phase2,
        account_snapshot,
        session_attestation,
        paper_attestation_policy,
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

    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_readonly",
        "gui_authority": "display_only",
        "account_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase2_account_status_source_fixture"),
        "phase2_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "account_snapshot": account_snapshot,
        "session_attestation": session_attestation,
        "paper_attestation_policy": paper_attestation_policy,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_account_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "readonly_account_snapshot_started": False,
        "paper_account_snapshot_started": False,
        "account_snapshot_present": False,
        "portfolio_positions_snapshot_present": False,
        "cash_ledger_present": False,
        "paper_account_attestation_present": False,
        "session_attestation_present": False,
        "connector_runtime_started": False,
        "gateway_socket_open": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "db_apply_performed": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
