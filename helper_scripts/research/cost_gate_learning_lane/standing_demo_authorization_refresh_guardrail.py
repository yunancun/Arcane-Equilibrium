#!/usr/bin/env python3
"""Refresh an expired standing Demo authorization under loss-control guardrails.

This helper is source-only by default. It consumes an existing
``standing_demo_operator_authorization_v1`` envelope, current bounded-Demo
runtime readiness, fresh Demo equity, and GUI/Rust RiskConfig. It emits a
candidate-scoped refreshed envelope preview only when the refresh does not
increase the existing resolved cap and preserves all no-authority boundaries.

It does not write the runtime standing envelope, mutate env/crontab, acquire a
Decision Lease, call Bybit, submit/cancel/modify orders, lower Cost Gate, or
create profit proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
    STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
)
from cost_gate_learning_lane.standing_demo_authorization import (
    summarize_standing_demo_authorization,
)


SCHEMA_VERSION = "standing_demo_authorization_refresh_guardrail_v1"
READY_STATUS = "STANDING_DEMO_AUTHORIZATION_REFRESH_READY_NO_RUNTIME_MUTATION"
NOT_READY_STATUS = "STANDING_DEMO_AUTHORIZATION_REFRESH_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

READINESS_SCHEMA_VERSION = "bounded_demo_runtime_readiness_v1"
READINESS_READY_STATUS = "BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES"
READINESS_AUTH_OR_PLAN_BLOCKED_STATUS = "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_AUTH_OR_PLAN"
DEMO_ACCOUNT_EQUITY_ARTIFACT_SCHEMA_VERSION = "demo_account_equity_artifact_v1"
DEMO_ACCOUNT_EQUITY_ARTIFACT_READY_STATUS = (
    "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY"
)
DEMO_BALANCE_FAST_ENDPOINTS = {
    "/api/v1/strategy/demo/balance?fast=1",
    "/api/v1/strategy/demo/balance?fast=true",
}

DEFAULT_AUTHORIZATION_TTL_HOURS = 12
DEFAULT_MAX_AUTHORIZATION_TTL_HOURS = 24
# soak-window TTL 上限：72h soak 窗 + 24h margin。demo-only 放寬(Demo 放寬/Live 收緊政策)，
# 僅在 operator 顯式 --soak-window-hours 時生效；不傳此參數則 12/24 默認逐位不變，
# 放寬路徑不觸及任何 live/live_demo 授權面(本 lane 全程 demo envelope)。
SOAK_MAX_AUTHORIZATION_TTL_HOURS = 96
DEFAULT_MAX_ACCOUNT_EQUITY_ARTIFACT_AGE_SECONDS = 15 * 60
HARD_MAX_AUTHORIZED_PROBE_ORDERS = 3


def _default_runtime_envelope_path() -> Path:
    """派生 runtime standing envelope 預期路徑。

    為什麼走 OPENCLAW_DATA_DIR：D3 SSOT 已遷 var/openclaw，硬編碼 /tmp/openclaw
    會使 refresh 鏈默認參數讀/寫舊 /tmp 副本而 engine 讀新 SSOT，造成雙真相分裂
    (RES-7)。鏡像 policy.py:823 既有慣例；同時滿足跨平台不硬編碼機器路徑。
    """
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return (
        data_dir
        / "cost_gate_learning_lane"
        / "standing_demo_operator_authorization.json"
    )


DEFAULT_RUNTIME_ENVELOPE_PATH = _default_runtime_envelope_path()
EXPIRED_STANDING_AUTH_READINESS_BLOCKERS = {
    "standing_authorization:standing_auth_expired",
}

BOUNDARY = (
    "source-only standing Demo authorization refresh guardrail; no runtime file "
    "write, env/crontab mutation, Decision Lease, Guardian/Rust authority grant, "
    "Bybit/private/order call, order/cancel/modify, PG write, Cost Gate lowering, "
    "live/mainnet authority, promotion proof, or profit proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "mainnet_authority_granted",
    "network_call_performed",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "standing_envelope_materialized",
    "writer_enabled",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value)) and value != 0
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


def _parse_dt(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "reading GUI risk TOML requires Python 3.11+ tomllib; use the project "
            "venv ./venvs/mac_dev/bin/python"
        ) from exc
    with path.open("rb") as fh:
        payload = tomllib.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a TOML table")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _authority_violations(payload: Any, *, prefix: str = "") -> list[str]:
    reasons: list[str] = []
    stack: list[tuple[str, Any]] = [(prefix, payload)]
    while stack:
        current_prefix, node = stack.pop()
        if isinstance(node, list):
            for index, item in enumerate(node):
                stack.append((f"{current_prefix}[{index}]", item))
            continue
        if not isinstance(node, dict):
            continue
        adjustment = node.get("main_cost_gate_adjustment")
        if adjustment not in (None, "", "NONE"):
            reasons.append(f"{current_prefix}.main_cost_gate_adjustment_not_none")
        for key, value in node.items():
            child_prefix = f"{current_prefix}.{key}" if current_prefix else key
            if key in AUTHORITY_TRUE_KEYS and _truthy(value):
                reasons.append(f"{child_prefix}_true")
            if key == "order_authority" and value not in (None, "", "NOT_GRANTED"):
                reasons.append(f"{child_prefix}_not_granted")
            if isinstance(value, (dict, list)):
                stack.append((child_prefix, value))
    return sorted(set(reasons))


def _candidate_identity(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(payload.get("candidate"))
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _candidate_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in ("side_cell_key", "strategy_name", "symbol", "side"):
        if _str(left.get(key)) != _str(right.get(key)):
            return False
    left_horizon = left.get("outcome_horizon_minutes")
    right_horizon = right.get("outcome_horizon_minutes")
    return left_horizon in (None, "") or right_horizon in (None, "") or left_horizon == right_horizon


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
        "correlated_exposure_max_pct": global_config.get("max_correlated_exposure_pct"),
        "max_order_notional_usdt": global_config.get("max_order_notional_usdt"),
    }


def _equity_payload_data(artifact: dict[str, Any]) -> dict[str, Any]:
    payload = (
        _dict(artifact.get("payload"))
        or _dict(artifact.get("balance_payload"))
        or _dict(artifact.get("source_payload"))
    )
    if not payload:
        return {}
    data = _dict(payload.get("data"))
    return data or payload


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


def _equity_resolution(
    artifact: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> tuple[Decimal | None, dict[str, Any]]:
    payload = _dict(artifact)
    data = _equity_payload_data(payload)
    reasons: list[str] = []
    authority_reasons = _authority_violations(payload, prefix="account_equity_artifact")
    if not payload:
        reasons.append("account_equity_artifact_required")
    if (
        payload
        and payload.get("schema_version") != DEMO_ACCOUNT_EQUITY_ARTIFACT_SCHEMA_VERSION
    ):
        reasons.append("account_equity_artifact_schema_version_invalid")
    status = _str(payload.get("status"))
    if payload and status != DEMO_ACCOUNT_EQUITY_ARTIFACT_READY_STATUS:
        reasons.append("account_equity_artifact_status_not_ready")
    environment = _str(payload.get("environment")).lower()
    if payload and environment != "demo":
        reasons.append("account_equity_artifact_environment_not_demo")
    endpoint = _str(payload.get("source_endpoint"))
    if payload and endpoint not in DEMO_BALANCE_FAST_ENDPOINTS:
        reasons.append("account_equity_source_endpoint_not_demo_fast_balance")
    if payload and _str(data.get("read_model")) != "rust_snapshot_fast":
        reasons.append("account_equity_read_model_not_rust_snapshot_fast")
    if payload and _str(data.get("pipeline_status")) != "connected":
        reasons.append("account_equity_pipeline_status_not_connected")

    generated_at = _parse_dt(payload.get("generated_at_utc"))
    age_seconds: float | None = None
    if payload and generated_at is None:
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
    reasons.extend(authority_reasons)
    accepted = bool(payload) and not reasons
    return (equity if accepted else None), {
        "accepted": accepted,
        "schema_version": payload.get("schema_version"),
        "status": status or None,
        "environment": environment or None,
        "source_endpoint": endpoint or None,
        "read_model": data.get("read_model"),
        "pipeline_status": data.get("pipeline_status"),
        "generated_at_utc": generated_at.isoformat() if generated_at else None,
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "max_age_seconds": max_age_seconds,
        "equity_usdt": _round_decimal(equity, 8),
        "blocking_reasons": sorted(set(reasons)),
        "authority_contamination_reasons": authority_reasons,
    }


def _derive_current_gui_cap(
    *,
    gui_risk_config: dict[str, Any] | None,
    equity_usdt: Decimal | None,
    equity: dict[str, Any],
) -> tuple[Decimal | None, dict[str, Any]]:
    limits = _risk_limits(gui_risk_config)
    per_trade_fraction = _dec(limits.get("per_trade_risk_pct"))
    position_size_max_pct = _dec(limits.get("position_size_max_pct"))
    max_order_notional = _dec(limits.get("max_order_notional_usdt"))
    reasons: list[str] = []
    if not limits:
        reasons.append("gui_risk_config_limits_missing")
    if not equity.get("accepted"):
        reasons.extend(_list(equity.get("blocking_reasons")))
    if equity_usdt is None or equity_usdt <= 0:
        reasons.append("account_equity_usdt_missing_or_non_positive")
    if per_trade_fraction is None or per_trade_fraction <= 0:
        reasons.append("per_trade_risk_pct_missing_or_non_positive")
    elif per_trade_fraction > 1:
        reasons.append("per_trade_risk_pct_not_fraction")
    if position_size_max_pct is None or position_size_max_pct <= 0:
        reasons.append("position_size_max_pct_missing_or_non_positive")

    per_trade_budget = (
        equity_usdt * per_trade_fraction
        if equity_usdt is not None
        and equity_usdt > 0
        and per_trade_fraction is not None
        and Decimal("0") < per_trade_fraction <= Decimal("1")
        else None
    )
    single_position_budget = (
        equity_usdt * position_size_max_pct / Decimal("100")
        if equity_usdt is not None
        and equity_usdt > 0
        and position_size_max_pct is not None
        and position_size_max_pct > 0
        else None
    )
    candidates = [
        value
        for value in (per_trade_budget, single_position_budget, max_order_notional)
        if value is not None and value > 0
    ]
    current_cap = min(candidates) if not reasons and candidates else None
    if not candidates:
        reasons.append("no_positive_gui_risk_cap_candidate")
    return current_cap, {
        "cap_resolved": current_cap is not None,
        "blocking_reasons": sorted(set(reasons)),
        "risk_source_of_truth": "GUI-backed Rust RiskConfig",
        "account_equity_usdt": _round_decimal(equity_usdt, 8),
        "per_trade_risk_pct_fraction": _round_decimal(per_trade_fraction, 8),
        "per_trade_risk_pct_display": _round_decimal(
            per_trade_fraction * Decimal("100")
            if per_trade_fraction is not None
            else None,
            4,
        ),
        "position_size_max_pct": _round_decimal(position_size_max_pct, 4),
        "per_trade_budget_usdt": _round_decimal(per_trade_budget, 8),
        "single_position_budget_usdt": _round_decimal(single_position_budget, 8),
        "max_order_notional_usdt": _round_decimal(max_order_notional, 8),
        "current_gui_resolved_cap_usdt": _round_decimal(current_cap, 8),
        "gui_percent_semantics": (
            "GUI 10.0% is TOML per_trade_risk_pct=0.1 and must not be "
            "interpreted as a 10 USDT notional cap"
        ),
    }


def _existing_static_reasons(existing: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not existing:
        return ["existing_standing_demo_authorization_required"]
    if existing.get("schema_version") != STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION:
        reasons.append("existing_schema_version_invalid")
    if existing.get("status") != STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS:
        reasons.append("existing_status_not_active")
    if existing.get("demo_only") is not True:
        reasons.append("existing_demo_only_not_true")
    if _str(existing.get("environment")).lower() != "demo":
        reasons.append("existing_environment_not_demo")
    if _str(existing.get("scope")).lower() != "demo_api_only_bounded_probe":
        reasons.append("existing_scope_invalid")
    if existing.get("candidate_scoping_required") is not True:
        reasons.append("existing_candidate_scoping_required_not_true")
    if not _candidate_matches(_candidate_identity(existing), candidate):
        reasons.append("existing_candidate_mismatch")
    if _dec(_dict(existing.get("risk_cap_lineage")).get("resolved_cap_usdt")) is None:
        reasons.append("existing_resolved_cap_missing")
    if _dec(existing.get("max_authorized_probe_orders_per_candidate")) is None:
        reasons.append("existing_max_probe_orders_missing")
    return sorted(set(reasons))


def _readiness_blocking_reasons(readiness: dict[str, Any]) -> list[str]:
    reasons: list[str] = [
        _str(reason)
        for reason in _list(readiness.get("blocking_reasons"))
        if _str(reason)
    ]
    for name, check in _dict(readiness.get("checks")).items():
        for reason in _list(_dict(check).get("blocking_reasons")):
            text = _str(reason)
            if text:
                reasons.append(f"{name}:{text}")
    return sorted(set(reasons))


def _readiness_resolution(
    readiness: dict[str, Any],
    candidate: dict[str, Any],
    *,
    allow_expired_standing_auth_readiness_only: bool,
) -> tuple[list[str], dict[str, Any]]:
    reasons: list[str] = []
    if not readiness:
        return ["runtime_readiness_required"], {
            "accepted": False,
            "status": None,
            "blocking_reasons": [],
            "allow_expired_standing_auth_readiness_only": allow_expired_standing_auth_readiness_only,
            "expired_standing_auth_readiness_exception_applied": False,
        }
    blocking_reasons = _readiness_blocking_reasons(readiness)
    expired_standing_auth_only = (
        readiness.get("status") == READINESS_AUTH_OR_PLAN_BLOCKED_STATUS
        and bool(blocking_reasons)
        and set(blocking_reasons).issubset(EXPIRED_STANDING_AUTH_READINESS_BLOCKERS)
    )
    exception_applied = (
        allow_expired_standing_auth_readiness_only and expired_standing_auth_only
    )
    if readiness.get("schema_version") != READINESS_SCHEMA_VERSION:
        reasons.append("runtime_readiness_schema_version_invalid")
    if readiness.get("status") != READINESS_READY_STATUS and not exception_applied:
        reasons.append("runtime_readiness_status_not_ready")
    if not _candidate_matches(_candidate_identity(readiness), candidate):
        reasons.append("runtime_readiness_candidate_mismatch")
    answers = _dict(readiness.get("answers"))
    if _truthy(answers.get("order_submission_performed")):
        reasons.append("runtime_readiness_order_submission_performed_true")
    return sorted(set(reasons)), {
        "accepted": not reasons,
        "status": readiness.get("status"),
        "blocking_reasons": blocking_reasons,
        "allow_expired_standing_auth_readiness_only": allow_expired_standing_auth_readiness_only,
        "expired_standing_auth_only": expired_standing_auth_only,
        "expired_standing_auth_readiness_exception_applied": exception_applied,
        "other_runtime_readiness_blockers_accepted": False,
    }


def _build_envelope_preview(
    *,
    existing: dict[str, Any],
    candidate: dict[str, Any],
    operator_id: str,
    max_probe_orders: int,
    expires_at_utc: dt.datetime,
    now_utc: dt.datetime,
    risk_cap_lineage: dict[str, Any],
    source_refs: dict[str, Any],
    authorization_ttl_hours: int,
    soak_window_hours: int | None,
) -> dict[str, Any]:
    stamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    side_hash = hashlib.sha256(
        json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    # soak_window_ttl 審計字段：逐簽顯式記錄本次 TTL 與是否走 soak 放寬路徑，
    # 使「demo-only 放寬」在 envelope 內可審計(非默認 12/24 時 operator 必顯式指定)。
    soak_window_ttl = {
        "authorization_ttl_hours": authorization_ttl_hours,
        "soak_window_hours": soak_window_hours,
        "soak_window_ttl_relaxation_applied": soak_window_hours is not None,
        "reason": (
            "demo-only soak-window TTL relaxation explicitly requested by operator"
            if soak_window_hours is not None
            else "default standing-demo TTL; no soak-window relaxation"
        ),
    }
    return {
        "schema_version": STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "status": STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
        "standing_authorization_id": (
            f"standing-demo-refresh-{stamp}-{side_hash}"
        ),
        "operator_id": operator_id or existing.get("operator_id"),
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "demo_only": True,
        "candidate_scoping_required": True,
        "candidate": candidate,
        "max_authorized_probe_orders_per_candidate": max_probe_orders,
        "expires_at_utc": expires_at_utc.isoformat(),
        "soak_window_ttl": soak_window_ttl,
        "risk_cap_lineage": risk_cap_lineage,
        "source_refs": source_refs,
        "answers": {
            "candidate_scoping_required": True,
            "demo_only": True,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "crontab_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }


def build_standing_demo_authorization_refresh_guardrail(
    *,
    existing_authorization: dict[str, Any] | None,
    runtime_readiness: dict[str, Any] | None,
    account_equity_artifact: dict[str, Any] | None,
    gui_risk_config: dict[str, Any] | None,
    existing_authorization_path: Path | None = None,
    runtime_readiness_path: Path | None = None,
    account_equity_artifact_path: Path | None = None,
    gui_risk_config_path: Path | None = None,
    operator_id: str | None = None,
    max_authorized_probe_orders: int | None = None,
    authorization_ttl_hours: int = DEFAULT_AUTHORIZATION_TTL_HOURS,
    max_authorization_ttl_hours: int = DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    soak_window_hours: int | None = None,
    max_account_equity_artifact_age_seconds: int = (
        DEFAULT_MAX_ACCOUNT_EQUITY_ARTIFACT_AGE_SECONDS
    ),
    allow_expired_standing_auth_readiness_only: bool = False,
    runtime_envelope_path: Path = DEFAULT_RUNTIME_ENVELOPE_PATH,
    now_utc: dt.datetime | None = None,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    existing = _dict(existing_authorization)
    readiness = _dict(runtime_readiness)
    candidate = _candidate_identity(existing)
    source_reasons: list[str] = []
    # soak-window TTL 對齊：operator 顯式 --soak-window-hours N(1..96) 時，TTL 放寬到 N，
    # 且 max-TTL 帽同步抬到 SOAK_MAX_AUTHORIZATION_TTL_HOURS。作用域封鎖：未傳此參數時
    # authorization_ttl_hours / max_authorization_ttl_hours 逐位沿用 12/24 默認，放寬不外溢。
    soak_window_applied = soak_window_hours is not None
    if soak_window_applied:
        if soak_window_hours < 1 or soak_window_hours > SOAK_MAX_AUTHORIZATION_TTL_HOURS:
            source_reasons.append("soak_window_hours_out_of_bounds")
        else:
            authorization_ttl_hours = soak_window_hours
            max_authorization_ttl_hours = SOAK_MAX_AUTHORIZATION_TTL_HOURS
    source_reasons.extend(_existing_static_reasons(existing, candidate))
    readiness_reasons, readiness_resolution = _readiness_resolution(
        readiness,
        candidate,
        allow_expired_standing_auth_readiness_only=(
            allow_expired_standing_auth_readiness_only
        ),
    )
    source_reasons.extend(readiness_reasons)

    old_expires_at = _parse_dt(existing.get("expires_at_utc"))
    old_expired = old_expires_at is not None and old_expires_at <= now
    if old_expires_at is None:
        source_reasons.append("existing_expires_at_invalid")

    old_cap = _dec(_dict(existing.get("risk_cap_lineage")).get("resolved_cap_usdt"))
    old_probe_orders = _dec(existing.get("max_authorized_probe_orders_per_candidate"))
    requested_probe_orders = (
        max_authorized_probe_orders
        if max_authorized_probe_orders is not None
        else int(old_probe_orders or 0)
    )
    if requested_probe_orders < 1:
        source_reasons.append("max_authorized_probe_orders_must_be_positive")
    if requested_probe_orders > HARD_MAX_AUTHORIZED_PROBE_ORDERS:
        source_reasons.append("max_authorized_probe_orders_exceeds_hard_cap")
    if old_probe_orders is not None and requested_probe_orders > int(old_probe_orders):
        source_reasons.append("max_authorized_probe_orders_increases_prior_envelope")
    if authorization_ttl_hours < 1 or authorization_ttl_hours > max_authorization_ttl_hours:
        source_reasons.append("authorization_ttl_hours_out_of_bounds")
    # max-TTL 帽守衛：非 soak 時上限=24h(DEFAULT_MAX)，soak 放寬時上限=96h(SOAK_MAX)。
    effective_max_ttl_guardrail = (
        SOAK_MAX_AUTHORIZATION_TTL_HOURS
        if soak_window_applied
        else DEFAULT_MAX_AUTHORIZATION_TTL_HOURS
    )
    if max_authorization_ttl_hours > effective_max_ttl_guardrail:
        source_reasons.append("max_authorization_ttl_hours_exceeds_guardrail")

    equity_usdt, equity = _equity_resolution(
        account_equity_artifact,
        now_utc=now,
        max_age_seconds=max(1, int(max_account_equity_artifact_age_seconds)),
    )
    current_cap, current_cap_resolution = _derive_current_gui_cap(
        gui_risk_config=gui_risk_config,
        equity_usdt=equity_usdt,
        equity=equity,
    )
    source_reasons.extend(_list(equity.get("blocking_reasons")))
    source_reasons.extend(_list(current_cap_resolution.get("blocking_reasons")))
    if old_cap is None or old_cap <= 0:
        source_reasons.append("prior_resolved_cap_missing_or_non_positive")
    effective_cap = (
        min(old_cap, current_cap)
        if old_cap is not None and current_cap is not None
        else None
    )

    authority_reasons: list[str] = []
    authority_reasons.extend(_authority_violations(existing, prefix="existing"))
    authority_reasons.extend(_authority_violations(readiness, prefix="runtime_readiness"))
    authority_reasons.extend(
        _authority_violations(account_equity_artifact, prefix="account_equity_artifact")
    )

    source_refs = {
        "existing_authorization_path": str(existing_authorization_path)
        if existing_authorization_path
        else None,
        "existing_authorization_sha256": _sha256(existing_authorization_path),
        "runtime_readiness_path": str(runtime_readiness_path)
        if runtime_readiness_path
        else None,
        "runtime_readiness_sha256": _sha256(runtime_readiness_path),
        "account_equity_artifact_path": str(account_equity_artifact_path)
        if account_equity_artifact_path
        else None,
        "account_equity_artifact_sha256": _sha256(account_equity_artifact_path),
        "gui_risk_config_path": str(gui_risk_config_path) if gui_risk_config_path else None,
        "gui_risk_config_sha256": _sha256(gui_risk_config_path),
    }
    risk_cap_lineage = {
        "risk_source_of_truth": "GUI-backed Rust RiskConfig",
        "cap_source": (
            "min(current_gui_riskconfig_equity_resolved_cap_usdt, "
            "prior_standing_envelope_resolved_cap_usdt)"
        ),
        "account_equity_usdt": current_cap_resolution.get("account_equity_usdt"),
        "per_trade_risk_pct_fraction": current_cap_resolution.get(
            "per_trade_risk_pct_fraction"
        ),
        "per_trade_risk_pct_display": current_cap_resolution.get(
            "per_trade_risk_pct_display"
        ),
        "position_size_max_pct": current_cap_resolution.get("position_size_max_pct"),
        "single_position_budget_usdt": current_cap_resolution.get(
            "single_position_budget_usdt"
        ),
        "current_gui_resolved_cap_usdt": current_cap_resolution.get(
            "current_gui_resolved_cap_usdt"
        ),
        "prior_standing_resolved_cap_usdt": _round_decimal(old_cap, 8),
        "resolved_cap_usdt": _round_decimal(effective_cap, 8),
        "rounded_notional_usdt": None,
        "cap_not_increased_from_prior_standing": (
            effective_cap is not None and old_cap is not None and effective_cap <= old_cap
        ),
        "order_shape_must_be_rebuilt_after_refresh": True,
        "local_10_usdt_cap_is_global_risk_authority": False,
        "bounded_probe_local_cap_usdt_is_authority": False,
    }
    can_preview = not source_reasons and not authority_reasons and effective_cap is not None
    envelope_preview: dict[str, Any] = {}
    standing_summary: dict[str, Any] = {}
    if can_preview:
        envelope_preview = _build_envelope_preview(
            existing=existing,
            candidate=candidate,
            operator_id=operator_id or _str(existing.get("operator_id")),
            max_probe_orders=requested_probe_orders,
            expires_at_utc=now + dt.timedelta(hours=authorization_ttl_hours),
            now_utc=now,
            risk_cap_lineage=risk_cap_lineage,
            source_refs=source_refs,
            authorization_ttl_hours=authorization_ttl_hours,
            soak_window_hours=soak_window_hours if soak_window_applied else None,
        )
        standing_summary = summarize_standing_demo_authorization(
            envelope_preview,
            {
                "status": "FRESH",
                "schema_version": STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
            },
            now_utc=now,
            max_authorization_ttl_hours=max_authorization_ttl_hours,
            candidate=candidate,
        )
        if standing_summary.get("valid_for_candidate_scoped_authorization") is not True:
            source_reasons.append("refreshed_standing_demo_authorization_invalid")
            envelope_preview = {}
    status = (
        AUTHORITY_BOUNDARY_VIOLATION_STATUS
        if authority_reasons
        else READY_STATUS
        if envelope_preview
        else NOT_READY_STATUS
    )
    blocking_gates = []
    if source_reasons:
        blocking_gates.append("source_inputs_valid")
    if authority_reasons:
        blocking_gates.append("authority_boundary_preserved")
    if not envelope_preview:
        blocking_gates.append("refreshed_envelope_preview_valid")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": ";".join(blocking_gates) or "ready_no_runtime_mutation",
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "runtime_envelope_path": str(runtime_envelope_path),
        "source_refs": source_refs,
        "old_authorization": {
            "standing_authorization_id": existing.get("standing_authorization_id")
            or existing.get("authorization_id"),
            "expires_at_utc": old_expires_at.isoformat() if old_expires_at else None,
            "expired": old_expired,
            "max_authorized_probe_orders_per_candidate": int(old_probe_orders or 0),
            "resolved_cap_usdt": _round_decimal(old_cap, 8),
        },
        "runtime_readiness_resolution": readiness_resolution,
        "equity_resolution": equity,
        "current_gui_cap_resolution": current_cap_resolution,
        "risk_cap_lineage": risk_cap_lineage,
        "envelope_preview": envelope_preview,
        "standing_demo_authorization_validation": standing_summary,
        "blocking_gates": blocking_gates,
        "source_blockers": sorted(set(source_reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "summary": {
            "refresh_ready_no_runtime_mutation": bool(envelope_preview),
            "old_authorization_expired": old_expired,
            "candidate_side_cell_key": candidate.get("side_cell_key"),
            "current_gui_resolved_cap_usdt": current_cap_resolution.get(
                "current_gui_resolved_cap_usdt"
            ),
            "prior_standing_resolved_cap_usdt": _round_decimal(old_cap, 8),
            "refreshed_resolved_cap_usdt": risk_cap_lineage.get("resolved_cap_usdt"),
            "cap_not_increased_from_prior_standing": risk_cap_lineage.get(
                "cap_not_increased_from_prior_standing"
            ),
            "max_authorized_probe_orders_per_candidate": requested_probe_orders,
            "authorization_ttl_hours": authorization_ttl_hours,
            "max_authorization_ttl_hours": max_authorization_ttl_hours,
            "soak_window_hours": soak_window_hours if soak_window_applied else None,
            "soak_window_ttl_relaxation_applied": soak_window_applied,
            "expired_standing_auth_readiness_exception_applied": (
                readiness_resolution.get(
                    "expired_standing_auth_readiness_exception_applied"
                )
            ),
            "standing_envelope_materialized": False,
            "bounded_demo_probe_authorized": False,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "max_safe_next_action": (
                "pm_owned_runtime_materialize_refreshed_standing_envelope"
                if envelope_preview
                else "repair_refresh_guardrail_blockers"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "refresh_ready_no_runtime_mutation": bool(envelope_preview),
            "expired_standing_auth_readiness_exception_applied": (
                readiness_resolution.get(
                    "expired_standing_auth_readiness_exception_applied"
                )
            ),
            "runtime_readiness_other_blockers_accepted": False,
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "crontab_mutation_performed": False,
            "standing_envelope_materialized": False,
            "standing_demo_authorization_valid": bool(envelope_preview),
            "standing_demo_authorization_consumed": False,
            "operator_authorization_object_emitted": False,
            "bounded_demo_probe_authorized": False,
            "decision_lease_emitted": False,
            "guardian_risk_gate_passed_by_this_packet": False,
            "rust_authority_granted_by_this_packet": False,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "order_submission_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(review: dict[str, Any]) -> str:
    summary = _dict(review.get("summary"))
    lines = [
        "# Standing Demo Authorization Refresh Guardrail",
        "",
        f"- Status: `{review.get('status')}`",
        f"- Reason: `{review.get('reason')}`",
        f"- Candidate: `{summary.get('candidate_side_cell_key')}`",
        f"- Old expired: `{summary.get('old_authorization_expired')}`",
        f"- Refreshed cap: `{summary.get('refreshed_resolved_cap_usdt')}`",
        f"- Runtime mutation performed: `{_dict(review.get('answers')).get('runtime_mutation_performed')}`",
        "",
        "## Blocking Gates",
    ]
    blockers = _list(review.get("blocking_gates"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standing-demo-authorization-json", type=Path, required=True)
    parser.add_argument("--runtime-readiness-json", type=Path, required=True)
    parser.add_argument("--account-equity-artifact-json", type=Path, required=True)
    parser.add_argument("--gui-risk-config-toml", type=Path, required=True)
    parser.add_argument("--operator-id")
    parser.add_argument("--max-authorized-probe-orders", type=int)
    parser.add_argument("--authorization-ttl-hours", type=int, default=DEFAULT_AUTHORIZATION_TTL_HOURS)
    parser.add_argument(
        "--max-authorization-ttl-hours",
        type=int,
        default=DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    )
    parser.add_argument(
        "--soak-window-hours",
        type=int,
        default=None,
        help=(
            "demo-only soak-window TTL relaxation in hours (1..96). When set, the "
            "refreshed envelope TTL and the max-TTL guardrail widen to cover a soak "
            "window so learning survives a full soak without a mid-window human "
            "refresh. Omit to keep the 12h default / 24h hard cap unchanged. Does "
            "not touch live/live_demo authorization; this lane is a demo envelope."
        ),
    )
    parser.add_argument(
        "--max-account-equity-artifact-age-seconds",
        type=int,
        default=DEFAULT_MAX_ACCOUNT_EQUITY_ARTIFACT_AGE_SECONDS,
    )
    parser.add_argument(
        "--allow-expired-standing-auth-readiness-only",
        action="store_true",
        help=(
            "Allow refresh to consume a bounded Demo runtime-readiness packet whose "
            "only blocker is the standing auth being expired. Credential, connector, "
            "plan, engine, candidate, and authority blockers still fail closed."
        ),
    )
    parser.add_argument("--runtime-envelope-path", type=Path, default=DEFAULT_RUNTIME_ENVELOPE_PATH)
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    review = build_standing_demo_authorization_refresh_guardrail(
        existing_authorization=_read_json(args.standing_demo_authorization_json),
        runtime_readiness=_read_json(args.runtime_readiness_json),
        account_equity_artifact=_read_json(args.account_equity_artifact_json),
        gui_risk_config=_read_toml(args.gui_risk_config_toml),
        existing_authorization_path=args.standing_demo_authorization_json,
        runtime_readiness_path=args.runtime_readiness_json,
        account_equity_artifact_path=args.account_equity_artifact_json,
        gui_risk_config_path=args.gui_risk_config_toml,
        operator_id=args.operator_id,
        max_authorized_probe_orders=args.max_authorized_probe_orders,
        authorization_ttl_hours=args.authorization_ttl_hours,
        max_authorization_ttl_hours=args.max_authorization_ttl_hours,
        soak_window_hours=args.soak_window_hours,
        max_account_equity_artifact_age_seconds=(
            args.max_account_equity_artifact_age_seconds
        ),
        allow_expired_standing_auth_readiness_only=(
            args.allow_expired_standing_auth_readiness_only
        ),
        runtime_envelope_path=args.runtime_envelope_path,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, review)
    if args.output:
        _write_text(args.output, render_markdown(review))
    if args.print_json:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    elif not args.output and not args.json_output:
        print(render_markdown(review), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
