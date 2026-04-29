"""Bounded demo applier for ML/Dream edge recommendations.

Consumes ``learning.mlde_shadow_recommendations`` and applies only demo-scoped
parameter changes through Rust IPC. Live/live_demo rows are never applied here;
positive demo evidence emits a governed live ``experiment_plan`` candidate.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

try:
    import psycopg2  # type: ignore
    from psycopg2.extras import DictCursor, Json  # type: ignore
except ImportError:  # pragma: no cover - runtime DB path only
    psycopg2 = None  # type: ignore[assignment]
    DictCursor = None  # type: ignore[assignment]
    Json = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
IpcCall = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class DemoApplierConfig:
    enabled: bool = True
    engine_mode: str = "demo"
    lookback_hours: int = 168
    min_confidence: float = 0.35
    min_samples: int = 5
    max_recommendations: int = 16
    max_param_delta_pct: float = 0.20
    max_risk_delta_pct: float = 0.10
    dedupe_hours: int = 6
    conf_scale_min: float = 0.50
    conf_scale_max: float = 1.80
    rank_conf_scale_step_pct: float = 0.05
    veto_conf_scale_step_pct: float = 0.10
    live_candidate_min_confidence: float = 0.65
    live_candidate_min_samples: int = 30
    live_candidate_min_net_bps: float = 5.0
    dry_run: bool = False


def config_from_env() -> DemoApplierConfig:
    def _bool(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() not in {"0", "false", "no", "off"}

    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, str(default)))
        except ValueError:
            return default
    def _float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, str(default)))
        except ValueError:
            return default
    return DemoApplierConfig(
        enabled=_bool("OPENCLAW_MLDE_DEMO_APPLIER_ENABLED", True),
        engine_mode=os.environ.get("OPENCLAW_MLDE_DEMO_APPLIER_ENGINE", "demo"),
        lookback_hours=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_LOOKBACK_HOURS", 168)),
        min_confidence=max(0.0, min(1.0, _float("OPENCLAW_MLDE_DEMO_APPLIER_MIN_CONFIDENCE", 0.35))),
        min_samples=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_MIN_SAMPLES", 5)),
        max_recommendations=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_MAX_RECOMMENDATIONS", 16)),
        max_param_delta_pct=max(0.01, min(0.95, _float("OPENCLAW_MLDE_DEMO_APPLIER_MAX_PARAM_DELTA_PCT", 0.20))),
        max_risk_delta_pct=max(0.01, min(0.50, _float("OPENCLAW_MLDE_DEMO_APPLIER_MAX_RISK_DELTA_PCT", 0.10))),
        dedupe_hours=max(1, _int("OPENCLAW_MLDE_DEMO_APPLIER_DEDUPE_HOURS", 6)),
        conf_scale_min=max(0.05, _float("OPENCLAW_MLDE_CONF_SCALE_MIN", 0.50)),
        conf_scale_max=max(0.10, _float("OPENCLAW_MLDE_CONF_SCALE_MAX", 1.80)),
        rank_conf_scale_step_pct=max(0.0, min(0.50, _float("OPENCLAW_MLDE_RANK_CONF_SCALE_STEP_PCT", 0.05))),
        veto_conf_scale_step_pct=max(0.0, min(0.50, _float("OPENCLAW_MLDE_VETO_CONF_SCALE_STEP_PCT", 0.10))),
        live_candidate_min_confidence=max(0.0, min(1.0, _float("OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_CONFIDENCE", 0.65))),
        live_candidate_min_samples=max(1, _int("OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_SAMPLES", 30)),
        live_candidate_min_net_bps=_float("OPENCLAW_MLDE_LIVE_CANDIDATE_MIN_NET_BPS", 5.0),
        dry_run=_bool("OPENCLAW_MLDE_DEMO_APPLIER_DRY_RUN", False),
    )


def _resolve_dsn(dsn: Optional[str]) -> Optional[str]:
    return dsn or os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")

def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

def _unwrap_ipc_payload(response: dict[str, Any]) -> Any:
    payload: Any = response.get("result") if isinstance(response, dict) and "result" in response else response
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def _round_step(value: float, step: Any) -> float:
    try:
        s = float(step)
    except (TypeError, ValueError):
        return value
    if s <= 0:
        return value
    return round(value / s) * s

def _bounded_numeric(
    *,
    current: Any,
    desired: Any,
    min_value: float,
    max_value: float,
    step: Any = None,
    max_delta_pct: float,
) -> float | bool | None:
    if isinstance(desired, bool):
        return desired
    try:
        cur = float(current)
        want = float(desired)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(cur) or not math.isfinite(want):
        return None
    if abs(cur) > 1e-12:
        lo = cur * (1.0 - max_delta_pct)
        hi = cur * (1.0 + max_delta_pct)
    else:
        span = max(max_value - min_value, 1.0)
        lo = cur - span * max_delta_pct
        hi = cur + span * max_delta_pct
    delta_lo = min(lo, hi)
    delta_hi = max(lo, hi)
    out = _clamp(_clamp(want, delta_lo, delta_hi), min_value, max_value)
    out = _round_step(out, step)
    out = _clamp(_clamp(out, delta_lo, delta_hi), min_value, max_value)
    return int(out) if isinstance(current, int) and not isinstance(current, bool) else out

def _range_map(ranges: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(r.get("name")): r
        for r in ranges
        if isinstance(r, dict) and r.get("name") and r.get("agent_adjustable", True)
    }

def _desired_from_direction(current: Any, pct: float, direction: str) -> float | None:
    try:
        cur = float(current)
    except (TypeError, ValueError):
        return None
    d = direction.lower()
    if any(token in d for token in ("raise", "widen", "lengthen", "tighten", "increase")):
        return cur * (1.0 + abs(pct))
    if any(token in d for token in ("lower", "reduce", "shorten", "decrease")):
        return cur * (1.0 - abs(pct))
    return cur * (1.0 + pct)

def _derived_strategy_targets(
    strategy_name: str,
    payload: dict[str, Any],
    current: dict[str, Any],
    rec_type: str,
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    if isinstance(payload.get("proposed_params"), dict):
        return dict(payload["proposed_params"])
    if rec_type == "rank":
        cur = float(current.get("conf_scale", 1.0) or 1.0)
        return {"conf_scale": cur * (1.0 + cfg.rank_conf_scale_step_pct)}
    if rec_type == "veto":
        cur = float(current.get("conf_scale", 1.0) or 1.0)
        return {"conf_scale": cur * (1.0 - cfg.veto_conf_scale_step_pct)}

    pct = float(payload.get("suggested_change_pct") or 0.0)
    direction = str(payload.get("direction") or "")
    param_name = str(payload.get("param_name") or "")
    candidates: dict[str, Any] = {}
    def add_if_current(name: str, local_pct: float | None = None, local_direction: str | None = None) -> None:
        if name in current:
            desired = _desired_from_direction(
                current[name],
                pct if local_pct is None else local_pct,
                direction if local_direction is None else local_direction,
            )
            if desired is not None:
                candidates[name] = desired

    if strategy_name == "grid_trading" and param_name in {"grid_spacing_bps", "spacing_bps"}:
        add_if_current("cooldown_ms", pct, "lengthen")
        add_if_current("max_cooldown_boost", pct * 0.5, "raise")
    elif strategy_name == "ma_crossover" and param_name in {"min_hold_seconds", "min_hold_ms"}:
        add_if_current("min_persistence_ms", pct, "lengthen")
        add_if_current("cooldown_ms", pct * 0.5, "lengthen")
    elif strategy_name == "bb_breakout" and param_name == "volume_threshold":
        add_if_current("volume_threshold", pct, "raise")
        add_if_current("min_persistence_ms", pct * 0.5, "lengthen")
    elif strategy_name == "bb_reversion" and param_name in {"exit_conf_base", "confidence_threshold"}:
        add_if_current("confluence_threshold_no_trade", pct, "raise")
        add_if_current("confluence_threshold_full", pct * 0.5, "raise")
    elif strategy_name == "funding_arb" and param_name in {"min_funding_edge_bps", "funding_threshold"}:
        add_if_current("funding_threshold", pct, "raise")
    elif param_name:
        add_if_current(param_name, pct, direction)
    return candidates

def build_strategy_patch(
    *,
    strategy_name: str,
    recommendation_type: str,
    payload: dict[str, Any],
    current_params: dict[str, Any],
    param_ranges: list[dict[str, Any]],
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    desired = _derived_strategy_targets(strategy_name, payload, current_params, recommendation_type, cfg)
    ranges = _range_map(param_ranges)
    patch: dict[str, Any] = {}
    for name, want in desired.items():
        if name == "conf_scale":
            cur = float(current_params.get("conf_scale", 1.0) or 1.0)
            val = _bounded_numeric(
                current=cur,
                desired=want,
                min_value=cfg.conf_scale_min,
                max_value=cfg.conf_scale_max,
                max_delta_pct=cfg.max_param_delta_pct,
            )
        else:
            spec = ranges.get(name)
            if spec is None:
                continue
            val = _bounded_numeric(
                current=current_params.get(name),
                desired=want,
                min_value=float(spec.get("min")),
                max_value=float(spec.get("max")),
                step=spec.get("step"),
                max_delta_pct=cfg.max_param_delta_pct,
            )
        if val is None:
            continue
        if current_params.get(name) != val:
            patch[name] = val
    return patch

def _nested_get(root: dict[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    cur: Any = root
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur

def _put_nested(root: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cur = root
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value

def _bounded_risk_patch(
    raw_patch: dict[str, Any],
    current_risk_config: dict[str, Any],
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    def walk(raw: dict[str, Any], current: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, desired in raw.items():
            cur = current.get(key) if isinstance(current, dict) else None
            next_path = (*path, str(key))
            if isinstance(desired, dict) and isinstance(cur, dict):
                nested = walk(desired, cur, next_path)
                if nested:
                    out[key] = nested
                continue
            if isinstance(desired, bool) and isinstance(cur, bool):
                if desired != cur:
                    out[key] = desired
                continue
            try:
                cur_f = float(cur)
                want_f = float(desired)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(cur_f) or not math.isfinite(want_f):
                continue
            field = next_path[-1]
            min_value = 0.0001 if field == "per_trade_risk_pct" else 0.0
            if field in {"leverage_max", "open_positions_max"}:
                min_value = 1.0
            max_value = max(cur_f * (1.0 + cfg.max_risk_delta_pct), cur_f, min_value)
            bounded = _bounded_numeric(
                current=cur,
                desired=want_f,
                min_value=min_value,
                max_value=max_value,
                step=1.0 if isinstance(cur, int) and not isinstance(cur, bool) else None,
                max_delta_pct=cfg.max_risk_delta_pct,
            )
            if bounded is not None and bounded != cur:
                out[key] = bounded
        return out
    return walk(raw_patch, current_risk_config, ())

def build_risk_patch(
    *,
    payload: dict[str, Any],
    current_risk_config: dict[str, Any],
    recommendation_type: str,
    cfg: DemoApplierConfig,
) -> dict[str, Any]:
    if isinstance(payload.get("risk_patch"), dict):
        return _bounded_risk_patch(dict(payload["risk_patch"]), current_risk_config, cfg)
    if recommendation_type != "regret_summary":
        return {}

    direction = str(payload.get("net_regret_direction") or "balanced")
    if direction not in {"overtrading", "undertrading"}:
        return {}
    sign = -1.0 if direction == "overtrading" else 0.5
    patch: dict[str, Any] = {}
    for path in (
        ("limits", "per_trade_risk_pct"),
        ("limits", "leverage_max"),
        ("limits", "open_positions_max"),
    ):
        cur = _nested_get(current_risk_config, path)
        if cur is None:
            continue
        try:
            cur_f = float(cur)
        except (TypeError, ValueError):
            continue
        desired = cur_f * (1.0 + sign * cfg.max_risk_delta_pct)
        if path[-1] == "open_positions_max":
            desired = max(1, round(desired))
        bounded = _bounded_numeric(
            current=cur,
            desired=desired,
            min_value=1.0 if path[-1] != "per_trade_risk_pct" else 0.001,
            max_value=max(cur_f * (1.0 + cfg.max_risk_delta_pct), cur_f, 1.0),
            step=1.0 if path[-1] == "open_positions_max" else None,
            max_delta_pct=cfg.max_risk_delta_pct,
        )
        if bounded is not None and bounded != cur:
            _put_nested(patch, path, bounded)
    return patch

def should_create_live_candidate(row: dict[str, Any], cfg: DemoApplierConfig) -> bool:
    try:
        expected = float(row.get("expected_net_bps") or 0.0)
        confidence = float(row.get("confidence") or 0.0)
        samples = int(row.get("sample_count") or 0)
    except (TypeError, ValueError):
        return False
    return (
        expected >= cfg.live_candidate_min_net_bps
        and confidence >= cfg.live_candidate_min_confidence
        and samples >= cfg.live_candidate_min_samples
    )

def _fingerprint(kind: str, target: str, patch: dict[str, Any]) -> str:
    payload = json.dumps({"kind": kind, "target": target, "patch": patch}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

async def _default_ipc_call(method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        from exchange_connectors.bybit_connector.control_api_v1.app.ipc_dispatch import (  # type: ignore
            one_shot_ipc_call,
        )
    except ImportError:
        from app.ipc_dispatch import one_shot_ipc_call  # type: ignore
    return await one_shot_ipc_call(
        method,
        params=params,
        timeout=timeout,
        wrap_errors_as_http=False,
        error_context="mlde_demo_applier",
    )

async def _get_strategy_state(ipc_call: IpcCall, engine: str, strategy: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    params_resp = await ipc_call("get_strategy_params", {"engine": engine, "strategy_name": strategy}, 5.0)
    ranges_resp = await ipc_call("get_param_ranges", {"engine": engine, "strategy_name": strategy}, 5.0)
    current = _as_dict(_unwrap_ipc_payload(params_resp))
    ranges_payload = _unwrap_ipc_payload(ranges_resp)
    if isinstance(ranges_payload, str):
        try:
            ranges_payload = json.loads(ranges_payload)
        except json.JSONDecodeError:
            ranges_payload = []
    if isinstance(ranges_payload, dict):
        ranges_payload = ranges_payload.get("ranges", [])
    ranges = ranges_payload if isinstance(ranges_payload, list) else []
    return current, [r for r in ranges if isinstance(r, dict)]

async def _get_risk_config(ipc_call: IpcCall, engine: str) -> dict[str, Any]:
    resp = await ipc_call("get_risk_config", {"engine": engine}, 5.0)
    payload = _unwrap_ipc_payload(resp)
    data = _as_dict(payload)
    return _as_dict(data.get("config", data))

def _fetch_pending(cur: Any, cfg: DemoApplierConfig) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, ts, engine_mode, source, recommendation_type, strategy_name,
               symbol, expected_net_bps, confidence, sample_count, payload
          FROM learning.mlde_shadow_recommendations
         WHERE ts >= now() - (%s::int || ' hours')::interval
           AND engine_mode = %s
           AND NOT applied
           AND COALESCE(confidence, 0.0) >= %s
           AND COALESCE(sample_count, 0) >= %s
         ORDER BY confidence DESC NULLS LAST, sample_count DESC NULLS LAST, ts DESC
         LIMIT %s
        """,
        (cfg.lookback_hours, cfg.engine_mode, cfg.min_confidence, cfg.min_samples, cfg.max_recommendations),
    )
    return [dict(row) for row in cur.fetchall()]

def _already_applied(cur: Any, fingerprint: str, cfg: DemoApplierConfig) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM learning.mlde_param_applications
             WHERE ts >= now() - (%s::int || ' hours')::interval
               AND payload->>'fingerprint' = %s
               AND status IN ('applied', 'dry_run')
        )
        """,
        (cfg.dedupe_hours, fingerprint),
    )
    row = cur.fetchone()
    return bool(row and row[0])

def _record_application(
    cur: Any,
    *,
    row: dict[str, Any],
    application_type: str,
    target_name: str,
    patch: dict[str, Any],
    prev_snapshot: dict[str, Any],
    ipc_response: dict[str, Any],
    status: str,
    reason: str,
    requires_governance: bool,
    payload: dict[str, Any],
) -> int:
    cur.execute(
        """
        INSERT INTO learning.mlde_param_applications
            (engine_mode, recommendation_id, application_type, target_name,
             patch, prev_snapshot, ipc_response, status, reason,
             requires_governance, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            row.get("engine_mode"),
            row.get("id"),
            application_type,
            target_name,
            Json(patch),
            Json(prev_snapshot),
            Json(ipc_response),
            status,
            reason,
            requires_governance,
            Json(payload),
        ),
    )
    return int(cur.fetchone()[0])

def _mark_recommendation_applied(cur: Any, rec_id: int, applied: bool) -> None:
    cur.execute(
        """
        UPDATE learning.mlde_shadow_recommendations
           SET applied = %s,
               requires_governance = CASE WHEN engine_mode IN ('live', 'live_demo') THEN true ELSE false END
         WHERE id = %s
        """,
        (applied, rec_id),
    )

def _insert_live_candidate(
    cur: Any,
    *,
    source_row: dict[str, Any],
    application_id: int,
    application_type: str,
    patch: dict[str, Any],
) -> None:
    payload = {
        "policy": "live_governed_promotion_candidate",
        "source_demo_recommendation_id": source_row.get("id"),
        "source_demo_application_id": application_id,
        "application_type": application_type,
        "patch": patch,
        "requires": ["GovernanceHub", "DecisionLease", "live_gates"],
    }
    cur.execute(
        """
        INSERT INTO learning.mlde_shadow_recommendations
            (engine_mode, symbol, strategy_name, source, recommendation_type,
             primary_metric, expected_net_bps, confidence, sample_count,
             payload, applied, requires_governance, created_by)
        VALUES
            ('live', %s, %s, 'ml_shadow', 'experiment_plan',
             'net_bps_after_fee', %s, %s, %s, %s, false, true,
             'mlde_demo_applier')
        """,
        (
            source_row.get("symbol"),
            source_row.get("strategy_name"),
            source_row.get("expected_net_bps"),
            source_row.get("confidence"),
            source_row.get("sample_count"),
            Json(payload),
        ),
    )

def _record_skip(
    cur: Any,
    *,
    row: dict[str, Any],
    reason: str,
    application_type: str = "strategy_params",
    target_name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _record_application(
        cur,
        row=row,
        application_type=application_type,
        target_name=target_name or str(row.get("strategy_name") or "unknown"),
        patch={},
        prev_snapshot={},
        ipc_response={},
        status="skipped",
        reason=reason,
        requires_governance=False,
        payload=payload or {},
    )
    _mark_recommendation_applied(cur, int(row["id"]), True)
    return {"status": "skipped", "reason": reason}

async def _apply_one(
    cur: Any,
    row: dict[str, Any],
    cfg: DemoApplierConfig,
    ipc_call: IpcCall,
) -> dict[str, Any]:
    payload = _as_dict(row.get("payload"))
    rec_type = str(row.get("recommendation_type") or "")
    strategy = str(row.get("strategy_name") or "")
    if row.get("engine_mode") != cfg.engine_mode or cfg.engine_mode != "demo":
        return _record_skip(cur, row=row, reason="non_demo_engine")
    if rec_type == "regret_summary" or isinstance(payload.get("risk_patch"), dict):
        current_risk = await _get_risk_config(ipc_call, cfg.engine_mode)
        patch = build_risk_patch(
            payload=payload,
            current_risk_config=current_risk,
            recommendation_type=rec_type,
            cfg=cfg,
        )
        kind = "risk_config"
        target = "risk_config"
        prev = current_risk
    else:
        if not strategy or strategy == "unknown":
            return _record_skip(cur, row=row, reason="missing_strategy")
        current_params, ranges = await _get_strategy_state(ipc_call, cfg.engine_mode, strategy)
        patch = build_strategy_patch(
            strategy_name=strategy,
            recommendation_type=rec_type,
            payload=payload,
            current_params=current_params,
            param_ranges=ranges,
            cfg=cfg,
        )
        kind = "strategy_params"
        target = strategy
        prev = current_params
    if not patch:
        return _record_skip(
            cur,
            row=row,
            reason="empty_patch",
            application_type=kind,
            target_name=target,
            payload={"source_payload": payload},
        )
    fp = _fingerprint(kind, target, patch)
    if _already_applied(cur, fp, cfg):
        _record_application(
            cur,
            row=row,
            application_type=kind,
            target_name=target,
            patch=patch,
            prev_snapshot=prev,
            ipc_response={},
            status="skipped",
            reason="dedupe",
            requires_governance=False,
            payload={"fingerprint": fp},
        )
        _mark_recommendation_applied(cur, int(row["id"]), True)
        return {"status": "skipped", "reason": "dedupe"}
    if cfg.dry_run:
        status = "dry_run"
        ipc_response: dict[str, Any] = {"dry_run": True}
    elif kind == "strategy_params":
        ipc_response = await ipc_call(
            "update_strategy_params",
            {
                "engine": cfg.engine_mode,
                "strategy_name": target,
                "params_json": json.dumps(patch, separators=(",", ":")),
            },
            5.0,
        )
        status = "applied"
    else:
        ipc_response = await ipc_call(
            "patch_risk_config",
            {"engine": cfg.engine_mode, "source": "agent", "patch": patch},
            5.0,
        )
        status = "applied"
    app_id = _record_application(
        cur,
        row=row,
        application_type=kind,
        target_name=target,
        patch=patch,
        prev_snapshot=prev,
        ipc_response=ipc_response,
        status=status,
        reason=f"mlde:{row.get('source')}:{rec_type}",
        requires_governance=False,
        payload={"fingerprint": fp, "source_payload": payload},
    )
    _mark_recommendation_applied(cur, int(row["id"]), status in {"applied", "dry_run"})
    live_candidate = False
    if status == "applied" and should_create_live_candidate(row, cfg):
        _insert_live_candidate(
            cur,
            source_row=row,
            application_id=app_id,
            application_type=kind,
            patch=patch,
        )
        _record_application(
            cur,
            row={**row, "engine_mode": "live"},
            application_type="live_promotion_candidate",
            target_name=target,
            patch=patch,
            prev_snapshot={},
            ipc_response={},
            status="candidate",
            reason="positive_demo_evidence_governed_live_candidate",
            requires_governance=True,
            payload={"source_demo_application_id": app_id, "source_demo_recommendation_id": row.get("id")},
        )
        live_candidate = True
    return {"status": status, "application_type": kind, "target": target,
            "patch_keys": sorted(patch.keys()), "live_candidate": live_candidate}

async def _run_async(
    dsn: str,
    cfg: DemoApplierConfig,
    ipc_call: IpcCall,
) -> dict[str, Any]:
    if psycopg2 is None or DictCursor is None or Json is None:
        raise RuntimeError("psycopg2 not installed")
    summary: dict[str, Any] = {
        "enabled": cfg.enabled,
        "engine_mode": cfg.engine_mode,
        "seen": 0,
        "applied": 0,
        "dry_run": 0,
        "skipped": 0,
        "failed": 0,
        "live_candidates": 0,
        "details": [],
    }
    if not cfg.enabled:
        return summary
    if cfg.engine_mode != "demo":
        summary["skipped"] = 1
        summary["details"].append({"status": "skipped", "reason": "non_demo_config"})
        return summary
    with psycopg2.connect(dsn, connect_timeout=2, cursor_factory=DictCursor) as conn:  # pragma: no cover - DB path
        with conn.cursor() as cur:
            rows = _fetch_pending(cur, cfg)
            summary["seen"] = len(rows)
            for row in rows:
                try:
                    result = await _apply_one(cur, row, cfg, ipc_call)
                    status = str(result.get("status") or "skipped")
                    if status == "applied":
                        summary["applied"] += 1
                    elif status == "dry_run":
                        summary["dry_run"] += 1
                    elif status == "skipped":
                        summary["skipped"] += 1
                    else:
                        summary["failed"] += 1
                    if result.get("live_candidate"):
                        summary["live_candidates"] += 1
                    summary["details"].append(result)
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    summary["failed"] += 1
                    summary["details"].append({"status": "failed", "recommendation_id": row.get("id"), "error": str(exc)})
                    try:
                        _record_application(
                            cur,
                            row=row,
                            application_type="strategy_params",
                            target_name=str(row.get("strategy_name") or "unknown"),
                            patch={},
                            prev_snapshot={},
                            ipc_response={},
                            status="failed",
                            reason=str(exc),
                            requires_governance=False,
                            payload={},
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()
    return summary

def run_mlde_demo_applier(
    dsn: Optional[str] = None,
    cfg: Optional[DemoApplierConfig] = None,
    *,
    ipc_call: Optional[IpcCall] = None,
) -> dict[str, Any]:
    cfg = cfg or config_from_env()
    resolved = _resolve_dsn(dsn)
    if not resolved:
        return {"enabled": cfg.enabled, "skipped": "no_database_url", "applied": 0}
    return asyncio.run(_run_async(resolved, cfg, ipc_call or _default_ipc_call))
