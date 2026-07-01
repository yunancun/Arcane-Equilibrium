from __future__ import annotations

"""Evidence-clock status normalizers for the Stock/ETF display-only surface."""

from typing import Any

from .stock_etf_status_common import (
    _COLLECTOR_RUN_CONTRACT_ID,
    _DENIED_OPERATIONS,
    _DQ_MANIFEST_CONTRACT_ID,
    _EVIDENCE_CLOCK_CONTRACT_ID,
    _MARKET_DATA_PROVENANCE_CONTRACT_ID,
    _SAFETY_FALSE_FIELDS,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _collector_run_fail_closed,
    _dq_manifest_fail_closed,
    _evidence_clock_fail_closed,
    _frozen_inputs_fail_closed,
    _market_data_provenance_fail_closed,
    _normalize_api_allowlist,
    _phase2_fail_closed,
    _scorecard_fail_closed,
)

def _normalize_market_data_provenance(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _market_data_provenance_fail_closed(reason or "missing_market_data_provenance")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _MARKET_DATA_PROVENANCE_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(source.get("connector_runtime_started")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
    }


def _normalize_evidence_clock(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _evidence_clock_fail_closed(reason or "missing_evidence_clock")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _EVIDENCE_CLOCK_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "status": _as_str(source.get("status"), "NOT_STARTED"),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "checker_contacted_ibkr": _as_bool(source.get("checker_contacted_ibkr")),
        "checker_started_connector_runtime": _as_bool(
            source.get("checker_started_connector_runtime")
        ),
        "checker_started_evidence_clock": _as_bool(
            source.get("checker_started_evidence_clock")
        ),
        "checker_wrote_scorecard": _as_bool(source.get("checker_wrote_scorecard")),
        "checker_applied_db": _as_bool(source.get("checker_applied_db")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
        "ibkr_readonly_paper_connector_green_5d": _as_bool(
            source.get("ibkr_readonly_paper_connector_green_5d")
        ),
        "shadow_collector_green_5d": _as_bool(source.get("shadow_collector_green_5d")),
    }


def _normalize_collector_run(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _collector_run_fail_closed(reason or "missing_collector_run")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _COLLECTOR_RUN_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "collector_run_id": _as_str(source.get("collector_run_id"), ""),
        "trading_day": _as_str(source.get("trading_day"), ""),
        "expected_trading_sessions": _as_int(source.get("expected_trading_sessions")),
        "completed_trading_sessions": _as_int(source.get("completed_trading_sessions")),
        "pit_universe_contract_hash_present": _as_bool(
            source.get("pit_universe_contract_hash_present")
        ),
        "market_data_provenance_contract_hash_present": _as_bool(
            source.get("market_data_provenance_contract_hash_present")
        ),
        "reference_data_sources_contract_hash_present": _as_bool(
            source.get("reference_data_sources_contract_hash_present")
        ),
        "storage_capacity_contract_hash_present": _as_bool(
            source.get("storage_capacity_contract_hash_present")
        ),
        "gap_report_hash_present": _as_bool(source.get("gap_report_hash_present")),
        "dq_manifest_hash_present": _as_bool(source.get("dq_manifest_hash_present")),
        "replay_manifest_hash_present": _as_bool(
            source.get("replay_manifest_hash_present")
        ),
        "source_artifact_hash_present": _as_bool(
            source.get("source_artifact_hash_present")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(source.get("connector_runtime_started")),
        "market_data_ingestion_started": _as_bool(
            source.get("market_data_ingestion_started")
        ),
        "evidence_writer_started": _as_bool(source.get("evidence_writer_started")),
        "scorecard_writer_started": _as_bool(source.get("scorecard_writer_started")),
        "db_apply_performed": _as_bool(source.get("db_apply_performed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
    }


def _normalize_frozen_inputs(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _frozen_inputs_fail_closed(reason or "missing_frozen_inputs")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "universe_hash_present": _as_bool(source.get("universe_hash_present")),
        "benchmark_hash_present": _as_bool(source.get("benchmark_hash_present")),
        "cost_model_hash_present": _as_bool(source.get("cost_model_hash_present")),
        "strategy_hypothesis_hash_present": _as_bool(
            source.get("strategy_hypothesis_hash_present")
        ),
        "reference_data_sources_contract_hash_present": _as_bool(
            source.get("reference_data_sources_contract_hash_present")
        ),
        "paper_shadow_divergence_threshold_hash_present": _as_bool(
            source.get("paper_shadow_divergence_threshold_hash_present")
        ),
        "gui_evidence_view_available": _as_bool(
            source.get("gui_evidence_view_available")
        ),
        "daily_scorecard_regeneration_passed": _as_bool(
            source.get("daily_scorecard_regeneration_passed")
        ),
    }


def _normalize_dq_manifest(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _dq_manifest_fail_closed(reason or "missing_dq_manifest")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _DQ_MANIFEST_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "shape_accepted": _as_bool(source.get("shape_accepted")),
        "shape_blockers": [str(item) for item in _as_list(source.get("shape_blockers"))],
        "passes_day_quality": _as_bool(source.get("passes_day_quality")),
        "collector_run_id": _as_str(source.get("collector_run_id"), ""),
        "trading_day": _as_str(source.get("trading_day"), ""),
        "market_data_provenance_contract_hash_present": _as_bool(
            source.get("market_data_provenance_contract_hash_present")
        ),
        "source_artifact_hash_present": _as_bool(
            source.get("source_artifact_hash_present")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(source.get("connector_runtime_started")),
        "market_data_ingestion_started": _as_bool(
            source.get("market_data_ingestion_started")
        ),
        "dq_writer_started": _as_bool(source.get("dq_writer_started")),
        "evidence_clock_started": _as_bool(source.get("evidence_clock_started")),
        "scorecard_writer_started": _as_bool(source.get("scorecard_writer_started")),
        "db_apply_performed": _as_bool(source.get("db_apply_performed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
        "calendar_aware_coverage_bps": _as_int(source.get("calendar_aware_coverage_bps")),
        "symbol_completeness_bps": _as_int(source.get("symbol_completeness_bps")),
        "latency_dq_passed": _as_bool(source.get("latency_dq_passed")),
        "market_data_provenance_accepted": _as_bool(
            source.get("market_data_provenance_accepted")
        ),
        "scorecard_regeneration_passed": _as_bool(
            source.get("scorecard_regeneration_passed")
        ),
    }


def _normalize_scorecard(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    if not source:
        return _scorecard_fail_closed()
    return {
        "writer_started": _as_bool(source.get("writer_started")),
        "db_apply_performed": _as_bool(source.get("db_apply_performed")),
        "daily_scorecard_regeneration_passed": _as_bool(
            source.get("daily_scorecard_regeneration_passed")
        ),
    }


def _evidence_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    market_data_provenance: dict[str, Any],
    collector_run: dict[str, Any],
    evidence_clock: dict[str, Any],
    frozen_inputs: dict[str, Any],
    dq_manifest: dict[str, Any],
    scorecard: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper") != "paper":
        violations.append("environment_mismatch")
    if _as_bool(source.get("phase3_started")):
        violations.append("phase3_started")
    if _as_str(market_data_provenance.get("expected_contract_id"), "") != (
        _MARKET_DATA_PROVENANCE_CONTRACT_ID
    ):
        violations.append("market_data_expected_contract_id_mismatch")
    if _as_bool(market_data_provenance.get("ibkr_contact_performed")):
        violations.append("market_data_ibkr_contact_performed")
    if _as_bool(market_data_provenance.get("connector_runtime_started")):
        violations.append("market_data_connector_runtime_started")
    if _as_bool(market_data_provenance.get("secret_content_serialized")):
        violations.append("market_data_secret_content_serialized")
    if _as_bool(market_data_provenance.get("live_or_tiny_live_authorized")):
        violations.append("market_data_live_or_tiny_live_authorized")
    if _as_str(collector_run.get("expected_contract_id"), "") != _COLLECTOR_RUN_CONTRACT_ID:
        violations.append("collector_run_expected_contract_id_mismatch")
    if _as_bool(collector_run.get("ibkr_contact_performed")):
        violations.append("collector_run_ibkr_contact_performed")
    if _as_bool(collector_run.get("connector_runtime_started")):
        violations.append("collector_run_connector_runtime_started")
    if _as_bool(collector_run.get("market_data_ingestion_started")):
        violations.append("collector_run_market_data_ingestion_started")
    if _as_bool(collector_run.get("evidence_writer_started")):
        violations.append("collector_run_evidence_writer_started")
    if _as_bool(collector_run.get("scorecard_writer_started")):
        violations.append("collector_run_scorecard_writer_started")
    if _as_bool(collector_run.get("db_apply_performed")):
        violations.append("collector_run_db_apply_performed")
    if _as_bool(collector_run.get("secret_content_serialized")):
        violations.append("collector_run_secret_content_serialized")
    if _as_bool(collector_run.get("live_or_tiny_live_authorized")):
        violations.append("collector_run_live_or_tiny_live_authorized")
    if _as_str(dq_manifest.get("expected_contract_id"), "") != _DQ_MANIFEST_CONTRACT_ID:
        violations.append("dq_manifest_expected_contract_id_mismatch")
    if _as_bool(dq_manifest.get("ibkr_contact_performed")):
        violations.append("dq_manifest_ibkr_contact_performed")
    if _as_bool(dq_manifest.get("connector_runtime_started")):
        violations.append("dq_manifest_connector_runtime_started")
    if _as_bool(dq_manifest.get("market_data_ingestion_started")):
        violations.append("dq_manifest_market_data_ingestion_started")
    if _as_bool(dq_manifest.get("dq_writer_started")):
        violations.append("dq_manifest_writer_started")
    if _as_bool(dq_manifest.get("evidence_clock_started")):
        violations.append("dq_manifest_evidence_clock_started")
    if _as_bool(dq_manifest.get("scorecard_writer_started")):
        violations.append("dq_manifest_scorecard_writer_started")
    if _as_bool(dq_manifest.get("db_apply_performed")):
        violations.append("dq_manifest_db_apply_performed")
    if _as_bool(dq_manifest.get("secret_content_serialized")):
        violations.append("dq_manifest_secret_content_serialized")
    if _as_bool(dq_manifest.get("live_or_tiny_live_authorized")):
        violations.append("dq_manifest_live_or_tiny_live_authorized")
    if _as_str(evidence_clock.get("expected_contract_id"), "") != _EVIDENCE_CLOCK_CONTRACT_ID:
        violations.append("evidence_clock_expected_contract_id_mismatch")
    if _as_bool(evidence_clock.get("checker_contacted_ibkr")):
        violations.append("evidence_clock_contacted_ibkr")
    if _as_bool(evidence_clock.get("checker_started_connector_runtime")):
        violations.append("evidence_clock_started_connector_runtime")
    if _as_bool(evidence_clock.get("checker_started_evidence_clock")):
        violations.append("evidence_clock_started")
    if _as_bool(evidence_clock.get("checker_wrote_scorecard")):
        violations.append("evidence_clock_wrote_scorecard")
    if _as_bool(evidence_clock.get("checker_applied_db")):
        violations.append("evidence_clock_applied_db")
    if _as_bool(evidence_clock.get("secret_content_serialized")):
        violations.append("evidence_clock_secret_content_serialized")
    if _as_bool(evidence_clock.get("live_or_tiny_live_authorized")):
        violations.append("evidence_clock_live_or_tiny_live_authorized")
    if _as_bool(frozen_inputs.get("daily_scorecard_regeneration_passed")):
        violations.append("frozen_inputs_daily_scorecard_regenerated")
    if _as_bool(scorecard.get("writer_started")):
        violations.append("scorecard_writer_started")
    if _as_bool(scorecard.get("db_apply_performed")):
        violations.append("scorecard_db_apply_performed")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_evidence_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    market_data_provenance = _normalize_market_data_provenance(
        source.get("market_data_provenance"),
        reason,
    )
    evidence_clock = _normalize_evidence_clock(source.get("evidence_clock"), reason)
    collector_run = _normalize_collector_run(source.get("collector_run"), reason)
    frozen_inputs = _normalize_frozen_inputs(source.get("frozen_inputs"), reason)
    dq_manifest = _normalize_dq_manifest(source.get("dq_manifest"), reason)
    scorecard = _normalize_scorecard(source.get("scorecard"))

    contract_violations = _evidence_status_contract_violations(
        source,
        phase2,
        market_data_provenance,
        collector_run,
        evidence_clock,
        frozen_inputs,
        dq_manifest,
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
    elif _as_str(source.get("evidence_status_state"), "blocked") == "green":
        status_state = "blocked"

    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "gui_authority": "display_only",
        "evidence_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase3_evidence_status_source_fixture"),
        "phase3_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "market_data_provenance": market_data_provenance,
        "collector_run": collector_run,
        "evidence_clock": evidence_clock,
        "frozen_inputs": frozen_inputs,
        "dq_manifest": dq_manifest,
        "scorecard": scorecard,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_evidence_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "evidence_clock_started": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
