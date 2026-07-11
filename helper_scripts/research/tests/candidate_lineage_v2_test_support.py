"""Qualified candidate-lineage v2 測試資料工廠 / test-data factory.

這個模組只透過 ``candidate_evaluation_context`` 的公開介面建立、驗證及接合
lineage，讓 board-v2 測試不必複製容易漂移的 hash/schema 細節。
"""

from __future__ import annotations

import copy
import datetime as dt
import json
from collections.abc import Mapping
from typing import Any

from cost_gate_learning_lane.candidate_evaluation_context import (
    EVENT_SCHEMA_VERSION,
    REGIME_BUCKETS,
    attach_candidate_evaluation_context,
    build_candidate_evaluation_context,
    canonical_sha256,
    validate_candidate_evaluation_context,
    validate_candidate_event_context,
)


_DEFAULT_AS_OF_UTC_DATE = "2026-07-10"
_DEFAULT_CAPTURED_AT_MS = int(
    dt.datetime(2026, 7, 9, 12, tzinfo=dt.timezone.utc).timestamp() * 1_000
)
_DEFAULT_REGIME = "neutral|low_vol|liquid"
_BUILD_GIT_SHA = "0123456789abcdef0123456789abcdef01234567"
_EVENT_BOUNDARY = (
    "immutable learning evidence only; no training, serving, promotion, order, "
    "lease, gate, config, broker, or runtime authority"
)
_STABLE_OVERRIDE_FIELDS = {
    "target_regime_context",
    "context_hashes",
    "resource",
    "portfolio",
    "proof",
    "hidden_oos_state",
}
_RESERVED_OUTCOME_FIELDS = {
    "record_type",
    "attempt_id",
    "event_ts_ms",
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "horizon_minutes",
    "candidate_summary",
}


def build_candidate_event_context_v1(
    *,
    context_id: str = "ctx-qualified-lineage-v2-001",
    captured_at_ms: int = _DEFAULT_CAPTURED_AT_MS,
    strategy_name: str = "ma_crossover",
    symbol: str = "BTCUSDT",
    side: str = "Buy",
    horizon_minutes: int = 60,
    evidence_engine_mode: str = "live_demo",
    strategy_version: str = _BUILD_GIT_SHA,
    strategy_params: Mapping[str, Any] | None = None,
    conf_scale: float = 1.0,
) -> dict[str, Any]:
    """建立 canonical raw event，並以 public validator 做完整語意驗證。

    Build one canonical raw event and prove it through the public validator.
    ``context_id`` 與 ``captured_at_ms`` 可讓測試穩定控制 event identity/hash。
    """
    params = copy.deepcopy(
        dict(strategy_params) if strategy_params is not None else {"fast": 5, "slow": 20}
    )
    params_json = json.dumps(
        params,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    strategy_config_hash = canonical_sha256(
        {"strategy_params": params, "conf_scale": conf_scale}
    )
    scan_id = f"scan:{context_id}"
    portfolio_snapshot = {
        "schema_version": "candidate_portfolio_snapshot_v1",
        "captured_at_ms": captured_at_ms,
        "balance": 10_000.0,
        "accepted_demo_equity_usdt": 10_000.0,
        "peak_balance": 10_000.0,
        "drawdown_pct": 0.0,
        "position_count": 0,
        "gross_mark_notional_usdt": 0.0,
        "net_mark_notional_usdt": 0.0,
        "total_realized_pnl": 0.0,
        "total_fees": 0.0,
        "total_funding_pnl": 0.0,
        "trade_count": 0,
    }
    pipeline_kind = "demo" if evidence_engine_mode == "demo" else "live"
    endpoint_environment = "demo" if evidence_engine_mode == "demo" else "live_demo"
    body: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "captured_at_ms": captured_at_ms,
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "build_git_sha": strategy_version,
        "strategy_params_json": params_json,
        "strategy_params_canonical_json": params_json,
        "conf_scale": conf_scale,
        "strategy_config_hash": strategy_config_hash,
        "symbol": symbol,
        "side": side,
        "horizon_policy": {
            "schema_version": "candidate_horizon_policy_v1",
            "source": "OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES",
            "outcome_horizon_minutes": horizon_minutes,
            "default_applied": False,
        },
        "evidence_engine_mode": evidence_engine_mode,
        "pipeline_kind": pipeline_kind,
        "endpoint_environment": endpoint_environment,
        "venue": "bybit",
        "product": "linear_perpetual",
        "context_id": context_id,
        "signal_id": f"signal:{context_id}",
        "scan_id": scan_id,
        "scanner_inputs": {
            "authority_mode": "advisory",
            "legacy_would_block": False,
            "legacy_block_reason": None,
            "scan_id": scan_id,
            "best_strategy": strategy_name,
            "intent_strategy": strategy_name,
            "market_regime": "range",
            "trend_phase": "neutral",
            "trend_score": 0.1,
            "range_score": 0.8,
            "shock_score": 0.0,
            "close_alignment": 0.5,
            "range_position": 0.4,
            "crowding_score": 0.2,
            "reversal_risk_score": 0.1,
            "directional_efficiency": 0.3,
            "dir_pct": 0.2,
            "signed_dir_pct": -0.2,
            "range_pct": 0.6,
            "fr_bps": 0.4,
            "f_ma": 61.0,
            "f_grid": 40.0,
            "f_bbrv": 55.0,
            "f_bkout": 12.0,
            "f_funding_arb": 8.0,
            "edge_bps": -2.5,
            "edge_n": 17,
            "edge_status": "observed",
            "route_mode": "advisory",
            "market_status": "compatible",
            "route_reason": "scanner_candidate",
            "opportunity": None,
            "final_score": 58.0,
            "raw_score": 62.0,
        },
        "market_inputs": {
            "observed_at_ms": captured_at_ms,
            "last_price": 2_500.0,
            "best_bid": 2_499.9,
            "best_ask": 2_500.1,
            "tick_size": 0.1,
            "index_price": 2_499.8,
            "funding_rate": 0.0001,
            "open_interest": 1_000_000.0,
            "atr_value": 25.0,
        },
        "risk_context": {
            "risk_state": "NORMAL",
            "governance_profile": "Validation",
            "risk_config_hash": canonical_sha256({"profile": "test-validation"}),
        },
        "portfolio_snapshot": portfolio_snapshot,
        "portfolio_snapshot_ref": (
            f"paper_state:{evidence_engine_mode}:{context_id}:{captured_at_ms}"
        ),
        "portfolio_snapshot_hash": canonical_sha256(portfolio_snapshot),
        "capture_status": "CAPTURE_COMPLETE",
        "capture_blockers": [],
        "boundary": _EVENT_BOUNDARY,
    }
    event = {**body, "event_hash": canonical_sha256(body)}
    return validate_candidate_event_context(event)


def build_candidate_evaluation_context_v1(
    candidate_event_context: Mapping[str, Any],
    *,
    as_of_utc_date: str = _DEFAULT_AS_OF_UTC_DATE,
    evidence_regime_label: str = _DEFAULT_REGIME,
    stable_projection_overrides: Mapping[str, Any] | None = None,
    daily_bucket_distinct_entries: int = 5,
    require_event_in_window: bool = True,
) -> dict[str, Any]:
    """建立 D-7..D-1 evaluation lineage，支援 deterministic stable-field 變體。

    ``stable_projection_overrides`` only accepts evaluation inputs that survive
    into the stable learning projection.  Derived hashes are always recomputed
    with the public canonical helper; callers cannot smuggle a stale hash.
    """
    event = validate_candidate_event_context(candidate_event_context)
    as_of = _parse_utc_date(as_of_utc_date)
    window_dates = [as_of - dt.timedelta(days=offset) for offset in range(7, 0, -1)]
    event_date = dt.datetime.fromtimestamp(
        event["captured_at_ms"] / 1_000,
        tz=dt.timezone.utc,
    ).date()
    if require_event_in_window and event_date not in window_dates:
        raise ValueError("event captured date must be within evaluation D-7..D-1")
    if (
        isinstance(daily_bucket_distinct_entries, bool)
        or not isinstance(daily_bucket_distinct_entries, int)
        or daily_bucket_distinct_entries < 0
    ):
        raise ValueError("daily_bucket_distinct_entries must be a nonnegative int")

    resource_body: dict[str, Any] = {
        "daily_buckets": [
            {
                "utc_date": day.isoformat(),
                "scan_complete": True,
                "distinct_entries": daily_bucket_distinct_entries,
            }
            for day in window_dates
        ],
        "estimated_rows_scanned": 700,
        "predicted_canonical_bytes": 7_000,
        "zero_resource_attested": False,
    }
    hidden_oos_body: dict[str, Any] = {
        "schema_version": "hidden_oos_state_v1",
        "state": "sealed",
        "open_count": 0,
        "opened_for_iteration": False,
        "consumed": False,
        "invalidated": False,
        "family_id": "qualified-lineage-v2-test-family",
        "split_hash": canonical_sha256({"split": "qualified-lineage-v2-test"}),
    }
    values: dict[str, dict[str, Any]] = {
        "target_regime_context": {
            "label": _DEFAULT_REGIME,
            "utc_date": (as_of - dt.timedelta(days=1)).isoformat(),
            "point_in_time": "D-1",
            "source_complete": True,
            "source_hash": canonical_sha256({"source": "target-regime-test"}),
            "classifier_hash": canonical_sha256({"classifier": "test-v1"}),
        },
        "context_hashes": {
            "data": canonical_sha256({"context": "data"}),
            "evidence": canonical_sha256({"context": "evidence"}),
            "cost": canonical_sha256({"context": "cost"}),
            "portfolio": canonical_sha256({"context": "portfolio"}),
        },
        "resource": resource_body,
        "portfolio": {
            "sector_exposure_share": "0.1",
            "strategy_active_target_share": "0.2",
            "beta_to_portfolio": "-1.5",
        },
        "proof": {
            "proof_stage": 1,
            "completed_proof_stages": [0, 1],
            "next_gap": {"kind": "NONE", "code": "DATA_GATES_READY"},
        },
        "hidden_oos_state": hidden_oos_body,
    }
    _apply_stable_projection_overrides(values, stable_projection_overrides)

    # 為什麼 / Why: resource 與 hidden state 的 derived hashes 必須覆蓋任何
    # fixture 變體，避免測試意外把 invalid hash 當成 qualified lineage。
    resource = values["resource"]
    if "daily_buckets" in resource and [
        item.get("utc_date") if isinstance(item, Mapping) else None
        for item in resource["daily_buckets"]
    ] != [day.isoformat() for day in window_dates]:
        raise ValueError("resource.daily_buckets must remain exact D-7..D-1")
    resource.pop("resource_estimator_hash", None)
    resource["resource_estimator_hash"] = canonical_sha256(resource)
    hidden_oos_state = values["hidden_oos_state"]
    hidden_oos_state.pop("state_hash", None)
    hidden_oos_state["state_hash"] = canonical_sha256(hidden_oos_state)

    regime_entry_counts = {label: 0 for label in (*REGIME_BUCKETS, "unknown")}
    regime_entry_counts[evidence_regime_label] = 30
    evaluation = build_candidate_evaluation_context(
        candidate_event_context=event,
        as_of_utc_date=as_of.isoformat(),
        evidence_regime_label=evidence_regime_label,
        regime_entry_counts=regime_entry_counts,
        target_regime_context=values["target_regime_context"],
        context_hashes=values["context_hashes"],
        resource=resource,
        portfolio=values["portfolio"],
        proof=values["proof"],
        hidden_oos_state=hidden_oos_state,
    )
    return validate_candidate_evaluation_context(evaluation)


def attach_candidate_lineage_v2(
    blocked_signal_outcome: Mapping[str, Any],
    *,
    context_id: str = "ctx-qualified-lineage-v2-001",
    captured_at_ms: int | None = None,
    strategy_name: str = "ma_crossover",
    symbol: str = "BTCUSDT",
    side: str = "Buy",
    horizon_minutes: int = 60,
    as_of_utc_date: str = _DEFAULT_AS_OF_UTC_DATE,
    evidence_regime_label: str = _DEFAULT_REGIME,
    evidence_engine_mode: str = "live_demo",
    strategy_version: str = _BUILD_GIT_SHA,
    strategy_params: Mapping[str, Any] | None = None,
    conf_scale: float = 1.0,
    stable_projection_overrides: Mapping[str, Any] | None = None,
    daily_bucket_distinct_entries: int = 5,
    require_event_in_window: bool = True,
    outcome_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """將 valid raw/evaluation lineage 接到既有 blocked outcome 的 detached copy。

    Attach qualified lineage to a detached copy and enforce exact outer bindings:
    attempt/event timestamp, strategy, symbol, side, horizon, and side-cell key.
    """
    if not isinstance(blocked_signal_outcome, Mapping):
        raise TypeError("blocked_signal_outcome must be a mapping")
    row = copy.deepcopy(dict(blocked_signal_outcome))
    if row.get("record_type") != "blocked_signal_outcome":
        raise ValueError("record_type must be blocked_signal_outcome")
    if outcome_fields is not None:
        if not isinstance(outcome_fields, Mapping):
            raise TypeError("outcome_fields must be a mapping")
        reserved = set(outcome_fields) & _RESERVED_OUTCOME_FIELDS
        if reserved:
            raise ValueError(
                "outcome_fields cannot override lineage bindings: "
                + ", ".join(sorted(reserved))
            )
        row.update(copy.deepcopy(dict(outcome_fields)))

    as_of = _parse_utc_date(as_of_utc_date)
    if captured_at_ms is None:
        captured_at_ms = int(
            dt.datetime.combine(
                as_of - dt.timedelta(days=1),
                dt.time(12),
                tzinfo=dt.timezone.utc,
            ).timestamp()
            * 1_000
        )
    event = build_candidate_event_context_v1(
        context_id=context_id,
        captured_at_ms=captured_at_ms,
        strategy_name=strategy_name,
        symbol=symbol,
        side=side,
        horizon_minutes=horizon_minutes,
        evidence_engine_mode=evidence_engine_mode,
        strategy_version=strategy_version,
        strategy_params=strategy_params,
        conf_scale=conf_scale,
    )
    evaluation = build_candidate_evaluation_context_v1(
        event,
        as_of_utc_date=as_of.isoformat(),
        evidence_regime_label=evidence_regime_label,
        stable_projection_overrides=stable_projection_overrides,
        daily_bucket_distinct_entries=daily_bucket_distinct_entries,
        require_event_in_window=require_event_in_window,
    )
    summary_source = row.get("candidate_summary", {})
    if not isinstance(summary_source, Mapping):
        raise TypeError("candidate_summary must be a mapping when present")
    summary = copy.deepcopy(dict(summary_source))
    summary["candidate_event_context"] = event
    summary["candidate_event_context_status"] = "VALID"
    row["candidate_summary"] = attach_candidate_evaluation_context(
        summary,
        candidate_evaluation_context=evaluation,
    )

    # Exact outer binding is deliberately last / 外層 identity 最後強制綁定。
    row.update(
        {
            "attempt_id": context_id,
            "event_ts_ms": captured_at_ms,
            "strategy_name": strategy_name,
            "symbol": symbol,
            "side": side,
            "horizon_minutes": horizon_minutes,
            "side_cell_key": f"{strategy_name}|{symbol}|{side}",
        }
    )
    row.setdefault("entry_ts_ms", captured_at_ms)
    return row


def _apply_stable_projection_overrides(
    values: dict[str, dict[str, Any]],
    overrides: Mapping[str, Any] | None,
) -> None:
    if overrides is None:
        return
    if not isinstance(overrides, Mapping):
        raise TypeError("stable_projection_overrides must be a mapping")
    unknown = set(overrides) - _STABLE_OVERRIDE_FIELDS
    if unknown:
        raise ValueError(
            "unsupported stable projection overrides: " + ", ".join(sorted(unknown))
        )
    for field, override in overrides.items():
        if not isinstance(override, Mapping):
            raise TypeError(f"stable projection override {field} must be a mapping")
        values[field] = _deep_merge(values[field], override)


def _deep_merge(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _parse_utc_date(value: str) -> dt.date:
    if not isinstance(value, str):
        raise TypeError("as_of_utc_date must be an ISO date string")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("as_of_utc_date must be an ISO date string") from exc
    if parsed.isoformat() != value:
        raise ValueError("as_of_utc_date must be canonical ISO date")
    return parsed


__all__ = [
    "attach_candidate_lineage_v2",
    "build_candidate_evaluation_context_v1",
    "build_candidate_event_context_v1",
]
