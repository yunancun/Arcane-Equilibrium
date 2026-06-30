"""Scorecard status normalizers for the Stock/ETF display-only surface."""

from __future__ import annotations

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _SAFETY_FALSE_FIELDS,
    _SCORECARD_VERDICT_CONTRACT_ID,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
)


def _scorecard_verdict_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _SCORECARD_VERDICT_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "verdict_label": "insufficient_evidence",
        "scorecard_input_bundle_hash_present": False,
        "evidence_clock_manifest_hash_present": False,
        "dq_manifest_hash_present": False,
        "formula_appendix_hash_present": False,
        "statistical_preregistration_hash_present": False,
        "benchmark_version_hash_present": False,
        "cost_model_version_hash_present": False,
        "strategy_hypothesis_hash_present": False,
        "reference_data_sources_hash_present": False,
        "scorecard_manifest_hash_present": False,
        "verdict_rationale_hash_present": False,
        "paper_shadow_window_trading_days": 0,
        "min_window_trading_days": 0,
        "independent_observation_count": 0,
        "min_independent_observation_count": 0,
        "gross_pnl_minor_units": 0,
        "net_pnl_minor_units": 0,
        "commission_minor_units": 0,
        "spread_slippage_minor_units": 0,
        "fx_drag_minor_units": 0,
        "tax_drag_minor_units": 0,
        "benchmark_excess_lcb_bps": 0,
        "conservative_cost_stress_lcb_bps": 0,
        "paper_shadow_divergence_bps": 0,
        "max_paper_shadow_divergence_bps": 0,
        "psr_bps": 0,
        "min_psr_bps": 0,
        "dsr_bps": 0,
        "min_dsr_bps": 0,
        "concentration_label_passed": False,
        "regime_label_passed": False,
        "breadth_label_passed": False,
        "freshness_label_passed": False,
        "survivorship_label_passed": False,
        "execution_realism_label_passed": False,
        "qc_review_hash_present": False,
        "mit_review_hash_present": False,
        "qa_review_hash_present": False,
        "qc_review_passed": False,
        "mit_review_passed": False,
        "qa_review_passed": False,
        "scorecard_is_derived_only": False,
        "paper_and_shadow_fills_separate": False,
        "live_fill_claimed": False,
        "bybit_live_execution_unchanged": False,
        "sealed": False,
    }


def _normalize_scorecard_verdict(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _scorecard_verdict_fail_closed(reason or "missing_scorecard_verdict")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _SCORECARD_VERDICT_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "verdict_label": _as_str(
            source.get("verdict_label"),
            "insufficient_evidence",
        ),
        "scorecard_input_bundle_hash_present": _as_bool(
            source.get("scorecard_input_bundle_hash_present")
        ),
        "evidence_clock_manifest_hash_present": _as_bool(
            source.get("evidence_clock_manifest_hash_present")
        ),
        "dq_manifest_hash_present": _as_bool(source.get("dq_manifest_hash_present")),
        "formula_appendix_hash_present": _as_bool(
            source.get("formula_appendix_hash_present")
        ),
        "statistical_preregistration_hash_present": _as_bool(
            source.get("statistical_preregistration_hash_present")
        ),
        "benchmark_version_hash_present": _as_bool(
            source.get("benchmark_version_hash_present")
        ),
        "cost_model_version_hash_present": _as_bool(
            source.get("cost_model_version_hash_present")
        ),
        "strategy_hypothesis_hash_present": _as_bool(
            source.get("strategy_hypothesis_hash_present")
        ),
        "reference_data_sources_hash_present": _as_bool(
            source.get("reference_data_sources_hash_present")
        ),
        "scorecard_manifest_hash_present": _as_bool(
            source.get("scorecard_manifest_hash_present")
        ),
        "verdict_rationale_hash_present": _as_bool(
            source.get("verdict_rationale_hash_present")
        ),
        "paper_shadow_window_trading_days": _as_int(
            source.get("paper_shadow_window_trading_days")
        ),
        "min_window_trading_days": _as_int(source.get("min_window_trading_days")),
        "independent_observation_count": _as_int(
            source.get("independent_observation_count")
        ),
        "min_independent_observation_count": _as_int(
            source.get("min_independent_observation_count")
        ),
        "gross_pnl_minor_units": _as_int(source.get("gross_pnl_minor_units")),
        "net_pnl_minor_units": _as_int(source.get("net_pnl_minor_units")),
        "commission_minor_units": _as_int(source.get("commission_minor_units")),
        "spread_slippage_minor_units": _as_int(
            source.get("spread_slippage_minor_units")
        ),
        "fx_drag_minor_units": _as_int(source.get("fx_drag_minor_units")),
        "tax_drag_minor_units": _as_int(source.get("tax_drag_minor_units")),
        "benchmark_excess_lcb_bps": _as_int(
            source.get("benchmark_excess_lcb_bps")
        ),
        "conservative_cost_stress_lcb_bps": _as_int(
            source.get("conservative_cost_stress_lcb_bps")
        ),
        "paper_shadow_divergence_bps": _as_int(
            source.get("paper_shadow_divergence_bps")
        ),
        "max_paper_shadow_divergence_bps": _as_int(
            source.get("max_paper_shadow_divergence_bps")
        ),
        "psr_bps": _as_int(source.get("psr_bps")),
        "min_psr_bps": _as_int(source.get("min_psr_bps")),
        "dsr_bps": _as_int(source.get("dsr_bps")),
        "min_dsr_bps": _as_int(source.get("min_dsr_bps")),
        "concentration_label_passed": _as_bool(
            source.get("concentration_label_passed")
        ),
        "regime_label_passed": _as_bool(source.get("regime_label_passed")),
        "breadth_label_passed": _as_bool(source.get("breadth_label_passed")),
        "freshness_label_passed": _as_bool(source.get("freshness_label_passed")),
        "survivorship_label_passed": _as_bool(
            source.get("survivorship_label_passed")
        ),
        "execution_realism_label_passed": _as_bool(
            source.get("execution_realism_label_passed")
        ),
        "qc_review_hash_present": _as_bool(source.get("qc_review_hash_present")),
        "mit_review_hash_present": _as_bool(source.get("mit_review_hash_present")),
        "qa_review_hash_present": _as_bool(source.get("qa_review_hash_present")),
        "qc_review_passed": _as_bool(source.get("qc_review_passed")),
        "mit_review_passed": _as_bool(source.get("mit_review_passed")),
        "qa_review_passed": _as_bool(source.get("qa_review_passed")),
        "scorecard_is_derived_only": _as_bool(
            source.get("scorecard_is_derived_only")
        ),
        "paper_and_shadow_fills_separate": _as_bool(
            source.get("paper_and_shadow_fills_separate")
        ),
        "live_fill_claimed": _as_bool(source.get("live_fill_claimed")),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "sealed": _as_bool(source.get("sealed")),
    }


def _scorecard_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    scorecard: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_bool(source.get("live_or_tiny_live_authorized")):
        violations.append("live_or_tiny_live_authorized")
    for key in (
        "phase3_started",
        "scorecard_writer_started",
        "db_apply_performed",
        "evidence_clock_started",
        "paper_shadow_window_complete",
    ):
        if _as_bool(source.get(key)):
            violations.append(key)
    if reason is not None:
        return violations
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper_shadow") != "paper_shadow":
        violations.append("environment_mismatch")
    if (
        _as_str(scorecard.get("expected_contract_id"), "")
        != _SCORECARD_VERDICT_CONTRACT_ID
    ):
        violations.append("scorecard_expected_contract_id_mismatch")
    if _as_bool(scorecard.get("accepted")):
        violations.append("scorecard_accepted_before_writer")
    for key in (
        "scorecard_input_bundle_hash_present",
        "evidence_clock_manifest_hash_present",
        "dq_manifest_hash_present",
        "formula_appendix_hash_present",
        "statistical_preregistration_hash_present",
        "benchmark_version_hash_present",
        "cost_model_version_hash_present",
        "strategy_hypothesis_hash_present",
        "reference_data_sources_hash_present",
        "scorecard_manifest_hash_present",
        "verdict_rationale_hash_present",
        "concentration_label_passed",
        "regime_label_passed",
        "breadth_label_passed",
        "freshness_label_passed",
        "survivorship_label_passed",
        "execution_realism_label_passed",
        "qc_review_hash_present",
        "mit_review_hash_present",
        "qa_review_hash_present",
        "qc_review_passed",
        "mit_review_passed",
        "qa_review_passed",
        "scorecard_is_derived_only",
        "paper_and_shadow_fills_separate",
        "live_fill_claimed",
        "bybit_live_execution_unchanged",
        "sealed",
    ):
        if _as_bool(scorecard.get(key)):
            violations.append(f"scorecard_{key}")
    for key in (
        "paper_shadow_window_trading_days",
        "min_window_trading_days",
        "independent_observation_count",
        "min_independent_observation_count",
        "gross_pnl_minor_units",
        "net_pnl_minor_units",
        "commission_minor_units",
        "spread_slippage_minor_units",
        "fx_drag_minor_units",
        "tax_drag_minor_units",
        "benchmark_excess_lcb_bps",
        "conservative_cost_stress_lcb_bps",
        "paper_shadow_divergence_bps",
        "max_paper_shadow_divergence_bps",
        "psr_bps",
        "min_psr_bps",
        "dsr_bps",
        "min_dsr_bps",
    ):
        if _as_int(scorecard.get(key)) != 0:
            violations.append(f"scorecard_{key}_present")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_scorecard_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    scorecard = _normalize_scorecard_verdict(source.get("scorecard"), reason)

    contract_violations = _scorecard_status_contract_violations(
        source,
        phase2,
        scorecard,
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
        "environment": "paper_shadow",
        "gui_authority": "display_only",
        "scorecard_status_state": status_state,
        "phase": _as_str(
            source.get("phase"),
            "phase3_scorecard_status_source_fixture",
        ),
        "phase3_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "scorecard": scorecard,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_scorecard_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "paper_shadow_window_complete": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "live_or_tiny_live_authorized": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
