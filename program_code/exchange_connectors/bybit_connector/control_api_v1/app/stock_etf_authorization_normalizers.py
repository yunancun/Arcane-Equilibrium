from __future__ import annotations

"""Authorization status normalizers for the Stock/ETF display-only surface."""

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

_AUTH_MATRIX_CONTRACT_ID = "feature_flag_secret_auth_matrix_v1"
_SECRET_SLOT_CONTRACT_ID = "ibkr_secret_slot_contract_v1"
_PHASE2_GATE_CONTRACT_ID = "phase2_ibkr_external_surface_gate_v1"
_SESSION_ATTESTATION_CONTRACT_ID = "ibkr_session_attestation_v1"


def _matrix_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _AUTH_MATRIX_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "gui_lane_state_override_denied": True,
        "server_rust_matrix_authoritative": True,
        "request_asset_lane": "stock_etf_cash",
        "request_broker": "ibkr",
        "request_environment": "paper",
        "request_instrument_kind": "stock",
        "request_operation": "paper_order_submit",
        "request_allowed": False,
        "effective_authority_scope": "denied",
        "blockers": [reason],
    }


def _secret_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _SECRET_SLOT_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "contract_present": False,
        "readonly_slot_posture": "unknown",
        "paper_slot_posture": "unknown",
        "live_slot_posture": "unknown",
        "owner_only_permissions": False,
        "env_var_credential_fallback_denied": False,
        "live_secret_absent_or_empty": False,
        "secret_slot_fingerprint_present": False,
        "account_fingerprint_hash_present": False,
        "secret_content_serialized": False,
        "account_id_serialized": False,
    }


def _phase2_artifact_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _PHASE2_GATE_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "ibkr_contact_allowed": False,
        "blockers": [reason],
        "artifact_id_present": False,
        "sealed": False,
        "raw_artifact_hash_present": False,
        "redacted_summary_hash_present": False,
    }


def _session_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _SESSION_ATTESTATION_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "status": "BLOCKED",
        "attestation_accepted": False,
        "blockers": [reason],
        "environment": "read_only",
        "account_fingerprint_present": False,
        "account_fingerprint_is_live": False,
        "secret_slot_fingerprint_present": False,
        "api_server_version_present": False,
        "raw_artifact_hash_present": False,
    }


def _envelope_fail_closed() -> dict[str, Any]:
    return {
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "permission_scope": "denied",
        "secret_slot_fingerprint_present": False,
        "account_fingerprint_hash_present": False,
        "risk_config_hash_present": False,
        "expires_at_ms": 0,
    }


def _normalize_matrix(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _matrix_fail_closed(reason or "missing_authorization_matrix")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _AUTH_MATRIX_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "gui_lane_state_override_denied": source.get(
            "gui_lane_state_override_denied"
        )
        is not False,
        "server_rust_matrix_authoritative": source.get(
            "server_rust_matrix_authoritative"
        )
        is not False,
        "request_asset_lane": _as_str(source.get("request_asset_lane"), ""),
        "request_broker": _as_str(source.get("request_broker"), ""),
        "request_environment": _as_str(source.get("request_environment"), ""),
        "request_instrument_kind": _as_str(source.get("request_instrument_kind"), ""),
        "request_operation": _as_str(source.get("request_operation"), ""),
        "request_allowed": _as_bool(source.get("request_allowed")),
        "effective_authority_scope": _as_str(
            source.get("effective_authority_scope"),
            "denied",
        ),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
    }


def _normalize_secret(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _secret_fail_closed(reason or "missing_secret_slot_contract")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _SECRET_SLOT_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "contract_present": _as_bool(source.get("contract_present")),
        "readonly_slot_posture": _as_str(source.get("readonly_slot_posture"), "unknown"),
        "paper_slot_posture": _as_str(source.get("paper_slot_posture"), "unknown"),
        "live_slot_posture": _as_str(source.get("live_slot_posture"), "unknown"),
        "owner_only_permissions": _as_bool(source.get("owner_only_permissions")),
        "env_var_credential_fallback_denied": _as_bool(
            source.get("env_var_credential_fallback_denied")
        ),
        "live_secret_absent_or_empty": _as_bool(
            source.get("live_secret_absent_or_empty")
        ),
        "secret_slot_fingerprint_present": _as_bool(
            source.get("secret_slot_fingerprint_present")
        ),
        "account_fingerprint_hash_present": _as_bool(
            source.get("account_fingerprint_hash_present")
        ),
        "secret_content_serialized": _as_bool(
            source.get("secret_content_serialized")
        ),
        "account_id_serialized": _as_bool(source.get("account_id_serialized")),
    }


def _normalize_phase2_artifact(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _phase2_artifact_fail_closed(reason or "missing_phase2_gate_artifact")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _PHASE2_GATE_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "ibkr_contact_allowed": _as_bool(source.get("ibkr_contact_allowed")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "artifact_id_present": _as_bool(source.get("artifact_id_present")),
        "sealed": _as_bool(source.get("sealed")),
        "raw_artifact_hash_present": _as_bool(
            source.get("raw_artifact_hash_present")
        ),
        "redacted_summary_hash_present": _as_bool(
            source.get("redacted_summary_hash_present")
        ),
    }


def _normalize_session(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _session_fail_closed(reason or "missing_session_attestation")
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
        "attestation_accepted": _as_bool(source.get("attestation_accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "environment": _as_str(source.get("environment"), "read_only"),
        "account_fingerprint_present": _as_bool(
            source.get("account_fingerprint_present")
        ),
        "account_fingerprint_is_live": _as_bool(
            source.get("account_fingerprint_is_live")
        ),
        "secret_slot_fingerprint_present": _as_bool(
            source.get("secret_slot_fingerprint_present")
        ),
        "api_server_version_present": _as_bool(
            source.get("api_server_version_present")
        ),
        "raw_artifact_hash_present": _as_bool(
            source.get("raw_artifact_hash_present")
        ),
    }


def _normalize_envelope(value: Any) -> dict[str, Any]:
    fallback = _envelope_fail_closed()
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "asset_lane": _as_str(source.get("asset_lane"), "stock_etf_cash"),
        "broker": _as_str(source.get("broker"), "ibkr"),
        "environment": _as_str(source.get("environment"), "paper"),
        "permission_scope": _as_str(source.get("permission_scope"), "denied"),
        "secret_slot_fingerprint_present": _as_bool(
            source.get("secret_slot_fingerprint_present")
        ),
        "account_fingerprint_hash_present": _as_bool(
            source.get("account_fingerprint_hash_present")
        ),
        "risk_config_hash_present": _as_bool(source.get("risk_config_hash_present")),
        "expires_at_ms": _as_int(source.get("expires_at_ms")),
    }


def _normalize_feature_flags(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "stock_etf_lane_enabled": _as_bool(source.get("stock_etf_lane_enabled")),
        "ibkr_readonly_enabled": _as_bool(source.get("ibkr_readonly_enabled")),
        "ibkr_paper_enabled": _as_bool(source.get("ibkr_paper_enabled")),
        "asset_lane_default": _as_str(source.get("asset_lane_default"), "crypto_perp"),
        "stock_etf_shadow_only": source.get("stock_etf_shadow_only") is not False,
    }


def _authorization_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    matrix: dict[str, Any],
    secret: dict[str, Any],
    artifact: dict[str, Any],
    session: dict[str, Any],
    envelope: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    for key in (
        "phase2_started",
        "phase3_started",
        "risk_runtime_started",
        "paper_order_rehearsal_started",
        "paper_order_submitted",
        "connector_runtime_started",
        "db_apply_performed",
        "evidence_clock_started",
        "scorecard_writer_started",
        "paper_order_authority_present",
        "scoped_authorization_present",
        "decision_lease_valid",
        "guardian_allows",
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
    if _as_str(matrix.get("expected_contract_id"), "") != _AUTH_MATRIX_CONTRACT_ID:
        violations.append("matrix_expected_contract_id_mismatch")
    if _as_bool(matrix.get("request_allowed")):
        violations.append("authorization_request_allowed")
    if _as_str(matrix.get("effective_authority_scope"), "denied") != "denied":
        violations.append("authorization_scope_not_denied")
    if not _as_bool(matrix.get("gui_lane_state_override_denied")):
        violations.append("gui_lane_state_override_not_denied")
    if not _as_bool(matrix.get("server_rust_matrix_authoritative")):
        violations.append("server_rust_matrix_not_authoritative")
    if _as_str(secret.get("expected_contract_id"), "") != _SECRET_SLOT_CONTRACT_ID:
        violations.append("secret_expected_contract_id_mismatch")
    if _as_bool(secret.get("secret_content_serialized")):
        violations.append("secret_content_serialized")
    if _as_bool(secret.get("account_id_serialized")):
        violations.append("secret_account_id_serialized")
    if _as_str(artifact.get("expected_contract_id"), "") != _PHASE2_GATE_CONTRACT_ID:
        violations.append("phase2_artifact_expected_contract_id_mismatch")
    if _as_bool(artifact.get("ibkr_contact_allowed")):
        violations.append("phase2_artifact_contact_allowed")
    if _as_str(session.get("expected_contract_id"), "") != _SESSION_ATTESTATION_CONTRACT_ID:
        violations.append("session_expected_contract_id_mismatch")
    if _as_bool(session.get("attestation_accepted")):
        violations.append("session_attestation_accepted")
    if _as_bool(session.get("account_fingerprint_is_live")):
        violations.append("session_live_account_fingerprint")
    if _as_str(envelope.get("permission_scope"), "denied") != "denied":
        violations.append("authorization_envelope_scope_not_denied")
    if _as_int(envelope.get("expires_at_ms")) > 0:
        violations.append("authorization_envelope_expiry_claimed")
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_authorization_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    matrix = _normalize_matrix(source.get("authorization_matrix"), reason)
    secret = _normalize_secret(source.get("secret_slot_contract"), reason)
    artifact = _normalize_phase2_artifact(source.get("phase2_gate_artifact"), reason)
    session = _normalize_session(source.get("session_attestation"), reason)
    envelope = _normalize_envelope(source.get("authorization_envelope"))
    feature_flags = _normalize_feature_flags(source.get("feature_flags"))

    contract_violations = _authorization_contract_violations(
        source,
        phase2,
        matrix,
        secret,
        artifact,
        session,
        envelope,
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
    elif _as_bool(matrix.get("request_allowed")):
        status_state = "paper_authority_claimed"

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "gui_authority": "display_only",
        "authorization_status_state": status_state,
        "phase": _as_str(
            source.get("phase"),
            "phase2_authorization_status_source_fixture",
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
        "authorization_matrix": matrix,
        "feature_flags": feature_flags,
        "secret_slot_contract": secret,
        "phase2_gate_artifact": artifact,
        "session_attestation": session,
        "authorization_envelope": envelope,
        "phase2_started": False,
        "phase3_started": False,
        "risk_runtime_started": False,
        "paper_order_rehearsal_started": False,
        "paper_order_submitted": False,
        "connector_runtime_started": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "scorecard_writer_started": False,
        "paper_order_authority_present": False,
        "scoped_authorization_present": False,
        "decision_lease_valid": False,
        "guardian_allows": False,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_authorization_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
