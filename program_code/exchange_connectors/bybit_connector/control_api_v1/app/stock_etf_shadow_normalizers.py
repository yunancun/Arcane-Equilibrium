from __future__ import annotations

"""Shadow-model status normalizers for the Stock/ETF display-only surface."""

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _SAFETY_FALSE_FIELDS,
    _SHADOW_FILL_MODEL_CONTRACT_ID,
    _STRATEGY_HYPOTHESIS_CONTRACT_ID,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
    _shadow_fill_model_fail_closed,
    _strategy_hypothesis_fail_closed,
)

def _normalize_shadow_fill_model(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _shadow_fill_model_fail_closed(reason or "missing_shadow_fill_model")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _SHADOW_FILL_MODEL_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "signal_id": _as_str(source.get("signal_id"), ""),
        "side": _as_str(source.get("side"), "unknown"),
        "intended_notional_minor_units": _as_int(
            source.get("intended_notional_minor_units")
        ),
        "market_session_id": _as_str(source.get("market_session_id"), ""),
        "quote_or_bar_source_hash_present": _as_bool(
            source.get("quote_or_bar_source_hash_present")
        ),
        "conservative_fill_price_micros": _as_int(
            source.get("conservative_fill_price_micros")
        ),
        "spread_bps": _as_int(source.get("spread_bps")),
        "slippage_bps": _as_int(source.get("slippage_bps")),
        "cost_bps": _as_int(source.get("cost_bps")),
        "rejection_reason": _as_str(source.get("rejection_reason"), ""),
        "synthetic_shadow": _as_bool(source.get("synthetic_shadow")),
        "broker_paper_fill_linked": _as_bool(source.get("broker_paper_fill_linked")),
        "live_fill_linked": _as_bool(source.get("live_fill_linked")),
    }


def _normalize_strategy_hypothesis(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _strategy_hypothesis_fail_closed(reason or "missing_strategy_hypothesis")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _STRATEGY_HYPOTHESIS_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "hypothesis_id": _as_str(source.get("hypothesis_id"), ""),
        "hypothesis_version": _as_str(source.get("hypothesis_version"), ""),
        "strategy_family": _as_str(source.get("strategy_family"), "unknown_denied"),
        "primary_timeframe": _as_str(source.get("primary_timeframe"), "unknown_denied"),
        "instrument_scope": _as_str(source.get("instrument_scope"), "unknown_denied"),
        "paper_shadow_only": source.get("paper_shadow_only") is not False,
        "profitability_claimed": _as_bool(source.get("profitability_claimed")),
        "live_or_tiny_live_authority_claimed": _as_bool(
            source.get("live_or_tiny_live_authority_claimed")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "ibkr_live_denied": source.get("ibkr_live_denied") is not False,
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
    }


def _shadow_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    shadow_fill_model: dict[str, Any],
    strategy_hypothesis: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "shadow") != "shadow":
        violations.append("environment_mismatch")
    if _as_bool(source.get("phase3_started")):
        violations.append("phase3_started")
    if _as_bool(source.get("shadow_collector_started")):
        violations.append("shadow_collector_started")
    if _as_bool(source.get("shadow_signal_emitted")):
        violations.append("shadow_signal_emitted")
    if _as_bool(source.get("shadow_fill_generated")):
        violations.append("shadow_fill_generated")
    if _as_bool(source.get("scorecard_writer_started")):
        violations.append("scorecard_writer_started")
    if _as_bool(source.get("db_apply_performed")):
        violations.append("db_apply_performed")
    if _as_str(shadow_fill_model.get("expected_contract_id"), "") != (
        _SHADOW_FILL_MODEL_CONTRACT_ID
    ):
        violations.append("shadow_fill_expected_contract_id_mismatch")
    if _as_bool(shadow_fill_model.get("broker_paper_fill_linked")):
        violations.append("shadow_fill_linked_to_broker_paper_fill")
    if _as_bool(shadow_fill_model.get("live_fill_linked")):
        violations.append("shadow_fill_linked_to_live_fill")
    if _as_str(strategy_hypothesis.get("expected_contract_id"), "") != (
        _STRATEGY_HYPOTHESIS_CONTRACT_ID
    ):
        violations.append("strategy_expected_contract_id_mismatch")
    if not _as_bool(strategy_hypothesis.get("paper_shadow_only")):
        violations.append("strategy_not_paper_shadow_only")
    if _as_bool(strategy_hypothesis.get("profitability_claimed")):
        violations.append("strategy_profitability_claimed")
    if _as_bool(strategy_hypothesis.get("live_or_tiny_live_authority_claimed")):
        violations.append("strategy_live_or_tiny_live_authority_claimed")
    if not _as_bool(strategy_hypothesis.get("bybit_live_execution_unchanged")):
        violations.append("strategy_bybit_live_not_protected")
    if not _as_bool(strategy_hypothesis.get("ibkr_live_denied")):
        violations.append("strategy_ibkr_live_not_denied")
    if _as_bool(strategy_hypothesis.get("ibkr_contact_performed")):
        violations.append("strategy_ibkr_contact_performed")
    if _as_bool(strategy_hypothesis.get("secret_content_serialized")):
        violations.append("strategy_secret_content_serialized")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_shadow_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    shadow_fill_model = _normalize_shadow_fill_model(
        source.get("shadow_fill_model"),
        reason,
    )
    strategy_hypothesis = _normalize_strategy_hypothesis(
        source.get("strategy_hypothesis"),
        reason,
    )

    contract_violations = _shadow_status_contract_violations(
        source,
        phase2,
        shadow_fill_model,
        strategy_hypothesis,
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
    elif _as_bool(shadow_fill_model.get("accepted")) and _as_bool(
        strategy_hypothesis.get("accepted")
    ):
        status_state = "source_ready"

    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "shadow",
        "gui_authority": "display_only",
        "shadow_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase3_shadow_status_source_fixture"),
        "phase3_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "shadow_fill_model": shadow_fill_model,
        "strategy_hypothesis": strategy_hypothesis,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_shadow_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "shadow_collector_started": False,
        "shadow_signal_emitted": False,
        "shadow_fill_generated": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
