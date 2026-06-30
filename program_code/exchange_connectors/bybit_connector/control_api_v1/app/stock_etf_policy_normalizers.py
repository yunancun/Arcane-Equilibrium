from __future__ import annotations

"""Policy/capability status normalizers for the Stock/ETF display-only surface."""

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

_RISK_POLICY_CONTRACT_ID = "stock_etf_risk_policy_v1"
_BROKER_CAPABILITY_REGISTRY_ID = "broker_capability_registry_v1"


def _as_number(value: Any) -> int | float:
    return value if type(value) in (int, float) else 0


def _risk_policy_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _RISK_POLICY_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "config_version": 0,
        "accepted": False,
        "blockers": [reason],
        "environment": "paper",
        "enabled": False,
        "shadow_only": True,
        "max_order_notional_usd": 0,
        "max_position_notional_usd": 0,
        "max_daily_notional_usd": 0,
        "max_open_orders": 0,
        "max_open_positions": 0,
        "allow_fractional_shares": False,
        "allow_margin": False,
        "allow_short": False,
        "allow_options": False,
        "allow_cfd": False,
        "allow_transfer": False,
        "allow_live": False,
        "allowed_kind_count": 0,
        "denied_kind_count": 0,
        "requires_frozen_universe_hash": False,
        "requires_instrument_identity_hash": False,
        "requires_market_session": False,
        "cost_model_required_before_shadow_fill": False,
        "cost_model_required_before_scorecard": False,
        "commission_schedule_required": False,
        "spread_estimate_required": False,
        "slippage_estimate_required": False,
        "fx_drag_required": False,
        "conservative_fill_penalty_required": False,
        "rust_authority_required": False,
        "session_attestation_required": False,
        "decision_lease_required": False,
        "guardian_required": False,
        "idempotency_key_required": False,
        "broker_reconciliation_required": False,
        "bybit_live_execution_unchanged": True,
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "secret_content_serialized": False,
    }


def _capability_registry_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_registry_id": _BROKER_CAPABILITY_REGISTRY_ID,
        "registry_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "operation_count": 0,
        "required_audit_field_count": 0,
        "read_operation_count": 0,
        "paper_operation_count": 0,
        "denied_operation_count": 0,
        "bybit_live_execution_unchanged": True,
        "python_broker_write_authority_denied": True,
        "ibkr_live_denied": True,
        "cfd_margin_reserved_denied": True,
        "first_ibkr_contact_performed": False,
        "secret_content_serialized": False,
    }


def _normalize_risk_policy(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _risk_policy_fail_closed(reason or "missing_risk_policy")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _RISK_POLICY_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "config_version": _as_int(source.get("config_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "environment": _as_str(source.get("environment"), "paper"),
        "enabled": _as_bool(source.get("enabled")),
        "shadow_only": source.get("shadow_only") is not False,
        "max_order_notional_usd": _as_number(source.get("max_order_notional_usd")),
        "max_position_notional_usd": _as_number(
            source.get("max_position_notional_usd")
        ),
        "max_daily_notional_usd": _as_number(source.get("max_daily_notional_usd")),
        "max_open_orders": _as_int(source.get("max_open_orders")),
        "max_open_positions": _as_int(source.get("max_open_positions")),
        "allow_fractional_shares": _as_bool(source.get("allow_fractional_shares")),
        "allow_margin": _as_bool(source.get("allow_margin")),
        "allow_short": _as_bool(source.get("allow_short")),
        "allow_options": _as_bool(source.get("allow_options")),
        "allow_cfd": _as_bool(source.get("allow_cfd")),
        "allow_transfer": _as_bool(source.get("allow_transfer")),
        "allow_live": _as_bool(source.get("allow_live")),
        "allowed_kind_count": _as_int(source.get("allowed_kind_count")),
        "denied_kind_count": _as_int(source.get("denied_kind_count")),
        "requires_frozen_universe_hash": _as_bool(
            source.get("requires_frozen_universe_hash")
        ),
        "requires_instrument_identity_hash": _as_bool(
            source.get("requires_instrument_identity_hash")
        ),
        "requires_market_session": _as_bool(source.get("requires_market_session")),
        "cost_model_required_before_shadow_fill": _as_bool(
            source.get("cost_model_required_before_shadow_fill")
        ),
        "cost_model_required_before_scorecard": _as_bool(
            source.get("cost_model_required_before_scorecard")
        ),
        "commission_schedule_required": _as_bool(
            source.get("commission_schedule_required")
        ),
        "spread_estimate_required": _as_bool(source.get("spread_estimate_required")),
        "slippage_estimate_required": _as_bool(
            source.get("slippage_estimate_required")
        ),
        "fx_drag_required": _as_bool(source.get("fx_drag_required")),
        "conservative_fill_penalty_required": _as_bool(
            source.get("conservative_fill_penalty_required")
        ),
        "rust_authority_required": _as_bool(source.get("rust_authority_required")),
        "session_attestation_required": _as_bool(
            source.get("session_attestation_required")
        ),
        "decision_lease_required": _as_bool(source.get("decision_lease_required")),
        "guardian_required": _as_bool(source.get("guardian_required")),
        "idempotency_key_required": _as_bool(source.get("idempotency_key_required")),
        "broker_reconciliation_required": _as_bool(
            source.get("broker_reconciliation_required")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(
            source.get("connector_runtime_started")
        ),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
    }


def _normalize_capability_registry(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _capability_registry_fail_closed(
        reason or "missing_broker_capability_registry"
    )
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_registry_id": _as_str(
            source.get("expected_registry_id"),
            _BROKER_CAPABILITY_REGISTRY_ID,
        ),
        "registry_id": _as_str(source.get("registry_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "operation_count": _as_int(source.get("operation_count")),
        "required_audit_field_count": _as_int(
            source.get("required_audit_field_count")
        ),
        "read_operation_count": _as_int(source.get("read_operation_count")),
        "paper_operation_count": _as_int(source.get("paper_operation_count")),
        "denied_operation_count": _as_int(source.get("denied_operation_count")),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "python_broker_write_authority_denied": source.get(
            "python_broker_write_authority_denied"
        )
        is not False,
        "ibkr_live_denied": source.get("ibkr_live_denied") is not False,
        "cfd_margin_reserved_denied": source.get("cfd_margin_reserved_denied")
        is not False,
        "first_ibkr_contact_performed": _as_bool(
            source.get("first_ibkr_contact_performed")
        ),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
    }


def _risk_policy_has_required_source_proofs(policy: dict[str, Any]) -> bool:
    required_true = (
        "shadow_only",
        "bybit_live_execution_unchanged",
        "requires_frozen_universe_hash",
        "requires_instrument_identity_hash",
        "requires_market_session",
        "cost_model_required_before_shadow_fill",
        "cost_model_required_before_scorecard",
        "commission_schedule_required",
        "spread_estimate_required",
        "slippage_estimate_required",
        "fx_drag_required",
        "conservative_fill_penalty_required",
        "rust_authority_required",
        "session_attestation_required",
        "decision_lease_required",
        "guardian_required",
        "idempotency_key_required",
        "broker_reconciliation_required",
    )
    return (
        _as_str(policy.get("contract_id"), "") == _RISK_POLICY_CONTRACT_ID
        and _as_int(policy.get("source_version")) == 1
        and _as_int(policy.get("config_version")) == 1
        and _as_number(policy.get("max_order_notional_usd")) > 0
        and _as_number(policy.get("max_position_notional_usd")) > 0
        and _as_number(policy.get("max_daily_notional_usd")) > 0
        and _as_int(policy.get("max_open_orders")) > 0
        and _as_int(policy.get("max_open_positions")) > 0
        and _as_int(policy.get("allowed_kind_count")) >= 3
        and _as_int(policy.get("denied_kind_count")) >= 2
        and not _as_bool(policy.get("enabled"))
        and not any(
            _as_bool(policy.get(key))
            for key in (
                "allow_margin",
                "allow_short",
                "allow_options",
                "allow_cfd",
                "allow_transfer",
                "allow_live",
                "ibkr_contact_performed",
                "connector_runtime_started",
                "secret_content_serialized",
            )
        )
        and all(_as_bool(policy.get(key)) for key in required_true)
    )


def _registry_has_required_source_proofs(registry: dict[str, Any]) -> bool:
    return (
        _as_str(registry.get("registry_id"), "") == _BROKER_CAPABILITY_REGISTRY_ID
        and _as_int(registry.get("source_version")) == 1
        and _as_int(registry.get("operation_count")) >= 15
        and _as_int(registry.get("required_audit_field_count")) >= 7
        and _as_int(registry.get("read_operation_count")) >= 1
        and _as_int(registry.get("paper_operation_count")) >= 3
        and _as_int(registry.get("denied_operation_count")) >= 4
        and _as_bool(registry.get("bybit_live_execution_unchanged"))
        and _as_bool(registry.get("python_broker_write_authority_denied"))
        and _as_bool(registry.get("ibkr_live_denied"))
        and _as_bool(registry.get("cfd_margin_reserved_denied"))
        and not _as_bool(registry.get("first_ibkr_contact_performed"))
        and not _as_bool(registry.get("secret_content_serialized"))
    )


def _policy_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    risk: dict[str, Any],
    registry: dict[str, Any],
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
    if _as_str(risk.get("expected_contract_id"), "") != _RISK_POLICY_CONTRACT_ID:
        violations.append("risk_expected_contract_id_mismatch")
    if (
        _as_str(registry.get("expected_registry_id"), "")
        != _BROKER_CAPABILITY_REGISTRY_ID
    ):
        violations.append("registry_expected_id_mismatch")
    if _as_bool(risk.get("enabled")):
        violations.append("risk_policy_runtime_enabled")
    for key in (
        "allow_margin",
        "allow_short",
        "allow_options",
        "allow_cfd",
        "allow_transfer",
        "allow_live",
    ):
        if _as_bool(risk.get(key)):
            violations.append(f"risk_policy_{key}")
    if _as_bool(risk.get("ibkr_contact_performed")):
        violations.append("risk_policy_ibkr_contact_performed")
    if _as_bool(risk.get("connector_runtime_started")):
        violations.append("risk_policy_connector_runtime_started")
    if _as_bool(risk.get("secret_content_serialized")):
        violations.append("risk_policy_secret_content_serialized")
    if not _as_bool(risk.get("bybit_live_execution_unchanged")):
        violations.append("risk_policy_bybit_live_not_protected")
    if _as_bool(risk.get("accepted")) and not _risk_policy_has_required_source_proofs(
        risk
    ):
        violations.append("risk_policy_accepted_without_source_proofs")
    if _as_bool(registry.get("first_ibkr_contact_performed")):
        violations.append("registry_first_ibkr_contact_performed")
    if _as_bool(registry.get("secret_content_serialized")):
        violations.append("registry_secret_content_serialized")
    if not _as_bool(registry.get("bybit_live_execution_unchanged")):
        violations.append("registry_bybit_live_not_protected")
    if not _as_bool(registry.get("python_broker_write_authority_denied")):
        violations.append("registry_python_broker_write_not_denied")
    if not _as_bool(registry.get("ibkr_live_denied")):
        violations.append("registry_ibkr_live_not_denied")
    if not _as_bool(registry.get("cfd_margin_reserved_denied")):
        violations.append("registry_cfd_margin_not_denied")
    if _as_bool(registry.get("accepted")) and not _registry_has_required_source_proofs(
        registry
    ):
        violations.append("registry_accepted_without_source_proofs")
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_policy_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    risk = _normalize_risk_policy(source.get("risk_policy"), reason)
    registry = _normalize_capability_registry(
        source.get("broker_capability_registry"),
        reason,
    )

    contract_violations = _policy_status_contract_violations(
        source,
        phase2,
        risk,
        registry,
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
    elif _as_bool(risk.get("accepted")) and _as_bool(registry.get("accepted")):
        status_state = "source_ready"

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "gui_authority": "display_only",
        "policy_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase2_policy_status_source_fixture"),
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
        "risk_policy": risk,
        "broker_capability_registry": registry,
        "phase2_started": False,
        "phase3_started": False,
        "risk_runtime_started": False,
        "paper_order_rehearsal_started": False,
        "paper_order_submitted": False,
        "connector_runtime_started": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "scorecard_writer_started": False,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_policy_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
