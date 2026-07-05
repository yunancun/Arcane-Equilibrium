#!/usr/bin/env python3
"""Build a source-only current-candidate no-order refresh envelope.

This packet binds the current Cost Gate false-negative candidate to GUI-backed
Rust RiskConfig cap resolution before any future public quote/current
construction refresh. It does not capture quotes, query PG, call Bybit, mutate
runtime state, admit orders, lower gates, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


SCHEMA_VERSION = "cost_gate_current_candidate_no_order_refresh_envelope_v1"
READY_STATUS = (
    "CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY"
)
FALSE_NEGATIVE_REVIEW_INPUT_NOT_READY_STATUS = (
    "FALSE_NEGATIVE_REVIEW_INPUT_NOT_READY"
)
FALSE_NEGATIVE_PREFLIGHT_INPUT_NOT_READY_STATUS = (
    "FALSE_NEGATIVE_PREFLIGHT_INPUT_NOT_READY"
)
BOUNDED_AUTH_INPUT_NOT_NO_AUTHORITY_STATUS = (
    "BOUNDED_AUTH_INPUT_NOT_NO_AUTHORITY"
)
GUI_RISK_CAP_INPUT_REQUIRED_STATUS = "GUI_RISK_CAP_INPUT_REQUIRED_NO_AUTHORITY"
CANDIDATE_MISMATCH_STATUS = "CANDIDATE_MISSING_OR_MISMATCH"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION = (
    "cost_gate_false_negative_operator_review_v1"
)
FALSE_NEGATIVE_PREFLIGHT_SCHEMA_VERSION = (
    "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
)
BOUNDED_AUTH_PACKET_SCHEMA_VERSION = (
    "bounded_demo_probe_operator_authorization_packet_v1"
)
DEMO_ACCOUNT_EQUITY_ARTIFACT_SCHEMA_VERSION = "demo_account_equity_artifact_v1"
DEMO_ACCOUNT_EQUITY_ARTIFACT_READY_STATUS = (
    "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY"
)
DEMO_BALANCE_FAST_ENDPOINTS = {
    "/api/v1/strategy/demo/balance?fast=1",
    "/api/v1/strategy/demo/balance?fast=true",
}

DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 24 * 60 * 60
DEFAULT_EQUITY_ARTIFACT_MAX_AGE_SECONDS = 15 * 60
RECOMMENDED_BASE_URL = "https://api.bybit.com"
ALLOWED_BASE_URLS = ["https://api.bybit.com", "https://api-demo.bybit.com"]
TIME_PATH = "/v5/market/time"
TICKERS_PATH = "/v5/market/tickers"
INSTRUMENTS_PATH = "/v5/market/instruments-info"
USER_AGENT = "openclaw-current-candidate-public-refresh/1.0"
DEFAULT_TIMEOUT_SECONDS = 2.0
CANONICAL_MAX_FRESH_BBO_AGE_MS = 1000
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,40}$")
IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

BOUNDARY = (
    "artifact-only current-candidate no-order refresh envelope; no quote "
    "capture, network call, PG query/write, Bybit call, private/auth/order "
    "endpoint, order, config, risk, cap, auth, runtime mutation, Cost Gate "
    "lowering, freshness gate lowering, probe authority, order authority, "
    "live authority, order admission, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "auth_headers_present",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "canonical_plan_mutation_performed",
    "config_mutation_performed",
    "cookie_headers_present",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "network_call_performed",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_write_performed",
    "placement_call_performed",
    "plan_mutation_performed",
    "private_endpoint_called",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "public_quote_capture_allowed_by_this_packet",
    "public_quote_capture_allowed_by_this_policy",
    "public_quote_capture_performed",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "enabled",
            "grant",
            "granted",
            "authorize",
            "authorized",
            "ready",
        }
    return False


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _round_decimal(value: Decimal | None, places: int = 8) -> float | None:
    if value is None:
        return None
    quant = Decimal("1").scaleb(-places)
    return float(value.quantize(quant))


def _parse_utc_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _generated_at(payload: dict[str, Any]) -> Any:
    return (
        payload.get("generated_at_utc")
        or payload.get("generated")
        or payload.get("ts_utc")
    )


def _sha256_path(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
    required: bool = True,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = _generated_at(payload or {}) if present else None
    parsed = _parse_utc_timestamp(generated_at) if generated_at else None
    age_seconds: float | None = None
    if parsed is not None:
        age_seconds = (now_utc - parsed).total_seconds()
    if not present:
        status = "MISSING" if required else "NOT_SUPPLIED"
    elif parsed is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age_seconds is not None and age_seconds < -60:
        status = "FROM_FUTURE"
    elif age_seconds is not None and age_seconds > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": _sha256_path(path),
        "status": status,
        "present": present,
        "required": required,
        "generated_at_utc": generated_at,
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
        "payload_status": (payload or {}).get("status") if present else None,
    }


def _authority_preserved(*payloads: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stack: list[Any] = list(payloads)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        adjustment = data.get("main_cost_gate_adjustment")
        if adjustment not in (None, "", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
        for key in AUTHORITY_TRUE_KEYS:
            if _truthy(data.get(key)):
                reasons.append(f"{key}_true")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _candidate_from_review(packet: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(packet)
    candidate = _dict(payload.get("candidate"))
    symbols = _list(candidate.get("symbols"))
    sides = _list(candidate.get("sides"))
    strategies = _list(candidate.get("strategy_names"))
    direct_symbol = candidate.get("symbol")
    direct_side = candidate.get("side")
    direct_strategy = candidate.get("strategy_name")
    return {
        "side_cell_key": candidate.get("side_cell_key")
        or payload.get("selected_side_cell_key"),
        "strategy_name": direct_strategy or (strategies[0] if strategies else None),
        "symbol": direct_symbol or (symbols[0] if symbols else None),
        "side": direct_side or (sides[0] if sides else None),
        "outcome_horizon_minutes": (
            candidate.get("outcome_horizon_minutes")
            or candidate.get("dominant_horizon_minutes")
            or (_list(candidate.get("horizon_minutes")) or [None])[0]
        ),
    }


def _candidate_from_preflight(packet: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(packet)
    design = _dict(payload.get("bounded_demo_probe_design"))
    candidate = _dict(payload.get("candidate")) or _dict(design.get("candidate"))
    return {
        "side_cell_key": candidate.get("side_cell_key") or payload.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": (
            candidate.get("outcome_horizon_minutes")
            or payload.get("outcome_horizon_minutes")
        ),
    }


def _candidate_from_bounded_auth(packet: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(packet)
    candidate = _dict(payload.get("candidate"))
    if candidate:
        return {key: candidate.get(key) for key in IDENTITY_FIELDS}
    preflight = _dict(payload.get("preflight"))
    preflight_candidate = _dict(preflight.get("candidate"))
    if preflight_candidate:
        return {key: preflight_candidate.get(key) for key in IDENTITY_FIELDS}
    operator_authorization = _dict(payload.get("operator_authorization"))
    auth_candidate = _dict(operator_authorization.get("candidate"))
    return {key: auth_candidate.get(key) for key in IDENTITY_FIELDS}


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(candidate.get(key) for key in IDENTITY_FIELDS)


def _candidate_match(candidates: list[dict[str, Any]]) -> bool:
    non_empty = [candidate for candidate in candidates if candidate.get("side_cell_key")]
    if len(non_empty) < 2:
        return False
    first = _candidate_key(non_empty[0])
    return all(_candidate_key(candidate) == first for candidate in non_empty[1:])


def _normalized_horizon(value: Any) -> int | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not parsed.is_integer():
        return None
    return int(parsed)


def _candidate_identity_reasons(candidate: dict[str, Any]) -> list[str]:
    side_cell_key = _str(candidate.get("side_cell_key"))
    strategy = _str(candidate.get("strategy_name"))
    raw_symbol = _str(candidate.get("symbol"))
    symbol = raw_symbol.upper()
    side = _str(candidate.get("side"))
    horizon = _normalized_horizon(candidate.get("outcome_horizon_minutes"))
    reasons: list[str] = []
    if not side_cell_key or not strategy or not raw_symbol or not side or horizon is None:
        reasons.append("candidate_identity_incomplete")
    if raw_symbol and raw_symbol != symbol:
        reasons.append("candidate_symbol_not_uppercase")
    if symbol and SYMBOL_RE.fullmatch(symbol) is None:
        reasons.append("candidate_symbol_not_safe")
    if side and side not in {"Buy", "Sell"}:
        reasons.append("candidate_side_not_buy_sell")
    if horizon is not None and horizon <= 0:
        reasons.append("candidate_horizon_not_positive")
    if side_cell_key and strategy and symbol and side:
        if side_cell_key != f"{strategy}|{symbol}|{side}":
            reasons.append("candidate_side_cell_key_mismatch")
    return sorted(set(reasons))


def _bounded_auth_no_authority(
    packet: dict[str, Any] | None,
    artifact: dict[str, Any],
) -> tuple[bool, list[str]]:
    payload = _dict(packet)
    if not payload and artifact.get("required") is not True:
        return True, []
    reasons: list[str] = []
    if artifact.get("status") != "FRESH":
        reasons.append("bounded_auth_artifact_not_fresh")
    if payload.get("schema_version") != BOUNDED_AUTH_PACKET_SCHEMA_VERSION:
        reasons.append("bounded_auth_schema_version_invalid")
    if payload.get("operator_authorization") not in (None, {}):
        reasons.append("bounded_auth_operator_authorization_object_present")
    answers = _dict(payload.get("answers"))
    for key in (
        "bounded_demo_probe_authorized",
        "operator_authorization_object_emitted",
        "active_runtime_probe_authority",
        "active_runtime_order_authority",
        "probe_authority_granted",
        "order_authority_granted",
        "live_authority_granted",
    ):
        if _truthy(answers.get(key)) or _truthy(payload.get(key)):
            reasons.append(f"{key}_true")
    decision = _str(payload.get("decision")).lower()
    if decision and decision not in {"defer", "reject"}:
        reasons.append("bounded_auth_decision_not_defer_or_reject")
    return not reasons, sorted(set(reasons))


def _equity_payload_data(artifact: dict[str, Any]) -> dict[str, Any]:
    payload = (
        _dict(artifact.get("payload"))
        or _dict(artifact.get("balance_payload"))
        or _dict(artifact.get("source_payload"))
    )
    if not payload:
        return {}
    return _dict(payload.get("data")) or payload


def _extract_equity_usdt(data: dict[str, Any]) -> Decimal | None:
    for key in (
        "totalEquity",
        "total_equity",
        "equity",
        "balance",
        "totalWalletBalance",
        "total_wallet_balance",
        "walletBalance",
        "wallet_balance",
    ):
        equity = _dec(data.get(key))
        if equity is not None:
            return equity
    return None


def _resolve_account_equity_from_artifact(
    *,
    account_equity_artifact: dict[str, Any] | None,
    account_equity_usdt: Any,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> tuple[Decimal | None, dict[str, Any]]:
    artifact = _dict(account_equity_artifact)
    data = _equity_payload_data(artifact)
    reasons: list[str] = []
    authority_ok, authority_reasons = _authority_preserved(artifact)
    if not artifact:
        reasons.append("account_equity_artifact_required")
    if (
        artifact
        and artifact.get("schema_version")
        != DEMO_ACCOUNT_EQUITY_ARTIFACT_SCHEMA_VERSION
    ):
        reasons.append("account_equity_artifact_schema_version_invalid")
    artifact_status = _str(artifact.get("status"))
    if artifact and artifact_status != DEMO_ACCOUNT_EQUITY_ARTIFACT_READY_STATUS:
        reasons.append("account_equity_artifact_status_not_ready")
    environment = _str(artifact.get("environment")).lower()
    if artifact and environment != "demo":
        reasons.append("account_equity_artifact_environment_not_demo")
    source_endpoint = _str(artifact.get("source_endpoint"))
    if artifact and source_endpoint not in DEMO_BALANCE_FAST_ENDPOINTS:
        reasons.append("account_equity_source_endpoint_not_demo_fast_balance")
    if artifact and _str(data.get("read_model")) != "rust_snapshot_fast":
        reasons.append("account_equity_read_model_not_rust_snapshot_fast")
    if artifact and _str(data.get("pipeline_status")) != "connected":
        reasons.append("account_equity_pipeline_status_not_connected")
    if not authority_ok:
        reasons.extend(authority_reasons)

    generated_at = _parse_utc_timestamp(artifact.get("generated_at_utc"))
    age_seconds: float | None = None
    if artifact and generated_at is None:
        reasons.append("account_equity_artifact_generated_at_utc_missing_or_invalid")
    elif generated_at is not None:
        age_seconds = (now_utc - generated_at).total_seconds()
        if age_seconds < -60:
            reasons.append("account_equity_artifact_from_future")
        elif age_seconds > max_age_seconds:
            reasons.append("account_equity_artifact_stale")

    equity = _extract_equity_usdt(data)
    if equity is None or equity <= 0:
        reasons.append("account_equity_artifact_equity_missing_or_non_positive")

    manual_equity = _dec(account_equity_usdt)
    if manual_equity is not None and equity is not None and manual_equity != equity:
        reasons.append("account_equity_usdt_mismatch_artifact")

    accepted = bool(artifact) and not reasons
    return (equity if accepted else None), {
        "schema_version": artifact.get("schema_version"),
        "status": artifact_status or None,
        "accepted": bool(accepted),
        "blocking_reasons": sorted(set(reasons)),
        "environment": environment or None,
        "source_endpoint": source_endpoint or None,
        "read_model": data.get("read_model"),
        "pipeline_status": data.get("pipeline_status"),
        "generated_at_utc": generated_at.isoformat() if generated_at else None,
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "max_age_seconds": max_age_seconds,
        "equity_usdt": _round_decimal(equity, 8),
        "manual_account_equity_usdt": _round_decimal(manual_equity, 8),
        "authority_preserved": authority_ok,
        "authority_contamination_reasons": authority_reasons,
        "source_contract": (
            "demo_account_equity_artifact_v1 wrapping "
            "/api/v1/strategy/demo/balance?fast=1 rust_snapshot_fast output"
        ),
    }


def _risk_limits(gui_risk_config: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(gui_risk_config)
    config = _dict(payload.get("config")) or payload
    if _dict(config.get("limits")):
        return _dict(config.get("limits"))
    global_config = _dict(config.get("global_config")) or _dict(config.get("p1"))
    if not global_config:
        return {}
    p1_pct = _dec(global_config.get("p1_risk_pct"))
    return {
        "per_trade_risk_pct": (p1_pct / Decimal("100")) if p1_pct is not None else None,
        "position_size_max_pct": global_config.get("max_single_position_pct"),
        "total_exposure_max_pct": global_config.get("max_total_exposure_pct"),
        "correlated_exposure_max_pct": global_config.get(
            "max_correlated_exposure_pct"
        ),
        "max_order_notional_usdt": global_config.get("max_order_notional_usdt"),
    }


def _derive_gui_risk_cap(
    *,
    gui_risk_config: dict[str, Any] | None,
    account_equity_usdt: Decimal | None,
    equity_resolution: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    limits = _risk_limits(gui_risk_config)
    equity = account_equity_usdt
    per_trade_fraction = _dec(limits.get("per_trade_risk_pct"))
    max_single_position_pct = _dec(limits.get("position_size_max_pct"))
    max_order_notional = _dec(limits.get("max_order_notional_usdt"))
    reasons: list[str] = []
    if not limits:
        reasons.append("gui_risk_config_limits_missing")
    if not equity_resolution.get("accepted"):
        reasons.extend(_list(equity_resolution.get("blocking_reasons")))
    if equity is None or equity <= 0:
        reasons.append("account_equity_usdt_missing_or_non_positive")
    if per_trade_fraction is None or per_trade_fraction <= 0:
        reasons.append("per_trade_risk_pct_missing_or_non_positive")
    elif per_trade_fraction > 1:
        reasons.append("per_trade_risk_pct_not_fraction")
    if max_single_position_pct is None or max_single_position_pct <= 0:
        reasons.append("position_size_max_pct_missing_or_non_positive")

    per_trade_budget = (
        equity * per_trade_fraction
        if equity is not None
        and equity > 0
        and per_trade_fraction is not None
        and Decimal("0") < per_trade_fraction <= Decimal("1")
        else None
    )
    single_position_budget = (
        equity * max_single_position_pct / Decimal("100")
        if equity is not None
        and equity > 0
        and max_single_position_pct is not None
        and max_single_position_pct > 0
        else None
    )
    candidates = [
        value
        for value in (per_trade_budget, single_position_budget, max_order_notional)
        if value is not None and value > 0
    ]
    resolved = min(candidates) if not reasons and candidates else None
    if not candidates:
        reasons.append("no_positive_gui_risk_cap_candidate")
    return resolved, {
        "cap_resolved": resolved is not None,
        "blocking_reasons": sorted(set(reasons)),
        "source": "GUI Risk tab -> Rust RiskConfig limits",
        "risk_source_of_truth": "GUI-backed Rust RiskConfig",
        "account_equity_usdt": _round_decimal(equity, 8),
        "account_equity_artifact_accepted": equity_resolution.get("accepted"),
        "account_equity_artifact_blocking_reasons": equity_resolution.get(
            "blocking_reasons"
        ),
        "account_equity_artifact_generated_at_utc": equity_resolution.get(
            "generated_at_utc"
        ),
        "account_equity_artifact_age_seconds": equity_resolution.get("age_seconds"),
        "account_equity_artifact_max_age_seconds": equity_resolution.get(
            "max_age_seconds"
        ),
        "per_trade_risk_pct_fraction": _round_decimal(per_trade_fraction, 8),
        "per_trade_risk_pct_display": _round_decimal(
            per_trade_fraction * Decimal("100")
            if per_trade_fraction is not None
            else None,
            4,
        ),
        "position_size_max_pct": _round_decimal(max_single_position_pct, 4),
        "per_trade_budget_usdt": _round_decimal(per_trade_budget, 8),
        "single_position_budget_usdt": _round_decimal(single_position_budget, 8),
        "max_order_notional_usdt": _round_decimal(max_order_notional, 8),
        "resolved_cap_usdt": _round_decimal(resolved, 8),
        "resolution_rule": (
            "min(account_equity_usdt * per_trade_risk_pct, "
            "account_equity_usdt * position_size_max_pct / 100, "
            "max_order_notional_usdt when enabled)"
        ),
        "gui_percent_semantics": (
            "GUI 10.0% is TOML per_trade_risk_pct=0.1 and must not be "
            "interpreted as a 10 USDT notional cap"
        ),
        "bounded_probe_local_cap_usdt_is_authority": False,
        "gui_risk_config_is_authority": True,
    }


def _request_spec(label: str, path: str, query: dict[str, str]) -> dict[str, Any]:
    return {
        "label": label,
        "method": "GET",
        "base_url_policy": {
            "recommended_base_url": RECOMMENDED_BASE_URL,
            "allowed_base_urls": ALLOWED_BASE_URLS,
        },
        "path": path,
        "query": query,
        "headers_allowlist": ["User-Agent"],
        "required_user_agent": USER_AGENT,
        "auth_or_cookie_headers_allowed": False,
        "private_or_order_paths_allowed": False,
        "redirects_allowed": False,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "capture_permitted_by_this_packet": False,
    }


def _refresh_envelope(
    *,
    candidate: dict[str, Any],
    cap_resolution: dict[str, Any],
) -> dict[str, Any]:
    symbol = _str(candidate.get("symbol")).upper()
    required_requests = [
        _request_spec("server_time", TIME_PATH, {}),
        _request_spec(
            "ticker",
            TICKERS_PATH,
            {"category": "linear", "symbol": symbol},
        ),
        _request_spec(
            "instrument",
            INSTRUMENTS_PATH,
            {"category": "linear", "symbol": symbol},
        ),
    ]
    return {
        "candidate_identity": {
            "required_exact_fields": {key: candidate.get(key) for key in IDENTITY_FIELDS},
            "identity_rule": "future quote, snapshot, construction, order, fill, and outcome artifacts must exact-match this side-cell",
        },
        "resolved_gui_risk_cap": {
            "resolved_cap_usdt": cap_resolution.get("resolved_cap_usdt"),
            "per_trade_budget_usdt": cap_resolution.get("per_trade_budget_usdt"),
            "single_position_budget_usdt": cap_resolution.get(
                "single_position_budget_usdt"
            ),
            "max_order_notional_usdt": cap_resolution.get("max_order_notional_usdt"),
            "per_trade_risk_pct_display": cap_resolution.get(
                "per_trade_risk_pct_display"
            ),
            "per_trade_risk_pct_fraction": cap_resolution.get(
                "per_trade_risk_pct_fraction"
            ),
            "position_size_max_pct": cap_resolution.get("position_size_max_pct"),
            "risk_source_of_truth": cap_resolution.get("risk_source_of_truth"),
            "gui_percent_semantics": cap_resolution.get("gui_percent_semantics"),
            "resolution_rule": cap_resolution.get("resolution_rule"),
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "future_public_quote_refresh_review": {
            "source_helper": (
                "helper_scripts/research/cost_gate_learning_lane/"
                "bbo_freshness_public_quote_capture.py"
            ),
            "runtime_capture_allowed_by_this_packet": False,
            "network_call_performed_by_this_packet": False,
            "requires_separate_pm_e3_bb_review_before_runtime_capture": True,
            "requires_candidate_scoped_runtime_invocation_record": True,
            "requires_no_auth_cookie_or_private_endpoint_evidence": True,
        },
        "request_envelope_review": {
            "method": "GET",
            "required_requests": required_requests,
            "allowed_base_urls": ALLOWED_BASE_URLS,
            "recommended_base_url": RECOMMENDED_BASE_URL,
            "headers_allowlist": ["User-Agent"],
            "auth_or_cookie_headers_allowed": False,
            "private_or_order_paths_allowed": False,
            "redirects_allowed": False,
            "timeout_seconds_default": DEFAULT_TIMEOUT_SECONDS,
            "exact_query_required": True,
            "additional_requests_allowed": False,
        },
        "freshness_and_market_data_gates": {
            "max_fresh_bbo_age_ms": CANONICAL_MAX_FRESH_BBO_AGE_MS,
            "ticker_must_have_exactly_one_row": True,
            "instrument_must_have_exactly_one_row": True,
            "bid_ask_required": True,
            "bid_must_be_less_than_ask": True,
            "bid_ask_size_positive": True,
            "spread_bps_must_be_recorded": True,
            "instrument_status_required": "Trading",
            "instrument_category_required": "linear",
            "instrument_filters_required": ["tick_size", "qty_step", "min_notional"],
            "raw_public_quote_is_not_construction_input": True,
        },
        "handoff_contract": {
            "public_quote_to_snapshot_adapter": {
                "source_helper": (
                    "helper_scripts/research/cost_gate_learning_lane/"
                    "public_quote_market_snapshot_adapter.py"
                ),
                "output_schema_version": "bounded_probe_candidate_market_snapshot_v1",
                "output_source": (
                    "bybit_public_quote_capture:"
                    "bbo_freshness_public_quote_capture_v1"
                ),
                "ready_status": "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER",
                "requires_candidate_exact_match": True,
                "requires_cap_match": True,
                "requires_public_quote_path_sha": True,
                "cap_must_match_resolved_gui_risk_cap_usdt": True,
                "single_position_budget_must_match_gui_position_size_max_pct": True,
            },
            "snapshot_to_construction_preview": {
                "source_helper": (
                    "helper_scripts/research/cost_gate_learning_lane/"
                    "bounded_probe_candidate_construction_preview.py"
                ),
                "expected_schema_version": (
                    "bounded_demo_probe_candidate_construction_preview_v1"
                ),
                "requires_fresh_bbo": True,
                "requires_instrument_trading": True,
                "order_admission_ready_from_this_contract": False,
            },
            "raw_quote_can_feed_order_construction_directly": False,
        },
        "pm_e3_bb_review_checklist": [
            "confirm current candidate exact-match across review, preflight, and bounded auth if supplied",
            "confirm GUI RiskConfig resolves cap from percent and equity, not from local 10 USDT defaults",
            "confirm max-single-position is GUI percent-derived exposure budget, not a fixed USDT input",
            "confirm no auth/cookie/private/order endpoint in request envelope",
            "confirm base URL is allowlisted and method is GET for all requests",
            "confirm redirects are refused and timeout remains bounded",
            "confirm fresh BBO max age remains 1000ms and is not relaxed",
            "confirm adapter handoff is path+sha backed before construction preview",
            "confirm refresh review does not grant order/probe/live authority",
        ],
        "failure_conditions": [
            "candidate_identity_mismatch",
            "gui_risk_cap_unresolved_or_not_gui_backed",
            "gui_max_single_position_budget_missing_or_not_percent_derived",
            "account_equity_artifact_missing_stale_or_not_ready",
            "auth_or_cookie_header_present",
            "private_or_order_endpoint_used",
            "non_get_method_or_query_not_exact",
            "base_url_not_allowlisted",
            "redirect_followed",
            "bbo_stale_or_bid_ask_invalid",
            "instrument_not_trading_or_filters_missing",
            "raw_quote_used_as_construction_input_without_adapter",
            "cost_gate_or_freshness_gate_lowered",
            "runtime_or_plan_or_risk_mutation_attempted",
            "order_admission_claimed_without_separate_authorization_review",
        ],
        "max_safe_next_action": (
            "pm_e3_bb_review_public_quote_current_construction_refresh_runtime_invocation"
        ),
    }


def build_current_candidate_no_order_refresh_envelope(
    *,
    false_negative_review: dict[str, Any] | None,
    false_negative_preflight: dict[str, Any] | None,
    bounded_auth: dict[str, Any] | None = None,
    gui_risk_config: dict[str, Any] | None = None,
    account_equity_artifact: dict[str, Any] | None = None,
    account_equity_usdt: float | None = None,
    false_negative_review_path: Path | None = None,
    false_negative_preflight_path: Path | None = None,
    bounded_auth_path: Path | None = None,
    account_equity_artifact_path: Path | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    max_account_equity_artifact_age_seconds: int = (
        DEFAULT_EQUITY_ARTIFACT_MAX_AGE_SECONDS
    ),
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    review = _dict(false_negative_review)
    preflight = _dict(false_negative_preflight)
    auth = _dict(bounded_auth)
    review_artifact = _artifact_summary(
        name="false_negative_operator_review",
        path=false_negative_review_path,
        payload=review,
        now_utc=now,
        max_age_seconds=max(1, int(max_artifact_age_seconds)),
    )
    preflight_artifact = _artifact_summary(
        name="false_negative_bounded_probe_preflight",
        path=false_negative_preflight_path,
        payload=preflight,
        now_utc=now,
        max_age_seconds=max(1, int(max_artifact_age_seconds)),
    )
    auth_artifact = _artifact_summary(
        name="bounded_probe_operator_authorization",
        path=bounded_auth_path,
        payload=auth,
        now_utc=now,
        max_age_seconds=max(1, int(max_artifact_age_seconds)),
        required=False,
    )
    authority_ok, authority_reasons = _authority_preserved(review, preflight, auth)
    review_candidate = _candidate_from_review(review)
    preflight_candidate = _candidate_from_preflight(preflight)
    auth_candidate = _candidate_from_bounded_auth(auth)
    candidate_inputs = [review_candidate, preflight_candidate]
    if auth_candidate.get("side_cell_key"):
        candidate_inputs.append(auth_candidate)
    candidates_match = _candidate_match(candidate_inputs)
    candidate = review_candidate if candidates_match else {}
    identity_reasons = _candidate_identity_reasons(candidate)
    bounded_auth_ok, bounded_auth_reasons = _bounded_auth_no_authority(
        auth,
        auth_artifact,
    )
    equity_usdt, equity_resolution = _resolve_account_equity_from_artifact(
        account_equity_artifact=account_equity_artifact,
        account_equity_usdt=account_equity_usdt,
        now_utc=now,
        max_age_seconds=max(1, int(max_account_equity_artifact_age_seconds)),
    )
    resolved_cap_usdt, cap_resolution = _derive_gui_risk_cap(
        gui_risk_config=gui_risk_config,
        account_equity_usdt=equity_usdt,
        equity_resolution=equity_resolution,
    )
    review_ready_for_identity = (
        review_artifact.get("status") == "FRESH"
        and review.get("schema_version")
        == FALSE_NEGATIVE_OPERATOR_REVIEW_SCHEMA_VERSION
        and bool(review_candidate.get("side_cell_key"))
    )
    preflight_ready_for_identity = (
        preflight_artifact.get("status") == "FRESH"
        and preflight.get("schema_version") == FALSE_NEGATIVE_PREFLIGHT_SCHEMA_VERSION
        and bool(preflight_candidate.get("side_cell_key"))
    )

    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not review_ready_for_identity:
        status = FALSE_NEGATIVE_REVIEW_INPUT_NOT_READY_STATUS
        reason = "false_negative_review_missing_stale_schema_invalid_or_no_candidate"
    elif not preflight_ready_for_identity:
        status = FALSE_NEGATIVE_PREFLIGHT_INPUT_NOT_READY_STATUS
        reason = "false_negative_preflight_missing_stale_schema_invalid_or_no_candidate"
    elif not bounded_auth_ok:
        status = BOUNDED_AUTH_INPUT_NOT_NO_AUTHORITY_STATUS
        reason = "bounded_auth_input_is_not_no_authority_or_not_fresh"
    elif not candidates_match or identity_reasons:
        status = CANDIDATE_MISMATCH_STATUS
        reason = "candidate_missing_or_mismatch_across_current_inputs"
    elif resolved_cap_usdt is None:
        status = GUI_RISK_CAP_INPUT_REQUIRED_STATUS
        reason = "gui_risk_config_and_accepted_account_equity_artifact_required"
    else:
        status = READY_STATUS
        reason = "current_candidate_no_order_refresh_envelope_ready"

    envelope = (
        _refresh_envelope(candidate=candidate, cap_resolution=cap_resolution)
        if status == READY_STATUS
        else {}
    )
    candidate_identity_ready = (
        review_ready_for_identity
        and preflight_ready_for_identity
        and bounded_auth_ok
        and candidates_match
        and not identity_reasons
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_inputs": {
            "false_negative_review": review_artifact,
            "false_negative_preflight": preflight_artifact,
            "bounded_auth": auth_artifact,
            "account_equity_artifact_path": (
                str(account_equity_artifact_path)
                if account_equity_artifact_path
                else None
            ),
            "account_equity_artifact_sha256": _sha256_path(
                account_equity_artifact_path
            ),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "bounded_auth_no_authority": bounded_auth_ok,
            "bounded_auth_no_authority_reasons": bounded_auth_reasons,
            "candidate_match": candidates_match,
            "candidate_identity_reasons": identity_reasons,
            "gui_risk_config_source": cap_resolution.get("source"),
            "gui_risk_cap_resolved": cap_resolution.get("cap_resolved"),
            "gui_risk_cap_blocking_reasons": cap_resolution.get("blocking_reasons"),
        },
        "candidate_inputs": {
            "false_negative_review": review_candidate,
            "false_negative_preflight": preflight_candidate,
            "bounded_auth": auth_candidate,
        },
        "candidate": candidate if candidate_identity_ready else {},
        "cap_resolution": cap_resolution,
        "account_equity_resolution": equity_resolution,
        "refresh_envelope": envelope,
        "summary": {
            "current_candidate_no_order_refresh_envelope_ready": status == READY_STATUS,
            "candidate_side_cell_key": candidate.get("side_cell_key") if candidate else None,
            "risk_source_of_truth": cap_resolution.get("risk_source_of_truth"),
            "resolved_cap_usdt": cap_resolution.get("resolved_cap_usdt"),
            "gui_p1_risk_trade_pct": cap_resolution.get("per_trade_risk_pct_display"),
            "local_10_usdt_cap_is_global_risk_authority": False,
            "runtime_capture_allowed_by_this_packet": False,
            "network_call_performed": False,
            "public_quote_capture_performed": False,
            "order_admission_ready": False,
            "p0_authorization_required_before_order": True,
            "pm_e3_bb_review_required_before_capture": status == READY_STATUS,
            "request_count": (
                len(
                    _list(
                        _dict(envelope.get("request_envelope_review")).get(
                            "required_requests"
                        )
                    )
                )
                if status == READY_STATUS
                else 0
            ),
            "max_fresh_bbo_age_ms": (
                _dict(envelope.get("freshness_and_market_data_gates")).get(
                    "max_fresh_bbo_age_ms"
                )
                if status == READY_STATUS
                else None
            ),
            "max_safe_next_action": (
                envelope.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_current_no_authority_inputs_or_equity_artifact"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "current_candidate_no_order_refresh_envelope_ready": status == READY_STATUS,
            "runtime_capture_allowed_by_this_packet": False,
            "public_quote_capture_performed": False,
            "network_call_performed": False,
            "bybit_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "bybit_private_call_performed": False,
            "auth_headers_present": False,
            "cookie_headers_present": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "freshness_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "cap_mutation_performed": False,
            "risk_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "order_admission_ready": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    cap = _dict(packet.get("cap_resolution"))
    envelope = _dict(packet.get("refresh_envelope"))
    lines = [
        "# Current Candidate No-Order Refresh Envelope",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## GUI Cap Resolution", ""])
    for key in (
        "risk_source_of_truth",
        "account_equity_usdt",
        "per_trade_risk_pct_fraction",
        "per_trade_risk_pct_display",
        "position_size_max_pct",
        "per_trade_budget_usdt",
        "single_position_budget_usdt",
        "max_order_notional_usdt",
        "resolved_cap_usdt",
        "gui_percent_semantics",
    ):
        lines.append(f"- `{key}`: `{cap.get(key)}`")
    lines.extend(["", "## Request Envelope Review", ""])
    request_review = _dict(envelope.get("request_envelope_review"))
    if request_review:
        lines.append("```json")
        lines.append(json.dumps(request_review, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
    lines.extend(["", "## E3/BB Review Checklist", ""])
    for item in _list(envelope.get("pm_e3_bb_review_checklist")):
        lines.append(f"- {item}")
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in _dict(packet.get("answers")).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _read_toml(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - Python < 3.11 fallback path
        raise RuntimeError(
            "reading GUI risk TOML requires Python 3.11+ tomllib; use the project "
            "venv ./venvs/mac_dev/bin/python"
        ) from exc
    with path.open("rb") as fh:
        payload = tomllib.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a TOML table")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--false-negative-review-json", type=Path, required=True)
    parser.add_argument("--false-negative-preflight-json", type=Path, required=True)
    parser.add_argument("--bounded-auth-json", type=Path)
    parser.add_argument("--gui-risk-config-toml", type=Path, required=True)
    parser.add_argument("--account-equity-artifact-json", type=Path, required=True)
    parser.add_argument("--account-equity-usdt", type=float)
    parser.add_argument(
        "--max-artifact-age-seconds",
        type=int,
        default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-account-equity-artifact-age-seconds",
        type=int,
        default=DEFAULT_EQUITY_ARTIFACT_MAX_AGE_SECONDS,
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_current_candidate_no_order_refresh_envelope(
        false_negative_review=_read_json(args.false_negative_review_json),
        false_negative_preflight=_read_json(args.false_negative_preflight_json),
        bounded_auth=_read_json(args.bounded_auth_json),
        gui_risk_config=_read_toml(args.gui_risk_config_toml),
        account_equity_artifact=_read_json(args.account_equity_artifact_json),
        account_equity_usdt=args.account_equity_usdt,
        false_negative_review_path=args.false_negative_review_json,
        false_negative_preflight_path=args.false_negative_preflight_json,
        bounded_auth_path=args.bounded_auth_json,
        account_equity_artifact_path=args.account_equity_artifact_json,
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        max_account_equity_artifact_age_seconds=(
            args.max_account_equity_artifact_age_seconds
        ),
    )
    markdown = render_markdown(packet)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
